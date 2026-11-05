"""Tracer a limity v tomto procese. Zastavenie cez rúry skúša integračný test."""

import sys
import threading

import pytest
from tests.conftest import TraceProgram

from krok.backend.budget import Budget
from krok.backend.tracer import MAX_FRAMES, TraceAborted, Tracer
from krok.common.trace import Limits


def test_variables_keep_order_of_creation(trace_program: TraceProgram) -> None:
    source = """\
def f(prepinac):
    if prepinac:
        b = 1
    a = 2
    b = 3
    del a
    a = 4
    return b


f(False)
"""
    returning = next(s for s in trace_program(source)["steps"] if s["event"] == "return")
    assert returning["frames"][-1]["order"] == ["prepinac", "b", "a"]


@pytest.mark.parametrize(
    "source",
    [
        "r = [x * 2\n     for x in range(3)]\n",
        "class A:\n    r = [x * 2\n         for x in range(3)]\n\n\nr = A.r\n",
    ],
    ids=["modul", "trieda"],
)
def test_recording_does_not_change_the_program(
    trace_program: TraceProgram, source: str, recwarn: pytest.WarningsRecorder
) -> None:
    # V Pythone 3.12 by f_locals premennú x prepísalo a správny program by spadol.
    trace = trace_program(source)
    assert trace["status"] == "ok"
    final = trace["steps"][-1]
    assert final["heap"][str(final["frames"][-1]["vars"]["r"][1])]["items"] == [
        ["int", 0],
        ["int", 2],
        ["int", 4],
    ]
    assert not recwarn.list


def test_key_that_is_not_a_string_in_globals_is_ignored(trace_program: TraceProgram) -> None:
    trace = trace_program("globals()[1] = 2\nx = 3\n")
    assert trace["status"] == "ok"
    assert trace["steps"][-1]["frames"][0]["order"] == ["x"]


def test_only_user_file_is_stepped(trace_program: TraceProgram) -> None:
    trace = trace_program("import random\nrandom.seed(1)\nx = random.randint(1, 6)\n")
    assert {step["path"] for step in trace["steps"]} == {"program.py"}
    assert all(len(step["frames"]) == 1 for step in trace["steps"])


def test_deep_stack_is_shortened_with_real_depth(trace_program: TraceProgram) -> None:
    source = "def f(n):\n    if n:\n        f(n - 1)\n\n\nf(30)\n"
    deepest = max(trace_program(source)["steps"], key=lambda step: step["stack_len"])
    assert deepest["stack_len"] == 32
    assert len(deepest["frames"]) == MAX_FRAMES
    assert deepest["frames"][0]["is_global"]
    assert deepest["frames"][-1]["vars"]["n"] == ["int", 0]


def test_infinite_recursion_ends_as_program_error(trace_program: TraceProgram) -> None:
    trace = trace_program("def f():\n    f()\n\n\nf()\n")
    assert trace["status"] == "exception"
    assert trace["final_exception"]["type"] == "RecursionError"
    assert trace["truncated"] is True  # trasovanie zanikne spolu s pretečením zásobníka


@pytest.mark.parametrize(
    ("source", "limits", "status"),
    [
        ("while True:\n    pass\n", Limits(steps=50), "step_limit"),
        ("while True:\n    pass\n", Limits(seconds=0.05), "time_limit"),
        (
            "x = []\nwhile True:\n    x.append(bytearray(10**6))\n",
            Limits(memory_mb=20),
            "memory_limit",
        ),
        (
            "while True:\n    try:\n        pass\n    except Exception:\n        pass\n",
            Limits(steps=10),
            "step_limit",
        ),
    ],
    ids=["kroky", "cas", "pamat", "except-exception"],
)
def test_limit_gives_partial_trace(
    trace_program: TraceProgram, source: str, limits: Limits, status: str
) -> None:
    trace = trace_program(source, limits=limits)
    assert (trace["status"], trace["truncated"]) == (status, True)
    assert trace["step_count"] > 0


def test_exit_is_a_normal_end(trace_program: TraceProgram) -> None:
    trace = trace_program("import sys\nsys.exit(3)\n")
    assert (trace["status"], trace["final_exception"]) == ("ok", None)


def test_syntax_error_has_position_and_no_steps(trace_program: TraceProgram) -> None:
    trace = trace_program("x = 1\nprint(x\n")
    assert (trace["status"], trace["step_count"]) == ("exception", 0)
    error = trace["final_exception"]
    assert error["type"] == "SyntaxError"
    assert (error["line"], error["col"]) == (2, 5)


def test_error_position_counts_characters_and_last_step_has_whole_output(
    trace_program: TraceProgram,
) -> None:
    trace = trace_program('print("a")\nž = "čšť" + 1\n')
    error = trace["final_exception"]
    assert (error["line"], error["col"], error["end_col"]) == (2, 4, 13)
    assert trace["steps"][-1]["exc"]["col"] == 4
    assert "TypeError" in error["traceback"]
    assert "krok" not in error["traceback"]
    assert trace["steps"][-1]["stderr_len"] == len(error["traceback"])


class FixedOutput:
    stdout_len = 0
    stderr_len = 0


def test_tracer_snapshots_real_frame_outside_trace_function() -> None:
    # Coverage nemeria kód volaný z trasovacej funkcie, preto tu cesta aj priamo.
    def tracer(limits: Limits) -> Tracer:
        return Tracer(__file__, "", Budget(limits), FixedOutput(), threading.Event())

    recorder = tracer(Limits())
    frame = sys._getframe()
    recorder.user_line(frame)
    recorder.user_call(frame, None)
    try:
        1 / 0  # noqa: B018
    except ZeroDivisionError:
        recorder.user_exception(frame, sys.exc_info())
    assert [step["event"] for step in recorder.steps] == ["line", "call", "exception"]
    assert recorder.steps[0]["frames"][-1]["vars"]["recorder"][0] == "ref"
    assert recorder.steps[2]["exc"]["type"] == "ZeroDivisionError"

    with pytest.raises(TraceAborted):
        tracer(Limits(steps=0)).user_line(frame)

    stopped = tracer(Limits())
    stopped._stop.set()
    with pytest.raises(KeyboardInterrupt):
        stopped.user_line(frame)
    assert stopped.status == "interrupted"
