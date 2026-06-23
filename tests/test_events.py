from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pytest

from app.core.events import fmt_duration, handle_command, resolve_event_time
from app.core.parser import parse
from app.core.wake_window import WakeWindowConfig
from tests.fakes import FakeRepository

TZ = ZoneInfo("America/Sao_Paulo")

CONFIG = WakeWindowConfig(
    bands=((6, 60, 75), (12, 75, 90), (17, 90, 120), (26, 120, 150),
           (52, 150, 210), (9999, 240, 300)),
    bedtime_window=(time(19, 0), time(20, 30)),
    reminder_lead_minutes=20,
    quiet_hours=(time(20, 30), time(6, 0)),
)

ELOA = {"id": "c1", "name": "Eloá", "birth_date": date(2026, 3, 3)}


def at(h, m=0):
    return datetime(2026, 6, 22, h, m, tzinfo=TZ)


def at_next(h, m=0):
    # Madrugada/manhã do dia seguinte (noite atravessa a meia-noite).
    return datetime(2026, 6, 23, h, m, tzinfo=TZ)


def run(repo, text, now):
    return handle_command(repo, ELOA, "cg1", parse(text), now, CONFIG)


# ── helpers ──────────────────────────────────────────────────────────
@pytest.mark.parametrize("mins,expected", [(0, "0min"), (45, "45min"),
                                           (60, "1h"), (90, "1h30"), (125, "2h05")])
def test_fmt_duration(mins, expected):
    assert fmt_duration(mins) == expected


def test_resolve_event_time_uses_now_when_none():
    assert resolve_event_time(None, at(14)) == at(14)


def test_resolve_event_time_combines_hour():
    assert resolve_event_time(time(13, 30), at(15)) == at(13, 30)


# ── fluxo de sono ────────────────────────────────────────────────────
def test_sleep_then_wake_flow():
    repo = FakeRepository()
    r1 = run(repo, "1 13:00", at(13, 5))
    assert r1.ok and "13:00" in r1.message
    assert repo.get_open_session("c1") is not None

    r2 = run(repo, "2 14:30", at(14, 35))
    assert r2.ok
    assert "dormiu 1h30" in r2.message
    assert "16:00" in r2.message      # próximo sono ideal (acordou 14:30 + 90min)
    assert "16:30" in r2.message      # limite máx (+120min)
    assert "15:40" in r2.message      # lembrete (20min antes do ideal)
    assert repo.get_open_session("c1") is None


def test_sleep_when_already_sleeping_is_rejected():
    repo = FakeRepository()
    run(repo, "1 13:00", at(13, 5))
    r = run(repo, "1 13:30", at(13, 35))
    assert not r.ok
    assert "já está dormindo" in r.message


def test_wake_without_open_session_is_rejected():
    repo = FakeRepository()
    r = run(repo, "2", at(14))
    assert not r.ok
    assert "Não há sono em andamento" in r.message


def test_future_time_is_rejected():
    repo = FakeRepository()
    r = run(repo, "1 16:00", at(14))   # 16h ainda não chegou
    assert not r.ok
    assert "futuro" in r.message


def test_wake_before_start_is_rejected():
    repo = FakeRepository()
    run(repo, "1 14:00", at(14, 5))
    r = run(repo, "2 13:00", at(14, 30))
    assert not r.ok
    assert "antes do início" in r.message


def test_night_session_kind():
    repo = FakeRepository()
    r = run(repo, "5 20:00", at(20, 5))
    assert r.ok and "noite" in r.message.lower()
    assert repo.get_open_session("c1")["kind"] == "night"


# ── mamada ───────────────────────────────────────────────────────────
def test_feed():
    repo = FakeRepository()
    r = run(repo, "3 15:00", at(15, 5))
    assert r.ok and "Mamada" in r.message
    assert len(repo.feedings) == 1


# ── status ───────────────────────────────────────────────────────────
def test_status_while_sleeping():
    repo = FakeRepository()
    run(repo, "1 13:00", at(13, 5))
    r = run(repo, "6", at(13, 50))
    assert "está na soneca" in r.message
    assert "há 50min" in r.message


def test_status_while_awake_with_overtired():
    repo = FakeRepository()
    run(repo, "1 13:00", at(13, 5))
    run(repo, "2 13:30", at(13, 35))   # janela ideal fecha 15:00, máx 15:30
    r = run(repo, "6", at(15, 45))     # já passou do limite
    assert "acordada desde 13:30" in r.message
    assert "overtired" in r.message


def test_status_no_records():
    repo = FakeRepository()
    r = run(repo, "6", at(14))
    assert "Nenhum registro" in r.message


def test_wake_response_shows_bedtime():
    repo = FakeRepository()
    run(repo, "1 16:00", at(16, 5))
    r = run(repo, "2 17:30", at(17, 35))
    assert "Bedtime sugerido" in r.message
    assert "rotina" in r.message and "banho" in r.message


def test_status_awake_shows_bedtime():
    repo = FakeRepository()
    run(repo, "1 12:00", at(12, 5))
    run(repo, "2 13:00", at(13, 5))
    r = run(repo, "6", at(13, 30))
    assert "Bedtime sugerido" in r.message
    assert "rotina" in r.message and "banho" in r.message


def test_sleep_registers_difficulty_and_shows_tags():
    repo = FakeRepository()
    r = run(repo, "1 14 colo trabalho", at(14, 5))
    assert "colo" in r.message and "deu trabalho" in r.message
    assert repo.sessions[0]["difficulty"] == "hard"
    assert repo.sessions[0]["location"] == "arms"


# ── desfazer ─────────────────────────────────────────────────────────
def test_undo_removes_last_event():
    repo = FakeRepository()
    run(repo, "1 13:00", at(13, 5))
    run(repo, "3 13:10", at(13, 15))   # mamada é o último evento
    r = run(repo, "desfazer", at(13, 20))
    assert r.ok and "Mamada" in r.message
    assert len(repo.feedings) == 0
    assert len(repo.sessions) == 1     # a soneca permanece


def test_undo_nothing():
    repo = FakeRepository()
    r = run(repo, "0", at(14))
    assert not r.ok and "Nada para desfazer" in r.message


# ── modo noite ───────────────────────────────────────────────────────
def test_night_feed_does_not_end_session():
    repo = FakeRepository()
    run(repo, "5 20:00", at(20, 5))
    r = run(repo, "3 23:00", at(23, 5))   # mamada da noite
    assert r.ok
    assert "Mamada da noite" in r.message
    assert "1º despertar" in r.message
    # A noite continua aberta — não virou "acordar definitivo".
    assert repo.get_open_session("c1") is not None


def test_night_feed_counts_wakings():
    repo = FakeRepository()
    run(repo, "5 20:00", at(20, 5))
    run(repo, "3 23:00", at(23, 5))
    r = run(repo, "3 03:00", at_next(3, 5))
    assert "2º despertar" in r.message


def test_night_status_lists_wakings():
    repo = FakeRepository()
    run(repo, "5 20:00", at(20, 5))
    run(repo, "3 23:00", at(23, 5))
    run(repo, "3 03:00", at_next(3, 5))
    r = run(repo, "6", at_next(5))
    assert "na noite desde 20:00" in r.message
    assert "2 despertar(es)" in r.message
    assert "23:00" in r.message and "03:00" in r.message


def test_morning_wake_ends_night_with_summary():
    repo = FakeRepository()
    run(repo, "5 20:00", at(20, 5))
    run(repo, "3 23:00", at(23, 5))
    run(repo, "3 03:00", at_next(3, 5))
    r = run(repo, "2 07:00", at_next(7, 5))   # bom dia
    assert r.ok
    assert "Bom dia" in r.message
    assert "11h" in r.message                 # 20:00 -> 07:00
    assert "2 despertar(es)" in r.message
    assert repo.get_open_session("c1") is None
    # Começa o dia: calcula a 1ª janela (07:00 + 90min = 08:30).
    assert "08:30" in r.message


# ── roteamento p/ IA ─────────────────────────────────────────────────
def test_natural_language_flag():
    repo = FakeRepository()
    r = run(repo, "ela dormiu bem essa noite?", at(9))
    assert r.to_ai is True


def test_bare_number_error_passthrough():
    repo = FakeRepository()
    r = run(repo, "14", at(14))
    assert not r.ok and "14" in r.message
