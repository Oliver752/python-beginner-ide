"""Most medzi klientom backendu (čítacie vlákna) a widgetmi (hlavné vlákno Qt)."""

from PySide6.QtCore import QObject, QTimer, Signal

from krok.services.backend_client import BackendClient, Exited, Output


class ProgramRunner(QObject):
    output = Signal(str, str)  # prúd ("stdout" alebo "stderr"), text
    finished = Signal(str)  # "finished", "failed" alebo "stopped"

    def __init__(self, parent: QObject | None = None) -> None:
        super().__init__(parent)
        self._client: BackendClient | None = None
        # Udalosti z vlákien preberá časovač, widgetov sa smie dotýkať len hlavné vlákno.
        self._timer = QTimer(self)
        self._timer.setInterval(16)
        self._timer.timeout.connect(self._drain)

    def run(self, source: str, path: str) -> None:
        if self._client is not None:
            self._client.stop()
        self._client = BackendClient()
        self._client.start(source, path)
        self._timer.start()

    def send_input(self, text: str) -> None:
        if self._client is not None:
            self._client.send_input(text)

    def stop(self) -> None:
        if self._client is not None:
            self._client.stop()
            self._finish("stopped")

    def _drain(self) -> None:
        if self._client is None:
            return
        for event in self._client.poll():
            match event:
                case Output(stream, text):
                    self.output.emit(stream, text)
                case Exited(returncode):
                    self._finish("finished" if returncode == 0 else "failed")

    def _finish(self, outcome: str) -> None:
        self._client = None
        self._timer.stop()
        self.finished.emit(outcome)
