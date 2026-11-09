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
