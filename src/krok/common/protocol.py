"""Protokol medzi frontendom a backendom.

Backend píše na stdout výstup programu ako obyčajný text a medzi neho vkladá
správy: riadky "\\x02" + JSON. Frontend posiela backendu na stdin riadky JSON (príkazy).
"""

import json
from typing import Any

MESSAGE_START = "\x02"

Item = str | dict[str, Any]


def encode_message(message: dict[str, Any]) -> str:
    return MESSAGE_START + json.dumps(message) + "\n"


def encode_command(command: dict[str, Any]) -> str:
    return json.dumps(command) + "\n"


class MessageParser:
    """Rozdeľuje prúd zo stdout backendu na text programu (str) a správy (dict)."""

    def __init__(self) -> None:
        # Začiatok správy, ktorej koniec ešte neprišiel.
        self._pending = ""

    def feed(self, data: str) -> list[Item]:
        data = self._pending + data
        self._pending = ""
        items: list[Item] = []
        position = 0
        while (start := data.find(MESSAGE_START, position)) >= 0:
            end = data.find("\n", start)
            if end < 0:
                self._pending = data[start:]
                data = data[:start]
                break
            if start > position:
                items.append(data[position:start])
            items.append(_decode(data[start : end + 1]))
            position = end + 1
        if position < len(data):
            items.append(data[position:])
        return items

    def finish(self) -> list[Item]:
        """Na konci prúdu vráti nedokončenú správu ako obyčajný text."""
        rest, self._pending = self._pending, ""
        return [rest] if rest else []


def _decode(line: str) -> Item:
    # Znak \x02 mohol vypísať aj samotný program; čo nie je platná správa, je jeho výstup.
    try:
        message = json.loads(line[1:])
    except ValueError:
        return line
    return message if isinstance(message, dict) else line
