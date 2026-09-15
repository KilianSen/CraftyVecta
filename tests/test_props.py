from craftyvecta import props


def test_update_keeps_other_lines(tmp_path):
    f = tmp_path / "server.properties"
    f.write_text("#Minecraft server properties\nmotd=A Minecraft Server\nserver-port=25565\n", encoding="utf-8")

    assert props.update(f, {"server-port": "25501", "rcon.port": "26501"})
    assert f.read_text(encoding="utf-8") == (
        "#Minecraft server properties\nmotd=A Minecraft Server\nserver-port=25501\nrcon.port=26501\n"
    )
    assert not props.update(f, {"server-port": "25501"})


def test_update_creates_file_and_keeps_crlf(tmp_path):
    f = tmp_path / "new.properties"
    assert props.update(f, {"server-port": "25500"})
    assert props.read(f) == {"server-port": "25500"}

    crlf = tmp_path / "crlf.properties"
    crlf.write_bytes(b"a=1\r\nb=2\r\n")
    props.update(crlf, {"b": "3"})
    assert crlf.read_bytes() == b"a=1\r\nb=3\r\n"


def test_read_separators_and_escapes(tmp_path):
    f = tmp_path / "x.properties"
    f.write_text("a = 1\nb:2\nc 3\n! comment\n# comment\nmotd=\\u00A7aHi\\nthere\n", encoding="utf-8")
    assert props.read(f) == {"a": "1", "b": "2", "c": "3", "motd": "§aHi\nthere"}
    assert props.read(tmp_path / "missing") == {}


def test_dump_round_trips(tmp_path):
    values = {"name": "A\\B", "description": " leading space", "token": "abc"}
    f = tmp_path / "vecta.properties"
    f.write_text(props.dump(values), encoding="utf-8")
    assert props.read(f) == values
