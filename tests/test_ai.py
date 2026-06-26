import json
from datetime import date, datetime, time
from types import SimpleNamespace
from zoneinfo import ZoneInfo

from app.ai.agent import _build_context, run_agent
from app.ai.tools import execute_tool
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


# ── execução de ferramentas (reaproveita as regras) ──────────────────
def test_tool_registrar_inicio_sono():
    repo = FakeRepository()
    msg = execute_tool(repo, ELOA, "cg1", CONFIG, at(13, 5),
                       "registrar_inicio_sono", {"horario": "13:00", "local": "colo"})
    assert "Soneca iniciada às 13:00" in msg
    s = repo.get_open_session("c1")
    assert s["location"] == "arms"


def test_tool_registrar_mamada():
    repo = FakeRepository()
    msg = execute_tool(repo, ELOA, "cg1", CONFIG, at(15, 5),
                       "registrar_mamada", {"horario": "15:00"})
    assert "Mamada registrada às 15:00" in msg
    assert len(repo.feedings) == 1


def test_tool_acordou_enforces_rules():
    # Sem sono aberto -> a regra de negócio responde o erro.
    repo = FakeRepository()
    msg = execute_tool(repo, ELOA, "cg1", CONFIG, at(14), "registrar_acordou", {})
    assert "Não há sono em andamento" in msg


def test_tool_registra_dificuldade():
    repo = FakeRepository()
    execute_tool(repo, ELOA, "cg1", CONFIG, at(13, 5), "registrar_inicio_sono",
                 {"horario": "13:00", "dificuldade": "trabalho"})
    assert repo.sessions[0]["difficulty"] == "hard"


def test_tool_sugerir_bedtime_with_constraint():
    repo = FakeRepository()
    s = repo.create_session("c1", "cg1", "nap", at(16), "crib")
    repo.end_session(s["id"], at(17))             # acordou 17h
    # Sem restrição: bedtime ideal cai na janela [19:00, 20:30].
    msg = execute_tool(repo, ELOA, "cg1", CONFIG, at(17, 30), "sugerir_bedtime", {})
    assert "Bedtime sugerido" in msg
    # Com restrição "só após 20:30": empurra o bedtime.
    msg2 = execute_tool(repo, ELOA, "cg1", CONFIG, at(17, 30),
                        "sugerir_bedtime", {"nao_antes": "20:30"})
    assert "20:30" in msg2
    assert "19:30" in msg2     # rotina 1h antes
    assert "20:00" in msg2     # banho 30min antes


def test_tool_historico():
    repo = FakeRepository()
    # Dois dias com sonecas/mamadas.
    for day in (20, 21):
        s = repo.create_session("c1", "cg1", "nap",
                                datetime(2026, 6, day, 9, 0, tzinfo=TZ), "crib")
        repo.end_session(s["id"], datetime(2026, 6, day, 10, 0, tzinfo=TZ))
        repo.create_feeding("c1", "cg1", datetime(2026, 6, day, 10, 30, tzinfo=TZ))
    out = execute_tool(repo, ELOA, "cg1", CONFIG,
                       datetime(2026, 6, 22, 8, 0, tzinfo=TZ), "consultar_historico", {"dias": 3})
    assert "20/06" in out and "21/06" in out
    assert "1 soneca(s)" in out and "1h" in out


# ── contexto injetado no prompt ──────────────────────────────────────
def test_build_context_reports_state_and_day():
    repo = FakeRepository()
    repo.create_session("c1", "cg1", "nap", at(9), "crib")
    repo.end_session(repo.sessions[0]["id"], at(10))     # soneca de 1h
    repo.create_feeding("c1", "cg1", at(10, 30))
    ctx = _build_context(repo, ELOA, CONFIG, at(11))
    assert "Eloá, 15 semanas" in ctx
    assert "ACORDADA desde 10:00" in ctx
    assert "1 soneca(s), total 1h" in ctx
    assert "1 mamada(s)" in ctx


# ── laço de tool use com LLM falso ───────────────────────────────────
def _msg(content=None, tool_calls=None):
    return SimpleNamespace(content=content, tool_calls=tool_calls)


def _tool_call(call_id, name, args):
    return SimpleNamespace(
        id=call_id, function=SimpleNamespace(name=name, arguments=json.dumps(args))
    )


def _resp(message):
    return SimpleNamespace(choices=[SimpleNamespace(message=message)])


def _scripted_completion(steps):
    it = iter(steps)

    def completion(**kwargs):
        return _resp(next(it))

    return completion


def test_agent_executes_tool_then_answers():
    repo = FakeRepository()
    # 1ª resposta do modelo: chama a ferramenta de mamada.
    # 2ª resposta: texto final pro usuário.
    steps = [
        _msg(tool_calls=[_tool_call("t1", "registrar_mamada", {"horario": "15:00"})]),
        _msg(content="🍼 Anotei a mamada das 15:00!"),
    ]
    out = run_agent(repo, ELOA, "cg1", CONFIG, "ela mamou às 15h",
                    at(15, 5), completion=_scripted_completion(steps))
    assert out == "🍼 Anotei a mamada das 15:00!"
    assert len(repo.feedings) == 1            # a ferramenta realmente registrou


def test_clean_content_strips_leaked_tool_tags():
    from app.ai.agent import _clean_content
    out = _clean_content("Sim, é normal. <function=consultar_status></function>")
    assert "function" not in out
    assert out == "Sim, é normal."


def test_agent_plain_answer_without_tools():
    repo = FakeRepository()
    steps = [_msg(content="Catnaps de 30–45min são normais nessa fase 🙂")]
    out = run_agent(repo, ELOA, "cg1", CONFIG, "soneca curta é normal?",
                    at(14), completion=_scripted_completion(steps))
    assert "normais" in out
    assert repo.feedings == []                 # nada foi registrado


def test_agent_passes_tools_and_model(monkeypatch):
    repo = FakeRepository()
    seen = {}

    def completion(**kwargs):
        seen.update(kwargs)
        return _resp(_msg(content="ok"))

    monkeypatch.setenv("LLM_MODEL", "gemini/gemini-2.0-flash")
    run_agent(repo, ELOA, "cg1", CONFIG, "oi", at(14), completion=completion)
    assert seen["model"] == "gemini/gemini-2.0-flash"     # provedor vem do .env
    assert len(seen["tools"]) == 6                         # ferramentas expostas
