"""Agente de IA (LiteLLM) com tool use.

Monta o contexto com os dados reais do bebê, roda o laço de tool use e devolve a
resposta final em texto para enviar no WhatsApp. O provedor é definido por
`LLM_MODEL` (LiteLLM) — default Claude Sonnet 4.6, trocável por `.env`.
"""
from __future__ import annotations

import json
import os
import re
from datetime import datetime, time

from app.ai.tools import TOOL_SCHEMAS, execute_tool
from app.core.events import fmt_duration
from app.core.wake_window import (
    WakeWindowConfig,
    age_in_weeks,
    minutes_awake,
    window_minutes_for_age,
)
from app.repository import Repository

DEFAULT_MODEL = "anthropic/claude-sonnet-4-6"

SYSTEM_PROMPT = """Você é uma consultora de sono infantil experiente e acolhedora, \
conversando pelo WhatsApp com os pais de {name}. Escreva em português do Brasil \
de forma natural e calorosa — como uma amiga que entende muito de sono de bebê, \
não como um manual técnico. Use emojis com naturalidade quando fizer sentido.

O que você faz bem:
- Valida o que os pais estão sentindo antes de dar a dica prática.
- Traduz conceitos (janela de vigília, overtired, catnap, bedtime, regressão dos \
4 meses) em orientações concretas para o momento, usando os horários do contexto.
- Sugere ações específicas quando faz sentido: ambiente calmo, menos estímulo, \
colo, movimento, ruído branco.
- Se a pessoa relatar um evento ("dormiu", "mamou", "acordou 14h"), registra com \
as ferramentas e confirma de forma natural na conversa.

Limites:
- Use apenas dados do contexto abaixo. Não invente horários nem afirme eventos \
que não estejam registrados.
- Não faça diagnóstico médico. Nunca sugira práticas de sono inseguras.

— Contexto atual —
{context}"""


def _build_context(repo: Repository, child: dict, config: WakeWindowConfig, now: datetime) -> str:
    weeks = age_in_weeks(child["birth_date"], now.date())
    ideal_min, max_min = window_minutes_for_age(weeks, config)
    day_start = datetime.combine(now.date(), time(0, 0), tzinfo=now.tzinfo)

    sessions = repo.get_sessions_since(child["id"], day_start)
    feedings = repo.get_feedings_since(child["id"], day_start)
    naps = [s for s in sessions if s["kind"] == "nap"]
    total_nap = sum(
        minutes_awake(s["ended_at"], s["started_at"])
        for s in naps if s.get("ended_at")
    )

    lines = [
        f"Bebê: {child['name']}, {weeks} semanas de vida.",
        f"Janela de vigília ideal p/ a idade: {ideal_min}–{max_min} min.",
    ]

    open_session = repo.get_open_session(child["id"])
    if open_session:
        dur = fmt_duration(minutes_awake(now, open_session["started_at"]))
        tipo = "sono noturno" if open_session["kind"] == "night" else "soneca"
        lines.append(
            f"Agora: DORMINDO ({tipo}) desde "
            f"{open_session['started_at'].strftime('%H:%M')} (há {dur})."
        )
    else:
        last = repo.get_last_session(child["id"])
        if last and last.get("ended_at"):
            dur = fmt_duration(minutes_awake(now, last["ended_at"]))
            lines.append(
                f"Agora: ACORDADA desde {last['ended_at'].strftime('%H:%M')} (há {dur})."
            )
        else:
            lines.append("Agora: sem registro de sono ainda hoje.")

    lines.append(
        f"Hoje: {len(naps)} soneca(s), total {fmt_duration(total_nap)} de soneca; "
        f"{len(feedings)} mamada(s)."
    )
    lines.append(f"Hora atual: {now.strftime('%H:%M')}.")
    return "\n".join(lines)


# Alguns modelos (ex.: Llama no Groq) "falam" a chamada de ferramenta como texto
# em vez de usar o tool_calls estruturado. Removemos esses resíduos da resposta.
_TOOL_TAG_RE = re.compile(r"<function=.*?>.*?</function>|</?function[^>]*>", re.DOTALL)


def _clean_content(text) -> str:
    return _TOOL_TAG_RE.sub("", text or "").strip()


def _assistant_msg(msg) -> dict:
    """Converte a mensagem do modelo em dict reutilizável na próxima rodada."""
    out: dict = {"role": "assistant", "content": msg.content or ""}
    if getattr(msg, "tool_calls", None):
        out["tool_calls"] = [
            {
                "id": tc.id,
                "type": "function",
                "function": {"name": tc.function.name, "arguments": tc.function.arguments},
            }
            for tc in msg.tool_calls
        ]
    return out


def run_agent(
    repo: Repository,
    child: dict,
    caregiver_id,
    config: WakeWindowConfig,
    user_text: str,
    now: datetime,
    completion=None,
    max_rounds: int = 5,
) -> str:
    """Roda o agente e devolve a resposta em texto. `completion` é injetável
    para testes; em produção usa `litellm.completion`."""
    if completion is None:
        import litellm

        completion = litellm.completion

    context = _build_context(repo, child, config, now)
    messages = [
        {"role": "system", "content": SYSTEM_PROMPT.format(name=child["name"], context=context)},
        {"role": "user", "content": user_text},
    ]
    model = os.getenv("LLM_MODEL", DEFAULT_MODEL)

    for _ in range(max_rounds):
        resp = completion(model=model, messages=messages, tools=TOOL_SCHEMAS, temperature=0.3)
        msg = resp.choices[0].message
        messages.append(_assistant_msg(msg))

        tool_calls = getattr(msg, "tool_calls", None)
        if not tool_calls:
            return _clean_content(msg.content) or "Não entendi, pode repetir? 🙂"

        for tc in tool_calls:
            args = json.loads(tc.function.arguments or "{}")
            result = execute_tool(repo, child, caregiver_id, config, now, tc.function.name, args)
            messages.append({"role": "tool", "tool_call_id": tc.id, "content": result})

    return "Desculpa, não consegui concluir agora. Tente um comando direto (1–5)."
