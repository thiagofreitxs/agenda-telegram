"""Limpeza automática da conversa do Telegram.

O bot guarda o último ID de mensagem visto em cada chat e, de tempos em tempos,
apaga as mensagens recentes daquele chat. Assim a conversa não vira uma bola de
neve de mensagens antigas.

Observação: o Telegram só permite apagar mensagens com menos de ~48h, e o bot
pode apagar as mensagens dele e as mensagens recebidas no chat privado. Falhas
são simplesmente ignoradas.
"""

from __future__ import annotations

import logging

from telegram import Update
from telegram.ext import ContextTypes

from .. import config, db

logger = logging.getLogger(__name__)

# Quantas mensagens para trás apagar em cada limpeza.
_JANELA = 200
# Margem para cobrir as respostas que o bot enviou depois da última mensagem vista.
_MARGEM = 50

_ENABLED_KEY = "autoclean_enabled"


def _last_key(chat_id: int) -> str:
    return f"last_msg_{chat_id}"


def is_enabled() -> bool:
    default = "1" if config.AUTOCLEAN_ENABLED else "0"
    return db.get_setting(_ENABLED_KEY, default) == "1"


def set_enabled(value: bool) -> None:
    db.set_setting(_ENABLED_KEY, "1" if value else "0")


async def track_message(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Handler (grupo -1) que registra a última mensagem vista em cada chat."""
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
    """Job periódico: apaga as mensagens recentes dos chats autorizados."""
    if not is_enabled():
        return

    for chat_id in config.ALLOWED_TELEGRAM_IDS:
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
                await context.bot.delete_message(
                    chat_id=chat_id, message_id=message_id
                )
                apagadas += 1
            except Exception:  # noqa: BLE001 - mensagens inexistentes/antigas falham
                pass

        db.set_setting(_last_key(chat_id), "0")
        if apagadas:
            logger.info("Auto-limpeza: %s mensagens apagadas no chat %s", apagadas, chat_id)
