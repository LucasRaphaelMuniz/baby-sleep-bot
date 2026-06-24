"""Parser de comandos do WhatsApp.

Converte uma mensagem de texto num comando estruturado. É *puro* de propósito:
não conhece o "agora", não acessa banco e não tem efeitos colaterais — quem
resolve data/fuso e persistência é a camada de eventos. Isso o torna 100%
testável de forma determinística.
"""
from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import time
from enum import Enum
from typing import Optional


class CommandType(Enum):
    SLEEP_START = "sleep_start"        # 1 - dormiu (soneca)
    WAKE = "wake"                      # 2 - acordou
    FEED = "feed"                      # 3 - mamou / mamou e dormiu
    NIGHT_WAKING = "night_waking"      # 4 - despertou e dormiu de novo (sem mamar)
    NIGHT = "night"                    # 5 - sono noturno
    STATUS = "status"                  # 6 - status
    UNDO = "undo"                      # 9 / desfazer
    HELP = "help"                      # 0 - ajuda / menu
    ERROR = "error"                    # ambíguo: pedir esclarecimento
    NATURAL_LANGUAGE = "natural"       # não é comando -> roteia para a IA


# Atalho de texto -> tipo de comando.
_COMMANDS = {
    "1": CommandType.SLEEP_START,
    "2": CommandType.WAKE,
    "3": CommandType.FEED,
    "4": CommandType.NIGHT_WAKING,
    "5": CommandType.NIGHT,
    "6": CommandType.STATUS,
    "0": CommandType.HELP,
    "9": CommandType.UNDO,
    "desfazer": CommandType.UNDO,
    "ajuda": CommandType.HELP,
    "menu": CommandType.HELP,
}

# Vocabulário de local do sono (pt-BR -> canônico).
_LOCATIONS = {
    "berco": "crib", "berço": "crib",
    "colo": "arms",
    "carrinho": "stroller",
    "carro": "car",
    "peito": "breast", "mama": "breast",
}

# Vocabulário de dificuldade pra dormir (pt-BR -> canônico).
_DIFFICULTIES = {
    "fácil": "easy", "facil": "easy", "tranquilo": "easy",
    "trabalho": "hard", "difícil": "hard", "dificil": "hard", "custou": "hard",
}

# Aceita "14", "14:00", "14h", "14h30", "1430".
_TIME_RE = re.compile(r"^(\d{1,2})[:h]?(\d{2})?$")


@dataclass
class ParsedCommand:
    type: CommandType
    at: Optional[time] = None          # horário do evento; None = "agora"
    location: Optional[str] = None     # local canônico do sono, se informado
    difficulty: Optional[str] = None   # dificuldade pra dormir, se informada
    raw: str = ""                      # mensagem original (trim)
    error_message: Optional[str] = None


def parse_time(token: str) -> Optional[time]:
    """Converte um token de horário em `datetime.time`, ou None se inválido."""
    m = _TIME_RE.match(token)
    if not m:
        return None
    hh = int(m.group(1))
    mm = int(m.group(2)) if m.group(2) else 0
    if 0 <= hh <= 23 and 0 <= mm <= 59:
        return time(hh, mm)
    return None


def parse(message: str) -> ParsedCommand:
    """Interpreta uma mensagem recebida e devolve um `ParsedCommand`."""
    raw = (message or "").strip()
    tokens = raw.lower().split()
    if not tokens:
        return ParsedCommand(
            CommandType.ERROR, raw=raw, error_message="Mensagem vazia."
        )

    first = tokens[0]
    cmd = _COMMANDS.get(first)

    if cmd is None:
        # Número isolado fora de 0–5: ambíguo. Não adivinhamos — pedimos o comando.
        if first.isdigit() and len(tokens) == 1:
            return ParsedCommand(
                CommandType.ERROR,
                raw=raw,
                error_message=(
                    f"Recebi “{first}”. Adicione o comando na frente: "
                    f"`1 {first}` (dormiu {first}h) ou "
                    f"`2 {first}` (acordou {first}h)."
                ),
            )
        # Qualquer outro texto livre vai para a IA.
        return ParsedCommand(CommandType.NATURAL_LANGUAGE, raw=raw)

    # Comandos sem argumentos.
    if cmd in (CommandType.STATUS, CommandType.UNDO, CommandType.HELP):
        return ParsedCommand(cmd, raw=raw)

    # Argumentos opcionais (ordem livre): horário, local e dificuldade.
    # Tokens não reconhecidos são ignorados.
    at: Optional[time] = None
    location: Optional[str] = None
    difficulty: Optional[str] = None
    for tok in tokens[1:]:
        if at is None and (parsed := parse_time(tok)) is not None:
            at = parsed
            continue
        if location is None and tok in _LOCATIONS:
            location = _LOCATIONS[tok]
            continue
        if difficulty is None and tok in _DIFFICULTIES:
            difficulty = _DIFFICULTIES[tok]

    return ParsedCommand(cmd, at=at, location=location, difficulty=difficulty, raw=raw)
