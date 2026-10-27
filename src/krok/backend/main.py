"""Backend: prijme príkaz od frontendu a vykoná program."""

import io
import queue
import sys
from typing import Any

from krok.backend.channel import Channel, ImmediateReader, InputStream, MessageStream
from krok.backend.runner import run_program


def main() -> int:
    stdout = sys.stdout
    assert isinstance(stdout, io.TextIOWrapper)
    # Na Windows sa "\n" na výstupe prekladá na "\r\n"; frontend chce text bez prekladu.
    stdout.reconfigure(newline="\n")
    channel = Channel(stdout)
    commands: queue.Queue[dict[str, Any]] = queue.Queue()
    inputs: queue.Queue[str] = queue.Queue()
    ImmediateReader(sys.stdin.fileno(), commands, inputs).start()
    sys.stdin = InputStream(inputs)
    sys.stderr = MessageStream(channel, "stderr")
    command = commands.get()
    return run_program(command["source"], command["path"])
