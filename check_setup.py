"""Verifica se o bot multiusuário está configurado corretamente.

Uso:  .venv\\Scripts\\python.exe check_setup.py
"""

from __future__ import annotations

import sys

from app import config, store

OK = "[OK]"
WARN = "[!!]"
FAIL = "[XX]"


def _line(status: str, texto: str) -> None:
    print(f" {status}  {texto}")


def main() -> int:
    print("=" * 60)
    print(" VERIFICACAO - AGENDA MULTIUSUARIO")
    print("=" * 60)
    print(f" Python: {sys.version.split()[0]}")

    ok = True

    print("\n== Telegram ==")
    if config.TELEGRAM_BOT_TOKEN and "Exemplo" not in config.TELEGRAM_BOT_TOKEN:
        _line(OK, "TELEGRAM_BOT_TOKEN preenchido.")
    else:
        _line(FAIL, "TELEGRAM_BOT_TOKEN ausente.")
        ok = False

    print("\n== OAuth do Google (por usuario) ==")
    if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
        _line(OK, "GOOGLE_CLIENT_ID / SECRET preenchidos.")
    else:
        _line(FAIL, "GOOGLE_CLIENT_ID / SECRET ausentes.")
        ok = False
    _line(OK, f"URL publica: {config.APP_BASE_URL}")
    _line(OK, f"Redirect URI: {config.redirect_uri()}")
    print("       (cadastre exatamente esta URL no cliente OAuth 'Aplicacao Web')")
    if config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET:
        try:
            from app.services import google_oauth

            url = google_oauth.authorization_url("teste")
            _line(OK, f"URL de autorizacao gerada ({len(url)} chars).")
        except Exception as exc:  # noqa: BLE001
            _line(FAIL, f"Erro ao gerar URL de autorizacao: {exc}")
            ok = False

    print("\n== Banco de dados (GitHub) ==")
    if config.GITHUB_DATA_REPO and config.GITHUB_DATA_TOKEN:
        _line(OK, f"Repositorio: {config.GITHUB_DATA_REPO}/{config.GITHUB_DATA_PATH}")
        try:
            users = store.all_users()
            _line(OK, f"Conexao OK. {len(users)} usuario(s) cadastrado(s).")
        except Exception as exc:  # noqa: BLE001
            _line(FAIL, f"Falha ao acessar o banco: {exc}")
            ok = False
    else:
        _line(FAIL, "GITHUB_DATA_REPO / GITHUB_DATA_TOKEN ausentes.")
        ok = False

    print("\n" + "=" * 60)
    if ok:
        print(" TUDO PRONTO! Inicie com: python -m app.main")
        return 0
    print(" Faltam passos (itens com [XX]).")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
