"""Contrato de acesso a dados.

A camada de regras (`events.py`) depende apenas deste protocolo, não do
Supabase diretamente. Assim conseguimos testar as regras com um repositório
falso em memória e plugar o Supabase em produção (`db.SupabaseRepository`).

Convenção: sessões/mamadas trafegam como `dict` com datetimes já convertidos
para `datetime` *timezone-aware*.
"""
from __future__ import annotations

from datetime import date, datetime
from typing import Optional, Protocol


class Repository(Protocol):
    # ── Cuidadores / bebês / onboarding ──────────────────────────────
    def get_caregiver_by_phone(self, phone: str) -> Optional[dict]:
        ...

    def create_caregiver(self, phone: str, name: Optional[str] = None) -> dict:
        ...

    def create_child(
        self, name: str, birth_date: date, timezone: str,
        pairing_code: Optional[str] = None,
    ) -> dict:
        ...

    def link_caregiver_child(self, caregiver_id: str, child_id: str) -> None:
        ...

    def get_child_for_caregiver(self, caregiver_id: str) -> Optional[dict]:
        """Bebê associado ao cuidador (uso doméstico: um bebê por cuidador)."""

    def get_child_by_pairing_code(self, code: str) -> Optional[dict]:
        """Bebê cujo código de pareamento bate com `code`, ou None."""

    def get_onboarding_state(self, phone: str) -> Optional[dict]:
        ...

    def upsert_onboarding_state(
        self,
        phone: str,
        step: str,
        baby_name: Optional[str] = None,
        child_id: Optional[str] = None,
    ) -> dict:
        ...

    def clear_onboarding_state(self, phone: str) -> None:
        ...

    # ── Sono ─────────────────────────────────────────────────────────
    def get_open_session(self, child_id: str) -> Optional[dict]:
        """Sono em andamento (ended_at IS NULL) do bebê, ou None."""

    def get_last_session(self, child_id: str) -> Optional[dict]:
        """Sessão de sono mais recente (por started_at), ou None."""

    def get_sessions_since(self, child_id: str, since: datetime) -> list[dict]:
        """Sessões de sono iniciadas a partir de `since`, em ordem cronológica."""

    def create_session(
        self,
        child_id: str,
        caregiver_id: Optional[str],
        kind: str,
        started_at: datetime,
        location: Optional[str],
        difficulty: Optional[str] = None,
    ) -> dict:
        ...

    def end_session(self, session_id: str, ended_at: datetime) -> dict:
        ...

    # ── Mamadas ──────────────────────────────────────────────────────
    def create_feeding(
        self,
        child_id: str,
        caregiver_id: Optional[str],
        fed_at: datetime,
        kind: str = "breast",
    ) -> dict:
        ...

    def get_feedings_since(self, child_id: str, since: datetime) -> list[dict]:
        """Mamadas do bebê a partir de `since` (inclusive), em ordem
        cronológica. Usado para contar despertares da noite."""

    # ── Desfazer ─────────────────────────────────────────────────────
    def get_last_event(self, child_id: str) -> Optional[dict]:
        """Último evento criado (sono ou mamada). Retorna dict com ao menos
        as chaves `type` ('session'|'feeding'), `id` e `label`."""

    def delete_event(self, event: dict) -> None:
        """Remove o evento descrito por `get_last_event`."""

    # ── Lembretes (polling) ──────────────────────────────────────────
    def get_all_children(self) -> list[dict]:
        ...

    def get_caregivers_for_child(self, child_id: str) -> list[dict]:
        ...

    def get_wake_window(self, child_id: str, since_session_id: str) -> Optional[dict]:
        """Linha de cache da janela de vigília aberta por aquela sessão, ou None."""

    def create_wake_window(
        self,
        child_id: str,
        since_session_id: str,
        window_start: datetime,
        close_ideal: datetime,
        close_max: datetime,
    ) -> dict:
        ...

    def mark_wake_window_notified(
        self, wake_window_id: str, field: str, ts: datetime
    ) -> None:
        """Marca `reminder_notified_at` ou `overtired_notified_at` (idempotência)."""
