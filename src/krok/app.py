"""Spustenie grafickej aplikácie."""

import sys

from PySide6.QtWidgets import QApplication

from krok import __version__
from krok.frontend.i18n import DEFAULT_LANGUAGE, LanguageSwitcher
from krok.frontend.main_window import MainWindow


def main() -> int:
    app = QApplication(sys.argv)
    app.setApplicationName("Krok")
    app.setApplicationVersion(__version__)

    languages = LanguageSwitcher()
    languages.set_language(DEFAULT_LANGUAGE)

    window = MainWindow(languages)
    window.show()
    return app.exec()
