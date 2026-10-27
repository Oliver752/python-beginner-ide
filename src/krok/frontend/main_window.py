"""Hlavné okno aplikácie."""

from PySide6.QtCore import QEvent, Qt
from PySide6.QtGui import QAction, QActionGroup, QCloseEvent, QKeySequence
from PySide6.QtWidgets import QMainWindow, QSplitter, QStyle, QToolBar

from krok.frontend.console import Console
from krok.frontend.editor import CodeEditor
from krok.frontend.i18n import LANGUAGES, LanguageSwitcher
from krok.frontend.program_runner import ProgramRunner

# Pod týmto menom uvádza traceback program, ktorý ešte nie je uložený v súbore.
UNTITLED = "<untitled>"


class MainWindow(QMainWindow):
    def __init__(self, languages: LanguageSwitcher) -> None:
        super().__init__()
        self._languages = languages
        self.setWindowTitle("Krok")
        self.resize(1000, 700)
        # Kontextové menu okna by dovolilo skryť panel nástrojov a začiatočník by ho nevrátil.
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.NoContextMenu)

        self._editor = CodeEditor()
        self._console = Console()
        splitter = QSplitter(Qt.Orientation.Vertical)
        splitter.addWidget(self._editor)
        splitter.addWidget(self._console)
        splitter.setSizes([500, 200])
        self.setCentralWidget(splitter)

        self._runner = ProgramRunner(self)
        self._runner.output.connect(self._console.append_output)
        self._runner.finished.connect(self._on_program_finished)
        self._console.input_submitted.connect(self._runner.send_input)

        self._quit_action = QAction(self)
        self._quit_action.setShortcut(QKeySequence("Ctrl+Q"))
        self._quit_action.setMenuRole(QAction.MenuRole.QuitRole)
        self._quit_action.triggered.connect(self.close)

        icons = self.style()
        self._run_action = QAction(icons.standardIcon(QStyle.StandardPixmap.SP_MediaPlay), "", self)
        self._run_action.setShortcut(QKeySequence("F5"))
        self._run_action.triggered.connect(self._run_program)
        self._stop_action = QAction(
            icons.standardIcon(QStyle.StandardPixmap.SP_MediaStop), "", self
        )
        self._stop_action.setShortcut(QKeySequence("Ctrl+F2"))
        self._stop_action.setEnabled(False)
        self._stop_action.triggered.connect(self._runner.stop)

        toolbar = QToolBar(self)
        toolbar.setObjectName("main_toolbar")
        toolbar.setMovable(False)
        toolbar.setToolButtonStyle(Qt.ToolButtonStyle.ToolButtonTextBesideIcon)
        toolbar.addActions([self._run_action, self._stop_action])
        self.addToolBar(toolbar)

        self._language_group = QActionGroup(self)
        for code, name in LANGUAGES.items():
            action = QAction(name, self)
            action.setData(code)
            action.setCheckable(True)
            self._language_group.addAction(action)
        self._language_group.triggered.connect(self._on_language_chosen)

        self._file_menu = self.menuBar().addMenu("")
        self._file_menu.addAction(self._quit_action)
        self._view_menu = self.menuBar().addMenu("")
        self._language_menu = self._view_menu.addMenu("")
        self._language_menu.addActions(self._language_group.actions())
        self._run_menu = self.menuBar().addMenu("")
        self._run_menu.addActions([self._run_action, self._stop_action])

        self._retranslate()
        self._editor.setFocus()

    def changeEvent(self, event: QEvent) -> None:
        if event.type() == QEvent.Type.LanguageChange:
            self._retranslate()
        super().changeEvent(event)

    def closeEvent(self, event: QCloseEvent) -> None:
        self._runner.stop()
        super().closeEvent(event)

    def _retranslate(self) -> None:
        self._file_menu.setTitle(self.tr("&File"))
        self._quit_action.setText(self.tr("&Quit"))
        self._view_menu.setTitle(self.tr("&View"))
        self._language_menu.setTitle(self.tr("&Language"))
        self._run_menu.setTitle(self.tr("&Run", "menu"))
        self._run_action.setText(self.tr("&Run", "action"))
        self._run_action.setToolTip(self.tr("Run the program (F5)"))
        self._stop_action.setText(self.tr("S&top"))
        self._stop_action.setToolTip(self.tr("Stop the program (Ctrl+F2)"))
        # Zaškrtnutie podľa skutočného jazyka, aj keď ho zmenilo niečo iné ako toto menu.
        for action in self._language_group.actions():
            action.setChecked(action.data() == self._languages.language)

    def _on_language_chosen(self, action: QAction) -> None:
        self._languages.set_language(action.data())

    def _run_program(self) -> None:
        self._console.start_session()
        self._runner.run(self._editor.toPlainText(), UNTITLED)
        self._stop_action.setEnabled(True)
        self._console.setFocus()

    def _on_program_finished(self, outcome: str) -> None:
        self._stop_action.setEnabled(False)
        messages = {
            "finished": self.tr("Program finished."),
            "failed": self.tr("Program ended with an error."),
            "stopped": self.tr("Program stopped."),
        }
        self._console.end_session(messages[outcome])
