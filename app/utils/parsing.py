"""Interpretação de datas/horas escritas em linguagem natural (pt-BR).

Suporta expressões como:
    "Dentista amanhã às 14h"      -> amanhã 14:00
    "Pagar contas amanhã"         -> amanhã no horário padrão (09:00)
    "Festa sábado à noite"        -> sábado 19:00
    "Almoço hoje meio-dia"        -> hoje 12:00
    "em 2 horas tomar remédio"    -> daqui a 2 horas
    "Reunião 25/12/2026 10:30"    -> data e hora explícitas
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

from dateparser.search import search_dates

# Horário explícito no formato "14:00"/"14:30" (após normalização).
_CLOCK_PATTERN = re.compile(r"\d{1,2}:\d{2}")

# Períodos do dia e o horário que representam.
_PERIODS: list[tuple[re.Pattern[str], int]] = [
    (re.compile(r"\bmeia-noite\b", re.IGNORECASE), 0),
    (re.compile(r"\bmadrugada\b", re.IGNORECASE), 1),
    (re.compile(r"\bmanh[ãa]\b", re.IGNORECASE), 9),
    (re.compile(r"\bmeio-dia\b", re.IGNORECASE), 12),
    (re.compile(r"\btarde\b", re.IGNORECASE), 14),
    (re.compile(r"\bnoite\b", re.IGNORECASE), 19),
]

# "14h", "14h30", "9 h" -> "14:00", "14:30", "09:00".
# Evita "em 2h"/"daqui 2h" (que são duração, não horário).
_HOUR_SUFFIX = re.compile(
    r"(?<![\w./])([01]?\d|2[0-3])\s*h\s*(\d{2})?(?![\w/])", re.IGNORECASE
)
_DURATION_PREFIX = re.compile(r"(em|daqui)\s*$", re.IGNORECASE)

# "em 2 horas", "daqui a 30 minutos" -> deslocamento relativo a partir de agora.
_RELATIVE_DURATION = re.compile(
    r"\b(?:em|daqui\s+a?)\s+(\d{1,4})\s*(horas?|h|minutos?|mins?|min)\b",
    re.IGNORECASE,
)

# Limpeza do título (preposições/artigos soltos nas pontas).
_LEADING_STOP = re.compile(
    r"^(?:de|da|do|das|dos|à|às|as|ao|aos|em|no|na|nos|nas|para|pra|com)\b[\s,]*",
    re.IGNORECASE,
)
_TRAILING_STOP = re.compile(
    r"[\s,]+(?:de|da|do|das|dos|à|às|as|em|no|na)$", re.IGNORECASE
)
_EDGE_JUNK = " \t-–—,:;./|"


@dataclass
class ParsedEvent:
    title: str
    start: datetime
    end: datetime


def _normalize_hour_notation(text: str) -> str:
    """Converte "14h"/"14h30" em "14:00"/"14:30"."""

    def replace(match: re.Match[str]) -> str:
        prefix = text[max(0, match.start() - 6) : match.start()]
        if _DURATION_PREFIX.search(prefix):
            return match.group(0)  # é duração, não horário
        hour = int(match.group(1))
        if not 0 <= hour <= 23:
            return match.group(0)
        minutes = match.group(2) or "00"
        return f"{hour:02d}:{minutes}"

    return _HOUR_SUFFIX.sub(replace, text)


def _extract_period(text: str) -> tuple[str, int | None]:
    """Remove "de manhã / à noite..." do texto e devolve a hora sugerida."""
    hour: int | None = None
    for pattern, value in _PERIODS:
        if pattern.search(text):
            if hour is None:
                hour = value
            text = pattern.sub(" ", text, count=1)
    return text, hour


def _match_relative_duration(text: str, now: datetime) -> tuple[datetime | None, str]:
    match = _RELATIVE_DURATION.search(text)
    if not match:
        return None, text
    amount = int(match.group(1))
    unit = match.group(2).lower()
    delta = timedelta(hours=amount) if unit.startswith("h") else timedelta(minutes=amount)
    start = (now + delta).replace(second=0, microsecond=0)
    cleaned = text[: match.start()] + " " + text[match.end() :]
    return start, cleaned


def _clean_title(text: str) -> str:
    text = re.sub(r"\s+", " ", text).strip()
    text = text.strip(_EDGE_JUNK).strip()
    previous = None
    while previous != text:
        previous = text
        text = _LEADING_STOP.sub("", text).strip()
        text = _TRAILING_STOP.sub("", text).strip(_EDGE_JUNK).strip()
    return text or "Compromisso"


def _apply_default_time(dt: datetime, default_time: str) -> datetime:
    try:
        hour, minute = (int(part) for part in default_time.split(":"))
    except ValueError:
        hour, minute = 9, 0
    return dt.replace(hour=hour, minute=minute, second=0, microsecond=0)


def _build(title: str, start: datetime, duration_min: int) -> ParsedEvent:
    start = start.replace(second=0, microsecond=0)
    end = start + timedelta(minutes=max(1, duration_min))
    return ParsedEvent(title=title, start=start, end=end)


def parse_event_text(
    text: str,
    *,
    timezone: str,
    duration_min: int = 60,
    default_time: str = "09:00",
) -> ParsedEvent | None:
    """Extrai título, início e fim de um texto livre. Retorna None se não achar data."""
    text = (text or "").strip()
    if not text:
        return None

    tz = ZoneInfo(timezone)
    now = datetime.now(tz)

    working = _normalize_hour_notation(text)
    working, period_hour = _extract_period(working)

    # Caso 1: duração relativa ("em 2 horas"), que já define o início.
    relative_start, working = _match_relative_duration(working, now)
    if relative_start is not None:
        if period_hour is not None:
            relative_start = relative_start.replace(hour=period_hour, minute=0)
        return _build(_clean_title(working), relative_start, duration_min)

    # Caso 2: data/hora via dateparser.
    settings = {
        "TIMEZONE": timezone,
        "TO_TIMEZONE": timezone,
        "RETURN_AS_TIMEZONE_AWARE": True,
        "PREFER_DATES_FROM": "future",
        "RELATIVE_BASE": now,
    }
    try:
        found = search_dates(working, languages=["pt", "en"], settings=settings)
    except Exception:
        found = None
    if not found:
        return None

    matched_text, start = next(
        ((fragment, value) for fragment, value in found if value is not None),
        (None, None),
    )
    if start is None or matched_text is None:
        return None

    start = start.replace(tzinfo=tz) if start.tzinfo is None else start.astimezone(tz)

    if _CLOCK_PATTERN.search(matched_text):
        pass  # horário explícito no texto
    elif period_hour is not None:
        start = start.replace(hour=period_hour, minute=0)
    else:
        start = _apply_default_time(start, default_time)

    title = _clean_title(working.replace(matched_text, " ", 1))
    return _build(title, start, duration_min)
