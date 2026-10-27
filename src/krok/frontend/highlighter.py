"""Zvýrazňovanie syntaxe Pythonu."""

import builtins
import keyword
import re

from PySide6.QtGui import QSyntaxHighlighter, QTextDocument

from krok.frontend.theme import colors, text_format

KEYWORDS = frozenset(keyword.kwlist)
BUILTINS = frozenset(name for name in dir(builtins) if not name.startswith("_")) - KEYWORDS

_PREFIX = r"(?:[rRbBuUfF]|[rR][bBfF]|[bBfF][rR])?"
_TOKENS = re.compile(
    r"(?P<comment>#.*)"
    rf"|(?P<triple>{_PREFIX}(?:'''|\"\"\"))"
    rf"|(?P<string>{_PREFIX}(?:'(?:\\.|[^'\\])*'?|\"(?:\\.|[^\"\\])*\"?))"
    r"|(?P<number>\b(?:0[xX][\da-fA-F_]+|0[oO][0-7_]+|0[bB][01_]+"
    r"|\d[\d_]*(?:\.[\d_]*)?(?:[eE][+-]?\d+)?[jJ]?)|\.\d[\d_]*(?:[eE][+-]?\d+)?[jJ]?)"
    r"|(?P<name>[^\W\d]\w*)"
)
# Qt počíta pozície v UTF-16, kde znak mimo BMP (napr. emoji) zaberá dve miesta.
_ASTRAL = re.compile("[\U00010000-\U0010ffff]")

# Stav bloku hovorí, ktorými úvodzovkami otvorený reťazec pokračuje na ďalší riadok.
_STATE_OF_QUOTE = {"'''": 1, '"""': 2}
_QUOTE_OF_STATE = {1: "'''", 2: '"""'}


class PythonHighlighter(QSyntaxHighlighter):
    def __init__(self, document: QTextDocument) -> None:
        super().__init__(document)
        palette = colors()
        self._formats = {
            kind: text_format(palette[kind], bold=kind == "keyword")
            for kind in ("keyword", "builtin", "string", "number", "comment", "definition")
        }

    def highlightBlock(self, text: str) -> None:
        text = _ASTRAL.sub("\ufffd\ufffd", text)
        position = 0
        state = self.previousBlockState()
        if state in _QUOTE_OF_STATE:
            close = text.find(_QUOTE_OF_STATE[state])
            if close < 0:
                self.setFormat(0, len(text), self._formats["string"])
                self.setCurrentBlockState(state)
                return
            position = close + 3
            self.setFormat(0, position, self._formats["string"])
        self.setCurrentBlockState(0)

        after_def = False
        while (match := _TOKENS.search(text, position)) is not None:
            kind = match.lastgroup
            start, position = match.span()
            word = match.group() if kind == "name" else ""
            if kind == "triple":
                quote = match.group()[-3:]
                close = text.find(quote, position)
                if close < 0:
                    self.setFormat(start, len(text) - start, self._formats["string"])
                    self.setCurrentBlockState(_STATE_OF_QUOTE[quote])
                    return
                position = close + 3
                kind = "string"
            elif kind == "name":
                kind = _classify(word, after_def)
            after_def = word in ("def", "class")
            if kind is not None:
                self.setFormat(start, position - start, self._formats[kind])


def _classify(word: str, after_def: bool) -> str | None:
    if after_def:
        return "definition"
    if word in KEYWORDS:
        return "keyword"
    if word in BUILTINS:
        return "builtin"
    return None
