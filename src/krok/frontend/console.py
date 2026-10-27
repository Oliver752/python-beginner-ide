"""Konzola: výstup bežiaceho programu a vstup pre input()."""

from PySide6.QtCore import QMimeData, Qt, Signal
from PySide6.QtGui import QContextMenuEvent, QKeyEvent, QKeySequence, QTextCharFormat, QTextCursor
from PySide6.QtWidgets import QPlainTextEdit, QWidget

from krok.frontend.theme import code_font, colors, text_format

# Staršie riadky sa zahadzujú a príliš dlhý riadok sa skráti, inak by výpis spomalil IDE:
# Qt pri každom pripísaní nanovo rozloží celý riadok.
MAX_LINES = 5000
MAX_LINE_LENGTH = 10_000


class Console(QPlainTextEdit):
    input_submitted = Signal(str)

    def __init__(self, parent: QWidget | None = None) -> None:
        super().__init__(parent)
        self.setFont(code_font())
        self.setReadOnly(True)
        self.setUndoRedoEnabled(False)
        palette = colors()
        self._formats = {
            "stdout": QTextCharFormat(),
            "stderr": text_format(palette["error"]),
            "input": text_format(palette["input"], bold=True),
            "info": text_format(palette["info"], italic=True),
        }
        # Text pred touto pozíciou vypísal program; upravovať sa dá len vstup za ňou.
        self._input_start = 0

    def start_session(self) -> None:
        self.clear()
        self._input_start = 0
        self.setReadOnly(False)
        self.setCurrentCharFormat(self._formats["input"])

    def end_session(self, message: str) -> None:
        self.setReadOnly(True)
        cursor = QTextCursor(self.document())
        cursor.movePosition(QTextCursor.MoveOperation.End)
        if not cursor.atBlockStart():
            cursor.insertText("\n")
        cursor.insertText(message, self._formats["info"])
        self._scroll_to_end()

    def append_output(self, stream: str, text: str) -> None:
        scrollbar = self.verticalScrollBar()
        follow = scrollbar.value() == scrollbar.maximum()
        # Výstup ide pred rozpísaný vstup, takže výzva programu zostane pred ním.
        cursor = QTextCursor(self.document())
        cursor.setPosition(self._input_start)
        column = cursor.positionInBlock()
        kept = ""
        for index, line in enumerate(text.split("\n")):
            if index:
                kept += "\n"
                column = 0
            room = MAX_LINE_LENGTH - column
            if len(line) <= room:
                kept += line
                column += len(line)
                continue
            kept += line[: max(room, 0)]
            if column <= MAX_LINE_LENGTH:  # riadok ešte nemá značku skrátenia
                cursor.insertText(kept, self._formats[stream])
                cursor.insertText(self.tr(" … [line too long]"), self._formats["info"])
                kept = ""
            column = MAX_LINE_LENGTH + 1
        cursor.insertText(kept, self._formats[stream])
        self._input_start = cursor.position()
        self._drop_old_lines()
        if follow:
            self._scroll_to_end()

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if self.isReadOnly() or event.matches(QKeySequence.StandardKey.Copy):
            super().keyPressEvent(event)
            return
        if event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter):
            self._submit()
            return
        cursor = self.textCursor()
        if (
            event.key() == Qt.Key.Key_Backspace
            and not cursor.hasSelection()
            and cursor.position() <= self._input_start
        ):
            return
        if _modifies_text(event):
            if cursor.selectionStart() < self._input_start:
                self.moveCursor(QTextCursor.MoveOperation.End)
            self.setCurrentCharFormat(self._formats["input"])
        super().keyPressEvent(event)

    def insertFromMimeData(self, source: QMimeData) -> None:
        if self.textCursor().selectionStart() < self._input_start:
            self.moveCursor(QTextCursor.MoveOperation.End)
        self.setCurrentCharFormat(self._formats["input"])
        super().insertFromMimeData(source)

    def contextMenuEvent(self, event: QContextMenuEvent) -> None:
        menu = self.createStandardContextMenu(event.pos())
        if self.textCursor().selectionStart() < self._input_start:
            for action in menu.actions():
                if action.objectName() in ("edit-cut", "edit-delete"):
                    action.setEnabled(False)
        menu.exec(event.globalPos())

    def _submit(self) -> None:
        cursor = QTextCursor(self.document())
        cursor.setPosition(self._input_start)
        cursor.movePosition(QTextCursor.MoveOperation.End, QTextCursor.MoveMode.KeepAnchor)
        # Vložený text môže mať viac riadkov, program dostane každý zvlášť.
        lines = cursor.selectedText().split(" ")
        cursor.clearSelection()
        cursor.insertText("\n", self._formats["input"])
        self._input_start = cursor.position()
        self.setTextCursor(cursor)
        for line in lines:
            self.input_submitted.emit(line)

    def _drop_old_lines(self) -> None:
        excess = self.document().blockCount() - MAX_LINES
        if excess > 0:
            cursor = QTextCursor(self.document())
            cursor.movePosition(
                QTextCursor.MoveOperation.NextBlock, QTextCursor.MoveMode.KeepAnchor, excess
            )
            self._input_start -= cursor.position()
            cursor.removeSelectedText()

    def _scroll_to_end(self) -> None:
        scrollbar = self.verticalScrollBar()
        scrollbar.setValue(scrollbar.maximum())


def _modifies_text(event: QKeyEvent) -> bool:
    return (
        (bool(event.text()) and event.text().isprintable())
        or event.key() in (Qt.Key.Key_Backspace, Qt.Key.Key_Delete)
        or event.matches(QKeySequence.StandardKey.Paste)
        or event.matches(QKeySequence.StandardKey.Cut)
    )
