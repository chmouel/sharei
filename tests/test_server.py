import io
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
    for path in ("/artifacts", "/shots", "/clip", "/drop"):
        status, _, body = get(live_server + path)
        assert status == 200 and b"<!doctype html>" in body
    import http.client
    from urllib.parse import urlparse

    u = urlparse(live_server)
    conn = http.client.HTTPConnection(u.hostname, u.port)
    conn.request("GET", "/")
    resp = conn.getresponse()
    assert resp.status == 302 and resp.getheader("Location") == "/shots"
    conn.close()


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


def test_audio_and_pdf_previews(live_server):
    assert upload(live_server, "song.opus", b"OggS")["view"] == "/play/inbox/song.opus"
    assert upload(live_server, "doc.pdf", b"%PDF-1.4")["view"] == "/pdf/inbox/doc.pdf"
    _, headers, _ = get(live_server + "/poub/inbox/song.opus")
    assert headers["Content-Type"] == "audio/ogg"
    assert "Content-Disposition" not in headers
    _, headers, body = get(live_server + "/play/inbox/song.opus")
    assert b'<audio src="/poub/inbox/song.opus"' in body and b"<video" not in body
    _, headers, body = get(live_server + "/pdf/inbox/doc.pdf")
    csp = headers["Content-Security-Policy"]
    nonce = csp.split("'nonce-")[1].split("'")[0]
    assert f"script-src 'nonce-{nonce}';" in csp and "worker-src 'self'" in csp
    assert f'<script type="module" nonce="{nonce}">'.encode() in body
    assert b'data-url="/poub/inbox/doc.pdf"' in body
    assert get(live_server + "/vendor/pdf.worker.min.mjs")[0] == 200
    for path in ("/pdf/inbox/song.opus", "/play/inbox/doc.pdf", "/pdf/inbox/x.pdf"):
        with pytest.raises(urllib.error.HTTPError) as error:
            get(live_server + path)
        assert error.value.code == 404


def heic_bytes(alpha=False):
    image_module = pytest.importorskip("PIL.Image")
    pytest.importorskip("pillow_heif").register_heif_opener()
    mode = "RGBA" if alpha else "RGB"
    colour = (10, 120, 200, 128) if alpha else (10, 120, 200)
    buffer = io.BytesIO()
    image_module.new(mode, (40, 30), colour).save(buffer, "HEIF")
    return buffer.getvalue()


def test_heif_opener_is_registered_once_on_first_use(live_server, monkeypatch):
    from sharei import server

    heif = pytest.importorskip("pillow_heif")
    calls = []
    real = heif.register_heif_opener

    def counting():
        calls.append(1)
        real()

    data = heic_bytes()
    monkeypatch.setattr(server, "_heif_state", None)
    monkeypatch.setattr(heif, "register_heif_opener", counting)
    assert upload(live_server, "a.heic", data)["name"] == "a.jpg"
    assert upload(live_server, "b.heic", data)["name"] == "b.jpg"
    assert calls == [1] and server._heif_state is True


def test_upload_heic_becomes_jpeg(live_server, sharei_root):
    result = upload(live_server, "IMG_1234.HEIC", heic_bytes())
    assert result["name"] == "IMG_1234.jpg"
    assert result["url"] == "/poub/inbox/IMG_1234.jpg"
    assert (sharei_root / "inbox/drop/IMG_1234.jpg").is_file()
    _, headers, body = get(live_server + result["url"])
    assert headers["Content-Type"] == "image/jpeg"
    assert headers["Content-Disposition"] is None
    assert body[:2] == b"\xff\xd8" and result["size"] == len(body)


def test_upload_heic_with_alpha_becomes_png(live_server):
    result = upload(live_server, "sticker.heic", heic_bytes(alpha=True))
    assert result["name"] == "sticker.png"
    _, headers, body = get(live_server + result["url"])
    assert headers["Content-Type"] == "image/png"
    assert body[:8] == b"\x89PNG\r\n\x1a\n"


def test_upload_heic_named_after_another_image_is_still_converted(live_server):
    result = upload(live_server, "photo.jpg", heic_bytes())
    assert result["name"] == "photo.jpg"
    assert get(live_server + result["url"])[2][:2] == b"\xff\xd8"


def test_upload_heic_name_keeps_an_already_browser_format(live_server):
    from PIL import Image

    buffer = io.BytesIO()
    Image.new("RGB", (8, 8), (1, 2, 3)).save(buffer, "JPEG")
    result = upload(live_server, "photo.heic", buffer.getvalue())
    assert result["name"] == "photo.jpg"
    assert get(live_server + result["url"])[2] == buffer.getvalue()


def test_converted_names_still_get_collision_suffixes(live_server, sharei_root):
    names = [upload(live_server, "IMG_1.HEIC", heic_bytes())["name"] for _ in range(2)]
    assert names == ["IMG_1.jpg", "IMG_1-1.jpg"]
    assert sorted(item.name for item in (sharei_root / "inbox/drop").iterdir()) == [
        "IMG_1-1.jpg",
        "IMG_1.jpg",
    ]


def broken_open(real_open, failure):
    """Break the exclusive create of a converted file, either at open or mid-write."""

    class Truncated:
        def __init__(self, handle):
            self.handle = handle

        def __enter__(self):
            return self

        def __exit__(self, *exception):
            self.handle.close()
            return False

        def write(self, data):
            self.handle.write(data[:2])
            raise OSError(28, "No space left on device")

    def failing_open(self, mode="r", *args, **kwargs):
        if mode != "xb":
            return real_open(self, mode, *args, **kwargs)
        if failure == "open":
            raise OSError(28, "No space left on device")
        return Truncated(real_open(self, mode, *args, **kwargs))

    return failing_open


@pytest.mark.parametrize("failure", ["open", "write"])
def test_failed_heic_conversion_keeps_the_upload(
    live_server, sharei_root, monkeypatch, failure
):
    from pathlib import Path

    data = heic_bytes()
    monkeypatch.setattr(Path, "open", broken_open(Path.open, failure))
    result = upload(live_server, "IMG_2.heic", data)
    assert result["name"] == "IMG_2.heic"
    assert get(live_server + result["url"])[2] == data
    assert sorted(item.name for item in (sharei_root / "inbox/drop").iterdir()) == [
        "IMG_2.heic"
    ]


def test_upload_heic_is_kept_without_pillow_heif(live_server, monkeypatch):
    from sharei import server

    monkeypatch.setattr(server, "_heif_state", False)
    data = heic_bytes()
    result = upload(live_server, "IMG_1234.heic", data)
    assert result["name"] == "IMG_1234.heic"
    assert get(live_server + result["url"])[2] == data
    _, headers, _ = get(live_server + result["url"])
    assert headers["Content-Type"] == "image/heic"
    assert headers["Content-Disposition"] is None


def test_share_heic_becomes_jpeg(live_server, sharei_root):
    boundary = "sharei-boundary"
    body = (
        (
            f'--{boundary}\r\nContent-Disposition: form-data; name="title"\r\n\r\na photo\r\n'
            f'--{boundary}\r\nContent-Disposition: form-data; name="file"; '
            'filename="IMG_9.HEIC"\r\nContent-Type: application/octet-stream\r\n\r\n'
        ).encode()
        + heic_bytes()
        + f"\r\n--{boundary}--\r\n".encode()
    )
    request = urllib.request.Request(
        live_server + "/share",
        data=body,
        method="POST",
        headers={"Content-Type": f"multipart/form-data; boundary={boundary}"},
    )
    with urllib.request.urlopen(request) as response:
        assert response.status == 200
    assert (sharei_root / "inbox/drop/IMG_9.jpg").is_file()
    assert not (sharei_root / "inbox/drop/IMG_9.HEIC").exists()


def test_share_buttons_on_shots_and_drop(live_server, sharei_root):
    shot = sharei_root / "inbox/shots/a.png"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(b"\x89PNG\r\n\x1a\n")
    upload(live_server, "pic.png", b"\x89PNG\r\n\x1a\n")
    upload(live_server, 'pi"c.png', b"\x89PNG\r\n\x1a\n")
    upload(live_server, "note.txt", b"hi")
    assert b'id="share-shot"' in get(live_server + "/shots")[2]
    _, _, drop = get(live_server + "/drop")
    assert b'data-share="/poub/inbox/pic.png"' in drop
    assert b'data-name="pi&quot;c.png"' in drop
    assert b'data-share="/poub/inbox/note.txt"' not in drop


SVG = (
    b'<svg xmlns="http://www.w3.org/2000/svg" width="4" height="4">'
    b'<script>alert(1)</script><rect width="4" height="4"/></svg>'
)


def test_svg_screenshot_gets_a_tile_and_an_inline_sandboxed_image(
    live_server, sharei_root
):
    shot = sharei_root / "inbox/shots/chart.svg"
    shot.parent.mkdir(parents=True)
    shot.write_bytes(SVG)
    _, _, body = get(live_server + "/shots")
    assert b"chart.svg" in body
    assert b'src="/thumb/inbox/shots/chart.svg' in body
    _, headers, thumb = get(live_server + "/thumb/inbox/shots/chart.svg")
    assert headers["Content-Type"] == "image/svg+xml" and thumb == SVG
    assert headers["Content-Security-Policy"] == "sandbox"
    _, headers, full = get(live_server + "/shot/inbox/shots/chart.svg")
    assert headers["Content-Type"] == "image/svg+xml" and full == SVG
    assert headers["Content-Security-Policy"] == "sandbox"


def test_dropped_svg_is_an_image_but_stays_sandboxed(live_server):
    result = upload(live_server, "chart.svg", SVG)
    assert "view" not in result
    recent = json.loads(get(live_server + "/recent")[2])
    assert recent["drop"][0]["image"] is True and "view" not in recent["drop"][0]
    _, headers, body = get(live_server + "/poub/inbox/chart.svg")
    assert headers["Content-Type"] == "image/svg+xml" and body == SVG
    assert "Content-Disposition" not in headers
    assert headers["Content-Security-Policy"] == "sandbox"
    assert headers["X-Content-Type-Options"] == "nosniff"
    _, _, drop = get(live_server + "/drop")
    assert b'<img src="/poub/inbox/chart.svg"' in drop
    assert b'href="/view/inbox/chart.svg"' not in drop
    # The source stays readable, and a raster keeps its plain inline response.
    assert b"&lt;svg" in get(live_server + "/view/inbox/chart.svg")[2]
    upload(live_server, "shot.png", b"\x89PNG\r\n\x1a\n")
    _, headers, _ = get(live_server + "/poub/inbox/shot.png")
    assert "Content-Security-Policy" not in headers
