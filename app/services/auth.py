"""Obtém e mantém credenciais válidas do Google para cada usuário."""

from __future__ import annotations

import logging
import threading
import time

from . import google_oauth
from .. import store

logger = logging.getLogger(__name__)

_lock = threading.Lock()
_cache: dict[str, tuple[object, float]] = {}  # telegram_id -> (creds, expira_em)


def credentials_for(record: dict):
    """Devolve credenciais válidas para o usuário (renovando o token se preciso)."""
    telegram_id = str(record.get("telegram_id") or record.get("id"))
    with _lock:
        cached = _cache.get(telegram_id)
        if cached and cached[1] > time.time() + 120:
            return cached[0]

    refresh_token = store.decrypt(record.get("refresh_token"))
    if not refresh_token:
        raise RuntimeError("Conta do Google não conectada.")

    creds = google_oauth.credentials_from_refresh(refresh_token)
    with _lock:
        _cache[telegram_id] = (creds, time.time() + 3300)  # ~55 min

    try:
        store.update_user(telegram_id, access_token=store.encrypt(creds.token))
    except Exception:  # noqa: BLE001
        logger.warning("Não foi possível persistir o access_token.")
    return creds


def invalidate(telegram_id) -> None:
    with _lock:
        _cache.pop(str(telegram_id), None)
