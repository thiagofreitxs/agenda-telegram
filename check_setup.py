"""Verifica se o projeto está pronto para rodar.

Uso:
    .venv\\Scripts\\python.exe check_setup.py
    .venv\\Scripts\\python.exe check_setup.py --google   (testa de verdade a agenda)
"""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timedelta

from app import config

OK = "[OK]"
WARN = "[!!]"
FAIL = "[XX]"


def _line(status: str, texto: str) -> None:
    print(f" {status}  {texto}")


def check_env() -> bool:
    print("\n== Configuracao do .env ==")
    tudo_ok = True

    if os.path.exists(".env"):
        _line(OK, "Arquivo .env encontrado.")
    else:
        _line(WARN, "Nao existe .env (copie de .env.example).")
        tudo_ok = False

    token = config.TELEGRAM_BOT_TOKEN
    if token and ":" in token and len(token) > 30 and "Exemplo" not in token:
        _line(OK, f"TELEGRAM_BOT_TOKEN preenchido ({token[:10]}...).")
    else:
        _line(FAIL, "TELEGRAM_BOT_TOKEN ausente ou ainda com o valor de exemplo.")
        tudo_ok = False

    if config.ALLOWED_TELEGRAM_IDS and config.ALLOWED_TELEGRAM_IDS != {123456789}:
        _line(OK, f"ALLOWED_TELEGRAM_IDS: {sorted(config.ALLOWED_TELEGRAM_IDS)}")
    else:
        _line(FAIL, "ALLOWED_TELEGRAM_IDS vazio ou ainda com o exemplo (123456789). "
                    "Envie /id ao bot para descobrir o seu.")
        tudo_ok = False

    _line(OK, f"TIMEZONE: {config.TIMEZONE}")
    _line(OK, f"Calendario alvo: {config.GOOGLE_CALENDAR_ID}")
    return tudo_ok


def check_google() -> bool:
    print("\n== Credenciais do Google ==")
    fontes = []
    if config.GOOGLE_TOKEN_JSON:
        fontes.append("GOOGLE_TOKEN_JSON (variavel)")
    if os.path.exists(config.GOOGLE_TOKEN_FILE):
        fontes.append(config.GOOGLE_TOKEN_FILE)
    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        fontes.append("GOOGLE_SERVICE_ACCOUNT_JSON (variavel)")
    if config.GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(
        config.GOOGLE_SERVICE_ACCOUNT_FILE
    ):
        fontes.append(config.GOOGLE_SERVICE_ACCOUNT_FILE)

    if not fontes:
        _line(FAIL, "Nenhuma credencial encontrada.")
        _line(OK, "Rode:  python authorize_google.py")
        return False

    _line(OK, "Credencial presente: " + ", ".join(fontes))
    from app.services import calendar_service as cs

    try:
        cs._load_credentials()
        _line(OK, "Credencial carregada com sucesso.")
        return True
    except cs.CalendarError as exc:
        _line(FAIL, f"Erro ao carregar credencial: {exc}")
        return False


def check_google_live() -> bool:
    print("\n== Teste real no Google Calendar ==")
    from app.services import calendar_service as cs

    agora = datetime.now()
    try:
        eventos = cs.list_events(agora, agora + timedelta(days=7), 10)
    except cs.CalendarError as exc:
        _line(FAIL, f"Falha ao consultar a agenda: {exc}")
        return False
    _line(OK, f"Conexao OK. {len(eventos)} evento(s) nos proximos 7 dias.")
    for evento in eventos[:5]:
        _line(OK, f"  - {evento.start:%d/%m %H:%M} {evento.summary}")
    return True


def main() -> int:
    parser = argparse.ArgumentParser(description="Verifica a configuracao da agenda.")
    parser.add_argument(
        "--google", action="store_true", help="Faz uma chamada real ao Google Calendar."
    )
    args = parser.parse_args()

    print("=" * 55)
    print(" VERIFICACAO DO SETUP - AGENDA TELEGRAM + GOOGLE")
    print("=" * 55)
    print(f" Python: {sys.version.split()[0]}")

    env_ok = check_env()
    google_ok = check_google()

    if args.google and google_ok:
        check_google_live()

    print("\n" + "=" * 55)
    if env_ok and google_ok:
        print(" TUDO PRONTO! Inicie com:  python -m app.main")
        return 0
    print(" Faltam passos. Corrija os itens marcados com [XX] acima.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
