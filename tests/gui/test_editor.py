from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from krok.frontend.editor import CodeEditor


def make_editor(qtbot: QtBot) -> CodeEditor:
    editor = CodeEditor()
    qtbot.addWidget(editor)
    return editor


def test_enter_keeps_and_adjusts_indentation(qtbot: QtBot) -> None:
    editor = make_editor(qtbot)
    # QTest.keyClicks v PySide6 6.8 zhodí proces pri znaku mimo ASCII, preto bez diakritiky.
    for line in ["for i in range(3):", "if i:  # kontrola", "break"]:
        qtbot.keyClicks(editor, line)
        qtbot.keyClick(editor, Qt.Key.Key_Return)
    qtbot.keyClicks(editor, "print(i)")
    assert editor.toPlainText() == (
        "for i in range(3):\n    if i:  # kontrola\n        break\n    print(i)"
    )


def test_tab_and_backspace_work_in_steps_of_four_spaces(qtbot: QtBot) -> None:
    editor = make_editor(qtbot)
    qtbot.keyClick(editor, Qt.Key.Key_Tab)
    qtbot.keyClick(editor, Qt.Key.Key_Tab)
    qtbot.keyClick(editor, Qt.Key.Key_Backspace)
    assert editor.toPlainText() == " " * 4

    editor.setPlainText("a\nb")
    editor.selectAll()
    qtbot.keyClick(editor, Qt.Key.Key_Tab)
    assert editor.toPlainText() == "    a\n    b"
    qtbot.keyClick(editor, Qt.Key.Key_Backtab)
    assert editor.toPlainText() == "a\nb"
