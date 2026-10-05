"""Leitura e validação das configurações (variáveis de ambiente / .env)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

# Carrega o .env (se existir) sem sobrescrever variáveis já definidas no ambiente.
load_dotenv()


def _get_str(name: str, default: str = "") -> str:
    value = os.getenv(name)
    return value.strip() if value is not None else default


def _get_int(name: str, default: int) -> int:
    raw = _get_str(name)
    if not raw:
        return default
    try:
        return int(raw)
    except ValueError:
        return default


# --- Telegram ---------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = _get_str("TELEGRAM_BOT_TOKEN")

# Aceita IDs separados por vírgula, ponto e vírgula ou espaço.
_raw_ids = _get_str("ALLOWED_TELEGRAM_IDS").replace(";", ",").replace(" ", ",")
ALLOWED_TELEGRAM_IDS: set[int] = {
    int(part) for part in (p.strip() for p in _raw_ids.split(",")) if part.isdigit()
}

# --- Geral ------------------------------------------------------------------
TIMEZONE: str = _get_str("TIMEZONE", "America/Sao_Paulo")
LOG_LEVEL: str = _get_str("LOG_LEVEL", "INFO").upper()
DATABASE_PATH: str = _get_str("DATABASE_PATH", "data/agenda.db")

# --- Google Calendar --------------------------------------------------------
GOOGLE_CALENDAR_ID: str = _get_str("GOOGLE_CALENDAR_ID", "primary")
GOOGLE_TOKEN_FILE: str = _get_str("GOOGLE_TOKEN_FILE", "token.json")
GOOGLE_TOKEN_JSON: str = _get_str("GOOGLE_TOKEN_JSON")
GOOGLE_CLIENT_SECRET_FILE: str = _get_str("GOOGLE_CLIENT_SECRET_FILE", "client_secret.json")
GOOGLE_SERVICE_ACCOUNT_FILE: str = _get_str("GOOGLE_SERVICE_ACCOUNT_FILE")
GOOGLE_SERVICE_ACCOUNT_JSON: str = _get_str("GOOGLE_SERVICE_ACCOUNT_JSON")

# --- Comportamento ----------------------------------------------------------
DEFAULT_EVENT_DURATION_MIN: int = _get_int("DEFAULT_EVENT_DURATION_MIN", 60)
DEFAULT_EVENT_TIME: str = _get_str("DEFAULT_EVENT_TIME", "09:00")
REMINDER_LEAD_MINUTES: int = _get_int("REMINDER_LEAD_MINUTES", 30)
REMINDER_CHECK_INTERVAL_SECONDS: int = _get_int("REMINDER_CHECK_INTERVAL_SECONDS", 60)
ALL_DAY_REMINDER_TIME: str = _get_str("ALL_DAY_REMINDER_TIME", "08:00")
# Limpeza automática da conversa (apaga as mensagens do chat periodicamente).
AUTOCLEAN_MINUTES: int = _get_int("AUTOCLEAN_MINUTES", 30)
AUTOCLEAN_ENABLED: bool = _get_str("AUTOCLEAN_ENABLED", "true").lower() not in {"0", "false", "no"}


def has_google_credentials() -> bool:
    return bool(
        GOOGLE_TOKEN_JSON
        or GOOGLE_SERVICE_ACCOUNT_JSON
        or os.path.exists(GOOGLE_TOKEN_FILE)
        or (GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(GOOGLE_SERVICE_ACCOUNT_FILE))
    )


def validate() -> list[str]:
    """Falha (com mensagem clara) se faltar o essencial; devolve avisos não fatais."""
    problems: list[str] = []
    if not TELEGRAM_BOT_TOKEN:
        problems.append(
            "TELEGRAM_BOT_TOKEN não definido. Gere um token com o @BotFather no Telegram."
        )
    if not ALLOWED_TELEGRAM_IDS:
        problems.append(
            "ALLOWED_TELEGRAM_IDS não definido. Envie /id para o seu bot e coloque o número aqui "
            "(sem isso, qualquer pessoa poderia usar sua agenda)."
        )
    if problems:
        raise SystemExit("Configuração incompleta:\n- " + "\n- ".join(problems))

    warnings: list[str] = []
    if not has_google_credentials():
        warnings.append(
            "Google Calendar ainda não configurado. Os comandos de agenda vão avisar "
            "até você rodar 'python authorize_google.py' (ou configurar uma service account)."
        )
    return warnings
