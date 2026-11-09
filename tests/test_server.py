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
