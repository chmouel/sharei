import re
import urllib.request

import pytest

from sharei import client, server


@pytest.fixture
def sharec(live_server, monkeypatch):
    monkeypatch.setattr(client, "SHAREI_URL", live_server)
    monkeypatch.setattr(server.Handler, "log_message", lambda *args: None)
    return client


def test_get_clip_prints_raw_text(sharec, capsysbinary):
    for text in ("one", "two"):
        urllib.request.urlopen(
            urllib.request.Request(
                f"{sharec.SHAREI_URL}/clip",
                data=text.encode(),
                headers={"Content-Type": "text/plain"},
            )
        ).read()
    sharec.get_main(["clip", "1"])
    assert capsysbinary.readouterr().out == b"one"
    with pytest.raises(sharec.Abort):
        sharec.get_main(["clip", "5"])


def test_get_drop_never_overwrites(sharec, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    sharec.upload("old.txt", b"old", "")
    sharec.upload("note.txt", b"new", "")
    (tmp_path / "note.txt").write_text("mine")
    sharec.get_main(["drop", "-f"])
    assert (tmp_path / "note.txt").read_text() == "mine"
    assert (tmp_path / "note-1.txt").read_bytes() == b"new"
    sharec.get_main(["drop", "1", "-o", str(tmp_path / "sub.txt")])
    assert (tmp_path / "sub.txt").read_bytes() == b"old"
    with pytest.raises(sharec.Abort, match="already exists"):
        sharec.get_main(["drop", "-o", str(tmp_path / "sub.txt")])
    with pytest.raises(sharec.Abort, match="No dropped file"):
        sharec.get_main(["drop", "2"])


def test_free_name_ignores_hidden_and_paths(tmp_path):
    assert client.free_name(tmp_path, "../../.bashrc") == tmp_path / "bashrc"
    assert client.free_name(tmp_path, "...") == tmp_path / "download"


def test_get_shows_in_terminal(sharec, tmp_path, monkeypatch, capsysbinary):
    work = tmp_path / "work"
    work.mkdir()
    monkeypatch.chdir(work)
    monkeypatch.setattr(sharec.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sharec, "terminal_size", lambda: (80, 24, 10, 20))
    png = (
        b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x04\x00\x00\x00\x00\x01"
        + b"\x00" * 6000
    )
    sharec.upload("wide.png", png, "")
    sharec.get_main(["drop"])
    out = capsysbinary.readouterr().out
    assert out.startswith(b"\x1b_Ga=T,f=100,q=2,c=80,m=1;")
    assert out.count(b"\x1b_G") == 2 and b"\x1b_Gm=0;" in out
    assert b"".join(
        part.split(b";", 1)[1] for part in out.rstrip(b"\n").split(b"\x1b\\")[:-1]
    ) == sharec.base64.standard_b64encode(png)

    sharec.upload("note.txt", b"hi\x1b]0;pwned\x07 there", "")
    sharec.get_main(["drop"])
    assert capsysbinary.readouterr().out == b"hi]0;pwned there\n"

    sharec.upload("blob.bin", b"\x00\x01binary", "")
    sharec.get_main(["drop"])
    assert (work / "blob.bin").read_bytes() == b"\x00\x01binary"
    assert list(work.iterdir()) == [work / "blob.bin"]


def test_get_shot_waits_for_a_key_then_clears(sharec, monkeypatch, capsysbinary):
    monkeypatch.setattr(sharec.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sharec.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sharec, "terminal_size", lambda: (80, 24, 10, 20))
    keys = []
    monkeypatch.setattr(sharec, "wait_key", lambda: keys.append(True))
    tall = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x64\x00\x00\x03\xe8"
    sharec.upload("tall.png", tall, "")
    sharec.get_main(["drop"])
    out = capsysbinary.readouterr().out
    assert keys == [True]
    assert out.startswith(b"\x1b[?1049h") and out.endswith(b"\x1b[?1049l")
    image_id = re.search(rb"\x1b_Ga=T,f=100,q=2,c=4,i=(\d+),m=0;", out)[1]
    assert b"\x1b_Ga=d,d=I,i=" + image_id + b",q=2\x1b\\" in out
    assert b"tall.png: press any key" in out
