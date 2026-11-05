"""Zlaté stopy a invarianty modelu.

Zlatá stopa stráži konkrétny výsledok, invarianty pravidlá, ktoré platia pre každú stopu.
Keby boli spolu, každá drobná zmena by prepísala všetky súbory a nikto by ich nečítal.
"""

import json
from pathlib import Path
from typing import Any

import pytest
from tests.conftest import Trace, TraceProgram

HERE = Path(__file__).parent
PROGRAMS = sorted((HERE / "programs").glob("*.py"))
INPUTS = {"09_vstup": ["Ján", "20"]}


@pytest.fixture(params=PROGRAMS, ids=lambda path: path.stem)
def program(request: pytest.FixtureRequest) -> Path:
    path: Path = request.param
    return path


def record(program: Path, trace_program: TraceProgram) -> Trace:
    trace = trace_program(program.read_text("utf-8"), INPUTS.get(program.stem, ()))
    trace["duration_ms"] = 0
    # Podčiarknutie v tracebacku sa medzi verziami Pythonu líši, polohu stráži final_exception.
    if trace["final_exception"]:
        trace["final_exception"]["traceback"] = ""
        trace["output"] = [chunk for chunk in trace["output"] if chunk[0] != "stderr"]
        trace["steps"][-1]["stderr_len"] = 0
    return trace


def lines_of(trace: Trace) -> list[str]:
    head = {key: value for key, value in trace.items() if key != "steps"}
    return [
        json.dumps(item, ensure_ascii=False, sort_keys=True) for item in (head, *trace["steps"])
    ]


def test_matches_golden_trace(
    program: Path, trace_program: TraceProgram, request: pytest.FixtureRequest
) -> None:
    expected = HERE / "expected" / (program.stem + ".jsonl")
    lines = lines_of(record(program, trace_program))
    if request.config.getoption("--update-golden"):
        expected.write_text("\n".join(lines) + "\n", "utf-8", newline="\n")
    assert lines == expected.read_text("utf-8").splitlines()


def references(value: Any) -> list[int]:
    """Čísla objektov v hodnote alebo boxe, ľubovoľne vnorené."""
    if isinstance(value, dict):
        return [number for item in value.values() for number in references(item)]
    if isinstance(value, list):
        if len(value) == 2 and value[0] == "ref":
            return [value[1]]
        return [number for item in value for number in references(item)]
    return []


def sizes(value: Any) -> list[dict[str, Any]]:
    """Všetky dvojice len a shown vnorené v kroku."""
    found = []
    if isinstance(value, dict):
        if "shown" in value:
            found.append(value)
        for item in value.values():
            found += sizes(item)
    elif isinstance(value, list):
        for item in value:
            found += sizes(item)
    return found


def test_invariants(program: Path, trace_program: TraceProgram) -> None:
    trace = record(program, trace_program)
    assert json.loads(json.dumps(trace, allow_nan=False)) == trace  # NFR-17
    steps = trace["steps"]
    assert trace["step_count"] == len(steps)
    previous: dict[str, Any] | None = None
    for number, step in enumerate(steps):
        assert step["i"] == number
        assert step["line"] >= 1

        roots = references(step["frames"]) + references(step["retval"])
        boxes = step["heap"]
        assert all(str(ref) in boxes for ref in roots + references(boxes))
        reachable = set(map(str, roots))
        pending = list(reachable)
        while pending:
            for ref in references(boxes[pending.pop()]):
                if str(ref) not in reachable:
                    reachable.add(str(ref))
                    pending.append(str(ref))
        assert reachable == set(boxes), "na halde je objekt, na ktorý nič neukazuje"

        assert all(size["shown"] <= size["len"] for size in sizes(step))
        for frame in step["frames"]:
            assert sorted(frame["order"]) == sorted(frame["vars"])
        assert (step["retval"] is not None) == (step["event"] == "return")
        assert (step["exc"] is not None) == (step["event"] == "exception")

        if previous is not None:
            assert step["stdout_len"] >= previous["stdout_len"]
            assert step["stderr_len"] >= previous["stderr_len"]
            before = [frame["fid"] for frame in previous["frames"]]
            after = [frame["fid"] for frame in step["frames"]]
            shared = sum(1 for a, b in zip(before, after, strict=False) if a == b)
            assert len(before) - shared <= 1, "z kroku na krok ubudol viac ako jeden rámec"
            assert len(after) - shared <= 1, "z kroku na krok pribudol viac ako jeden rámec"
        previous = step
