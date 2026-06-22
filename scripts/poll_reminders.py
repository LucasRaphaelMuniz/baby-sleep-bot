"""Entrypoint do cron de lembretes.

Rode periodicamente (ex.: a cada 1–2 min) via cron do Railway:

    python -m scripts.poll_reminders

Verifica quem está acordado e dispara lembrete / alerta de overtired.
"""
from __future__ import annotations

import os
import sys

# Garante a raiz do projeto no path mesmo se executado como arquivo.
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from datetime import datetime  # noqa: E402
from zoneinfo import ZoneInfo  # noqa: E402

from dotenv import load_dotenv  # noqa: E402

load_dotenv()

from app.config import load_wake_window_config  # noqa: E402
from app.db import SupabaseRepository  # noqa: E402
from app.notifications.reminders import run_reminder_check  # noqa: E402
from app.notifications.meta_client import send_whatsapp  # noqa: E402


def main() -> None:
    repo = SupabaseRepository()
    config = load_wake_window_config()
    tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))
    now = datetime.now(tz)

    actions = run_reminder_check(repo, config, now, send_whatsapp)
    print(f"[{now.isoformat()}] {len(actions)} aviso(s) enviado(s).", flush=True)


if __name__ == "__main__":
    main()
