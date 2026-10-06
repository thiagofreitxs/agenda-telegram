"""Comandos e mensagens que o bot responde no Telegram (multiusuário)."""

from __future__ import annotations

import asyncio
import html as _html
import logging
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import ContextTypes

from . import config, store, web
from .services import auth, calendar_service
from .utils.parsing import parse_day, parse_event_text

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


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def _md(value) -> str:
    """Escapa caracteres especiais do Markdown legado do Telegram."""
    text = str(value)
    for ch in ("\\", "_", "*", "`", "[", "]"):
        text = text.replace(ch, "\\" + ch)
    return text


def _weekday_full(dt: datetime) -> str:
    return _WEEKDAYS[dt.weekday()]


def _weekday_abbr(dt: datetime) -> str:
    return _WEEKDAYS_ABBR[dt.weekday()]


def _payload(update: Update) -> str:
    text = (update.effective_message.text or "").strip()
    parts = text.split(maxsplit=1)
    return parts[1].strip() if len(parts) > 1 else ""


def _user(update: Update) -> dict:
    return store.get_user(update.effective_user.id) or {}


async def _require_creds(update: Update):
    """Devolve credenciais válidas ou pede para conectar (e retorna None)."""
    message = update.effective_message
    user = _user(update)
    if not user.get("refresh_token"):
        await message.reply_text(
            "🔒 Você ainda não conectou o seu Google Calendar.\n"
            "Envie /conectar para autorizar o acesso.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return None
    try:
        return await asyncio.to_thread(auth.credentials_for, user)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Falha ao obter credenciais: %s", exc)
        await message.reply_text(
            "❌ Não consegui acessar sua conta Google. Envie /conectar novamente.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return None


async def _fetch_events(creds, start: datetime, end: datetime, limit: int = 50):
    return await asyncio.to_thread(calendar_service.list_events, creds, start, end, limit)


def _format_event(event: calendar_service.Event, *, with_id: bool = False) -> str:
    when = event.start.strftime("%d/%m")
    if event.all_day:
        title = f"{when} ({_weekday_abbr(event.start)}) • {_md(event.summary)} (dia inteiro)"
    else:
        title = (
            f"{when} ({_weekday_abbr(event.start)}) às {event.start.strftime('%H:%M')} "
            f"• {_md(event.summary)}"
        )
    if event.location:
        title += f" — 📍 {_md(event.location)}"
    if with_id:
        title += f"\n   `{event.id[:16]}`"
    return title


# --- comandos ----------------------------------------------------------------
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _user(update)
    conectado = "✅ conta conectada" if user.get("refresh_token") else "❌ ainda não conectada"
    await update.effective_message.reply_text(
        "👋 *Agenda no Telegram*\n\n"
        f"Status do Google: {conectado}\n\n"
        "*1º passo — conectar sua conta:*\n"
        "• `/conectar` — autoriza seu Google Calendar\n\n"
        "*Criar evento:*\n"
        "• `/novo Dentista amanhã às 14h`\n"
        "• ou só escreva: `Reunião sexta 10:30`\n\n"
        "*Consultar:*\n"
        "• `/hoje` · `/amanha` · `/semana` · `/proximos 10`\n\n"
        "*Gerenciar:*\n"
        "• `/cancelar` — cancela um evento\n"
        "• `/limpar_dia amanhã` — apaga o dia\n"
        "• `/limpar_tudo` — apaga tudo (com confirmação)\n"
        "• `/lembrete 60` — avisar X min antes\n"
        "• `/autolimpar on|off` — limpar a conversa\n"
        "• `/desconectar` · `/status` · `/id`\n\n"
        "Digite `/ajuda` para ver isto de novo.",
        parse_mode=ParseMode.MARKDOWN,
    )


cmd_help = cmd_start


async def cmd_conectar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    user_tg = update.effective_user
    record = store.get_user(user_tg.id) or {}

    if not (config.GOOGLE_CLIENT_ID and config.GOOGLE_CLIENT_SECRET):
        await message.reply_text(
            "⚙️ O bot ainda está sendo configurado pelo administrador. Tente mais tarde."
        )
        return

    # Garante que o usuário existe no banco.
    store.update_user(
        user_tg.id,
        username=user_tg.username or "",
        first_name=user_tg.first_name or "",
    )
    if not record:
        record = store.get_user(user_tg.id) or {}

    if record.get("refresh_token"):
        await message.reply_text(
            f"✅ Sua conta Google já está conectada"
            + (f" (`{record.get('email')}`)." if record.get("email") else ".")
            + "\nPara trocar, use /desconectar e depois /conectar.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    link = web.create_connect_link(user_tg.id)
    await message.reply_text(
        "🔗 <b>Conectar seu Google Calendar</b>\n\n"
        "Clique no link abaixo, faça login e autorize:\n"
        f"{link}\n\n"
        "<i>O link vale por 15 minutos. Depois volte aqui.</i>",
        parse_mode="HTML",
        disable_web_page_preview=True,
    )


async def cmd_desconectar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    uid = update.effective_user.id
    auth.invalidate(uid)
    store.update_user(uid, refresh_token=None, access_token=None, email=None)
    await update.effective_message.reply_text(
        "🔌 Sua conta Google foi desconectada. Use /conectar para reconectar."
    )


async def cmd_id(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    u = update.effective_user
    await update.effective_message.reply_text(
        f"👤 Seu ID: `{u.id}`\n💬 Chat: `{update.effective_chat.id}`",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_status(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    user = _user(update)
    lead = user.get("lead_minutes") or config.REMINDER_LEAD_MINUTES
    all_day = user.get("all_day_time") or config.ALL_DAY_REMINDER_TIME
    auto = "ligada" if user.get("autoclean", "1") == "1" else "desligada"
    conectado = f"`{user.get('email')}`" if user.get("refresh_token") else "_não conectado_"
    await update.effective_message.reply_text(
        "⚙️ *Sua configuração*\n"
        f"• Google: {conectado}\n"
        f"• Aviso: *{lead} min* antes\n"
        f"• Dia inteiro: aviso às *{all_day}*\n"
        f"• Limpeza da conversa: *{auto}*",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_novo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await _create_event(update, _payload(update))


async def on_text(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    text = (update.effective_message.text or "").strip()
    if not text:
        return
    if not _user(update).get("refresh_token"):
        await update.effective_message.reply_text(
            "🔒 Conecte seu Google primeiro com /conectar."
        )
        return
    await _create_event(update, text)


async def _create_event(update: Update, text: str) -> None:
    message = update.effective_message
    if not text:
        await message.reply_text(
            "Escreva o evento assim: `/novo Dentista amanhã às 14h`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    creds = await _require_creds(update)
    if creds is None:
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
            "Tente: `/novo Dentista amanhã às 14h` ou `/novo Almoço 12/10 12:30`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return

    await message.chat.send_action("typing")
    try:
        event = await asyncio.to_thread(
            calendar_service.create_event, creds, parsed.title, parsed.start, parsed.end
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Erro ao criar evento")
        await message.reply_text(
            f"❌ Não consegui criar o evento.\n{type(exc).__name__}: {exc}"
        )
        return

    lead = _user(update).get("lead_minutes") or config.REMINDER_LEAD_MINUTES
    await message.reply_text(
        "✅ *Evento criado!*\n"
        f"📌 {_md(event.summary)}\n"
        f"🗓 {event.start.strftime('%d/%m/%Y às %H:%M')}\n"
        f"⏳ Aviso {lead} min antes.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def _list_range(update: Update, start: datetime, end: datetime, header: str) -> None:
    message = update.effective_message
    creds = await _require_creds(update)
    if creds is None:
        return
    await message.chat.send_action("typing")
    try:
        events = await _fetch_events(creds, start, end)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(
            f"❌ Erro ao consultar a agenda.\n{type(exc).__name__}: {exc}"
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


async def cmd_hoje(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    await _list_range(update, start, start + timedelta(days=1), "📅 *Hoje*")


async def cmd_amanha(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0) + timedelta(days=1)
    await _list_range(update, start, start + timedelta(days=1), "📅 *Amanhã*")


async def cmd_semana(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    now = datetime.now(_tz())
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    await _list_range(update, start, start + timedelta(days=7), "📅 *Próximos 7 dias*")


async def cmd_proximos(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = _payload(update)
    limit = int(payload) if payload.isdigit() else 10
    limit = max(1, min(limit, 50))
    now = datetime.now(_tz())
    await _list_range(update, now, now + timedelta(days=365), f"📅 *Próximos {limit} compromissos*")


async def cmd_cancelar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    creds = await _require_creds(update)
    if creds is None:
        return
    payload = _payload(update)

    if not payload:
        now = datetime.now(_tz())
        try:
            events = await _fetch_events(creds, now, now + timedelta(days=60), 20)
        except Exception as exc:  # noqa: BLE001
            await message.reply_text(f"❌ {exc}")
            return
        if not events:
            await message.reply_text("Não há eventos futuros para cancelar.")
            return
        lines = ["🗑 *Para cancelar*, envie `/cancelar ` + código:", ""]
        lines += [_format_event(e, with_id=True) for e in events]
        lines.append("\nEx.: `/cancelar abc123...`")
        await message.reply_text("\n".join(lines), parse_mode=ParseMode.MARKDOWN)
        return

    try:
        event = await asyncio.to_thread(calendar_service.find_event_by_prefix, creds, payload)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(f"❌ {exc}")
        return
    if event is None:
        await message.reply_text("❌ Não encontrei nenhum evento com esse código.")
        return
    try:
        await asyncio.to_thread(calendar_service.delete_event, creds, event.id)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(f"❌ {exc}")
        return
    await message.reply_text(
        f"🗑 Evento cancelado: *{_md(event.summary)}* "
        f"({event.start.strftime('%d/%m/%Y às %H:%M')}).",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_limpar_dia(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    creds = await _require_creds(update)
    if creds is None:
        return
    payload = _payload(update)
    if not payload:
        await message.reply_text(
            "🗓 Use: `/limpar_dia amanhã` ou `/limpar_dia 25/12`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    day = parse_day(payload, timezone=config.TIMEZONE)
    if day is None:
        await message.reply_text(
            "🤔 Não entendi a data. Tente `/limpar_dia 25/12`.",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    tz = _tz()
    start = datetime(day.year, day.month, day.day, tzinfo=tz)
    end = start + timedelta(days=1)
    await message.chat.send_action("typing")
    try:
        events = await asyncio.to_thread(calendar_service.list_events, creds, start, end, 250)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(f"❌ {exc}")
        return
    if not events:
        await message.reply_text(f"Não há eventos em *{day.strftime('%d/%m/%Y')}*.", parse_mode=ParseMode.MARKDOWN)
        return
    deleted, failed = await asyncio.to_thread(calendar_service.delete_events, creds, events)
    texto = f"🗑 Apaguei *{deleted}* evento(s) de *{day.strftime('%d/%m/%Y')}*."
    if failed:
        texto += f"\n⚠️ {failed} não puderam ser apagados."
    await message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_limpar_tudo(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    message = update.effective_message
    creds = await _require_creds(update)
    if creds is None:
        return
    payload = _payload(update).strip().lower()
    tz = _tz()
    now = datetime.now(tz)
    limite = now + timedelta(days=3650)
    confirmado = payload in {"confirmar", "confirmo", "sim", "confirma", "yes"}

    await message.chat.send_action("typing")
    try:
        events = await asyncio.to_thread(calendar_service.list_all_events, creds, now, limite)
    except Exception as exc:  # noqa: BLE001
        await message.reply_text(f"❌ {exc}")
        return
    if not events:
        await message.reply_text("Não há eventos futuros para apagar.")
        return
    if not confirmado:
        await message.reply_text(
            f"⚠️ Isso vai *apagar {len(events)} evento(s)* a partir de agora.\n\n"
            "Para confirmar, envie: `/limpar_tudo confirmar`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    deleted, failed = await asyncio.to_thread(calendar_service.delete_events, creds, events)
    texto = f"🗑 Apaguei *{deleted}* evento(s) futuros."
    if failed:
        texto += f"\n⚠️ {failed} não puderam ser apagados."
    await message.reply_text(texto, parse_mode=ParseMode.MARKDOWN)


async def cmd_lembrete(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = _payload(update)
    uid = update.effective_user.id
    user = _user(update)
    if not payload.isdigit():
        atual = user.get("lead_minutes") or config.REMINDER_LEAD_MINUTES
        await update.effective_message.reply_text(
            f"⏰ Aviso atual: *{atual} minutos* antes.\nPara mudar: `/lembrete 60`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    minutes = max(0, min(int(payload), 24 * 60))
    store.update_user(uid, lead_minutes=minutes)
    await update.effective_message.reply_text(
        f"✅ Vou avisar *{minutes} minutos* antes.", parse_mode=ParseMode.MARKDOWN
    )


async def cmd_diario(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = _payload(update)
    uid = update.effective_user.id
    user = _user(update)
    if ":" not in payload:
        atual = user.get("all_day_time") or config.ALL_DAY_REMINDER_TIME
        await update.effective_message.reply_text(
            f"🗓 Aviso de dia inteiro: *{atual}*. Para mudar: `/diario 07:30`",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    try:
        hour, minute = (int(p) for p in payload.split(":", 1))
        assert 0 <= hour <= 23 and 0 <= minute <= 59
    except (ValueError, AssertionError):
        await update.effective_message.reply_text("Horário inválido. Use `/diario 08:00`.")
        return
    value = f"{hour:02d}:{minute:02d}"
    store.update_user(uid, all_day_time=value)
    await update.effective_message.reply_text(f"✅ Avisos de dia inteiro às *{value}*.", parse_mode=ParseMode.MARKDOWN)


async def cmd_autolimpar(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    payload = _payload(update).strip().lower()
    uid = update.effective_user.id
    user = _user(update)
    ligar = {"on", "ligar", "ativar", "sim", "1", "true"}
    desligar = {"off", "desligar", "desativar", "nao", "não", "0", "false"}
    if payload in ligar:
        store.update_user(uid, autoclean="1")
        await update.effective_message.reply_text(
            f"🧹 Limpeza da conversa *ATIVADA* (a cada {config.AUTOCLEAN_MINUTES} min).",
            parse_mode=ParseMode.MARKDOWN,
        )
        return
    if payload in desligar:
        store.update_user(uid, autoclean="0")
        await update.effective_message.reply_text(
            "🧹 Limpeza *DESATIVADA*.", parse_mode=ParseMode.MARKDOWN
        )
        return
    estado = "ATIVADA" if user.get("autoclean", "1") == "1" else "DESATIVADA"
    await update.effective_message.reply_text(
        f"🧹 Limpeza da conversa está *{estado}* (a cada {config.AUTOCLEAN_MINUTES} min).\n"
        "Para mudar: `/autolimpar on` ou `/autolimpar off`.",
        parse_mode=ParseMode.MARKDOWN,
    )


async def cmd_erro(update: Update, context: ContextTypes.DEFAULT_TYPE) -> None:
    await update.effective_message.reply_text(
        "Não reconheci esse comando. Use `/ajuda`.", parse_mode=ParseMode.MARKDOWN
    )
