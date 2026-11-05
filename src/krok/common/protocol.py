"""Protokol medzi frontendom a backendom.

Backend píše na stdout výstup programu ako obyčajný text a medzi neho vkladá
správy: riadky "\\x02" + token + JSON. Token je náhodný pre každý beh, aby výpis programu
nemohol správu napodobniť. Frontend posiela backendu na stdin riadky JSON (príkazy).
"""

import json
from typing import Any

MESSAGE_START = "\x02"

Item = str | dict[str, Any]


def encode_message(message: dict[str, Any], token: str) -> str:
    return MESSAGE_START + token + json.dumps(message) + "\n"


def encode_command(command: dict[str, Any]) -> str:
    return json.dumps(command) + "\n"


class MessageParser:
    """Rozdeľuje prúd zo stdout backendu na text programu (str) a správy (dict)."""

    def __init__(self, token: str) -> None:
        self._marker = MESSAGE_START + token
        # Začiatok značky, ktorej koniec ešte neprišiel.
        self._partial = ""
        # Kusy správy bez konca. Stopa má aj desiatky MB, opakované spájanie by bolo kvadratické.
        self._message: list[str] = []

    def feed(self, data: str) -> list[Item]:
        data = self._partial + data
        self._partial = ""
        items: list[Item] = []
        if self._message:
            end = data.find("\n")
            if end < 0:
                self._message.append(data)
                return items
            items.append(self._decode(data[:end]))
            data = data[end + 1 :]

        text_start = search = 0
        while (start := data.find(MESSAGE_START, search)) >= 0:
            head = data[start : start + len(self._marker)]
            if head != self._marker:
                if self._marker.startswith(head):
                    self._partial = data[start:]
                    data = data[:start]
                    break
                search = start + 1  # znak \x02 vypísal program
                continue
            if start > text_start:
                items.append(data[text_start:start])
            body = start + len(self._marker)
            end = data.find("\n", body)
            if end < 0:
                self._message.append(data[body:])
                return items
            items.append(self._decode(data[body:end]))
            text_start = search = end + 1
        if text_start < len(data):
            items.append(data[text_start:])
        return items

    def finish(self) -> list[Item]:
        """Na konci prúdu vráti nedokončenú správu ako obyčajný text."""
        rest = self._partial + "".join(self._message)
        self._partial = ""
        self._message = []
        return [rest] if rest else []

    def _decode(self, tail: str) -> Item:
        text = "".join(self._message) + tail
        self._message = []
        # Beh, ktorý token uhádol alebo prečítal, nesmie zhodiť čítacie vlákno frontendu.
        try:
            message = json.loads(text)
        except ValueError:
            return text
        return message if isinstance(message, dict) else text
