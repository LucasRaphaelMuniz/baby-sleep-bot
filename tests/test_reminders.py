from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.notifications.reminders import in_quiet_hours, run_reminder_check
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


def at(h, m=0):
    return datetime(2026, 6, 22, h, m, tzinfo=TZ)


def make_repo():
    """Eloá acordada desde 13:00; janela ideal 14:30, máx 15:00, lembrete 14:10."""
    repo = FakeRepository()
    cg1 = repo.create_caregiver("+5511111111111")
    cg2 = repo.create_caregiver("+5522222222222")
    child = repo.create_child("Eloá", date(2026, 3, 3), "America/Sao_Paulo")
    repo.link_caregiver_child(cg1["id"], child["id"])
    repo.link_caregiver_child(cg2["id"], child["id"])
    s = repo.create_session(child["id"], cg1["id"], "nap", at(12), "crib")
    repo.end_session(s["id"], at(13))     # acordou 13:00
    return repo, child


class Spy:
    def __init__(self):
        self.sent = []

    def __call__(self, phone, text):
        self.sent.append((phone, text))


# ── quiet hours ──────────────────────────────────────────────────────
def test_in_quiet_hours_wraps_midnight():
    q = (time(20, 30), time(6, 0))
    assert in_quiet_hours(time(23, 0), q)
    assert in_quiet_hours(time(3, 0), q)
    assert not in_quiet_hours(time(14, 0), q)


# ── estágio 1: lembrete ──────────────────────────────────────────────
def test_no_reminder_before_lead_time():
    repo, _ = make_repo()
    spy = Spy()
    assert run_reminder_check(repo, CONFIG, at(14, 0), spy) == []   # antes das 14:10
    assert spy.sent == []


def test_reminder_fires_to_both_caregivers():
    repo, _ = make_repo()
    spy = Spy()
    actions = run_reminder_check(repo, CONFIG, at(14, 12), spy)
    assert len(actions) == 1 and actions[0]["stage"] == "reminder"
    assert {p for p, _ in spy.sent} == {"+5511111111111", "+5522222222222"}
    assert all("janela ideal" in t.lower() for _, t in spy.sent)


def test_reminder_not_resent():
    repo, _ = make_repo()
    spy = Spy()
    run_reminder_check(repo, CONFIG, at(14, 12), spy)
    run_reminder_check(repo, CONFIG, at(14, 20), spy)   # 2ª passada do cron
    assert len(spy.sent) == 2                           # só os 2 do 1º disparo


# ── estágio 2: overtired ─────────────────────────────────────────────
def test_overtired_fires_after_max():
    repo, _ = make_repo()
    spy = Spy()
    actions = run_reminder_check(repo, CONFIG, at(15, 5), spy)   # passou das 15:00
    assert actions[0]["stage"] == "overtired"
    assert all("overtired" in t.lower() for _, t in spy.sent)


def test_overtired_not_resent():
    repo, _ = make_repo()
    spy = Spy()
    run_reminder_check(repo, CONFIG, at(15, 5), spy)
    run_reminder_check(repo, CONFIG, at(15, 30), spy)
    assert len(spy.sent) == 2


# ── silêncios ────────────────────────────────────────────────────────
def test_no_reminder_while_sleeping():
    repo, child = make_repo()
    repo.create_session(child["id"], None, "nap", at(14, 5), "crib")  # dormiu de novo
    spy = Spy()
    assert run_reminder_check(repo, CONFIG, at(14, 30), spy) == []
    assert spy.sent == []


def test_no_reminder_during_quiet_hours():
    repo, _ = make_repo()
    spy = Spy()
    # 21:00 está dentro de quiet_hours -> nada dispara, mesmo acordada.
    assert run_reminder_check(repo, CONFIG, at(21, 0), spy) == []


def test_new_wake_period_reminds_again():
    # Dorme e acorda de novo -> nova janela (nova since_session_id) -> novo lembrete.
    repo, child = make_repo()
    spy = Spy()
    run_reminder_check(repo, CONFIG, at(14, 12), spy)        # lembrete da 1ª janela
    s2 = repo.create_session(child["id"], None, "nap", at(14, 30), "crib")
    repo.end_session(s2["id"], at(15, 0))                    # acordou de novo 15:00
    run_reminder_check(repo, CONFIG, at(16, 25), spy)        # 15:00+90-20 = 16:10
    stages = [t for _, t in spy.sent]
    assert len(spy.sent) == 4                                # 2 + 2 cuidadores
