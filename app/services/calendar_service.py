"""Integração com a Google Calendar API.

Suporta dois modos de autenticação:
1. OAuth (recomendado) - acessa o seu calendário principal. Gere o token com
   ``python authorize_google.py``.
2. Conta de serviço - compartilhe o calendário com o e-mail da service account.
"""

from __future__ import annotations

import json
import os
import threading
from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from zoneinfo import ZoneInfo

from google.auth.transport.requests import Request
from google.oauth2 import service_account
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from .. import config

SCOPES = ["https://www.googleapis.com/auth/calendar"]

_service_lock = threading.Lock()
_service_cache = None


class CalendarError(RuntimeError):
    """Erro amigável para problemas ao falar com o Google Calendar."""


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


# --- Credenciais e serviço ---------------------------------------------------
def _load_credentials():
    # 1) OAuth via token em JSON (variável de ambiente) ou arquivo.
    token_info = None
    if config.GOOGLE_TOKEN_JSON:
        try:
            token_info = json.loads(config.GOOGLE_TOKEN_JSON)
        except json.JSONDecodeError as exc:
            raise CalendarError("GOOGLE_TOKEN_JSON não é um JSON válido.") from exc
    elif os.path.exists(config.GOOGLE_TOKEN_FILE):
        with open(config.GOOGLE_TOKEN_FILE, encoding="utf-8") as handle:
            token_info = json.load(handle)

    if token_info:
        creds = Credentials.from_authorized_user_info(token_info, SCOPES)
        if not creds.valid:
            if creds.expired and creds.refresh_token:
                creds.refresh(Request())
                _persist_token(creds)
            else:
                raise CalendarError(
                    "Token do Google inválido/expirado. Rode novamente "
                    "'python authorize_google.py'."
                )
        return creds

    # 2) Conta de serviço via JSON (variável de ambiente) ou arquivo.
    if config.GOOGLE_SERVICE_ACCOUNT_JSON:
        try:
            info = json.loads(config.GOOGLE_SERVICE_ACCOUNT_JSON)
        except json.JSONDecodeError as exc:
            raise CalendarError(
                "GOOGLE_SERVICE_ACCOUNT_JSON não é um JSON válido. "
                "Verifique se você colou a linha inteira, sem quebras."
            ) from exc
        try:
            return service_account.Credentials.from_service_account_info(
                info, scopes=SCOPES
            )
        except Exception as exc:  # noqa: BLE001
            raise CalendarError(
                f"GOOGLE_SERVICE_ACCOUNT_JSON inválido: {type(exc).__name__}: {exc}"
            ) from exc
    if config.GOOGLE_SERVICE_ACCOUNT_FILE and os.path.exists(
        config.GOOGLE_SERVICE_ACCOUNT_FILE
    ):
        return service_account.Credentials.from_service_account_file(
            config.GOOGLE_SERVICE_ACCOUNT_FILE, scopes=SCOPES
        )

    raise CalendarError(
        "Nenhuma credencial do Google configurada. Rode 'python authorize_google.py' "
        "ou configure GOOGLE_SERVICE_ACCOUNT_JSON."
    )


def _persist_token(creds: Credentials) -> None:
    """Salva o token atualizado no arquivo, quando estiver usando arquivo."""
    if config.GOOGLE_TOKEN_JSON:
        return
    path = config.GOOGLE_TOKEN_FILE
    if not path:
        return
    try:
        with open(path, "w", encoding="utf-8") as handle:
            handle.write(creds.to_json())
    except OSError:
        # Não é fatal: em ambientes read-only apenas não persistimos.
        pass


def _service():
    global _service_cache
    if _service_cache is None:
        with _service_lock:
            if _service_cache is None:
                creds = _load_credentials()
                _service_cache = build(
                    "calendar", "v3", credentials=creds, cache_discovery=False
                )
    return _service_cache


def _tz() -> ZoneInfo:
    return ZoneInfo(config.TIMEZONE)


def _parse_datetime(value: dict) -> tuple[datetime, bool]:
    """Devolve (datetime com fuso, é dia inteiro?)."""
    if "dateTime" in value:
        raw = value["dateTime"]
        if raw.endswith("Z"):
            raw = raw[:-1] + "+00:00"
        dt = datetime.fromisoformat(raw)
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=_tz())
        return dt.astimezone(_tz()), False
    # Evento de dia inteiro: "date" apenas (ex.: 2026-10-05)
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


# --- Operações ---------------------------------------------------------------
def list_events(time_min: datetime, time_max: datetime, max_results: int = 50) -> list[Event]:
    """Lista eventos entre dois instantes, ordenados por início."""
    service = _service()
    try:
        result = (
            service.events()
            .list(
                calendarId=config.GOOGLE_CALENDAR_ID,
                timeMin=time_min.astimezone(_tz()).isoformat(),
                timeMax=time_max.astimezone(_tz()).isoformat(),
                singleEvents=True,
                orderBy="startTime",
                maxResults=max_results,
            )
            .execute()
        )
    except Exception as exc:  # noqa: BLE001 - convertemos em erro amigável
        raise CalendarError(f"Falha ao consultar o Google Calendar: {exc}") from exc

    return [
        _to_event(item)
        for item in result.get("items", [])
        if item.get("status") != "cancelled"
    ]


def list_all_events(
    time_min: datetime, time_max: datetime, page_limit: int = 250, max_events: int = 5000
) -> list[Event]:
    """Lista TODOS os eventos do intervalo, paginando (para limpezas)."""
    service = _service()
    events: list[Event] = []
    page_token: str | None = None
    while True:
        try:
            result = (
                service.events()
                .list(
                    calendarId=config.GOOGLE_CALENDAR_ID,
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


def delete_events(events: list[Event]) -> tuple[int, int]:
    """Apaga uma lista de eventos. Devolve (apagados, falhas)."""
    deleted = 0
    failed = 0
    for event in events:
        try:
            delete_event(event.id)
            deleted += 1
        except CalendarError:
            failed += 1
    return deleted, failed


def create_event(
    summary: str,
    start: datetime,
    end: datetime,
    *,
    description: str | None = None,
    location: str | None = None,
) -> Event:
    service = _service()
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
            service.events()
            .insert(calendarId=config.GOOGLE_CALENDAR_ID, body=body)
            .execute()
        )
    except Exception as exc:  # noqa: BLE001
        raise CalendarError(f"Falha ao criar o evento: {exc}") from exc
    return _to_event(created)


def delete_event(event_id: str) -> None:
    service = _service()
    try:
        service.events().delete(
            calendarId=config.GOOGLE_CALENDAR_ID, eventId=event_id
        ).execute()
    except Exception as exc:  # noqa: BLE001
        raise CalendarError(f"Falha ao cancelar o evento: {exc}") from exc


def find_event_by_prefix(prefix: str) -> Event | None:
    """Busca um evento futuro cujo ID comece pelo prefixo informado."""
    now = datetime.now(_tz())
    events = list_events(now - timedelta(minutes=1), now + timedelta(days=365), max_results=250)
    prefix = prefix.strip()
    for event in events:
        if event.id == prefix:
            return event
    for event in events:
        if event.id.startswith(prefix):
            return event
    return None
