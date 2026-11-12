import http.client
import json
import re
import shutil
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
def aniflow_servers(tmp_path, monkeypatch):
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    running = []

    def start(root):
        httpd = aniflow.Server(("127.0.0.1", 0), root)
        thread = threading.Thread(target=httpd.serve_forever, daemon=True)
        thread.start()
        running.append((httpd, thread))

        def request(path, method="GET", headers=None, body=None):
            connection = http.client.HTTPConnection(*httpd.server_address, timeout=5)
            connection.request(method, path, body=body, headers=headers or {})
            response = connection.getresponse()
            result = response.status, dict(response.getheaders()), response.read()
            connection.close()
            return result

        return request

    yield start
    for httpd, thread in running:
        httpd.shutdown()
        httpd.server_close()
        thread.join()


@pytest.fixture
def aniflow_server(local_docs, aniflow_servers):
    return aniflow_servers(local_docs)


def test_browse_folders_and_markdown(aniflow_server):
    status, headers, _ = aniflow_server("/")
    assert status == 302 and headers["Location"] == "/files/"
    status, _, body = aniflow_server("/files/")
    assert status == 200
    assert b'href="/files/guides/"' in body
    assert b'href="/files/README.md"' in body
    assert body.index(b'href="/files/guides/"') < body.index(b'href="/files/README.md"')
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
        b"data-qr ",
        b"data-search ",
        b'id="notes-links"',
    ):
        assert unwanted not in body
    assert b'data-comments="/comments/file/guides/start.md"' in body
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


@pytest.mark.parametrize("path", ["/files/", "/files/guides/", "/files/README.md"])
def test_help_is_linked_from_folders_and_documents(aniflow_server, path):
    status, _, body = aniflow_server(path)
    assert status == 200
    assert b'href="/help"' in body


def test_help_works_without_files_or_configuration(aniflow_server, local_docs):
    for path in local_docs.iterdir():
        if path.is_file() or path.is_symlink():
            path.unlink()
        else:
            shutil.rmtree(path)
    before = set(local_docs.rglob("*"))
    status, headers, body = aniflow_server("/help")
    assert status == 200
    assert b'data-local-root="/"' in body
    assert b'href="/help?raw=1"' in body
    assert b'href="/files/"' in body
    assert "script-src 'nonce-" in headers["Content-Security-Policy"]
    block = body.decode().split(
        '<script type="application/json" id="markdown-source">'
    )[1]
    assert json.loads(block.split("</script>", 1)[0]) == aniflow.HELP.read_text("utf-8")
    assert set(local_docs.rglob("*")) == before


def test_help_source_and_icon_catalog(aniflow_server):
    status, headers, body = aniflow_server("/help?raw")
    assert status == 200
    assert headers["Content-Type"] == "text/plain; charset=utf-8"
    assert headers["X-Content-Type-Options"] == "nosniff"
    assert body == aniflow.HELP.read_bytes()
    status, _, body = aniflow_server("/icons/")
    assert status == 200
    assert json.loads(body) == {"icons": sorted(server.ICON_NAMES)}


def test_help_obeys_request_checks(aniflow_server):
    assert aniflow_server("/help", headers={"Host": "evil.example"})[0] == 403
    assert aniflow_server("/help", method="POST")[0] == 405


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


def post_comment(request, action, target, data=None, query="", headers=None):
    return request(
        f"/comments/{action}/{target}{query}",
        method="POST",
        body=json.dumps(data).encode() if data is not None else b"",
        headers=headers,
    )


def test_comments_crud_and_feedback(aniflow_server, local_docs, tmp_path):
    before = {
        path: path.read_bytes() for path in local_docs.rglob("*") if path.is_file()
    }
    status, _, body = post_comment(
        aniflow_server,
        "add",
        "file/README.md",
        {"start": 1, "end": 1, "body": "<script>Keep as text</script>"},
    )
    assert status == 200
    [comment] = json.loads(body)["comments"]
    assert comment["quote"] == ["# Hello"]
    assert comment["body"] == "<script>Keep as text</script>"
    status, _, body = post_comment(
        aniflow_server,
        "edit",
        "file/README.md",
        {"body": "A clearer title"},
        query="?id=" + comment["id"],
    )
    assert (
        status == 200 and json.loads(body)["comments"][0]["body"] == "A clearer title"
    )
    status, _, body = aniflow_server("/comments/file/README.md?format=prompt")
    assert status == 200
    assert b"Review comments on README.md (aniflow):" in body
    assert b"A clearer title" in body and b"# Hello" in body
    assert len(list((tmp_path / "cache/aniflow/comments").rglob("*.json"))) == 1
    assert {
        path: path.read_bytes() for path in local_docs.rglob("*") if path.is_file()
    } == before
    status, _, body = post_comment(
        aniflow_server,
        "delete",
        "file/README.md",
        query="?id=" + comment["id"],
    )
    assert status == 200 and json.loads(body)["comments"] == []


def test_comments_persist_and_are_separate_by_root_and_document(
    aniflow_server,
    aniflow_servers,
    local_docs,
    tmp_path,
):
    for target in ("help", "file/README.md", "file/guides/%C3%A9%20space.markdown"):
        assert (
            post_comment(aniflow_server, "add", target, {"start": 1, "body": target})[0]
            == 200
        )
    restarted = aniflow_servers(local_docs)
    other_root = tmp_path / "other"
    other_root.mkdir()
    (other_root / "README.md").write_text("# Hello\n")
    other = aniflow_servers(other_root)
    for target in ("help", "file/README.md", "file/guides/%C3%A9%20space.markdown"):
        status, _, body = restarted("/comments/" + target)
        assert status == 200 and json.loads(body)["comments"][0]["body"] == target
    assert json.loads(other("/comments/file/README.md")[2])["comments"] == []
    assert json.loads(other("/comments/help")[2])["comments"] == []
    assert b'data-comments="/comments/help"' in restarted("/help")[2]


@pytest.mark.parametrize(
    "target",
    [
        "file/missing.md",
        "file/script.js",
        "file/.secret.md",
        "file/.private/note.md",
        "file/%2e%2e/outside.md",
        "file/escape.md",
        "file/secret-alias.md",
        "file/escape-dir/outside.md",
        "file/guides/",
        "file/%00.md",
        "other",
    ],
)
def test_comments_reject_unavailable_sources(aniflow_server, target):
    assert aniflow_server("/comments/" + target)[0] == 404
    assert (
        post_comment(aniflow_server, "add", target, {"start": 1, "body": "x"})[0] == 404
    )


def test_comments_validate_requests(aniflow_server):
    target = "file/README.md"
    for data in (
        [],
        {"start": 1, "body": ""},
        {"start": 0, "body": "x"},
        {"start": True, "body": "x"},
        {"start": 1, "end": 100, "body": "x"},
        {"start": 1, "body": "x" * (server.COMMENT_MAX_CHARS + 1)},
    ):
        assert post_comment(aniflow_server, "add", target, data)[0] == 400
    assert (
        aniflow_server("/comments/add/" + target, method="POST", body=b"{invalid")[0]
        == 400
    )
    assert (
        aniflow_server("/comments/add/" + target, method="POST", body=b"x" * 20000)[0]
        == 413
    )
    assert (
        post_comment(
            aniflow_server, "edit", target, {"body": "x"}, query="?id=missing"
        )[0]
        == 404
    )
    assert post_comment(aniflow_server, "delete", target, query="?id=missing")[0] == 404
    assert post_comment(aniflow_server, "unknown", target)[0] == 404
    assert (
        post_comment(
            aniflow_server,
            "add",
            target,
            {"start": 1, "body": "x"},
            headers={"Origin": "https://evil.example"},
        )[0]
        == 403
    )
    assert (
        aniflow_server("/comments/" + target, headers={"Host": "evil.example"})[0]
        == 403
    )
    assert json.loads(aniflow_server("/comments/" + target)[2])["comments"] == []


def test_comments_follow_source_edits(aniflow_server, local_docs):
    post_comment(
        aniflow_server, "add", "file/README.md", {"start": 1, "body": "Follow this"}
    )
    path = local_docs / "README.md"
    path.write_text("New opening\n\n# Hello\n")
    [comment] = json.loads(aniflow_server("/comments/file/README.md")[2])["comments"]
    assert comment["start"] == 3 and not comment.get("outdated")
    path.write_text("New opening\n\n# Changed\n")
    [comment] = json.loads(aniflow_server("/comments/file/README.md")[2])["comments"]
    assert comment["outdated"] is True
    path.unlink()
    assert aniflow_server("/comments/file/README.md")[0] == 404


def test_comment_cache_is_not_served(aniflow_server, tmp_path):
    post_comment(
        aniflow_server, "add", "help", {"start": 1, "body": "Private feedback"}
    )
    [storage] = (tmp_path / "cache/aniflow/comments").rglob("*.json")
    for path in (
        "/comments/" + storage.name,
        "/files/.comments/" + storage.name,
        "/files/%2e%2e/cache/" + storage.name,
    ):
        assert aniflow_server(path)[0] == 404
