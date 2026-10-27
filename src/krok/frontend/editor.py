"""Editor kódu: čísla riadkov, zvýraznený aktuálny riadok, odsadzovanie po štyroch medzerách."""

import re
from typing import Any

from PySide6.QtCore import QRect, QSize, Qt
from PySide6.QtGui import (
    QKeyEvent,
    QPainter,
    QPaintEvent,
    QPalette,
    QResizeEvent,
    QTextBlock,
    QTextCursor,
    QTextFormat,
)
from PySide6.QtWidgets import QPlainTextEdit, QTextEdit, QWidget

from krok.frontend.highlighter import PythonHighlighter
from krok.frontend.theme import code_font, colors

INDENT = 4
# Po týchto príkazoch blok končí, nový riadok sa preto odsadí o úroveň menej.
_DEDENT_AFTER = re.compile(r"(return|pass|break|continue|raise)\b")


class CodeEditor(QPlainTextEdit):
    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self._colors = colors()
        self.setFont(code_font())
        self.setLineWrapMode(QPlainTextEdit.LineWrapMode.NoWrap)
        self.setTabStopDistance(self.fontMetrics().horizontalAdvance(" ") * INDENT)
        self._highlighter = PythonHighlighter(self.document())
        self._line_numbers = _LineNumberArea(self)
        self.blockCountChanged.connect(self._update_margin)
        self.updateRequest.connect(self._update_line_numbers)
        self.cursorPositionChanged.connect(self._highlight_current_line)
        self._update_margin()
        self._highlight_current_line()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        key = event.key()
        modifiers = event.modifiers() & ~Qt.KeyboardModifier.KeypadModifier
        plain = modifiers == Qt.KeyboardModifier.NoModifier
        if key in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and (
            plain or modifiers == Qt.KeyboardModifier.ShiftModifier
        ):
            self._new_line()
        elif key == Qt.Key.Key_Tab and plain:
            self._indent()
        elif key == Qt.Key.Key_Backtab:
            self._dedent()
        elif not (key == Qt.Key.Key_Backspace and plain and self._backspace_indent()):
            super().keyPressEvent(event)

    def resizeEvent(self, event: QResizeEvent) -> None:
        super().resizeEvent(event)
        area = self.contentsRect()
        self._line_numbers.setGeometry(
            QRect(area.left(), area.top(), self.line_number_width(), area.height())
        )

    def line_number_width(self) -> int:
        digits = max(len(str(self.blockCount())), 2)
        return 16 + self.fontMetrics().horizontalAdvance("9") * digits

    def paint_line_numbers(self, event: QPaintEvent) -> None:
        painter = QPainter(self._line_numbers)
        painter.fillRect(event.rect(), self._colors["gutter"])
        block = self.firstVisibleBlock()
        top = round(self.blockBoundingGeometry(block).translated(self.contentOffset()).top())
        current = self.textCursor().blockNumber()
        width = self._line_numbers.width() - 8
        height = self.fontMetrics().height()
        while block.isValid() and top <= event.rect().bottom():
            bottom = top + round(self.blockBoundingRect(block).height())
            if block.isVisible() and bottom >= event.rect().top():
                number = block.blockNumber()
                if number == current:
                    painter.setPen(self.palette().color(QPalette.ColorRole.Text))
                else:
                    painter.setPen(self._colors["line_number"])
                painter.drawText(
                    0, top, width, height, Qt.AlignmentFlag.AlignRight, str(number + 1)
                )
            block = block.next()
            top = bottom
        painter.end()

    def _update_margin(self) -> None:
        self.setViewportMargins(self.line_number_width(), 0, 0, 0)

    def _update_line_numbers(self, rect: QRect, dy: int) -> None:
        if dy:
            self._line_numbers.scroll(0, dy)
        else:
            self._line_numbers.update(0, rect.y(), self._line_numbers.width(), rect.height())

    def _highlight_current_line(self) -> None:
        # Stub PySide6 6.8 nepozná atribúty format a cursor, preto Any.
        selection: Any = QTextEdit.ExtraSelection()
        selection.format.setBackground(self._colors["current_line"])
        selection.format.setProperty(QTextFormat.Property.FullWidthSelection, True)
        selection.cursor = self.textCursor()
        selection.cursor.clearSelection()
        self.setExtraSelections([selection])
        self._line_numbers.update()

    def _new_line(self) -> None:
        cursor = self.textCursor()
        line = cursor.block().text()[: cursor.positionInBlock()]
        indent = len(line) - len(line.lstrip(" "))
        code = line.strip()
        if "#" in code and not code.endswith(":"):
            code = code[: code.rindex("#")].rstrip()  # bez komentára na konci riadku
        if code.endswith(":"):
            indent += INDENT
        elif _DEDENT_AFTER.match(code):
            indent = max(indent - INDENT, 0)
        cursor.insertText("\n" + " " * indent)
        self.setTextCursor(cursor)
        self.ensureCursorVisible()

    def _indent(self) -> None:
        cursor = self.textCursor()
        if not cursor.hasSelection():
            cursor.insertText(" " * (INDENT - cursor.positionInBlock() % INDENT))
            self.setTextCursor(cursor)
            return
        cursor.beginEditBlock()
        for block in self._selected_blocks():
            QTextCursor(block).insertText(" " * INDENT)
        cursor.endEditBlock()

    def _dedent(self) -> None:
        cursor = self.textCursor()
        cursor.beginEditBlock()
        for block in self._selected_blocks():
            spaces = len(block.text()) - len(block.text().lstrip(" "))
            line = QTextCursor(block)
            line.movePosition(
                QTextCursor.MoveOperation.Right,
                QTextCursor.MoveMode.KeepAnchor,
                min(spaces, INDENT),
            )
            line.removeSelectedText()
        cursor.endEditBlock()

    def _backspace_indent(self) -> bool:
        """Backspace v odsadení zmaže celú úroveň. Vráti, či sa uplatnil."""
        cursor = self.textCursor()
        column = cursor.positionInBlock()
        if cursor.hasSelection() or column == 0 or cursor.block().text()[:column].strip(" "):
            return False
        cursor.movePosition(
            QTextCursor.MoveOperation.Left,
            QTextCursor.MoveMode.KeepAnchor,
            (column - 1) % INDENT + 1,
        )
        cursor.removeSelectedText()
        return True

    def _selected_blocks(self) -> list[QTextBlock]:
        cursor = self.textCursor()
        first = self.document().findBlock(cursor.selectionStart())
        last = self.document().findBlock(cursor.selectionEnd())
        # Výber, ktorý končí na začiatku riadku, ten riadok nezahŕňa.
        if last != first and cursor.selectionEnd() == last.position():
            last = last.previous()
        blocks = [first]
        while blocks[-1] != last:
            blocks.append(blocks[-1].next())
        return blocks


class _LineNumberArea(QWidget):
    def __init__(self, editor: CodeEditor) -> None:
        super().__init__(editor)
        self._editor = editor

    def sizeHint(self) -> QSize:
        return QSize(self._editor.line_number_width(), 0)

    def paintEvent(self, event: QPaintEvent) -> None:
        self._editor.paint_line_numbers(event)
