"""Limpeza automática da conversa do Telegram (por usuário)."""

from __future__ import annotations

import asyncio
import logging

from telegram import Update
from telegram.ext import ContextTypes

from .. import config, db, store

logger = logging.getLogger(__name__)

_JANELA = 200
_MARGEM = 50


def _last_key(chat_id: int) -> str:
    return f"last_msg_{chat_id}"


async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Registra a última mensagem vista em cada chat."""
    message = update.effective_message
    chat = update.effective_chat
    if message is None or chat is None:
        return
    try:
        current = int(db.get_setting(_last_key(chat.id), "0") or 0)
    except (TypeError, ValueError):
        current = 0
    if message.message_id > current:
        db.set_setting(_last_key(chat.id), str(message.message_id))


async def autoclean_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    if config.AUTOCLEAN_MINUTES <= 0:
        return
    users = await asyncio.to_thread(store.all_users)
    for tid, record in users.items():
        if record.get("autoclean", "1") != "1":
            continue
        try:
            chat_id = int(tid)
        except (TypeError, ValueError):
            continue
        try:
            last = int(db.get_setting(_last_key(chat_id), "0") or 0)
        except (TypeError, ValueError):
            last = 0
        if last <= 0:
            continue

        inicio = max(1, last - _JANELA)
        fim = last + _MARGEM
        apagadas = 0
        for message_id in range(inicio, fim + 1):
            try:
                await context.bot.delete_message(chat_id=chat_id, message_id=message_id)
                apagadas += 1
            except Exception:  # noqa: BLE001
                pass
        db.set_setting(_last_key(chat_id), "0")
        if apagadas:
            logger.info("Auto-limpeza: %s mensagens apagadas no chat %s", apagadas, chat_id)
