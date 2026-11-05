import time

from krok.common.protocol import Item, MessageParser, encode_message

TOKEN = "abc123"


def merged(items: list[Item]) -> list[Item]:
    result: list[Item] = []
    for item in items:
        last = result[-1] if result else None
        if isinstance(item, str) and isinstance(last, str):
            result[-1] = last + item
        else:
            result.append(item)
    return result


def test_parser_separates_messages_from_output_split_into_chunks() -> None:
    message = {"event": "output", "stream": "stderr", "text": "chyba\n"}
    stream = "Meno: " + encode_message(message, TOKEN) + "ok\n"
    parser = MessageParser(TOKEN)
    items: list[Item] = []
    for i in range(0, len(stream), 3):  # správa príde roztrhnutá na viac kúskov
        items += parser.feed(stream[i : i + 3])
    assert merged(items) == ["Meno: ", message, "ok\n"]


def test_program_output_cannot_pretend_to_be_a_message() -> None:
    forged = encode_message({"event": "output", "stream": "stderr", "text": "x"}, "iny-token")
    parser = MessageParser(TOKEN)
    assert merged(parser.feed(forged + "\x02")) == [forged]
    assert parser.finish() == ["\x02"]  # mohol to byť začiatok značky, koniec prúdu to rozhodol


def test_large_message_is_parsed_in_linear_time() -> None:
    message = {"event": "trace", "text": "x" * 40_000_000}
    stream = encode_message(message, TOKEN)
    parser = MessageParser(TOKEN)
    items: list[Item] = []
    started = time.monotonic()
    for i in range(0, len(stream), 8192):
        items += parser.feed(stream[i : i + 8192])
    assert items == [message]
    assert time.monotonic() - started < 5  # opakované spájanie by trvalo minúty
