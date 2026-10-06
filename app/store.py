"""Armazenamento dos usuários usando um repositório privado do GitHub como banco.

Como o plano gratuito do Render não tem disco, guardamos um arquivo JSON
(``GITHUB_DATA_PATH``) em um repositório privado, acessado pela API de Contents
do GitHub. Os tokens sensíveis do Google são criptografados antes de gravar.

Formato do arquivo::

    {"users": {"<telegram_id>": {...}}}
"""

from __future__ import annotations

import base64
import hashlib
import json
import logging
import threading
import time

import requests
from cryptography.fernet import Fernet

from . import config

logger = logging.getLogger(__name__)

_lock = threading.RLock()
_cache: dict | None = None
_cache_sha: str | None = None


# --- Criptografia -----------------------------------------------------------
def _fernet() -> Fernet:
    key = base64.urlsafe_b64encode(
        hashlib.sha256(config.APP_ENCRYPTION_KEY.encode("utf-8")).digest()
    )
    return Fernet(key)


def encrypt(value: str | None) -> str | None:
    if not value:
        return value
    return _fernet().encrypt(value.encode("utf-8")).decode("ascii")


def decrypt(value: str | None) -> str | None:
    if not value:
        return value
    try:
        return _fernet().decrypt(value.encode("ascii")).decode("utf-8")
    except Exception:  # noqa: BLE001
        return None


# --- API do GitHub ----------------------------------------------------------
def _headers() -> dict:
    return {
        "Authorization": f"Bearer {config.GITHUB_DATA_TOKEN}",
        "Accept": "application/vnd.github+json",
    }


def _contents_url() -> str:
    return (
        f"https://api.github.com/repos/{config.GITHUB_DATA_REPO}"
        f"/contents/{config.GITHUB_DATA_PATH}"
    )


def _load_remote() -> tuple[dict, str | None]:
    resp = requests.get(
        _contents_url(),
        headers=_headers(),
        params={"ref": config.GITHUB_DATA_BRANCH},
        timeout=30,
    )
    if resp.status_code == 404:
        return {"users": {}}, None
    resp.raise_for_status()
    data = resp.json()
    raw = base64.b64decode(data["content"]).decode("utf-8")
    payload = json.loads(raw) if raw.strip() else {"users": {}}
    payload.setdefault("users", {})
    return payload, data.get("sha")


def _save_remote(payload: dict, sha: str | None) -> str | None:
    body = {
        "message": "atualiza dados da agenda",
        "content": base64.b64encode(
            json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
        ).decode("ascii"),
        "branch": config.GITHUB_DATA_BRANCH,
    }
    if sha:
        body["sha"] = sha
    resp = requests.put(_contents_url(), headers=_headers(), json=body, timeout=30)
    resp.raise_for_status()
    return resp.json().get("content", {}).get("sha")


def _ensure_loaded() -> None:
    global _cache, _cache_sha
    if _cache is None:
        try:
            _cache, _cache_sha = _load_remote()
        except Exception as exc:  # noqa: BLE001
            logger.exception("Falha ao carregar o banco do GitHub: %s", exc)
            _cache, _cache_sha = {"users": {}}, None


def _persist() -> None:
    global _cache_sha
    assert _cache is not None
    try:
        _cache_sha = _save_remote(_cache, _cache_sha)
    except requests.HTTPError as exc:
        # Provável conflito de SHA: recarrega e tenta de novo uma vez.
        logger.warning("Conflito ao gravar no GitHub (%s); recarregando...", exc)
        _cache_fresh, sha = _load_remote()
        for tid, user in _cache["users"].items():
            _cache_fresh["users"][tid] = user
        _cache.clear()
        _cache.update(_cache_fresh)
        _cache_sha = _save_remote(_cache, sha)


# --- API pública ------------------------------------------------------------
def reload() -> None:
    global _cache, _cache_sha
    with _lock:
        _cache, _cache_sha = _load_remote()


def all_users() -> dict[str, dict]:
    with _lock:
        _ensure_loaded()
        return {k: dict(v) for k, v in _cache["users"].items()}


def get_user(telegram_id: int | str) -> dict | None:
    with _lock:
        _ensure_loaded()
        user = _cache["users"].get(str(telegram_id))
        return dict(user) if user else None


def save_user(telegram_id: int | str, data: dict) -> None:
    with _lock:
        _ensure_loaded()
        _cache["users"][str(telegram_id)] = data
        _persist()


def update_user(telegram_id: int | str, **fields) -> dict:
    with _lock:
        _ensure_loaded()
        key = str(telegram_id)
        fields.pop("telegram_id", None)
        user = _cache["users"].setdefault(key, {})
        user.update(fields)
        user["telegram_id"] = int(telegram_id) if str(telegram_id).lstrip("-").isdigit() else telegram_id
        user["updated_at"] = int(time.time())
        _persist()
        return dict(user)


def delete_user(telegram_id: int | str) -> None:
    with _lock:
        _ensure_loaded()
        _cache["users"].pop(str(telegram_id), None)
        _persist()
