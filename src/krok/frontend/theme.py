"""Písmo a farby editora a konzoly."""

from PySide6.QtGui import QColor, QFont, QGuiApplication, QPalette, QTextCharFormat

# Farby textu majú kontrast aspoň 4,5 : 1 voči pozadiu aj voči zvýraznenému riadku (NFR-14).
_LIGHT = {
    "keyword": "#0033b3",
    "builtin": "#7a3e9d",
    "string": "#067d17",
    "number": "#1750eb",
    "comment": "#5c6670",
    "definition": "#00627a",
    "error": "#c62828",
    "input": "#2e7d32",
    "info": "#5c6670",
    "line_number": "#57606a",
    "gutter": "#f6f8fa",
    "current_line": "#f2f5fa",
}
_DARK = {
    "keyword": "#79b8ff",
    "builtin": "#d7a2d2",
    "string": "#d7a184",
    "number": "#b5cea8",
    "comment": "#8fbc7a",
    "definition": "#dcdcaa",
    "error": "#f48771",
    "input": "#89d185",
    "info": "#9e9e9e",
    "line_number": "#9e9e9e",
    "gutter": "#262626",
    "current_line": "#383838",
}


def code_font() -> QFont:
    font = QFont()
    # Použije sa prvé dostupné písmo; ak nie je žiadne, systémové neproporcionálne.
    font.setFamilies(["Cascadia Mono", "Consolas", "Menlo", "DejaVu Sans Mono"])
    font.setStyleHint(QFont.StyleHint.Monospace)
    font.setPointSize(11)
    return font


def colors() -> dict[str, QColor]:
    base = QGuiApplication.palette().color(QPalette.ColorRole.Base)
    scheme = _DARK if base.lightness() < 128 else _LIGHT
    return {name: QColor(value) for name, value in scheme.items()}


def text_format(color: QColor, *, bold: bool = False, italic: bool = False) -> QTextCharFormat:
    result = QTextCharFormat()
    result.setForeground(color)
    if bold:
        result.setFontWeight(QFont.Weight.Bold)
    result.setFontItalic(italic)
    return result
