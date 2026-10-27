"""Komunikácia backendu s frontendom: správy na stdout, príkazy zo stdin."""

import io
import json
import os
import queue
import threading
from typing import Any, TextIO

from krok.common.protocol import encode_message


class Channel:
    """Posiela frontendu správy protokolu."""

    def __init__(self, stream: TextIO) -> None:
        self._stream = stream
        self._lock = threading.Lock()

    def send(self, message: dict[str, Any]) -> None:
        with self._lock:
            self._stream.write(encode_message(message))
            self._stream.flush()


class MessageStream(io.TextIOBase):
    """Textový prúd, ktorého obsah odchádza ako správy.

    Takto ide chybový výstup programu. Stdout a stderr sú dve rúry a frontend by
    nevedel zaručiť ich vzájomné poradie, traceback by sa mohol objaviť pred výpisom.
    """

    def __init__(self, channel: Channel, name: str) -> None:
        super().__init__()
        self._channel = channel
        self._name = name

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        if text:
            self._channel.send({"event": "output", "stream": self._name, "text": text})
        return len(text)


class InputStream(io.TextIOBase):
    """Náhrada sys.stdin: riadky pre input() prichádzajú od ImmediateReader."""

    def __init__(self, lines: "queue.Queue[str]") -> None:
        super().__init__()
        self._lines = lines

    def readable(self) -> bool:
        return True

    def readline(self, size: int = -1, /) -> str:  # type: ignore[override]  # ako v typeshed
        return self._lines.get() + "\n"


class ImmediateReader(threading.Thread):
    """Jediný čitateľ stdin backendu.

    Keby stdin čítal aj input(), dvaja čitatelia by si kradli riadky
    a príkaz od frontendu by mohol skončiť ako vstup programu.

    Číta priamo z deskriptora. Vlákno čakajúce v sys.stdin.buffer by držalo jeho
    zámok a interpreter by pri ukončení spadol (Fatal Python error: _enter_buffered_busy).
    """

    def __init__(
        self,
        fd: int,
        commands: "queue.Queue[dict[str, Any]]",
        inputs: "queue.Queue[str]",
    ) -> None:
        super().__init__(name="ImmediateReader", daemon=True)
        self._fd = fd
        self._commands = commands
        self._inputs = inputs

    def run(self) -> None:
        pending = b""
        while chunk := os.read(self._fd, 65536):
            *lines, pending = (pending + chunk).split(b"\n")
            for line in lines:
                command = json.loads(line)
                if command["cmd"] == "input":
                    self._inputs.put(command["text"])
                else:
                    self._commands.put(command)
        # Rúra sa zavrela, frontend teda skončil alebo spadol. Program nemá komu bežať.
        os._exit(1)
