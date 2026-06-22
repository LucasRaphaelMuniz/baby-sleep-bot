"""Verificação periódica de lembretes (polling, 2 estágios).

Projetado para rodar via cron (ex.: a cada 1–2 min no Railway). Não agenda nada
em memória — o estado vive no Postgres (`wake_windows`), então sobrevive a
redeploy e é idempotente. Cancela sozinho: se o bebê dorme, deixa de estar
"acordado" e nada dispara.

Estágios:
  1. Lembrete  — em `T - reminder_lead` antes do fechamento ideal da janela.
  2. Overtired — quando passa do máximo e o bebê continua acordado.

Regras de silêncio: nada dispara se há sono em andamento ou se estamos dentro
de `quiet_hours`.
"""
from __future__ import annotations

from datetime import datetime, time
from typing import Callable

from config import messages as M
from app.core.events import fmt_duration
from app.core.wake_window import WakeWindowConfig, compute_window, minutes_awake
from app.repository import Repository

# notifier(phone, text) -> None
Notifier = Callable[[str, str], None]


def in_quiet_hours(now_t: time, quiet: tuple[time, time]) -> bool:
    start, end = quiet
    if start <= end:
        return start <= now_t < end
    return now_t >= start or now_t < end   # janela que atravessa a meia-noite


def run_reminder_check(
    repo: Repository,
    config: WakeWindowConfig,
    now: datetime,
    notifier: Notifier,
) -> list[dict]:
    """Verifica todas as crianças e dispara os avisos devidos. Retorna a lista
    de ações executadas (útil para log e testes)."""
    actions: list[dict] = []

    if in_quiet_hours(now.timetz().replace(tzinfo=None), config.quiet_hours):
        return actions

    for child in repo.get_all_children():
        if repo.get_open_session(child["id"]):
            continue  # dormindo: sem janela, sem aviso

        last = repo.get_last_session(child["id"])
        if not last or not last.get("ended_at"):
            continue  # nunca dormiu ainda

        win = compute_window(last["ended_at"], child["birth_date"], config)
        ww = repo.get_wake_window(child["id"], last["id"]) or repo.create_wake_window(
            child["id"], last["id"], win.woke_at, win.close_ideal, win.close_max
        )
        phones = [c["phone"] for c in repo.get_caregivers_for_child(child["id"])]
        if not phones:
            continue

        if now >= win.close_max:
            if not ww.get("overtired_notified_at"):
                text = M.overtired_alert(child["name"], win.close_max.strftime("%H:%M"))
                for p in phones:
                    notifier(p, text)
                repo.mark_wake_window_notified(ww["id"], "overtired_notified_at", now)
                actions.append({"child": child["id"], "stage": "overtired", "phones": phones})
        elif now >= win.reminder_at:
            if not ww.get("reminder_notified_at"):
                awake = fmt_duration(minutes_awake(now, win.woke_at))
                text = M.window_reminder(child["name"], awake, win.close_ideal.strftime("%H:%M"))
                for p in phones:
                    notifier(p, text)
                repo.mark_wake_window_notified(ww["id"], "reminder_notified_at", now)
                actions.append({"child": child["id"], "stage": "reminder", "phones": phones})

    return actions
