"""Webhook do Twilio (WhatsApp).

Recebe as mensagens, valida a assinatura do Twilio (opcional em dev), delega
para `app.handler.process_message` e devolve a resposta em TwiML.
"""
from __future__ import annotations

import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, request
from twilio.request_validator import RequestValidator
from twilio.twiml.messaging_response import MessagingResponse

from app.config import load_wake_window_config
from app.db import SupabaseRepository
from app.handler import process_message

bp = Blueprint("webhook", __name__)


def _is_valid_twilio_request() -> bool:
    """Valida a assinatura do Twilio. Desligável em dev com TWILIO_VALIDATE=false."""
    if os.getenv("TWILIO_VALIDATE", "true").lower() == "false":
        return True
    token = os.getenv("TWILIO_AUTH_TOKEN")
    if not token:
        return True  # sem token configurado (dev), não valida
    validator = RequestValidator(token)
    signature = request.headers.get("X-Twilio-Signature", "")
    return validator.validate(request.url, request.form.to_dict(), signature)


def _twiml(text: str) -> Response:
    resp = MessagingResponse()
    resp.message(text)
    return Response(str(resp), mimetype="application/xml")


@bp.post("/webhook/twilio")
def twilio_webhook() -> Response:
    if not _is_valid_twilio_request():
        return Response("Invalid signature", status=403)

    from_number = request.form.get("From", "")
    body = request.form.get("Body", "")

    repo = SupabaseRepository()
    config = load_wake_window_config()
    tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))
    now = datetime.now(tz)

    reply = process_message(repo, config, from_number, body, now)
    return _twiml(reply)


@bp.get("/health")
def health() -> Response:
    return Response("ok", mimetype="text/plain")
