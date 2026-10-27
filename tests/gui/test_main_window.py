from typing import cast

from PySide6.QtCore import QCoreApplication
from PySide6.QtGui import QAction, QKeySequence
from pytestqt.qtbot import QtBot

from krok.frontend.console import Console
from krok.frontend.editor import CodeEditor
from krok.frontend.i18n import LanguageSwitcher
from krok.frontend.main_window import MainWindow


def make_window(qtbot: QtBot, languages: LanguageSwitcher) -> MainWindow:
    window = MainWindow(languages)
    qtbot.addWidget(window)
    window.show()
    return window


def menu_titles(window: MainWindow) -> list[str]:
    # LanguageChange čaká vo fronte udalostí, texty v okne sa zmenia až po ich spracovaní.
    QCoreApplication.processEvents()
    return [action.text() for action in window.menuBar().actions()]


def find_action(window: MainWindow, matches: object) -> QAction:
    # Stub PySide6 6.8 nemá findChildren generický, typ treba doplniť ručne.
    actions = cast(list[QAction], window.findChildren(QAction))
    return next(a for a in actions if a.data() == matches or a.shortcut() == matches)


def test_window_opens(qtbot: QtBot, languages: LanguageSwitcher) -> None:
    window = make_window(qtbot, languages)
    assert window.windowTitle() == "Krok"
    assert menu_titles(window) == ["&File", "&View", "&Run"]


def test_language_change_retranslates_open_window(
    qtbot: QtBot, languages: LanguageSwitcher
) -> None:
    window = make_window(qtbot, languages)
    languages.set_language("sk")
    assert menu_titles(window) == ["&Súbor", "&Zobraziť", "S&pustenie"]
    assert find_action(window, "sk").isChecked()
    languages.set_language("en")
    assert menu_titles(window) == ["&File", "&View", "&Run"]
    assert find_action(window, "en").isChecked()


def test_language_menu_switches_language(qtbot: QtBot, languages: LanguageSwitcher) -> None:
    window = make_window(qtbot, languages)
    find_action(window, "sk").trigger()
    assert languages.language == "sk"
    assert menu_titles(window) == ["&Súbor", "&Zobraziť", "S&pustenie"]


def test_f5_runs_program_and_shows_output(qtbot: QtBot, languages: LanguageSwitcher) -> None:
    window = make_window(qtbot, languages)
    cast(CodeEditor, window.findChild(CodeEditor)).setPlainText('print("Ahoj")')
    console = cast(Console, window.findChild(Console))
    find_action(window, QKeySequence("F5")).trigger()
    qtbot.waitUntil(
        lambda: console.isReadOnly() and "Ahoj" in console.toPlainText(), timeout=10_000
    )
    assert console.toPlainText() == "Ahoj\nProgram finished."
