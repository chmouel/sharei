import http.client
import json
import re
import threading

import pytest

from sharei import aniflow, notes, server


@pytest.fixture
def local_docs(tmp_path):
    root = tmp_path / "docs"
    root.mkdir()
    (root / "README.md").write_text(
        "# Hello\n\n[Guide](guides/start.md#first)\n", encoding="utf-8"
    )
    (root / "guides").mkdir()
    (root / "guides" / "start.md").write_text(
        "# First\n\n![Picture](../images/picture.svg)\n", encoding="utf-8"
    )
    (root / "guides" / "é space.markdown").write_text("# Unicode\n", encoding="utf-8")
    (root / "images").mkdir()
    (root / "images" / "picture.svg").write_text(
        '<svg xmlns="http://www.w3.org/2000/svg"/>', encoding="utf-8"
    )
    (root / "script.js").write_text("alert(1)", encoding="utf-8")
    (root / ".secret.md").write_text("secret", encoding="utf-8")
    (root / ".private").mkdir()
    (root / ".private" / "note.md").write_text("secret", encoding="utf-8")
    (root / "secret-alias.md").symlink_to(root / ".secret.md")
    (tmp_path / "outside.md").write_text("outside", encoding="utf-8")
    (root / "escape.md").symlink_to(tmp_path / "outside.md")
    (root / "escape-dir").symlink_to(tmp_path, target_is_directory=True)
    return root


@pytest.fixture
def aniflow_server(local_docs):
    httpd = aniflow.Server(("127.0.0.1", 0), local_docs)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()

    def request(path, method="GET", headers=None):
        connection = http.client.HTTPConnection(*httpd.server_address, timeout=5)
        connection.request(method, path, headers=headers or {})
        response = connection.getresponse()
        result = response.status, dict(response.getheaders()), response.read()
        connection.close()
        return result

    yield request
    httpd.shutdown()
    httpd.server_close()
    thread.join()


def test_browse_folders_and_markdown(aniflow_server):
    status, headers, _ = aniflow_server("/")
    assert status == 302 and headers["Location"] == "/files/"
    status, _, body = aniflow_server("/files/")
    assert status == 200
    assert b'href="/files/guides/"' in body
    assert b'href="/files/README.md"' in body
    assert body.index(b">guides/</a>") < body.index(b">README.md</a>")
    assert b"script.js" not in body
    assert b"secret" not in body and b"escape" not in body
    status, headers, _ = aniflow_server("/files/guides")
    assert status == 302 and headers["Location"] == "/files/guides/"
    status, _, body = aniflow_server("/files/guides/")
    assert status == 200
    assert b'href="/files/"' in body
    assert b'href="/files/guides/%C3%A9%20space.markdown"' in body
    assert aniflow_server("/files/guides/%C3%A9%20space.markdown")[0] == 200


def test_reader_is_standard_markdown_without_sharei_tools(aniflow_server, monkeypatch):
    monkeypatch.setattr(notes, "VAULT", object())
    monkeypatch.setattr(server, "QR_ENABLED", True)
    status, headers, body = aniflow_server("/files/guides/start.md")
    assert status == 200
    assert b'data-local-root="/files/"' in body
    assert b'href="/files/guides/"' in body
    assert b'id="theme-select"' in body
    for unwanted in (
        b"data-notes",
        b"data-comments=",
        b"data-qr ",
        b"data-search ",
        b'id="notes-links"',
    ):
        assert unwanted not in body
    policy = headers["Content-Security-Policy"]
    nonce = policy.split("'nonce-")[1].split("'")[0]
    assert "'self'" not in policy.split("script-src ")[1].split(";")[0]
    for script in re.findall(rb"<script([^>]*)>", body):
        assert b"application/json" in script or f'nonce="{nonce}"'.encode() in script
    for name in (*server.MARKDOWN_SCRIPTS, "github-markdown.css", "mermaid.min.js"):
        assert aniflow_server("/vendor/" + name)[0] == 200


def test_source_is_escaped_and_reread(aniflow_server, local_docs):
    source = "# Updated\n\n</script><script>alert(1)</script> & <b>\n"
    (local_docs / "README.md").write_text(source, encoding="utf-8")
    _, _, body = aniflow_server("/files/README.md")
    assert b"<script>alert(1)" not in body
    block = body.decode().split(
        '<script type="application/json" id="markdown-source">'
    )[1]
    assert json.loads(block.split("</script>", 1)[0]) == source
    status, headers, body = aniflow_server("/files/README.md?raw")
    assert status == 200 and body.decode() == source
    assert headers["Content-Type"] == "text/plain; charset=utf-8"


def test_assets_are_served_safely(aniflow_server):
    for path in ("/files/images/picture.svg", "/icons/agent.svg"):
        status, headers, body = aniflow_server(path)
        assert status == 200 and b"<svg" in body
        assert headers["Content-Type"] == "image/svg+xml"
        assert headers["Content-Security-Policy"] == "sandbox"
        assert headers["X-Content-Type-Options"] == "nosniff"
    status, headers, body = aniflow_server("/files/script.js")
    assert status == 200 and body == b"alert(1)"
    assert headers["Content-Disposition"].startswith("attachment;")


@pytest.mark.parametrize(
    "path",
    [
        "/files/missing.md",
        "/files/.secret.md",
        "/files/%2ehidden.md",
        "/files/.private/note.md",
        "/files/%2e%2e/outside.md",
        "/files/guides/%2e%2e/%2e%2e/outside.md",
        "/files/%2Fetc/passwd",
        "/files/%00.md",
        "/files/escape.md",
        "/files/escape-dir/outside.md",
        "/files/secret-alias.md",
        "/vendor/../server.py",
        "/vendor/LICENSE.mermaid",
        "/icons/../server.py",
        "/clip",
        "/shots",
        "/notes",
        "/state",
    ],
)
def test_unavailable_paths_are_404(aniflow_server, path):
    assert aniflow_server(path)[0] == 404


def test_requests_are_read_only_and_host_checked(aniflow_server, local_docs):
    assert aniflow_server("/files/", headers={"Host": "evil.example"})[0] == 403
    assert (
        aniflow_server("/vendor/mermaid.min.js", headers={"Host": "evil.example"})[0]
        == 403
    )
    status, headers, _ = aniflow_server("/upload?name=x", method="POST")
    assert status == 405 and headers["Allow"] == "GET"
    assert (
        aniflow_server(
            "/clip", method="POST", headers={"Origin": "https://evil.example"}
        )[0]
        == 403
    )
    assert not (local_docs / "x").exists()


def test_directory_names_are_escaped(aniflow_server, local_docs):
    (local_docs / '<img src=x onerror="alert(1)">.md').write_text(
        "# Safe", encoding="utf-8"
    )
    _, _, body = aniflow_server("/files/")
    assert b'<img src=x onerror="alert(1)">' not in body
    assert b"&lt;img" in body


def test_empty_directory(aniflow_server, local_docs):
    (local_docs / "empty").mkdir()
    status, _, body = aniflow_server("/files/empty/")
    assert status == 200 and b"No Markdown files or folders here." in body


def test_main_uses_available_port_without_loading_sharei_config(
    local_docs, monkeypatch, capsys
):
    monkeypatch.chdir(local_docs)
    monkeypatch.setattr("sys.argv", ["aniflow"])

    def unexpected_config(*args, **kwargs):
        pytest.fail("aniflow must not read sharei config")

    def stop(httpd):
        assert httpd.root == local_docs
        assert httpd.server_address[0] == "127.0.0.1"
        assert httpd.server_address[1] > 0
        raise KeyboardInterrupt

    monkeypatch.setattr(server, "load_config", unexpected_config)
    monkeypatch.setattr(aniflow.Server, "serve_forever", stop)
    aniflow.main()
    output = capsys.readouterr().out
    assert re.search(r"http://127\.0\.0\.1:[1-9]\d*", output)


def test_main_rejects_missing_directory(tmp_path, monkeypatch, capsys):
    monkeypatch.setattr("sys.argv", ["aniflow", str(tmp_path / "missing")])
    with pytest.raises(SystemExit, match="2"):
        aniflow.main()
    assert "not a directory" in capsys.readouterr().err
