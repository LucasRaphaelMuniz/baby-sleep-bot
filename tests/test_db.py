from app.db import _dt


def test_dt_converts_utc_to_app_tz(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "America/Sao_Paulo")
    # Supabase devolve timestamptz em UTC; 21:30Z = 18:30 em São Paulo.
    d = _dt("2026-06-22T21:30:00+00:00")
    assert d.strftime("%H:%M") == "18:30"
    assert d.utcoffset().total_seconds() == -3 * 3600


def test_dt_assumes_utc_when_naive(monkeypatch):
    monkeypatch.setenv("TIMEZONE", "America/Sao_Paulo")
    d = _dt("2026-06-22T21:30:00")
    assert d.strftime("%H:%M") == "18:30"


def test_dt_none():
    assert _dt(None) is None
