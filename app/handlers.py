"""Comandos e mensagens que o bot responde no Telegram."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timedelta
from functools import wraps
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import config, db
from .services import calendar_service
from .utils.parsing import parse_event_text

logger = logging.getLogger(__name__)

_WEEKDAYS = [
    "Segunda-feira",
    "Terça-feira",
    "Quarta-feira",
    "Quinta-feira",
    "Sexta-feira",
    "Sábado",
    "Domingo",
]
_WEEKDAYS_ABBR = ["seg", "ter", "qua", "qui", "sex", "sáb", "dom"]


def _weekday_full(dt: datetime) -> str:
    return _WEEKDAYS[dt.weekday()]


def _weekday_abbr(dt: datetime) -> str:
    return _WEEKDAYS_ABBR[dt.weekday()]


# --- utilidades --------------------------------------------------------------
def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def restricted(func):
    """Garante que só os IDs autorizados usem o bot."""

    @wraps(func)
    async def wrapper(update: Update, context: ContextTypes.DEFAULT_TYPE):
        user = update.effective_user
        allowed = config.ALLOWED_TELEGRAM_IDS
        if allowed and (user is None or user.id not in allowed):
            if update.effective_message:
                await update.effective_message.reply_text(
                    "⛔ Você não tem acesso a esta agenda.\n"
                    f"Seu ID é `{user.id if user else '?'}`."
                )
            return
        return await func(update, context)

    return wrapper


def _payload(update: Update) -> str:
    """Retorna o texto digitado depois do comando."""
    text = (update.effective_message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _format_event(event: calendar_service.Event, *, with_id: bool = False) -> str:
    if event.all_day:
        when = event.start.strftime("%d/%m")
        title = f"{when} ({_weekday_abbr(event.start)}) • {event.summary} (dia inteiro)"
    else:
        when = event.start.strftime("%d/%m")
        title = f"{when} ({_weekday_abbr(event.start)}) às {event.start.strftime('%H:%M')} • {event.summary}"
    if event.location:
        title += f" — 📍 {event.location}"
    if with_id:
        title += f"\n   `{event.id[:16]}`"
    return title


async def _fetch_events(start: datetime, end: datetime, limit: int = 50):
    return await asyncio.to_thread(calendar_service.list_events, start, end, limit)


# --- comandos ----------------------------------------------------------------
@restricted
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "👋 *Sua agenda pessoal no Telegram*\n\n"
        "Eu leio e escrevo no seu *Google Calendar* e te aviso antes de cada compromisso.\n\n"
        "*Criar evento:*\n"
        "• `/novo Dentista amanhã às 14h`\n"
        "• ou só escreva: `Reunião com João sexta 10:30`\n\n"
        "*Consultar:*\n"
        "• `/hoje` — agenda de hoje\n"
        "• `/amanha` — agenda de amanhã\n"
        "• `/semana` — próximos 7 dias\n"
        "• `/proximos 10` — próximos compromissos\n\n"
        "*Gerenciar:*\n"
        "• `/cancelar` — lista e cancela um evento\n"
        "• `/lembrete 60` — avisar X minutos antes\n"
        "• `/diario 08:00` — horário do aviso de eventos de dia inteiro\n"
        "• `/id` — mostra seu ID do Telegram\n"
        "• `/status` — configuração atual\n\n"
        "Digite `/ajuda` para ver isto de novo.",
        parse_mode=ParseMode.MARKDOWN,
    )


cmd_help = cmd_start


@restricted
async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = update.effective_user
    chat = update.effective_chat
    await update.effective_message.reply_text(
        f"👤 Seu ID de usuário: `{user.id}`\n"
        f"💬 ID do chat: `{chat.id}`\n\n"
        "Coloque seu ID de usuário em `ALLOWED_TELEGRAM_IDS` no arquivo `.env`.",
        parse_mode=ParseMode.MARKDOWN,
    )


@restricted
async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    lead = db.get_setting("reminder_lead_minutes", str(config.REMINDER_LEAD_MINUTES))
    all_day = db.get_setting("all_day_reminder_time", config.ALL_DAY_REMINDER_TIME)
    text = (
        "⚙️ *Configuração atual*\n"
        f"• Calendário: `{config.GOOGLE_CALENDAR_ID}`\n"
        f"• Fuso: `{config.TIMEZONE}`\n"
        f"• Aviso: *{lead} min* antes\n"
        f"• Eventos de dia inteiro: aviso às *{all_day}*\n"
        f"• Duração padrão: *{config.DEFAULT_EVENT_DURATION_MIN} min*"
    )
    await update.effective_message.reply_text(text, parse_mode=ParseMode.MARKDOWN)


@restricted
async def cmd_novo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _create_event(update, _payload(update))


@restricted
async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    """Qualquer texto que não seja comando vira um novo evento."""
    await _create_event(update, (update.effective_message.text or "").strip())


async def _create_event(update: Update, text: str) -> None:
    message = update.effective_message
    if not text:
        await message.reply_text(
            "Escreva o evento assim: `/novo Dentista amanhã às 14h`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    parsed = parse_event_text(
        text,
        timezone=config.TIMEZONE,
        duration_min=config.DEFAULT_EVENT_DURATION_MIN,
        default_time=config.DEFAULT_EVENT_TIME,
    )
    if parsed is None:
        await message.reply_text(
            "🤔 Não consegui identificar a data/hora.\n"
            "Tente algo como: `/novo Dentista amanhã às 14h` ou "
            "`/novo Almoço 12/10 12:30`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await message.chat.send_action("typing")
    try:
        event = await asyncio.to_thread(
            calendar_service.create_event,
            parsed.title,
            parsed.start,
            parsed.end,
        )
    except Exception as exc:  # inclui CalendarError
        logger.exception("Erro ao criar evento")
        await message.reply_text(
            f"❌ Não consegui criar o evento.\n`{type(exc).__name__}: {exc}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await message.reply_text(
        "✅ *Evento criado!*\n"
        f"📌 {event.summary}\n"
        f"🗓 {event.start.strftime('%d/%m/%Y às %H:%M')}\n"
        f"⏳ Aviso {db.get_setting('reminder_lead_minutes', str(config.REMINDER_LEAD_MINUTES))} min antes.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _list_range(update: Update, start: datetime, end: datetime, header: str) -> None:
    message = update.effective_message
    await message.chat.send_action("typing")
    try:
        events = await _fetch_events(start, end)
    except Exception as exc:  # inclui CalendarError
        logger.exception("Erro no Google Calendar")
        await message.reply_text(
            f"❌ Erro ao falar com o Google Calendar.\n`{type(exc).__name__}: {exc}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if not events:
        await message.reply_text(f"{header}\n\n_Nenhum compromisso._", parse_mode=ParseMode.MARKDOWN)
        return

    lines = [header, ""]
    current_day = None
    for event in events:
        day = event.start.strftime("%d/%m/%Y")
        if day != current_day:
            current_day = day
            lines.append(f"*{day} — {_weekday_full(event.start)}*")
        lines.append("• " + _format_event(event))
    await message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)


@restricted
async def cmd_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    await _list_range(update, start, start + timedelta(days=1), "📅 *Hoje*")


@restricted
async def cmd_amanha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    await _list_range(update, start, start + timedelta(days=1), "📅 *Amanhã*")


@restricted
async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    await _list_range(update, start, start + timedelta(days=7), "📅 *Próximos 7 dias*")


@restricted
async def cmd_proximos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = _payload(update)
    limit = int(payload) if payload.isdigit() else 10
    limit = max(1, min(limit, 50))
    now = datetime.now(_tz())
    await _list_range(
        update, now, now + timedelta(days=365), f"📅 *Próximos {limit} compromissos*"
    )


@restricted
async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    payload = _payload(update)

    if not payload:
        now = datetime.now(_tz())
        try:
            events = await _fetch_events(now, now + timedelta(days=60), 20)
        except calendar_service.CalendarError as exc:
            await message.reply_text(f"❌ {exc}")
            return
        if not events:
            await message.reply_text("Não há eventos futuros para cancelar.")
            return
        lines = [
            "🗑 *Para cancelar*, envie `/cancelar ` seguido do código do evento:",
            "",
        ]
        for event in events:
            lines.append(_format_event(event, with_id=True))
        lines.append("\nEx.: `/cancelar abc123...`")
        await message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        return

    try:
        event = await asyncio.to_thread(calendar_service.find_event_by_prefix, payload)
    except Exception as exc:  # inclui CalendarError
        logger.exception("Erro no Google Calendar")
        await message.reply_text(
            f"❌ Erro ao falar com o Google Calendar.\n`{type(exc).__name__}: {exc}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    if event is None:
        await message.reply_text("❌ Não encontrei nenhum evento com esse código.")
        return

    try:
        await asyncio.to_thread(calendar_service.delete_event, event.id)
    except Exception as exc:  # inclui CalendarError
        logger.exception("Erro no Google Calendar")
        await message.reply_text(
            f"❌ Erro ao falar com o Google Calendar.\n`{type(exc).__name__}: {exc}`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await message.reply_text(
        f"🗑 Evento cancelado: *{event.summary}* "
        f"({event.start.strftime('%d/%m/%Y às %H:%M')}).",
        parse_mode=ParseMode.MARKDOWN,
    )


@restricted
async def cmd_lembrete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = _payload(update)
    if not payload.isdigit():
        atual = db.get_setting("reminder_lead_minutes", str(config.REMINDER_LEAD_MINUTES))
        await update.effective_message.reply_text(
            f"⏰ Aviso atual: *{atual} minutos* antes.\n"
            "Para mudar: `/lembrete 60`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    minutes = max(0, min(int(payload), 24 * 60))
    db.set_setting("reminder_lead_minutes", str(minutes))
    await update.effective_message.reply_text(
        f"✅ Agora vou avisar *{minutes} minutos* antes de cada compromisso.",
        parse_mode=ParseMode.MARKDOWN,
    )


@restricted
async def cmd_diario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = _payload(update)
    if ":" not in payload:
        atual = db.get_setting("all_day_reminder_time", config.ALL_DAY_REMINDER_TIME)
        await update.effective_message.reply_text(
            f"🗓 Aviso de eventos de dia inteiro: *{atual}*.\n"
            "Para mudar: `/diario 07:30`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    try:
        hour, minute = (int(part) for part in payload.split(":", 1))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AssertionError):
        await update.effective_message.reply_text("Horário inválido. Use algo como `/diario 08:00`.")
        return
    value = f"{hour:02d}:{minute:02d}"
    db.set_setting("all_day_reminder_time", value)
    await update.effective_message.reply_text(
        f"✅ Eventos de dia inteiro serão avisados às *{value}*.",
        parse_mode=ParseMode.MARKDOWN,
    )


@restricted
async def cmd_erro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Não reconheci esse comando. Use `/ajuda` para ver o que eu sei fazer.",
        parse_mode=ParseMode.MARKDOWN,
    )
