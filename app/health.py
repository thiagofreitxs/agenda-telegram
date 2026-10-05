"""Pequeno servidor HTTP de health-check.

Algumas hospedagens (Render, Koyeb, etc.) esperam que o serviço abra uma porta
na variável de ambiente ``PORT``. Este servidor responde 200 OK e mantém o bot
"vivo" nesses planos, sem interferir no polling do Telegram.
"""

from __future__ import annotations

import asyncio
import logging
import os
import threading
from http.server import BaseHTTPRequestHandler, HTTPServer

import requests

logger = logging.getLogger(__name__)

_CORPO = b"agenda-bot: ok\n"


class _Handler(BaseHTTPRequestHandler):
    def do_GET(self) -> None:  # noqa: N802
        self.send_response(200)
        self.send_header("Content-Type", "text/plain; charset=utf-8")
        self.send_header("Content-Length", str(len(_CORPO)))
        self.end_headers()
        self.wfile.write(_CORPO)

    def do_HEAD(self) -> None:  # noqa: N802
        self.send_response(200)
        self.end_headers()

    def log_message(self, *args) -> None:  # silencia o log
        pass


def start_health_server() -> HTTPServer | None:
    """Inicia o health-check se a variável PORT estiver definida."""
    port = os.getenv("PORT")
    if not port:
        return None
    try:
        server = HTTPServer(("0.0.0.0", int(port)), _Handler)
    except (ValueError, OSError) as exc:
        logger.warning("Não foi possível abrir o health-check na porta %s: %s", port, exc)
        return None

    thread = threading.Thread(target=server.serve_forever, daemon=True)
    thread.start()
    logger.info("Health-check ouvindo na porta %s", port)
    return server


async def self_ping_job(context) -> None:
    """Faz o serviço acessar a própria URL pública para não dormir (Render free).

    O Render disponibiliza a variável RENDER_EXTERNAL_URL automaticamente.
    """
    url = os.getenv("RENDER_EXTERNAL_URL")
    if not url:
        return
    try:
        await asyncio.to_thread(lambda: requests.get(url, timeout=30))
        logger.info("Auto-ping OK (%s)", url)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Auto-ping falhou: %s", exc)
