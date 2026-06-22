from datetime import time

import pytest

from app.core.parser import CommandType, parse, parse_time


# ── parse_time ───────────────────────────────────────────────────────
@pytest.mark.parametrize(
    "token,expected",
    [
        ("14", time(14, 0)),
        ("9", time(9, 0)),
        ("14:00", time(14, 0)),
        ("14:30", time(14, 30)),
        ("14h", time(14, 0)),
        ("14h30", time(14, 30)),
        ("1430", time(14, 30)),
        ("0900", time(9, 0)),
        ("900", time(9, 0)),
    ],
)
def test_parse_time_valid(token, expected):
    assert parse_time(token) == expected


@pytest.mark.parametrize("token", ["24", "25:00", "14:60", "abc", "", "99"])
def test_parse_time_invalid(token):
    assert parse_time(token) is None


# ── comandos simples ─────────────────────────────────────────────────
def test_sleep_now():
    cmd = parse("1")
    assert cmd.type is CommandType.SLEEP_START
    assert cmd.at is None
    assert cmd.location is None


def test_sleep_with_hour_only():
    cmd = parse("1 14")
    assert cmd.type is CommandType.SLEEP_START
    assert cmd.at == time(14, 0)


def test_sleep_with_full_time():
    assert parse("1 14:00").at == time(14, 0)
    assert parse("1 14h30").at == time(14, 30)


def test_sleep_with_location():
    cmd = parse("1 14 colo")
    assert cmd.at == time(14, 0)
    assert cmd.location == "arms"


def test_sleep_location_without_time():
    cmd = parse("1 carrinho")
    assert cmd.at is None
    assert cmd.location == "stroller"


def test_sleep_with_difficulty():
    cmd = parse("1 14 colo trabalho")
    assert cmd.at == time(14, 0)
    assert cmd.location == "arms"
    assert cmd.difficulty == "hard"


def test_sleep_difficulty_easy_order_free():
    # ordem livre entre hora/local/dificuldade
    cmd = parse("1 fácil 14:30")
    assert cmd.at == time(14, 30)
    assert cmd.difficulty == "easy"


def test_wake_feed_night():
    assert parse("2").type is CommandType.WAKE
    assert parse("3").type is CommandType.FEED
    assert parse("5").type is CommandType.NIGHT


def test_status_ignores_extra_tokens():
    cmd = parse("4 lixo aqui")
    assert cmd.type is CommandType.STATUS
    assert cmd.at is None


def test_undo_variants():
    assert parse("0").type is CommandType.UNDO
    assert parse("desfazer").type is CommandType.UNDO
    assert parse("DESFAZER").type is CommandType.UNDO


# ── casos de erro / linguagem natural ────────────────────────────────
def test_bare_number_is_error():
    cmd = parse("14")
    assert cmd.type is CommandType.ERROR
    assert "14" in cmd.error_message


def test_empty_message_is_error():
    assert parse("   ").type is CommandType.ERROR


def test_free_text_routes_to_ai():
    cmd = parse("ela tá dormindo pouco hoje, é normal?")
    assert cmd.type is CommandType.NATURAL_LANGUAGE
    assert cmd.raw.startswith("ela")


def test_location_word_alone_routes_to_ai():
    # "colo" sozinho não é comando; vira pergunta para a IA.
    assert parse("colo").type is CommandType.NATURAL_LANGUAGE
