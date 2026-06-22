"""Envio de mensagens WhatsApp via Twilio (API REST, para avisos proativos)."""
from __future__ import annotations

import os


def _client():
    from twilio.rest import Client

    return Client(os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"])


def send_whatsapp(to: str, body: str) -> None:
    from_ = os.environ["TWILIO_WHATSAPP_FROM"]
    to_ = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    _client().messages.create(from_=from_, to=to_, body=body)
