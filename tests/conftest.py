import subprocess
import threading
from http.server import ThreadingHTTPServer
from pathlib import Path

import pytest

from sharei import server


def make_repo(path: Path) -> Path:
    path.mkdir(parents=True)
    subprocess.run(["git", "init", "-q", str(path)], check=True)
    return path


def write(path: Path, data: bytes = b"x") -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(data)
    return path


@pytest.fixture
def sharei_root(tmp_path, monkeypatch):
    root = tmp_path / "root"
    root.mkdir()
    monkeypatch.setattr(server, "ROOT", root)
    monkeypatch.setattr(server, "ARTIFACT_RULES", ())
    monkeypatch.setattr(
        server, "ARTIFACT_CACHE", {"at": 0.0, "items": [], "thread": None}
    )
    monkeypatch.setenv("XDG_CACHE_HOME", str(tmp_path / "cache"))
    return root


@pytest.fixture
def live_server(sharei_root):
    httpd = ThreadingHTTPServer(("127.0.0.1", 0), server.Handler)
    thread = threading.Thread(target=httpd.serve_forever, daemon=True)
    thread.start()
    yield f"http://127.0.0.1:{httpd.server_address[1]}"
    httpd.shutdown()
    httpd.server_close()
