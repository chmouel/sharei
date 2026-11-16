import http.client
import json
import time
from urllib.parse import urlsplit

import pytest

from sharei import server

PUBLIC = {"X-Sharei-Public": "1"}


def call(base, method, path, body=None, headers=None):
    """A raw request, so paths reach the server exactly as written."""
    parts = urlsplit(base)
    connection = http.client.HTTPConnection(parts.hostname, parts.port, timeout=10)
    try:
        connection.putrequest(method, path, skip_accept_encoding=True)
        for name, value in (headers or {}).items():
            connection.putheader(name, value)
        if body is not None:
            connection.putheader("Content-Length", str(len(body)))
        connection.endheaders(body)
        response = connection.getresponse()
        return response.status, dict(response.getheaders()), response.read()
    finally:
        connection.close()


def upload(base, name, data, replace=False):
    status, _, body = call(
        base,
        "POST",
        f"/upload?project=inbox&name={name}{'&replace=1' if replace else ''}",
        data,
    )
    assert status == 200, body
    return json.loads(body)


def share(base, key, target="poub"):
    status, _, body = call(base, "POST", f"/public?target={target}&key={key}", b"")
    assert status == 200, body
    return urlsplit(json.loads(body)["url"]).path


def test_shared_file_is_served_with_strict_headers(live_server):
    upload(live_server, "notes.txt", b"hello")
    link = share(live_server, "inbox/notes.txt")
    assert link.startswith("/public/") and link.endswith("/notes.txt")
    assert share(live_server, "inbox/notes.txt") == link

    status, headers, body = call(live_server, "GET", link, headers=PUBLIC)
    assert (status, body) == (200, b"hello")
    assert headers["Content-Security-Policy"] == "sandbox"
    assert headers["Cache-Control"] == "no-store"
    assert headers["Referrer-Policy"] == "no-referrer"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert headers["Content-Disposition"].startswith("attachment")
    token = link.split("/")[2]
    assert call(live_server, "GET", f"/public/{token}/other-name")[0] == 200

    recent = json.loads(call(live_server, "GET", "/recent")[2])
    assert recent["drop"][0]["public"].endswith(link)
    assert b"public-pill" in call(live_server, "GET", "/drop")[2]


def test_html_and_shots_can_be_public(live_server, sharei_root):
    upload(live_server, "page.html", b"<script>alert(1)</script>")
    status, headers, _ = call(
        live_server, "GET", share(live_server, "inbox/page.html"), headers=PUBLIC
    )
    assert status == 200
    assert headers["Content-Security-Policy"] == "sandbox"

    shot = sharei_root / "inbox" / "shots" / "a.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    link = share(live_server, "inbox/shots/a.png", target="shot")
    status, headers, body = call(live_server, "GET", link, headers=PUBLIC)
    assert (status, headers["Content-Type"]) == (200, "image/png")
    assert body.startswith(b"\x89PNG")


@pytest.mark.parametrize(
    "path",
    [
        "/public/AAAAAAAAAAAAAAAAAAAAAA/x",
        "/public/short",
        "/public/",
        "/public",
    ],
)
def test_unknown_or_malformed_tokens_are_404(live_server, path):
    upload(live_server, "a.txt", b"a")
    share(live_server, "inbox/a.txt")
    assert call(live_server, "GET", path, headers=PUBLIC)[0] == 404


def test_public_door_reaches_nothing_else(live_server, sharei_root):
    upload(live_server, "a.txt", b"secret")
    shot = sharei_root / "inbox" / "shots" / "s.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\nfake")
    token = share(live_server, "inbox/a.txt").split("/")[2]
    private = [
        "/",
        "/drop",
        "/shots",
        "/clip",
        "/clip/raw",
        "/recent",
        "/state",
        "/notes-search",
        "/poub/inbox/a.txt",
        "/shot/inbox/shots/s.png",
        "/thumb/inbox/shots/s.png",
        "/view/inbox/a.txt",
        "/static/aniflow.js",
        f"/shot/inbox/../../public/{token}",
        f"/poub/inbox/a.txt?/public/{token}",
        "/public/..%2fpoub/inbox/a.txt",
        "/public/%2e%2e/poub/inbox/a.txt",
    ]
    for path in private:
        assert call(live_server, "GET", path, headers=PUBLIC)[0] == 404, path
    assert call(live_server, "GET", "/poub/inbox/a.txt")[0] == 200
    for value in ("1", "", "0", "no"):
        status = call(live_server, "GET", "/drop", headers={"X-Sharei-Public": value})
        assert status[0] == 404, value
    for path in (
        "/public?target=poub&key=inbox/a.txt",
        "/public/delete?target=poub&key=inbox/a.txt",
        "/upload?project=inbox&name=b.txt",
        "/clip",
        "/poub/delete-all",
    ):
        assert call(live_server, "POST", path, b"x", headers=PUBLIC)[0] == 404, path
    assert (sharei_root / "inbox" / "drop" / "a.txt").read_bytes() == b"secret"
    assert not (sharei_root / "inbox" / "drop" / "b.txt").exists()
    assert call(live_server, "GET", f"/public/{token}/a.txt", headers=PUBLIC)[0] == 200


def test_delete_and_reupload_never_revive_a_link(live_server):
    upload(live_server, "a.txt", b"one")
    link = share(live_server, "inbox/a.txt")
    assert call(live_server, "POST", "/poub/delete/inbox/a.txt", b"")[0] == 200
    upload(live_server, "a.txt", b"two")
    assert call(live_server, "GET", link)[0] == 404
    assert "public" not in json.loads(call(live_server, "GET", "/recent")[2])["drop"][0]


def test_another_file_at_the_same_path_is_refused(live_server, sharei_root):
    upload(live_server, "a.txt", b"one")
    link = share(live_server, "inbox/a.txt")
    path = sharei_root / "inbox" / "drop" / "a.txt"
    path.unlink()
    path.write_bytes(b"swapped behind sharei's back")
    assert call(live_server, "GET", link)[0] == 404


def test_replace_keeps_a_live_link_but_not_an_expired_one(live_server):
    upload(live_server, "a.txt", b"one")
    link = share(live_server, "inbox/a.txt")
    assert upload(live_server, "a.txt", b"two", replace=True)["public"].endswith(link)
    assert call(live_server, "GET", link)[2] == b"two"

    assert (
        call(
            live_server, "POST", "/expiry?target=poub&key=inbox/a.txt&seconds=60", b""
        )[0]
        == 200
    )
    key = next(iter(server.EXPIRY))
    server.EXPIRY[key] = time.time() - 1
    assert call(live_server, "GET", link)[0] == 404
    upload(live_server, "a.txt", b"three", replace=True)
    assert call(live_server, "GET", link)[0] == 404


def test_sweep_revokes_expired_links(live_server):
    upload(live_server, "a.txt", b"one")
    share(live_server, "inbox/a.txt")
    call(live_server, "POST", "/expiry?target=poub&key=inbox/a.txt&seconds=60", b"")
    server.EXPIRY[next(iter(server.EXPIRY))] = time.time() - 1
    assert server.sweep_expired() == 1
    assert server.PUBLIC == {}


def test_unshare_persists_and_failures_are_reported(live_server, monkeypatch):
    upload(live_server, "a.txt", b"one")
    upload(live_server, "b.txt", b"two")
    link_a = share(live_server, "inbox/a.txt")
    link_b = share(live_server, "inbox/b.txt")
    unshare_a = "/public/delete?target=poub&key=inbox/a.txt"
    assert json.loads(call(live_server, "POST", unshare_a, b"")[2]) == {"deleted": 1}
    assert call(live_server, "GET", link_a)[0] == 404
    server.public_load()
    assert call(live_server, "GET", link_a)[0] == 404
    assert call(live_server, "GET", link_b)[0] == 200

    def broken():
        raise OSError("disk full")

    monkeypatch.setattr(server, "public_save_locked", broken)
    unshare_b = "/public/delete?target=poub&key=inbox/b.txt"
    status, _, body = call(live_server, "POST", unshare_b, b"")
    assert status == 500 and b"unshare again" in body
    assert call(live_server, "GET", link_b)[0] == 404
    status, _, _ = call(live_server, "POST", "/public?target=poub&key=inbox/a.txt", b"")
    assert status == 500
    assert server.PUBLIC == {}


def test_corrupt_store_turns_every_link_off(sharei_root):
    (sharei_root / server.PUBLIC_FILE).write_text("{not json")
    server.PUBLIC["A" * 22] = {"path": "inbox/drop/a", "dev": 0, "ino": 0, "mtime": 0}
    server.public_load()
    assert server.PUBLIC == {}


def test_tokens_are_kept_out_of_the_log(live_server, capsys):
    upload(live_server, "a.txt", b"one")
    link = share(live_server, "inbox/a.txt")
    call(live_server, "GET", link)
    output = capsys.readouterr().out
    assert "/public/<redacted>" in output
    assert link.split("/")[2] not in output
