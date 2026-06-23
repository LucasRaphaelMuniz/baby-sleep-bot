"""Cliente Supabase e implementação do repositório.

`SupabaseRepository` satisfaz o protocolo `app.repository.Repository`. As regras
de negócio (`app.core.events`) não importam este módulo diretamente — recebem o
repositório por injeção, o que mantém a lógica testável sem banco.
"""
from __future__ import annotations

import os
from datetime import date, datetime, timezone
from typing import Optional
from zoneinfo import ZoneInfo


def _app_tz() -> ZoneInfo:
    return ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))


def get_client():
    # Import preguiçoso: importar este módulo não exige o pacote `supabase`
    # (mantém o núcleo/handler testável sem a dependência instalada).
    from supabase import create_client

    url = os.environ["SUPABASE_URL"]
    key = os.environ["SUPABASE_KEY"]
    return create_client(url, key)


def _dt(value) -> Optional[datetime]:
    """Converte timestamptz do Supabase (geralmente em UTC) para um datetime
    aware no fuso configurado — assim a exibição (HH:MM) mostra a hora local."""
    if value is None:
        return None
    if not isinstance(value, datetime):
        value = datetime.fromisoformat(value)
    if value.tzinfo is None:
        value = value.replace(tzinfo=timezone.utc)
    return value.astimezone(_app_tz())


def _row(session: Optional[dict]) -> Optional[dict]:
    """Normaliza datetimes de uma linha de sleep_sessions."""
    if not session:
        return None
    session = dict(session)
    session["started_at"] = _dt(session.get("started_at"))
    session["ended_at"] = _dt(session.get("ended_at"))
    return session


def _child_row(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    row = dict(row)
    if isinstance(row.get("birth_date"), str):
        row["birth_date"] = date.fromisoformat(row["birth_date"])
    return row


def _ww_row(row: Optional[dict]) -> Optional[dict]:
    if not row:
        return None
    row = dict(row)
    for k in ("window_start", "close_ideal", "close_max",
              "reminder_notified_at", "overtired_notified_at"):
        row[k] = _dt(row.get(k))
    return row


class SupabaseRepository:
    def __init__(self, client=None):
        self.db = client or get_client()

    # ── Cuidadores / bebês / onboarding ──────────────────────────────
    def get_caregiver_by_phone(self, phone: str) -> Optional[dict]:
        res = (
            self.db.table("caregivers").select("*").eq("phone", phone)
            .limit(1).execute()
        )
        return res.data[0] if res.data else None

    def create_caregiver(self, phone: str, name: Optional[str] = None) -> dict:
        res = self.db.table("caregivers").insert({"phone": phone, "name": name}).execute()
        return res.data[0]

    def create_child(self, name, birth_date, timezone, pairing_code=None) -> dict:
        res = (
            self.db.table("children")
            .insert({
                "name": name,
                "birth_date": birth_date.isoformat(),
                "timezone": timezone,
                "pairing_code": pairing_code,
            })
            .execute()
        )
        return _child_row(res.data[0])

    def get_child_by_pairing_code(self, code: str) -> Optional[dict]:
        res = (
            self.db.table("children").select("*")
            .eq("pairing_code", code).limit(1).execute()
        )
        return _child_row(res.data[0]) if res.data else None

    def link_caregiver_child(self, caregiver_id: str, child_id: str) -> None:
        self.db.table("caregiver_children").upsert(
            {"caregiver_id": caregiver_id, "child_id": child_id}
        ).execute()

    def get_child_for_caregiver(self, caregiver_id: str) -> Optional[dict]:
        link = (
            self.db.table("caregiver_children").select("child_id")
            .eq("caregiver_id", caregiver_id).limit(1).execute()
        )
        if not link.data:
            return None
        res = (
            self.db.table("children").select("*")
            .eq("id", link.data[0]["child_id"]).limit(1).execute()
        )
        return _child_row(res.data[0]) if res.data else None

    def get_onboarding_state(self, phone: str) -> Optional[dict]:
        res = (
            self.db.table("onboarding_states").select("*").eq("phone", phone)
            .limit(1).execute()
        )
        return res.data[0] if res.data else None

    def upsert_onboarding_state(
        self, phone, step, baby_name=None, child_id=None
    ) -> dict:
        existing = self.get_onboarding_state(phone) or {}
        row = {
            "phone": phone,
            "step": step,
            "baby_name": baby_name if baby_name is not None else existing.get("baby_name"),
            "child_id": child_id if child_id is not None else existing.get("child_id"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self.db.table("onboarding_states").upsert(row).execute()
        return row

    def clear_onboarding_state(self, phone: str) -> None:
        self.db.table("onboarding_states").delete().eq("phone", phone).execute()

    # ── Sono ─────────────────────────────────────────────────────────
    def get_open_session(self, child_id: str) -> Optional[dict]:
        res = (
            self.db.table("sleep_sessions")
            .select("*")
            .eq("child_id", child_id)
            .is_("ended_at", "null")
            .limit(1)
            .execute()
        )
        return _row(res.data[0]) if res.data else None

    def get_last_session(self, child_id: str) -> Optional[dict]:
        res = (
            self.db.table("sleep_sessions")
            .select("*")
            .eq("child_id", child_id)
            .order("started_at", desc=True)
            .limit(1)
            .execute()
        )
        return _row(res.data[0]) if res.data else None

    def get_sessions_since(self, child_id: str, since: datetime) -> list[dict]:
        res = (
            self.db.table("sleep_sessions").select("*")
            .eq("child_id", child_id)
            .gte("started_at", since.isoformat())
            .order("started_at")
            .execute()
        )
        return [_row(s) for s in res.data]

    def create_session(
        self, child_id, caregiver_id, kind, started_at, location, difficulty=None
    ) -> dict:
        res = (
            self.db.table("sleep_sessions")
            .insert(
                {
                    "child_id": child_id,
                    "caregiver_id": caregiver_id,
                    "kind": kind,
                    "started_at": started_at.isoformat(),
                    "location": location,
                    "difficulty": difficulty,
                }
            )
            .execute()
        )
        return _row(res.data[0])

    def end_session(self, session_id, ended_at) -> dict:
        res = (
            self.db.table("sleep_sessions")
            .update({"ended_at": ended_at.isoformat()})
            .eq("id", session_id)
            .execute()
        )
        return _row(res.data[0])

    # ── Mamadas ──────────────────────────────────────────────────────
    def create_feeding(self, child_id, caregiver_id, fed_at, kind="breast") -> dict:
        res = (
            self.db.table("feedings")
            .insert(
                {
                    "child_id": child_id,
                    "caregiver_id": caregiver_id,
                    "fed_at": fed_at.isoformat(),
                    "kind": kind,
                }
            )
            .execute()
        )
        return res.data[0]

    def get_feedings_since(self, child_id: str, since: datetime) -> list[dict]:
        res = (
            self.db.table("feedings")
            .select("*")
            .eq("child_id", child_id)
            .gte("fed_at", since.isoformat())
            .order("fed_at")
            .execute()
        )
        return [{**f, "fed_at": _dt(f["fed_at"])} for f in res.data]

    def create_night_waking(self, session_id: str, woke_at) -> dict:
        res = (
            self.db.table("night_wakings")
            .insert({"sleep_session_id": session_id, "woke_at": woke_at.isoformat(),
                     "reason": "comfort"})
            .execute()
        )
        return res.data[0]

    def get_night_wakings_since(self, session_id: str) -> list[dict]:
        res = (
            self.db.table("night_wakings").select("*")
            .eq("sleep_session_id", session_id).order("woke_at").execute()
        )
        return [{**w, "woke_at": _dt(w["woke_at"])} for w in res.data]

    # ── Desfazer ─────────────────────────────────────────────────────
    def get_last_event(self, child_id: str) -> Optional[dict]:
        sess = (
            self.db.table("sleep_sessions")
            .select("*")
            .eq("child_id", child_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        feed = (
            self.db.table("feedings")
            .select("*")
            .eq("child_id", child_id)
            .order("created_at", desc=True)
            .limit(1)
            .execute()
        )
        candidates = []
        if sess.data:
            s = sess.data[0]
            label_t = "Soninho da noite" if s["kind"] == "night" else "Soneca"
            candidates.append(
                {
                    "type": "session",
                    "id": s["id"],
                    "created_at": _dt(s["created_at"]),
                    "label": f"{label_t} {_dt(s['started_at']).strftime('%H:%M')}",
                }
            )
        if feed.data:
            f = feed.data[0]
            candidates.append(
                {
                    "type": "feeding",
                    "id": f["id"],
                    "created_at": _dt(f["created_at"]),
                    "label": f"Mamada {_dt(f['fed_at']).strftime('%H:%M')}",
                }
            )
        if not candidates:
            return None
        return max(candidates, key=lambda c: c["created_at"])

    def delete_event(self, event: dict) -> None:
        table = "sleep_sessions" if event["type"] == "session" else "feedings"
        self.db.table(table).delete().eq("id", event["id"]).execute()

    # ── Lembretes ────────────────────────────────────────────────────
    def get_all_children(self) -> list[dict]:
        res = self.db.table("children").select("*").execute()
        return [_child_row(r) for r in res.data]

    def get_caregivers_for_child(self, child_id: str) -> list[dict]:
        link = (
            self.db.table("caregiver_children").select("caregiver_id")
            .eq("child_id", child_id).execute()
        )
        ids = [row["caregiver_id"] for row in link.data]
        if not ids:
            return []
        res = self.db.table("caregivers").select("*").in_("id", ids).execute()
        return res.data

    def get_wake_window(self, child_id: str, since_session_id: str) -> Optional[dict]:
        res = (
            self.db.table("wake_windows").select("*")
            .eq("child_id", child_id).eq("since_session_id", since_session_id)
            .limit(1).execute()
        )
        return _ww_row(res.data[0]) if res.data else None

    def create_wake_window(
        self, child_id, since_session_id, window_start, close_ideal, close_max
    ) -> dict:
        res = (
            self.db.table("wake_windows")
            .insert({
                "child_id": child_id,
                "since_session_id": since_session_id,
                "window_start": window_start.isoformat(),
                "close_ideal": close_ideal.isoformat(),
                "close_max": close_max.isoformat(),
            })
            .execute()
        )
        return _ww_row(res.data[0])

    def mark_wake_window_notified(self, wake_window_id, field, ts) -> None:
        self.db.table("wake_windows").update(
            {field: ts.isoformat()}
        ).eq("id", wake_window_id).execute()
