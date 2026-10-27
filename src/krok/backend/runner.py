"""Spustenie programu používateľa bez trasovania."""

import linecache
import os
import sys
import traceback

# Rámce z tohto priečinka patria IDE, nie programu, a v tracebacku sa nezobrazujú.
BACKEND_DIR = os.path.dirname(os.path.abspath(__file__)) + os.sep


def run_program(source: str, path: str) -> int:
    """Vykoná program ako modul __main__ a vráti návratový kód ako interpreter."""
    # Program nemusí byť v súbore; bez záznamu v linecache by traceback neukázal jeho riadky.
    linecache.cache[path] = (len(source), None, source.splitlines(keepends=True), path)
    sys.argv = [path]
    try:
        exec(compile(source, path, "exec", dont_inherit=True), {"__name__": "__main__"})
    except SystemExit as request:
        return _exit_code(request.code)
    except BaseException as error:
        report = traceback.TracebackException.from_exception(error)
        _hide_backend_frames(report)
        print("".join(report.format()), end="", file=sys.stderr)
        return 1
    return 0


def _exit_code(code: str | int | None) -> int:
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def _hide_backend_frames(report: traceback.TracebackException) -> None:
    report.stack = traceback.StackSummary.from_list(
        [frame for frame in report.stack if not frame.filename.startswith(BACKEND_DIR)]
    )
    for nested in (report.__cause__, report.__context__, *(report.exceptions or ())):
        if nested is not None:
            _hide_backend_frames(nested)
