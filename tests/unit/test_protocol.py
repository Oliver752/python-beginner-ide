from krok.common.protocol import Item, MessageParser, encode_message


def test_parser_separates_messages_from_output_split_into_chunks() -> None:
    message = {"event": "output", "stream": "stderr", "text": "chyba\n"}
    stream = "Meno: " + encode_message(message) + "ok\n" + "\x02nie je json\n"
    parser = MessageParser()
    items: list[Item] = []
    for i in range(0, len(stream), 3):  # správa príde roztrhnutá na viac kúskov
        items += parser.feed(stream[i : i + 3])

    merged: list[Item] = []
    for item in items:
        last = merged[-1] if merged else None
        if isinstance(item, str) and isinstance(last, str):
            merged[-1] = last + item
        else:
            merged.append(item)
    assert merged == ["Meno: ", message, "ok\n\x02nie je json\n"]
