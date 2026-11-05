"""Backend: prijme príkaz od frontendu a vykoná program."""

import io
import queue
import sys
import threading
from typing import Any

from krok.backend.channel import Channel, ImmediateReader, InputStream, MessageStream
from krok.backend.runner import run_program


def main() -> int:
    stdout = sys.stdout
    assert isinstance(stdout, io.TextIOWrapper)
    # Na Windows sa "\n" na výstupe prekladá na "\r\n"; frontend chce text bez prekladu.
    stdout.reconfigure(newline="\n")
    commands: queue.Queue[dict[str, Any]] = queue.Queue()
    inputs: queue.Queue[str | None] = queue.Queue()
    stop = threading.Event()
    ImmediateReader(sys.stdin.fileno(), commands, inputs, stop).start()
    sys.stdin = InputStream(inputs)
    command = commands.get()
    channel = Channel(stdout, command["token"])
    sys.stderr = MessageStream(channel, "stderr")
    if command["cmd"] == "visualize":
        # Až tu: bežné spustenie nemá čakať na import psutil a bdb (stovky ms).
        from krok.backend.visualize import Visualization
        from krok.common.trace import Limits

        limits = Limits(**command["limits"])
        return Visualization(
            command["source"], command["path"], channel, inputs, stop, limits
        ).run()
    return run_program(command["source"], command["path"])
