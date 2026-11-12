import base64
import importlib.util
import io
import json
import os
import re
import subprocess
import sys
import urllib.error
import urllib.request
from pathlib import Path

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


def test_confirm_without_terminal_points_at_yes():
    result = subprocess.run(
        [sys.executable, "-c", "from sharei import client; client.confirm('Go?')"],
        stdin=subprocess.DEVNULL,
        capture_output=True,
        text=True,
        start_new_session=True,
        check=False,
    )
    assert result.returncode == 1
    assert "pass -y" in result.stderr


def test_get_comments_and_replace_keep_review(sharec, tmp_path, monkeypatch, capsys):
    monkeypatch.chdir(tmp_path)
    sharec.upload("plan.md", b"# Plan\n\nStep one.\n", "inbox")
    urllib.request.urlopen(
        urllib.request.Request(
            f"{sharec.SHAREI_URL}/comments/add/inbox/plan.md",
            data=json.dumps({"start": 3, "end": 3, "body": "Too vague"}).encode(),
            headers={"Content-Type": "application/json"},
        )
    ).read()
    sharec.get_main(["comments", "plan.md"])
    assert capsys.readouterr().out == (
        "Review comments on plan.md (sharei):\n\nplan.md:3\n> Step one.\nToo vague\n"
    )
    with pytest.raises(sharec.Abort, match="-p PROJECT"):
        sharec.get_main(["comments", "other.md"])

    (tmp_path / "plan.md").write_text("# Plan\n\nStep one, with detail.\n")
    monkeypatch.setattr(
        sys, "argv", ["sharec", "plan.md", "-p", "inbox", "--replace", "--json"]
    )
    sharec.main()
    assert json.loads(capsys.readouterr().out)["name"] == "plan.md"
    sharec.get_main(["comments", "--json"])
    [entry] = json.loads(capsys.readouterr().out)["comments"]
    assert entry["outdated"] is True and entry["body"] == "Too vague"


def test_get_clip_json_prints_the_whole_state(sharec, capsys):
    sharec.clip_main(["first"])
    sharec.clip_main(["second"])
    sharec.get_main(["clip", "--json"])
    state = json.loads(capsys.readouterr().out)
    assert state["text"] == "second"
    assert [entry["text"] for entry in state["history"]] == ["first"]
    with pytest.raises(SystemExit):
        sharec.get_main(["clip", "--json", "--copy"])


@pytest.fixture
def vaulted(sharec, tmp_path, monkeypatch):
    from sharei import notes

    root = tmp_path / "vault"
    (root / "Shared").mkdir(parents=True)
    (root / "Shared" / "Trip.md").write_text("# Trip\n\nramen in kyoto\n")
    (root / "Shared" / "readme.txt").write_text("plain words\n")
    (root / "Shared" / "photo.png").write_bytes(b"\x89PNG\r\n\x1a\n")
    (root / "Private").mkdir()
    (root / "Private" / "secret.md").write_text("ramen\n")
    monkeypatch.setattr(notes, "CACHE", {"at": 0.0, "index": None, "thread": None})
    monkeypatch.setattr(notes, "TEXTS", {})
    monkeypatch.setattr(notes, "TEXTS_HELD", [0])
    monkeypatch.setattr(
        notes,
        "VAULT",
        notes.configure("test", {"vault": str(root), "folders": ["Shared"]}),
    )
    return root


def test_notes_lists_and_searches(vaulted, capsys):
    client.notes_main([])
    assert capsys.readouterr().out == (
        "note Shared/Trip.md\n"
        "file Shared/photo.png\n"
        "file Shared/readme.txt\n"
        "folder Shared\n"
    )
    client.notes_main(["ramen"])
    out = capsys.readouterr().out
    assert out.startswith("note Shared/Trip.md\n")
    assert ": ramen in kyoto" in out and "Private" not in out
    client.notes_main(["ramen", "--json"])
    answer = json.loads(capsys.readouterr().out)
    assert [note["p"] for note in answer["results"]] == ["Shared/Trip.md"]


def test_notes_json_carries_public_links(sharec, vaulted, capsys, monkeypatch):
    monkeypatch.setattr(sharec, "PUBLIC_URL", "https://share.example.com")
    sharec.notes_main(["--json"])
    answer = json.loads(capsys.readouterr().out)
    note = next(item for item in answer["items"] if item["k"] == "note")
    assert note["url"] == "https://share.example.com" + note["h"]
    sharec.notes_main(["ramen", "--json"])
    answer = json.loads(capsys.readouterr().out)
    assert answer["results"][0]["url"].startswith("https://share.example.com/notes/")


def test_get_list_json_carries_public_links(sharec, capsys, monkeypatch):
    monkeypatch.setattr(sharec, "PUBLIC_URL", "https://share.example.com")
    sharec.upload("plan.txt", b"x", "")
    sharec.get_main(["list", "--json"])
    [drop] = json.loads(capsys.readouterr().out)["drop"]
    assert drop["url"] == "https://share.example.com/poub/inbox/plan.txt"
    assert drop["view"] == "https://share.example.com/view/inbox/plan.txt"


def test_get_clip_json_carries_a_public_link(sharec, capsys, monkeypatch):
    monkeypatch.setattr(sharec, "PUBLIC_URL", "https://share.example.com")
    sharec.clip_main(["hi"])
    sharec.get_main(["clip", "--json"])
    assert (
        json.loads(capsys.readouterr().out)["url"] == "https://share.example.com/clip"
    )


def test_cp_puts_text_on_the_clipboard(sharec, monkeypatch):
    copied = []
    monkeypatch.setattr(sharec, "write_clipboard", copied.append)
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"piped")))
    sharec.cp_main(["-"])
    sharec.cp_main(["given"])
    assert copied == [b"piped", b"given"]
    monkeypatch.setattr(sys, "stdin", io.TextIOWrapper(io.BytesIO(b"")))
    with pytest.raises(SystemExit):
        sharec.cp_main(["-"])
    with pytest.raises(SystemExit):
        sharec.cp_main([""])


def test_notes_need_a_vault(sharec, monkeypatch):
    from sharei import notes

    monkeypatch.setattr(notes, "VAULT", None)
    with pytest.raises(sharec.Abort):
        sharec.notes_main([])


def test_cat_prints_a_route(sharec, capsysbinary):
    uploaded = sharec.upload("note.txt", b"hello", "")
    sharec.cat_main([uploaded["url"] + "?raw"])
    assert capsysbinary.readouterr().out == b"hello"
    with pytest.raises(SystemExit):
        sharec.cat_main(["poub/inbox/note.txt"])
    with pytest.raises(sharec.Abort):
        sharec.cat_main(["/poub/inbox/missing.txt"])


FILTER = Path(__file__).resolve().parents[1] / "contrib" / "raffi" / "sharei_filter.py"


@pytest.fixture
def raffi(sharec, tmp_path):
    if not FILTER.is_file():  # pragma: no cover - shipped in the source tree
        pytest.skip("the raffi script filter is not here")

    def run(*args, **extra):
        env = {
            "HOME": str(tmp_path),
            "PATH": os.environ["PATH"],
            "XDG_CACHE_HOME": str(tmp_path / "cache"),
            "SHAREI_URL": sharec.SHAREI_URL,
            "SHAREI_PUBLIC_URL": sharec.SHAREI_URL,
            **extra,
        }
        done = subprocess.run(
            [sys.executable, str(FILTER), *args],
            capture_output=True,
            check=True,
            env=env,
            text=True,
        )
        return json.loads(done.stdout)

    return run


def test_filter_drops_the_notes_view_without_a_vault(raffi):
    from sharei import notes

    notes.VAULT = None
    answer = raffi()
    assert [view["id"] for view in answer["views"]] == ["clip", "drop", "shots"]
    assert answer["view"] == "clip"


def test_filter_names_previews_after_what_they_hold(sharec, tmp_path, monkeypatch):
    module = load_filter()
    assert module.image_suffix(b"RIFF\x00\x00\x00\x00WEBPVP8 ") == ".webp"
    assert module.image_suffix(b"\x89PNG\r\n\x1a\n") == ".png"
    assert module.image_suffix(b"\xff\xd8\xff\xe0") == ".jpg"
    assert module.image_suffix(b"GIF89a") == ".gif"
    assert module.image_suffix(b"<svg xmlns='x'>") == ".svg"
    prolog = b'<?xml version="1.0"?>\n<!-- ' + b"x" * 600 + b" -->\n<svg/>"
    assert module.image_suffix(prolog) == ".svg"
    assert module.image_suffix(b"not an image") == ""
    assert module.image_suffix(b"BMP: a text file, not a bitmap") == ""
    bitmap = (
        b"BM" + (70).to_bytes(4, "little") + b"\x00" * 4 + (54).to_bytes(4, "little")
    )
    assert module.image_suffix(bitmap) == ".bmp"
    monkeypatch.setenv("PATH", os.environ["PATH"])
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    monkeypatch.setenv("SHAREI_URL", sharec.SHAREI_URL)
    webp = b"RIFF\x00\x00\x00\x00WEBPVP8 " + b"\x00" * 8
    sharec.upload("shot.png", webp, "")
    saved = module.download("/poub/inbox/shot.png", ".png")
    assert saved and saved.endswith(".webp")
    assert Path(saved).read_bytes() == webp
    assert module.download("/poub/inbox/missing.png") is None
    sharec.upload("drawing.png", b"<?xml version='1.0'?><svg xmlns='http://x'/>", "")
    svg = module.download("/poub/inbox/drawing.png", ".png")
    assert svg and svg.endswith(".svg")


def test_filter_shows_how_much_it_left_out():
    drawn = load_filter().truncation(40, 160)
    assert drawn["valid"] is False and "40 of 160" in drawn["title"]


def load_filter():
    spec = importlib.util.spec_from_file_location("sharei_filter", FILTER)
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_filter_draws_markdown_in_the_preview():
    drawn = load_filter().rendered(
        "---\ntags: [a]\n---\n# Title\n\n**bold** and [[Note|alias]]\n"
        "\n- [x] done\n\n| a | b |\n|---|---|\n| 1 | 2 |\n"
    )
    assert "\x1b[90m  tags: [a]\x1b[39m" in drawn
    assert "\x1b[1;35mTitle\x1b[0m" in drawn
    assert "\x1b[1mbold\x1b[22m" in drawn
    assert "\x1b[4;36malias\x1b[24;39m" in drawn
    assert "\x1b[32m\u2611\x1b[39m done" in drawn
    assert "\x1b[1ma\x1b[22m" in drawn
    assert " 1 \x1b[90m\u2502\x1b[39m 2 " in drawn  # cells, edges dimmed
    for raw in ("**", "# Title", "[[", "|---|"):
        assert raw not in drawn


def test_raffi_filter_lists_every_view(raffi, vaulted, sharec):
    sharec.clip_main(["some shared text"])
    sharec.upload("plan.txt", b"step one\n", "")
    answer = raffi()
    assert [view["id"] for view in answer["views"]] == [
        "notes",
        "clip",
        "drop",
        "shots",
    ]
    assert answer["view"] == "notes"
    listed = {
        item["title"]: item["variables"]["SHAREI_KIND"] for item in answer["items"]
    }
    assert listed == {"Trip": "note", "readme.txt": "file", "photo.png": "file"}
    assert answer["items"][0]["arg"].endswith("/notes/Shared/Trip.md")
    assert "_folded" not in answer["items"][0]

    [photo] = raffi("photo")["items"]
    assert photo["variables"]["SHAREI_KIND"] == "file"
    assert photo["arg"].endswith("/notes-file/Shared/photo.png")

    found = raffi("ramen")
    [note] = found["items"]
    assert (
        note["arg"].endswith("#find=1:ramen") or "#find=" in note["children"][0]["arg"]
    )

    [clip] = raffi("clip", "shared")["items"]
    assert clip["title"] == "some shared text"
    assert clip["variables"] == {"SHAREI_KIND": "clip", "SHAREI_CLIP": ""}
    assert raffi("clip", "nothing like it")["items"] == []
    assert raffi("drop")["items"][0]["title"] == "plan.txt"

    note = raffi(RAFFI_PREVIEW="1", SHAREI_KIND="note", SHAREI_PATH="Shared/Trip.md")
    assert "ramen in kyoto" in note["sections"][0]["content"]
