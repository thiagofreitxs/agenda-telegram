"""Verificação periódica da agenda e envio de lembretes no Telegram."""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from .. import config, db
from . import calendar_service

logger = logging.getLogger(__name__)


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def _lead_minutes() -> int:
    raw = db.get_setting("reminder_lead_minutes", str(config.REMINDER_LEAD_MINUTES))
    try:
        return max(0, int(raw))
    except (TypeError, ValueError):
        return config.REMINDER_LEAD_MINUTES


def _all_day_reminder_time() -> time:
    raw = db.get_setting("all_day_reminder_time", config.ALL_DAY_REMINDER_TIME)
    try:
        hour, minute = (int(part) for part in raw.split(":"))
        return time(hour=hour, minute=minute)
    except (ValueError, AttributeError):
        return time(hour=8, minute=0)


def format_reminder(event: calendar_service.Event) -> str:
    if event.all_day:
        when = event.start.strftime("%d/%m/%Y")
        lines = [f"📌 *Hoje* é o dia de:", f"*{event.summary}*", f"🗓 {when} (dia inteiro)"]
    else:
        when = event.start.strftime("%d/%m/%Y às %H:%M")
        lines = ["⏰ *Lembrete*", f"*{event.summary}*", f"🗓 {when}"]

    if event.location:
        lines.append(f"📍 {event.location}")
    if event.description:
        preview = event.description.strip().splitlines()[0][:200]
        lines.append(f"📝 {preview}")
    if event.html_link:
        lines.append(f"🔗 [Abrir no Google Calendar]({event.html_link})")
    return "\n".join(lines)


async def _broadcast(context: ContextTypes.DEFAULT_TYPE, text: str) -> None:
    for chat_id in config.ALLOWED_TELEGRAM_IDS:
        try:
            await context.bot.send_message(
                chat_id=chat_id, text=text, parse_mode="Markdown",
                disable_web_page_preview=True,
            )
        except Exception:  # noqa: BLE001
            logger.exception("Falha ao enviar lembrete para %s", chat_id)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Job periódico: avisa sobre eventos que começam dentro da antecedência."""
    tz = _tz()
    now = datetime.now(tz)
    lead = timedelta(minutes=_lead_minutes())
    slack = timedelta(seconds=config.REMINDER_CHECK_INTERVAL_SECONDS)

    try:
        events = await asyncio.to_thread(
            calendar_service.list_events,
            now - timedelta(minutes=1),
            now + lead + slack,
        )
    except calendar_service.CalendarError as exc:
        logger.warning("Lembrete adiado: %s", exc)
        return

    for event in events:
        if event.all_day:
            await _maybe_remind_all_day(context, event, now)
            continue

        if event.start < now or event.start > now + lead:
            continue

        key_iso = event.start.isoformat()
        if await asyncio.to_thread(db.reminder_already_sent, event.id, key_iso):
            continue

        await _broadcast(context, format_reminder(event))
        await asyncio.to_thread(db.mark_reminder_sent, event.id, key_iso)
        logger.info("Lembrete enviado: %s (%s)", event.summary, key_iso)


async def _maybe_remind_all_day(
    context: ContextTypes.DEFAULT_TYPE,
    event: calendar_service.Event,
    now: datetime,
) -> None:
    """Eventos de dia inteiro são avisados no horário configurado (padrão 08:00)."""
    if event.start.date() != now.date():
        return
    target = _all_day_reminder_time()
    reminder_at = datetime.combine(now.date(), target, tzinfo=now.tzinfo)
    if now < reminder_at or now - reminder_at > timedelta(minutes=5):
        return

    key_iso = event.start.isoformat()
    if await asyncio.to_thread(db.reminder_already_sent, event.id, key_iso):
        return

    await _broadcast(context, format_reminder(event))
    await asyncio.to_thread(db.mark_reminder_sent, event.id, key_iso)


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    """Remove registros de lembretes antigos uma vez por dia."""
    await asyncio.to_thread(db.cleanup_old_reminders, 60)
