"""Backend v skutočnom procese, bez GUI."""

import time
from collections.abc import Callable

from krok.services.backend_client import BackendClient, Event, Exited, Output


def start(source: str) -> BackendClient:
    client = BackendClient()
    client.start(source, "<untitled>")
    return client


def collect(
    client: BackendClient, done: Callable[[list[Event]], bool], timeout: float = 10
) -> list[Event]:
    events: list[Event] = []
    deadline = time.monotonic() + timeout
    while not done(events):
        assert time.monotonic() < deadline, f"backend neodpovedá, doteraz: {events}"
        events += client.poll()
        time.sleep(0.01)
    return events


def exited(events: list[Event]) -> bool:
    return bool(events) and isinstance(events[-1], Exited)


def text(events: list[Event], stream: str = "stdout") -> str:
    return "".join(e.text for e in events if isinstance(e, Output) and e.stream == stream)


def test_error_comes_after_output_without_backend_frames() -> None:
    events = collect(start('print("pred chybou")\n1 / 0\n'), exited)
    streams = [e.stream for e in events if isinstance(e, Output)]
    assert "stdout" not in streams[streams.index("stderr") :]
    assert text(events) == "pred chybou\n"
    error = text(events, "stderr")
    assert 'File "<untitled>", line 2' in error
    assert "ZeroDivisionError" in error
    assert "krok" not in error
    assert events[-1] == Exited(1)


def test_input_reaches_running_program() -> None:
    client = start('meno = input("Meno: ")\nprint("Ahoj,", meno)\n')
    events = collect(client, lambda events: text(events) == "Meno: ")
    client.send_input("Ján")
    events += collect(client, exited)
    assert text(events) == "Meno: Ahoj, Ján\n"
    assert events[-1] == Exited(0)


def test_stop_ends_infinite_loop() -> None:
    client = start("while True:\n    pass\n")
    time.sleep(0.3)
    assert client.running
    client.stop()
    deadline = time.monotonic() + 1
    while client.running:
        assert time.monotonic() < deadline, "backend beží aj po zastavení"
        time.sleep(0.01)
