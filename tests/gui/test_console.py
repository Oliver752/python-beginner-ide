from PySide6.QtCore import Qt
from pytestqt.qtbot import QtBot

from krok.frontend.console import Console


def test_typed_input_stays_after_program_output(qtbot: QtBot) -> None:
    console = Console()
    qtbot.addWidget(console)
    console.start_session()
    qtbot.keyClicks(console, "Jan")  # používateľ píše skôr, ako sa objaví výzva
    console.append_output("stdout", "Meno: ")
    with qtbot.waitSignal(console.input_submitted) as submitted:
        qtbot.keyClick(console, Qt.Key.Key_Return)
    assert submitted.args == ["Jan"]

    qtbot.keyClick(console, Qt.Key.Key_Backspace)  # výstup programu sa zmazať nedá
    assert console.toPlainText() == "Meno: Jan\n"
