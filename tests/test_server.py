import json
import urllib.error
import urllib.request

import pytest


def get(url):
    with urllib.request.urlopen(url) as response:
        return response.status, response.headers, response.read()


def upload(base, name, data):
    request = urllib.request.Request(
        f"{base}/upload?project=inbox&name={name}", data=data, method="POST"
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def test_pages_render(live_server):
    for path in ("/", "/shots", "/clip", "/drop"):
        status, _, body = get(live_server + path)
        assert status == 200 and b"<!doctype html>" in body


def test_upload_text_gets_viewer_and_escapes(live_server):
    result = upload(
        live_server, "x.py", b"print('</script><script>alert(1)</script>')\n"
    )
    assert result["view"] == "/view/inbox/x.py"
    _, headers, body = get(live_server + result["view"])
    assert b"<script>alert(1)" not in body
    assert (
        "'self'"
        not in headers["Content-Security-Policy"].split("script-src")[1].split(";")[0]
    )


def test_view_page_themes_under_csp(live_server):
    result = upload(live_server, "x.go", b"package main\n")
    _, headers, body = get(live_server + result["view"])
    nonce = headers["Content-Security-Policy"].split("'nonce-")[1].split("'")[0]
    assert f'<script nonce="{nonce}">'.encode() in body
    assert b'data-theme-default="auto"' in body


def test_reader_css_covers_both_modes():
    from sharei.server import THEME_READER_CSS

    for mode in ("dark", "light"):
        selector = f'html[data-mode="{mode}"] .markdown-body {{'
        block = THEME_READER_CSS.split(selector, 1)[1].split("}", 1)[0]
        assert "--bgColor-default" in block


def test_binary_has_no_viewer(live_server):
    result = upload(live_server, "blob.bin", b"\x00\x01\x02")
    assert "view" not in result
    with pytest.raises(urllib.error.HTTPError) as error:
        get(live_server + "/view/inbox/blob.bin")
    assert error.value.code == 404


@pytest.mark.parametrize(
    "path", ["/poub/inbox/..%2f..%2fetc%2fpasswd", "/view/inbox/.hidden"]
)
def test_unsafe_paths_are_404(live_server, path):
    with pytest.raises(urllib.error.HTTPError) as error:
        get(live_server + path)
    assert error.value.code in (400, 404)


def test_foreign_host_is_rejected(live_server):
    request = urllib.request.Request(
        live_server + "/", headers={"Host": "evil.example.com"}
    )
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code in (400, 403, 421)


def test_video_plays_inline_and_seeks(live_server):
    data = bytes(range(256)) * 4
    result = upload(live_server, "clip.mp4", data)
    assert result["view"] == "/play/inbox/clip.mp4"
    _, headers, body = get(live_server + result["view"])
    assert b'<video src="/poub/inbox/clip.mp4"' in body
    assert "media-src 'self'" in headers["Content-Security-Policy"]

    url = live_server + result["url"]
    _, headers, body = get(url)
    assert "Content-Disposition" not in headers and body == data
    for header, expected in (("bytes=10-19", data[10:20]), ("bytes=-5", data[-5:])):
        request = urllib.request.Request(url, headers={"Range": header})
        with urllib.request.urlopen(request) as response:
            assert response.status == 206 and response.read() == expected
            assert response.headers["Content-Range"].endswith(f"/{len(data)}")
    request = urllib.request.Request(url, headers={"Range": "bytes=5000-"})
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(request)
    assert error.value.code == 416


def test_delete_shots_of_one_project(live_server, sharei_root):
    for project in ("alpha", "beta"):
        shot = sharei_root / project / "shots" / "a.png"
        shot.parent.mkdir(parents=True)
        shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    _, _, body = get(live_server + "/shots")
    assert b'data-wipe-project="alpha"' in body
    request = urllib.request.Request(
        live_server + "/shots/delete-all?project=alpha", data=b"", method="POST"
    )
    with urllib.request.urlopen(request) as response:
        assert json.load(response) == {"deleted": 1}
    assert not (sharei_root / "alpha/shots/a.png").exists()
    assert (sharei_root / "beta/shots/a.png").exists()


def post(url, data=b""):
    request = urllib.request.Request(
        url, data=data, method="POST", headers={"Content-Type": "text/plain"}
    )
    with urllib.request.urlopen(request) as response:
        return json.load(response)


def test_clip_history_keeps_last_five(live_server):
    for index in range(7):
        state = post(live_server + "/clip", f"text {index}".encode())
    post(live_server + "/clip", b"text 3")
    texts = [entry["text"] for entry in state["history"]]
    assert texts == ["text 5", "text 4", "text 3", "text 2", "text 1"]
    state = post(live_server + "/clip", b"text 3")
    assert [entry["text"] for entry in state["history"]] == [
        "text 6",
        "text 5",
        "text 4",
        "text 2",
        "text 1",
    ]
    assert get(live_server + "/clip/raw?n=1")[2] == b"text 6"
    for bad in ("?n=6", "?n=-1", "?n=x"):
        with pytest.raises(urllib.error.HTTPError) as error:
            get(live_server + "/clip/raw" + bad)
        assert error.value.code == 404


def test_clip_history_restore_delete_clear(live_server):
    post(live_server + "/clip", b"first")
    state = post(live_server + "/clip", b"second")
    first = state["history"][0]["id"]
    state = post(live_server + f"/clip/history/restore?id={first}")
    assert state["text"] == "first"
    assert [entry["text"] for entry in state["history"]] == ["second"]
    state = post(live_server + "/clip/clear")
    assert state["text"] == "" and len(state["history"]) == 1
    state = post(live_server + f"/clip/history/delete?id={state['history'][0]['id']}")
    assert state["history"] == []
    with pytest.raises(urllib.error.HTTPError) as error:
        post(live_server + f"/clip/history/delete?id={first}")
    assert error.value.code == 404
    post(live_server + "/clip", b"a")
    post(live_server + "/clip", b"b")
    assert post(live_server + "/clip/history/clear")["history"] == []


def test_clip_history_entries_expire(live_server):
    from sharei import server

    post(live_server + "/clip", b"old")
    post(live_server + "/clip", b"new")
    server.CLIP["history"][0]["updated"] -= 3600
    state = json.loads(get(live_server + "/clip/state")[2])
    assert state["text"] == "new" and state["history"] == []


def test_qr_on_reader_pages_and_public_url(live_server, monkeypatch):
    from sharei import server

    monkeypatch.setattr(server, "PUBLIC_URL", "https://share.example.com/</script>")
    status, headers, body = get(live_server + "/vendor/qrcode.js")
    assert status == 200 and b"qrcode" in body
    upload(live_server, "a.txt", b"hello")
    status, headers, body = get(live_server + "/view/inbox/a.txt")
    nonce = headers["Content-Security-Policy"].split("'nonce-")[1].split("'")[0]
    assert b'<button type="button" data-qr aria-label=' in body
    assert f'<script nonce="{nonce}">window.shareiPublicUrl = '.encode() in body
    assert b'"https://share.example.com/<\\/script>"' in body
    assert b"share.example.com/</script>" not in body


@pytest.mark.parametrize(
    ("host", "loopback"),
    [
        ("127.0.0.1", True),
        ("::1", True),
        ("[::1]", True),
        ("localhost", True),
        ("0.0.0.0", False),
        ("::", False),
        ("192.168.1.2", False),
        ("box.lan", False),
    ],
)
def test_listens_on_loopback(host, loopback):
    from sharei import server

    assert server.listens_on_loopback(host) is loopback
