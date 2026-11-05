"""Meranie výkonu záznamu cez skutočný backend: python -m pytest -m perf -s."""

import json
import time
from typing import Any

import pytest

from krok.services.backend_client import BackendClient, Exited, Message

pytestmark = pytest.mark.perf

LOOP = "sucet = 0\nfor i in range({n}):\n    sucet += i\n"
BIG_LIST = "cisla = list(range(1000))\nfor i in range({n}):\n    cisla[i % 1000] = i\n"
MATRIX = "m = [[0] * 50 for _ in range(50)]\nfor i in range({n}):\n    m[i % 50][i % 50] = i\n"
CALLS = "def f(x):\n    return x + 1\n\n\nfor i in range({n}):\n    f(i)\n"
OUTPUT = "for i in range({n}):\n    print(i)\n"
OBJECTS = (
    "class Uzol:\n    def __init__(self, hodnota, dalsi):\n"
    "        self.hodnota = hodnota\n        self.dalsi = dalsi\n\n\n"
    "hlava = None\nfor i in range({n}):\n    hlava = Uzol(i, hlava)\n"
)


def measure(source: str) -> tuple[dict[str, Any], float]:
    client = BackendClient()
    started = time.monotonic()
    client.visualize(source, "program.py")
    trace: dict[str, Any] = {}
    finished = False
    while not (trace and finished):
        assert time.monotonic() - started < 90, "backend neodpovedá"
        for event in client.poll():
            if isinstance(event, Message):
                trace = event.data["trace"]
            elif isinstance(event, Exited):
                finished = True
        time.sleep(0.001)
    return trace, time.monotonic() - started


@pytest.mark.parametrize(
    ("name", "template", "n", "budget"),
    [
        ("slucka 2 000 krokov", LOOP, 1000, 2.0),
        ("slucka 10 000 krokov", LOOP, 5000, 10.0),
        ("zoznam 1000 prvkov, 2 000 krokov", BIG_LIST, 1000, 2.0),
        ("zoznam 1000 prvkov, 10 000 krokov", BIG_LIST, 5000, 10.0),
        pytest.param(
            "matica 50 x 50, 2 000 krokov",
            MATRIX,
            1000,
            2.0,
            marks=pytest.mark.xfail(reason="R-01: 65 MB JSON, vyrieši rozdielové ukladanie v M6"),
        ),
        ("volania, 10 000 krokov", CALLS, 1650, 10.0),
        ("vypis, 10 000 krokov", OUTPUT, 5000, 10.0),
        ("spajany zoznam, 10 000 krokov", OBJECTS, 1600, 10.0),
    ],
)
def test_recording_meets_budget(name: str, template: str, n: int, budget: float) -> None:
    trace, seconds = measure(template.format(n=n))
    size = len(json.dumps(trace)) / 1024 / 1024
    print(f"\n{name}: {trace['step_count']} krokov, {seconds:.2f} s, JSON {size:.1f} MB")
    assert trace["status"] == "ok"
    assert seconds < budget  # NFR-01
