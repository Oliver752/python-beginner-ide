"""Spustenie programu používateľa bez trasovania."""

import linecache
import sys

from krok.backend.excinfo import format_error


def prepare_program(source: str, path: str) -> None:
    # Program nemusí byť v súbore; bez záznamu v linecache by traceback neukázal jeho riadky.
    linecache.cache[path] = (len(source), None, source.splitlines(keepends=True), path)
    sys.argv = [path]


def exit_code(code: str | int | None) -> int:
    if code is None:
        return 0
    if isinstance(code, int):
        return code
    print(code, file=sys.stderr)
    return 1


def run_program(source: str, path: str) -> int:
    """Vykoná program ako modul __main__ a vráti návratový kód ako interpreter."""
    prepare_program(source, path)
    try:
        exec(compile(source, path, "exec", dont_inherit=True), {"__name__": "__main__"})
    except SystemExit as request:
        return exit_code(request.code)
    except BaseException as error:
        print(format_error(error), end="", file=sys.stderr)
        return 1
    return 0
