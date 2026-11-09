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
    sharec.get_main(["drop"])
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
