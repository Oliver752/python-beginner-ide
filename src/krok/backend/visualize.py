"""Beh na vizualizáciu: program beží pod tracerom a výsledkom je jedna stopa."""

import io
import os
import queue
import sys
import threading
import time
from typing import Any, TextIO

from krok.backend.budget import Budget
from krok.backend.channel import Channel, InputStream
from krok.backend.excinfo import final_exception, format_error
from krok.backend.runner import exit_code, prepare_program
from krok.backend.tracer import Tracer
from krok.common.trace import SCHEMA_VERSION, Limits

# Po zastavení má program čas na bloky finally. Kto zastavenie zachytí, dlhšie nebeží.
GRACE_SECONDS = 1.0


class OutputLog:
    """Výstup programu v poradí, v akom vznikol. Krok si pamätá len dosiahnuté dĺžky."""

    def __init__(self) -> None:
        self.inputs: list[str] = []
        self.stdout_len = 0
        self.stderr_len = 0
        # Kusy sa spoja až na konci, spájanie po každom print by bolo kvadratické.
        self._parts: list[tuple[str, list[str]]] = []

    def add(self, stream: str, text: str) -> None:
        if stream == "stdout":
            self.stdout_len += len(text)
        else:
            self.stderr_len += len(text)
        if not self._parts or self._parts[-1][0] != stream:
            self._parts.append((stream, []))
        self._parts[-1][1].append(text)

    def add_input(self, line: str) -> None:
        # Text zadaný študentom patrí do konzoly tam, kde ho zadal.
        self.inputs.append(line.removesuffix("\n"))
        self.add("stdout", line)

    def chunks(self) -> list[list[str]]:
        return [[stream, "".join(parts)] for stream, parts in self._parts]


class RecordingStream(io.TextIOBase):
    """Text ide do konzoly okamžite (kvôli input()) a zároveň do záznamu."""

    def __init__(self, target: TextIO, name: str, log: OutputLog) -> None:
        super().__init__()
        self._target = target
        self._name = name
        self._log = log

    def writable(self) -> bool:
        return True

    def write(self, text: str) -> int:
        self._log.add(self._name, text)
        self._target.write(text)
        return len(text)

    def flush(self) -> None:
        self._target.flush()


class RecordedInput(InputStream):
    """input() počas záznamu: riadky sú súčasťou stopy a čakanie sa nepočíta do limitu."""

    def __init__(self, lines: "queue.Queue[str | None]", log: OutputLog, budget: Budget) -> None:
        super().__init__(lines)
        self._log = log
        self._budget = budget

    def readline(self, size: int = -1, /) -> str:  # type: ignore[override]  # ako v typeshed
        started = time.monotonic()
        try:
            line = super().readline(size)
        finally:
            self._budget.exclude(time.monotonic() - started)
        self._log.add_input(line)
        return line


class Visualization:
    def __init__(
        self,
        source: str,
        path: str,
        channel: Channel,
        inputs: "queue.Queue[str | None]",
        stop: threading.Event,
        limits: Limits,
    ) -> None:
        self._source = source
        self._path = path
        self._channel = channel
        self._inputs = inputs
        self._stop = stop
        self._budget = Budget(limits)
        self._log = OutputLog()
        self._tracer = Tracer(path, source, self._budget, self._log, stop)
        self._delivery = threading.Lock()
        self._delivered = False

    def run(self) -> int:
        threading.Thread(target=self._guard, name="TraceGuard", daemon=True).start()
        saved = sys.stdin, sys.stdout, sys.stderr, sys.argv
        sys.stdin = RecordedInput(self._inputs, self._log, self._budget)
        sys.stdout = RecordingStream(sys.stdout, "stdout", self._log)
        sys.stderr = RecordingStream(sys.stderr, "stderr", self._log)
        prepare_program(self._source, self._path)
        try:
            status, code, final = self._execute()
        finally:
            sys.stdin, sys.stdout, sys.stderr, sys.argv = saved
        self._deliver(status, final)
        self._stop.set()  # strážca už nemá na čo čakať
        return code

    def _execute(self) -> tuple[str, int, dict[str, Any] | None]:
        """Vykoná program a vráti stav stopy, návratový kód a výnimku, ktorá ho ukončila."""
        lines = self._source.split("\n")
        try:
            code = compile(self._source, self._path, "exec", dont_inherit=True)
            self._tracer.record_program(code, {"__name__": "__main__"})
        except SystemExit as request:
            return self._tracer.status, exit_code(request.code), None
        except BaseException as error:
            if self._stop.is_set():
                return self._interrupted_status(), 1, None
            print(format_error(error), end="", file=sys.stderr)
            return "exception", 1, final_exception(error, self._path, lines)
        return self._tracer.status, 0, None

    def _interrupted_status(self) -> str:
        return "interrupted" if self._tracer.status == "ok" else self._tracer.status

    def _guard(self) -> None:
        """Dodá čiastočnú stopu, aj keď program po zastavení nekončí.

        Výnimku z trasovacej funkcie môže zachytiť holý except a program by bežal ďalej
        bez dohľadu. Rovnako sa z dlhého time.sleep() nevráti k ďalšej udalosti.
        """
        self._stop.wait()
        time.sleep(GRACE_SECONDS)
        self._tracer.complete = False
        if self._deliver(self._interrupted_status(), None):
            os._exit(1)

    def _deliver(self, status: str, final: dict[str, Any] | None) -> bool:
        with self._delivery:
            if self._delivered:
                return False
            self._delivered = True
            self._channel.send({"event": "trace", "trace": self._trace(status, final)})
            return True

    def _trace(self, status: str, final: dict[str, Any] | None) -> dict[str, Any]:
        steps = self._tracer.steps
        if steps:
            # Posledný krok ukazuje celý výstup vrátane tracebacku a blokov finally.
            steps[-1]["stdout_len"] = self._log.stdout_len
            steps[-1]["stderr_len"] = self._log.stderr_len
        if status == "backend_error":
            final = {"type": "backend_error", "message": self._tracer.error}
        return {
            "schema_version": SCHEMA_VERSION,
            "heap_mode": "full",
            "status": status,
            "step_count": len(steps),
            "truncated": not self._tracer.complete,
            "duration_ms": self._budget.elapsed_ms(),
            "final_exception": final,
            "output": self._log.chunks(),
            "inputs": self._log.inputs,
            "steps": steps,
        }
