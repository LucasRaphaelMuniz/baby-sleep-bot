"""Orquestrador de mensagens.

Ponto único de entrada da lógica: recebe (telefone, texto) e decide entre
conduzir o *onboarding* (primeiro uso / cadastro) ou processar um comando de
registro. Não conhece Flask nem o provedor de WhatsApp — recebe um repositório por injeção, o
que mantém todo o fluxo testável sem rede.
"""
from __future__ import annotations

import os
import re
from datetime import date, datetime
from typing import Optional

from config import messages as M
from app.core.events import handle_command
from app.core.parser import parse
from app.core.wake_window import WakeWindowConfig
from app.repository import Repository

_DATE_RE = re.compile(r"^\s*(\d{1,2})[/\-.](\d{1,2})[/\-.](\d{2,4})\s*$")
_NEGATIVE = {"não", "nao", "n", "no", "pular", "skip", "-"}


def normalize_phone(raw: str) -> str:
    """Converte 'whatsapp:+55 11 99999-9999' em '+5511999999999'."""
    raw = (raw or "").strip().replace("whatsapp:", "")
    digits = re.sub(r"\D", "", raw)
    return "+" + digits if digits else ""


def _valid_phone(phone: str) -> bool:
    return phone.startswith("+") and len(re.sub(r"\D", "", phone)) >= 10


def parse_birth_date(text: str) -> Optional[date]:
    m = _DATE_RE.match(text or "")
    if not m:
        return None
    d, mo, y = int(m.group(1)), int(m.group(2)), int(m.group(3))
    if y < 100:
        y += 2000
    try:
        return date(y, mo, d)
    except ValueError:
        return None


def process_message(
    repo: Repository,
    config: WakeWindowConfig,
    phone: str,
    body: str,
    now: datetime,
) -> str:
    """Processa uma mensagem recebida e devolve o texto da resposta."""
    phone = normalize_phone(phone)
    state = repo.get_onboarding_state(phone)
    caregiver = repo.get_caregiver_by_phone(phone)

    # Em onboarding (ou número desconhecido) -> fluxo de cadastro.
    if state is not None or caregiver is None:
        return _onboard(repo, phone, body, state, now)

    child = repo.get_child_for_caregiver(caregiver["id"])
    if child is None:
        # Cuidador sem bebê vinculado (estado inesperado): recomeça o cadastro.
        return _onboard(repo, phone, body, None, now)

    cmd = parse(body)
    result = handle_command(repo, child, caregiver["id"], cmd, now, config)
    if result.to_ai:
        # Texto livre: delega para a IA (responde dúvidas / registra por linguagem natural).
        from app.ai.agent import run_agent

        return run_agent(repo, child, caregiver["id"], config, cmd.raw, now)
    return result.message


def _onboard(repo, phone, body, state, now) -> str:
    text = (body or "").strip()

    if state is None:
        repo.upsert_onboarding_state(phone, step="awaiting_name")
        return M.WELCOME_ASK_NAME

    step = state["step"]

    if step == "awaiting_name":
        name = text[:50] or "bebê"
        repo.upsert_onboarding_state(phone, step="awaiting_birth", baby_name=name)
        return M.ask_birth(name)

    if step == "awaiting_birth":
        birth = parse_birth_date(text)
        if not birth:
            return M.BIRTH_INVALID
        caregiver = repo.get_caregiver_by_phone(phone) or repo.create_caregiver(phone)
        tz = os.getenv("TIMEZONE", "America/Sao_Paulo")
        child = repo.create_child(state["baby_name"], birth, tz)
        repo.link_caregiver_child(caregiver["id"], child["id"])
        repo.upsert_onboarding_state(
            phone, step="awaiting_partner",
            baby_name=state["baby_name"], child_id=child["id"],
        )
        return M.ask_partner(child["name"])

    if step == "awaiting_partner":
        if text.lower() in _NEGATIVE:
            repo.clear_onboarding_state(phone)
            return M.onboarding_done(state["baby_name"])
        partner = normalize_phone(text)
        if not _valid_phone(partner):
            return M.PARTNER_INVALID
        existing = repo.get_caregiver_by_phone(partner) or repo.create_caregiver(partner)
        repo.link_caregiver_child(existing["id"], state["child_id"])
        repo.clear_onboarding_state(phone)
        return M.partner_added(partner, state["baby_name"])

    # Passo desconhecido: reinicia com segurança.
    repo.clear_onboarding_state(phone)
    return M.WELCOME_ASK_NAME
