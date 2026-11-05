"""Kódovanie hodnôt programu do modelu stopy.

Každá hodnota je pole so značkou typu, napríklad ["int", 42], ["float", "nan"] alebo
["ref", 12]: JSON nerozlišuje 1 a 1.0 a nepozná NaN ani Infinity. Skrátenie vyjadruje
dvojica len (skutočná veľkosť) a shown (zobrazená), nikdy zástupný prvok v zozname.
"""

import inspect
import math
import sys
from collections import deque
from itertools import islice
from types import FunctionType, MethodType, ModuleType, NoneType
from typing import Any

from krok.backend.safe_repr import class_name, safe_repr
from krok.backend.visual_ids import VisualIds

Value = list[Any]
Box = dict[str, Any]

MAX_ITEMS = 100
MAX_TEXT = 200
MAX_DEPTH = 6
# Vnorené zoznamy 100 x 100 x 100 by inak v každom kroku znamenali milión hodnôt.
MAX_BOXES = 500

_COLLECTIONS: dict[str, Any] = {
    base.__name__: base for base in (list, tuple, deque, set, frozenset, dict)
}
_KINDS: dict[type, str] = {}
_BIG_INT = 10**MAX_TEXT
_DIGITS_PER_BIT = math.log10(2)


def _encode_int(value: int) -> Value:
    if -_BIG_INT < value < _BIG_INT:
        return ["int", value]
    try:
        text = str(value)
    except ValueError:  # viac číslic, než dovolí sys.get_int_max_str_digits()
        return ["int", "", {"len": int(value.bit_length() * _DIGITS_PER_BIT) + 1, "shown": 0}]
    return ["int", text[:MAX_TEXT], {"len": len(text), "shown": MAX_TEXT}]


def _encode_float(value: float) -> Value:
    return ["float", value if math.isfinite(value) else str(value)]


def _encode_str(value: str) -> Value:
    if len(value) <= MAX_TEXT:
        return ["str", value]
    return ["str", value[:MAX_TEXT], {"len": len(value), "shown": MAX_TEXT}]


def _encode_none(_: None) -> Value:
    return ["none"]


def _encode_bool(value: bool) -> Value:
    return ["bool", value]


_PRIMITIVES: dict[type, Any] = {
    NoneType: _encode_none,
    bool: _encode_bool,
    int: _encode_int,
    float: _encode_float,
    str: _encode_str,
}


def is_hidden(name: str, value: Any) -> bool:
    """Mená, ktoré si študent nevytvoril: __name__, __class__ a parameter .0 generátora.

    Vlastné metódy ako __init__ zostávajú, tie patria k tomu, čo sa učí.
    """
    if not isinstance(name, str) or name.startswith("."):  # globals()[1] = 2 je povolené
        return True
    return name.startswith("__") and name.endswith("__") and not isinstance(value, FunctionType)


def _in_stdlib(module: str | None) -> bool:
    return (module or "").partition(".")[0] in sys.stdlib_module_names


def _shows_attributes(cls: type) -> bool:
    """Objekty tried z programu ukazujeme po atribútoch.

    Ich __repr__ sa nevolá vôbec: môže spadnúť, zacykliť sa alebo niečo vypísať (NFR-08)
    a zdedený object.__repr__ by ukázal len adresu.
    """
    method: Any = cls.__repr__
    if method is object.__repr__:
        return True
    return isinstance(method, FunctionType) and not _in_stdlib(method.__module__)


def _find_kind(cls: type) -> str:
    for name, base in _COLLECTIONS.items():
        if issubclass(cls, base):
            return name
    if issubclass(cls, type):
        return "class"
    if cls in (FunctionType, MethodType):
        return "function"
    if issubclass(cls, ModuleType):
        return "module"
    return "instance" if _shows_attributes(cls) else "object"


def _instance_attributes(obj: Any) -> dict[Any, Any]:
    # Priame čítanie obíde __getattribute__ a __getattr__ z programu.
    try:
        attributes = object.__getattribute__(obj, "__dict__")
    except Exception:  # bez __dict__ alebo vlastná vlastnosť s týmto menom
        return {}
    return attributes if isinstance(attributes, dict) else {}


def _class_attributes(cls: type) -> dict[str, Any]:
    if _in_stdlib(cls.__module__):
        return {}
    names = type.__getattribute__(cls, "__dict__")
    return {name: value for name, value in names.items() if not is_hidden(name, value)}


def _function_box(obj: Any) -> Box:
    function = obj.__func__ if isinstance(obj, MethodType) else obj
    if not isinstance(function, FunctionType):
        return {"type": "function", "name": type(function).__name__, "params": [], "line": None}
    code = function.__code__
    count = code.co_argcount + code.co_kwonlyargcount
    count += bool(code.co_flags & inspect.CO_VARARGS)
    count += bool(code.co_flags & inspect.CO_VARKEYWORDS)
    return {
        "type": "function",
        "name": function.__name__,
        "params": list(code.co_varnames[:count]),
        "line": code.co_firstlineno,
    }


class Snapshot:
    """Halda jedného kroku: len objekty dosiahnuteľné z hodnôt zakódovaných cez value().

    Nezmenený box zdieľa pamäť s predchádzajúcimi krokmi cez slovník known. Matica 50 x 50
    tak pri 2 000 krokoch zaberie jednotky MB namiesto stoviek.
    """

    def __init__(self, ids: VisualIds, known: dict[str, Box]) -> None:
        self._ids = ids
        self._known = known
        self._seen: set[int] = set()
        # Do šírky: objekt dostupný aj plytšou cestou sa nesmie skrátiť kvôli hlbšej.
        self._pending: deque[tuple[int, Any, int]] = deque()

    def value(self, obj: Any, depth: int = 1) -> Value:
        encode = _PRIMITIVES.get(type(obj))
        if encode is not None:
            return encode(obj)  # type: ignore[no-any-return]
        number = self._ids.number(obj)
        if number not in self._seen:
            self._seen.add(number)
            self._pending.append((number, obj, depth))
        return ["ref", number]

    def heap(self) -> dict[str, Box]:
        boxes: dict[str, Box] = {}
        while self._pending:
            number, obj, depth = self._pending.popleft()
            limit = MAX_ITEMS if depth <= MAX_DEPTH and len(boxes) < MAX_BOXES else 0
            try:
                box = self._box(obj, depth + 1, limit)
            except Exception:  # čudný objekt z programu pokazí len svoj box, nie celú stopu
                box = {"type": "object", "class": class_name(obj), "value": ["str", "?"]}
            key = str(number)
            known = self._known.get(key)
            if known == box:
                box = known
            else:
                self._known[key] = box
            boxes[key] = box
        return boxes

    def _box(self, obj: Any, depth: int, limit: int) -> Box:
        cls = type(obj)
        kind = _KINDS.get(cls) or _KINDS.setdefault(cls, _find_kind(cls))
        if kind == "dict":
            box = self._pairs(dict.items(obj), dict.__len__(obj), depth, limit, encode_keys=True)
        elif kind in _COLLECTIONS:
            base = _COLLECTIONS[kind]
            items = list(islice(base.__iter__(obj), limit))
            box = {
                "len": base.__len__(obj),
                "shown": len(items),
                "items": [self.value(item, depth) for item in items],
            }
        elif kind == "instance":
            attributes = _instance_attributes(obj)
            box = self._pairs(attributes.items(), len(attributes), depth, limit)
            return {"type": "instance", "class": cls.__name__, **box}
        elif kind == "class":
            attributes = _class_attributes(obj)
            box = self._pairs(attributes.items(), len(attributes), depth, limit)
            bases = [base.__name__ for base in obj.__bases__ if base is not object]
            return {"type": "class", "name": obj.__name__, "bases": bases, **box}
        elif kind == "function":
            return _function_box(obj)
        elif kind == "module":
            return {"type": "module", "name": obj.__name__}
        else:
            return {"type": "object", "class": cls.__name__, "value": _encode_str(safe_repr(obj))}
        box["type"] = kind
        if cls is not _COLLECTIONS[kind]:
            box["class"] = cls.__name__
        return box

    def _pairs(
        self, pairs: Any, size: int, depth: int, limit: int, *, encode_keys: bool = False
    ) -> Box:
        items = [
            [self.value(key, depth) if encode_keys else str(key), self.value(value, depth)]
            for key, value in list(islice(pairs, limit))
        ]
        return {"len": size, "shown": len(items), "items": items}
