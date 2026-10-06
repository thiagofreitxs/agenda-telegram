"""Integração com a Google Calendar API (multiusuário).

As funções recebem as credenciais do usuário (``creds``) — obtidas em
``app.services.auth`` — e operam no calendário principal dele.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from googleapiclient.discovery import build

from .. import config

logger = logging.getLogger(__name__)


class CalendarError(RuntimeError):
    """Erro amigável ao falar com o Google Calendar."""


@dataclass
class Event:
    id: str
    summary: str
    start: datetime
    end: datetime | None
    all_day: bool
    location: str | None = None
    description: str | None = None
    html_link: str | None = None


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def _service(creds):
    return build("calendar", "v3", credentials=creds, cache_discovery=False)


def _parse_datetime(value: dict) -> tuple[datetime, bool]:
    if "dateTime" in value:
        raw = value["dateTime"]
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz())
        return dt.astimezone(_tz()), False
    day = date.fromisoformat(value["date"])
    return datetime.combine(day, time.min, tzinfo=_tz()), True


def _to_event(item: dict) -> Event:
    start, all_day = _parse_datetime(item.get("start", {}))
    end = None
    if item.get("end"):
        try:
            end, _ = _parse_datetime(item["end"])
        except (KeyError, ValueError):
            end = None
    return Event(
        id=item.get("id", ""),
        summary=item.get("summary") or "(sem título)",
        start=start,
        end=end,
        all_day=all_day,
        location=item.get("location"),
        description=item.get("description"),
        html_link=item.get("htmlLink"),
    )


def list_events(creds, time_min: datetime, time_max: datetime, max_results: int = 50) -> list[Event]:
    try:
        result = (
            _service(creds)
            .events()
            .list(
                calendarId="primary",
                timeMin=time_min.astimezone(_tz()).isoformat(),
                timeMax=time_max.astimezone(_tz()).isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise CalendarError(f"Falha ao consultar o Google Calendar: {exc}") from exc
    return [
        _to_event(item)
        for item in result.get("items", [])
        if item.get("status") != "cancelled"
    ]


def list_all_events(
    creds, time_min: datetime, time_max: datetime, page_limit: int = 250, max_events: int = 5000
) -> list[Event]:
    events: list[Event] = []
    page_token: str | None = None
    service = _service(creds)
    while True:
        try:
            result = (
                service.events()
                .list(
                    calendarId="primary",
                    timeMin=time_min.astimezone(_tz()).isoformat(),
                    timeMax=time_max.astimezone(_tz()).isoformat(),
                    singleEvents=True,
                    orderBy="startTime",
                    maxResults=page_limit,
                    pageToken=page_token,
                )
                .execute()
            )
        except Exception as exc:  # noqa: BLE001
            raise CalendarError(f"Falha ao consultar o Google Calendar: {exc}") from exc
        events.extend(
            _to_event(item)
            for item in result.get("items", [])
            if item.get("status") != "cancelled"
        )
        page_token = result.get("nextPageToken")
        if not page_token or len(events) >= max_events:
            break
    return events


def create_event(
    creds,
    summary: str,
    start: datetime,
    end: datetime,
    *,
    description: str | None = None,
    location: str | None = None,
) -> Event:
    body = {
        "summary": summary,
        "start": {"dateTime": start.isoformat(), "timeZone": config.TIMEZONE},
        "end": {"dateTime": end.isoformat(), "timeZone": config.TIMEZONE},
    }
    if description:
        body["description"] = description
    if location:
        body["location"] = location
    try:
        created = (
            _service(creds).events().insert(calendarId="primary", body=body).execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise CalendarError(f"Falha ao criar o evento: {exc}") from exc
    return _to_event(created)


def delete_event(creds, event_id: str) -> None:
    try:
        _service(creds).events().delete(
            calendarId="primary", eventId=event_id
        ).execute()
    except Exception as exc:  # noqa: BLE001
        raise CalendarError(f"Falha ao cancelar o evento: {exc}") from exc


def delete_events(creds, events: list[Event]) -> tuple[int, int]:
    deleted = 0
    failed = 0
    for event in events:
        try:
            delete_event(creds, event.id)
            deleted += 1
        except CalendarError:
            failed += 1
    return deleted, failed


def find_event_by_prefix(creds, prefix: str) -> Event | None:
    now = datetime.now(_tz())
    events = list_events(creds, now - timedelta(minutes=1), now + timedelta(days=365), 250)
    prefix = prefix.strip()
    for event in events:
        if event.id == prefix:
            return event
    for event in events:
        if event.id.startswith(prefix):
            return event
    return None
