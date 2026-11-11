import base64
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
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


def test_get_browses_images_with_keys(sharec, monkeypatch, capsysbinary):
    monkeypatch.setattr(sharec.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sharec.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sharec, "terminal_size", lambda: (80, 24, 10, 20))
    keys = iter([b"j", b"\x1b[C", b"k", b"\x7f", b"q"])
    monkeypatch.setattr(sharec, "wait_key", lambda: next(keys))
    tall = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x64\x00\x00\x03\xe8"
    sharec.upload("a.png", tall, "")
    sharec.upload("note.txt", b"text", "")
    sharec.upload("b.png", tall, "")
    sharec.get_main(["drop"])
    out = capsysbinary.readouterr().out
    assert next(keys, None) is None
    shown = re.findall(rb"\x1b\[2m(\S+)  (\d)/3", out)
    assert shown == [
        (b"b.png", b"1"),
        (b"a.png", b"3"),
        (b"b.png", b"1"),
        (b"a.png", b"3"),
        (b"b.png", b"1"),
    ]
    assert out.startswith(b"\x1b[?1049h") and out.endswith(b"\x1b[?1049l")
    image_id = re.search(rb"\x1b_Ga=T,f=100,q=2,c=4,i=(\d+),m=0;", out)[1]
    assert out.count(b"\x1b_Ga=d,d=I,i=" + image_id + b",q=2\x1b\\") == 6


def test_get_browse_deletes_after_confirming(sharec, monkeypatch, capsysbinary):
    monkeypatch.setattr(sharec.sys.stdout, "isatty", lambda: True)
    monkeypatch.setattr(sharec.sys.stdin, "isatty", lambda: True)
    monkeypatch.setattr(sharec, "terminal_size", lambda: (80, 24, 10, 20))
    keys = iter([b"D", b"n", b"D", b"y", b"D", b"y"])
    monkeypatch.setattr(sharec, "wait_key", lambda: next(keys))
    tall = b"\x89PNG\r\n\x1a\n\x00\x00\x00\rIHDR\x00\x00\x00\x64\x00\x00\x03\xe8"
    sharec.upload("a.png", tall, "")
    sharec.upload("note.txt", b"text", "")
    sharec.upload("b.png", tall, "")
    sharec.get_main(["drop"])
    out = capsysbinary.readouterr().out
    assert next(keys, None) is None
    assert out.count(b"Delete b.png from sharei? D to confirm") == 2
    assert b"Delete a.png from sharei? D to confirm" in out
    assert out.endswith(b"\x1b[?1049l")
    assert [item["name"] for item in sharec.recent(10, "")["drop"]] == ["note.txt"]


def test_clip_sets_text_ttl_and_clears(sharec, capsys):
    sharec.clip_main(["first"])
    sharec.clip_main(["second", "--ttl", "0"])
    assert "never expires" in capsys.readouterr().err
    assert sharec.fetch("/clip/raw") == b"second"
    assert sharec.fetch("/clip/raw?n=1") == b"first"
    sharec.clip_main(["--ttl", "60"])
    assert sharec.fetch("/clip/raw") == b"second"
    assert "expires in" in capsys.readouterr().err
    sharec.clip_main(["--clear"])
    assert sharec.fetch("/clip/raw") == b""
    with pytest.raises(SystemExit):
        sharec.clip_main([""])


def test_upload_json_defaults_to_repo_project(sharec, tmp_path, monkeypatch, capsys):
    subprocess.run(["git", "init", "-q", str(tmp_path)], check=True)
    subprocess.run(
        [
            "git",
            "-C",
            str(tmp_path),
            "remote",
            "add",
            "origin",
            "git@github.com:me/My.Repo.git",
        ],
        check=True,
    )
    (tmp_path / "notes.md").write_text("# hi\n")
    monkeypatch.chdir(tmp_path)
    monkeypatch.setattr(sharec, "PUBLIC_URL", "https://share.example.com")
    monkeypatch.setattr(sys, "argv", ["sharec", "notes.md", "--json"])
    sharec.main()
    response = json.loads(capsys.readouterr().out)
    assert response["project"] == "My.Repo"
    assert response["url"] == "https://share.example.com/poub/My.Repo/notes.md"
    assert response["view"] == "https://share.example.com/md/My.Repo/notes.md"


def test_https_requests_send_basic_auth(sharec, tmp_path, monkeypatch):
    seen = []

    def fake_urlopen(req, timeout):
        seen.append(req)
        return io.BytesIO(b"ok")

    monkeypatch.setattr(sharec, "SHAREI_URL", "https://share.example.com")
    monkeypatch.setattr(sharec, "AUTH", {})
    monkeypatch.setattr(sharec.urllib.request, "urlopen", fake_urlopen)
    monkeypatch.setenv("HOME", str(tmp_path))
    monkeypatch.delenv("SHAREI_PASS_ENTRY", raising=False)
    netrc_file = tmp_path / ".netrc"
    netrc_file.write_text("machine share.example.com login me password secret\n")
    netrc_file.chmod(0o600)
    assert sharec.fetch("/clip/raw") == b"ok"
    expected = "Basic " + base64.b64encode(b"me:secret").decode()
    assert seen[0].unredirected_hdrs["Authorization"] == expected

    bin_dir = tmp_path / "bin"
    bin_dir.mkdir()
    (bin_dir / "pass").write_text("#!/bin/sh\nprintf 'p4ss\\nuser: you\\n'\n")
    (bin_dir / "pass").chmod(0o755)
    monkeypatch.setenv("PATH", f"{bin_dir}{os.pathsep}{os.environ['PATH']}")
    monkeypatch.setenv("SHAREI_PASS_ENTRY", "web/share")
    monkeypatch.setattr(sharec, "AUTH", {})
    sharec.fetch("/clip/raw")
    expected = "Basic " + base64.b64encode(b"you:p4ss").decode()
    assert seen[1].unredirected_hdrs["Authorization"] == expected


def test_falls_back_to_public_url_without_local_service(sharec, monkeypatch):
    def refuse(*args, **kwargs):
        raise OSError("refused")

    monkeypatch.setattr(sharec, "SHAREI_URL", "")
    monkeypatch.setattr(sharec, "PUBLIC_URL", "https://share.example.com")
    monkeypatch.setattr(sharec.socket, "create_connection", refuse)
    assert sharec.target() == "https://share.example.com"


def test_unauthorized_explains_how_to_log_in(sharec, monkeypatch):
    def deny(req, timeout):
        raise urllib.error.HTTPError(req.full_url, 401, "Unauthorized", {}, None)

    monkeypatch.setattr(sharec.urllib.request, "urlopen", deny)
    with pytest.raises(sharec.Abort, match="SHAREI_PASS_ENTRY"):
        sharec.fetch("/recent")


def test_show_in_terminal_saves_a_vector_instead_of_dumping_its_source(sharec):
    svg = b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4"/>'
    assert sharec.show_in_terminal([], 0, svg) is False
