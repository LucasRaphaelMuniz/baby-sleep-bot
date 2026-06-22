"""Cálculo de janela de vigília e bedtime.

Funções puras: recebem datas/horas e a configuração, devolvem números e
datetimes. Não acessam banco nem relógio global — o "agora" é sempre passado
pelo chamador, o que torna o módulo determinístico e testável.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, time, timedelta
from typing import Tuple


@dataclass(frozen=True)
class WakeWindowConfig:
    # Faixas (up_to_weeks, ideal_min, max_min), ordenadas por up_to_weeks asc.
    bands: Tuple[Tuple[int, int, int], ...]
    bedtime_window: Tuple[time, time]
    reminder_lead_minutes: int
    quiet_hours: Tuple[time, time]
    routine_start_offset: int = 60   # min antes do bedtime p/ iniciar a rotina
    routine_bath_offset: int = 30    # min antes do bedtime p/ o banho


@dataclass(frozen=True)
class WakeWindow:
    woke_at: datetime
    ideal_minutes: int
    max_minutes: int
    close_ideal: datetime    # alvo para o bebê já estar dormindo
    close_max: datetime      # limite antes da zona de overtired
    reminder_at: datetime    # disparo do lembrete (estágio 1)


def age_in_weeks(birth_date: date, ref_date: date) -> int:
    """Idade em semanas completas na data de referência (nunca negativa)."""
    return max(0, (ref_date - birth_date).days // 7)


def window_minutes_for_age(weeks: int, config: WakeWindowConfig) -> Tuple[int, int]:
    """Retorna (ideal_min, max_min) para a idade, segundo as faixas do config."""
    for up_to, ideal, mx in config.bands:
        if weeks <= up_to:
            return ideal, mx
    _, ideal, mx = config.bands[-1]   # fallback: última faixa
    return ideal, mx


def compute_window(
    woke_at: datetime, birth_date: date, config: WakeWindowConfig
) -> WakeWindow:
    """Calcula a janela de vigília a partir do horário em que o bebê acordou."""
    weeks = age_in_weeks(birth_date, woke_at.date())
    ideal_min, max_min = window_minutes_for_age(weeks, config)
    close_ideal = woke_at + timedelta(minutes=ideal_min)
    close_max = woke_at + timedelta(minutes=max_min)
    reminder_at = close_ideal - timedelta(minutes=config.reminder_lead_minutes)
    return WakeWindow(
        woke_at=woke_at,
        ideal_minutes=ideal_min,
        max_minutes=max_min,
        close_ideal=close_ideal,
        close_max=close_max,
        reminder_at=reminder_at,
    )


def minutes_awake(now: datetime, woke_at: datetime) -> int:
    """Minutos de vigília acumulados até `now`."""
    return int((now - woke_at).total_seconds() // 60)


def is_overtired(now: datetime, window: WakeWindow) -> bool:
    """True se já passou do máximo da janela (risco de overtired)."""
    return now >= window.close_max


def suggest_bedtime(
    last_wake_at: datetime, birth_date: date, config: WakeWindowConfig
) -> datetime:
    """Sugere o bedtime: fechamento ideal da última janela, limitado à
    bedtime_window configurada."""
    target = compute_window(last_wake_at, birth_date, config).close_ideal
    day = last_wake_at.date()
    lo = datetime.combine(day, config.bedtime_window[0], tzinfo=last_wake_at.tzinfo)
    hi = datetime.combine(day, config.bedtime_window[1], tzinfo=last_wake_at.tzinfo)
    if target < lo:
        return lo
    if target > hi:
        return hi
    return target


@dataclass(frozen=True)
class BedtimePlan:
    bedtime: datetime
    start_routine: datetime   # quando começar o ritual de soninho
    bath: datetime            # quando dar o banho


def bedtime_plan(
    last_wake_at: datetime,
    birth_date: date,
    config: WakeWindowConfig,
    earliest: time | None = None,
) -> BedtimePlan:
    """Plano de bedtime com a rotina (início do ritual e banho). `earliest`
    força um horário mínimo (ex.: 'só consigo após 20h') — sobrepõe o ideal."""
    bt = suggest_bedtime(last_wake_at, birth_date, config)
    if earliest is not None:
        forced = datetime.combine(bt.date(), earliest, tzinfo=bt.tzinfo)
        if forced > bt:
            bt = forced
    return BedtimePlan(
        bedtime=bt,
        start_routine=bt - timedelta(minutes=config.routine_start_offset),
        bath=bt - timedelta(minutes=config.routine_bath_offset),
    )
