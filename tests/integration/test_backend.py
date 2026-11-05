"""Backend v skutočnom procese, bez GUI."""

import time
from collections.abc import Callable
from typing import Any

import pytest

from krok.common.trace import Limits
from krok.services.backend_client import BackendClient, Event, Exited, Message, Output


def start(source: str) -> BackendClient:
    client = BackendClient()
    client.start(source, "<untitled>")
    return client


def visualize(source: str, limits: Limits | None = None) -> BackendClient:
    client = BackendClient()
    client.visualize(source, "program.py", limits)
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


def trace_of(events: list[Event]) -> dict[str, Any]:
    traces = [e.data["trace"] for e in events if isinstance(e, Message)]
    assert len(traces) == 1
    trace: dict[str, Any] = traces[0]
    return trace


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


def test_trace_arrives_with_live_output_and_shared_box() -> None:
    source = 'a = [1]\nb = a\nx = input("Meno: ")\nprint("Ahoj", x)\n'
    client = visualize(source, Limits(seconds=0.5))
    events = collect(client, lambda events: text(events) == "Meno: ")  # výstup ide hneď
    time.sleep(0.7)  # čakanie na študenta sa do časového limitu nepočíta
    client.send_input("Ján")
    events += collect(client, exited)
    assert events[-1] == Exited(0)

    trace = trace_of(events)
    assert trace["status"] == "ok"
    assert trace["inputs"] == ["Ján"]
    final = trace["steps"][-1]["frames"][-1]["vars"]
    assert final["a"] == final["b"]
    assert final["a"][0] == "ref"


def test_interrupt_gives_partial_trace_within_a_second() -> None:
    client = visualize('print("bezi")\nwhile True:\n    pass\n')
    collect(client, lambda events: text(events) == "bezi\n")
    time.sleep(0.3)
    client.interrupt()
    trace = trace_of(collect(client, exited, timeout=1))
    assert trace["status"] == "interrupted"
    assert trace["truncated"] is True
    assert trace["step_count"] > 0


def test_interrupt_behaves_like_ctrl_c_in_waiting_input() -> None:
    source = (
        "try:\n"
        '    input("Meno: ")\n'
        "except KeyboardInterrupt:\n"
        '    print("prerusene")\n'
        "finally:\n"
        '    print("upratane")\n'
    )
    client = visualize(source)
    events = collect(client, lambda events: text(events) == "Meno: ")
    client.interrupt()
    events += collect(client, exited, timeout=1)
    assert text(events) == "Meno: prerusene\nupratane\n"
    assert trace_of(events)["status"] == "interrupted"


@pytest.mark.parametrize(
    "tail",
    [
        "while True:\n    try:\n        pass\n    except:\n        pass\n",
        'while True:\n    try:\n        input("Cislo: ")\n    except:\n        pass\n',
        "import time\ntime.sleep(60)\n",
    ],
    ids=["zachyti-v-cykle", "zachyti-v-input", "stoji-mimo-trasovania"],
)
def test_trace_arrives_even_if_program_does_not_stop(tail: str) -> None:
    client = visualize('print("bezi")\n' + tail)
    collect(client, lambda events: "bezi\n" in text(events))
    client.interrupt()
    trace = trace_of(collect(client, exited, timeout=2))
    assert (trace["status"], trace["truncated"]) == ("interrupted", True)
