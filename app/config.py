"""Leitura e validação das configurações (variáveis de ambiente / .env)."""

from __future__ import annotations

import os

from dotenv import load_dotenv

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


def _get_ids(name: str) -> set[int]:
    raw = _get_str(name).replace(";", ",").replace(" ", ",")
    return {int(p) for p in (x.strip() for x in raw.split(",")) if p.isdigit()}


# --- Telegram ---------------------------------------------------------------
TELEGRAM_BOT_TOKEN: str = _get_str("TELEGRAM_BOT_TOKEN")
# Lista de admins (opcional). Se vazia, ninguém tem comandos de admin.
ADMIN_TELEGRAM_IDS: set[int] = _get_ids("ADMIN_TELEGRAM_IDS")

# --- Geral ------------------------------------------------------------------
TIMEZONE: str = _get_str("TIMEZONE", "America/Sao_Paulo")
LOG_LEVEL: str = _get_str("LOG_LEVEL", "INFO").upper()
DATABASE_PATH: str = _get_str("DATABASE_PATH", "data/agenda.db")
DEFAULT_EVENT_DURATION_MIN: int = _get_int("DEFAULT_EVENT_DURATION_MIN", 60)
DEFAULT_EVENT_TIME: str = _get_str("DEFAULT_EVENT_TIME", "09:00")
REMINDER_LEAD_MINUTES: int = _get_int("REMINDER_LEAD_MINUTES", 30)
REMINDER_CHECK_INTERVAL_SECONDS: int = _get_int("REMINDER_CHECK_INTERVAL_SECONDS", 90)
ALL_DAY_REMINDER_TIME: str = _get_str("ALL_DAY_REMINDER_TIME", "08:00")
AUTOCLEAN_MINUTES: int = _get_int("AUTOCLEAN_MINUTES", 30)
AUTOCLEAN_ENABLED: bool = _get_str("AUTOCLEAN_ENABLED", "true").lower() not in {
    "0",
    "false",
    "no",
}

# --- OAuth Web do Google ----------------------------------------------------
# URL pública do serviço (no Render é definido automaticamente).
APP_BASE_URL: str = (
    _get_str("APP_BASE_URL")
    or os.getenv("RENDER_EXTERNAL_URL", "").strip().rstrip("/")
    or "http://localhost:8080"
)
OAUTH_REDIRECT_PATH: str = _get_str("OAUTH_REDIRECT_PATH", "/oauth/callback")
GOOGLE_CLIENT_ID: str = _get_str("GOOGLE_CLIENT_ID")
GOOGLE_CLIENT_SECRET: str = _get_str("GOOGLE_CLIENT_SECRET")

# --- Banco de dados (GitHub) ------------------------------------------------
GITHUB_DATA_REPO: str = _get_str("GITHUB_DATA_REPO")
GITHUB_DATA_TOKEN: str = _get_str("GITHUB_DATA_TOKEN")
GITHUB_DATA_PATH: str = _get_str("GITHUB_DATA_PATH", "users.json")
GITHUB_DATA_BRANCH: str = _get_str("GITHUB_DATA_BRANCH", "main")
# Chave para criptografar os tokens do Google guardados no repositório.
APP_ENCRYPTION_KEY: str = _get_str("APP_ENCRYPTION_KEY", "troque-esta-chave-de-criptografia")
GOOGLE_SERVICE_ACCOUNT_FILE: str = _get_str("GOOGLE_SERVICE_ACCOUNT_FILE")


def redirect_uri() -> str:
    return APP_BASE_URL.rstrip("/") + OAUTH_REDIRECT_PATH


def validate() -> list[str]:
    """Falha se faltar o essencial; devolve avisos não fatais."""
    problems: list[str] = []
    if not TELEGRAM_BOT_TOKEN:
        problems.append("TELEGRAM_BOT_TOKEN não definido (gere no @BotFather).")
    if problems:
        raise SystemExit("Configuração incompleta:\n- " + "\n- ".join(problems))

    warnings: list[str] = []
    if not (GOOGLE_CLIENT_ID and GOOGLE_CLIENT_SECRET):
        warnings.append(
            "GOOGLE_CLIENT_ID/SECRET não definidos: os usuários não conseguirão conectar "
            "o Google. Crie um cliente OAuth do tipo 'Aplicação Web'."
        )
    if not (GITHUB_DATA_REPO and GITHUB_DATA_TOKEN):
        warnings.append(
            "GITHUB_DATA_REPO/GITHUB_DATA_TOKEN não definidos: não há onde guardar os "
            "dados dos usuários."
        )
    return warnings
