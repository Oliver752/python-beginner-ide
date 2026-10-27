"""Jazyk rozhrania: preklady Qt Linguist a ich prepínanie za behu.

Reťazce v kóde sú anglické (``self.tr("&File")``), takže angličtina nepotrebuje súbor
.qm. Po zmene jazyka dostane každý widget udalosť ``QEvent.LanguageChange``
a texty si nastaví znova. Qt ju widgetom doručuje cez front udalostí, teda až pri
najbližšom spracovaní udalostí, nie hneď v ``set_language``.
"""

from pathlib import Path

from PySide6.QtCore import QCoreApplication, QLibraryInfo, QTranslator

TRANSLATIONS_DIR = Path(__file__).resolve().parent.parent / "translations"

SOURCE_LANGUAGE = "en"
DEFAULT_LANGUAGE = "sk"
# Názvy jazykov sa neprekladajú, každý je uvedený vo vlastnom jazyku.
LANGUAGES = {"sk": "Slovenčina", "en": "English"}


class LanguageSwitcher:
    def __init__(self) -> None:
        # Odkazy treba držať: PySide6 nepreberá vlastníctvo nainštalovaného prekladača
        # a po zbehnutí garbage collectora by preklad potichu zmizol.
        self._translators: list[QTranslator] = []
        self._language = SOURCE_LANGUAGE

    @property
    def language(self) -> str:
        return self._language

    def set_language(self, language: str) -> None:
        if language not in LANGUAGES:
            raise ValueError(f"unsupported language: {language!r}")
        # Najprv načítať: ak súbor chýba, ostane platný doterajší jazyk.
        translators = self._load(language)
        self._language = language
        for translator in self._translators:
            QCoreApplication.removeTranslator(translator)
        for translator in translators:
            QCoreApplication.installTranslator(translator)
        self._translators = translators

    @staticmethod
    def _load(language: str) -> list[QTranslator]:
        if language == SOURCE_LANGUAGE:
            return []
        own = QTranslator()
        if not own.load(f"krok_{language}", str(TRANSLATIONS_DIR)):
            raise FileNotFoundError(TRANSLATIONS_DIR / f"krok_{language}.qm")
        translators = [own]
        # Preklady samotného Qt: štandardné tlačidlá dialógov, kontextové menu editora.
        # Nie sú nevyhnutné, preto ich chýbanie nevadí.
        qt = QTranslator()
        qt_dir = QLibraryInfo.path(QLibraryInfo.LibraryPath.TranslationsPath)
        if qt.load(f"qtbase_{language}", qt_dir):
            translators.append(qt)
        return translators
