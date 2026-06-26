"""Regras de negócio do registro de eventos.

Recebe um comando já interpretado (`parser.ParsedCommand`), o estado do bebê e
um repositório, aplica as regras (rejeitar hora futura, "já está dormindo",
"não há sono em andamento", desfazer) e devolve um `EventResult` com o texto a
responder no WhatsApp. Não conhece Supabase nem o provedor de mensagens.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, time
from typing import Optional

from app.core.parser import CommandType, ParsedCommand
from app.core.wake_window import (
    WakeWindowConfig,
    bedtime_plan,
    compute_window,
    is_overtired,
    minutes_awake,
)
from app.repository import Repository

# Rótulos pt-BR para exibição.
_LOCATION_PT = {
    "crib": "berço", "arms": "colo", "stroller": "carrinho",
    "car": "carro", "breast": "peito",
}
_DIFFICULTY_PT = {
    "easy": "fácil", "hard": "deu trabalho",
    "only_held": "só no colo", "only_motion": "só em movimento",
}


@dataclass
class EventResult:
    ok: bool
    message: str                       # texto para responder no WhatsApp
    to_ai: bool = False                # True = rotear para a IA (passo 4)
    session_id: Optional[str] = None


# ── helpers ──────────────────────────────────────────────────────────
def _hhmm(dt: datetime) -> str:
    return dt.strftime("%H:%M")


def fmt_duration(total_minutes: int) -> str:
    total_minutes = max(0, total_minutes)
    h, m = divmod(total_minutes, 60)
    if h and m:
        return f"{h}h{m:02d}"
    if h:
        return f"{h}h"
    return f"{m}min"


def resolve_event_time(at: Optional[time], now: datetime) -> datetime:
    """Combina o horário informado (HH:MM) com a data de `now`. Se `at` for
    None, usa o próprio `now`. Mantém o fuso de `now`."""
    if at is None:
        return now
    return datetime.combine(now.date(), at, tzinfo=now.tzinfo)


# ── dispatcher ───────────────────────────────────────────────────────
def handle_command(
    repo: Repository,
    child: dict,                       # {id, name, birth_date, ...}
    caregiver_id: Optional[str],
    cmd: ParsedCommand,
    now: datetime,
    config: WakeWindowConfig,
) -> EventResult:
    if cmd.type is CommandType.ERROR:
        return EventResult(ok=False, message=cmd.error_message or "Comando inválido.")
    if cmd.type is CommandType.NATURAL_LANGUAGE:
        return EventResult(ok=True, message="", to_ai=True)
    if cmd.type is CommandType.SLEEP_START:
        return _start_sleep(repo, child, caregiver_id, cmd, now, kind="nap")
    if cmd.type is CommandType.NIGHT:
        return _start_sleep(repo, child, caregiver_id, cmd, now, kind="night")
    if cmd.type is CommandType.WAKE:
        return _wake(repo, child, cmd, now, config)
    if cmd.type is CommandType.FEED:
        return _feed(repo, child, caregiver_id, cmd, now)
    if cmd.type is CommandType.NIGHT_WAKING:
        return _night_waking(repo, child, caregiver_id, cmd, now)
    if cmd.type is CommandType.STATUS:
        return _status(repo, child, now, config)
    if cmd.type is CommandType.UNDO:
        return _undo(repo, child)
    if cmd.type is CommandType.HELP:
        from config.messages import COMMANDS_HELP
        return EventResult(ok=True, message=COMMANDS_HELP)
    return EventResult(ok=False, message="Comando não reconhecido.")


# ── handlers ─────────────────────────────────────────────────────────
def _start_sleep(repo, child, caregiver_id, cmd, now, kind) -> EventResult:
    ev = resolve_event_time(cmd.at, now)
    if ev > now:
        return EventResult(
            ok=False,
            message=f"⏳ {_hhmm(ev)} é no futuro. Confere o horário?",
        )
    open_session = repo.get_open_session(child["id"])
    if open_session:
        return EventResult(
            ok=False,
            message=(
                f"{child['name']} já está dormindo desde "
                f"{_hhmm(open_session['started_at'])}. Mande `2` para acordar."
            ),
        )
    session = repo.create_session(
        child_id=child["id"],
        caregiver_id=caregiver_id,
        kind=kind,
        started_at=ev,
        location=cmd.location,
        difficulty=cmd.difficulty,
    )
    label = (
        "🌙 Soninho da noite iniciado" if kind == "night" else "😴 Soneca iniciada"
    )
    tags = [_LOCATION_PT.get(cmd.location), _DIFFICULTY_PT.get(cmd.difficulty)]
    tags = [t for t in tags if t]
    extra = f" ({', '.join(tags)})" if tags else ""
    return EventResult(
        ok=True,
        message=f"{label} às {_hhmm(ev)}{extra}.",
        session_id=session["id"],
    )


def _wake(repo, child, cmd, now, config) -> EventResult:
    open_session = repo.get_open_session(child["id"])
    if not open_session:
        return EventResult(
            ok=False,
            message="Não há sono em andamento. Quis registrar mamada (`3`)?",
        )
    ev = resolve_event_time(cmd.at, now)
    if ev > now:
        return EventResult(ok=False, message=f"⏳ {_hhmm(ev)} é no futuro. Confere o horário?")
    if ev < open_session["started_at"]:
        return EventResult(
            ok=False,
            message=(
                f"Horário antes do início do sono "
                f"({_hhmm(open_session['started_at'])}). Confere?"
            ),
        )
    repo.end_session(open_session["id"], ev)

    # Encerrar um sono noturno = "bom dia": começa o dia e a 1ª janela.
    if open_session["kind"] == "night":
        return _morning_wake(repo, child, open_session, ev, config)

    slept = fmt_duration(minutes_awake(ev, open_session["started_at"]))
    win = compute_window(ev, child["birth_date"], config)
    plan = bedtime_plan(ev, child["birth_date"], config)
    return EventResult(
        ok=True,
        message=(
            f"⏰ Acordou às {_hhmm(ev)} (dormiu {slept}).\n"
            f"🎯 Próximo sono ideal ~{_hhmm(win.close_ideal)} "
            f"(limite {_hhmm(win.close_max)}).\n"
            f"🔔 Lembrete às {_hhmm(win.reminder_at)}.\n"
            f"🌙 Bedtime sugerido ~{_hhmm(plan.bedtime)} "
            f"(rotina {_hhmm(plan.start_routine)}, banho {_hhmm(plan.bath)})."
        ),
    )


def _morning_wake(repo, child, night_session, ev, config) -> EventResult:
    night_dur = fmt_duration(minutes_awake(ev, night_session["started_at"]))
    since = night_session["started_at"]
    feeds = len(repo.get_feedings_since(child["id"], since))
    wakings_no_feed = len(repo.get_night_wakings_since(night_session["id"]))
    total_wakings = feeds + wakings_no_feed
    parts = []
    if feeds:
        parts.append(f"{feeds} c/ mamada")
    if wakings_no_feed:
        parts.append(f"{wakings_no_feed} s/ mamada")
    waking_detail = f" ({', '.join(parts)})" if parts else ""
    win = compute_window(ev, child["birth_date"], config)
    return EventResult(
        ok=True,
        message=(
            f"☀️ Bom dia! Acordou às {_hhmm(ev)}.\n"
            f"🌙 Noite: {night_dur}, {total_wakings} despertar(es){waking_detail}.\n"
            f"🎯 Próximo sono ideal ~{_hhmm(win.close_ideal)} "
            f"(limite {_hhmm(win.close_max)}).\n"
            f"🔔 Lembrete às {_hhmm(win.reminder_at)}."
        ),
    )


def _night_waking(repo, child, caregiver_id, cmd, now) -> EventResult:
    open_session = repo.get_open_session(child["id"])
    if not open_session or open_session["kind"] != "night":
        return EventResult(
            ok=False,
            message="Só registra despertar durante o sono da noite. Mande `5` para iniciar a noite.",
        )
    ev = resolve_event_time(cmd.at, now)
    if ev > now:
        return EventResult(ok=False, message=f"⏳ {_hhmm(ev)} é no futuro. Confere o horário?")
    repo.create_night_waking(open_session["id"], ev)
    n = len(repo.get_night_wakings_since(open_session["id"]))
    return EventResult(
        ok=True,
        message=f"🌙 Despertar às {_hhmm(ev)} ({n}º, sem mamar). Voltou a dormir 😴",
    )


def _feed(repo, child, caregiver_id, cmd, now) -> EventResult:
    ev = resolve_event_time(cmd.at, now)
    if ev > now:
        return EventResult(ok=False, message=f"⏳ {_hhmm(ev)} é no futuro. Confere o horário?")
    open_session = repo.get_open_session(child["id"])
    repo.create_feeding(child["id"], caregiver_id, ev)

    # Mamada durante o sono noturno = despertar da noite (sem avisos).
    if open_session and open_session["kind"] == "night":
        n = len(repo.get_feedings_since(child["id"], open_session["started_at"]))
        return EventResult(
            ok=True,
            message=f"🌙 Mamada da noite às {_hhmm(ev)} ({n}º despertar). Bom descanso 😴",
        )
    return EventResult(ok=True, message=f"🍼 Mamada registrada às {_hhmm(ev)}.")


def _status(repo, child, now, config) -> EventResult:
    open_session = repo.get_open_session(child["id"])
    if open_session:
        dur = fmt_duration(minutes_awake(now, open_session["started_at"]))
        if open_session["kind"] == "night":
            feeds = repo.get_feedings_since(child["id"], open_session["started_at"])
            wakings = repo.get_night_wakings_since(open_session["id"])
            total = len(feeds) + len(wakings)
            line = f"{total} despertar(es)"
            events = (
                [(_hhmm(f["fed_at"]), "🍼") for f in feeds]
                + [(_hhmm(w["woke_at"]), "💤") for w in wakings]
            )
            if events:
                events.sort()
                detail = "\n".join(f"{t}{e}" for t, e in events)
                line += f":\n{detail}"
            return EventResult(
                ok=True,
                message=(
                    f"🌙 {child['name']} na noite desde "
                    f"{_hhmm(open_session['started_at'])} (há {dur}).\n{line}."
                ),
            )
        return EventResult(
            ok=True,
            message=(
                f"😴 {child['name']} está na soneca desde "
                f"{_hhmm(open_session['started_at'])} (há {dur})."
            ),
        )

    last = repo.get_last_session(child["id"])
    if not last or not last.get("ended_at"):
        return EventResult(
            ok=True,
            message=f"Nenhum registro de sono ainda. Mande `1` quando {child['name']} dormir.",
        )

    ended = last["ended_at"]
    win = compute_window(ended, child["birth_date"], config)
    awake = fmt_duration(minutes_awake(now, ended))
    base = (
        f"🌤 {child['name']} acordada desde {_hhmm(ended)} (há {awake}).\n"
        f"🎯 Próximo sono ideal ~{_hhmm(win.close_ideal)}."
    )
    if is_overtired(now, win):
        base += f"\n⚠️ Passou do limite ({_hhmm(win.close_max)}) — risco de overtired."
    plan = bedtime_plan(ended, child["birth_date"], config)
    base += (
        f"\n🌙 Bedtime sugerido ~{_hhmm(plan.bedtime)} "
        f"(rotina {_hhmm(plan.start_routine)}, banho {_hhmm(plan.bath)})."
    )
    return EventResult(ok=True, message=base)


def _undo(repo, child) -> EventResult:
    last = repo.get_last_event(child["id"])
    if not last:
        return EventResult(ok=False, message="Nada para desfazer.")
    repo.delete_event(last)
    return EventResult(ok=True, message=f"↩️ Desfeito: {last['label']}.")
