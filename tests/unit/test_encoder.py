import math
from collections import Counter, deque
from typing import Any

import pytest

from krok.backend.encoder import MAX_BOXES, MAX_DEPTH, MAX_TEXT, Snapshot
from krok.backend.safe_repr import safe_repr
from krok.backend.visual_ids import VisualIds


def encode(*values: Any) -> tuple[list[Any], dict[str, Any]]:
    snapshot = Snapshot(VisualIds(), {})
    encoded = [snapshot.value(value) for value in values]
    return encoded, snapshot.heap()


@pytest.mark.parametrize(
    ("value", "expected"),
    [
        (None, ["none"]),
        (True, ["bool", True]),
        (1, ["int", 1]),
        (1.0, ["float", 1.0]),
        (math.nan, ["float", "nan"]),
        (-math.inf, ["float", "-inf"]),
        ("ľ", ["str", "ľ"]),
        ("x" * (MAX_TEXT + 5), ["str", "x" * MAX_TEXT, {"len": MAX_TEXT + 5, "shown": MAX_TEXT}]),
    ],
)
def test_values_are_tagged(value: Any, expected: list[Any]) -> None:
    assert encode(value)[0] == [expected]


def test_big_numbers_are_shortened_and_never_break_json() -> None:
    tag, text, size = encode(10**300)[0][0]
    assert (tag, text) == ("int", "1" + "0" * (MAX_TEXT - 1))
    assert size == {"len": 301, "shown": MAX_TEXT}
    # Nad sys.get_int_max_str_digits() by str() aj json.dumps() zlyhali.
    assert encode(10**5000)[0][0] == ["int", "", {"len": 5001, "shown": 0}]


def test_visual_id_survives_object_death() -> None:
    ids = VisualIds()
    numbers = {ids.number([]) for _ in range(1000)}  # bez keepalive by sa adresy opakovali
    assert len(numbers) == 1000


def test_unchanged_box_shares_memory_between_steps() -> None:
    ids = VisualIds()
    known: dict[str, Any] = {}
    data = [1]

    def step() -> dict[str, Any]:
        snapshot = Snapshot(ids, known)
        snapshot.value(data)
        return snapshot.heap()

    first, second = step(), step()
    assert first["1"] is second["1"]
    data.append(2)
    assert step()["1"]["items"] == [["int", 1], ["int", 2]]  # zmena sa nesmie stratiť
    assert first["1"]["items"] == [["int", 1]]  # staršie kroky ostávajú, ako boli


def test_depth_limit_leaves_resolvable_stub_and_prefers_shallow_path() -> None:
    leaf = [1]
    deep: list[Any] = [leaf]
    for _ in range(MAX_DEPTH + 2):
        deep = [deep]
    (deep_ref, leaf_ref), heap = encode(deep, leaf)
    assert heap[str(leaf_ref[1])]["items"] == [["int", 1]]  # plytká cesta vyhrá

    box = heap[str(deep_ref[1])]
    for _ in range(MAX_DEPTH - 1):
        box = heap[str(box["items"][0][1])]
    stub = heap[str(box["items"][0][1])]
    assert (stub["len"], stub["shown"], stub["items"]) == (1, 0, [])


def test_box_count_is_limited() -> None:
    _, heap = encode(*[[0] for _ in range(MAX_BOXES * 2)])
    assert len(heap) == MAX_BOXES * 2  # odkaz musí zostať platný
    assert sum(1 for box in heap.values() if box["shown"]) == MAX_BOXES


class Hostile:
    """Objekt z programu, ktorý zhodí každého, kto sa ho nesprávne dotkne."""

    def __init__(self) -> None:
        self.value = 1

    def __repr__(self) -> str:
        raise AssertionError("__repr__ programu sa nesmie volať")

    def __getattr__(self, name: str) -> Any:
        raise AssertionError("__getattr__ programu sa nesmie volať")

    def __iter__(self) -> Any:
        raise AssertionError("__iter__ programu sa nesmie volať")


class HostileList(list[int]):
    __repr__ = Hostile.__repr__
    __iter__ = Hostile.__iter__


class HostileMeta(type):
    def __getattribute__(cls, name: str) -> Any:
        raise RuntimeError(name)


class WithHostileMeta(metaclass=HostileMeta):
    pass


def test_strange_object_spoils_only_its_own_box() -> None:
    (strange, plain), heap = encode(WithHostileMeta, [1])
    assert heap[str(strange[1])]["class"] == "HostileMeta"
    assert heap[str(plain[1])]["items"] == [["int", 1]]


def test_code_from_program_is_never_called() -> None:
    (instance, sequence), heap = encode(Hostile(), HostileList([1]))
    assert heap[str(instance[1])] == {
        "type": "instance",
        "class": "Hostile",
        "len": 1,
        "shown": 1,
        "items": [["value", ["int", 1]]],
    }
    assert heap[str(sequence[1])]["class"] == "HostileList"
    assert heap[str(sequence[1])]["items"] == [["int", 1]]


def test_library_types_keep_their_shape() -> None:
    (counter, queue, numbers), heap = encode(Counter("aa"), deque([1]), range(3))
    assert heap[str(counter[1])]["class"] == "Counter"
    assert heap[str(counter[1])]["items"] == [[["str", "a"], ["int", 2]]]
    assert heap[str(queue[1])]["type"] == "deque"
    assert heap[str(numbers[1])]["value"] == ["str", "range(0, 3)"]


def test_safe_repr_survives_failure_and_hides_address() -> None:
    assert safe_repr(ValueError("x")) == "ValueError('x')"
    assert safe_repr(object()) == "<object object>"
    assert safe_repr(Hostile()) == "<Hostile>"
