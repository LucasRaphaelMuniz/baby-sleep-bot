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


def _bedtime(repo, child, config, now, nao_antes) -> str:
    last = repo.get_last_session(child["id"])
    ref = last["ended_at"] if last and last.get("ended_at") else now
    earliest = parse_time(nao_antes) if nao_antes else None
    plan = bedtime_plan(ref, child["birth_date"], config, earliest=earliest)
    return (
        f"Bedtime sugerido: {_hhmm(plan.bedtime)}. "
        f"Iniciar a rotina ~{_hhmm(plan.start_routine)}, banho ~{_hhmm(plan.bath)}."
    )
