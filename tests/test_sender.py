import app.notifications.meta_client as meta_client
import app.notifications.twilio_client as twilio_client
from app.notifications.sender import send_whatsapp


def test_dispatch_to_meta_by_default(monkeypatch):
    calls = []
    monkeypatch.delenv("WHATSAPP_PROVIDER", raising=False)
    monkeypatch.setattr(meta_client, "send_whatsapp", lambda to, b: calls.append(("meta", to, b)))
    send_whatsapp("+5511999999999", "oi")
    assert calls == [("meta", "+5511999999999", "oi")]


def test_dispatch_to_twilio_when_configured(monkeypatch):
    calls = []
    monkeypatch.setenv("WHATSAPP_PROVIDER", "twilio")
    monkeypatch.setattr(twilio_client, "send_whatsapp", lambda to, b: calls.append(("twilio", to, b)))
    send_whatsapp("+5511999999999", "oi")
    assert calls == [("twilio", "+5511999999999", "oi")]
