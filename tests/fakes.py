"""Repositório falso em memória, compartilhado pelos testes.

Implementa o protocolo `app.repository.Repository` sem banco, para exercitar as
regras de negócio e o orquestrador de forma determinística.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional


class FakeRepository:
    def __init__(self):
        self.sessions: list[dict] = []
        self.feedings: list[dict] = []
        self.caregivers: list[dict] = []
        self.children: list[dict] = []
        self.links: set[tuple[str, str]] = set()
        self.onboarding: dict[str, dict] = {}
        self.wake_windows: list[dict] = []
        self._seq = 0

    def _next_id(self, prefix: str) -> str:
        self._seq += 1
        return f"{prefix}{self._seq}"

    # ── Cuidadores / bebês / onboarding ──────────────────────────────
    def get_caregiver_by_phone(self, phone: str) -> Optional[dict]:
        return next((c for c in self.caregivers if c["phone"] == phone), None)

    def create_caregiver(self, phone: str, name: Optional[str] = None) -> dict:
        c = {"id": self._next_id("cg"), "phone": phone, "name": name}
        self.caregivers.append(c)
        return c

    def create_child(self, name: str, birth_date: date, timezone: str) -> dict:
        ch = {
            "id": self._next_id("ch"), "name": name,
            "birth_date": birth_date, "timezone": timezone,
        }
        self.children.append(ch)
        return ch

    def link_caregiver_child(self, caregiver_id: str, child_id: str) -> None:
        self.links.add((caregiver_id, child_id))

    def get_child_for_caregiver(self, caregiver_id: str) -> Optional[dict]:
        for cg, ch in self.links:
            if cg == caregiver_id:
                return next((c for c in self.children if c["id"] == ch), None)
        return None

    def get_onboarding_state(self, phone: str) -> Optional[dict]:
        return self.onboarding.get(phone)

    def upsert_onboarding_state(self, phone, step, baby_name=None, child_id=None) -> dict:
        st = self.onboarding.get(phone, {})
        st.update({"phone": phone, "step": step})
        if baby_name is not None:
            st["baby_name"] = baby_name
        if child_id is not None:
            st["child_id"] = child_id
        self.onboarding[phone] = st
        return st

    def clear_onboarding_state(self, phone: str) -> None:
        self.onboarding.pop(phone, None)

    # ── Sono ─────────────────────────────────────────────────────────
    def get_open_session(self, child_id: str) -> Optional[dict]:
        for s in self.sessions:
            if s["child_id"] == child_id and s["ended_at"] is None:
                return s
        return None

    def get_last_session(self, child_id: str) -> Optional[dict]:
        rows = [s for s in self.sessions if s["child_id"] == child_id]
        return max(rows, key=lambda s: s["started_at"]) if rows else None

    def get_sessions_since(self, child_id, since) -> list[dict]:
        return sorted(
            [s for s in self.sessions
             if s["child_id"] == child_id and s["started_at"] >= since],
            key=lambda s: s["started_at"],
        )

    def create_session(self, child_id, caregiver_id, kind, started_at,
                        location, difficulty=None) -> dict:
        s = {
            "id": self._next_id("s"), "child_id": child_id,
            "caregiver_id": caregiver_id, "kind": kind,
            "started_at": started_at, "ended_at": None,
            "location": location, "difficulty": difficulty, "_seq": self._seq,
        }
        self.sessions.append(s)
        return s

    def end_session(self, session_id, ended_at) -> dict:
        for s in self.sessions:
            if s["id"] == session_id:
                s["ended_at"] = ended_at
                return s
        raise KeyError(session_id)

    # ── Mamadas ──────────────────────────────────────────────────────
    def create_feeding(self, child_id, caregiver_id, fed_at, kind="breast") -> dict:
        f = {
            "id": self._next_id("f"), "child_id": child_id,
            "caregiver_id": caregiver_id, "fed_at": fed_at, "kind": kind,
            "_seq": self._seq,
        }
        self.feedings.append(f)
        return f

    def get_feedings_since(self, child_id, since) -> list[dict]:
        return sorted(
            [f for f in self.feedings
             if f["child_id"] == child_id and f["fed_at"] >= since],
            key=lambda f: f["fed_at"],
        )

    # ── Desfazer ─────────────────────────────────────────────────────
    def get_last_event(self, child_id: str) -> Optional[dict]:
        cands = []
        for s in self.sessions:
            if s["child_id"] == child_id:
                cands.append({"type": "session", "id": s["id"], "_seq": s["_seq"],
                              "label": f"Soneca {s['started_at'].strftime('%H:%M')}"})
        for f in self.feedings:
            if f["child_id"] == child_id:
                cands.append({"type": "feeding", "id": f["id"], "_seq": f["_seq"],
                              "label": f"Mamada {f['fed_at'].strftime('%H:%M')}"})
        return max(cands, key=lambda c: c["_seq"]) if cands else None

    def delete_event(self, event: dict) -> None:
        if event["type"] == "session":
            self.sessions = [s for s in self.sessions if s["id"] != event["id"]]
        else:
            self.feedings = [f for f in self.feedings if f["id"] != event["id"]]

    # ── Lembretes ────────────────────────────────────────────────────
    def get_all_children(self) -> list[dict]:
        return list(self.children)

    def get_caregivers_for_child(self, child_id: str) -> list[dict]:
        ids = {cg for cg, ch in self.links if ch == child_id}
        return [c for c in self.caregivers if c["id"] in ids]

    def get_wake_window(self, child_id, since_session_id):
        return next(
            (w for w in self.wake_windows
             if w["child_id"] == child_id and w["since_session_id"] == since_session_id),
            None,
        )

    def create_wake_window(self, child_id, since_session_id, window_start, close_ideal, close_max):
        w = {
            "id": self._next_id("ww"), "child_id": child_id,
            "since_session_id": since_session_id, "window_start": window_start,
            "close_ideal": close_ideal, "close_max": close_max,
            "reminder_notified_at": None, "overtired_notified_at": None,
        }
        self.wake_windows.append(w)
        return w

    def mark_wake_window_notified(self, wake_window_id, field, ts):
        for w in self.wake_windows:
            if w["id"] == wake_window_id:
                w[field] = ts
