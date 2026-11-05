"""Záznam behu programu po krokoch; každý krok je snímka zásobníka a haldy."""

import bdb
import dis
import inspect
import sys
import threading
import traceback
from types import CodeType, FrameType
from typing import Any, Protocol

from krok.backend.budget import Budget
from krok.backend.encoder import Box, Snapshot, is_hidden
from krok.backend.excinfo import code_position, summary
from krok.backend.visual_ids import VisualIds

MAX_FRAMES = 20

_RETURNS = {dis.opmap[name] for name in ("RETURN_VALUE", "RETURN_CONST", "YIELD_VALUE")}
_YIELD = dis.opmap["YIELD_VALUE"]
_NOTHING = object()


def _really_returned(frame: FrameType) -> bool:
    """Odlíši návrat od výnimky, ktorá rámec opúšťa: udalosť return príde v oboch prípadoch.

    Spoznať sa to dá len podľa inštrukcie. Podľa predchádzajúcej udalosti exception nie,
    výnimka prechádzajúca cez finally ďalšiu nemá. Python 3.13 po yield ukazuje až za neho.
    """
    code = frame.f_code.co_code
    return code[frame.f_lasti] in _RETURNS or code[frame.f_lasti - 2] == _YIELD


def _namespace(frame: FrameType) -> dict[str, Any]:
    """Premenné rámca.

    V Pythone 3.12 čítanie f_locals z trasovacej funkcie prepíše premennú comprehension
    v module a v tele triedy na None a správny program spadne. Pozorovanie nesmie meniť beh.
    """
    code = frame.f_code
    if code.co_flags & inspect.CO_OPTIMIZED:
        return frame.f_locals
    if code.co_name == "<module>":
        return frame.f_globals
    return {} if code.co_varnames else frame.f_locals


class TraceAborted(BaseException):
    """Ukončí program pri prekročení limitu. Nie je Exception, aby ju except Exception nechytil."""


class OutputCounter(Protocol):
    @property
    def stdout_len(self) -> int: ...

    @property
    def stderr_len(self) -> int: ...


class Tracer(bdb.Bdb):
    """Sleduje len rámce súboru používateľa, do štandardnej knižnice nevstupuje.

    Stav kroku je stav pred vykonaním jeho riadku. Výnimka vyvolaná z trasovacej funkcie
    trasovanie natrvalo vypne, preto po zastavení a po limite ďalšie kroky nevznikajú.
    """

    def __init__(
        self,
        path: str,
        source: str,
        budget: Budget,
        output: OutputCounter,
        stop: threading.Event,
    ) -> None:
        super().__init__()
        self.reset()
        self.steps: list[dict[str, Any]] = []
        self.status = "ok"
        self.error: str | None = None
        self.complete = True
        self._path = path
        self._lines = source.split("\n")
        self._budget = budget
        self._output = output
        self._stop = stop
        self._ids = VisualIds()
        self._boxes: dict[str, Box] = {}
        self._frame_ids: dict[FrameType, int] = {}
        self._orders: dict[int, list[str]] = {}

    def record_program(self, code: CodeType, namespace: dict[str, Any]) -> None:
        previous = sys.gettrace()
        sys.settrace(self.trace_dispatch)
        try:
            exec(code, namespace)
        finally:
            # Vypnuté trasovanie znamená, že stopa nedošla po koniec programu.
            self.complete = sys.gettrace() == self.trace_dispatch
            sys.settrace(previous)

    def stop_here(self, frame: FrameType) -> bool:
        return frame.f_code.co_filename == self._path

    def user_line(self, frame: FrameType) -> None:
        self._record(frame, "line")

    def user_call(self, frame: FrameType, argument_list: None) -> None:
        self._record(frame, "call")

    def user_return(self, frame: FrameType, return_value: Any) -> None:
        if _really_returned(frame):
            self._record(frame, "return", retval=return_value)

    def user_exception(self, frame: FrameType, exc_info: Any) -> None:
        position = code_position(frame.f_code, frame.f_lasti, self._lines)
        self._record(frame, "exception", exc={**summary(exc_info[1]), **position})

    def _record(
        self,
        frame: FrameType,
        event: str,
        retval: Any = _NOTHING,
        exc: dict[str, Any] | None = None,
    ) -> None:
        if self._stop.is_set():
            self.status = "interrupted"
            raise KeyboardInterrupt
        limit = self._budget.exceeded(len(self.steps))
        if limit is not None:
            self._abort(limit)
        try:
            self.steps.append(self._step(frame, event, retval, exc))
        except RecursionError:
            pass  # tesne pod limitom rekurzie sa snímka na zásobník nezmestí
        except Exception:
            self.error = traceback.format_exc()
            self._abort("backend_error")

    def _abort(self, status: str) -> None:
        self.status = status
        self._stop.set()
        raise TraceAborted

    def _step(
        self, frame: FrameType, event: str, retval: Any, exc: dict[str, Any] | None
    ) -> dict[str, Any]:
        stack = self._user_stack(frame)
        snapshot = Snapshot(self._ids, self._boxes)
        step: dict[str, Any] = {
            "i": len(self.steps),
            "event": event,
            "path": self._path,
            "line": frame.f_lineno,
            "col": self._indent(frame.f_lineno),
            "keyframe": True,
            "stack_len": len(stack),
            "frames": self._frames(stack, snapshot),
            "stdout_len": self._output.stdout_len,
            "stderr_len": self._output.stderr_len,
            "retval": None if retval is _NOTHING else snapshot.value(retval),
            "exc": exc,
        }
        step["heap"] = snapshot.heap()
        step["heap_removed"] = []
        return step

    def _user_stack(self, top: FrameType) -> list[FrameType]:
        stack = []
        frame: FrameType | None = top
        while frame is not None and frame is not self.botframe:
            if frame.f_code.co_filename == self._path:
                stack.append(frame)
            frame = frame.f_back
        stack.reverse()
        return stack

    def _frames(self, stack: list[FrameType], snapshot: Snapshot) -> list[dict[str, Any]]:
        shown = list(enumerate(stack))
        if len(shown) > MAX_FRAMES:
            # Študenta zaujíma, kde program práve je a odkiaľ vyšiel.
            shown = [shown[0], *shown[1 - MAX_FRAMES :]]
        return [self._frame(frame, stack[i - 1] if i else None, snapshot) for i, frame in shown]

    def _frame(
        self, frame: FrameType, caller: FrameType | None, snapshot: Snapshot
    ) -> dict[str, Any]:
        number = self._frame_ids.setdefault(frame, len(self._frame_ids) + 1)
        variables = {
            name: value for name, value in _namespace(frame).items() if not is_hidden(name, value)
        }
        return {
            "fid": number,
            "name": frame.f_code.co_name,
            "path": self._path,
            "line": frame.f_lineno,
            "vars": {name: snapshot.value(value) for name, value in variables.items()},
            "order": self._order(number, variables),
            "is_global": frame.f_code.co_name == "<module>",
            "call_line": None if caller is None else caller.f_lineno,
        }

    def _order(self, number: int, names: dict[str, Any]) -> list[str]:
        """Poradie vzniku premenných; f_locals ich vracia v poradí v kóde."""
        known = self._orders.get(number, [])
        if len(known) != len(names) or not names.keys() >= set(known):
            kept = [name for name in known if name in names]
            known = self._orders[number] = kept + [n for n in names if n not in kept]
        return known

    def _indent(self, line: int | None) -> int:
        if line is None or not 0 < line <= len(self._lines):
            return 0
        text = self._lines[line - 1]
        return len(text) - len(text.lstrip())
