from datetime import date, datetime, time
from zoneinfo import ZoneInfo

from app.handler import normalize_phone, parse_birth_date, process_message
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

LUCAS = "whatsapp:+5511988887777"
YASMIN = "whatsapp:+5511955554444"


def now():
    return datetime(2026, 6, 22, 13, 0, tzinfo=TZ)


def send(repo, phone, body, at=None):
    return process_message(repo, CONFIG, phone, body, at or now())


# ── helpers ──────────────────────────────────────────────────────────
def test_normalize_phone():
    assert normalize_phone("whatsapp:+55 11 98888-7777") == "+5511988887777"
    assert normalize_phone("5511955554444") == "+5511955554444"


def test_parse_birth_date():
    assert parse_birth_date("03/03/2026") == date(2026, 3, 3)
    assert parse_birth_date("3-3-26") == date(2026, 3, 3)
    assert parse_birth_date("31/02/2026") is None
    assert parse_birth_date("ontem") is None


# ── onboarding ───────────────────────────────────────────────────────
def test_onboarding_full_flow_with_partner():
    repo = FakeRepository()

    r1 = send(repo, LUCAS, "oi")
    assert "nome" in r1.lower()

    r2 = send(repo, LUCAS, "Eloá")
    assert "data de nascimento" in r2.lower()

    r3 = send(repo, LUCAS, "03/03/2026")
    assert "outro cuidador" in r3.lower()
    # Bebê e cuidador criados e vinculados.
    cg = repo.get_caregiver_by_phone("+5511988887777")
    assert cg is not None
    child = repo.get_child_for_caregiver(cg["id"])
    assert child["name"] == "Eloá" and child["birth_date"] == date(2026, 3, 3)

    r4 = send(repo, LUCAS, "+5511955554444")
    assert "adicionado" in r4.lower()
    # Yasmin já vinculada à mesma Eloá.
    yas = repo.get_caregiver_by_phone("+5511955554444")
    assert repo.get_child_for_caregiver(yas["id"])["id"] == child["id"]
    # Onboarding encerrado.
    assert repo.get_onboarding_state("+5511988887777") is None


def test_onboarding_decline_partner():
    repo = FakeRepository()
    send(repo, LUCAS, "oi")
    send(repo, LUCAS, "Eloá")
    send(repo, LUCAS, "03/03/2026")
    r = send(repo, LUCAS, "não")
    assert "Tudo certo" in r
    assert repo.get_onboarding_state("+5511988887777") is None


def test_onboarding_invalid_date_reasks():
    repo = FakeRepository()
    send(repo, LUCAS, "oi")
    send(repo, LUCAS, "Eloá")
    r = send(repo, LUCAS, "amanhã")
    assert "formato" in r.lower()
    # Continua no passo da data.
    assert repo.get_onboarding_state("+5511988887777")["step"] == "awaiting_birth"


# ── multiusuário (estado compartilhado) ──────────────────────────────
def _onboard(repo):
    send(repo, LUCAS, "oi")
    send(repo, LUCAS, "Eloá")
    send(repo, LUCAS, "03/03/2026")
    send(repo, LUCAS, "+5511955554444")   # adiciona Yasmin


def test_shared_state_between_caregivers():
    repo = FakeRepository()
    _onboard(repo)

    # Yasmin registra a soneca.
    r_y = send(repo, YASMIN, "1 13:00", at=datetime(2026, 6, 22, 13, 5, tzinfo=TZ))
    assert "Soneca iniciada" in r_y

    # Lucas pede status e vê o registro da Yasmin.
    r_l = send(repo, LUCAS, "4", at=datetime(2026, 6, 22, 13, 50, tzinfo=TZ))
    assert "está na soneca desde 13:00" in r_l

    # Lucas encerra a MESMA soneca que a Yasmin abriu.
    r_l2 = send(repo, LUCAS, "2 14:30", at=datetime(2026, 6, 22, 14, 35, tzinfo=TZ))
    assert "Acordou às 14:30" in r_l2


def test_yasmin_skips_onboarding():
    repo = FakeRepository()
    _onboard(repo)
    # Primeira mensagem da Yasmin já cai no fluxo normal (sem onboarding).
    r = send(repo, YASMIN, "4", at=datetime(2026, 6, 22, 13, 0, tzinfo=TZ))
    assert "Nenhum registro" in r
    assert repo.get_onboarding_state("+5511955554444") is None


def test_natural_language_routes_to_agent(monkeypatch):
    repo = FakeRepository()
    _onboard(repo)

    captured = {}

    def fake_agent(repo_, child, caregiver_id, config, text, now_):
        captured["text"] = text
        return "resposta da IA 🤖"

    import app.ai.agent as agent_mod
    monkeypatch.setattr(agent_mod, "run_agent", fake_agent)

    r = send(repo, LUCAS, "ela tá dormindo pouco hoje?")
    assert r == "resposta da IA 🤖"
    assert captured["text"] == "ela tá dormindo pouco hoje?"
