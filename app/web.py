"""Servidor web: health-check + fluxo OAuth do Google por usuário.

Rotas:
  ``/``                       health-check (Render)
  ``/oauth/start?t=<token>``  inicia a conexão do Google
  ``/oauth/callback``         recebe o código do Google e guarda os tokens
  ``/oauth/success``          página de sucesso
"""

from __future__ import annotations

import asyncio
import logging
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from urllib.parse import parse_qs, urlparse

import requests

from . import config, store
from .services import auth, google_oauth

logger = logging.getLogger(__name__)

# Tokens de conexão pendentes: token -> (telegram_id, expira_em)
_pending: dict[str, tuple[int, float]] = {}
_pending_lock = threading.Lock()
_TTL = 15 * 60


def create_connect_link(telegram_id: int) -> str:
    token = secrets.token_urlsafe(24)
    with _pending_lock:
        _pending[token] = (int(telegram_id), time.time() + _TTL)
    return f"{config.APP_BASE_URL.rstrip('/')}/oauth/start?t={token}"


def _consume(token: str) -> int | None:
    with _pending_lock:
        entry = _pending.get(token)
        if not entry:
            return None
        telegram_id, expiry = entry
        if expiry < time.time():
            _pending.pop(token, None)
            return None
        return telegram_id


_SUCESSO = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>Conectado!</title></head><body style="font-family:sans-serif;text-align:center;margin-top:80px">
<h1>&#9989; Google conectado!</h1>
<p>Pronto. Volte para o <b>Telegram</b> e use os comandos, por exemplo:</p>
<p><code>/novo Dentista amanhã às 14h</code></p></body></html>"""

_ERRO = """<!doctype html><html lang="pt-br"><head><meta charset="utf-8">
<title>Erro</title></head><body style="font-family:sans-serif;text-align:center;margin-top:80px">
<h1>&#10060; Algo deu errado</h1><p>{msg}</p>
<p>Volte ao Telegram e envie <code>/conectar</code> novamente.</p></body></html>"""


class _Handler(BaseHTTPRequestHandler):
    def _send(self, code: int, body: str, ctype: str) -> None:
        data = body.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", ctype)
        self.send_header("Content-Length", str(len(data)))
        self.end_headers()
        self.wfile.write(data)

    def _redirect(self, location: str) -> None:
        self.send_response(302)
        self.send_header("Location", location)
        self.end_headers()

    def do_GET(self) -> None:  # noqa: N802
        parsed = urlparse(self.path)
        path = parsed.path.rstrip("/") or "/"
        query = parse_qs(parsed.query)
        try:
            if path in ("/", "/health"):
                self._send(200, "agenda-bot: ok\n", "text/plain; charset=utf-8")
            elif path == "/oauth/start":
                self._oauth_start(query)
            elif path == config.OAUTH_REDIRECT_PATH.rstrip("/"):
                self._oauth_callback(query)
            elif path == "/oauth/success":
                self._send(200, _SUCESSO, "text/html; charset=utf-8")
            else:
                self._send(404, "not found\n", "text/plain; charset=utf-8")
        except Exception as exc:  # noqa: BLE001
            logger.exception("Erro no servidor web")
            self._send(500, _ERRO.format(msg=str(exc)), "text/html; charset=utf-8")

    def _oauth_start(self, query: dict) -> None:
        token = (query.get("t") or [""])[0]
        telegram_id = _consume(token)
        if not telegram_id:
            self._send(
                400,
                _ERRO.format(msg="Link expirado ou inválido."),
                "text/html; charset=utf-8",
            )
            return
        if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
            self._send(
                500,
                _ERRO.format(msg="O bot ainda não foi configurado pelo administrador."),
                "text/html; charset=utf-8",
            )
            return
        url = google_oauth.authorization_url(state=token)
        self._redirect(url)

    def _oauth_callback(self, query: dict) -> None:
        if query.get("error"):
            self._send(
                200,
                _ERRO.format(msg=f"Autorização negada: {query['error'][0]}"),
                "text/html; charset=utf-8",
            )
            return
        code = (query.get("code") or [""])[0]
        state = (query.get("state") or [""])[0]
        telegram_id = _consume(state)
        if not code or not telegram_id:
            self._send(
                400,
                _ERRO.format(msg="Resposta inválida do Google."),
                "text/html; charset=utf-8",
            )
            return

        creds = google_oauth.exchange_code(code)
        email = google_oauth.fetch_email(creds)

        record = store.get_user(telegram_id) or {}
        record.update(
            {
                "telegram_id": telegram_id,
                "refresh_token": store.encrypt(creds.refresh_token),
                "access_token": store.encrypt(creds.token),
                "email": email,
                "connected_at": int(time.time()),
            }
        )
        store.save_user(telegram_id, record)
        auth.invalidate(telegram_id)

        with _pending_lock:
            _pending.pop(state, None)

        _notify_telegram(telegram_id, email)
        self._redirect("/oauth/success")

    def log_message(self, *args) -> None:  # silencia logs do servidor
        pass


def _notify_telegram(telegram_id: int, email: str | None) -> None:
    if not config.TELEGRAM_BOT_TOKEN:
        return
    try:
        requests.post(
            f"https://api.telegram.org/bot{config.TELEGRAM_BOT_TOKEN}/sendMessage",
            json={
                "chat_id": telegram_id,
                "text": (
                    "✅ *Google conectado!*"
                    + (f"\nConta: `{email}`" if email else "")
                    + "\n\nJá pode usar:\n`/novo Dentista amanhã às 14h`\n`/hoje`"
                ),
                "parse_mode": "Markdown",
            },
            timeout=30,
        )
    except requests.RequestException:
        logger.warning("Não foi possível avisar o usuário %s no Telegram.", telegram_id)


def start_web_server() -> ThreadingHTTPServer | None:
    port = int(os.getenv("PORT", "0") or 0)
    if not port:
        return None
    server = ThreadingHTTPServer(("0.0.0.0", port), _Handler)
    threading.Thread(target=server.serve_forever, daemon=True).start()
    logger.info("Servidor web ouvindo na porta %s (redirect: %s)", port, config.redirect_uri())
    return server


async def self_ping_job(context) -> None:
    """Acessa a própria URL para não dormir (plano grátis do Render)."""
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        return
    try:
        await asyncio.to_thread(lambda: requests.get(url, timeout=30))
        logger.info("Auto-ping OK (%s)", url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto-ping falhou: %s", exc)
