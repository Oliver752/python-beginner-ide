from collections.abc import Iterator

import pytest
from PySide6.QtWidgets import QApplication

from krok.frontend.i18n import SOURCE_LANGUAGE, LanguageSwitcher


@pytest.fixture
def languages(qapp: QApplication) -> Iterator[LanguageSwitcher]:
    switcher = LanguageSwitcher()
    yield switcher
    # QApplication je spoločná pre všetky testy, prekladače v nej nesmú zostať.
    switcher.set_language(SOURCE_LANGUAGE)
