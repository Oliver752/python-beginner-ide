"""Opis výnimiek pre konzolu a stopu."""

import os
import traceback
from types import CodeType
from typing import Any

# Rámce z tohto priečinka patria IDE, nie programu, a v tracebacku sa nezobrazujú.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__)) + os.sep


def format_error(error: BaseException) -> str:
    """Traceback ako z interpretera, bez rámcov backendu."""
    report = traceback.TracebackException.from_exception(error)
    _hide_backend_frames(report)
    return "".join(report.format())


def _hide_backend_frames(report: traceback.TracebackException) -> None:
    report.stack = traceback.StackSummary.from_list(
        [frame for frame in report.stack if not frame.filename.startswith(BACKEND_DIR)]
    )
    for nested in (report.__cause__, report.__context__, *(report.exceptions or ())):
        if nested is not None:
            _hide_backend_frames(nested)


def summary(error: BaseException) -> dict[str, str]:
    try:
        message = str(error)
    except Exception:  # __str__ z programu
        message = ""
    return {"type": type(error).__name__, "message": message}


def code_position(code: CodeType, lasti: int, lines: list[str]) -> dict[str, int | None]:
    """Rozsah inštrukcie v kóde (PEP 657), stĺpce v znakoch od nuly."""
    line, end_line, col, end_col = list(code.co_positions())[lasti // 2]
    return _position(lines, line, end_line, col, end_col)


def final_exception(error: BaseException, path: str, lines: list[str]) -> dict[str, Any]:
    """Opis výnimky, ktorá ukončila program: kde ju podčiarknuť a pôvodný traceback."""
    position: dict[str, int | None] = _position(lines, None, None, None, None)
    if isinstance(error, SyntaxError) and error.filename == path:
        position = {
            "line": error.lineno,
            "col": _zero_based(error.offset),
            "end_line": error.end_lineno,
            "end_col": _zero_based(error.end_offset),
        }
    entry = error.__traceback__
    while entry is not None:
        if entry.tb_frame.f_code.co_filename == path:
            position = code_position(entry.tb_frame.f_code, entry.tb_lasti, lines)
        entry = entry.tb_next
    return {**summary(error), **position, "traceback": format_error(error)}


def _zero_based(offset: int | None) -> int | None:
    return offset - 1 if offset else None


def _position(
    lines: list[str],
    line: int | None,
    end_line: int | None,
    col: int | None,
    end_col: int | None,
) -> dict[str, int | None]:
    return {
        "line": line,
        "col": _characters(lines, line, col),
        "end_line": end_line,
        "end_col": _characters(lines, end_line, end_col),
    }


def _characters(lines: list[str], line: int | None, offset: int | None) -> int | None:
    # CPython uvádza stĺpce v bajtoch UTF-8, editor pracuje so znakmi.
    if line is None or offset is None or not 0 < line <= len(lines):
        return offset
    return len(lines[line - 1].encode()[:offset].decode(errors="replace"))
