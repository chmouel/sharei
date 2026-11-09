import os
import urllib.error
import urllib.request

import pytest

from conftest import make_repo, write
from sharei import server


def labels(items):
    return sorted((item["app"], item["relative"]) for item in items)


def test_pattern_matches_double_star():
    match = server.pattern_matches
    assert match(["dist", "a.whl"], ["dist", "*.whl"])
    assert match(["a.apk"], ["**", "*.apk"])
    assert match(
        ["x", "build", "outputs", "apk", "debug", "a.apk"],
        ["**", "outputs", "apk", "**", "*.apk"],
    )
    assert not match(["dist", "sub", "a.whl"], ["dist", "*.whl"])


def test_glob_root_discovers_repos_and_skips_unsafe_files(
    tmp_path, sharei_root, monkeypatch
):
    repos = tmp_path / "repos"
    one = make_repo(repos / "One")
    two = make_repo(repos / "two")
    (repos / "not-a-repo").mkdir()
    write(repos / "not-a-repo" / "dist" / "a.whl")
    write(one / "dist" / "one-1.0.whl")
    write(one / "dist" / "nested" / "deep.whl")
    write(two / "app" / "build" / "outputs" / "apk" / "debug" / "app-two-debug.apk")
    write(two / "node_modules" / "pkg" / "app" / "build" / "outputs" / "apk" / "x.apk")
    write(two / ".hidden" / "app" / "build" / "outputs" / "apk" / "y.apk")
    secret = write(tmp_path / "secret.whl")
    os.symlink(secret, one / "dist" / "escape.whl")
    monkeypatch.setattr(
        server,
        "ARTIFACT_RULES",
        (
            server.ArtifactRule(
                str(repos / "*"), ("dist/*.whl", "**/outputs/apk/**/*.apk")
            ),
        ),
    )
    items = server.scan_artifacts()
    assert labels(items) == [
        ("One", "dist/one-1.0.whl"),
        ("two", "app/build/outputs/apk/debug/app-two-debug.apk"),
    ]
    by_app = {item["app"]: item for item in items}
    assert by_app["One"]["project"] == "one"
    assert by_app["two"]["label"] == "debug"


def test_explicit_entry_wins_over_glob(tmp_path, sharei_root, monkeypatch):
    repo = make_repo(tmp_path / "repos" / "liseur")
    write(repo / "out" / "a.zip")
    monkeypatch.setattr(
        server,
        "ARTIFACT_RULES",
        (
            server.ArtifactRule(str(tmp_path / "repos" / "*"), ("out/*",)),
            server.ArtifactRule(str(repo), ("out/*.zip",), "Liseur", "books"),
        ),
    )
    repos = server.artifact_repos()
    assert [(r.name, r.project) for r in repos] == [("Liseur", "books")]


def test_cap_per_repo(tmp_path, sharei_root, monkeypatch):
    repo = make_repo(tmp_path / "r")
    for index in range(7):
        write(repo / "out" / f"{index}.bin")
    monkeypatch.setattr(server, "ARTIFACT_MAX_FILES", 3)
    monkeypatch.setattr(
        server, "ARTIFACT_RULES", (server.ArtifactRule(str(repo), ("out/*",)),)
    )
    assert len(server.scan_artifacts()) == 3


@pytest.mark.parametrize(
    "entry",
    [
        {"root": "~/x"},
        {"root": "~/x", "patterns": ["../etc/*"]},
        {"root": "~/x", "patterns": ["/etc/*"]},
        {"root": "~/x/*", "patterns": ["*"], "name": "X"},
        {"root": "~/x", "patterns": ["*"], "project": "bad name"},
        {"root": "~/x", "patterns": ["*"], "apk_dir": "a"},
    ],
)
def test_parse_artifacts_rejects_bad_entries(entry):
    with pytest.raises(SystemExit):
        server.parse_artifacts("config", [entry])


def test_old_apps_config_is_rejected(tmp_path):
    config = tmp_path / "config.toml"
    config.write_text('[[apps]]\nname = "A"\nroot = "~/a"\n')
    with pytest.raises(SystemExit, match="artifacts"):
        server.load_config(config, True)


def test_download_serves_only_scanned_files(tmp_path, live_server, monkeypatch):
    repo = make_repo(tmp_path / "r")
    write(repo / "dist" / "tool.whl", b"wheel")
    write(repo / "dist" / "app.apk", b"apk")
    monkeypatch.setattr(
        server, "ARTIFACT_RULES", (server.ArtifactRule(str(repo), ("dist/*",)),)
    )
    items = {item["relative"]: item for item in server.available_artifacts()}

    with urllib.request.urlopen(
        f"{live_server}/download/{items['dist/app.apk']['key']}"
    ) as response:
        assert (
            response.headers["Content-Type"]
            == "application/vnd.android.package-archive"
        )
        assert response.headers["Content-Disposition"].startswith("attachment")
        assert response.read() == b"apk"
    with urllib.request.urlopen(f"{live_server}/artifacts") as response:
        page = response.read().decode()
    assert "tool.whl" in page and "Install" in page and "Download" in page

    bogus = server.artifact_key(tmp_path / "elsewhere")
    with pytest.raises(urllib.error.HTTPError) as error:
        urllib.request.urlopen(f"{live_server}/download/{bogus}")
    assert error.value.code == 404
