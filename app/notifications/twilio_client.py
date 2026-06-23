"""Envio de mensagens WhatsApp via Twilio (API REST).

Alternativa ao `meta_client` — selecionada por `WHATSAPP_PROVIDER=twilio`.
O `import twilio` é preguiçoso para manter o núcleo testável sem a dependência.
"""
from __future__ import annotations

import os


def send_whatsapp(to: str, body: str) -> None:
    from twilio.rest import Client

    client = Client(
        os.environ["TWILIO_ACCOUNT_SID"], os.environ["TWILIO_AUTH_TOKEN"]
    )
    to_ = to if to.startswith("whatsapp:") else f"whatsapp:{to}"
    from_ = os.environ["TWILIO_WHATSAPP_FROM"]
    from_ = from_ if from_.startswith("whatsapp:") else f"whatsapp:{from_}"
    client.messages.create(from_=from_, to=to_, body=body)
