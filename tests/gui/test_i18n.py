import pytest
from PySide6.QtCore import QCoreApplication

from krok.frontend.i18n import LanguageSwitcher


def test_unknown_language_is_rejected(languages: LanguageSwitcher) -> None:
    with pytest.raises(ValueError):
        languages.set_language("xx")
    assert languages.language == "en"


def test_slovak_includes_qt_own_translations(languages: LanguageSwitcher) -> None:
    languages.set_language("sk")
    assert QCoreApplication.translate("QWidgetTextControl", "&Undo") == "&Späť"
