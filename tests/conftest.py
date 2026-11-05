import io
import os
import queue
import threading
from collections.abc import Callable, Iterable
from typing import Any

import pytest

from krok.backend.channel import Channel
from krok.backend.visualize import Visualization
from krok.common.trace import Limits

# GUI testy bežia bez zobrazovania okien. Musí sa nastaviť pred vytvorením QApplication.
os.environ.setdefault("QT_QPA_PLATFORM", "offscreen")

Trace = dict[str, Any]
TraceProgram = Callable[..., Trace]


class CapturedChannel(Channel):
    def __init__(self) -> None:
        super().__init__(io.StringIO(), "")
        self.messages: list[dict[str, Any]] = []

    def send(self, message: dict[str, Any]) -> None:
        self.messages.append(message)


def pytest_addoption(parser: pytest.Parser) -> None:
    parser.addoption(
        "--update-golden", action="store_true", help="prepíše zlaté stopy; git diff treba prezrieť"
    )


@pytest.fixture
def trace_program() -> TraceProgram:
    """Záznam programu v tomto procese, bez rúr. Stačí na všetko okrem zastavenia."""

    def record(source: str, inputs: Iterable[str] = (), limits: Limits | None = None) -> Trace:
        channel = CapturedChannel()
        lines: queue.Queue[str | None] = queue.Queue()
        for line in inputs:
            lines.put(line)
        Visualization(
            source, "program.py", channel, lines, threading.Event(), limits or Limits()
        ).run()
        trace: Trace = channel.messages[-1]["trace"]
        return trace

    return record
