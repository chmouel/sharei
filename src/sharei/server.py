#!/usr/bin/env python3
"""Serve build artifacts from your repos, per-project screenshots and drop folders, and a throwaway clipboard
on a phone-friendly page. Installed as a PWA over HTTPS, it also shows up in the Android Share menu.

Files live under ROOT/<project>/shots and ROOT/<project>/drop (ROOT defaults to ~/tmp/sharei). Settings come
from ~/.config/sharei/config.toml when present; see config.example.toml next to this script."""

from __future__ import annotations

import argparse
import base64
import codecs
import email.parser
import email.policy
import fnmatch
import functools
import glob
import hashlib
import html
import http.client
import http.cookies
import importlib
import io
import ipaddress
import json
import mimetypes
import os
import posixpath
import re
import secrets
import socket
import subprocess
import threading
import time
import tomllib
import zlib
from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple, TypedDict
from urllib.parse import (ParseResult, parse_qs, quote, unquote, urlparse,
                          urlsplit)

from sharei import notes, push
from sharei.assets import (ANNOTATE_JS, CAROUSEL_JS, CLIP_CSS, CLIP_JS,
                           CODE_CSS, CODE_JS, DROP_CSS, DROP_JS, EXPIRY_JS,
                           EXTRA_CSS, FOLDER_ICON, LIVE_JS, NOTE_ICON,
                           NOTES_CSS, NOTES_JS, PDF_CSS, PDF_JS, PLAY_CSS,
                           PUSH_JS, QR_CSS, QR_JS, SEARCH_CSS, SEARCH_JS,
                           SHARE_JS, SORT_ICON, SW_JS)
from sharei.reader import (MARKDOWN_CSS, MARKDOWN_JS, MARKDOWN_SCRIPTS,
                           PRESENT_BUTTON, READER_CSS, REVIEW_BUTTON,
                           REVIEW_DOCK)
from sharei.themes import (THEME_KEYS, THEME_PICKER_JS, THEME_READER_CSS,
                           THEMES, theme_app_css, theme_script, theme_select)

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
# What an <img> shows and a browser tab renders. Pillow cannot rasterise a vector
# to draw a thumbnail, and unlike a raster an SVG is a document that can carry
# scripts, so it only ever leaves under VECTOR_CSP.
VECTOR_SUFFIXES = {".svg"}
VECTOR_TYPES = {".svg": "image/svg+xml"}
IMAGE_LIKE_SUFFIXES = IMAGE_SUFFIXES | VECTOR_SUFFIXES
# Opaque origin for what the browser renders as a document. HTML keeps its
# scripts; an SVG needs none to be drawn.
HTML_CSP = "sandbox allow-scripts allow-forms"
VECTOR_CSP = "sandbox"
# HEIC/HEIF stills are converted to JPEG on upload; these cover what is left
# when pillow-heif is missing or the file cannot be decoded.
HEIC_SUFFIXES = {".heic", ".heif"}
HEIC_BRANDS = {b"heic", b"heix", b"heim", b"heis", b"hevc", b"hevx", b"hevm", b"hevs"}
HEIC_TYPES = {".heic": "image/heic", ".heif": "image/heif"}
# What a HEIC file becomes when it already holds one of them.
BROWSER_IMAGE_SUFFIXES = {
    "JPEG": ".jpg",
    "PNG": ".png",
    "WEBP": ".webp",
    "GIF": ".gif",
}
HTML_SUFFIXES = {".html", ".htm"}
VIDEO_SUFFIXES = {".mp4", ".m4v", ".mov", ".webm", ".ogv"}
# Spelled out because mimetypes misses some of these on a few systems.
AUDIO_TYPES = {
    ".mp3": "audio/mpeg",
    ".m4a": "audio/mp4",
    ".ogg": "audio/ogg",
    ".opus": "audio/ogg",
    ".wav": "audio/wav",
    ".flac": "audio/flac",
}
MEDIA_SUFFIXES = VIDEO_SUFFIXES | AUDIO_TYPES.keys()
MARKDOWN_SUFFIXES = {".md", ".markdown"}
TEXT_MAX_BYTES = 2 * 1024**2
HIGHLIGHT_MAX_BYTES = 512 * 1024
# highlight.js language per filename or suffix where the bare suffix is not one of its
# names or aliases; anything else is tried as is, then auto-detected in the browser.
LANGUAGE_NAMES = {
    "dockerfile": "bash",
    "containerfile": "bash",
    "makefile": "makefile",
    "gnumakefile": "makefile",
    "justfile": "makefile",
    "cmakelists.txt": "cmake",
}
LANGUAGE_SUFFIXES = {
    ".txt": "plaintext",
    ".log": "plaintext",
    ".csv": "plaintext",
    ".tsv": "plaintext",
    ".env": "bash",
    ".zsh": "bash",
    ".fish": "bash",
    ".mjs": "javascript",
    ".cjs": "javascript",
    ".jsx": "javascript",
    ".tsx": "typescript",
    ".mts": "typescript",
    ".kts": "kotlin",
    ".toml": "ini",
    ".conf": "ini",
    ".cfg": "ini",
    ".service": "ini",
    ".svg": "xml",
    ".htm": "xml",
    ".vue": "xml",
    ".jsonl": "json",
    ".lock": "json",
    ".tf": "ini",
    ".gradle": "kotlin",
    ".patch": "diff",
}
SHEBANG_LANGUAGES = (
    ("python", "python"),
    ("node", "javascript"),
    ("perl", "perl"),
    ("ruby", "ruby"),
    ("sh", "bash"),
)


class ArtifactRule(NamedTuple):
    """One [[artifacts]] entry; root may be a glob that matches several repos."""

    root: str
    patterns: tuple[str, ...]
    name: str | None = None
    project: str | None = None


class ArtifactRepo(NamedTuple):
    name: str
    project: str
    root: Path
    patterns: tuple[str, ...]


ARTIFACT_RULES: tuple[ArtifactRule, ...] = ()
ARTIFACT_SKIP_DIRS = {"node_modules", "__pycache__", "venv"}
ARTIFACT_MAX_FILES = 500
# Directories plus files looked at per pattern and checkout, so a "**" over a big tree stays cheap.
ARTIFACT_MAX_VISITS = 50_000
# Scans run in the background; pages show the last result and never wait more than
# ARTIFACT_FIRST_WAIT for one, since a glob root over many big repos can take a while.
ARTIFACT_CACHE_SECONDS = 15.0
ARTIFACT_FIRST_WAIT = 2.0
ARTIFACT_CACHE: dict[str, object] = {"at": 0.0, "items": [], "thread": None}
ARTIFACT_LOCK = threading.Lock()
ROOT = Path.home() / "tmp" / "sharei"
DEFAULT_PROJECT = "inbox"
# Base URL that QR codes use for sharei's own pages when the browser is on a loopback address.
PUBLIC_URL = ""
PROJECT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

CLIP_MAX_BYTES = 1024 * 1024
CLIP_LOCK = threading.Lock()
CLIP_DEFAULT_TTL = 10 * 60
CLIP_MAX_TTL = 7 * 24 * 60 * 60
CLIP_TTL_CHOICES = (60, 600, 3600, 0)
CLIP_HISTORY_MAX = 5

EXPIRY_FILE = ".expiry.json"
EXPIRY_LOCK = threading.Lock()
EXPIRY: dict[str, float] = {}
EXPIRY_MAX = 30 * 24 * 60 * 60
EXPIRY_SWEEP_SECONDS = 60


class ClipEntry(TypedDict):
    id: int
    text: str
    updated: float
    ttl: int


class ClipState(TypedDict):
    text: str
    version: int
    updated: float
    ttl: int
    history: list[ClipEntry]


CLIP: ClipState = {
    "text": "",
    "version": 0,
    "updated": 0.0,
    "ttl": CLIP_DEFAULT_TTL,
    "history": [],
}

UPLOAD_MAX_BYTES = 2 * 1024**3
# Review comments on dropped markdown live in <project>/drop/.comments/<name>.json.
COMMENTS_DIR = ".comments"
COMMENTS_MAX = 200
COMMENT_MAX_CHARS = 4000
COMMENT_MAX_LINES = 200
COMMENTS_LOCK = threading.Lock()
# Share target bodies are parsed in memory, so they get a lower cap than /upload.
SHARE_MAX_BYTES = 200 * 1024**2
SHARE_LOCK = threading.Lock()
POUB_LIST_LIMIT = 200
ALLOWED_HOSTS: set[str] = set()
ALLOWED_ORIGINS: set[str] = set()
ALLOWED_HOST_SUFFIXES = (
    ".local",
    ".lan",
    ".localdomain",
    ".home",
    ".internal",
    ".ts.net",
)
THUMB_MAX = 480
# Bumped when the bytes a thumbnail holds change, so an old cached one is not served.
THUMB_VERSION = 2

SCRIPT_DIR = Path(__file__).resolve().parent
VENDOR = SCRIPT_DIR / "vendor"
# Diagram icons built from Lucide by contrib/icons/make_icons.py, served by name only.
ICONS_DIR = SCRIPT_DIR / "icons"
ICON_NAMES = frozenset(path.stem for path in ICONS_DIR.glob("*.svg"))
# Only these files are reachable under /vendor/, everything else in that folder stays private.
VENDOR_TYPES = {
    "highlight.min.js": "text/javascript; charset=utf-8",
    "markdown-it.min.js": "text/javascript; charset=utf-8",
    "markdown-it-emoji.min.js": "text/javascript; charset=utf-8",
    "markdown-it-footnote.min.js": "text/javascript; charset=utf-8",
    "purify.min.js": "text/javascript; charset=utf-8",
    "markerjs3.js": "text/javascript; charset=utf-8",
    "markerjs-ui.js": "text/javascript; charset=utf-8",
    "github-markdown.css": "text/css; charset=utf-8",
    "mermaid.min.js": "text/javascript; charset=utf-8",
    "qrcode.js": "text/javascript; charset=utf-8",
    "pdf.min.mjs": "text/javascript; charset=utf-8",
    "pdf.worker.min.mjs": "text/javascript; charset=utf-8",
}
# Data URL type the browser has to send back per suffix. GIFs are missing on purpose: the canvas would flatten
# the animation into a still frame and the editor cannot encode GIF again.
ANNOTATE_TYPES = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}
ANNOTATE_MAX_BYTES = 48 * 1024 * 1024


def cache_root() -> Path:
    configured = os.environ.get("CACHE_DIRECTORY")
    if configured:
        return Path(configured)
    return Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache") / "sharei"


THUMBS = cache_root() / "thumbs"
CLIP_FILE = cache_root() / "clip.json"
PUSH_DIR = cache_root() / "push"


class Counts(TypedDict):
    artifacts: int
    shots: int
    clip: int
    drop: int


class PoubFile(TypedDict):
    project: str
    name: str
    size: str
    date: str
    url: str
    thumb: str
    image: bool
    text: bool
    timestamp: float
    expires: float | None


THEME_DEFAULT = "auto"


def theme_picker() -> str:
    items = [
        '<button type="button" data-theme="auto"><span class="swatch auto" aria-hidden="true"></span>Auto</button>'
    ]
    for name, (label, _, values) in THEMES.items():
        palette = dict(zip(THEME_KEYS, values, strict=True))
        items.append(
            f'<button type="button" data-theme="{name}"><span class="swatch" aria-hidden="true" '
            f'style="background:{palette["base"]};border-color:{palette["edge"]};color:{palette["accent"]}"></span>'
            f"{html.escape(label)}</button>"
        )
    push_button = (
        '<button type="button" data-push class="theme-button push-button" hidden aria-pressed="false" '
        'aria-label="Turn on notifications" title="Turn on notifications">'
        '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true">'
        '<path d="M10 2.75a5 5 0 0 0-5 5v3.1L3.6 13.4h12.8L15 10.85v-3.1a5 5 0 0 0-5-5z" '
        'fill="none" stroke="currentColor" stroke-width="1.6" stroke-linejoin="round"/>'
        '<path d="M8 15.6a2 2 0 0 0 4 0" fill="none" stroke="currentColor" stroke-width="1.6" '
        'stroke-linecap="round"/><path class="push-slash" d="M3.5 3.5l13 13" stroke="currentColor" '
        'stroke-width="1.6" stroke-linecap="round"/></svg></button>'
        if PUSH_ENABLED
        else ""
    )
    return (
        f'<div class="theme-picker">{search_button("theme-button")}{push_button}<button class="theme-button" id="theme-button" type="button" '
        'aria-label="Theme" title="Theme" aria-haspopup="true" aria-expanded="false">'
        '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><circle cx="10" cy="10" r="7.5" '
        'fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 2.5a7.5 7.5 0 0 1 0 15z" '
        'fill="currentColor"/></svg></button>'
        f'<div class="theme-menu" id="theme-menu" hidden>{"".join(items)}</div></div>'
    )


def project_worktrees(root: Path) -> list[Path]:
    try:
        result = subprocess.run(
            ["git", "-C", str(root), "worktree", "list", "--porcelain"],
            check=True,
            capture_output=True,
            text=True,
        )
    except (OSError, subprocess.CalledProcessError):
        return [root]

    paths = [
        Path(line.removeprefix("worktree "))
        for line in result.stdout.splitlines()
        if line.startswith("worktree ")
    ]
    return paths or [root]


def artifact_key(path: Path) -> str:
    return (
        base64.urlsafe_b64encode(str(path.resolve()).encode("utf-8"))
        .decode("ascii")
        .rstrip("=")
    )


def project_from_name(name: str) -> str | None:
    project = re.sub(r"[^A-Za-z0-9._-]+", "-", name.lower()).strip("-.")[:64]
    return project if valid_project(project) else None


def artifact_repos() -> list[ArtifactRepo]:
    repos: list[ArtifactRepo] = []
    seen: set[Path] = set()
    # Explicit roots first, so they win over a glob root that also matches them.
    for rule in sorted(ARTIFACT_RULES, key=lambda rule: glob.has_magic(rule.root)):
        expanded = os.path.expanduser(rule.root)
        if not glob.has_magic(expanded):
            root = Path(expanded)
            if root.resolve() not in seen:
                seen.add(root.resolve())
                name = rule.name or root.name
                project = (
                    rule.project or project_from_name(root.name) or DEFAULT_PROJECT
                )
                repos.append(ArtifactRepo(name, project, root, rule.patterns))
            continue
        for match in sorted(glob.glob(expanded)):
            root = Path(match)
            # Linked worktrees have a .git file; they are listed under their main checkout.
            if not (root / ".git").is_dir() or root.resolve() in seen:
                continue
            project = project_from_name(root.name)
            if project is None:
                continue
            seen.add(root.resolve())
            repos.append(ArtifactRepo(root.name, project, root, rule.patterns))
    return repos


def pattern_matches(parts: list[str], pattern: list[str]) -> bool:
    if not pattern:
        return not parts
    if pattern[0] == "**":
        return any(
            pattern_matches(parts[index:], pattern[1:])
            for index in range(len(parts) + 1)
        )
    return (
        bool(parts)
        and fnmatch.fnmatchcase(parts[0], pattern[0])
        and pattern_matches(parts[1:], pattern[1:])
    )


def artifact_files(checkout: Path, pattern: str) -> list[Path]:
    """Files under checkout matching pattern, walking only from its literal prefix."""
    pattern_parts = pattern.split("/")
    prefix: list[str] = []
    for part in pattern_parts:
        if glob.has_magic(part):
            break
        prefix.append(part)
    try:
        base = checkout.resolve(strict=True)
    except OSError:
        return []
    start = checkout.joinpath(*prefix)
    found: list[Path] = []
    visits = 0
    if len(prefix) == len(pattern_parts):
        candidates = [start]
    else:
        candidates = []
        if not start.is_dir():
            return []
        for directory, dirs, files in os.walk(start):
            dirs[:] = sorted(
                name
                for name in dirs
                if not name.startswith(".") and name not in ARTIFACT_SKIP_DIRS
            )
            visits += len(dirs) + len(files)
            candidates.extend(
                Path(directory, name)
                for name in sorted(files)
                if not name.startswith(".")
                and fnmatch.fnmatchcase(name, pattern_parts[-1])
            )
            if visits > ARTIFACT_MAX_VISITS:
                break
    for path in candidates:
        relative = path.relative_to(checkout)
        if any(part.startswith(".") for part in relative.parts):
            continue
        if not pattern_matches(list(relative.parts), pattern_parts):
            continue
        try:
            # Symlinks may point anywhere; only serve what really lives in the checkout.
            path.resolve(strict=True).relative_to(base)
        except (OSError, ValueError):
            continue
        if path.is_file():
            found.append(path)
    return found


def scan_artifacts() -> list[dict[str, str]]:
    items: list[dict[str, str]] = []
    for repo in artifact_repos():
        paths: dict[Path, tuple[str, Path]] = {}
        for checkout in project_worktrees(repo.root):
            branch = (
                "main checkout"
                if checkout.resolve() == repo.root.resolve()
                else checkout.name
            )
            for pattern in repo.patterns:
                for path in artifact_files(checkout, pattern):
                    paths.setdefault(
                        path.resolve(), (branch, path.relative_to(checkout))
                    )
        repo_items: list[dict[str, str]] = []
        for path, (branch, relative) in paths.items():
            try:
                info = path.stat()
            except OSError:
                continue
            label = path.name
            if path.suffix == ".apk":
                label = path.stem.removeprefix(f"app-{repo.project}-").removeprefix(
                    "app-"
                )
            repo_items.append(
                {
                    "app": repo.name,
                    "checkout": branch,
                    "date": datetime.fromtimestamp(info.st_mtime).strftime(
                        "%b %-d, %H:%M"
                    ),
                    "label": label,
                    "path": str(path),
                    "key": artifact_key(path),
                    "size": human_size(info.st_size),
                    "project": repo.project,
                    "relative": relative.as_posix(),
                    "timestamp": str(info.st_mtime),
                }
            )
        repo_items.sort(key=lambda item: float(item["timestamp"]), reverse=True)
        items.extend(repo_items[:ARTIFACT_MAX_FILES])
    return sorted(items, key=lambda item: float(item["timestamp"]), reverse=True)


def refresh_artifacts() -> None:
    items = scan_artifacts()
    with ARTIFACT_LOCK:
        ARTIFACT_CACHE["items"] = items
        ARTIFACT_CACHE["at"] = time.monotonic()
        ARTIFACT_CACHE["thread"] = None


def available_artifacts() -> list[dict[str, str]]:
    with ARTIFACT_LOCK:
        thread = ARTIFACT_CACHE["thread"]
        stale = time.monotonic() - float(ARTIFACT_CACHE["at"]) > ARTIFACT_CACHE_SECONDS  # type: ignore[arg-type]
        if stale and thread is None:
            thread = threading.Thread(target=refresh_artifacts, daemon=True)
            ARTIFACT_CACHE["thread"] = thread
            thread.start()
        first = not ARTIFACT_CACHE["at"]
    if first and isinstance(thread, threading.Thread):
        thread.join(ARTIFACT_FIRST_WAIT)
    with ARTIFACT_LOCK:
        return list(ARTIFACT_CACHE["items"])  # type: ignore[call-overload]


def valid_project(name: str) -> bool:
    return PROJECT_NAME.fullmatch(name) is not None


def drop_dir(project: str) -> Path:
    return ROOT / project / "drop"


def under_root(path: Path) -> bool:
    """Reject paths that a symlinked project or drop folder would lead outside ROOT."""
    try:
        path.resolve().relative_to(ROOT.resolve())
    except (OSError, ValueError):
        return False
    return True


def pretty_path(path: Path) -> str:
    try:
        return "~/" + path.relative_to(Path.home()).as_posix()
    except ValueError:
        return str(path)


def known_projects() -> list[str]:
    names = {repo.project for repo in artifact_repos()}
    if ROOT.is_dir():
        names.update(
            path.name
            for path in ROOT.iterdir()
            if path.is_dir() and valid_project(path.name)
        )
    names.discard(DEFAULT_PROJECT)
    return [DEFAULT_PROJECT, *sorted(names, key=str.lower)]


def shot_files(project: str | None = None) -> list[Path]:
    return [
        path
        for path in ROOT.glob(f"{project or '*'}/shots/**/*")
        if path.suffix.lower() in IMAGE_LIKE_SUFFIXES
        and path.is_file()
        and under_root(path)
        and not expired(path)
    ]


def available_shots(project: str | None = None) -> list[dict[str, str]]:
    shots: list[dict[str, str]] = []
    for path in shot_files(project):
        modified = path.stat().st_mtime
        relative = path.relative_to(ROOT)
        shots.append(
            {
                "project": relative.parts[0],
                "name": relative.relative_to(Path(*relative.parts[:2])).as_posix(),
                "date": datetime.fromtimestamp(modified).strftime("%b %-d, %H:%M"),
                "key": quote(relative.as_posix()),
                "url": f"/shot/{quote(relative.as_posix())}?v={int(modified)}",
                "thumb": f"/thumb/{quote(relative.as_posix())}?v={int(modified)}"
                f"&t={THUMB_VERSION}",
                "timestamp": str(modified),
                "expires": str(expires_at(path) or ""),
            }
        )
    return sorted(shots, key=lambda shot: float(shot["timestamp"]), reverse=True)


def thumbnail_cache_path(
    path: Path, style: str = "top", version: str = str(THUMB_VERSION)
) -> Path:
    """Where a thumbnail lives. An empty version is the pre-`THUMB_VERSION` name."""
    identity = f"{path.resolve()}:{path.stat().st_mtime_ns}:{THUMB_MAX}:{style}"
    digest = hashlib.sha256(f"{identity}:{version}".encode()).hexdigest()[:32]
    return THUMBS / f"{digest}.webp"


def vector_headers(base: dict[str, str]) -> dict[str, str]:
    """Serve an SVG inline but unable to reach the page: its scripts never run."""
    return {
        **base,
        "Content-Security-Policy": VECTOR_CSP,
        "X-Content-Type-Options": "nosniff",
    }


def render_thumbnail(path: Path, style: str = "top") -> bytes:
    # Lazy import so a missing Pillow degrades to serving the original image.
    image_module = importlib.import_module("PIL.Image")
    ops = importlib.import_module("PIL.ImageOps")
    with image_module.open(path) as image:
        image.draft("RGB", (THUMB_MAX, THUMB_MAX))
        # A phone photo carries its rotation in EXIF, and a dropped diagram can
        # be transparent: a browser applied both, so a thumbnail has to as well.
        image = ops.exif_transpose(image)
        alpha = image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info
        width, height = image.size
        # Shots tile in a 9:16 grid and show the top of the page, so a tall one
        # is cropped before shrinking instead of being squeezed into a sliver.
        # A dropped file keeps its whole frame: it is a picture, not a page.
        if style == "top" and height * 9 > width * 16:
            image = image.crop((0, 0, width, -(-width * 16 // 9)))
        image.thumbnail((THUMB_MAX, THUMB_MAX))
        buffer = io.BytesIO()
        image.convert("RGBA" if alpha else "RGB").save(
            buffer, "WEBP", quality=72, method=4
        )
    return buffer.getvalue()


_heif_state: bool | None = None
HEIF_LOCK = threading.Lock()


def heif_available() -> bool:
    """Register pillow-heif's Pillow opener once; False when either is missing."""
    global _heif_state
    if _heif_state is None:
        with HEIF_LOCK:
            if _heif_state is None:
                try:
                    importlib.import_module("PIL.Image")
                    importlib.import_module("pillow_heif").register_heif_opener()
                    _heif_state = True
                except (ImportError, OSError):
                    _heif_state = False
    return _heif_state


def looks_like_heic(path: Path, name: str) -> bool:
    """True when the name or the ISO base media ftyp box says HEIC/HEIF."""
    if Path(name).suffix.lower() in HEIC_SUFFIXES:
        return True
    try:
        with path.open("rb") as stream:
            head = stream.read(48)
    except OSError:
        return False
    if len(head) < 16 or head[4:8] != b"ftyp":
        return False
    # Major brand, then the compatible ones that follow the minor version.
    brands = {head[8:12]}
    brands.update(head[offset : offset + 4] for offset in range(16, len(head), 4))
    return bool(brands & HEIC_BRANDS)


def convert_heic_upload(temporary: Path, name: str) -> tuple[Path, str]:
    """Rewrite a HEIC upload in place as a JPEG, or a PNG when it has alpha.

    Returns the temporary to publish and the name to publish it under. A
    missing Pillow or pillow-heif, an undecodable file or a failed write leaves
    the upload untouched, so it still lands as the file that was sent.
    """
    if not looks_like_heic(temporary, name) or not heif_available():
        return temporary, name
    image_module = importlib.import_module("PIL.Image")
    try:
        with image_module.open(temporary) as image:
            already_shown = BROWSER_IMAGE_SUFFIXES.get(image.format or "")
            if already_shown is not None:
                return temporary, Path(name).stem + already_shown
            buffer = io.BytesIO()
            if image.mode in ("RGBA", "LA", "PA") or "transparency" in image.info:
                suffix = ".png"
                image.save(buffer, "PNG")
            else:
                suffix = ".jpg"
                options = {
                    key: image.info[key]
                    for key in ("exif", "icc_profile")
                    if image.info.get(key)
                }
                image.convert("RGB").save(buffer, "JPEG", quality=90, **options)
    except Exception as error:  # noqa: BLE001 - three libraries raise their own errors
        print(f"heic conversion failed for {name}: {error}")
        return temporary, name
    # A new file, not an in-place rewrite: a full disk must not eat the upload.
    replacement = temporary.with_name(f".part-{os.getpid()}-{secrets.token_hex(8)}")
    owned = False
    try:
        with replacement.open("xb") as stream:
            owned = True
            os.chmod(replacement, 0o644)
            stream.write(buffer.getvalue())
    except OSError as error:
        if owned:
            try:
                replacement.unlink(missing_ok=True)
            except OSError:
                pass
        print(f"heic conversion failed for {name}: {error}")
        return temporary, name
    temporary.unlink(missing_ok=True)
    return replacement, Path(name).stem + suffix


def forget_thumbnail(path: Path) -> None:
    """Drop every rendering of path; a cache problem never blocks the deletion."""
    for style in ("top", "fit"):
        for version in ("", str(THUMB_VERSION)):
            try:
                cached = thumbnail_cache_path(path, style, version)
                cached.unlink(missing_ok=True)
            except OSError as error:
                print(f"Cannot drop a thumbnail of {path}: {error}")


def clear_thumbnails() -> None:
    if not THUMBS.is_dir():
        return
    for path in THUMBS.iterdir():
        try:
            path.unlink()
        except OSError:
            continue


def delete_shot(encoded: str) -> bool:
    path = shot_path(encoded)
    if path is None:
        return False
    forget_thumbnail(path)
    path.unlink()
    expiry_forget(path)
    return True


def delete_all_shots(project: str | None = None) -> int:
    deleted = 0
    for path in shot_files(project):
        try:
            forget_thumbnail(path)
            path.unlink()
        except OSError:
            continue
        expiry_forget(path)
        deleted += 1
    if project is None:
        clear_thumbnails()
    return deleted


def annotate_path(target: str, encoded: str) -> Path | None:
    if target == "shots":
        return shot_path(encoded)
    if target == "drop":
        return poub_path(encoded)
    return None


def image_key(path: Path) -> str:
    """Return the quoted URL key that /shot/ and /poub/ accept for path."""
    relative = path.relative_to(ROOT)
    if len(relative.parts) > 2 and relative.parts[1] == "shots":
        return quote(relative.as_posix())
    return f"{quote(relative.parts[0])}/{quote(path.name)}"


def replace_image(path: Path, payload: bytes) -> None:
    """Overwrite path in place, keeping its mode, and drop the stale thumbnail first."""
    temporary = path.with_name(f".{path.name}.{secrets.token_hex(4)}.part")
    try:
        temporary.write_bytes(payload)
        os.chmod(temporary, path.stat().st_mode & 0o777)
        forget_thumbnail(path)
        os.replace(temporary, path)
    finally:
        temporary.unlink(missing_ok=True)


def delete_poub(encoded: str) -> bool:
    path = poub_path(encoded)
    if path is None:
        return False
    forget_thumbnail(path)
    path.unlink()
    expiry_forget(path)
    comments_forget(path)
    return True


def delete_all_poub(project: str | None = None) -> int:
    deleted = 0
    for path in poub_paths(project):
        try:
            forget_thumbnail(path)
            path.unlink()
        except OSError:
            continue
        expiry_forget(path)
        comments_forget(path)
        deleted += 1
    return deleted


def expiry_key(path: Path) -> str | None:
    try:
        return path.resolve().relative_to(ROOT.resolve()).as_posix()
    except (OSError, ValueError):
        return None


def expiry_load() -> None:
    try:
        data = json.loads((ROOT / EXPIRY_FILE).read_text())
    except (OSError, ValueError):
        return
    if isinstance(data, dict):
        with EXPIRY_LOCK:
            EXPIRY.clear()
            EXPIRY.update(
                (str(key), float(value))
                for key, value in data.items()
                if isinstance(value, (int, float))
            )


def expiry_save_locked() -> None:
    target = ROOT / EXPIRY_FILE
    temporary = target.with_name(f"{EXPIRY_FILE}.{secrets.token_hex(4)}.part")
    try:
        temporary.write_text(json.dumps(EXPIRY, sort_keys=True))
        os.replace(temporary, target)
    except OSError as error:
        print(f"Cannot save {target}: {error}")
    finally:
        temporary.unlink(missing_ok=True)


def expires_at(path: Path) -> float | None:
    if not EXPIRY:
        return None
    key = expiry_key(path)
    return EXPIRY.get(key) if key else None


def expired(path: Path) -> bool:
    when = expires_at(path)
    return when is not None and when <= time.time()


def expiry_set(path: Path, seconds: int) -> float | None:
    key = expiry_key(path)
    if key is None:
        return None
    with EXPIRY_LOCK:
        when = time.time() + seconds if seconds else None
        if when is None:
            EXPIRY.pop(key, None)
        else:
            EXPIRY[key] = when
        expiry_save_locked()
    return when


def expiry_forget(path: Path) -> None:
    """Drop the entry so a later file under the same name does not inherit it."""
    key = expiry_key(path)
    if key is None or key not in EXPIRY:
        return
    with EXPIRY_LOCK:
        if EXPIRY.pop(key, None) is not None:
            expiry_save_locked()


def sweep_expired() -> int:
    root = ROOT.resolve()
    now = time.time()
    deleted = 0
    with EXPIRY_LOCK:
        changed = False
        for key, when in list(EXPIRY.items()):
            try:
                path = (root / key).resolve()
                relative = path.relative_to(root)
            except (OSError, ValueError):
                relative = None
            if (
                relative is None
                or len(relative.parts) < 3
                or relative.parts[1] not in ("drop", "shots")
                or not path.is_file()
            ):
                del EXPIRY[key]
                changed = True
                continue
            if when > now:
                continue
            try:
                forget_thumbnail(path)  # both styles, shots and drops alike
                path.unlink()
                if relative.parts[1] == "drop":
                    comments_forget(path)
            except OSError as error:
                print(f"Cannot delete expired {path}: {error}")
                continue
            del EXPIRY[key]
            changed = True
            deleted += 1
        if changed:
            expiry_save_locked()
    return deleted


def expiry_sweeper() -> None:
    while True:
        time.sleep(EXPIRY_SWEEP_SECONDS)
        try:
            sweep_expired()
        except Exception as error:  # noqa: BLE001 - keep the sweeper alive
            print(f"Expiry sweep failed: {error}")


def shot_path(encoded: str) -> Path | None:
    try:
        root = ROOT.resolve()
        path = (ROOT / unquote(encoded)).resolve()
        relative = path.relative_to(root)
    except (OSError, ValueError):
        return None
    if (
        len(relative.parts) < 3
        or relative.parts[1] != "shots"
        or not valid_project(relative.parts[0])
        or path.suffix.lower() not in IMAGE_LIKE_SUFFIXES
        or not path.is_file()
        or expired(path)
    ):
        return None
    return path


def poub_image_path(encoded: str) -> Path | None:
    """A dropped image that can be thumbnailed, or None for anything else."""
    path = poub_path(encoded)
    if path is None or path.suffix.lower() not in IMAGE_LIKE_SUFFIXES:
        return None
    return path


def poub_path(encoded: str) -> Path | None:
    parts = unquote(encoded).split("/")
    if len(parts) == 1:
        parts.insert(0, DEFAULT_PROJECT)
    if (
        len(parts) != 2
        or not valid_project(parts[0])
        or not parts[1]
        or parts[1].startswith(".")
    ):
        return None
    folder = drop_dir(parts[0])
    if not under_root(folder):
        return None
    try:
        root = folder.resolve()
        path = (folder / parts[1]).resolve()
    except OSError:
        return None
    if path.parent != root or not path.is_file() or expired(path):
        return None
    return path


def human_size(size: int) -> str:
    value = float(size)
    for unit in ("B", "KB", "MB", "GB"):
        if value < 1024 or unit == "GB":
            return f"{value:.0f} {unit}" if unit == "B" else f"{value:.1f} {unit}"
        value /= 1024
    return f"{value:.1f} TB"


def safe_poub_name(raw: str) -> str | None:
    name = raw.replace("\\", "/").rsplit("/", 1)[-1].strip()
    name = "".join(character for character in name if character.isprintable())
    if name.startswith("."):
        return None
    if not name:
        name = "file"
    if len(name) > 180:
        suffix = Path(name).suffix[:20]
        name = name[: 180 - len(suffix)] + suffix
    return name


def open_upload(project: str) -> tuple[Path, int]:
    folder = drop_dir(project)
    folder.mkdir(parents=True, exist_ok=True)
    if not under_root(folder):
        raise OSError(f"{folder} leads outside {ROOT}")
    temporary = folder / f".part-{os.getpid()}-{secrets.token_hex(8)}"
    descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o644)
    return temporary, descriptor


def publish_poub(temporary: Path, name: str) -> Path:
    stem, suffix = Path(name).stem, Path(name).suffix
    for attempt in range(1000):
        candidate = temporary.parent / (
            name if attempt == 0 else f"{stem}-{attempt}{suffix}"
        )
        try:
            os.link(temporary, candidate)
        except FileExistsError:
            continue
        except OSError as error:
            raise OSError(
                f"cannot publish upload, hard links required: {error}"
            ) from error
        temporary.unlink(missing_ok=True)
        expiry_forget(candidate)
        comments_forget(candidate)
        return candidate
    raise OSError("too many files already use that name")


def replace_poub(temporary: Path, name: str) -> Path | None:
    """Swap an existing dropped file for the upload, keeping its name, expiry and comments."""
    path = temporary.parent / name
    if path.is_symlink() or not path.is_file():
        return None
    if expired(path):
        expiry_forget(path)
        comments_forget(path)
    forget_thumbnail(path)
    os.replace(temporary, path)
    return path


def comments_file(path: Path) -> Path:
    return path.parent / COMMENTS_DIR / f"{path.name}.json"


def comments_forget(path: Path) -> None:
    with COMMENTS_LOCK:
        try:
            comments_file(path).unlink(missing_ok=True)
        except OSError:
            pass


def comment_valid(entry: object) -> bool:
    return (
        isinstance(entry, dict)
        and isinstance(entry.get("id"), str)
        and isinstance(entry.get("body"), str)
        and isinstance(entry.get("quote"), list)
        and all(isinstance(line, str) for line in entry["quote"])
        and all(
            isinstance(entry.get(key), int) and not isinstance(entry.get(key), bool)
            for key in ("start", "end")
        )
        and 1 <= entry["start"] <= entry["end"]
    )


def comments_load(path: Path) -> list[dict]:
    try:
        data = json.loads(comments_file(path).read_text("utf-8"))
    except (OSError, ValueError):
        return []
    return (
        [entry for entry in data if comment_valid(entry)]
        if isinstance(data, list)
        else []
    )


def comments_save(path: Path, entries: list[dict]) -> None:
    target = comments_file(path)
    if not entries:
        target.unlink(missing_ok=True)
        return
    target.parent.mkdir(exist_ok=True)
    if target.parent.is_symlink() or not under_root(target.parent):
        raise OSError(f"{target.parent} leads outside {ROOT}")
    temporary = target.with_name(f".{target.name}.{secrets.token_hex(4)}.part")
    try:
        temporary.write_text(json.dumps(entries, indent=1), "utf-8")
        os.replace(temporary, target)
    finally:
        temporary.unlink(missing_ok=True)


def markdown_lines(path: Path) -> list[str]:
    """Source lines as markdown-it numbers them."""
    text = path.read_text("utf-8", errors="replace")
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    if lines and lines[-1] == "":
        lines.pop()
    return lines


def comment_anchor(entry: dict, lines: list[str]) -> dict:
    """Where the comment's quoted lines are now: same place, moved, or gone (outdated)."""
    start, end, quoted = entry["start"], entry["end"], entry["quote"]
    shown = {
        key: entry[key]
        for key in ("id", "body", "quote", "created", "updated")
        if key in entry
    }
    if lines[start - 1 : end] == quoted:
        return {**shown, "start": start, "end": end, "outdated": False}
    size = len(quoted)
    found = [
        index + 1
        for index in range(len(lines) - size + 1)
        if size and lines[index : index + size] == quoted
    ]
    if found:
        moved = min(found, key=lambda line: abs(line - start))
        return {**shown, "start": moved, "end": moved + size - 1, "outdated": False}
    last = max(1, len(lines))
    start = min(start, last)
    return {
        **shown,
        "start": start,
        "end": min(max(end, start), last),
        "outdated": True,
    }


def comments_view(path: Path) -> dict[str, object]:
    lines = markdown_lines(path)
    with COMMENTS_LOCK:
        entries = comments_load(path)
    comments = sorted(
        (comment_anchor(entry, lines) for entry in entries),
        key=lambda comment: (
            comment["start"],
            comment["end"],
            comment.get("created", 0),
        ),
    )
    return {"name": path.name, "lines": len(lines), "comments": comments}


def comments_count(path: Path) -> int:
    if not is_markdown(path.name) or not comments_file(path).is_file():
        return 0
    with COMMENTS_LOCK:
        return len(comments_load(path))


def comments_prompt(view: dict) -> str:
    """The comments as one block of text to paste back to whoever wrote the file."""
    name = view["name"]
    if not view["comments"]:
        return f"No review comments on {name}.\n"
    parts = [f"Review comments on {name} (sharei):"]
    for comment in view["comments"]:
        where = (
            str(comment["start"])
            if comment["start"] == comment["end"]
            else f"{comment['start']}-{comment['end']}"
        )
        head = f"{name}:{where}"
        if comment["outdated"]:
            head += " (outdated: these lines changed since the comment)"
        quoted = "\n".join(f"> {line}".rstrip() for line in comment["quote"])
        parts.append(f"{head}\n{quoted}\n{comment['body'].strip()}")
    return "\n\n".join(parts) + "\n"


def comment_change(
    path: Path, action: str, comment_id: str, data: object
) -> str | None:
    """Add, edit or delete a comment. Returns an error message, or None when done."""
    if action != "delete":
        if not isinstance(data, dict) or not isinstance(data.get("body"), str):
            return "body must be a string"
        body = data["body"].strip()
        if not body:
            return "the comment is empty"
        if len(body) > COMMENT_MAX_CHARS:
            return f"comments are limited to {COMMENT_MAX_CHARS} characters"
    now = time.time()
    lines = markdown_lines(path)
    with COMMENTS_LOCK:
        entries = comments_load(path)
        if action == "add":
            start, end = data.get("start"), data.get("end", data.get("start"))
            if not all(
                isinstance(value, int) and not isinstance(value, bool)
                for value in (start, end)
            ):
                return "start and end must be line numbers"
            if not 1 <= start <= end <= len(lines):
                return f"lines must be between 1 and {len(lines)}"
            if end - start + 1 > COMMENT_MAX_LINES:
                return f"a comment covers at most {COMMENT_MAX_LINES} lines"
            if len(entries) >= COMMENTS_MAX:
                return f"a file holds at most {COMMENTS_MAX} comments"
            entries.append(
                {
                    "id": secrets.token_hex(6),
                    "start": start,
                    "end": end,
                    "quote": lines[start - 1 : end],
                    "body": body,
                    "created": now,
                    "updated": now,
                }
            )
        else:
            index = next(
                (
                    index
                    for index, entry in enumerate(entries)
                    if entry["id"] == comment_id
                ),
                None,
            )
            if index is None:
                return "not found"
            if action == "delete":
                del entries[index]
            else:
                entries[index] = {**entries[index], "body": body, "updated": now}
        comments_save(path, entries)
    return None


def sweep_partials(max_age: float = 24 * 60 * 60) -> None:
    cutoff = time.time() - max_age
    for path in ROOT.glob("*/drop/.part-*"):
        if not under_root(path.parent):
            continue
        try:
            if path.stat().st_mtime < cutoff:
                path.unlink()
        except OSError:
            continue


def poub_files() -> list[PoubFile]:
    files: list[PoubFile] = []
    for path in poub_paths():
        try:
            stat = path.stat()
        except OSError:
            continue
        project = path.parent.parent.name
        files.append(
            PoubFile(
                project=project,
                name=path.name,
                size=human_size(stat.st_size),
                date=datetime.fromtimestamp(stat.st_mtime).strftime("%b %-d, %H:%M"),
                url=f"{quote(project)}/{quote(path.name)}",
                thumb=f"/thumb/{quote(project)}/{quote(path.name)}?v={stat.st_mtime_ns}"
                if path.suffix.lower() in IMAGE_LIKE_SUFFIXES
                else "",
                image=path.suffix.lower() in IMAGE_LIKE_SUFFIXES,
                text=looks_like_text(path),
                timestamp=stat.st_mtime,
                expires=expires_at(path),
            )
        )
    files.sort(key=lambda entry: entry["timestamp"], reverse=True)
    return files[:POUB_LIST_LIMIT]


def is_markdown(name: str) -> bool:
    return Path(name).suffix.lower() in MARKDOWN_SUFFIXES


def looks_like_text(path: Path) -> bool:
    """Cheap check on the first 8 KB, for listings: small enough, no NUL, valid UTF-8 so far."""
    try:
        if path.stat().st_size > TEXT_MAX_BYTES:
            return False
        with path.open("rb") as handle:
            head = handle.read(8192)
        codecs.getincrementaldecoder("utf-8")().decode(head, final=False)
    except (OSError, UnicodeDecodeError):
        return False
    return b"\0" not in head


def read_text_file(path: Path) -> str | None:
    try:
        if path.stat().st_size > TEXT_MAX_BYTES:
            return None
        data = path.read_bytes()
        return None if b"\0" in data else data.decode("utf-8")
    except (OSError, UnicodeDecodeError):
        return None


def view_url(project: str, path: Path) -> str | None:
    """Reader page for a dropped file: /md for markdown, /play for audio and video, /pdf for
    PDFs, /view for other text."""
    if path.suffix.lower() in MEDIA_SUFFIXES:
        return f"/play/{quote(project)}/{quote(path.name)}"
    if path.suffix.lower() == ".pdf":
        return f"/pdf/{quote(project)}/{quote(path.name)}"
    if is_markdown(path.name):
        return f"/md/{quote(project)}/{quote(path.name)}"
    if path.suffix.lower() not in IMAGE_LIKE_SUFFIXES and looks_like_text(path):
        return f"/view/{quote(project)}/{quote(path.name)}"
    return None


def code_language(name: str, text: str) -> str:
    lowered = name.lower()
    if lowered in LANGUAGE_NAMES:
        return LANGUAGE_NAMES[lowered]
    suffix = Path(lowered).suffix
    if suffix:
        return LANGUAGE_SUFFIXES.get(suffix, suffix[1:])
    if text.startswith("#!"):
        interpreter = text.split("\n", 1)[0]
        for needle, language in SHEBANG_LANGUAGES:
            if needle in interpreter:
                return language
    return ""


def qr_button() -> str:
    if not QR_ENABLED:
        return ""
    return '<button type="button" data-qr aria-label="Show a QR code for this page">QR</button>'


def qr_script(nonce: str = "") -> str:
    if not QR_ENABLED:
        return ""
    attribute = f' nonce="{nonce}"' if nonce else ""
    base = json.dumps(PUBLIC_URL).replace("</", "<\\/")
    return f"<script{attribute}>window.shareiPublicUrl = {base};{QR_JS}</script>"


SEARCH_ICON = (
    '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><circle cx="8.5" cy="8.5" r="5.5" '
    'fill="none" stroke="currentColor" stroke-width="1.7"/><path d="M12.6 12.6l4.4 4.4" '
    'stroke="currentColor" stroke-width="1.7" stroke-linecap="round"/></svg>'
)


def search_button(css_class: str = "") -> str:
    """The button that opens the notes picker, also bound to / and Ctrl/Cmd+K."""
    if notes.VAULT is None:
        return ""
    attribute = f' class="{css_class}"' if css_class else ""
    return (
        f'<button type="button" data-search{attribute} aria-label="Search notes (/ or Ctrl+K)" '
        f'title="Search notes (/ or Ctrl+K)">{SEARCH_ICON}</button>'
    )


def search_script(nonce: str = "") -> str:
    if notes.VAULT is None:
        return ""
    attribute = f' nonce="{nonce}"' if nonce else ""
    return f"<style>{SEARCH_CSS}</style><script{attribute}>{SEARCH_JS}</script>"


# The picker's list of every shared note, folder and file, rebuilt after each vault scan.
NOTES_ENTRIES: dict[str, object] = {"index": None, "entries": []}


def notes_entries(index: notes.Index) -> list[dict[str, object]]:
    if NOTES_ENTRIES["index"] is index:
        return NOTES_ENTRIES["entries"]  # type: ignore[return-value]
    entries: list[dict[str, object]] = []
    folders: dict[str, int] = {}
    for relative in sorted(index.shared):
        try:
            changed = int(index.files[relative].stat().st_mtime)
        except OSError:
            changed = 0
        parts = relative.split("/")
        for depth in range(1, len(parts)):
            folder = "/".join(parts[:depth])
            folders[folder] = max(folders.get(folder, 0), changed)
        suffix = posixpath.splitext(relative)[1].lower()
        if notes.is_markdown(relative):
            kind, href = "note", notes.url("/notes/", relative)
        elif suffix == ".pdf":
            kind, href = "file", notes.url("/notes-pdf/", relative)
        elif suffix in IMAGE_LIKE_SUFFIXES or suffix in MEDIA_SUFFIXES:
            kind, href = "file", notes.url("/notes-file/", relative)
        else:
            kind, href = "file", notes.url("/notes/", relative)
        entries.append({"p": relative, "k": kind, "h": href, "t": changed})
    for folder, changed in folders.items():
        entries.append(
            {
                "p": folder,
                "k": "folder",
                "h": notes.url("/notes/", folder) + "/",
                "t": changed,
            }
        )
    for entry in entries:
        icon = index.icons.get(entry["p"])  # type: ignore[arg-type]
        entry["i"] = notes.url("/notes-icon/", icon) if icon else ""
    NOTES_ENTRIES.update(index=index, entries=entries)
    return entries


def name_matches(
    index: notes.Index, terms: list[str], found: list[dict[str, object]]
) -> list[dict[str, object]]:
    """The notes a search hit, then every other shared entry whose path matches.

    The full text of the markdown notes is searchable; a PDF, a picture or a
    folder can only answer to its name, so they come after the notes, newest
    first, with no matching lines. `hits` is empty rather than missing: the
    picker draws those rows as a plain link, as it already does for a note
    whose path is what matched.
    """
    if not terms:
        return found
    seen = {entry["p"] for entry in found}
    rest = []
    for entry in notes_entries(index):
        relative = str(entry["p"])
        if relative in seen or not all(term in notes.fold(relative) for term in terms):
            continue
        # A file swapped for a symlink since the scan keeps its name in the
        # index, so ask the same question the text search asks before listing it.
        if entry["k"] != "folder" and notes.allowed(index, relative) is None:
            continue
        rest.append({**entry, "hits": []})
    rest.sort(key=lambda entry: -int(entry.get("t", 0)))  # type: ignore[arg-type]
    return found + rest[: max(0, notes.SEARCH_NOTES_MAX - len(found))]


def json_script(value: object) -> str:
    """JSON for a data <script>, escaped so no "</script>" in it can close the block early."""
    return (
        json.dumps(value)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )


def markdown_page(
    title: str,
    text: str,
    notice: str | None,
    back: tuple[str, str],
    links: list[tuple[str, str]],
    project: str | None = None,
    comments: str = "",
    note_links: dict[str, dict[str, str] | None] | None = None,
    crumbs: list[tuple[str, str]] | None = None,
    icon: str = "",
    local_root: str = "",
) -> tuple[bytes, str]:
    """The reader page and the nonce its scripts run under. The browser renders the markdown.

    With a comments URL the page also offers review mode, for line comments kept on the server.
    With note_links it reads an Obsidian note: links go through that map.
    """
    nonce = secrets.token_urlsafe(16)
    bases = (
        f' data-poub="/poub/{quote(project)}/" data-md="/md/{quote(project)}/"'
        if project
        else ""
    )
    extra = ""
    if local_root:
        bases += f' data-local-root="{html.escape(local_root)}"'
    if note_links is not None:
        bases += " data-notes"
        if notes.VAULT and not notes.VAULT.strict_breaks:
            bases += " data-breaks"
        extra = f'<script type="application/json" id="notes-links">{json_script(note_links)}</script>'
    trail = (
        '<nav class="crumbs" aria-label="Folders">'
        + "".join(
            f'<a href="{html.escape(href)}">{html.escape(label)}</a><span aria-hidden="true">/</span>'
            for label, href in crumbs
        )
        + f'<b aria-current="page">{icon}{html.escape(title)}</b>'
        + "</nav>"
        if crumbs
        else ""
    )
    if comments:
        bases += f' data-comments="{html.escape(comments)}" data-comment-max="{COMMENT_MAX_CHARS}"'
    review = (REVIEW_BUTTON, REVIEW_DOCK) if comments else ("", "")
    tools = theme_select(nonce) if local_root else qr_button() + search_button()
    tools_script = "" if local_root else qr_script(nonce) + search_script(nonce)
    favicon = "data:," if local_root else "/icon-192.png"
    actions = "".join(
        f'<a href="{html.escape(href)}"{" download" if label == "Download" else ""}>{html.escape(label)}</a>'
        for label, href in links
    )
    banner = (
        f'<p class="notice" role="status">{html.escape(notice)}</p>' if notice else ""
    )
    source = json_script(text)
    highlight = len(text.encode("utf-8")) <= HIGHLIGHT_MAX_BYTES
    scripts = "".join(
        f'<script nonce="{nonce}" src="/vendor/{name}"></script>'
        for name in MARKDOWN_SCRIPTS
        if highlight or name != "highlight.min.js"
    )
    document = f"""<!doctype html>
<html lang="en" data-theme-default="{THEME_DEFAULT}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{html.escape(title)}</title>
{theme_script(nonce)}
<link rel="icon" href="{favicon}">
<link rel="stylesheet" href="/vendor/github-markdown.css">
<style>{MARKDOWN_CSS}{READER_CSS}{THEME_READER_CSS}{QR_CSS}</style></head><body>
<header class="bar progress"><a href="{html.escape(back[1])}">← {html.escape(back[0])}</a><span class="name">{html.escape(title)}</span><nav>{actions}{PRESENT_BUTTON}{review[0]}{qr_button()}{search_button()}</nav></header>
<main class="page reader">{trail}{banner}
<details class="toc" id="toc" hidden><summary>Contents</summary><ol></ol></details>
<article class="markdown-body"{bases}><noscript><pre>{html.escape(text)}</pre></noscript></article></main>
{review[1]}
<script type="application/json" id="markdown-source">{source}</script>
{extra}
{scripts}
<script nonce="{nonce}">{MARKDOWN_JS}</script>
{tools_script}
</body></html>"""
    return document.encode("utf-8"), nonce


def code_page(
    name: str,
    text: str,
    links: list[tuple[str, str]],
    back: tuple[str, str] = ("Drop", "/drop"),
) -> tuple[bytes, str]:
    """A dropped text file with line numbers, highlighted in the browser by the vendored highlight.js."""
    nonce = secrets.token_urlsafe(16)
    text = text.replace("\r\n", "\n")
    lines = text.count("\n") + (0 if text.endswith("\n") or not text else 1)
    gutter = "".join(
        f'<a id="L{number}" href="#L{number}">{number}</a>'
        for number in range(1, max(lines, 1) + 1)
    )
    actions = "".join(
        f'<a href="{html.escape(href)}"{" download" if label == "Download" else ""}>{html.escape(label)}</a>'
        for label, href in links
    )
    highlight = len(text.encode("utf-8")) <= HIGHLIGHT_MAX_BYTES
    notice = (
        ""
        if highlight
        else '<p class="notice" role="status">Over 512 KB, shown without highlighting.</p>'
    )
    language = (
        f' data-lang="{html.escape(code_language(name, text))}"' if highlight else ""
    )
    document = f"""<!doctype html>
<html lang="en" data-theme-default="{THEME_DEFAULT}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{html.escape(name)}</title>
{theme_script(nonce)}
<link rel="icon" href="/icon-192.png">
<style>{MARKDOWN_CSS}{CODE_CSS}{THEME_READER_CSS}{QR_CSS}</style></head><body>
<header class="bar"><a href="{html.escape(back[1])}">← {html.escape(back[0])}</a><span class="name">{html.escape(name)}</span><nav>{actions}{qr_button()}{search_button()}</nav></header>
<main class="page code-page">{notice}
<div class="code"><div class="gutter">{gutter}</div><div class="scroll"><div class="line-mark" id="line-mark" hidden></div><pre><code id="code"{language}>{html.escape(text)}</code></pre></div></div>
</main>
{f'<script nonce="{nonce}" src="/vendor/highlight.min.js"></script>' if highlight else ""}
<script nonce="{nonce}">{CODE_JS}</script>
{qr_script(nonce)}{search_script(nonce)}
</body></html>"""
    return document.encode("utf-8"), nonce


def code_headers(nonce: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"script-src 'nonce-{nonce}'; connect-src 'self'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'self'"
        ),
    }


def play_page(project: str, name: str) -> tuple[bytes, str]:
    """A dropped video or audio file in the browser's own player, streamed from /poub."""
    nonce = secrets.token_urlsafe(16)
    url = html.escape(f"/poub/{quote(project)}/{quote(name)}")
    if Path(name).suffix.lower() in AUDIO_TYPES:
        player = f'<audio src="{url}" controls preload="metadata"></audio>'
    else:
        player = f'<video src="{url}" controls playsinline preload="metadata"></video>'
    document = f"""<!doctype html>
<html lang="en" data-theme-default="{THEME_DEFAULT}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{html.escape(name)}</title>
{theme_script(nonce)}
<link rel="icon" href="/icon-192.png">
<style>{MARKDOWN_CSS}{PLAY_CSS}{THEME_READER_CSS}{QR_CSS}</style></head><body>
<header class="bar"><a href="/drop">← Drop</a><span class="name">{html.escape(name)}</span><nav><a href="{url}" download>Download</a>{qr_button()}{search_button()}</nav></header>
<main class="page play-page">{player}</main>
{qr_script(nonce)}{search_script(nonce)}
</body></html>"""
    return document.encode("utf-8"), nonce


def play_headers(nonce: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; img-src 'self'; media-src 'self'; connect-src 'self'; "
            f"style-src 'self' 'unsafe-inline'; script-src 'nonce-{nonce}'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        ),
    }


def pdf_page(
    name: str, url: str, back: tuple[str, str] = ("Drop", "/drop")
) -> tuple[bytes, str]:
    """A PDF drawn page by page with pdf.js, fetched from url."""
    nonce = secrets.token_urlsafe(16)
    url = html.escape(url)
    document = f"""<!doctype html>
<html lang="en" data-theme-default="{THEME_DEFAULT}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{html.escape(name)}</title>
{theme_script(nonce)}
<link rel="icon" href="/icon-192.png">
<style>{MARKDOWN_CSS}{PDF_CSS}{THEME_READER_CSS}{QR_CSS}</style></head><body>
<header class="bar"><a href="{html.escape(back[1])}">← {html.escape(back[0])}</a><span class="name">{html.escape(name)}</span><nav><a href="{url}" download>Download</a>{qr_button()}{search_button()}</nav></header>
<main class="page pdf-page" data-url="{url}"><p class="pdf-status">Loading…</p></main>
<script type="module" nonce="{nonce}">{PDF_JS}</script>
{qr_script(nonce)}{search_script(nonce)}
</body></html>"""
    return document.encode("utf-8"), nonce


def pdf_headers(nonce: str) -> dict[str, str]:
    # The worker has to be a URL, so worker-src allows 'self'; scripts stay nonce-only,
    # which the module imports inherit, so an uploaded .js still cannot run here.
    return {
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; img-src 'self' blob: data:; connect-src 'self'; "
            f"worker-src 'self'; style-src 'self' 'unsafe-inline'; script-src 'nonce-{nonce}'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        ),
    }


def markdown_headers(nonce: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'self'; img-src 'self' https: data:; style-src 'self' 'unsafe-inline'; "
            f"script-src 'self' 'nonce-{nonce}'; object-src 'none'; base-uri 'none'; "
            "form-action 'none'; frame-ancestors 'self'"
        ),
    }


def counts(
    artifacts: list[dict[str, str]], shots: list[dict[str, str]], files: list[PoubFile]
) -> Counts:
    return Counts(
        artifacts=len(artifacts),
        shots=len(shots),
        clip=len(clip_snapshot()["text"]),
        drop=len(files),
    )


def clip_save_locked() -> None:
    temporary = CLIP_FILE.with_name(f".clip-{secrets.token_hex(4)}.part")
    try:
        CLIP_FILE.parent.mkdir(parents=True, exist_ok=True)
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(dict(CLIP), stream)
        os.replace(temporary, CLIP_FILE)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        print(f"cannot save clipboard: {error}")


def clip_load() -> None:
    try:
        data = json.loads(CLIP_FILE.read_text(encoding="utf-8"))
        text, version = str(data["text"]), int(data["version"])
        updated, ttl = (
            float(data["updated"]),
            max(0, min(int(data["ttl"]), CLIP_MAX_TTL)),
        )
        history = [
            ClipEntry(
                id=int(entry["id"]),
                text=str(entry["text"]),
                updated=float(entry["updated"]),
                ttl=max(0, min(int(entry["ttl"]), CLIP_MAX_TTL)),
            )
            for entry in data.get("history", [])
        ][:CLIP_HISTORY_MAX]
    except FileNotFoundError:
        return
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"ignoring saved clipboard {CLIP_FILE}: {error}")
        return
    with CLIP_LOCK:
        CLIP.update(
            text=text, version=version, updated=updated, ttl=ttl, history=history
        )
        clip_expire_locked()


def clip_state_locked() -> ClipState:
    return ClipState(
        text=CLIP["text"],
        version=CLIP["version"],
        updated=CLIP["updated"],
        ttl=CLIP["ttl"],
        history=[ClipEntry(**entry) for entry in CLIP["history"]],
    )


def clip_entry_expired(entry: ClipEntry, now: float) -> bool:
    return bool(entry["ttl"]) and entry["updated"] + entry["ttl"] <= now


def clip_expire_locked() -> None:
    now = time.time()
    changed = False
    if CLIP["text"] and CLIP["ttl"] and CLIP["updated"] + CLIP["ttl"] <= now:
        CLIP["text"] = ""
        CLIP["updated"] = 0.0
        changed = True
    history = [entry for entry in CLIP["history"] if not clip_entry_expired(entry, now)]
    if len(history) != len(CLIP["history"]):
        CLIP["history"] = history
        changed = True
    if changed:
        CLIP["version"] += 1
        clip_save_locked()


def clip_snapshot() -> ClipState:
    with CLIP_LOCK:
        clip_expire_locked()
        return clip_state_locked()


def clip_store(text: str) -> ClipState:
    """Set the clip. Unless the clip is being cleared, the text it replaces moves to the front of the history."""
    with CLIP_LOCK:
        clip_expire_locked()
        history = [entry for entry in CLIP["history"] if entry["text"] != text]
        previous = CLIP["text"]
        if text and previous and previous != text:
            history = [entry for entry in history if entry["text"] != previous]
            history.insert(
                0,
                ClipEntry(
                    id=CLIP["version"],
                    text=previous,
                    updated=CLIP["updated"],
                    ttl=CLIP["ttl"],
                ),
            )
        CLIP["history"] = history[:CLIP_HISTORY_MAX]
        CLIP["text"] = text
        CLIP["version"] += 1
        CLIP["updated"] = time.time() if text else 0.0
        clip_save_locked()
        return clip_state_locked()


def clip_history_entry(entry_id: int) -> ClipEntry | None:
    with CLIP_LOCK:
        clip_expire_locked()
        return next(
            (ClipEntry(**e) for e in CLIP["history"] if e["id"] == entry_id), None
        )


def clip_history_delete(entry_id: int | None) -> ClipState | None:
    """Drop one history entry, or all of them when entry_id is None."""
    with CLIP_LOCK:
        clip_expire_locked()
        history = [
            entry
            for entry in CLIP["history"]
            if entry_id is not None and entry["id"] != entry_id
        ]
        if len(history) == len(CLIP["history"]) and entry_id is not None:
            return None
        CLIP["history"] = history
        CLIP["version"] += 1
        clip_save_locked()
        return clip_state_locked()


def clip_set_ttl(seconds: int) -> ClipState:
    ttl = max(0, min(seconds, CLIP_MAX_TTL))
    with CLIP_LOCK:
        clip_expire_locked()
        if ttl != CLIP["ttl"]:
            CLIP["ttl"] = ttl
            CLIP["version"] += 1
            clip_save_locked()
        return clip_state_locked()


def clip_json(state: ClipState) -> dict[str, object]:
    return {
        "public_url": PUBLIC_URL,
        "text": state["text"],
        "version": state["version"],
        "updated": state["updated"],
        "chars": len(state["text"]),
        "ttl": state["ttl"],
        "expires_at": state["updated"] + state["ttl"]
        if state["updated"] and state["ttl"]
        else 0,
        "history": [
            {
                "id": entry["id"],
                "text": entry["text"],
                "updated": entry["updated"],
                "chars": len(entry["text"]),
                "expires_at": entry["updated"] + entry["ttl"] if entry["ttl"] else 0,
            }
            for entry in state["history"]
        ],
    }


def clip_page(state: ClipState, tab_counts: Counts) -> bytes:
    text = state["text"]
    updated = state["updated"]
    characters = len(text)
    payload = json.dumps(clip_json(state)).replace("</", "<\\/")
    if updated:
        left = max(0, int(updated + state["ttl"] - time.time())) if state["ttl"] else 0
        updated_label = (
            f"{datetime.fromtimestamp(updated).strftime('%b %-d, %H:%M:%S')}"
            f" · {characters} {'char' if characters == 1 else 'chars'}"
        )
        expiry_label = (
            f"clears in {left // 60}:{left % 60:02d}"
            if state["ttl"]
            else "never clears"
        )
    else:
        updated_label = "Nothing shared yet"
        expiry_label = "in memory"
    choices = "".join(
        f'<button type="button" data-ttl="{seconds}" aria-pressed="{"true" if state["ttl"] == seconds else "false"}">'
        f"{label}</button>"
        for seconds, label in (
            (60, "1 min"),
            (600, "10 min"),
            (3600, "1 hour"),
            (0, "Never"),
        )
    )
    body = f"""
  <header><h1>Clipboard</h1><p class="intro">Kept in memory only and cleared after the time you pick below.</p></header>
  <div class="shelf-label"><span>Shared clipboard</span><span class="count" id="clip-count">{characters} {"char" if characters == 1 else "chars"}</span></div>
  <section class="clip-card">
    <div class="clip-meta"><span id="clip-updated">{updated_label}</span><span id="clip-expiry">{expiry_label}</span></div>
    <div class="clip-ttl"><span>Clear after</span>{choices}</div>
    <div class="clip-link" id="clip-link" hidden><a target="_blank" rel="noopener noreferrer"></a>{'<span class="clip-ttl"><button type="button" data-qr>QR</button></span>' if QR_ENABLED else ""}</div>
    <textarea id="clip-text" placeholder="Paste or type here, then hit Send." spellcheck="false" autocapitalize="off" autocomplete="off" aria-label="Shared clipboard text">{html.escape(text)}</textarea>
    <div class="clip-actions">
      <button id="copy" class="primary" type="button">Copy</button>
      <button id="send" type="button">Send</button>
      <button id="paste" type="button">Paste</button>
      <button id="clear" type="button">Clear</button>
      <a id="rendered" class="wide" href="/clip/md">Read as markdown</a>
      <button id="reload" class="wide" type="button" hidden>Load the new text</button>
    </div>
    <p class="clip-status" id="clip-status" role="status" aria-live="polite"></p>
    <p class="clip-note">From a terminal: <code>curl -H 'Content-Type: text/plain' --data-binary 'some text' http://HOST:PORT/clip</code> to send, <code>curl http://HOST:PORT/clip/raw</code> to read, <code>?n=1</code> for the previous one.</p>
  </section>
  <section class="clip-history" id="clip-history"{"" if state["history"] else " hidden"}>
    <div class="shelf-label"><span>Earlier</span><span class="shelf-actions"><button class="wipe" id="history-clear" type="button">Forget all</button></span></div>
    <ol></ol>
  </section>
  <script id="clip-state" type="application/json">{payload}</script>
  <script>{CLIP_JS}</script>"""
    return layout("Clipboard", "clip", tab_counts, body, extra_css=CLIP_CSS)


def drop_page(files: list[PoubFile], tab_counts: Counts) -> bytes:
    groups: dict[str, list[str]] = {}
    for entry in files:
        name = html.escape(entry["name"])
        is_html = Path(entry["name"]).suffix.lower() in HTML_SUFFIXES
        href = f"/poub/{entry['url']}"
        if entry["image"]:
            src = entry["thumb"] or f"/poub/{entry['url']}"
            thumb = f'<img src="{src}" alt="" loading="lazy" decoding="async">'
            action = "Open"
            download = ""
        elif Path(entry["name"]).suffix.lower() in VIDEO_SUFFIXES:
            thumb = (
                f'<video src="/poub/{entry["url"]}#t=0.1" muted playsinline preload="metadata" '
                'tabindex="-1" aria-hidden="true"></video><span class="play-mark" aria-hidden="true">▶</span>'
            )
            action = "Play"
            download = ""
            href = f"/play/{entry['url']}"
        elif Path(entry["name"]).suffix.lower() in AUDIO_TYPES:
            thumb = '<span aria-hidden="true">♪</span>'
            action = "Play"
            download = ""
            href = f"/play/{entry['url']}"
        elif Path(entry["name"]).suffix.lower() == ".pdf":
            thumb = '<span class="pdf-mark" aria-hidden="true">PDF</span>'
            action = "Read"
            download = ""
            href = f"/pdf/{entry['url']}"
        elif is_markdown(entry["name"]):
            thumb = '<span aria-hidden="true">¶</span>'
            action = "Read"
            download = ""
            href = f"/md/{entry['url']}"
        elif is_html:
            thumb = (
                f'<iframe src="/poub/{entry["url"]}" sandbox="" tabindex="-1" aria-hidden="true" '
                'loading="lazy" scrolling="no"></iframe>'
            )
            action = "Open"
            download = ' target="_blank" rel="noopener"'
        elif entry["text"]:
            thumb = '<span aria-hidden="true">&lt;/&gt;</span>'
            action = "View"
            download = ""
            href = f"/view/{entry['url']}"
        else:
            thumb = '<span aria-hidden="true">▤</span>'
            action = "Get"
            download = " download"
        annotate = ""
        share = ""
        qr = (
            f'<button class="file-qr" type="button" data-qr="{html.escape(href)}" aria-label="QR code for {name}">▦</button>'
            if QR_ENABLED
            else ""
        )
        if Path(entry["name"]).suffix.lower() in ANNOTATE_TYPES:
            annotate = (
                f'<button class="file-annotate" type="button" data-annotate data-target="drop" '
                f'data-key="{entry["url"]}" data-url="/poub/{entry["url"]}" '
                f'aria-label="Annotate {name}">✎</button>'
            )
            share = (
                f'<button class="file-share" type="button" data-share="/poub/{entry["url"]}" '
                f'data-name="{name}" aria-label="Share {name}" hidden>↗</button>'
            )
        expires = f"{entry['expires']:.0f}" if entry["expires"] else ""
        groups.setdefault(entry["project"], []).append(f"""
          <div class="file-row{" has-tools" if annotate else ""}">
            <a class="file" href="{href}"{download}>
              <span class="file-thumb">{thumb}</span>
              <span class="file-copy"><strong>{name}</strong><small>{entry["size"]} <i>·</i> {entry["date"]}<span class="expires-left" data-expires-left="{expires}" data-prefix=" · expires in " hidden></span></small></span>
              <span class="file-action">{action}</span>
            </a>
            <span class="file-tools">{qr}{share}{annotate}<button class="file-expiry" type="button" data-expiry data-compact data-target="poub" data-key="{entry["url"]}" data-expires="{expires}" aria-label="Expiry for {name}">⏱</button><button class="file-delete" type="button" data-url="{entry["url"]}" aria-label="Delete {name}">✕</button></span>
          </div>""")
    wipe = (
        '<button class="wipe" id="delete-all" type="button">Delete all</button>'
        if groups
        else ""
    )
    listing = (
        "".join(
            f'<section class="drop-group"><div class="drop-head"><h2>{html.escape(project)} <span class="checkout">{len(rows)}</span></h2>'
            f"{wipe_project(project, len(rows)) if len(groups) > 1 else ''}</div>"
            f'<div class="file-list">{"".join(rows)}</div></section>'
            for project, rows in groups.items()
        )
        or '<div class="empty"><span>▤</span><h2>Nothing dropped yet</h2><p>Files you send from any device show up here.</p></div>'
    )
    options = "".join(
        f'<option value="{html.escape(name)}">{html.escape(name)}</option>'
        for name in known_projects()
    )
    root = html.escape(pretty_path(ROOT))
    body = f"""
  <header><h1>Drop</h1><p class="intro">Saved in {root}/&lt;project&gt;/drop. The Share menu saves to {html.escape(DEFAULT_PROJECT)}.</p></header>
  <div class="shelf-label"><span>Shared files</span><span class="shelf-actions"><span class="count">{len(files)} {"file" if len(files) == 1 else "files"}</span>{wipe}</span></div>
  <label class="project-pick">Save to <select id="project">{options}<option value="__new">New project…</option></select></label>
  <section class="drop-zone{" compact" if files else ""}" id="zone">
    <input id="file-input" type="file" multiple hidden>
    <button class="drop-button" id="pick" type="button">
      <span class="drop-icon" aria-hidden="true">⇪</span>
      <strong>Choose files</strong>
      <small>or drop them here · paste a screenshot or text with Ctrl/⌘+V</small>
    </button>
  </section>
  <ul class="upload-queue" id="queue" aria-live="polite"></ul>
  {listing}
  <footer>From a terminal: <code>curl --data-binary @FILE 'http://HOST:PORT/upload?project={html.escape(DEFAULT_PROJECT)}&amp;name=FILE'</code></footer>
  <script>{DROP_JS}</script>
  <script>{ANNOTATE_JS}</script>
  <script>{EXPIRY_JS}</script>
  <script>{SHARE_JS}</script>
  {live_script("drop", live_stamp(poub_paths()))}"""
    return layout("Drop files", "drop", tab_counts, body, extra_css=DROP_CSS)


def counts_now() -> Counts:
    return counts(available_artifacts(), available_shots(), poub_files())


def notes_crumbs(folder: str) -> list[tuple[str, str]]:
    """Notes, then each folder down to this one, as (label, URL)."""
    parts = folder.split("/") if folder else []
    return [("Notes", "/notes")] + [
        (part, notes.url("/notes/", "/".join(parts[: depth + 1])) + "/")
        for depth, part in enumerate(parts)
    ]


def read_note(path: Path) -> str | None:
    try:
        if path.stat().st_size > notes.MAX_NOTE_BYTES:
            return None
        return path.read_text("utf-8", errors="replace")
    except OSError:
        return None


def notes_icon(index: notes.Index, relative: str) -> str:
    """The Icon Fairy icon Obsidian shows for this note or folder, as an <img>."""
    name = index.icons.get(relative)
    if not name:
        return ""
    return f'<img class="note-icon" src="{notes.url("/notes-icon/", name)}" alt="">'


# Rows behind the filter box; the tree itself is not capped.
NOTES_FILTER_MAX = 2000


def notes_row(index: notes.Index, relative: str, show_folder: bool) -> str:
    path = index.files[relative]
    name = posixpath.basename(relative)
    suffix = posixpath.splitext(name)[1].lower()
    file_url = notes.url("/notes-file/", relative)
    download = ""
    if notes.is_markdown(name):
        thumb, action, href = NOTE_ICON, "Read", None
        name = posixpath.splitext(name)[0]
    elif suffix in IMAGE_LIKE_SUFFIXES:
        thumb = f'<img src="{file_url}" alt="" loading="lazy" decoding="async">'
        action, href = "Open", file_url
    elif suffix == ".pdf":
        thumb = '<span class="pdf-mark" aria-hidden="true">PDF</span>'
        action, href = "Read", notes.url("/notes-pdf/", relative)
    elif suffix in MEDIA_SUFFIXES:
        thumb, action, href = '<span aria-hidden="true">▶</span>', "Play", file_url
    elif looks_like_text(path):
        thumb, action, href = '<span aria-hidden="true">&lt;/&gt;</span>', "View", None
    else:
        thumb, action, href = '<span aria-hidden="true">▤</span>', "Get", file_url
        download = " download"
    if icon := notes_icon(index, relative):
        thumb = icon
    try:
        info = path.stat()
        changed = int(info.st_mtime)
        meta = f"{human_size(info.st_size)} <i>·</i> {datetime.fromtimestamp(info.st_mtime):%b %-d, %Y}"
    except OSError:
        changed, meta = 0, ""
    if show_folder:
        meta = f"{html.escape(posixpath.dirname(relative))} <i>·</i> {meta}"
    return (
        f'<a class="file" href="{href or notes.url("/notes/", relative)}"{download} '
        f'data-path="{html.escape(relative.lower())}" data-name="{html.escape(name.lower())}" '
        f'data-time="{changed}">'
        f'<span class="file-thumb">{thumb}</span>'
        f'<span class="file-copy"><strong>{html.escape(name)}</strong><small>{meta}</small></span>'
        f'<span class="file-action">{action}</span></a>'
    )


def notes_page(index: notes.Index, folder: str, tab_counts: Counts) -> bytes:
    """A shared folder of the vault: its subfolders, then its files, and a filter over
    everything below it."""
    prefix = folder + "/" if folder else ""
    changed: dict[str, float] = {}
    for relative in index.shared:
        if relative.startswith(prefix):
            try:
                changed[relative] = index.files[relative].stat().st_mtime
            except OSError:
                changed[relative] = 0.0
    # Newest first, then by name.
    below = sorted(changed, key=lambda relative: (-changed[relative], relative.lower()))
    folders: dict[str, tuple[int, float]] = {}
    files = []
    for relative in below:
        rest = relative[len(prefix) :]
        if "/" in rest:
            name = rest.split("/", 1)[0]
            size, newest = folders.get(name, (0, changed[relative]))
            folders[name] = (size + 1, newest)
        else:
            files.append(relative)
    rows = [
        f'<a class="file" href="{notes.url("/notes/", prefix + name)}/" data-folder '
        f'data-name="{html.escape(name.lower())}" data-time="{int(newest)}">'
        f'<span class="file-thumb folder-mark">{notes_icon(index, prefix + name) or FOLDER_ICON}</span>'
        f'<span class="file-copy"><strong>{html.escape(name)}</strong>'
        f"<small>{size} {'file' if size == 1 else 'files'} <i>·</i> "
        f"{datetime.fromtimestamp(newest):%b %-d, %Y}</small></span>"
        '<span class="file-action">Open</span></a>'
        for name, (size, newest) in folders.items()
    ] + [notes_row(index, relative, False) for relative in files]
    results = "".join(
        notes_row(index, relative, True) for relative in below[:NOTES_FILTER_MAX]
    )
    title = posixpath.basename(folder) if folder else "Notes"
    trail = ""
    if folder:
        trail = (
            '<nav class="notes-crumbs" aria-label="Folders">'
            + "".join(
                f'<a href="{html.escape(href)}">{html.escape(label)}</a><span aria-hidden="true">/</span>'
                for label, href in notes_crumbs(posixpath.dirname(folder))
            )
            + "</nav>"
        )
        intro = ""
    else:
        intro = '<p class="intro">Read-only folders from your Obsidian vault.</p>'
    listing = (
        f'<div class="file-list note-tree" id="note-tree">{"".join(rows)}</div>'
        if rows
        else '<div class="empty note-tree" id="note-tree"><span>¶</span><h2>No notes here</h2><p>Notes added to this folder show up after a reload.</p></div>'
    )
    total = f"{len(below)} {'file' if len(below) == 1 else 'files'}"
    body = f"""
  <header>{trail}<h1>{notes_icon(index, folder)}{html.escape(title)}</h1>{intro}</header>
  <input class="note-filter" id="note-filter" type="search" placeholder="Filter by name" aria-label="Filter notes by name" autocomplete="off">
  <div class="shelf-label"><span>{"Shared folders" if not folder else "In this folder"}</span><span class="shelf-actions"><span class="count" id="note-count">{total}</span><button class="note-sort" id="note-sort" type="button" hidden>{SORT_ICON}<span>Newest</span></button></span></div>
  {listing}
  <div class="file-list note-results" id="note-results" hidden>{results}</div>
  <script>{NOTES_JS}</script>"""
    return layout(
        f"{html.escape(title)} · Notes",
        "notes",
        tab_counts,
        body,
        extra_css=DROP_CSS + NOTES_CSS,
    )


def artifacts_page(artifacts: list[dict[str, str]], tab_counts: Counts) -> bytes:
    sections = []
    groups: dict[tuple[str, str], list[dict[str, str]]] = {}
    for apk in artifacts:
        groups.setdefault((apk["app"], apk["checkout"]), []).append(apk)

    for (app_name, checkout), items in groups.items():
        buttons = []
        for apk in items:
            buttons.append(f"""
                <a class="download" href="/download/{apk["key"]}" download>
                  <span class="button-icon" aria-hidden="true">↓</span>
                  <span class="button-copy"><strong>{html.escape(apk["label"])}</strong>
                    <small><span class="apk-meta">{apk["date"]} <i>·</i> {apk["size"]}</span><i>·</i><span class="apk-path">{html.escape(apk["relative"])}</span></small></span>
                  <span class="button-action">{"Install" if apk["relative"].endswith(".apk") else "Download"}</span>
                </a>""")
        section_label = (
            f'<span class="checkout">{html.escape(checkout)}</span>'
            if checkout != "main checkout"
            else ""
        )
        sections.append(f"""
          <section class="app-section">
            <div class="section-heading"><h2>{html.escape(app_name)}</h2>{section_label}</div>
            <div class="downloads">{"".join(buttons)}</div>
          </section>""")

    if not sections:
        empty = '<div class="empty"><span>□</span><h2>No artifacts found yet</h2><p>Add an <code>[[artifacts]]</code> entry to the config, build something, then refresh this page.</p></div>'
    else:
        empty = ""
    body = f"""
  <header><h1>Artifacts</h1><p class="intro">Builds from the projects in your config. Tap one to download it.</p></header>
  <div class="shelf-label"><span>Latest first</span><span class="count">{len(artifacts)} {"file" if len(artifacts) == 1 else "files"}</span></div>
  {"".join(sections)}{empty}
  <footer>Android may ask you to allow installs from your browser the first time you open an APK.</footer>"""
    return layout("Artifacts", "artifacts", tab_counts, body)


def wipe_project(project: str, count: int) -> str:
    name = html.escape(project)
    return (
        f'<button class="wipe" type="button" data-wipe-project="{name}" data-count="{count}" '
        f'aria-label="Delete everything in {name}">Delete</button>'
    )


def shots_page(shots: list[dict[str, str]], tab_counts: Counts) -> bytes:
    sections = []
    groups: dict[str, list[tuple[int, dict[str, str]]]] = {}
    for index, shot in enumerate(shots):
        groups.setdefault(shot["project"], []).append((index, shot))
    for project, items in groups.items():
        tiles = "".join(
            f"""
              <div class="tile-wrap">
                <a class="tile" href="{shot["url"]}" data-index="{index}">
                  <img src="{shot["thumb"]}" alt="{html.escape(shot["name"])}" loading="lazy" decoding="async">
                  <span>{html.escape(shot["name"])}</span>
                </a>{f'<span class="tile-expiry" data-expires-left="{shot["expires"]}" data-prefix="⏱ " hidden></span>' if shot["expires"] else ""}
                <button class="tile-delete" type="button" data-key="{shot["key"]}" aria-label="Delete {html.escape(shot["name"])}">✕</button>
              </div>"""
            for index, shot in items
        )
        sections.append(f"""
          <section class="app-section">
            <div class="section-heading"><h2>{html.escape(project)}</h2><span class="shelf-actions"><span class="checkout">{len(items)}</span>{wipe_project(project, len(items)) if len(groups) > 1 else ""}</span></div>
            <div class="gallery">{tiles}</div>
          </section>""")

    if sections:
        empty = ""
    else:
        empty = (
            '<div class="empty"><span>□</span><h2>No screenshots yet</h2><p>Save images in '
            f"{html.escape(pretty_path(ROOT))}/&lt;project&gt;/shots and they show up here.</p></div>"
        )
    wipe = (
        '<button class="wipe" id="delete-all" type="button">Delete all</button>'
        if shots
        else ""
    )
    data = json.dumps(
        [
            {
                key: shot[key]
                for key in ("project", "name", "date", "key", "url", "thumb", "expires")
            }
            for shot in shots
        ]
    )
    body = f"""
  <header><h1>Screenshots</h1><p class="intro">From {html.escape(pretty_path(ROOT))}/*/shots. Tap one to open it.</p></header>
  <div class="shelf-label"><span>Newest first</span><span class="shelf-actions"><span class="count">{len(shots)} {"shot" if len(shots) == 1 else "shots"}</span>{wipe}</span></div>
  {"".join(sections)}{empty}
  <div class="viewer" id="viewer" hidden role="dialog" aria-modal="true" aria-label="Screenshot viewer">
    <div class="viewer-bar"><span class="counter" id="counter"></span>
      <span class="viewer-tools"><button class="annotate" id="annotate-shot" type="button" data-annotate
        data-target="shots" hidden>Annotate</button>
      <button class="share" id="share-shot" type="button" hidden>Share</button>
      <button class="expiry-button" id="expiry-shot" type="button" data-expiry data-target="shot"
        data-label="Expire">Expire</button>
      <button class="wipe" id="delete-shot" type="button">Delete</button>
      <button class="close" id="close" type="button" aria-label="Close">✕</button></span></div>
    <button class="nav prev" id="prev" type="button" aria-label="Previous">‹</button>
    <div class="stage" id="stage"><img id="photo" alt=""></div>
    <button class="nav next" id="next" type="button" aria-label="Next">›</button>
    <div class="caption"><strong id="caption-name"></strong><small id="caption-meta"></small></div>
  </div>
  <script id="shots" type="application/json">{data.replace("</", "<\\/")}</script>
  <script>{CAROUSEL_JS}</script>
  <script>{ANNOTATE_JS}</script>
  <script>{EXPIRY_JS}</script>
  <script>{SHARE_JS}</script>
  {live_script("shots", live_stamp(shot_files()))}"""
    return layout("Screenshots", "shots", tab_counts, body, wide=True)


ICON_SIZES = (192, 512)
MANIFEST = {
    "name": "Sharei",
    "short_name": "Sharei",
    "start_url": "/clip",
    "scope": "/",
    "display": "standalone",
    "background_color": "#111820",
    "theme_color": "#111820",
    "icons": [
        {"src": f"/icon-{size}.png", "sizes": f"{size}x{size}", "type": "image/png"}
        for size in ICON_SIZES
    ],
    "share_target": {
        "action": "/share",
        "method": "POST",
        "enctype": "multipart/form-data",
        "params": {
            "title": "title",
            "text": "text",
            "url": "url",
            "files": [{"name": "files", "accept": ["*/*"]}],
        },
    },
}


@functools.cache
def icon_png(size: int) -> bytes:
    """Two overlapping mint squares (a copy glyph) on the page background, drawn without Pillow."""
    background, mint = bytes((0x11, 0x18, 0x20)), bytes((0xA5, 0xF2, 0xD1))
    stroke, radius = size * 0.055, size * 0.07

    def inside(
        x: float, y: float, box: tuple[float, float, float, float], inset: float = 0
    ) -> bool:
        left, top, right, bottom = (
            box[0] + inset,
            box[1] + inset,
            box[2] - inset,
            box[3] - inset,
        )
        if not (left <= x <= right and top <= y <= bottom):
            return False
        corner = max(radius - inset, 0)
        nearest_x = min(max(x, left + corner), right - corner)
        nearest_y = min(max(y, top + corner), bottom - corner)
        return (x - nearest_x) ** 2 + (y - nearest_y) ** 2 <= corner**2

    back = (size * 0.22, size * 0.32, size * 0.62, size * 0.78)
    front = (size * 0.38, size * 0.20, size * 0.78, size * 0.66)
    rows = bytearray()
    for row in range(size):
        rows.append(0)
        y = row + 0.5
        for column in range(size):
            x = column + 0.5
            if inside(x, y, front):
                rows += background if inside(x, y, front, stroke) else mint
            elif inside(x, y, back) and not inside(x, y, back, stroke):
                rows += mint
            else:
                rows += background

    def chunk(kind: bytes, data: bytes) -> bytes:
        return (
            len(data).to_bytes(4, "big")
            + kind
            + data
            + zlib.crc32(kind + data).to_bytes(4, "big")
        )

    header = size.to_bytes(4, "big") * 2 + bytes((8, 2, 0, 0, 0))
    return (
        b"\x89PNG\r\n\x1a\n"
        + chunk(b"IHDR", header)
        + chunk(b"IDAT", zlib.compress(bytes(rows), 9))
        + chunk(b"IEND", b"")
    )


def live_stamp(paths: list[Path]) -> str:
    digest = hashlib.sha256()
    for path in sorted(paths):
        try:
            stat = path.stat()
        except OSError:
            continue
        digest.update(
            f"{path}\0{stat.st_size}\0{stat.st_mtime_ns}\0{expires_at(path)}\n".encode(
                "utf-8", "surrogateescape"
            )
        )
    return digest.hexdigest()[:16]


def poub_paths(project: str | None = None) -> list[Path]:
    return [
        path
        for path in ROOT.glob(f"{project or '*'}/drop/*")
        if not path.name.startswith(".")
        and path.is_file()
        and valid_project(path.parent.parent.name)
        and under_root(path)
        and not expired(path)
    ]


RECENT_MAX = 50


def recent_payload(limit: int, project: str | None = None) -> dict[str, object]:
    now = time.time()
    state = clip_snapshot()
    stats = []
    for path in poub_paths(project):
        try:
            stats.append((path, path.stat()))
        except OSError:
            continue
    drop = []
    for path, stat in sorted(stats, key=lambda item: item[1].st_mtime, reverse=True)[
        :limit
    ]:
        drop.append(
            {
                "project": path.parent.parent.name,
                "name": path.name,
                "bytes": stat.st_size,
                "mtime": stat.st_mtime,
                "age_seconds": int(now - stat.st_mtime),
                "image": path.suffix.lower() in IMAGE_LIKE_SUFFIXES,
                **(
                    {
                        "thumb": f"/thumb/{quote(path.parent.parent.name)}"
                        f"/{quote(path.name)}"
                        f"?v={stat.st_mtime_ns}&t={THUMB_VERSION}"
                    }
                    if path.suffix.lower() in IMAGE_LIKE_SUFFIXES
                    else {}
                ),
                **({"expires": when} if (when := expires_at(path)) else {}),
                **({"comments": count} if (count := comments_count(path)) else {}),
                "url": f"/poub/{quote(path.parent.parent.name)}/{quote(path.name)}",
                **(
                    {"view": view}
                    if (view := view_url(path.parent.parent.name, path))
                    else {}
                ),
            }
        )
    shots = [
        {
            "project": shot["project"],
            "name": shot["name"],
            "mtime": float(shot["timestamp"]),
            "age_seconds": int(now - float(shot["timestamp"])),
            "url": shot["url"].split("?", 1)[0],
            **({"expires": float(shot["expires"])} if shot["expires"] else {}),
        }
        for shot in available_shots(project)[:limit]
    ]
    return {
        "public_url": PUBLIC_URL,
        "clip": {
            "chars": len(state["text"]),
            "updated": state["updated"],
            "age_seconds": int(now - state["updated"]) if state["updated"] else None,
            "ttl": state["ttl"],
            "expires_at": state["updated"] + state["ttl"]
            if state["updated"] and state["ttl"]
            else 0,
            "history": [
                {
                    "n": index,
                    "chars": len(entry["text"]),
                    "age_seconds": int(now - entry["updated"]),
                }
                for index, entry in enumerate(state["history"], start=1)
            ],
        },
        "drop": drop,
        "shots": shots,
    }


def live_script(kind: str, stamp: str) -> str:
    return f'<script data-kind="{kind}" data-stamp="{stamp}">{LIVE_JS}</script>'


def layout(
    title: str,
    active: str,
    tab_counts: Counts,
    body: str,
    wide: bool = False,
    extra_css: str = "",
) -> bytes:
    def tab(name: str, href: str, label: str, count: int, icon: str) -> str:
        current = ' aria-current="page"' if name == active else ""
        return (
            f'<a class="tab" href="{href}"{current}><span class="tab-icon" aria-hidden="true">{icon}</span>'
            f'{label}<span class="tab-count">{count or ""}</span></a>'
        )

    navigation = "".join(
        (
            tab("shots", "/shots", "Screenshots", tab_counts["shots"], "▣"),
            tab("drop", "/drop", "Drop", tab_counts["drop"], "⇪"),
            tab("clip", "/clip", "Clipboard", 0, "⎘"),
            tab("artifacts", "/artifacts", "Artifacts", tab_counts["artifacts"], "↓"),
            tab("notes", "/notes", "Notes", 0, "¶") if notes.VAULT else "",
        )
    )

    document = f"""<!doctype html>
<html lang="en" data-theme-default="{THEME_DEFAULT}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#111820"><title>{title}</title>
{theme_script()}
<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">
<link rel="icon" href="/icon-192.png">
<style>
{theme_app_css()}
  * {{ box-sizing:border-box }}
  body {{ margin:0; background:var(--base); color:var(--ink); font-family:ui-rounded,"SF Pro Rounded",system-ui,-apple-system,sans-serif; -webkit-font-smoothing:antialiased; }}
  .wrap {{ position:relative; width:min(100% - 36px, 620px); margin:0 auto; padding:18px 0 calc(90px + env(safe-area-inset-bottom)); }}
  header {{ padding:4px 2px 18px; }}
  h1 {{ display:flex; align-items:center; gap:10px; padding-right:48px; font-size:26px; letter-spacing:-.03em; line-height:1.1; margin:0 0 6px; font-weight:720; }}
  .intro {{ color:var(--muted); margin:0; font-size:14px; line-height:1.5; }}
  .shelf-label {{ display:flex; align-items:center; justify-content:space-between; margin:9px 2px 12px; color:var(--soft); font-size:13px; }}
  .count {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
  .app-section {{ background:var(--panel); border:1px solid var(--line); border-radius:20px; padding:17px 14px 14px; margin-bottom:13px; }}
  .section-heading {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 3px 12px; }}
  h2 {{ margin:0; font-size:18px; letter-spacing:-.025em; }}
  .checkout {{ color:var(--soft); background:var(--chip); border-radius:20px; padding:5px 9px; font-size:11px; max-width:58%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .downloads {{ display:grid; gap:8px; }}
  .download {{ display:flex; align-items:center; gap:12px; min-height:72px; padding:11px 12px; border:1px solid var(--edge); border-radius:14px; color:inherit; text-decoration:none; background:var(--field); -webkit-tap-highlight-color:transparent; transition:background .15s ease,border-color .15s ease,transform .15s ease; }}
  .download:active {{ transform:scale(.985); background:color-mix(in srgb, var(--accent) 12%, var(--field)); border-color:var(--accent-line); }}
  .download:focus-visible {{ outline:3px solid var(--accent); outline-offset:2px; }}
  .button-icon {{ display:grid; place-items:center; flex:0 0 40px; height:40px; border-radius:12px; background:var(--accent); color:var(--accent-ink); font-size:23px; font-weight:700; }}
  .button-copy {{ min-width:0; flex:1; display:grid; gap:4px; }}
  .button-copy strong {{ font-size:15px; font-weight:650; }}
  .button-copy small {{ display:flex; align-items:baseline; min-width:0; color:var(--muted); font-size:11px; }}
  .button-copy .apk-path {{ flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .button-copy .apk-meta {{ flex:0 0 auto; white-space:nowrap; }}
  .button-copy i {{ font-style:normal; padding:0 3px; flex:0 0 auto; }}
  .button-action {{ color:var(--accent); font-size:13px; font-weight:650; padding:0 1px; }}
  .empty {{ text-align:center; padding:56px 20px; background:var(--panel); border:1px dashed var(--dash); border-radius:20px; }}
  .empty>span {{ color:var(--accent); font-size:30px; }} .empty h2 {{ margin:10px 0 7px; }} .empty p {{ margin:0; color:var(--muted); font-size:14px; }}
  footer {{ color:var(--faint); font-size:12px; line-height:1.5; padding:14px 3px; }}
  @media (min-width:600px) {{ .wrap {{ padding-top:40px }} .app-section {{ padding:19px }} }}
  @media (prefers-reduced-motion:reduce) {{ *,*::before,*::after {{ transition:none!important; scroll-behavior:auto!important }} }}
{EXTRA_CSS}
{QR_CSS}
{extra_css}
</style></head><body><main class="wrap{" wide" if wide else ""}">
  <nav class="tabs" aria-label="Sections">{navigation}</nav>
  {theme_picker()}
  {body}
</main><script>{THEME_PICKER_JS}{PUSH_JS if PUSH_ENABLED else ""}</script>{qr_script()}{search_script()}</body></html>"""
    return document.encode("utf-8")


# Web Push. Enabled when the optional cryptography package is installed (the push extra);
# subscriptions and the VAPID key live in PUSH_DIR.
PUSH_ENABLED = False
QR_ENABLED = True
PUSH_SUBJECT = "mailto:sharei@localhost"
PUSH_SUBS_MAX = 20
# Events of one kind arriving within this many seconds go out as a single notification.
PUSH_DELAY = 2.0
PUSH_SHOT_POLL = 10.0
PUSH_COOKIE = "sharei-push"
PUSH_ID = re.compile(r"[0-9a-f]{24}")
PUSH_PAGES = {"drop": "/drop", "shots": "/shots", "clip": "/clip"}
PUSH_LOCK = threading.Lock()
PUSH_WAKE = threading.Condition(PUSH_LOCK)
PUSH_KEY: list[object] = []


class PushNote(TypedDict):
    title: str
    many: str
    body: str
    url: str
    count: int
    skip: str | None
    due: float


PUSH_PENDING: dict[str, PushNote] = {}


def push_id(endpoint: str) -> str:
    return hashlib.sha256(endpoint.encode("utf-8")).hexdigest()[:24]


def push_subs_locked() -> dict[str, dict]:
    try:
        subs = json.loads((PUSH_DIR / "subs.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}
    return subs if isinstance(subs, dict) else {}


def push_save_locked(subs: dict[str, dict]) -> None:
    target = PUSH_DIR / "subs.json"
    temporary = PUSH_DIR / f".subs-{secrets.token_hex(4)}.part"
    try:
        PUSH_DIR.mkdir(parents=True, exist_ok=True, mode=0o700)
        descriptor = os.open(temporary, os.O_CREAT | os.O_EXCL | os.O_WRONLY, 0o600)
        with os.fdopen(descriptor, "w", encoding="utf-8") as stream:
            json.dump(subs, stream)
        os.replace(temporary, target)
    except OSError as error:
        temporary.unlink(missing_ok=True)
        print(f"cannot save push subscriptions: {error}")


def push_key():
    with PUSH_LOCK:
        if not PUSH_KEY:
            PUSH_KEY.append(push.load_key(PUSH_DIR / "vapid.pem"))
        return PUSH_KEY[0]


def push_subscribe(data: object) -> str | None:
    """Store a browser's PushSubscription JSON; returns its id, or None if invalid."""
    if not isinstance(data, dict) or not isinstance(data.get("keys"), dict):
        return None
    endpoint, keys = data.get("endpoint"), data["keys"]
    p256dh, auth = keys.get("p256dh"), keys.get("auth")
    if not isinstance(p256dh, str) or not isinstance(auth, str):
        return None
    if not push.valid_keys(p256dh, auth) or not push.endpoint_allowed(endpoint):
        return None
    sub_id = push_id(endpoint)
    with PUSH_LOCK:
        subs = push_subs_locked()
        subs.pop(sub_id, None)
        subs[sub_id] = {
            "endpoint": endpoint,
            "keys": {"p256dh": p256dh, "auth": auth},
            "created": time.time(),
        }
        while len(subs) > PUSH_SUBS_MAX:
            subs.pop(next(iter(subs)))
        push_save_locked(subs)
    return sub_id


def push_forget(sub_ids: list[str]) -> bool:
    with PUSH_LOCK:
        subs = push_subs_locked()
        found = [sub_id for sub_id in sub_ids if subs.pop(sub_id, None) is not None]
        if found:
            push_save_locked(subs)
    return bool(found)


def push_notify(
    tag: str,
    title: str,
    many: str,
    body: str,
    skip: str | None = None,
    url: str = "",
    count: int = 1,
) -> None:
    """Queue a notification. `many` is the title once several events of this tag are
    folded together, with {count} for their number; `skip` is the sender's own id."""
    if not PUSH_ENABLED:
        return
    with PUSH_WAKE:
        previous = PUSH_PENDING.get(tag)
        if previous:
            count += previous["count"]
            if previous["skip"] != skip:
                skip = None
        PUSH_PENDING[tag] = PushNote(
            title=title,
            many=many,
            body=body,
            url=url or PUSH_PAGES[tag],
            count=count,
            skip=skip,
            due=time.monotonic() + PUSH_DELAY,
        )
        PUSH_WAKE.notify()


def push_take_due(now: float) -> list[tuple[str, PushNote]]:
    with PUSH_LOCK:
        due = [(tag, note) for tag, note in PUSH_PENDING.items() if note["due"] <= now]
        for tag, _ in due:
            del PUSH_PENDING[tag]
    return due


def push_payload(tag: str, note: PushNote) -> bytes:
    several = note["count"] > 1
    return json.dumps(
        {
            "title": note["many"].format(count=note["count"])
            if several
            else note["title"],
            "body": note["body"][:120],
            "url": PUSH_PAGES[tag] if several else note["url"],
            "tag": tag,
        }
    ).encode("utf-8")


def push_deliver(tag: str, note: PushNote) -> None:
    with PUSH_LOCK:
        subs = push_subs_locked()
    if not subs:
        return
    key, payload, gone = push_key(), push_payload(tag, note), []
    for sub_id, sub in subs.items():
        if sub_id == note["skip"]:
            continue
        host = urlsplit(str(sub.get("endpoint"))).hostname
        try:
            status = push.send(sub, payload, key, PUSH_SUBJECT, topic=tag)
        except (OSError, ValueError, KeyError, http.client.HTTPException) as error:
            print(f"push to {host} failed: {error}")
            continue
        if status in (404, 410):
            gone.append(sub_id)
        elif status >= 400:
            print(f"push service {host} answered {status}")
    if gone:
        push_forget(gone)


def push_worker() -> None:
    seen = set(shot_files())
    next_scan = time.monotonic() + PUSH_SHOT_POLL
    while True:
        with PUSH_WAKE:
            wake = min([note["due"] for note in PUSH_PENDING.values()] + [next_scan])
            delay = wake - time.monotonic()
            if delay > 0:
                PUSH_WAKE.wait(delay)
        now = time.monotonic()
        try:
            if now >= next_scan:
                next_scan = now + PUSH_SHOT_POLL
                current = set(shot_files())
                for path in sorted(current - seen):
                    push_notify(
                        "shots", "New screenshot", "{count} new screenshots", path.name
                    )
                seen = current
            for tag, note in push_take_due(now):
                push_deliver(tag, note)
        except Exception as error:  # noqa: BLE001 - keep the worker alive
            print(f"push failed: {error}")


def clip_preview(text: str) -> str:
    return " ".join(text.split())[:80]


def local_host_names() -> set[str]:
    names = {socket.gethostname(), socket.getfqdn()}
    names |= {f"{name}.local" for name in list(names) if name}
    return {name.lower().rstrip(".") for name in names if name}


def host_allowed(value: str | None) -> bool:
    if not value:
        return False
    host = value.strip().lower()
    if host.startswith("["):
        end = host.find("]")
        host = host[1:end] if end != -1 else host.lstrip("[")
    else:
        host = host.split(":", 1)[0]
    host = host.rstrip(".")
    if host == "localhost" or host in ALLOWED_HOSTS:
        return True
    try:
        address = ipaddress.ip_address(host)
    except ValueError:
        return host.endswith(ALLOWED_HOST_SUFFIXES)
    return not address.is_global


def origin_allowed(origin: str | None, host: str | None) -> bool:
    if not origin:
        return True
    if origin.strip().lower().rstrip("/") in ALLOWED_ORIGINS:
        return True
    parsed = urlparse(origin)
    return parsed.scheme == "http" and parsed.netloc.lower() == (host or "").lower()


class Handler(BaseHTTPRequestHandler):
    def request_allowed(self) -> bool:
        host = self.headers.get("Host")
        if not host_allowed(host):
            self.send_error(403, "Host not allowed")
            return False
        if not origin_allowed(self.headers.get("Origin"), host):
            self.send_error(403, "Cross-origin request refused")
            return False
        return True

    def do_GET(self) -> None:
        if not self.request_allowed():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", "/shots")
            self.end_headers()
            return

        if parsed.path == "/artifacts":
            apks, shots, files = available_artifacts(), available_shots(), poub_files()
            self.send_html(artifacts_page(apks, counts(apks, shots, files)))
            return

        if parsed.path == "/shots":
            apks, shots, files = available_artifacts(), available_shots(), poub_files()
            self.send_html(shots_page(shots, counts(apks, shots, files)))
            return

        if parsed.path == "/clip":
            apks, shots, files = available_artifacts(), available_shots(), poub_files()
            self.send_html(
                clip_page(clip_snapshot(), counts(apks, shots, files)),
                {"Cache-Control": "no-store"},
            )
            return

        if parsed.path == "/drop":
            apks, shots, files = available_artifacts(), available_shots(), poub_files()
            self.send_html(
                drop_page(files, counts(apks, shots, files)),
                {"Cache-Control": "no-store"},
            )
            return

        if parsed.path.startswith("/vendor/"):
            name = parsed.path.removeprefix("/vendor/")
            content_type = VENDOR_TYPES.get(name)
            if name == "qrcode.js" and not QR_ENABLED:
                content_type = None
            vendor_file = VENDOR / name
            if content_type is not None and vendor_file.is_file():
                self.send_file(
                    vendor_file,
                    content_type,
                    {"Cache-Control": "public, max-age=31536000, immutable"},
                )
                return

        if parsed.path == "/icons/":
            self.send_json({"icons": sorted(ICON_NAMES)})
            return

        if parsed.path.startswith("/icons/") and parsed.path.endswith(".svg"):
            name = parsed.path.removeprefix("/icons/").removesuffix(".svg")
            if name in ICON_NAMES:
                self.send_file(
                    ICONS_DIR / f"{name}.svg",
                    "image/svg+xml",
                    vector_headers({"Cache-Control": "public, max-age=86400"}),
                )
                return

        if parsed.path.startswith("/md/"):
            path = poub_path(parsed.path.removeprefix("/md/"))
            if path is not None and is_markdown(path.name):
                project = path.parent.parent.name
                url = f"/poub/{quote(project)}/{quote(path.name)}"
                try:
                    text = path.read_text("utf-8", errors="replace")
                except OSError:
                    self.send_error(404)
                    return
                body, nonce = markdown_page(
                    path.name,
                    text,
                    None,
                    ("Drop", "/drop"),
                    [("Raw", f"{url}?raw=1"), ("Download", url)],
                    project,
                    f"/comments/{quote(project)}/{quote(path.name)}",
                )
                self.send_html(body, markdown_headers(nonce))
                return

        if parsed.path.startswith("/comments/"):
            path = poub_path(parsed.path.removeprefix("/comments/"))
            if path is None or not is_markdown(path.name):
                self.send_json({"error": "not found"}, status=404)
                return
            try:
                view = comments_view(path)
            except OSError:
                self.send_json({"error": "not found"}, status=404)
                return
            if (parse_qs(parsed.query).get("format") or [""])[-1] == "prompt":
                self.send_bytes(
                    comments_prompt(view).encode("utf-8"),
                    "text/plain; charset=utf-8",
                    {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
                )
            else:
                self.send_json(view)
            return

        if parsed.path.startswith("/view/"):
            path = poub_path(parsed.path.removeprefix("/view/"))
            text = read_text_file(path) if path is not None else None
            if path is not None and text is not None:
                project = path.parent.parent.name
                url = f"/poub/{quote(project)}/{quote(path.name)}"
                body, nonce = code_page(
                    path.name, text, [("Raw", f"{url}?raw=1"), ("Download", url)]
                )
                self.send_html(body, code_headers(nonce))
                return

        if parsed.path.startswith("/play/"):
            path = poub_path(parsed.path.removeprefix("/play/"))
            if path is not None and path.suffix.lower() in MEDIA_SUFFIXES:
                body, nonce = play_page(path.parent.parent.name, path.name)
                self.send_html(body, play_headers(nonce))
                return

        if parsed.path.startswith("/pdf/"):
            path = poub_path(parsed.path.removeprefix("/pdf/"))
            if path is not None and path.suffix.lower() == ".pdf":
                body, nonce = pdf_page(
                    path.name,
                    f"/poub/{quote(path.parent.parent.name)}/{quote(path.name)}",
                )
                self.send_html(body, pdf_headers(nonce))
                return

        if parsed.path == "/clip/md":
            text = clip_snapshot()["text"]
            body, nonce = markdown_page(
                "Clipboard",
                text,
                None if text else "The clipboard is empty.",
                ("Clipboard", "/clip"),
                [("Raw", "/clip/raw")],
            )
            self.send_html(body, markdown_headers(nonce))
            return

        if parsed.path.startswith("/poub/"):
            path = poub_path(parsed.path.removeprefix("/poub/"))
            if path is not None:
                self.send_shared_file(path, "raw" in parse_qs(parsed.query))
                return

        if parsed.path == "/notes-search":
            index = notes.index()
            if index is not None:
                query = parse_qs(parsed.query).get("q", [""])[0]
                if not query.strip():
                    self.send_json(
                        {"public_url": PUBLIC_URL, "items": notes_entries(index)}
                    )
                    return
                terms, results = notes.search(index, query)
                self.send_json(
                    {
                        "public_url": PUBLIC_URL,
                        "terms": terms,
                        "results": name_matches(index, terms, results),
                    }
                )
                return

        if parsed.path == "/notes" or parsed.path.startswith("/notes/"):
            index = notes.index()
            relative = unquote(parsed.path.removeprefix("/notes").strip("/"))
            if index is not None and notes.is_folder(index, relative):
                self.send_html(
                    notes_page(index, notes.key(relative), counts_now()),
                    {"Cache-Control": "no-store"},
                )
                return
            path = notes.allowed(index, relative) if index is not None else None
            if path is not None:
                relative = notes.key(relative)
                back = notes_crumbs(posixpath.dirname(relative))[-1]
                download = [("Download", notes.url("/notes-file/", relative))]
                if notes.is_markdown(path.name):
                    text = read_note(path)
                    if text is not None:
                        crumbs = notes_crumbs(posixpath.dirname(relative))
                        body, nonce = markdown_page(
                            path.stem,
                            text,
                            None,
                            back,
                            [],
                            note_links=notes.link_map(
                                index, text, relative, looks_like_text
                            ),
                            crumbs=crumbs,
                            icon=notes_icon(index, relative),
                        )
                        self.send_html(body, markdown_headers(nonce))
                        return
                elif (text := read_text_file(path)) is not None:
                    body, nonce = code_page(path.name, text, download, back)
                    self.send_html(body, code_headers(nonce))
                    return
                else:
                    self.send_shared_file(path, False)
                    return

        if parsed.path.startswith("/notes-file/"):
            index = notes.index()
            relative = unquote(parsed.path.removeprefix("/notes-file/"))
            path = notes.allowed(index, relative) if index is not None else None
            if path is not None:
                self.send_shared_file(path, "raw" in parse_qs(parsed.query))
                return

        if parsed.path.startswith("/notes-icon/"):
            index = notes.index()
            name = unquote(parsed.path.removeprefix("/notes-icon/"))
            path = index.icon_files.get(name) if index is not None else None
            if path is not None:
                self.send_shared_file(path, False)
                return

        if parsed.path.startswith("/notes-pdf/"):
            index = notes.index()
            relative = notes.key(unquote(parsed.path.removeprefix("/notes-pdf/")))
            path = notes.allowed(index, relative) if index is not None else None
            if path is not None and path.suffix.lower() == ".pdf":
                body, nonce = pdf_page(
                    path.name,
                    notes.url("/notes-file/", relative),
                    notes_crumbs(posixpath.dirname(relative))[-1],
                )
                self.send_html(body, pdf_headers(nonce))
                return

        if parsed.path == "/clip/state":
            self.send_json(clip_json(clip_snapshot()))
            return

        if parsed.path == "/state":
            self.send_json(
                {"shots": live_stamp(shot_files()), "drop": live_stamp(poub_paths())}
            )
            return

        if parsed.path == "/recent":
            query = parse_qs(parsed.query)
            limit_text = (query.get("limit") or ["5"])[-1]
            try:
                limit = max(1, min(int(limit_text), RECENT_MAX))
            except ValueError:
                self.send_json({"error": "limit must be an integer"}, status=400)
                return
            project = self.query_project(query)
            if project is not False:
                self.send_json(recent_payload(limit, project))
            return

        if PUSH_ENABLED and parsed.path == "/sw.js":
            self.send_bytes(
                SW_JS.encode("utf-8"),
                "text/javascript; charset=utf-8",
                {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
            )
            return

        if PUSH_ENABLED and parsed.path == "/push/key":
            self.send_json({"key": push.b64url(push.public_bytes(push_key()))})
            return

        if parsed.path == "/manifest.webmanifest":
            body = json.dumps(MANIFEST).encode("utf-8")
            self.send_bytes(
                body, "application/manifest+json", {"Cache-Control": "no-cache"}
            )
            return

        if parsed.path in {f"/icon-{size}.png" for size in ICON_SIZES}:
            size = int(parsed.path.removeprefix("/icon-").removesuffix(".png"))
            self.send_bytes(
                icon_png(size), "image/png", {"Cache-Control": "public, max-age=86400"}
            )
            return

        if parsed.path == "/clip/raw":
            state = clip_snapshot()
            try:
                index = int((parse_qs(parsed.query).get("n") or ["0"])[-1])
            except ValueError:
                index = -1
            if not 0 <= index <= len(state["history"]):
                self.send_json({"error": "no such clipboard entry"}, status=404)
                return
            text = state["history"][index - 1]["text"] if index else state["text"]
            body = text.encode("utf-8")
            self.send_response(200)
            self.send_header("Content-Type", "text/plain; charset=utf-8")
            self.send_header("Content-Length", str(len(body)))
            self.send_header("Cache-Control", "no-store")
            self.end_headers()
            self.wfile.write(body)
            return

        if parsed.path.startswith("/thumb/"):
            encoded = parsed.path.removeprefix("/thumb/")
            path = shot_path(encoded)
            if path is not None:
                self.send_thumbnail(path)
                return
            dropped = poub_image_path(encoded)
            if dropped is not None:
                self.send_thumbnail(dropped, "fit")
                return

        if parsed.path.startswith("/shot/"):
            path = shot_path(parsed.path.removeprefix("/shot/"))
            if path is not None:
                headers = {"Cache-Control": "public, max-age=31536000, immutable"}
                if path.suffix.lower() in VECTOR_SUFFIXES:
                    headers = vector_headers(headers)
                self.send_file(
                    path,
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    headers,
                )
                return

        if parsed.path.startswith("/download/"):
            key = parsed.path.removeprefix("/download/")
            item = next(
                (item for item in available_artifacts() if item["key"] == key), None
            )
            if item is not None and Path(item["path"]).is_file():
                path = Path(item["path"])
                content_type = (
                    "application/vnd.android.package-archive"
                    if path.suffix == ".apk"
                    else mimetypes.guess_type(path.name)[0]
                    or "application/octet-stream"
                )
                self.send_file(
                    path,
                    content_type,
                    {
                        "Content-Disposition": "attachment; filename*=UTF-8''"
                        + quote(path.name),
                        "X-Content-Type-Options": "nosniff",
                    },
                )
                return

        self.send_error(404)

    def do_POST(self) -> None:
        if not self.request_allowed():
            return
        parsed = urlparse(self.path)
        if parsed.path == "/shots/delete-all":
            project = self.query_project(parse_qs(parsed.query))
            if project is not False:
                self.send_json({"deleted": delete_all_shots(project)})
            return

        if parsed.path.startswith("/shots/delete/"):
            self.handle_delete(parsed.path.removeprefix("/shots/delete/"), delete_shot)
            return

        if parsed.path == "/poub/delete-all":
            project = self.query_project(parse_qs(parsed.query))
            if project is not False:
                self.send_json({"deleted": delete_all_poub(project)})
            return

        if parsed.path.startswith("/poub/delete/"):
            self.handle_delete(parsed.path.removeprefix("/poub/delete/"), delete_poub)
            return

        if parsed.path == "/upload":
            self.handle_upload()
            return

        if parsed.path.startswith("/comments/"):
            self.handle_comment(parsed)
            return

        if parsed.path == "/expiry":
            self.handle_expiry(parse_qs(parsed.query))
            return

        if parsed.path == "/annotate":
            self.handle_annotate()
            return

        if parsed.path == "/share":
            self.handle_share()
            return

        if PUSH_ENABLED and parsed.path in ("/push/subscribe", "/push/unsubscribe"):
            self.handle_push(parsed.path.removeprefix("/push/"))
            return

        if parsed.path == "/clip/clear":
            self.send_json(clip_json(clip_store("")))
            return

        if parsed.path.startswith("/clip/history/"):
            self.handle_clip_history(
                parsed.path.removeprefix("/clip/history/"), parse_qs(parsed.query)
            )
            return

        if parsed.path == "/clip/ttl":
            query = parse_qs(parsed.query, keep_blank_values=True)
            seconds_text = (query.get("seconds") or [""])[-1]
            if not seconds_text:
                seconds_text = (
                    (self.read_body() or b"").decode("utf-8", "replace").strip()
                )
            try:
                seconds = int(seconds_text)
            except ValueError:
                self.send_json({"error": "seconds must be an integer"}, status=400)
                return
            self.send_json(clip_json(clip_set_ttl(seconds)))
            return

        if parsed.path != "/clip":
            self.send_error(404)
            return

        raw = self.read_body()
        if raw is None:
            self.send_error(400, "Malformed or oversized request body")
            return

        content_type = (
            (self.headers.get("Content-Type") or "").split(";")[0].strip().lower()
        )
        if content_type == "application/x-www-form-urlencoded":
            fields = parse_qs(raw.decode("utf-8", "replace"), keep_blank_values=True)
            if "text" not in fields:
                self.send_json(
                    {
                        "error": "form body needs a 'text' field; send text/plain for raw text"
                    },
                    status=400,
                )
                return
            text = fields["text"][-1]
        else:
            text = raw.decode("utf-8", "replace")
        state = clip_store(text)
        if text:
            push_notify(
                "clip", "Clipboard", "Clipboard", clip_preview(text), self.push_sender()
            )
        self.send_json(clip_json(state))

    def push_sender(self) -> str | None:
        """The push subscription of the browser making this request, so it is not
        notified about its own action."""
        cookies = http.cookies.SimpleCookie()
        try:
            cookies.load(self.headers.get("Cookie") or "")
        except http.cookies.CookieError:
            return None
        morsel = cookies.get(PUSH_COOKIE)
        return morsel.value if morsel and PUSH_ID.fullmatch(morsel.value) else None

    def handle_push(self, action: str) -> None:
        raw = self.read_body(8192)
        try:
            data = json.loads(raw or b"")
        except ValueError:
            data = None
        if action == "subscribe":
            sub_id = push_subscribe(data)
            if sub_id is None:
                self.send_json({"error": "invalid push subscription"}, status=400)
                return
            cookie = f"{PUSH_COOKIE}={sub_id}; Path=/; Max-Age=31536000; HttpOnly; SameSite=Strict"
            self.send_json({"id": sub_id}, headers={"Set-Cookie": cookie})
            return
        endpoint = data.get("endpoint") if isinstance(data, dict) else None
        ids = [push_id(endpoint)] if isinstance(endpoint, str) else []
        sender = self.push_sender()
        if sender:
            ids.append(sender)
        self.send_json(
            {"removed": push_forget(ids)},
            headers={
                "Set-Cookie": f"{PUSH_COOKIE}=; Path=/; Max-Age=0; SameSite=Strict"
            },
        )

    def handle_annotate(self) -> None:
        query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
        key = (query.get("key") or [""])[-1]
        target = (query.get("target") or [""])[-1]
        path = annotate_path(target, key)
        if path is None:
            self.send_json({"error": "not found"}, status=404)
            return
        image_type = ANNOTATE_TYPES.get(path.suffix.lower())
        if image_type is None:
            self.send_json(
                {
                    "error": f"{path.suffix or 'this file type'} cannot be annotated in place"
                },
                status=415,
            )
            return
        raw = self.read_body(ANNOTATE_MAX_BYTES)
        if raw is None:
            self.send_json(
                {"error": "annotation body is malformed or too large"}, status=413
            )
            return

        try:
            data = json.loads(raw)["data"]
            header, _, encoded = data.partition(",")
            if header.strip().lower() != f"data:{image_type};base64":
                raise ValueError(f"expected a {image_type} data URL")
            image = base64.b64decode(encoded, validate=True)
        except (AttributeError, KeyError, TypeError, ValueError):
            self.send_json(
                {"error": f'body must be {{"data": "data:{image_type};base64,..."}}'},
                status=400,
            )
            return
        if not image:
            self.send_json({"error": "empty image"}, status=400)
            return

        try:
            replace_image(path, image)
        except OSError as error:
            self.send_json({"error": str(error)}, status=500)
            return

        quoted = image_key(path)
        prefix = "/shot/" if target == "shots" else "/poub/"
        # The live poll compares these stamps; handing the fresh ones back keeps the page from reloading
        # under the user right after their own save.
        self.send_json(
            {
                "saved": len(image),
                "key": quoted,
                "url": f"{prefix}{quoted}?v={int(time.time())}",
                "stamps": {
                    "shots": live_stamp(shot_files()),
                    "drop": live_stamp(poub_paths()),
                },
            }
        )

    def handle_delete(self, encoded: str, remove: Callable[[str], bool]) -> None:
        try:
            removed = remove(encoded)
        except FileNotFoundError:
            removed = False
        except OSError as error:
            self.send_json({"error": str(error)}, status=500)
            return
        if not removed:
            self.send_json({"error": "not found"}, status=404)
            return
        self.send_json({"deleted": 1})

    def handle_expiry(self, query: dict[str, list[str]]) -> None:
        target = (query.get("target") or [""])[-1]
        resolve = {"poub": poub_path, "shot": shot_path}.get(target)
        if resolve is None:
            self.send_json({"error": "target must be poub or shot"}, status=400)
            return
        try:
            seconds = int((query.get("seconds") or [""])[-1])
        except ValueError:
            seconds = -1
        if not 0 <= seconds <= EXPIRY_MAX:
            self.send_json(
                {"error": f"seconds must be between 0 and {EXPIRY_MAX}"}, status=400
            )
            return
        path = resolve((query.get("key") or [""])[-1])
        if path is None:
            self.send_json({"error": "not found"}, status=404)
            return
        self.send_json({"expires": expiry_set(path, seconds)})

    def query_project(self, query: dict[str, list[str]]) -> str | None | bool:
        """Return the validated ?project= value, None when absent, or False after sending a 400."""
        project = (query.get("project") or [""])[-1]
        if not project:
            return None
        if not valid_project(project):
            self.send_json(
                {"error": "project must match [A-Za-z0-9][A-Za-z0-9._-]{0,63}"},
                status=400,
            )
            return False
        return project

    def handle_upload(self) -> None:
        query = parse_qs(urlparse(self.path).query, keep_blank_values=True)
        project = self.query_project(query)
        if project is False:
            return
        project = project or DEFAULT_PROJECT
        name = safe_poub_name(query.get("name", [""])[-1])
        if name is None:
            self.send_json({"error": "hidden or invalid filename"}, status=400)
            return
        try:
            length = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            length = -1
        if length < 0:
            self.send_json({"error": "Content-Length is required"}, status=411)
            return
        if length > UPLOAD_MAX_BYTES:
            self.send_json({"error": "file is too large"}, status=413)
            return

        try:
            temporary, descriptor = open_upload(project)
        except OSError as error:
            self.send_json({"error": str(error)}, status=500)
            return

        remaining = length
        try:
            with os.fdopen(descriptor, "wb") as stream:
                while remaining:
                    chunk = self.rfile.read(min(256 * 1024, remaining))
                    if not chunk:
                        raise ConnectionError("upload ended early")
                    stream.write(chunk)
                    remaining -= len(chunk)
        except (OSError, ConnectionError) as error:
            temporary.unlink(missing_ok=True)
            self.send_json({"error": str(error)}, status=400)
            return

        temporary, name = convert_heic_upload(temporary, name)
        replace = (query.get("replace") or [""])[-1].lower() in ("1", "true", "yes")
        try:
            path = replace_poub(temporary, name) if replace else None
            replaced = path is not None
            if path is None:
                path = publish_poub(temporary, name)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            self.send_json({"error": str(error)}, status=500)
            return

        view = view_url(project, path)
        push_notify(
            "drop",
            "New file",
            "{count} new files",
            path.name,
            self.push_sender(),
            view or "",
        )
        self.send_json(
            {
                "project": project,
                "name": path.name,
                "size": path.stat().st_size,
                "url": f"/poub/{quote(project)}/{quote(path.name)}",
                **({"view": view} if view else {}),
                **({"replaced": True} if replaced else {}),
            }
        )

    def handle_comment(self, parsed: ParseResult) -> None:
        action, _, encoded = parsed.path.removeprefix("/comments/").partition("/")
        if action not in ("add", "edit", "delete"):
            self.send_json({"error": "not found"}, status=404)
            return
        path = poub_path(encoded)
        if path is None or not is_markdown(path.name):
            self.send_json({"error": "not found"}, status=404)
            return
        data: object = None
        if action != "delete":
            body = self.read_body(COMMENT_MAX_CHARS * 4 + 1024)
            if body is None:
                self.send_json({"error": "request too large"}, status=413)
                return
            try:
                data = json.loads(body)
            except ValueError:
                self.send_json({"error": "body must be JSON"}, status=400)
                return
        comment_id = (parse_qs(parsed.query).get("id") or [""])[-1]
        try:
            error = comment_change(path, action, comment_id, data)
            view = comments_view(path)
        except OSError as failure:
            self.send_json({"error": str(failure)}, status=500)
            return
        if error:
            self.send_json(
                {"error": error}, status=404 if error == "not found" else 400
            )
            return
        self.send_json(view)

    def handle_share(self) -> None:
        content_type = self.headers.get("Content-Type") or ""
        if not content_type.lower().startswith("multipart/form-data"):
            self.send_error(415, "Share target expects multipart/form-data")
            return
        try:
            length = int(self.headers.get("Content-Length") or -1)
        except ValueError:
            length = -1
        if length < 0:
            self.send_error(411, "Content-Length is required")
            return
        if length > SHARE_MAX_BYTES:
            self.send_error(413, "Too large to share; use the Drop tab for big files")
            return
        fields: dict[str, str] = {}
        # One share parsed at a time keeps memory bounded to roughly one body.
        with SHARE_LOCK:
            saved = self.receive_share(content_type, length, fields)
        if saved is None:
            return

        text, url = fields.get("text", ""), fields.get("url", "")
        shared = "\n".join(
            value for value in (text, url if url not in text else "") if value
        )
        sender = self.push_sender()
        if saved:
            push_notify(
                "drop",
                "New file",
                "{count} new files",
                "From the Share menu",
                sender,
                count=saved,
            )
        if shared or (not saved and fields.get("title")):
            text = shared or fields["title"]
            clip_store(text)
            push_notify("clip", "Clipboard", "Clipboard", clip_preview(text), sender)

        self.send_response(303)
        self.send_header("Location", "/drop" if saved else "/clip")
        self.send_header("Content-Length", "0")
        self.end_headers()

    def receive_share(
        self, content_type: str, length: int, fields: dict[str, str]
    ) -> int | None:
        body = self.rfile.read(length)
        if len(body) != length:
            self.send_error(400, "Share body ended early")
            return None

        message = email.parser.BytesParser(policy=email.policy.HTTP).parsebytes(
            f"Content-Type: {content_type}\r\n\r\n".encode("latin-1", "replace") + body
        )
        del body
        if not message.is_multipart():
            self.send_error(400, "Malformed multipart body")
            return None

        saved = 0
        for part in message.iter_parts():
            name = part.get_param("name", header="content-disposition")
            payload = part.get_payload(decode=True) or b""
            filename = part.get_filename()
            if filename is None:
                if name in ("title", "text", "url"):
                    fields[name] = payload.decode(
                        part.get_content_charset() or "utf-8", "replace"
                    ).strip()
                continue
            # Text-only shares can carry an empty, unnamed file part.
            if not payload and not filename:
                continue
            safe = safe_poub_name(filename)
            if safe is None:
                continue
            temporary = None
            try:
                temporary, descriptor = open_upload(DEFAULT_PROJECT)
                with os.fdopen(descriptor, "wb") as stream:
                    stream.write(payload)
                temporary, safe = convert_heic_upload(temporary, safe)
                publish_poub(temporary, safe)
            except OSError as error:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                self.send_error(500, f"Could not save shared file: {error}")
                return None
            saved += 1
        return saved

    def handle_clip_history(self, action: str, query: dict[str, list[str]]) -> None:
        if action not in ("clear", "restore", "delete"):
            self.send_error(404)
            return
        entry_id = None
        if action != "clear":
            try:
                entry_id = int((query.get("id") or [""])[-1])
            except ValueError:
                self.send_json({"error": "id must be an integer"}, status=400)
                return
        if action == "restore":
            entry = clip_history_entry(entry_id)
            state = clip_store(entry["text"]) if entry is not None else None
        else:
            state = clip_history_delete(entry_id)
        if state is None:
            self.send_json({"error": "no such clipboard entry"}, status=404)
            return
        self.send_json(clip_json(state))

    def read_body(self, limit: int = CLIP_MAX_BYTES) -> bytes | None:
        if "chunked" in (self.headers.get("Transfer-Encoding") or "").lower():
            return self.read_chunked(limit)
        try:
            length = int(self.headers.get("Content-Length") or 0)
        except ValueError:
            return None
        if length < 0 or length > limit:
            return None
        return self.rfile.read(length)

    def read_chunked(self, limit: int = CLIP_MAX_BYTES) -> bytes | None:
        data = bytearray()
        while True:
            line = self.rfile.readline(1024)
            if not line:
                return None
            size_text = line.split(b";", 1)[0].strip()
            if not size_text or len(size_text) > 16:
                return None
            try:
                size = int(size_text, 16)
            except ValueError:
                return None
            if size < 0:
                return None
            if size == 0:
                while self.rfile.readline(65537) not in (b"\r\n", b"\n", b""):
                    continue
                return bytes(data)
            if len(data) + size > limit:
                return None
            chunk = self.rfile.read(size)
            if len(chunk) != size:
                return None
            if self.rfile.read(2) not in (b"\r\n", b"\n"):
                return None
            data += chunk

    def send_html(self, body: bytes, headers: dict[str, str] | None = None) -> None:
        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_json(
        self,
        payload: dict[str, object],
        status: int = 200,
        headers: dict[str, str] | None = None,
    ) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
        for name, value in (headers or {}).items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_bytes(
        self, body: bytes, content_type: str, headers: dict[str, str]
    ) -> None:
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(body)

    def send_thumbnail(self, path: Path, style: str = "top") -> None:
        immutable = {"Cache-Control": "public, max-age=31536000, immutable"}
        if path.suffix.lower() in VECTOR_SUFFIXES:
            # Nothing to rasterise or cache: the browser scales the vector itself.
            self.send_file(path, "image/svg+xml", vector_headers(immutable))
            return
        try:
            cached = thumbnail_cache_path(path, style)
            if cached.is_file():
                data = cached.read_bytes()
            else:
                data = render_thumbnail(path, style)
                try:
                    THUMBS.mkdir(parents=True, exist_ok=True)
                    temporary = cached.with_name(
                        f"{cached.name}.{secrets.token_hex(4)}.part"
                    )
                    temporary.write_bytes(data)
                    os.replace(temporary, cached)
                except OSError:
                    pass
        # Any renderer failure, Pillow's DecompressionBombError included, is
        # answered with the original image: a thumbnail is never worth a 500.
        except Exception as error:  # noqa: BLE001
            print(f"thumbnail failed for {path}: {error}")
            self.send_file(
                path,
                mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                immutable,
            )
            return
        self.send_response(200)
        self.send_header("Content-Type", "image/webp")
        self.send_header("Content-Length", str(len(data)))
        for name, value in immutable.items():
            self.send_header(name, value)
        self.end_headers()
        self.wfile.write(data)

    def send_shared_file(self, path: Path, raw: bool) -> None:
        """A dropped or shared file: media inline, text as text/plain on request, the rest
        as a download."""
        headers = {
            "Cache-Control": "no-cache",
            "X-Content-Type-Options": "nosniff",
        }
        suffix = path.suffix.lower()
        content_type = (
            AUDIO_TYPES.get(suffix)
            or HEIC_TYPES.get(suffix)
            or VECTOR_TYPES.get(suffix)
            or mimetypes.guess_type(path.name)[0]
            or "application/octet-stream"
        )
        if raw and (suffix in MARKDOWN_SUFFIXES or looks_like_text(path)):
            content_type = "text/plain; charset=utf-8"
        elif suffix in HTML_SUFFIXES:
            # Render in the browser, but in an opaque origin so the page
            # cannot reach the sharei API or its storage.
            headers["Content-Security-Policy"] = HTML_CSP
        elif suffix in VECTOR_SUFFIXES:
            headers.update(vector_headers({}))
        elif (
            suffix not in IMAGE_LIKE_SUFFIXES
            and suffix not in HEIC_SUFFIXES
            and suffix not in MEDIA_SUFFIXES
        ):
            headers["Content-Disposition"] = (
                f"attachment; filename*=UTF-8''{quote(path.name)}"
            )
        self.send_file(path, content_type, headers)

    def send_file(self, path: Path, content_type: str, headers: dict[str, str]) -> None:
        size = path.stat().st_size
        start, end = 0, size - 1
        status = 200
        # Video players need a single byte range to seek; anything fancier gets the whole file.
        match = re.fullmatch(
            r"bytes=(\d*)-(\d*)", self.headers.get("Range", "").strip()
        )
        if match and (match[1] or match[2]):
            if match[1]:
                start = int(match[1])
                end = min(int(match[2]), size - 1) if match[2] else size - 1
            else:
                start = max(size - int(match[2]), 0)
            if start > end or start >= size:
                self.send_response(416)
                self.send_header("Content-Range", f"bytes */{size}")
                self.send_header("Content-Length", "0")
                self.end_headers()
                return
            status = 206
        self.send_response(status)
        self.send_header("Content-Type", content_type)
        self.send_header("Accept-Ranges", "bytes")
        self.send_header("Content-Length", str(end - start + 1))
        if status == 206:
            self.send_header("Content-Range", f"bytes {start}-{end}/{size}")
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        with path.open("rb") as stream:
            stream.seek(start)
            remaining = end - start + 1
            try:
                while remaining and (chunk := stream.read(min(128 * 1024, remaining))):
                    self.wfile.write(chunk)
                    remaining -= len(chunk)
            except (BrokenPipeError, ConnectionResetError):
                self.close_connection = True

    def log_message(self, format: str, *args: object) -> None:
        print(f"{self.client_address[0]} - {format % args}")


def phone_ip() -> str | None:
    try:
        with socket.socket(socket.AF_INET, socket.SOCK_DGRAM) as probe:
            probe.connect(("192.0.2.1", 80))
            address = probe.getsockname()[0]
        return address if not ipaddress.ip_address(address).is_loopback else None
    except OSError:
        return None


def listens_on_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host.strip("[]")).is_loopback
    except ValueError:
        return host.lower() == "localhost"


CONFIG_TYPES: dict[str, type | tuple[type, ...]] = {
    "host": str,
    "port": int,
    "root": str,
    "default_project": str,
    "clip_ttl": int,
    "allow_hosts": list,
    "allow_origins": list,
    "artifacts": list,
    "theme": str,
    "public_url": str,
    "qr": bool,
    "notes": dict,
    "push_subject": str,
}
ARTIFACT_TYPES: dict[str, type] = {
    "name": str,
    "project": str,
    "root": str,
    "patterns": list,
}


def config_path(explicit: str | None) -> tuple[Path, bool]:
    if explicit or os.environ.get("SHAREI_CONFIG"):
        return Path(explicit or os.environ["SHAREI_CONFIG"]).expanduser(), True
    return Path(
        os.environ.get("XDG_CONFIG_HOME") or Path.home() / ".config"
    ) / "sharei" / "config.toml", False


def check_types(
    where: str, data: dict[str, object], types: dict[str, type | tuple[type, ...]]
) -> None:
    for key, value in data.items():
        if key not in types:
            raise SystemExit(
                f"sharei: {where}: unknown key {key!r} (known: {', '.join(types)})"
            )
        # bool is an int subclass; reject it so `port = true` is not taken as 1.
        if not isinstance(value, types[key]) or (
            isinstance(value, bool) and types[key] is not bool
        ):
            raise SystemExit(f"sharei: {where}: {key!r} has the wrong type")


def load_config(path: Path, required: bool) -> dict[str, object]:
    try:
        with path.open("rb") as stream:
            data = tomllib.load(stream)
    except FileNotFoundError:
        if required:
            raise SystemExit(f"sharei: config file not found: {path}") from None
        return {}
    except (OSError, tomllib.TOMLDecodeError) as error:
        raise SystemExit(f"sharei: cannot read {path}: {error}") from None
    if "apps" in data:
        raise SystemExit(
            f"sharei: {path}: [[apps]] was replaced by [[artifacts]], see config.example.toml"
        )
    check_types(str(path), data, CONFIG_TYPES)
    for key in ("allow_hosts", "allow_origins"):
        if not all(isinstance(item, str) for item in data.get(key, [])):
            raise SystemExit(f"sharei: {path}: {key!r} must be a list of strings")
    return data


def parse_artifacts(where: str, entries: list[object]) -> tuple[ArtifactRule, ...]:
    rules = []
    for index, entry in enumerate(entries):
        label = f"{where}: artifacts[{index}]"
        if not isinstance(entry, dict):
            raise SystemExit(f"sharei: {label} must be a table")
        check_types(label, entry, ARTIFACT_TYPES)
        patterns = entry.get("patterns")
        if "root" not in entry or not patterns:
            raise SystemExit(f"sharei: {label} needs root and patterns")
        for pattern in patterns:
            if (
                not isinstance(pattern, str)
                or not pattern
                or pattern.startswith("/")
                or any(part in ("", ".", "..") for part in pattern.split("/"))
            ):
                raise SystemExit(
                    f"sharei: {label}: pattern {pattern!r} must be a relative path like "
                    "'dist/*.whl' or '**/outputs/apk/**/*.apk'"
                )
        is_glob = glob.has_magic(entry["root"])
        if is_glob and ("name" in entry or "project" in entry):
            raise SystemExit(
                f"sharei: {label}: name and project only apply to a single root, "
                "not a glob; each matching repo uses its folder name"
            )
        project = entry.get("project")
        if project is not None and not valid_project(project):
            raise SystemExit(
                f"sharei: {label}: project {project!r} must match {PROJECT_NAME.pattern}"
            )
        rules.append(
            ArtifactRule(entry["root"], tuple(patterns), entry.get("name"), project)
        )
    return tuple(rules)


def main() -> None:
    global ARTIFACT_RULES, DEFAULT_PROJECT, ROOT
    global THEME_DEFAULT, PUBLIC_URL, PUSH_ENABLED, PUSH_SUBJECT, QR_ENABLED
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    parser.add_argument(
        "--config",
        metavar="FILE",
        help="TOML settings (default: $SHAREI_CONFIG, else ~/.config/sharei/config.toml if it "
        "exists); command-line flags win over it",
    )
    parser.add_argument(
        "--host",
        help="interface to listen on (default: 127.0.0.1; 0.0.0.0 opens it to your network, "
        "where anyone can reach it without a password)",
    )
    parser.add_argument("--port", type=int, help="default: 8000")
    parser.add_argument(
        "--root",
        metavar="DIR",
        help="holds <project>/shots and <project>/drop (default: ~/tmp/sharei)",
    )
    parser.add_argument(
        "--default-project",
        metavar="NAME",
        help="project for uploads without ?project= and for Share menu files (default: inbox)",
    )
    parser.add_argument(
        "--clip-ttl",
        type=int,
        default=None,
        metavar="SECONDS",
        help="clear the clipboard after this many seconds, 0 keeps it (default: the saved "
        "setting, else 600)",
    )
    parser.add_argument(
        "--allow-host",
        action="append",
        default=[],
        metavar="NAME",
        help="extra Host header accepted (repeatable); localhost, local names and "
        "non-global IPs are always allowed",
    )
    parser.add_argument(
        "--allow-origin",
        action="append",
        default=[],
        metavar="URL",
        help="extra Origin accepted for POSTs (repeatable), e.g. https://share.example.com "
        "behind a reverse proxy",
    )
    args = parser.parse_args()
    path, required = config_path(args.config)
    config = load_config(path, required)

    def setting(name: str, default: object) -> object:
        value = getattr(args, name)
        return value if value is not None else config.get(name, default)

    host, port = str(setting("host", "127.0.0.1")), int(setting("port", 8000))
    ROOT = Path(str(setting("root", ROOT))).expanduser().absolute()
    DEFAULT_PROJECT = str(setting("default_project", DEFAULT_PROJECT))
    if not valid_project(DEFAULT_PROJECT):
        raise SystemExit(
            f"sharei: default project {DEFAULT_PROJECT!r} must match {PROJECT_NAME.pattern}"
        )
    THEME_DEFAULT = str(config.get("theme", THEME_DEFAULT))
    if THEME_DEFAULT != "auto" and THEME_DEFAULT not in THEMES:
        raise SystemExit(
            f"sharei: theme {THEME_DEFAULT!r} must be one of auto, {', '.join(THEMES)}"
        )
    ARTIFACT_RULES = parse_artifacts(str(path), config.get("artifacts", []))  # type: ignore[arg-type]
    clip_ttl = setting("clip_ttl", None)
    PUBLIC_URL = str(config.get("public_url", "")).rstrip("/")
    if PUBLIC_URL and urlparse(PUBLIC_URL).scheme not in ("http", "https"):
        raise SystemExit(
            f"sharei: public_url {PUBLIC_URL!r} must start with http(s)://"
        )
    if not PUBLIC_URL and not listens_on_loopback(host):
        address = phone_ip()
        PUBLIC_URL = f"http://{address}:{port}" if address else ""

    QR_ENABLED = bool(config.get("qr", True))
    if "notes" in config:
        notes.VAULT = notes.configure(str(path), config["notes"])
    PUSH_ENABLED = push.available()
    PUSH_SUBJECT = str(
        config.get("push_subject")
        or (PUBLIC_URL if PUBLIC_URL.startswith("https://") else PUSH_SUBJECT)
    )
    if not PUSH_SUBJECT.startswith(("mailto:", "https://")):
        raise SystemExit(
            f"sharei: push_subject {PUSH_SUBJECT!r} must be a mailto: or https:// URL"
        )

    clip_load()
    if clip_ttl is not None:
        CLIP["ttl"] = max(0, min(int(clip_ttl), CLIP_MAX_TTL))  # type: ignore[call-overload]
    ALLOWED_HOSTS.update(local_host_names())
    for name in [*config.get("allow_hosts", []), *args.allow_host]:  # type: ignore[misc]
        if name.strip():
            ALLOWED_HOSTS.add(name.strip().lower().rstrip("."))
    for url in [*config.get("allow_origins", []), *args.allow_origin]:  # type: ignore[misc]
        if url.strip():
            ALLOWED_ORIGINS.add(url.strip().lower().rstrip("/"))
    drop_dir(DEFAULT_PROJECT).mkdir(parents=True, exist_ok=True)
    sweep_partials()
    expiry_load()
    sweep_expired()
    threading.Thread(target=expiry_sweeper, daemon=True).start()
    if PUSH_ENABLED:
        threading.Thread(target=push_worker, daemon=True).start()
    notes.index()
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Config: {path if config else 'built-in defaults'}; files under {ROOT}")
    print(
        f"Open http://localhost:{port}  (screenshots: /shots, clipboard: /clip, drop: /drop)"
    )
    address = phone_ip()
    if host == "0.0.0.0" and address:
        print(f"On your phone: http://{address}:{port}")
    if not PUSH_ENABLED:
        print("Phone notifications are off: install sharei with the push extra.")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
