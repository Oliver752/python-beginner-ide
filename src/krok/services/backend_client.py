"""Klient backendu: spustí ho v samostatnom procese a jeho výstup mení na udalosti."""

import codecs
import os
import queue
import subprocess
import sys
import threading
from dataclasses import dataclass
from typing import Any

from krok.common.protocol import Item, MessageParser, encode_command

# Plný front zastaví čítanie rúry, a tým aj backend. Program, ktorý vypisuje
# donekonečna, tak nezahltí pamäť IDE, len beží tak rýchlo, ako stíha konzola.
QUEUE_SIZE = 64
CHUNK_SIZE = 8192
KILL_TIMEOUT = 2.0


@dataclass(frozen=True)
class Output:
    stream: str  # "stdout" alebo "stderr"
    text: str


@dataclass(frozen=True)
class Message:
    data: dict[str, Any]


@dataclass(frozen=True)
class Exited:
    returncode: int


Event = Output | Message | Exited


class BackendClient:
    def __init__(self, interpreter: str = sys.executable) -> None:
        self._interpreter = interpreter
        self._events: queue.Queue[Event] = queue.Queue(QUEUE_SIZE)
        self._stopped = threading.Event()
        self._process: subprocess.Popen[bytes] | None = None

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    def start(self, source: str, path: str) -> None:
        # -u: bez neho by rúra zadržiavala výstup a konzola by vyzerala mŕtvo.
        # -P: aktuálny priečinok nejde do sys.path, takže súbor používateľa
        #     nazvaný napríklad queue.py nezatieni modul, ktorý potrebuje backend.
        self._process = subprocess.Popen(
            [self._interpreter, "-u", "-P", "-m", "krok.backend"],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            env=os.environ | {"PYTHONIOENCODING": "utf-8"},
            # Na Windows by konzolový python.exe inak otvoril vlastné okno.
            creationflags=getattr(subprocess, "CREATE_NO_WINDOW", 0),
        )
        errors = threading.Thread(target=self._read_errors, args=(self._process,), daemon=True)
        errors.start()
        threading.Thread(
            target=self._read_output, args=(self._process, errors), daemon=True
        ).start()
        self._send({"cmd": "run", "source": source, "path": path})

    def send_input(self, text: str) -> None:
        self._send({"cmd": "input", "text": text})

    def stop(self) -> None:
        """Ukončí backend. Udalosti, ktoré ešte neboli prevzaté, sa zahodia."""
        self._stopped.set()
        if self._process is not None:
            self._process.terminate()
            threading.Thread(target=_kill_if_stuck, args=(self._process,), daemon=True).start()

    def poll(self, limit: int = 16) -> list[Event]:
        """Vráti čakajúce udalosti; susedné kusy textu z jedného prúdu spojí."""
        events: list[Event] = []
        for _ in range(limit):
            try:
                event = self._events.get_nowait()
            except queue.Empty:
                break
            previous = events[-1] if events else None
            if (
                isinstance(event, Output)
                and isinstance(previous, Output)
                and previous.stream == event.stream
            ):
                events[-1] = Output(event.stream, previous.text + event.text)
            else:
                events.append(event)
        return events

    def _send(self, command: dict[str, Any]) -> None:
        assert self._process is not None and self._process.stdin is not None
        try:
            self._process.stdin.write(encode_command(command).encode())
            self._process.stdin.flush()
        except (OSError, ValueError):
            pass  # backend už skončil, ozve sa udalosťou Exited

    def _put(self, event: Event) -> None:
        # Po stop() nikto front nevyberá; čítacie vlákna nesmú čakať navždy.
        while not self._stopped.is_set():
            try:
                self._events.put(event, timeout=0.1)
                return
            except queue.Full:
                pass

    def _read_output(self, process: "subprocess.Popen[bytes]", errors: threading.Thread) -> None:
        assert process.stdout is not None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        parser = MessageParser()
        while chunk := os.read(process.stdout.fileno(), CHUNK_SIZE):
            for item in parser.feed(decoder.decode(chunk)):
                self._put(_to_event(item))
        for item in parser.finish():
            self._put(_to_event(item))
        # Exited musí prísť až po všetkom výstupe, aj po tom z rúry stderr.
        errors.join()
        self._put(Exited(process.wait()))

    def _read_errors(self, process: "subprocess.Popen[bytes]") -> None:
        # Sem píše len samotný interpreter (napr. pri páde); program posiela stderr ako správy.
        assert process.stderr is not None
        decoder = codecs.getincrementaldecoder("utf-8")(errors="replace")
        while chunk := os.read(process.stderr.fileno(), CHUNK_SIZE):
            self._put(Output("stderr", decoder.decode(chunk)))


def _to_event(item: Item) -> Event:
    if isinstance(item, str):
        return Output("stdout", item)
    if item.get("event") == "output":
        return Output(item["stream"], item["text"])
    return Message(item)


def _kill_if_stuck(process: "subprocess.Popen[bytes]") -> None:
    try:
        process.wait(KILL_TIMEOUT)
    except subprocess.TimeoutExpired:
        process.kill()
