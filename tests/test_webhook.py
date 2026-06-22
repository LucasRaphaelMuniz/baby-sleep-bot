from app.routes.webhook import extract_message


def _payload(text):
    return {
        "object": "whatsapp_business_account",
        "entry": [{"changes": [{"value": {"messages": [
            {"from": "5511988887777", "type": "text", "text": {"body": text}}
        ]}}]}],
    }


def test_extract_text_message():
    assert extract_message(_payload("1 14:00")) == ("5511988887777", "1 14:00")


def test_extract_ignores_delivery_status():
    payload = {"entry": [{"changes": [{"value": {
        "statuses": [{"status": "delivered"}]
    }}]}]}
    assert extract_message(payload) is None


def test_extract_ignores_non_text():
    payload = {"entry": [{"changes": [{"value": {"messages": [
        {"from": "55", "type": "image"}
    ]}}]}]}
    assert extract_message(payload) is None


def test_extract_handles_empty_payload():
    assert extract_message({}) is None
    assert extract_message({"entry": []}) is None
