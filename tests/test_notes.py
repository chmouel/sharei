import json
import os
import re
import urllib.error
import urllib.request

import pytest

from conftest import write
from sharei import notes


def get(url):
    with urllib.request.urlopen(url) as response:
        return response.status, response.read().decode(errors="replace")


def status(url):
    try:
        return get(url)[0]
    except urllib.error.HTTPError as error:
        return error.code


@pytest.fixture
def vault(tmp_path, monkeypatch):
    root = tmp_path / "vault"
    write(
        root / ".obsidian" / "app.json",
        json.dumps({"userIgnoreFilters": ["Shared/Ignored"]}).encode(),
    )
    write(
        root / "Shared" / "Demo.md",
        b"[[Other#Second part|other]] [[Secret]] ![[pic.png|200]]\n"
        b"![a](</Att/doc.pdf>) `[[Att/code.png]]` %%[[Att/comment.png]]%%\n",
    )
    write(root / "Shared" / "Sub" / "Other.md", b"# Other\n")
    write(root / "Shared" / "Ignored" / "skip.md", b"x")
    write(root / "Shared" / ".hidden" / "h.md", b"x")
    write(root / "Private" / "Secret.md", b"secret")
    for name in ("pic.png", "doc.pdf", "code.png", "comment.png", "unlinked.png"):
        write(root / "Att" / name, b"\x89PNG\r\n\x1a\n")
    (root / "Shared" / "escape.md").symlink_to(root / "Private" / "Secret.md")
    monkeypatch.setattr(
        notes, "CACHE", {"at": 0.0, "index": None, "thread": None, "links": {}}
    )
    monkeypatch.setattr(notes, "TEXTS", {})
    monkeypatch.setattr(notes, "TEXTS_HELD", [0])
    monkeypatch.setattr(
        notes,
        "VAULT",
        notes.configure("test", {"vault": str(root), "folders": ["Shared"]}),
    )
    return root


def test_no_notes_without_config(live_server, monkeypatch):
    monkeypatch.setattr(notes, "VAULT", None)
    assert status(live_server + "/notes") == 404
    assert 'href="/notes"' not in get(live_server + "/drop")[1]


def test_tree_lists_only_shared_files(live_server, vault):
    _, body = get(live_server + "/notes")
    assert 'href="/notes"' in body
    assert "Shared" in body
    assert "Private" not in body
    _, body = get(live_server + "/notes/Shared/")
    assert "Demo" in body and "Other" in body
    for hidden in ("Ignored", "/Shared/.hidden", "escape.md"):
        assert hidden not in body


@pytest.mark.parametrize(
    "path,code",
    [
        ("/notes/Shared/Demo.md", 200),
        ("/notes/Shared/Sub/Other.md", 200),
        ("/notes-file/Att/pic.png", 200),
        ("/notes-pdf/Att/doc.pdf", 200),
        ("/notes/Private/Secret.md", 404),
        ("/notes/Private/", 404),
        ("/notes/Shared/../Private/Secret.md", 404),
        ("/notes/Shared/%2e%2e/Private/Secret.md", 404),
        ("/notes-file/Shared/..%2fPrivate%2fSecret.md", 404),
        ("/notes/Shared/escape.md", 404),
        ("/notes/Shared/Ignored/skip.md", 404),
        ("/notes/Shared/.hidden/h.md", 404),
        ("/notes-file/.obsidian/app.json", 404),
        ("/notes-file/Att/unlinked.png", 404),
        ("/notes-file/Att/code.png", 404),
        ("/notes-file/Att/comment.png", 404),
        ("/notes-pdf/Att/pic.png", 404),
    ],
)
def test_access_rules(live_server, vault, path, code):
    assert status(live_server + path) == code


def test_note_link_map(live_server, vault):
    _, body = get(live_server + "/notes/Shared/Demo.md")
    found = re.search(r'id="notes-links">([^<]*)</script>', body)
    links = json.loads(found.group(1))
    assert links["Other"] == {"href": "/notes/Shared/Sub/Other.md"}
    assert links["Secret"] is None
    assert links["pic.png"]["src"] == "/notes-file/Att/pic.png"
    assert links["/Att/doc.pdf"] == {"href": "/notes-pdf/Att/doc.pdf"}
    assert "Att/code.png" not in links
    assert "secret" not in body


def test_icon_fairy_icons(live_server, vault):
    plugin = vault / ".obsidian" / "plugins" / "icon-fairy"
    write(vault / ".obsidian" / "community-plugins.json", b'["icon-fairy"]')
    icon_map = {
        "Shared": {"type": "custom", "value": "folder"},
        "Shared/Demo.md": {"value": "demo"},
        "Private": {"type": "custom", "value": "private"},
        "Private/Secret.md": {"type": "custom", "value": "secret"},
        "Shared/Sub/Other.md": {"type": "custom", "value": "../escape"},
    }
    write(plugin / "data.json", json.dumps({"iconMap": icon_map}).encode())
    for name in ("folder.png", "demo.svg", "private.png", "secret.png"):
        write(plugin / "icons" / name, b"\x89PNG\r\n\x1a\n")
    _, body = get(live_server + "/notes")
    assert 'src="/notes-icon/folder.png"' in body
    assert "private.png" not in body
    _, body = get(live_server + "/notes/Shared/")
    assert '<h1><img class="note-icon" src="/notes-icon/folder.png"' in body
    assert 'src="/notes-icon/demo.svg"' in body
    assert 'src="/notes-icon/demo.svg"' in get(live_server + "/notes/Shared/Demo.md")[1]
    assert status(live_server + "/notes-icon/folder.png") == 200
    for name in ("private.png", "secret.png", "missing.png", "..%2fdata.json"):
        assert status(live_server + "/notes-icon/" + name) == 404


@pytest.mark.parametrize(
    "folders", [["../x"], ["/etc"], ["Missing"], ["Shared/./x"], [".obsidian"]]
)
def test_config_rejects_bad_folders(vault, folders):
    with pytest.raises(SystemExit):
        notes.configure("test", {"vault": str(vault), "folders": folders})


def test_newest_first(live_server, vault):
    os.utime(vault / "Shared" / "Demo.md", (1_000_000, 1_000_000))
    os.utime(vault / "Shared" / "Sub" / "Other.md", (2_000_000, 2_000_000))
    write(vault / "Shared" / "Fresh.md", b"new")
    _, body = get(live_server + "/notes/Shared/")
    tree = body.split('id="note-tree"', 1)[1].split('id="note-results"', 1)[0]
    assert tree.index(">Sub<") < tree.index(">Fresh<") < tree.index(">Demo<")
    results = body.split('id="note-results"', 1)[1]
    assert results.index(">Fresh<") < results.index(">Other<") < results.index(">Demo<")


def test_search_names_lists_shared_only(live_server, vault):
    write(vault / "Shared" / "blob.bin", b"\x00\x01")
    _, body = get(live_server + "/notes-search")
    items = {item["p"]: item for item in json.loads(body)["items"]}
    assert items["Shared/Demo.md"]["k"] == "note"
    assert items["Shared/Demo.md"]["h"] == "/notes/Shared/Demo.md"
    assert items["Shared/Sub"] == {
        "p": "Shared/Sub",
        "k": "folder",
        "h": "/notes/Shared/Sub/",
        "t": items["Shared/Sub"]["t"],
        "i": "",
    }
    assert items["Shared/blob.bin"]["h"] == "/notes/Shared/blob.bin"
    assert not any(
        path.startswith(("Private", "Att", "Shared/Ignored", "Shared/.hidden"))
        or path == "Shared/escape.md"
        for path in items
    )
    # A file that is neither a note nor text downloads from its /notes/ link.
    with urllib.request.urlopen(live_server + "/notes/Shared/blob.bin") as response:
        assert response.read() == b"\x00\x01"
        assert "attachment" in response.headers["Content-Disposition"]


def test_search_text(live_server, vault):
    write(
        vault / "Shared" / "Café.md",
        b"# Menu\n\nA long day.\nThe CAFE opens at nine, cafe and croissant.\n",
    )
    write(vault / "Private" / "Cafe secret.md", b"cafe croissant unicorn")
    _, body = get(live_server + "/notes-search?q=caf%C3%A9+croissant")
    data = json.loads(body)
    assert data["terms"] == ["cafe", "croissant"]
    assert [result["p"] for result in data["results"]] == ["Shared/Café.md"]
    result = data["results"][0]
    assert result["h"] == "/notes/Shared/Caf%C3%A9.md"
    assert result["hits"] == [
        {"n": 4, "s": "The CAFE opens at nine, cafe and croissant."}
    ]
    # Words found in the path count too, so a title match with no line still shows.
    _, body = get(live_server + "/notes-search?q=sub+other")
    data = json.loads(body)
    assert [result["p"] for result in data["results"]] == ["Shared/Sub/Other.md"]
    assert data["results"][0]["hits"] == [{"n": 1, "s": "# Other"}]
    _, body = get(live_server + "/notes-search?q=unicorn")
    assert json.loads(body)["results"] == []


def test_search_text_follows_edits(live_server, vault):
    note = vault / "Shared" / "Sub" / "Other.md"
    assert json.loads(get(live_server + "/notes-search?q=zebra")[1])["results"] == []
    write(note, b"# Other\nzebra\nzebra crossing\n")
    os.utime(note, (1, 1))
    hits = json.loads(get(live_server + "/notes-search?q=zebra+crossing")[1])
    # The line holding the most words comes first.
    assert hits["results"][0]["hits"] == [
        {"n": 3, "s": "zebra crossing"},
        {"n": 2, "s": "zebra"},
    ]


def test_search_snippet_cut_around_match():
    line = "x" * 300 + " needle " + "y" * 300
    cut = notes.snippet(line, line, ["needle"])
    assert cut.startswith("…") and cut.endswith("…") and "needle" in cut
    assert len(cut) == notes.SEARCH_SNIPPET_CHARS + 2


def test_search_skips_note_swapped_for_symlink(live_server, vault):
    write(vault / "Private" / "Secret.md", b"the launch code is swordfish")
    note = vault / "Shared" / "Sub" / "Other.md"
    assert json.loads(get(live_server + "/notes-search?q=other")[1])["results"]
    note.unlink()
    note.symlink_to(vault / "Private" / "Secret.md")
    data = json.loads(get(live_server + "/notes-search?q=swordfish")[1])
    assert data["results"] == []


def test_search_snippet_after_folding_changes_length():
    line = "\ufb03" * 300 + " needle " + "x" * 300
    cut = notes.snippet(line, notes.fold(line), ["needle"])
    assert "needle" in cut


def test_search_needs_vault(live_server, monkeypatch):
    monkeypatch.setattr(notes, "VAULT", None)
    assert status(live_server + "/notes-search") == 404
    assert status(live_server + "/notes-search?q=x") == 404
    assert "data-search" not in get(live_server + "/drop")[1]


def test_search_button_and_script_on_pages(live_server, vault):
    for path in ("/drop", "/notes", "/notes/Shared/Demo.md", "/notes-pdf/Att/doc.pdf"):
        body = get(live_server + path)[1]
        assert "data-search" in body, path
        assert "window.shareiSearch" in body, path
