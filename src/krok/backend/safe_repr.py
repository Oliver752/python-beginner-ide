"""repr() objektu, ktorý nesmie zhodiť záznam."""

import re
from typing import Any

# Adresa je pre študenta šum a stopa by sa pri každom behu líšila.
_ADDRESS = re.compile(r" at 0x[0-9a-fA-F]+")


def class_name(obj: Any) -> str:
    # Obyčajné type(obj).__name__ by spustilo __getattribute__ metatriedy z programu.
    name: str = type.__getattribute__(type(obj), "__name__")
    return name


def safe_repr(obj: Any) -> str:
    """Text objektu; pri chybe v jeho __repr__ len názov triedy."""
    try:
        return _ADDRESS.sub("", repr(obj))
    except Exception:
        return f"<{class_name(obj)}>"
