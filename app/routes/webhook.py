"""Webhook do WhatsApp (Meta Cloud API).

- `GET /webhook/whatsapp`  → verificação inicial do webhook (hub.challenge).
- `POST /webhook/whatsapp` → recebe mensagens (JSON), processa e responde via API.

A Meta entrega a mensagem em JSON e espera HTTP 200 rápido; a resposta ao
usuário é enviada por uma chamada à Graph API (não pelo corpo da resposta).
"""
from __future__ import annotations

import hashlib
import hmac
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, request

from app.config import load_wake_window_config
from app.db import SupabaseRepository
from app.handler import process_message
from app.notifications.meta_client import send_whatsapp

bp = Blueprint("webhook", __name__)


def extract_message(payload: dict):
    """Extrai (telefone, texto) da primeira mensagem de texto do payload da
    Meta, ou None se for status de entrega / mensagem não-textual."""
    try:
        value = payload["entry"][0]["changes"][0]["value"]
        messages = value.get("messages")
        if not messages:
            return None
        msg = messages[0]
        if msg.get("type") != "text":
            return None
        return msg["from"], msg["text"]["body"]
    except (KeyError, IndexError, TypeError):
        return None


def _valid_signature() -> bool:
    """Valida X-Hub-Signature-256 (HMAC-SHA256 com o app secret da Meta).
    Desligável em dev com WHATSAPP_VALIDATE=false."""
    if os.getenv("WHATSAPP_VALIDATE", "true").lower() == "false":
        return True
    secret = os.getenv("WHATSAPP_APP_SECRET")
    if not secret:
        return True  # sem app secret configurado (dev), não valida
    received = request.headers.get("X-Hub-Signature-256", "")
    expected = "sha256=" + hmac.new(
        secret.encode(), request.get_data(), hashlib.sha256
    ).hexdigest()
    return hmac.compare_digest(received, expected)


@bp.get("/webhook/whatsapp")
def verify() -> Response:
    if (
        request.args.get("hub.mode") == "subscribe"
        and request.args.get("hub.verify_token") == os.getenv("WHATSAPP_VERIFY_TOKEN")
    ):
        return Response(request.args.get("hub.challenge", ""), mimetype="text/plain")
    return Response("Forbidden", status=403)


@bp.post("/webhook/whatsapp")
def incoming() -> Response:
    if not _valid_signature():
        return Response("Invalid signature", status=403)

    parsed = extract_message(request.get_json(silent=True) or {})
    if parsed is None:
        return Response("ok", mimetype="text/plain")  # status/não-texto: ignora

    phone, body = parsed
    repo = SupabaseRepository()
    config = load_wake_window_config()
    tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))
    now = datetime.now(tz)

    reply = process_message(repo, config, phone, body, now)
    send_whatsapp(phone, reply)
    return Response("ok", mimetype="text/plain")


@bp.get("/health")
def health() -> Response:
    return Response("ok", mimetype="text/plain")
