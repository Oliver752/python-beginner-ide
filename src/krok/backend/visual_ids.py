"""Trvalé čísla objektov: dve premenné s tým istým objektom ukazujú na jeden box."""

from typing import Any


class VisualIds:
    """Prideľuje objektom rastúce čísla, ktoré sa nikdy nepoužijú znova.

    CPython adresu uvoľneného objektu použije znova, preto sa na každý očíslovaný objekt
    drží silný odkaz. Počas záznamu sa tak pamäť neuvoľňuje a metódy __del__ sa nevykonajú.
    """

    def __init__(self) -> None:
        self._numbers: dict[int, int] = {}
        self._alive: list[Any] = []

    def number(self, obj: Any) -> int:
        key = id(obj)
        number = self._numbers.get(key)
        if number is None:
            self._alive.append(obj)
            number = self._numbers[key] = len(self._alive)
        return number
