"""Verificação periódica da agenda de TODOS os usuários e envio de lembretes."""

from __future__ import annotations

import asyncio
import html as _html
import logging
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

from telegram.ext import ContextTypes

from .. import config, db, store
from . import auth, calendar_service

logger = logging.getLogger(__name__)


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def format_reminder(event: calendar_service.Event) -> str:
    if event.all_day:
        when = event.start.strftime("%d/%m/%Y")
        lines = ["📌 <b>Hoje</b> é o dia de:", f"<b>{_html.escape(event.summary)}</b>", f"🗓 {when} (dia inteiro)"]
    else:
        when = event.start.strftime("%d/%m/%Y às %H:%M")
        lines = ["⏰ <b>Lembrete</b>", f"<b>{_html.escape(event.summary)}</b>", f"🗓 {when}"]
    if event.location:
        lines.append(f"📍 {_html.escape(event.location)}")
    if event.description:
        preview = event.description.strip().splitlines()[0][:200]
        lines.append(f"📝 {_html.escape(preview)}")
    if event.html_link:
        lines.append(f'🔗 <a href="{_html.escape(event.html_link)}">Abrir no Google Calendar</a>')
    return "\n".join(lines)


async def _send(context: ContextTypes.DEFAULT_TYPE, chat_id: int, text: str) -> None:
    try:
        await context.bot.send_message(
            chat_id=chat_id, text=text, parse_mode="HTML",
            disable_web_page_preview=True,
        )
    except Exception:  # noqa: BLE001
        logger.warning("Falha ao enviar lembrete para %s", chat_id)


def _parse_time(value: str | None) -> time:
    try:
        hour, minute = (int(p) for p in (value or config.ALL_DAY_REMINDER_TIME).split(":"))
        return time(hour=hour, minute=minute)
    except (ValueError, AttributeError):
        return time(hour=8, minute=0)


async def check_reminders(context: ContextTypes.DEFAULT_TYPE) -> None:
    tz = _tz()
    now = datetime.now(tz)
    slack = timedelta(seconds=config.REMINDER_CHECK_INTERVAL_SECONDS)

    users = await asyncio.to_thread(store.all_users)
    for tid, record in users.items():
        if not record.get("refresh_token"):
            continue
        try:
            creds = await asyncio.to_thread(auth.credentials_for, record)
        except Exception:  # noqa: BLE001
            logger.info("Usuário %s sem credenciais válidas; pulando.", tid)
            continue

        lead = timedelta(minutes=int(record.get("lead_minutes") or config.REMINDER_LEAD_MINUTES))
        try:
            events = await asyncio.to_thread(
                calendar_service.list_events,
                creds,
                now - timedelta(minutes=1),
                now + lead + slack,
            )
        except Exception as exc:  # noqa: BLE001
            logger.warning("Erro ao consultar agenda do usuário %s: %s", tid, exc)
            continue

        for event in events:
            if event.all_day:
                await _maybe_remind_all_day(context, int(tid), record, event, now)
                continue
            if event.start < now or event.start > now + lead:
                continue
            key = event.start.isoformat()
            if await asyncio.to_thread(db.reminder_already_sent, event.id, key):
                continue
            await _send(context, int(tid), format_reminder(event))
            await asyncio.to_thread(db.mark_reminder_sent, event.id, key)


async def _maybe_remind_all_day(
    context: ContextTypes.DEFAULT_TYPE,
    chat_id: int,
    record: dict,
    event: calendar_service.Event,
    now: datetime,
) -> None:
    if event.start.date() != now.date():
        return
    target = _parse_time(record.get("all_day_time"))
    reminder_at = datetime.combine(now.date(), target, tzinfo=now.tzinfo)
    if now < reminder_at or now - reminder_at > timedelta(minutes=5):
        return
    key = event.start.isoformat()
    if await asyncio.to_thread(db.reminder_already_sent, event.id, key):
        return
    await _send(context, chat_id, format_reminder(event))
    await asyncio.to_thread(db.mark_reminder_sent, event.id, key)


async def cleanup_job(context: ContextTypes.DEFAULT_TYPE) -> None:
    await asyncio.to_thread(db.cleanup_old_reminders, 60)
