"""Webhooks do WhatsApp (Meta Cloud API e Twilio).

Meta:
- `GET /webhook/whatsapp`  → verificação inicial do webhook (hub.challenge).
- `POST /webhook/whatsapp` → recebe JSON, processa e responde via Graph API.

Twilio:
- `POST /webhook/twilio`   → recebe form, processa e responde via TwiML.

As duas rotas coexistem; o provedor ativo é definido por qual delas você aponta
no painel (Meta ou Twilio). Apenas os lembretes proativos (cron) precisam saber
o provedor, via `WHATSAPP_PROVIDER` (ver `notifications/sender.py`).
"""
from __future__ import annotations

import hashlib
import hmac
import logging
import os
from datetime import datetime
from zoneinfo import ZoneInfo

from flask import Blueprint, Response, request

from app.config import load_wake_window_config
from app.db import SupabaseRepository
from app.handler import process_message
from app.notifications.meta_client import send_whatsapp

log = logging.getLogger(__name__)

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

    try:
        repo = SupabaseRepository()
        config = load_wake_window_config()
        tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))
        now = datetime.now(tz)
        reply = process_message(repo, config, phone, body, now)
        send_whatsapp(phone, reply)
    except Exception:
        log.exception("Erro ao processar mensagem Meta de %s: %r", phone, body)

    return Response("ok", mimetype="text/plain")


def _transcribe_audio(media_url: str) -> str:
    """Baixa o áudio do Twilio e transcreve via Whisper (OpenAI)."""
    import io
    import requests as req
    from openai import OpenAI

    sid = os.environ["TWILIO_ACCOUNT_SID"]
    token = os.environ["TWILIO_AUTH_TOKEN"]
    audio = req.get(media_url, auth=(sid, token), timeout=30)
    audio.raise_for_status()

    client = OpenAI()
    result = client.audio.transcriptions.create(
        model="whisper-1",
        file=("audio.ogg", io.BytesIO(audio.content), "audio/ogg"),
    )
    return result.text.strip()


@bp.post("/webhook/twilio")
def twilio_incoming() -> Response:
    from_number = request.form.get("From", "")
    body = request.form.get("Body", "")

    # Áudio: transcreve com Whisper e usa o texto como mensagem.
    if request.form.get("NumMedia", "0") != "0":
        media_type = request.form.get("MediaContentType0", "")
        if "audio" in media_type:
            media_url = request.form.get("MediaUrl0", "")
            try:
                body = _transcribe_audio(media_url)
                log.info("Áudio transcrito de %s: %r", from_number, body)
            except Exception:
                log.exception("Falha ao transcrever áudio de %s", from_number)
                body = ""
        if not body:
            return Response("", status=204)

    try:
        repo = SupabaseRepository()
        config = load_wake_window_config()
        tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))
        now = datetime.now(tz)
        reply = process_message(repo, config, from_number, body, now)
    except Exception:
        log.exception("Erro ao processar mensagem de %s: %r", from_number, body)
        reply = "⚠️ Ocorreu um erro interno. Tente novamente em instantes."

    # Envia via SDK (ativo) em vez de TwiML passivo — mais confiável no sandbox.
    try:
        from app.notifications.twilio_client import send_whatsapp as twilio_send
        twilio_send(from_number, reply)
    except Exception as exc:
        log.exception("Falha ao enviar resposta Twilio para %s", from_number)
        if os.getenv("AI_DEBUG", "").lower() == "true":
            return Response(f"[debug] {type(exc).__name__}: {exc}", status=200, mimetype="text/plain")

    return Response("", status=204)


@bp.get("/health")
def health() -> Response:
    return Response("ok", mimetype="text/plain")


@bp.post("/cron/reminders")
def cron_reminders() -> Response:
    """Endpoint chamado pelo cron externo (ex.: cron-job.org) a cada 2 min.
    Protegido por CRON_SECRET para evitar chamadas não autorizadas."""
    secret = os.getenv("CRON_SECRET")
    if secret and request.headers.get("X-Cron-Secret") != secret:
        return Response("Forbidden", status=403)

    try:
        from app.config import load_wake_window_config
        from app.db import SupabaseRepository
        from app.notifications.reminders import run_reminder_check
        from app.notifications.sender import send_whatsapp
        from zoneinfo import ZoneInfo

        repo = SupabaseRepository()
        config = load_wake_window_config()
        tz = ZoneInfo(os.getenv("TIMEZONE", "America/Sao_Paulo"))
        now = datetime.now(tz)
        actions = run_reminder_check(repo, config, now, send_whatsapp)
        log.info("cron/reminders: %d aviso(s)", len(actions))
        return Response(f"{len(actions)} aviso(s)", mimetype="text/plain")
    except Exception:
        log.exception("Erro no cron de lembretes")
        return Response("error", status=500)
