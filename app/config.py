"""Carregamento de configuração a partir de YAML + variáveis de ambiente."""
from __future__ import annotations

import os
from datetime import time
from pathlib import Path

import yaml

from app.core.wake_window import WakeWindowConfig


def _parse_hhmm(value: str) -> time:
    hh, mm = value.split(":")
    return time(int(hh), int(mm))


def load_wake_window_config(path: str | None = None) -> WakeWindowConfig:
    """Lê `config/wake_windows.yaml` (ou o caminho informado) e devolve a
    configuração tipada usada pelos cálculos de janela."""
    path = path or os.getenv("WAKE_WINDOWS_PATH", "config/wake_windows.yaml")
    data = yaml.safe_load(Path(path).read_text(encoding="utf-8"))

    bands = tuple(
        (int(b["up_to_weeks"]), int(b["ideal"]), int(b["max"]))
        for b in data["wake_windows"]
    )
    bt = data["bedtime_window"]
    qh = data["quiet_hours"]
    routine = data.get("bedtime_routine", {})
    return WakeWindowConfig(
        bands=bands,
        bedtime_window=(_parse_hhmm(bt[0]), _parse_hhmm(bt[1])),
        reminder_lead_minutes=int(data["reminder_lead_minutes"]),
        quiet_hours=(_parse_hhmm(qh[0]), _parse_hhmm(qh[1])),
        routine_start_offset=int(routine.get("start_offset_min", 60)),
        routine_bath_offset=int(routine.get("bath_offset_min", 30)),
    )
