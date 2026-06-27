"""Ferramentas (tool use) que a IA pode chamar.

Os schemas seguem o formato de function-calling do LiteLLM (compatível com
Anthropic/OpenAI/Gemini). A execução reaproveita `events.handle_command`, então
toda regra de negócio já testada (hora futura, "já está dormindo", modo noite…)
vale também quando a IA registra por linguagem natural.
"""
from __future__ import annotations

from datetime import datetime, time, timedelta

from app.core.events import _hhmm, fmt_duration, handle_command
from app.core.history import summarize_days
from app.core.parser import CommandType, ParsedCommand, parse_time
from app.core.wake_window import WakeWindowConfig, bedtime_plan
from app.repository import Repository

# Mesmo vocabulário de local do parser (pt-BR -> canônico).
_LOCATIONS = {
    "berço": "crib", "berco": "crib", "colo": "arms",
    "carrinho": "stroller", "carro": "car", "peito": "breast",
}
_DIFFICULTIES = {"fácil": "easy", "tranquilo": "easy", "trabalho": "hard", "difícil": "hard"}

TOOL_SCHEMAS = [
    {
        "type": "function",
        "function": {
            "name": "registrar_inicio_sono",
            "description": "Registra que o bebê começou a dormir (soneca ou sono noturno).",
            "parameters": {
                "type": "object",
                "properties": {
                    "horario": {"type": "string", "description": "Horário HH:MM. Omita para usar a hora atual."},
                    "tipo": {"type": "string", "enum": ["soneca", "noite"], "description": "Soneca (padrão) ou sono noturno."},
                    "local": {"type": "string", "enum": list(_LOCATIONS), "description": "Onde adormeceu, se informado."},
                    "dificuldade": {"type": "string", "enum": ["fácil", "trabalho"], "description": "Como foi pra dormir, se informado."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_acordou",
            "description": "Registra que o bebê acordou (encerra o sono em andamento). À noite, encerra a noite = bom dia.",
            "parameters": {
                "type": "object",
                "properties": {
                    "horario": {"type": "string", "description": "Horário HH:MM. Omita para usar a hora atual."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "registrar_mamada",
            "description": "Registra uma mamada. Durante o sono noturno, conta como despertar da noite.",
            "parameters": {
                "type": "object",
                "properties": {
                    "horario": {"type": "string", "description": "Horário HH:MM. Omita para usar a hora atual."},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_status",
            "description": "Consulta o estado atual do bebê (dormindo/acordada) e a próxima janela de sono.",
            "parameters": {"type": "object", "properties": {}},
        },
    },
    {
        "type": "function",
        "function": {
            "name": "consultar_historico",
            "description": "Resumo do sono dos últimos N dias (sonecas, mamadas, horário do bedtime). Use para perguntas sobre padrões/tendências.",
            "parameters": {
                "type": "object",
                "properties": {
                    "dias": {"type": "integer", "description": "Quantidade de dias (incluindo hoje). Padrão 3.", "default": 3},
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "apagar_evento",
            "description": (
                "Apaga um evento específico do banco. Use quando o usuário pedir para "
                "remover ou apagar um registro (ex.: 'apaga a mamada das 02:00'). "
                "Identifique o tipo e o horário e chame esta ferramenta."
            ),
            "parameters": {
                "type": "object",
                "required": ["tipo", "horario"],
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["soneca", "noite", "mamada", "despertar"],
                        "description": "Tipo do evento a apagar.",
                    },
                    "horario": {
                        "type": "string",
                        "description": "Horário HH:MM do evento a apagar.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "editar_horario",
            "description": (
                "Corrige o horário de um evento existente. Use quando o usuário disser "
                "'troca', 'corrige', 'muda', 'substitui' o horário de algum registro "
                "(ex.: 'a soneca das 13h foi na verdade às 13:30')."
            ),
            "parameters": {
                "type": "object",
                "required": ["tipo", "horario_atual", "horario_novo"],
                "properties": {
                    "tipo": {
                        "type": "string",
                        "enum": ["soneca_inicio", "soneca_fim", "noite_inicio", "noite_fim", "mamada", "despertar"],
                        "description": "Qual campo do evento editar.",
                    },
                    "horario_atual": {
                        "type": "string",
                        "description": "Horário HH:MM atual do evento (para localizá-lo).",
                    },
                    "horario_novo": {
                        "type": "string",
                        "description": "Novo horário HH:MM que deve substituir o atual.",
                    },
                },
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "sugerir_bedtime",
            "description": "Sugere o horário de bedtime e a rotina (início do ritual e banho). Use 'nao_antes' quando os pais tiverem uma restrição (ex.: 'só consigo após 20h').",
            "parameters": {
                "type": "object",
                "properties": {
                    "nao_antes": {"type": "string", "description": "Horário mínimo HH:MM, se houver restrição."},
                },
            },
        },
    },
]


def execute_tool(
    repo: Repository,
    child: dict,
    caregiver_id,
    config: WakeWindowConfig,
    now: datetime,
    name: str,
    args: dict,
) -> str:
    """Executa uma ferramenta e devolve o texto-resultado (vai de volta à IA)."""
    at = parse_time(args["horario"]) if args.get("horario") else None

    if name == "registrar_inicio_sono":
        kind = CommandType.NIGHT if args.get("tipo") == "noite" else CommandType.SLEEP_START
        cmd = ParsedCommand(
            kind, at=at,
            location=_LOCATIONS.get(args.get("local", "")),
            difficulty=_DIFFICULTIES.get(args.get("dificuldade", "")),
        )
    elif name == "registrar_acordou":
        cmd = ParsedCommand(CommandType.WAKE, at=at)
    elif name == "registrar_mamada":
        cmd = ParsedCommand(CommandType.FEED, at=at)
    elif name == "consultar_status":
        cmd = ParsedCommand(CommandType.STATUS)
    elif name == "consultar_historico":
        return _historico(repo, child, now, int(args.get("dias", 3)))
    elif name == "apagar_evento":
        return _apagar_evento(repo, child, now, args["tipo"], args["horario"])
    elif name == "editar_horario":
        return _editar_horario(repo, child, now, args["tipo"], args["horario_atual"], args["horario_novo"])
    elif name == "sugerir_bedtime":
        return _bedtime(repo, child, config, now, args.get("nao_antes"))
    else:
        return "Ferramenta desconhecida."

    return handle_command(repo, child, caregiver_id, cmd, now, config).message


def _historico(repo, child, now, dias) -> str:
    dias = max(1, min(dias, 30))
    since = datetime.combine(now.date() - timedelta(days=dias - 1), time(0, 0), tzinfo=now.tzinfo)
    sessions = repo.get_sessions_since(child["id"], since)
    feedings = repo.get_feedings_since(child["id"], since)
    return summarize_days(sessions, feedings, now, dias)


def _resolve_dt(horario: str, now: datetime) -> datetime:
    """Converte HH:MM para datetime no mesmo dia (ou ontem se futuro)."""
    from datetime import timedelta
    t = parse_time(horario)
    if t is None:
        raise ValueError(f"Horário inválido: {horario}")
    dt = datetime.combine(now.date(), t, tzinfo=now.tzinfo)
    if dt > now:
        dt -= timedelta(days=1)
    return dt


def _apagar_evento(repo, child, now: datetime, tipo: str, horario: str) -> str:
    dt = _resolve_dt(horario, now)
    open_session = repo.get_open_session(child["id"])

    if tipo == "mamada":
        ev = repo.find_feeding_near(child["id"], dt)
        if not ev:
            return f"Não encontrei mamada próxima de {horario}."
        repo.delete_feeding(ev["id"])
        return f"✅ Mamada das {horario} apagada."

    if tipo == "despertar":
        if not open_session:
            return "Não há noite em andamento para remover despertar."
        ev = repo.find_night_waking_near(open_session["id"], dt)
        if not ev:
            return f"Não encontrei despertar próximo de {horario}."
        repo.delete_night_waking(ev["id"])
        return f"✅ Despertar das {horario} apagado."

    kind = "night" if tipo == "noite" else "nap"
    ev = repo.find_session_near(child["id"], dt, kind=kind)
    if not ev:
        return f"Não encontrei {'noite' if kind == 'night' else 'soneca'} próxima de {horario}."
    repo.delete_session(ev["id"])
    return f"✅ {'Noite' if kind == 'night' else 'Soneca'} das {horario} apagada."


def _editar_horario(repo, child, now: datetime, tipo: str, horario_atual: str, horario_novo: str) -> str:
    dt_atual = _resolve_dt(horario_atual, now)
    dt_novo = _resolve_dt(horario_novo, now)
    open_session = repo.get_open_session(child["id"])

    if tipo == "mamada":
        ev = repo.find_feeding_near(child["id"], dt_atual)
        if not ev:
            return f"Não encontrei mamada próxima de {horario_atual}."
        repo.update_feeding(ev["id"], dt_novo)
        return f"✅ Mamada corrigida: {horario_atual} → {horario_novo}."

    if tipo == "despertar":
        if not open_session:
            return "Não há noite em andamento."
        ev = repo.find_night_waking_near(open_session["id"], dt_atual)
        if not ev:
            return f"Não encontrei despertar próximo de {horario_atual}."
        repo.update_night_waking(ev["id"], dt_novo)
        return f"✅ Despertar corrigido: {horario_atual} → {horario_novo}."

    kind_map = {
        "soneca_inicio": ("nap", "started_at"),
        "soneca_fim": ("nap", "ended_at"),
        "noite_inicio": ("night", "started_at"),
        "noite_fim": ("night", "ended_at"),
    }
    if tipo not in kind_map:
        return "Tipo não reconhecido."
    kind, field = kind_map[tipo]
    ev = repo.find_session_near(child["id"], dt_atual, kind=kind)
    if not ev:
        return f"Não encontrei sessão próxima de {horario_atual}."
    repo.update_session(ev["id"], **{field: dt_novo})
    return f"✅ Horário corrigido: {horario_atual} → {horario_novo}."


def _bedtime(repo, child, config, now, nao_antes) -> str:
    last = repo.get_last_session(child["id"])
    ref = last["ended_at"] if last and last.get("ended_at") else now
    earliest = parse_time(nao_antes) if nao_antes else None
    plan = bedtime_plan(ref, child["birth_date"], config, earliest=earliest)
    return (
        f"Bedtime sugerido: {_hhmm(plan.bedtime)}. "
        f"Iniciar a rotina ~{_hhmm(plan.start_routine)}, banho ~{_hhmm(plan.bath)}."
    )
