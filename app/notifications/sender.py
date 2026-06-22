"""Despacho de envio de WhatsApp conforme o provedor configurado.

`WHATSAPP_PROVIDER` (env) escolhe o backend: `meta` (default) ou `twilio`.
Usado pelos lembretes proativos (cron). As respostas do webhook são tratadas
diretamente na rota de cada provedor.
"""
from __future__ import annotations

import os


def send_whatsapp(to: str, body: str) -> None:
    provider = os.getenv("WHATSAPP_PROVIDER", "meta").lower()
    if provider == "twilio":
        from app.notifications import twilio_client as client
    else:
        from app.notifications import meta_client as client
    client.send_whatsapp(to, body)
