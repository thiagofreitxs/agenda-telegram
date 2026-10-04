"""Testes básicos do parser de datas em linguagem natural.

Rode com:  python -m pytest  (ou apenas python tests/test_parsing.py)
"""

from __future__ import annotations

import os
import sys
from datetime import datetime, timedelta
from zoneinfo import ZoneInfo

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from app.utils.parsing import parse_event_text  # noqa: E402

TZ = "America/Sao_Paulo"


def test_absolute_date_and_time():
    parsed = parse_event_text("Dentista 25/12/2026 às 14:30", timezone=TZ)
    assert parsed is not None
    assert parsed.title == "Dentista"
    assert parsed.start.year == 2026
    assert parsed.start.month == 12
    assert parsed.start.day == 25
    assert parsed.start.hour == 14
    assert parsed.start.minute == 30


def test_relative_day_uses_default_time():
    parsed = parse_event_text("Pagar contas amanhã", timezone=TZ, default_time="09:00")
    assert parsed is not None
    assert parsed.title == "Pagar contas"
    assert parsed.start.hour == 9
    assert parsed.start.minute == 0


def test_no_date_returns_none():
    assert parse_event_text("apenas um texto qualquer", timezone=TZ) is None


def test_duration_applied():
    parsed = parse_event_text("Reunião 25/12/2026 10:00", timezone=TZ, duration_min=30)
    assert parsed is not None
    assert parsed.end - parsed.start == timedelta(minutes=30)


if __name__ == "__main__":
    falhas = 0
    for nome, funcao in sorted(globals().items()):
        if nome.startswith("test_") and callable(funcao):
            try:
                funcao()
                print(f"PASS  {nome}")
            except AssertionError as exc:  # noqa: PERF203
                falhas += 1
                print(f"FAIL  {nome}: {exc}")
    raise SystemExit(1 if falhas else 0)
