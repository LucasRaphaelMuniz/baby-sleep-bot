from datetime import date, datetime, time

import pytest

from app.core.wake_window import (
    WakeWindowConfig,
    age_in_weeks,
    bedtime_plan,
    compute_window,
    is_overtired,
    minutes_awake,
    suggest_bedtime,
    window_minutes_for_age,
)

# Config de teste espelhando o YAML padrão (não depende de I/O).
CONFIG = WakeWindowConfig(
    bands=(
        (6, 60, 75),
        (12, 75, 90),
        (17, 90, 120),
        (26, 120, 150),
        (52, 150, 210),
        (9999, 240, 300),
    ),
    bedtime_window=(time(19, 0), time(20, 30)),
    reminder_lead_minutes=20,
    quiet_hours=(time(20, 30), time(6, 0)),
)

# Eloá nasceu em 03/03/2026.
ELOA_BIRTH = date(2026, 3, 3)


def test_age_in_weeks():
    # 03/03 -> 22/06 = 111 dias = 15 semanas completas.
    assert age_in_weeks(ELOA_BIRTH, date(2026, 6, 22)) == 15


def test_age_never_negative():
    assert age_in_weeks(ELOA_BIRTH, date(2026, 3, 1)) == 0


@pytest.mark.parametrize(
    "weeks,expected",
    [
        (0, (60, 75)),
        (6, (60, 75)),
        (7, (75, 90)),
        (15, (90, 120)),   # Eloá hoje
        (20, (120, 150)),
        (40, (150, 210)),
        (200, (240, 300)),
    ],
)
def test_window_minutes_for_age(weeks, expected):
    assert window_minutes_for_age(weeks, CONFIG) == expected


def test_compute_window():
    woke = datetime(2026, 6, 22, 13, 0)
    win = compute_window(woke, ELOA_BIRTH, CONFIG)
    assert win.ideal_minutes == 90
    assert win.max_minutes == 120
    assert win.close_ideal == datetime(2026, 6, 22, 14, 30)
    assert win.close_max == datetime(2026, 6, 22, 15, 0)
    # Lembrete 20 min antes do fechamento ideal.
    assert win.reminder_at == datetime(2026, 6, 22, 14, 10)


def test_minutes_awake():
    woke = datetime(2026, 6, 22, 13, 0)
    assert minutes_awake(datetime(2026, 6, 22, 14, 15), woke) == 75


def test_is_overtired():
    woke = datetime(2026, 6, 22, 13, 0)
    win = compute_window(woke, ELOA_BIRTH, CONFIG)
    assert not is_overtired(datetime(2026, 6, 22, 14, 59), win)
    assert is_overtired(datetime(2026, 6, 22, 15, 0), win)


def test_suggest_bedtime_clamped_to_window():
    # Última soneca termina cedo -> alvo cairia antes das 19h -> limita a 19h.
    last_wake = datetime(2026, 6, 22, 16, 0)
    assert suggest_bedtime(last_wake, ELOA_BIRTH, CONFIG) == datetime(2026, 6, 22, 19, 0)


def test_suggest_bedtime_within_window():
    # Acordou 17:40, janela ideal 90min -> 19:10, dentro de [19:00, 20:30].
    last_wake = datetime(2026, 6, 22, 17, 40)
    assert suggest_bedtime(last_wake, ELOA_BIRTH, CONFIG) == datetime(2026, 6, 22, 19, 10)


def test_bedtime_plan_routine_offsets():
    last_wake = datetime(2026, 6, 22, 17, 40)
    plan = bedtime_plan(last_wake, ELOA_BIRTH, CONFIG)
    assert plan.bedtime == datetime(2026, 6, 22, 19, 10)
    assert plan.start_routine == datetime(2026, 6, 22, 18, 10)   # 60min antes
    assert plan.bath == datetime(2026, 6, 22, 18, 40)            # 30min antes


def test_bedtime_plan_earliest_constraint_overrides():
    # "Só consigo após 21h" empurra o bedtime para além da janela ideal.
    last_wake = datetime(2026, 6, 22, 17, 40)
    plan = bedtime_plan(last_wake, ELOA_BIRTH, CONFIG, earliest=time(21, 0))
    assert plan.bedtime == datetime(2026, 6, 22, 21, 0)
    assert plan.start_routine == datetime(2026, 6, 22, 20, 0)
    assert plan.bath == datetime(2026, 6, 22, 20, 30)
