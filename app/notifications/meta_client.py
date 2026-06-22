"""Envio de mensagens WhatsApp via Meta Cloud API (Graph API).

Usado tanto pelas respostas do webhook quanto pelos lembretes proativos.
O `import requests` é preguiçoso para manter o núcleo testável sem a dependência.
"""
from __future__ import annotations

import os

GRAPH_VERSION = "v21.0"


def send_whatsapp(to: str, body: str) -> None:
    """Envia uma mensagem de texto para `to` (número em E.164, com ou sem '+')."""
    import requests

    phone_number_id = os.environ["WHATSAPP_PHONE_NUMBER_ID"]
    token = os.environ["WHATSAPP_TOKEN"]
    url = f"https://graph.facebook.com/{GRAPH_VERSION}/{phone_number_id}/messages"
    resp = requests.post(
        url,
        headers={"Authorization": f"Bearer {token}"},
        json={
            "messaging_product": "whatsapp",
            "to": to.lstrip("+"),          # Meta usa o wa_id em dígitos
            "type": "text",
            "text": {"body": body},
        },
        timeout=20,
    )
    resp.raise_for_status()
