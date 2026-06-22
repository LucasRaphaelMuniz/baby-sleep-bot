"""Resumo de sono ao longo de vários dias (para a IA analisar padrões).

Função pura: recebe as sessões/mamadas já carregadas e devolve um texto compacto,
um dia por linha, que a IA reescreve em linguagem natural ("as sonecas estão
alongando", "o bedtime está mais cedo", etc.).
"""
from __future__ import annotations

from datetime import datetime, timedelta


def _dur(minutes: int) -> str:
    h, m = divmod(max(0, minutes), 60)
    if h and m:
        return f"{h}h{m:02d}"
    return f"{h}h" if h else f"{m}min"


def summarize_days(
    sessions: list[dict],
    feedings: list[dict],
    now: datetime,
    days: int,
) -> str:
    """Resume os últimos `days` dias (incluindo hoje), um por linha."""
    day_list = [(now.date() - timedelta(days=i)) for i in range(days - 1, -1, -1)]
    lines = []
    for d in day_list:
        day_sessions = [s for s in sessions if s["started_at"].date() == d]
        naps = [s for s in day_sessions if s["kind"] == "nap" and s.get("ended_at")]
        nights = [s for s in day_sessions if s["kind"] == "night"]
        feeds = [f for f in feedings if f["fed_at"].date() == d]

        total_nap = sum(
            int((s["ended_at"] - s["started_at"]).total_seconds() // 60) for s in naps
        )
        parts = [f"{len(naps)} soneca(s) ({_dur(total_nap)})"]
        if nights:
            parts.append(f"noite iniciada {nights[0]['started_at'].strftime('%H:%M')}")
        parts.append(f"{len(feeds)} mamada(s)")
        lines.append(f"{d.strftime('%d/%m (%a)')}: " + ", ".join(parts))

    return "\n".join(lines) if lines else "Sem dados no período."
