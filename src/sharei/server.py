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
import re
import secrets
import socket
import subprocess
import threading
import time
import tomllib
import urllib.error
import urllib.request
import zlib
from collections.abc import Callable
from datetime import datetime
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from typing import NamedTuple, TypedDict
from urllib.parse import parse_qs, quote, unquote, urlparse, urlsplit

from sharei import push

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

SCRIPT_DIR = Path(__file__).resolve().parent
VENDOR = SCRIPT_DIR / "vendor"
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
MARKDOWN_CACHE = cache_root() / "markdown"

# Only used when the reader asks for GitHub's rendering; the default is local.
GITHUB_API = os.environ.get("SHAREI_GITHUB_API", "https://api.github.com").rstrip("/")
GITHUB_MARKDOWN_MAX_BYTES = 400 * 1024
GITHUB_TOKEN: str | None = None
GITHUB_TOKEN_PASS: str | None = None
TOKEN_LOCK = threading.Lock()
TOKEN_FROM_PASS_TRIED = False


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
    image: bool
    text: bool
    timestamp: float
    expires: float | None


THEME_DEFAULT = "auto"
THEME_KEYS = (
    "base",
    "panel",
    "field",
    "line",
    "edge",
    "ink",
    "soft",
    "muted",
    "faint",
    "accent",
    "accent-ink",
    "danger",
    "warn",
)
# Values follow THEME_KEYS. "dark" comes first: it is also the no-JavaScript fallback.
THEMES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "dark": (
        "Dark",
        "dark",
        (
            "#111820",
            "#19232b",
            "#1d2931",
            "#2b3940",
            "#34434a",
            "#eff5f3",
            "#bbc7c8",
            "#9aa9ad",
            "#849399",
            "#a5f2d1",
            "#10251d",
            "#ffb4a8",
            "#ffd68c",
        ),
    ),
    "light": (
        "Light",
        "light",
        (
            "#f3f5f4",
            "#ffffff",
            "#f6f8f7",
            "#e1e6e4",
            "#cdd6d3",
            "#16211d",
            "#3d4a46",
            "#5c6a66",
            "#6c7a76",
            "#0f7b56",
            "#ffffff",
            "#c4372b",
            "#9a6200",
        ),
    ),
    "dracula": (
        "Dracula",
        "dark",
        (
            "#21222c",
            "#282a36",
            "#2e303e",
            "#393b4b",
            "#44475a",
            "#f8f8f2",
            "#d4d4e4",
            "#a3a9cc",
            "#8890bd",
            "#bd93f9",
            "#21222c",
            "#ff6e6e",
            "#f1fa8c",
        ),
    ),
    "tokyo-night": (
        "Tokyo Night",
        "dark",
        (
            "#1a1b26",
            "#1f2335",
            "#24283b",
            "#292e42",
            "#3b4261",
            "#c0caf5",
            "#a9b1d6",
            "#8a93bd",
            "#737aa2",
            "#7aa2f7",
            "#16161e",
            "#f7768e",
            "#e0af68",
        ),
    ),
    "rose-pine": (
        "Rosé Pine",
        "dark",
        (
            "#191724",
            "#1f1d2e",
            "#26233a",
            "#2a273f",
            "#403d52",
            "#e0def4",
            "#c8c5df",
            "#908caa",
            "#7f7b98",
            "#ebbcba",
            "#191724",
            "#eb6f92",
            "#f6c177",
        ),
    ),
    "rose-pine-dawn": (
        "Rosé Pine Dawn",
        "light",
        (
            "#faf4ed",
            "#fffaf3",
            "#f4ede8",
            "#e6dfdb",
            "#cecacd",
            "#575279",
            "#625e83",
            "#797593",
            "#8e89a0",
            "#286983",
            "#fffaf3",
            "#b4637a",
            "#b8741a",
        ),
    ),
}
# The markdown and code readers use GitHub's light or dark palette by mode. These themes
# recolour the page and the syntax on top of it.
READER_THEMES: dict[str, dict[str, str]] = {
    "dracula": {
        "bgColor-default": "#282a36",
        "bgColor-muted": "#21222c",
        "fgColor-default": "#f8f8f2",
        "fgColor-muted": "#a3a9cc",
        "fgColor-accent": "#bd93f9",
        "borderColor-default": "#44475a",
        "borderColor-muted": "#393b4b",
        "color-prettylights-syntax-comment": "#6272a4",
        "color-prettylights-syntax-constant": "#bd93f9",
        "color-prettylights-syntax-entity": "#50fa7b",
        "color-prettylights-syntax-entity-tag": "#ff79c6",
        "color-prettylights-syntax-keyword": "#ff79c6",
        "color-prettylights-syntax-string": "#f1fa8c",
        "color-prettylights-syntax-variable": "#ffb86c",
        "color-prettylights-syntax-storage-modifier-import": "#f8f8f2",
    },
    "tokyo-night": {
        "bgColor-default": "#1a1b26",
        "bgColor-muted": "#16161e",
        "fgColor-default": "#c0caf5",
        "fgColor-muted": "#9aa5ce",
        "fgColor-accent": "#7aa2f7",
        "borderColor-default": "#3b4261",
        "borderColor-muted": "#292e42",
        "color-prettylights-syntax-comment": "#565f89",
        "color-prettylights-syntax-constant": "#ff9e64",
        "color-prettylights-syntax-entity": "#7aa2f7",
        "color-prettylights-syntax-entity-tag": "#f7768e",
        "color-prettylights-syntax-keyword": "#bb9af7",
        "color-prettylights-syntax-string": "#9ece6a",
        "color-prettylights-syntax-variable": "#2ac3de",
        "color-prettylights-syntax-storage-modifier-import": "#c0caf5",
    },
    "rose-pine": {
        "bgColor-default": "#191724",
        "bgColor-muted": "#1f1d2e",
        "fgColor-default": "#e0def4",
        "fgColor-muted": "#908caa",
        "fgColor-accent": "#c4a7e7",
        "borderColor-default": "#403d52",
        "borderColor-muted": "#26233a",
        "color-prettylights-syntax-comment": "#6e6a86",
        "color-prettylights-syntax-constant": "#c4a7e7",
        "color-prettylights-syntax-entity": "#ebbcba",
        "color-prettylights-syntax-entity-tag": "#9ccfd8",
        "color-prettylights-syntax-keyword": "#31748f",
        "color-prettylights-syntax-string": "#f6c177",
        "color-prettylights-syntax-variable": "#eb6f92",
        "color-prettylights-syntax-storage-modifier-import": "#e0def4",
    },
    "rose-pine-dawn": {
        "bgColor-default": "#faf4ed",
        "bgColor-muted": "#f2e9e1",
        "fgColor-default": "#575279",
        "fgColor-muted": "#797593",
        "fgColor-accent": "#907aa9",
        "borderColor-default": "#dfdad9",
        "borderColor-muted": "#f2e9e1",
        "color-prettylights-syntax-comment": "#9893a5",
        "color-prettylights-syntax-constant": "#907aa9",
        "color-prettylights-syntax-entity": "#d7827e",
        "color-prettylights-syntax-entity-tag": "#56949f",
        "color-prettylights-syntax-keyword": "#286983",
        "color-prettylights-syntax-string": "#ea9d34",
        "color-prettylights-syntax-variable": "#b4637a",
        "color-prettylights-syntax-storage-modifier-import": "#575279",
    },
}


def theme_app_css() -> str:
    rules = [
        (
            "  :root { --chip:color-mix(in srgb, var(--field) 50%, var(--line)); "
            "--dash:color-mix(in srgb, var(--edge) 70%, var(--muted)); "
            "--accent-line:color-mix(in srgb, var(--accent) 60%, var(--edge)); }"
        )
    ]
    for index, (name, (_, mode, values)) in enumerate(THEMES.items()):
        selector = (
            f':root, html[data-theme="{name}"]'
            if index == 0
            else f'html[data-theme="{name}"]'
        )
        props = " ".join(
            f"--{key}:{value};" for key, value in zip(THEME_KEYS, values, strict=True)
        )
        rules.append(f"  {selector} {{ color-scheme:{mode}; {props} }}")
    return "\n".join(rules)


HLJS_CSS = """
  .hljs { color:var(--fgColor-default); }
  .hljs-doctag, .hljs-keyword, .hljs-meta .hljs-keyword, .hljs-template-tag, .hljs-template-variable, .hljs-type, .hljs-variable.language_ { color:var(--color-prettylights-syntax-keyword); }
  .hljs-title, .hljs-title.class_, .hljs-title.class_.inherited__, .hljs-title.function_ { color:var(--color-prettylights-syntax-entity); }
  .hljs-attr, .hljs-attribute, .hljs-literal, .hljs-meta, .hljs-number, .hljs-operator, .hljs-selector-attr, .hljs-selector-class, .hljs-selector-id, .hljs-variable { color:var(--color-prettylights-syntax-constant); }
  .hljs-meta .hljs-string, .hljs-regexp, .hljs-string { color:var(--color-prettylights-syntax-string); }
  .hljs-built_in, .hljs-symbol { color:var(--color-prettylights-syntax-variable); }
  .hljs-code, .hljs-comment, .hljs-formula { color:var(--color-prettylights-syntax-comment); }
  .hljs-name, .hljs-quote, .hljs-selector-pseudo, .hljs-selector-tag { color:var(--color-prettylights-syntax-entity-tag); }
  .hljs-subst { color:var(--fgColor-default); }
  .hljs-section { color:var(--color-prettylights-syntax-markup-heading); font-weight:700; }
  .hljs-bullet { color:var(--color-prettylights-syntax-markup-list); }
  .hljs-emphasis { font-style:italic; }
  .hljs-strong { font-weight:700; }
  .hljs-addition { color:var(--color-prettylights-syntax-markup-inserted-text); background:var(--color-prettylights-syntax-markup-inserted-bg); }
  .hljs-deletion { color:var(--color-prettylights-syntax-markup-deleted-text); background:var(--color-prettylights-syntax-markup-deleted-bg); }
"""


def theme_reader_css() -> str:
    """GitHub's light and dark palettes keyed on the picked theme instead of the OS setting."""
    try:
        source = (VENDOR / "github-markdown.css").read_text(encoding="utf-8")
    except OSError:
        return HLJS_CSS
    rules = []
    for mode, props in re.findall(
        r"@media \(prefers-color-scheme: (dark|light)\) \{\s*\.markdown-body, \[data-theme=\"\w+\"\] \{(.*?)\n  \}\n\}",
        source,
        re.DOTALL,
    ):
        rules.append(
            f'  html[data-mode="{mode}"], html[data-mode="{mode}"] .markdown-body {{{props}\n  }}'
        )
    for name, values in READER_THEMES.items():
        props = " ".join(f"--{key}:{value};" for key, value in values.items())
        rules.append(
            f'  html[data-theme="{name}"], html[data-theme="{name}"] .markdown-body {{ {props} }}'
        )
    return "\n".join(rules) + HLJS_CSS


THEME_READER_CSS = theme_reader_css()


THEME_JS = """
(() => {
  const root = document.documentElement, key = 'sharei-theme';
  const themes = %s;
  const media = matchMedia('(prefers-color-scheme: dark)');
  function picked() {
    let saved = null;
    try { saved = localStorage.getItem(key); } catch (error) {}
    if (saved === 'auto' || (saved && saved in themes)) return saved;
    const fallback = root.dataset.themeDefault;
    return fallback && fallback in themes ? fallback : 'auto';
  }
  function apply() {
    const choice = picked();
    const theme = choice === 'auto' ? (media.matches ? 'dark' : 'light') : choice;
    root.dataset.choice = choice;
    root.dataset.theme = theme;
    root.dataset.mode = themes[theme][0];
    const meta = document.querySelector('meta[name=theme-color]');
    if (meta) meta.content = themes[theme][1];
  }
  window.shareiTheme = (name) => {
    try { localStorage.setItem(key, name); } catch (error) {}
    apply();
  };
  media.addEventListener('change', apply);
  addEventListener('storage', (event) => { if (event.key === key) apply(); });
  apply();
})();
"""


def theme_script(nonce: str = "") -> str:
    themes = {name: [mode, values[0]] for name, (_, mode, values) in THEMES.items()}
    attribute = f' nonce="{nonce}"' if nonce else ""
    return f"<script{attribute}>{THEME_JS % json.dumps(themes)}</script>"


THEME_PICKER_JS = """
(() => {
  const button = document.getElementById('theme-button');
  const menu = document.getElementById('theme-menu');
  function paint() {
    menu.querySelectorAll('button[data-theme]').forEach((item) => {
      item.setAttribute('aria-pressed', String(item.dataset.theme === document.documentElement.dataset.choice));
    });
  }
  function toggle(open) {
    menu.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    if (open) paint();
  }
  button.addEventListener('click', (event) => { event.stopPropagation(); toggle(menu.hidden); });
  menu.addEventListener('click', (event) => {
    const item = event.target.closest('button[data-theme]');
    if (!item) return;
    window.shareiTheme(item.dataset.theme);
    paint();
  });
  document.addEventListener('click', (event) => { if (!menu.hidden && !menu.contains(event.target)) toggle(false); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !menu.hidden) { toggle(false); button.focus(); } });
  const previousBusy = window.liveBusy;
  window.liveBusy = () => !menu.hidden || (previousBusy ? previousBusy() : false);
})();
"""


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
        f'<div class="theme-picker">{push_button}<button class="theme-button" id="theme-button" type="button" '
        'aria-label="Theme" title="Theme" aria-haspopup="true" aria-expanded="false">'
        '<svg viewBox="0 0 20 20" width="18" height="18" aria-hidden="true"><circle cx="10" cy="10" r="7.5" '
        'fill="none" stroke="currentColor" stroke-width="1.6"/><path d="M10 2.5a7.5 7.5 0 0 1 0 15z" '
        'fill="currentColor"/></svg></button>'
        f'<div class="theme-menu" id="theme-menu" hidden>{"".join(items)}</div></div>'
    )


EXTRA_CSS = """
  .tabs { position:fixed; left:0; right:0; bottom:0; z-index:5; display:grid; grid-template-columns:repeat(4, 1fr); padding:6px max(8px, env(safe-area-inset-left)) max(6px, env(safe-area-inset-bottom)) max(8px, env(safe-area-inset-right)); background:color-mix(in srgb, var(--base) 94%, transparent); border-top:1px solid var(--line); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); }
  .tab { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:3px; min-width:0; min-height:52px; padding:4px 2px; border-radius:12px; color:var(--muted); text-decoration:none; font-size:11.5px; font-weight:650; line-height:1; white-space:nowrap; -webkit-tap-highlight-color:transparent; transition:background .15s ease,color .15s ease; }
  .tab:hover { color:var(--ink); }
  .tab-icon { display:grid; place-items:center; width:46px; height:26px; border-radius:13px; font-size:15px; line-height:1; transition:background .15s ease; }
  .tab-count { position:absolute; top:2px; left:calc(50% + 10px); min-width:17px; padding:2px 4px; border-radius:9px; background:var(--line); color:var(--ink); font-size:10px; font-weight:700; line-height:1.1; text-align:center; font-variant-numeric:tabular-nums; }
  .tab-count:empty { display:none; }
  .tab[aria-current] { color:var(--accent); }
  .tab[aria-current] .tab-icon { background:var(--accent); color:var(--accent-ink); }
  .tab:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
  .theme-picker { position:absolute; top:18px; right:0; z-index:6; display:flex; gap:8px; }
  .theme-button { display:grid; place-items:center; width:36px; height:36px; border:1px solid var(--edge); border-radius:12px; background:var(--field); color:var(--muted); font:inherit; font-size:17px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .theme-button:hover, .theme-button[aria-expanded=true] { color:var(--ink); border-color:var(--accent-line); }
  .theme-button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .theme-menu { position:absolute; top:44px; right:0; display:grid; gap:2px; min-width:196px; padding:6px; white-space:nowrap; border:1px solid var(--edge); border-radius:14px; background:var(--panel); box-shadow:0 12px 32px rgba(0,0,0,.3); }
  .theme-menu[hidden] { display:none; }
  .theme-menu button { display:flex; align-items:center; gap:10px; padding:8px 10px; border:0; border-radius:10px; background:none; color:var(--ink); font:inherit; font-size:14px; font-weight:600; text-align:left; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .theme-menu button:hover { background:var(--field); }
  .theme-menu button:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
  .theme-menu button[aria-pressed=true] { background:color-mix(in srgb, var(--accent) 16%, var(--panel)); }
  .theme-menu button[aria-pressed=true]::after { content:"✓"; margin-left:auto; color:var(--accent); }
  .push-button[hidden] { display:none; }
  .push-button[aria-pressed=true] { color:var(--accent); border-color:var(--accent-line); }
  .push-button[aria-pressed=true] path:first-child { fill:currentColor; }
  .push-button:disabled { opacity:.6; cursor:progress; }
  .push-button .push-slash { display:none; }
  .push-button[data-state=blocked] .push-slash { display:inline; }
  .swatch { position:relative; flex:0 0 22px; height:22px; border:1px solid; border-radius:50%; }
  .swatch::after { content:""; position:absolute; inset:6px; border-radius:50%; background:currentColor; }
  .swatch.auto { border-color:#8a9590; background:linear-gradient(135deg, #f3f5f4 50%, #111820 50%); color:#0f7b56; }
  @media (min-width:600px) { .theme-picker { top:37px; } }
  @media (min-width:900px) {
    body { padding-left:96px; }
    .wrap { padding-bottom:48px; }
    .tabs { top:0; right:auto; width:96px; grid-template-columns:none; grid-auto-rows:min-content; align-content:start; gap:10px; padding:28px 8px; border-top:0; border-right:1px solid var(--line); }
    .tab { min-height:64px; font-size:12px; gap:6px; }
    .tab-icon { width:56px; height:32px; border-radius:16px; font-size:17px; }
    .tab-count { top:0; left:calc(50% + 14px); }
    .tab:hover .tab-icon { background:var(--field); }
    .tab[aria-current]:hover .tab-icon { background:var(--accent); }
  }
  .shelf-actions { display:flex; align-items:center; gap:10px; }
  .wipe { padding:6px 10px; border:1px solid color-mix(in srgb, var(--danger) 25%, var(--base)); border-radius:9px; background:color-mix(in srgb, var(--danger) 8%, var(--base)); color:var(--danger); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .wipe:hover { border-color:color-mix(in srgb, var(--danger) 50%, var(--base)); background:color-mix(in srgb, var(--danger) 14%, var(--base)); }
  .wipe:focus-visible { outline:2px solid var(--danger); outline-offset:2px; }
  .tile-wrap { position:relative; display:grid; min-width:0; }
  .tile-delete, .file-delete { position:absolute; top:5px; right:5px; display:grid; place-items:center; width:26px; height:26px; border:1px solid color-mix(in srgb, var(--danger) 35%, transparent); border-radius:8px; background:color-mix(in srgb, var(--base) 72%, transparent); color:var(--danger); font:inherit; font-size:12px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .tile-delete:focus-visible, .file-delete:focus-visible { outline:2px solid var(--danger); outline-offset:1px; }
  .annotate { padding:6px 10px; border:1px solid color-mix(in srgb, var(--accent) 35%, var(--base)); border-radius:9px; background:color-mix(in srgb, var(--accent) 10%, var(--base)); color:var(--accent); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .annotate:hover { border-color:color-mix(in srgb, var(--accent) 60%, var(--base)); background:color-mix(in srgb, var(--accent) 16%, var(--base)); }
  .annotate:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .annotate[hidden] { display:none; }
  .annotator { position:fixed; inset:0; z-index:20; display:flex; flex-direction:column; background:var(--base); padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .annotator-host { flex:1; min-height:0; }
  .annotator-host mjsui-annotation-editor { display:block; width:100%; height:100%; }
  .annotator-status { margin:0; padding:2px 12px; color:var(--danger); font-size:11.5px; text-align:center; }
  .annotator-status:empty { display:none; }
  .annotator-credit { margin:0; padding:3px 0; color:var(--faint); font-size:10.5px; line-height:1.4; text-align:center; }
  .annotator-credit a { color:var(--soft); text-decoration:underline; text-underline-offset:2px; }
  .file-row { position:relative; display:flex; }
  .file-row .file { flex:1; padding-right:80px; }
  .file-row.has-tools .file { padding-right:144px; }
  .file-tools { position:absolute; top:50%; right:10px; transform:translateY(-50%); display:flex; gap:6px; }
  .file-tools .file-delete { position:static; }
  .file-annotate, .file-expiry, .file-share { display:grid; place-items:center; width:26px; height:26px; border:1px solid color-mix(in srgb, var(--accent) 35%, transparent); border-radius:8px; background:color-mix(in srgb, var(--base) 72%, transparent); color:var(--accent); font:inherit; font-size:12px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .file-annotate:focus-visible, .file-expiry:focus-visible, .file-share:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
  .file-share[hidden] { display:none; }
  .file-qr { display:none; }
  @media (min-width:900px) {
    .file-qr { display:grid; place-items:center; width:26px; height:26px; border:1px solid color-mix(in srgb, var(--accent) 35%, transparent); border-radius:8px; background:color-mix(in srgb, var(--base) 72%, transparent); color:var(--accent); font:inherit; font-size:12px; line-height:1; cursor:pointer; }
    .file-qr:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
    .file-row .file { padding-right:112px; }
    .file-row.has-tools .file { padding-right:176px; }
  }
  .file-expiry { border-color:color-mix(in srgb, var(--warn) 30%, transparent); color:color-mix(in srgb, var(--warn) 70%, var(--muted)); }
  .file-expiry.set, .expiry-button.set { border-color:color-mix(in srgb, var(--warn) 60%, transparent); color:var(--warn); }
  .expires-left { color:var(--warn); }
  .expires-left[hidden] { display:none; }
  .expiry-button { padding:6px 10px; border:1px solid color-mix(in srgb, var(--warn) 25%, var(--base)); border-radius:9px; background:color-mix(in srgb, var(--warn) 8%, var(--base)); color:color-mix(in srgb, var(--warn) 70%, var(--muted)); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .expiry-button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .tile-expiry { position:absolute; top:5px; left:5px; padding:4px 7px; border-radius:8px; background:color-mix(in srgb, var(--base) 78%, transparent); color:var(--warn); font-size:11px; font-weight:650; line-height:1; pointer-events:none; }
  .expiry-menu { position:fixed; z-index:40; display:grid; gap:8px; padding:10px 12px; border:1px solid var(--edge); border-radius:12px; background:var(--base); box-shadow:0 12px 32px rgba(0,0,0,.35); color:var(--muted); font-size:12px; }
  .expiry-menu[hidden] { display:none; }
  .expiry-menu div { display:flex; flex-wrap:wrap; gap:6px; }
  .expiry-menu button { padding:7px 10px; border:1px solid var(--edge); border-radius:10px; background:var(--field); color:var(--muted); font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .expiry-menu button[aria-pressed=true] { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
  .expiry-menu button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .viewer-tools { display:flex; align-items:center; gap:8px; }
  .share { padding:6px 10px; border:1px solid var(--line); border-radius:9px; background:var(--panel); color:var(--ink); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .share:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .share[hidden] { display:none; }
  .wrap.wide { width:min(100% - 36px, 1180px); }
  .gallery { display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:12px 10px; }
  .tile { display:grid; gap:6px; min-width:0; color:var(--muted); text-decoration:none; font-size:11px; -webkit-tap-highlight-color:transparent; }
  .tile img { display:block; width:100%; aspect-ratio:9/16; object-fit:cover; object-position:top; border-radius:12px; border:1px solid var(--edge); background:var(--field); transition:transform .15s ease,border-color .15s ease; }
  .tile:hover img { border-color:var(--accent-line); }
  .tile:active img { transform:scale(.97); }
  .tile:focus-visible { outline:none; } .tile:focus-visible img { outline:3px solid var(--accent); outline-offset:2px; }
  .tile span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:0 2px; }
  body.viewing { overflow:hidden; }
  .viewer { position:fixed; inset:0; z-index:10; display:grid; grid-template-rows:auto minmax(0, 1fr) auto; background:color-mix(in srgb, var(--base) 97%, transparent); padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .viewer[hidden] { display:none; }
  .viewer-bar { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; }
  .counter { color:var(--soft); font-size:13px; font-variant-numeric:tabular-nums; }
  .close, .nav { display:grid; place-items:center; width:42px; height:42px; border:1px solid var(--line); border-radius:12px; background:var(--panel); color:var(--ink); font:inherit; font-size:17px; cursor:pointer; }
  .close:focus-visible, .nav:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .nav { position:absolute; top:50%; z-index:1; transform:translateY(-50%); font-size:28px; }
  .prev { left:16px; } .next { right:16px; }
  .viewer.single .nav { display:none; }
  .stage { position:relative; min-height:0; overflow:hidden; touch-action:pinch-zoom; user-select:none; -webkit-user-select:none; }
  .stage img { position:absolute; inset:0; margin:auto; max-width:calc(100% - 24px); max-height:100%; border-radius:14px; transition:transform .2s ease; -webkit-user-drag:none; }
  .caption { display:grid; gap:4px; padding:12px 16px 18px; text-align:center; }
  .caption strong { font-size:14px; font-weight:650; overflow-wrap:anywhere; }
  .caption small { color:var(--muted); font-size:12px; }
  @media (max-width:599px) { .gallery { grid-template-columns:repeat(auto-fill, minmax(96px, 1fr)); gap:10px 8px; } .nav { display:none; } }
"""

SHARE_JS = """
window.shareiCanShareFiles = (() => {
  try {
    const probe = new File([""], "sharei.png", { type: "image/png" });
    return navigator.canShare({ files: [probe] });
  } catch (error) {
    return false;
  }
})();
window.shareiShare = async (url, name) => {
  try {
    if (window.shareiCanShareFiles) {
      const response = await fetch(url);
      if (!response.ok) throw new Error("HTTP " + response.status);
      const blob = await response.blob();
      const type = blob.type || "application/octet-stream";
      await navigator.share({ files: [new File([blob], name, { type })] });
      return;
    }
    if (typeof navigator.share === "function") {
      await navigator.share({ url: new URL(url, location.href).href });
      return;
    }
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
  } catch (error) {
    if (error && error.name === "AbortError") return;
    alert("Could not share: " + (error && error.message ? error.message : error));
  }
};
if (typeof navigator.share === "function") {
  document.querySelectorAll("[data-share]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      window.shareiShare(button.dataset.share, button.dataset.name || "file");
    });
  });
}
"""

EXPIRY_JS = """
(() => {
  const choices = [["1h", 3600], ["24h", 86400], ["7d", 604800], ["30d", 2592000], ["Never", 0]];
  const left = (when) => {
    const seconds = Number(when) - Date.now() / 1000;
    if (seconds < 60) return "under a minute";
    if (seconds < 3600) return Math.round(seconds / 60) + "m";
    if (seconds < 172800) return Math.round(seconds / 3600) + "h";
    return Math.round(seconds / 86400) + "d";
  };
  function paint() {
    document.querySelectorAll("[data-expiry]").forEach((button) => {
      const when = button.dataset.expires;
      button.classList.toggle("set", !!when);
      button.textContent = when && !("compact" in button.dataset) ? "⏱ " + left(when) : (button.dataset.label || "⏱");
      button.title = when ? "Expires in " + left(when) : "Set an expiry";
    });
    document.querySelectorAll("[data-expires-left]").forEach((label) => {
      const when = label.dataset.expiresLeft;
      label.hidden = !when;
      if (when) label.textContent = (label.dataset.prefix || "") + left(when);
    });
  }
  window.shareiExpiryPaint = paint;

  const menu = document.createElement("div");
  menu.className = "expiry-menu";
  menu.hidden = true;
  menu.setAttribute("role", "dialog");
  menu.setAttribute("aria-label", "Delete after");
  menu.innerHTML = '<span>Delete after</span><div></div>';
  const row = menu.querySelector("div");
  let owner = null;
  for (const [label, seconds] of choices) {
    const choice = document.createElement("button");
    choice.type = "button";
    choice.textContent = label;
    choice.dataset.seconds = seconds;
    choice.addEventListener("click", () => apply(seconds));
    row.append(choice);
  }
  document.body.append(menu);
  const previousBusy = window.liveBusy;
  window.liveBusy = () => !menu.hidden || (previousBusy ? previousBusy() : false);

  function close() { menu.hidden = true; owner = null; }
  function open(button) {
    owner = button;
    row.querySelectorAll("button").forEach((choice) => choice.setAttribute("aria-pressed", String(choice.dataset.seconds === "0" && !button.dataset.expires)));
    menu.hidden = false;
    const box = button.getBoundingClientRect(), width = menu.offsetWidth, height = menu.offsetHeight;
    menu.style.left = Math.max(8, Math.min(box.right - width, innerWidth - width - 8)) + "px";
    menu.style.top = (box.bottom + height + 12 > innerHeight ? Math.max(8, box.top - height - 6) : box.bottom + 6) + "px";
    row.querySelector("button").focus({ preventScroll: true });
  }
  async function apply(seconds) {
    const button = owner;
    close();
    if (!button) return;
    const query = "?target=" + encodeURIComponent(button.dataset.target) + "&key=" + encodeURIComponent(button.dataset.key) + "&seconds=" + seconds;
    try {
      const response = await fetch("/expiry" + query, { method: "POST" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      location.reload();
    } catch (error) {
      alert("Could not set the expiry: " + error.message);
    }
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-expiry]");
    if (button) {
      event.preventDefault();
      event.stopPropagation();
      if (owner === button) close(); else open(button);
    } else if (!menu.contains(event.target)) close();
  }, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) { event.stopPropagation(); close(); }
  }, true);
  addEventListener("resize", close);
  paint();
  setInterval(paint, 60000);
})();
"""

CAROUSEL_JS = """
(() => {
  const shots = JSON.parse(document.getElementById("shots").textContent);
  const $ = (id) => document.getElementById(id);
  const viewer = $("viewer"), stage = $("stage"), photo = $("photo");
  let current = -1, loadToken = 0;
  window.liveBusy = () => !viewer.hidden;
  if (shots.length < 2) viewer.classList.add("single");

  function show(index) {
    current = (index + shots.length) % shots.length;
    const shot = shots[current];
    const token = ++loadToken;
    photo.src = shot.thumb || shot.url;
    photo.alt = shot.name;
    const full = new Image();
    full.onload = () => { if (token === loadToken) photo.src = shot.url; };
    full.src = shot.url;
    const annotate = $("annotate-shot");
    annotate.hidden = !/\\.(png|jpe?g|webp)$/i.test(shot.key);
    annotate.dataset.key = shot.key;
    annotate.dataset.url = shot.url;
    annotate.dataset.name = shot.name;
    const expiry = $("expiry-shot");
    expiry.dataset.key = shot.key;
    expiry.dataset.expires = shot.expires || "";
    if (window.shareiExpiryPaint) window.shareiExpiryPaint();
    $("counter").textContent = `${current + 1} / ${shots.length}`;
    $("caption-name").textContent = shot.name;
    $("caption-meta").textContent = `${shot.project} · ${shot.date}`;
    for (const offset of [-1, 1]) {
      const neighbour = shots[(current + offset + shots.length) % shots.length];
      new Image().src = neighbour.thumb || neighbour.url;
    }
  }
  function open(index, push) {
    show(index);
    viewer.hidden = false;
    document.body.classList.add("viewing");
    history[push ? "pushState" : "replaceState"]({ viewer: true }, "", "#shot=" + shots[current].key);
    $("close").focus({ preventScroll: true });
  }
  function step(offset) {
    show(current + offset);
    history.replaceState({ viewer: true }, "", "#shot=" + shots[current].key);
  }
  function hide() {
    viewer.hidden = true;
    document.body.classList.remove("viewing");
    const tile = document.querySelector(`.tile[data-index="${current}"]`);
    current = -1;
    if (tile) tile.focus({ preventScroll: true });
  }
  function close() {
    if (history.state && history.state.viewer && history.length > 1) return history.back();
    hide();
    history.replaceState(null, "", location.pathname);
  }
  function fromHash() {
    const index = shots.findIndex((shot) => location.hash === "#shot=" + shot.key);
    if (index >= 0) open(index, false); else if (current >= 0) hide();
  }

  document.querySelectorAll(".tile").forEach((tile) => tile.addEventListener("click", (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button) return;
    event.preventDefault();
    open(Number(tile.dataset.index), true);
  }));
  $("close").addEventListener("click", close);
  $("share-shot").hidden = typeof navigator.share !== "function";
  $("share-shot").addEventListener("click", () => {
    if (current >= 0) window.shareiShare(shots[current].url, shots[current].name);
  });
  $("prev").addEventListener("click", () => step(-1));
  $("next").addEventListener("click", () => step(1));
  document.addEventListener("sharei:annotated", (event) => {
    const index = shots.findIndex((shot) => shot.key === event.detail.key);
    if (index < 0) return;
    shots[index].url = event.detail.url;
    shots[index].thumb = event.detail.url.replace("/shot/", "/thumb/");
    const tile = document.querySelector(`.tile[data-index="${index}"] img`);
    if (tile) tile.src = shots[index].thumb;
    if (current === index) show(current);
  });
  document.addEventListener("keydown", (event) => {
    if (viewer.hidden || document.querySelector(".annotator")) return;
    if (event.key === "ArrowLeft") step(-1);
    else if (event.key === "ArrowRight") step(1);
    else if (event.key === "Escape") close();
  });
  window.addEventListener("popstate", fromHash);

  async function remove(url, question) {
    if (!confirm(question)) return;
    try {
      const response = await fetch(url, { method: "POST" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      location.reload();
    } catch (error) {
      alert("Could not delete: " + error.message);
    }
  }
  document.querySelectorAll(".tile-delete").forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    remove("/shots/delete/" + button.dataset.key, "Delete this screenshot?");
  }));
  $("delete-shot").addEventListener("click", () => {
    if (current >= 0) remove("/shots/delete/" + shots[current].key, "Delete this screenshot?");
  });
  const wipe = $("delete-all");
  if (wipe) wipe.addEventListener("click", () => remove("/shots/delete-all", `Delete ALL ${shots.length} screenshots? This cannot be undone.`));
  document.querySelectorAll("[data-wipe-project]").forEach((button) => button.addEventListener("click", () => {
    const project = button.dataset.wipeProject;
    remove("/shots/delete-all?project=" + encodeURIComponent(project), `Delete ${button.dataset.count === "1" ? "the screenshot" : "all " + button.dataset.count + " screenshots"} in ${project}? This cannot be undone.`);
  }));

  let startX = null, startY = 0, deltaX = 0;
  stage.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button) return;
    startX = event.clientX; startY = event.clientY; deltaX = 0;
    photo.style.transition = "none";
  });
  stage.addEventListener("pointermove", (event) => {
    if (startX === null) return;
    deltaX = event.clientX - startX;
    if (Math.abs(deltaX) > Math.abs(event.clientY - startY)) photo.style.transform = `translateX(${deltaX}px)`;
  });
  const release = (event) => {
    if (startX === null) return;
    const travel = { x: deltaX, y: event.clientY - startY };
    startX = null;
    photo.style.transition = "";
    photo.style.transform = "";
    if (Math.abs(travel.x) > 50) return step(travel.x < 0 ? 1 : -1);
    // A tap pages like a book: left third back, right third forward, middle closes.
    if (event.type !== "pointerup" || Math.abs(travel.x) >= 6 || Math.abs(travel.y) >= 10) return;
    const box = stage.getBoundingClientRect();
    const side = (event.clientX - box.left) / box.width;
    if (side < 1 / 3) step(-1);
    else if (side > 2 / 3) step(1);
    else close();
  };
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);
  stage.addEventListener("pointerleave", release);

  fromHash();
})();
"""


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
                "thumb": f"/thumb/{quote(relative.as_posix())}?v={int(modified)}",
                "timestamp": str(modified),
                "expires": str(expires_at(path) or ""),
            }
        )
    return sorted(shots, key=lambda shot: float(shot["timestamp"]), reverse=True)


def thumbnail_cache_path(path: Path) -> Path:
    digest = hashlib.sha256(
        f"{path.resolve()}:{path.stat().st_mtime_ns}:{THUMB_MAX}:top".encode()
    ).hexdigest()[:32]
    return THUMBS / f"{digest}.webp"


def vector_headers(base: dict[str, str]) -> dict[str, str]:
    """Serve an SVG inline but unable to reach the page: its scripts never run."""
    return {
        **base,
        "Content-Security-Policy": VECTOR_CSP,
        "X-Content-Type-Options": "nosniff",
    }


def render_thumbnail(path: Path) -> bytes:
    # Lazy import so a missing Pillow degrades to serving the original image.
    image_module = importlib.import_module("PIL.Image")
    with image_module.open(path) as image:
        image.draft("RGB", (THUMB_MAX, THUMB_MAX))
        # Tiles show the top 9:16 of a shot, so a tall page is cropped to that before shrinking
        # instead of being squeezed into a sliver the tile then has to blow up.
        width, height = image.size
        if height * 9 > width * 16:
            image = image.crop((0, 0, width, -(-width * 16 // 9)))
        image.thumbnail((THUMB_MAX, THUMB_MAX))
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "WEBP", quality=72, method=4)
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
    try:
        cached = thumbnail_cache_path(path)
    except OSError:
        return
    cached.unlink(missing_ok=True)


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
    path.unlink()
    expiry_forget(path)
    return True


def delete_all_poub(project: str | None = None) -> int:
    deleted = 0
    for path in poub_paths(project):
        try:
            path.unlink()
        except OSError:
            continue
        expiry_forget(path)
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
                if relative.parts[1] == "shots":
                    forget_thumbnail(path)
                path.unlink()
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
        return candidate
    raise OSError("too many files already use that name")


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


def github_token() -> str | None:
    global GITHUB_TOKEN, TOKEN_FROM_PASS_TRIED
    with TOKEN_LOCK:
        if GITHUB_TOKEN or not GITHUB_TOKEN_PASS or TOKEN_FROM_PASS_TRIED:
            return GITHUB_TOKEN
        # Asked once: a failing entry would otherwise run gpg on every render.
        TOKEN_FROM_PASS_TRIED = True
        try:
            result = subprocess.run(
                ["pass", "show", GITHUB_TOKEN_PASS],
                stdin=subprocess.DEVNULL,
                capture_output=True,
                text=True,
                timeout=30,
                check=True,
            )
        except (OSError, subprocess.SubprocessError) as error:
            detail = getattr(error, "stderr", None) or error
            print(
                f"pass show {GITHUB_TOKEN_PASS} failed, rendering without a token: {detail}"
            )
            return None
        GITHUB_TOKEN = result.stdout.partition("\n")[0].strip() or None
        return GITHUB_TOKEN


def github_markdown(text: str) -> tuple[str | None, str | None]:
    """GitHub's HTML for text, or None and the reason GitHub could not render it."""
    data = text.encode("utf-8")
    cached = MARKDOWN_CACHE / f"{hashlib.sha256(data).hexdigest()}.html"
    try:
        return cached.read_text("utf-8"), None
    except OSError:
        pass
    headers = {
        "Accept": "application/vnd.github+json",
        "Content-Type": "application/json",
        "User-Agent": "sharei",
        "X-GitHub-Api-Version": "2022-11-28",
    }
    token = github_token()
    if token:
        headers["Authorization"] = f"Bearer {token}"
    request = urllib.request.Request(
        f"{GITHUB_API}/markdown",
        data=json.dumps({"text": text, "mode": "gfm"}).encode("utf-8"),
        headers=headers,
        method="POST",
    )
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            rendered = response.read().decode("utf-8")
    except urllib.error.HTTPError as error:
        print(f"GitHub markdown API answered {error.code}: {error.reason}")
        return None, f"GitHub could not render it ({error.code} {error.reason})."
    except (OSError, ValueError) as error:
        print(f"GitHub markdown API unreachable: {error}")
        return None, "GitHub is unreachable."
    try:
        MARKDOWN_CACHE.mkdir(parents=True, exist_ok=True)
        temporary = cached.with_name(f"{cached.name}.{secrets.token_hex(4)}.part")
        temporary.write_text(rendered, "utf-8")
        os.replace(temporary, cached)
    except OSError:
        pass
    return rendered, None


MARKDOWN_CSS = """
  * { box-sizing:border-box }
  html { scroll-padding-top:64px; }
  body { margin:0; background:var(--bgColor-default, Canvas); color:var(--fgColor-default, CanvasText); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif; }
  .bar { position:sticky; top:0; z-index:2; display:flex; align-items:center; gap:12px; padding:10px max(16px, env(safe-area-inset-left)); background:color-mix(in srgb, var(--bgColor-muted) 92%, transparent); border-bottom:1px solid var(--borderColor-default); backdrop-filter:blur(8px); font-size:14px; }
  .bar a { color:var(--fgColor-accent); text-decoration:none; font-weight:600; white-space:nowrap; }
  .bar a:hover { text-decoration:underline; }
  .bar .name { flex:1; min-width:0; overflow:hidden; color:var(--fgColor-muted); text-overflow:ellipsis; white-space:nowrap; }
  .bar nav { display:flex; gap:14px; }
  .bar nav button { padding:0; border:0; background:none; color:var(--fgColor-accent); font:inherit; font-weight:600; cursor:pointer; }
  .bar nav button:hover { text-decoration:underline; }
  .bar nav .renderer { display:inline-flex; align-items:center; gap:3px; margin:-4px 0; padding:4px 6px; border-radius:6px; color:var(--fgColor-muted); }
  .bar nav .renderer:hover { color:var(--fgColor-default); text-decoration:none; }
  .bar nav .renderer[aria-pressed="true"] { color:var(--fgColor-accent); background:color-mix(in srgb, var(--fgColor-accent) 18%, transparent); }
  .bar nav .renderer:disabled { opacity:.5; cursor:progress; }
  .bar nav .renderer[hidden] { display:none; }
  .renderer svg { display:block; fill:currentColor; }
  .page { width:min(100%, 980px); margin:0 auto; padding:24px 16px 64px; }
  .notice { margin:0 0 16px; padding:10px 14px; border:1px solid color-mix(in srgb, var(--borderColor-attention-emphasis) 45%, transparent); border-radius:6px; background:var(--bgColor-attention-muted); color:var(--fgColor-default); font-size:14px; }
  .toc { margin:0 0 20px; padding:8px 14px; border:1px solid var(--borderColor-default); border-radius:6px; font-size:14px; }
  .toc summary { cursor:pointer; font-weight:600; padding:4px 0; }
  .toc ol { margin:6px 0 6px; padding:0; list-style:none; }
  .toc li { padding:3px 0; }
  .toc a { color:var(--fgColor-accent); text-decoration:none; }
  .toc a:hover { text-decoration:underline; }
  .markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5, .markdown-body h6 { position:relative; }
  .markdown-body .anchor { position:absolute; left:-1.1em; padding-right:.3em; color:var(--fgColor-muted); text-decoration:none; opacity:0; }
  .markdown-body :is(h1,h2,h3,h4,h5,h6):hover .anchor, .markdown-body .anchor:focus { opacity:1; }
  .markdown-body .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  .mermaid-diagram { margin:0 0 16px; overflow-x:auto; text-align:center; }
  .mermaid-diagram svg { max-width:100%; height:auto; }
  @media (min-width:768px) { .page { padding:32px 32px 80px; } }
"""

# The markdown reader only. Everything is scoped under .reader so it beats github-markdown.css
# by specificity rather than by source order.
READER_CSS = """
  @media (prefers-reduced-motion:no-preference) { html { scroll-behavior:smooth; } }
  ::selection { background:color-mix(in srgb, var(--fgColor-accent) 28%, transparent); }
  .bar.progress::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:2px; background:var(--fgColor-accent); transform:scaleX(var(--progress, 0)); transform-origin:left; pointer-events:none; }
  .page.reader { width:min(100%, 820px); }
  .reader .notice { border-radius:10px; }

  .reader .markdown-body { --measure:46rem; --mono:ui-monospace,"JetBrains Mono","SF Mono","Cascadia Code",Menlo,Consolas,monospace; max-width:var(--measure); margin:0 auto; font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans",sans-serif; font-size:16px; line-height:1.7; font-feature-settings:"kern","liga","calt"; text-rendering:optimizeLegibility; -webkit-font-smoothing:antialiased; overflow-wrap:break-word; }
  .reader .markdown-body > :first-child { margin-top:0 !important; }
  .reader .markdown-body p, .reader .markdown-body li { text-wrap:pretty; }

  .reader .markdown-body :is(h1, h2, h3, h4, h5, h6) { color:var(--fgColor-default); font-weight:700; letter-spacing:-.015em; line-height:1.25; text-wrap:balance; border:0; padding:0; }
  .reader .markdown-body h1 { margin:.2em 0 .55em; font-size:clamp(2rem, 1.45rem + 2.4vw, 2.75rem); font-weight:800; letter-spacing:-.032em; line-height:1.1; }
  .reader .markdown-body h2 { margin:1.8em 0 .65em; padding-top:1.1em; border-top:1px solid var(--borderColor-muted); font-size:1.55rem; letter-spacing:-.022em; }
  .reader .markdown-body :is(h1 + h2, hr + h2, h2:first-child) { margin-top:.6em; padding-top:0; border-top:0; }
  .reader .markdown-body h3 { margin:1.6em 0 .5em; font-size:1.22rem; }
  .reader .markdown-body h4 { margin:1.6em 0 .5em; font-size:1.04rem; }
  .reader .markdown-body :is(h5, h6) { margin:1.5em 0 .4em; color:var(--fgColor-muted); font-size:.95rem; }
  .reader .markdown-body h1 + p { color:var(--fgColor-muted); font-size:1.13em; line-height:1.6; }
  .reader .markdown-body .anchor { left:-1em; color:var(--fgColor-accent); font-weight:500; }

  .reader .markdown-body a:not(.anchor) { color:var(--fgColor-accent); text-decoration:underline; text-decoration-color:color-mix(in srgb, var(--fgColor-accent) 35%, transparent); text-decoration-thickness:.08em; text-underline-offset:.2em; transition:text-decoration-color .15s; }
  .reader .markdown-body a:not(.anchor):hover { text-decoration-color:currentColor; }
  .reader .markdown-body a:focus-visible, .reader .toc a:focus-visible { outline:2px solid var(--focus-outlineColor, var(--fgColor-accent)); outline-offset:2px; border-radius:3px; }
  .reader .markdown-body strong { font-weight:650; color:var(--fgColor-default); }

  .reader .markdown-body :is(ul, ol) { padding-left:1.6em; }
  .reader .markdown-body li + li, .reader .markdown-body li > :is(ul, ol) { margin-top:.35em; }
  .reader .markdown-body li::marker { color:var(--fgColor-muted); }
  .reader .markdown-body ol > li::marker { font-variant-numeric:tabular-nums; font-weight:600; }

  .reader .markdown-body :not(pre) > code, .reader .markdown-body :not(pre) > tt { padding:.14em .4em; border:1px solid color-mix(in srgb, var(--fgColor-default) 7%, transparent); border-radius:6px; background:color-mix(in srgb, var(--fgColor-default) 7%, transparent); font-family:var(--mono); font-size:.85em; }
  .reader .markdown-body a > code { color:inherit; }

  .reader .code-block { margin:0 0 1.3em; border:1px solid var(--borderColor-default); border-radius:12px; background:var(--bgColor-muted); overflow:hidden; }
  .reader .code-block-head { display:flex; align-items:center; justify-content:space-between; gap:8px; min-height:36px; padding:4px 6px 4px 14px; border-bottom:1px solid var(--borderColor-muted); color:var(--fgColor-muted); font:12px/1 var(--mono); }
  .reader .code-block-head button { display:inline-flex; align-items:center; gap:6px; padding:5px 9px; border:1px solid transparent; border-radius:7px; background:none; color:inherit; font:600 12px/1 system-ui,sans-serif; cursor:pointer; }
  .reader .code-block-head button:hover { border-color:var(--borderColor-default); color:var(--fgColor-default); }
  .reader .code-block-head button:focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:1px; }
  .reader .code-block-head button.copied { color:var(--fgColor-success); }
  .reader .code-block-head svg { fill:currentColor; }
  .reader .code-block :is(.highlight, .snippet-clipboard-content) { margin:0; }
  .reader .markdown-body .code-block pre { margin:0; padding:14px 16px; border-radius:0; background:none; font-family:var(--mono); font-size:13.5px; line-height:1.65; tab-size:4; }
  .reader .markdown-body .code-block pre code { font-size:inherit; }

  .reader .markdown-body blockquote { margin:0 0 1.15em; padding:.15em 0 .15em 1.15em; border-left:3px solid color-mix(in srgb, var(--fgColor-accent) 45%, var(--borderColor-default)); color:var(--fgColor-muted); }

  .reader .markdown-body .markdown-alert { --alert:var(--borderColor-accent-emphasis); margin:0 0 1.3em; padding:.85em 1.15em; border:0; border-left:3px solid var(--alert); border-radius:4px 12px 12px 4px; background:color-mix(in srgb, var(--alert) 9%, transparent); color:var(--fgColor-default); }
  .reader .markdown-body .markdown-alert.markdown-alert-tip { --alert:var(--borderColor-success-emphasis); }
  .reader .markdown-body .markdown-alert.markdown-alert-important { --alert:var(--borderColor-done-emphasis); }
  .reader .markdown-body .markdown-alert.markdown-alert-warning { --alert:var(--borderColor-attention-emphasis); }
  .reader .markdown-body .markdown-alert.markdown-alert-caution { --alert:var(--borderColor-danger-emphasis); }
  .reader .markdown-body .markdown-alert .markdown-alert-title { margin-bottom:.35em; font-weight:650; }

  .reader .markdown-body table { border-collapse:separate; border-spacing:0; border:1px solid var(--borderColor-default); border-radius:12px; font-size:.93em; font-variant-numeric:tabular-nums; }
  .reader .markdown-body table :is(th, td) { padding:9px 14px; border:0; border-bottom:1px solid var(--borderColor-muted); }
  .reader .markdown-body table :is(th, td) + :is(th, td) { border-left:1px solid var(--borderColor-muted); }
  .reader .markdown-body table th { background:var(--bgColor-muted); font-weight:650; text-align:left; }
  .reader .markdown-body table th[align="center"], .reader .markdown-body table td[align="center"] { text-align:center; }
  .reader .markdown-body table th[align="right"], .reader .markdown-body table td[align="right"] { text-align:right; }
  .reader .markdown-body table :is(th, td):is([align="right"], [align="center"]) { white-space:nowrap; }
  .reader .markdown-body table tr { background:none; border:0; }
  .reader .markdown-body table tbody tr:nth-child(2n) { background:color-mix(in srgb, var(--bgColor-muted) 55%, transparent); }
  .reader .markdown-body table tr:last-child > :is(th, td) { border-bottom:0; }
  .reader .markdown-body table thead + tbody tr:first-child > * { border-top:0; }

  .reader .markdown-body .contains-task-list { padding-left:.2em; }
  .reader .markdown-body .task-list-item { list-style:none; }
  .reader .markdown-body .task-list-item + .task-list-item { margin-top:.45em; }
  .reader .markdown-body .task-list-item-checkbox { appearance:none; -webkit-appearance:none; width:1.1em; height:1.1em; margin:0 .55em 0 0; vertical-align:-.18em; border:1.5px solid var(--borderColor-default); border-radius:5px; background:var(--bgColor-default); }
  .reader .markdown-body .task-list-item-checkbox { display:inline-grid; place-content:center; }
  .reader .markdown-body .task-list-item-checkbox:checked { border-color:var(--fgColor-accent); background:var(--fgColor-accent); }
  .reader .markdown-body .task-list-item-checkbox:checked::before { content:""; width:.28em; height:.55em; margin-top:-.12em; border:solid var(--bgColor-default); border-width:0 .13em .13em 0; transform:rotate(45deg); }
  .reader .markdown-body .task-list-item:has(> .task-list-item-checkbox:checked) { color:var(--fgColor-muted); }

  .reader .markdown-body hr { width:5rem; height:3px; margin:2.6em auto; border:0; border-radius:3px; background:var(--borderColor-default); }
  .reader .markdown-body img { border-radius:10px; }
  .reader .markdown-body :is(a, p) > img:only-child { display:inline-block; }
  .reader .markdown-body details { margin:0 0 1.15em; padding:.55em 1em; border:1px solid var(--borderColor-default); border-radius:12px; }
  .reader .markdown-body details > summary { margin:-.55em -1em; padding:.55em 1em; font-weight:600; cursor:pointer; }
  .reader .markdown-body details[open] > summary { margin-bottom:.6em; border-bottom:1px solid var(--borderColor-muted); }
  .reader .markdown-body kbd { font-family:var(--mono); }
  .reader .markdown-body .footnotes { margin-top:3em; padding-top:1.2em; border-top:1px solid var(--borderColor-muted); color:var(--fgColor-muted); font-size:.88em; }
  .reader .mermaid-diagram { margin:0 0 1.3em; padding:20px 16px; border:1px solid var(--borderColor-muted); border-radius:12px; background:var(--bgColor-muted); }

  .reader .toc { margin:0 auto 28px; max-width:46rem; padding:6px 16px; border-color:var(--borderColor-muted); border-radius:12px; background:color-mix(in srgb, var(--bgColor-muted) 60%, transparent); }
  .reader .toc summary { color:var(--fgColor-muted); font-size:13px; }
  .reader .toc ol { margin:4px 0 10px; border-left:1px solid var(--borderColor-muted); }
  .reader .toc li { padding:0; }
  .reader .toc a { display:block; margin-left:-1px; padding:4px 0 4px 12px; border-left:2px solid transparent; color:var(--fgColor-muted); line-height:1.4; }
  .reader .toc a:hover { color:var(--fgColor-default); text-decoration:none; }
  .reader .toc a[aria-current="location"] { border-left-color:var(--fgColor-accent); color:var(--fgColor-default); font-weight:600; }

  @media (max-width:767px) { .reader .markdown-body table :is(th, td) { padding:8px 10px; } }
  @media (min-width:768px) { .reader .markdown-body { font-size:17px; } .reader .markdown-body .code-block pre { font-size:14px; } }
  @media (min-width:1240px) {
    .page.reader { width:100%; display:grid; grid-template-columns:minmax(0, 46rem) 232px; justify-content:center; column-gap:64px; align-items:start; }
    .page.reader > * { grid-column:1; }
    .reader .markdown-body { width:100%; margin:0; }
    .reader .toc { grid-column:2; grid-row:1 / span 3; position:sticky; top:76px; max-height:calc(100vh - 100px); margin:0; padding:0 0 0 2px; border:0; background:none; overflow:auto; scrollbar-width:thin; }
    .reader .toc summary { pointer-events:none; list-style:none; padding:0 0 6px; }
    .reader .toc summary::-webkit-details-marker { display:none; }
  }
"""

# Octicons mark-github and markdown.
RENDERER_BUTTON = (
    '<button type="button" class="renderer" id="renderer" aria-pressed="false" '
    'aria-label="Render with GitHub" title="Render with GitHub" hidden>'
    '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M8 0c4.42 0 8 3.58 8 8a8.013 8.013 0 0 1-5.45 7.59c-.4.08-.55-.17-.55-.38 0-.27.01-1.13.01-2.2 0-.75-.25-1.23-.54-1.48 1.78-.2 3.65-.88 3.65-3.95 0-.88-.31-1.59-.82-2.15.08-.2.36-1.02-.08-2.12 0 0-.67-.22-2.2.82-.64-.18-1.32-.27-2-.27-.68 0-1.36.09-2 .27-1.53-1.03-2.2-.82-2.2-.82-.44 1.1-.16 1.92-.08 2.12-.51.56-.82 1.28-.82 2.15 0 3.06 1.86 3.75 3.64 3.95-.23.2-.44.55-.51 1.07-.46.21-1.61.55-2.33-.66-.15-.24-.6-.83-1.23-.82-.67.01-.27.38.01.53.34.19.73.9.82 1.13.16.45.68 1.31 2.69.94 0 .67.01 1.3.01 1.49 0 .21-.15.45-.55.38A7.995 7.995 0 0 1 0 8c0-4.42 3.58-8 8-8Z"></path></svg>'
    '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M14.85 3c.63 0 1.15.52 1.14 1.15v7.7c0 .63-.51 1.15-1.15 1.15H1.15C.52 13 0 12.48 0 11.84V4.15C0 3.52.52 3 1.15 3ZM9 11V5H7L5.5 7 4 5H2v6h2V8l1.5 1.92L7 8v3Zm2.99.5L14.5 8H13V5h-2v3H9.5Z"></path></svg>'
    "</button>"
)

MARKDOWN_SCRIPTS = (
    "highlight.min.js",
    "markdown-it.min.js",
    "markdown-it-footnote.min.js",
    "markdown-it-emoji.min.js",
    "purify.min.js",
)

MARKDOWN_JS = """
(() => {
const article = document.querySelector('article.markdown-body');
const toc = document.getElementById('toc');
const source = JSON.parse(document.getElementById('markdown-source').textContent);
const poub = article.dataset.poub || '';
const md = article.dataset.md || '';
const outside = /^(?:[a-z][a-z0-9+.-]*:|#|\\/)/i;
const markdownName = /\\.(?:md|markdown)$/i;

// GitHub's alert titles and octicons, so github-markdown.css styles them as on github.com.
const ALERTS = {
  note: ['Note', 'info', 'M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.5 7.75A.75.75 0 0 1 7.25 7h1a.75.75 0 0 1 .75.75v2.75h.25a.75.75 0 0 1 0 1.5h-2a.75.75 0 0 1 0-1.5h.25v-2h-.25a.75.75 0 0 1-.75-.75ZM8 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z'],
  tip: ['Tip', 'light-bulb', 'M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z'],
  important: ['Important', 'report', 'M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0 1 14.25 13H8.06l-2.573 2.573A1.458 1.458 0 0 1 3 14.543V13H1.75A1.75 1.75 0 0 1 0 11.25Zm1.75-.25a.25.25 0 0 0-.25.25v9.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h6.5a.25.25 0 0 0 .25-.25v-9.5a.25.25 0 0 0-.25-.25Zm7 2.25v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 9a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z'],
  warning: ['Warning', 'alert', 'M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z'],
  caution: ['Caution', 'stop', 'M4.47.22A.749.749 0 0 1 5 0h6c.199 0 .389.079.53.22l4.25 4.25c.141.14.22.331.22.53v6a.749.749 0 0 1-.22.53l-4.25 4.25A.749.749 0 0 1 11 16H5a.749.749 0 0 1-.53-.22L.22 11.53A.749.749 0 0 1 0 11V5c0-.199.079-.389.22-.53Zm.84 1.28L1.5 5.31v5.38l3.81 3.81h5.38l3.81-3.81V5.31L10.69 1.5ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z'],
};
const ALERT_MARK = /^\\[!(note|tip|important|warning|caution)\\][ \\t]*(?:\\n|$)/i;
const TASK_MARK = /^\\[([ xX])\\][ \\t]+/;

// Task lists, alerts and table alignment, written the way GitHub's renderer writes them.
function githubFlavour(markdown) {
  markdown.core.ruler.push('sharei_github', (state) => {
    const tokens = state.tokens;
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index];
      if ((token.type === 'th_open' || token.type === 'td_open') && token.attrGet('style')) {
        const align = /text-align:(left|right|center)/.exec(token.attrGet('style'));
        token.attrs = token.attrs.filter((attr) => attr[0] !== 'style');
        if (align) token.attrSet('align', align[1]);
      }
      const inline = tokens[index + 2];
      if (!inline || inline.type !== 'inline' || tokens[index + 1].type !== 'paragraph_open') continue;
      const children = inline.children || [];
      if (token.type === 'blockquote_open') {
        const match = ALERT_MARK.exec(inline.content);
        if (!match) continue;
        const kind = match[1].toLowerCase();
        let depth = 0, close = index;
        for (; close < tokens.length; close++) {
          if (tokens[close].type === 'blockquote_open') depth++;
          else if (tokens[close].type === 'blockquote_close' && --depth === 0) break;
        }
        token.meta = { alert: kind };
        tokens[close].meta = { alert: kind };
        const marker = match[0].trim();
        let consumed = '';
        while (children.length && children[0].type === 'text' && consumed.length < marker.length) consumed += children.shift().content;
        if (children.length && /^(soft|hard)break$/.test(children[0].type)) children.shift();
        if (!children.length) tokens[index + 1].hidden = tokens[index + 3].hidden = true;
      } else if (token.type === 'list_item_open') {
        const match = TASK_MARK.exec(inline.content);
        if (!match || !children.length || children[0].type !== 'text' || !children[0].content.startsWith(match[0])) continue;
        children[0].content = children[0].content.slice(match[0].length);
        const box = new state.Token('html_inline', '', 0);
        box.content = '<input type="checkbox" class="task-list-item-checkbox" disabled' + (match[1] === ' ' ? '' : ' checked') + '> ';
        children.unshift(box);
        token.attrJoin('class', 'task-list-item');
        for (let back = index - 1; back >= 0; back--) {
          const list = tokens[back];
          if (list.level === token.level - 1 && /^(bullet|ordered)_list_open$/.test(list.type)) {
            if (!(list.attrGet('class') || '').includes('contains-task-list')) list.attrJoin('class', 'contains-task-list');
            break;
          }
        }
      }
    }
  });
  const rules = markdown.renderer.rules;
  rules.blockquote_open = (tokens, index, options, env, self) => {
    const kind = tokens[index].meta && tokens[index].meta.alert;
    if (!kind) return self.renderToken(tokens, index, options);
    const [title, icon, path] = ALERTS[kind];
    return '<div class="markdown-alert markdown-alert-' + kind + '"><p class="markdown-alert-title"><svg class="octicon octicon-' + icon + ' mr-2" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="' + path + '"></path></svg>' + title + '</p>\\n';
  };
  rules.blockquote_close = (tokens, index, options, env, self) =>
    tokens[index].meta && tokens[index].meta.alert ? '</div>\\n' : self.renderToken(tokens, index, options);
  rules.fence = (tokens, index) => {
    const token = tokens[index];
    const text = token.content.replace(/\\n$/, '');
    const language = (token.info.trim().split(/\\s+/)[0] || '').toLowerCase().replace(/[^a-z0-9_+#.-]/g, '');
    if (!language) return '<pre class="notranslate"><code>' + markdown.utils.escapeHtml(text) + '</code></pre>\\n';
    const body = language !== 'mermaid' && window.hljs && hljs.getLanguage(language)
      ? hljs.highlight(text, { language: language, ignoreIllegals: true }).value
      : markdown.utils.escapeHtml(text);
    // The highlight-source-* wrapper is what the mermaid step below looks for.
    return '<div class="highlight highlight-source-' + language + '"><pre class="notranslate">' + body + '</pre></div>\\n';
  };
  if (rules.footnote_ref) {
    rules.footnote_caption = (tokens, index) => String(tokens[index].meta.id + 1);
    const footnoteRef = rules.footnote_ref;
    rules.footnote_ref = (...args) => footnoteRef(...args).replace('<a ', '<a data-footnote-ref aria-describedby="footnote-label" ');
    rules.footnote_block_open = () => '<section class="footnotes" data-footnotes>\\n<h2 id="footnote-label" class="sr-only">Footnotes</h2>\\n<ol>\\n';
    rules.footnote_block_close = () => '</ol>\\n</section>\\n';
  }
}

// Raw HTML in the file, and whatever GitHub sends back, is untrusted: DOMPurify drops scripts,
// handlers and javascript: URLs, and the fragment stays in its inert document until its links
// are rewritten below.
function sanitize(markup) {
  return DOMPurify.sanitize(markup, {
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: ['style', 'form', 'button', 'textarea', 'select'],
    FORBID_ATTR: ['style'],
  });
}

let markdown = null;
function renderLocal() {
  try {
    if (!markdown) {
      markdown = window.markdownit({ html: true, linkify: true });
      // Without a scheme, README.md would become a link to a Moldovan domain.
      markdown.linkify.set({ fuzzyLink: false });
      if (window.markdownitFootnote) markdown.use(window.markdownitFootnote);
      if (window.markdownitEmoji) markdown.use(window.markdownitEmoji);
      githubFlavour(markdown);
    }
    return sanitize(markdown.render(source));
  } catch (error) {
    console.error('markdown rendering failed', error);
    const pre = document.createElement('pre');
    pre.textContent = source;
    const fragment = document.createDocumentFragment();
    fragment.append(pre);
    return fragment;
  }
}

// Files are flat in the drop folder, so a relative ./img/a.png is looked up as a.png next to this file.
function local(value) {
  if (!value || outside.test(value)) return null;
  const match = value.match(/^([^?#]*)(?:\\?[^#]*)?(#.*)?$/);
  let path = match[1];
  try { path = decodeURIComponent(path); } catch (error) { /* keep it encoded */ }
  const name = path.split('/').filter(Boolean).pop();
  return name ? { name: name, hash: match[2] || '' } : null;
}

let diagramCount = 0;
// Mermaid's base theme recoloured from the page, so diagrams follow the picked theme.
function diagramColours(dark) {
  const style = getComputedStyle(article);
  const context = document.createElement('canvas').getContext('2d');
  const rgb = (name) => {
    context.fillStyle = '#808080';
    context.fillStyle = style.getPropertyValue(name).trim() || '#808080';
    const value = context.fillStyle;
    if (value[0] === '#') return [1, 3, 5].map((at) => parseInt(value.slice(at, at + 2), 16));
    return value.match(/[\\d.]+/g).slice(0, 3).map(Number);
  };
  const hex = (colour) => '#' + colour.map((part) => Math.round(part).toString(16).padStart(2, '0')).join('');
  const mix = (front, back, amount) => front.map((part, index) => part * amount + back[index] * (1 - amount));
  const back = rgb('--bgColor-muted');
  const ink = rgb('--fgColor-default');
  const muted = rgb('--fgColor-muted');
  const accent = rgb('--fgColor-accent');
  const line = rgb('--borderColor-default');
  const node = hex(mix(accent, back, dark ? 0.2 : 0.14));
  return {
    darkMode: dark,
    background: hex(back),
    mainBkg: node,
    primaryColor: node,
    primaryBorderColor: hex(mix(accent, back, 0.65)),
    primaryTextColor: hex(ink),
    secondaryColor: hex(mix(muted, back, 0.16)),
    secondaryBorderColor: hex(line),
    secondaryTextColor: hex(ink),
    tertiaryColor: hex(mix(ink, back, 0.05)),
    tertiaryBorderColor: hex(line),
    tertiaryTextColor: hex(ink),
    textColor: hex(ink),
    lineColor: hex(muted),
    clusterBkg: hex(mix(ink, back, 0.04)),
    clusterBorder: hex(line),
    edgeLabelBackground: hex(back),
    noteBkgColor: hex(mix(accent, back, 0.08)),
    noteBorderColor: hex(line),
    noteTextColor: hex(ink),
    fontFamily: style.fontFamily,
    fontSize: '15px',
    dropShadow: 'none',
    useGradient: false,
  };
}

function drawDiagrams() {
  const diagrams = [...article.querySelectorAll('.highlight-source-mermaid')];
  if (!diagrams.length) return;
  const draw = async () => {
    const dark = document.documentElement.dataset.mode === 'dark';
    let themeVariables = null;
    try { themeVariables = diagramColours(dark); } catch (error) { /* mermaid's own palette */ }
    mermaid.initialize(themeVariables
      ? { startOnLoad: false, securityLevel: 'strict', theme: 'base', themeVariables: themeVariables }
      : { startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'default' });
    for (const block of diagrams) {
      const id = 'mermaid-' + diagramCount++;
      try {
        const result = await mermaid.render(id, block.textContent);
        const holder = document.createElement('div');
        holder.className = 'mermaid-diagram';
        holder.innerHTML = result.svg;
        block.replaceWith(holder);
      } catch (error) {
        document.getElementById('d' + id)?.remove();
        block.title = 'Mermaid: ' + (error.message || error);
      }
    }
  };
  if (window.mermaid) {
    draw();
    return;
  }
  const script = document.createElement('script');
  script.src = '/vendor/mermaid.min.js';
  script.onload = draw;
  document.head.append(script);
}

const COPY_ICON = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg>';

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const done = document.execCommand('copy');
    area.remove();
    return done;
  }
}

// Each code block gets a header with its language and a copy button.
function frameCode() {
  for (const pre of article.querySelectorAll('pre')) {
    if (pre.closest('.code-block, .mermaid-diagram')) continue;
    const box = pre.closest('.highlight, .snippet-clipboard-content') || pre;
    if (box.classList.contains('highlight-source-mermaid')) continue;
    const kind = [...box.classList].map((name) => /^highlight-(?:source|text)-(.+)$/.exec(name)).find(Boolean);
    const figure = document.createElement('figure');
    figure.className = 'code-block';
    const head = document.createElement('div');
    head.className = 'code-block-head';
    const label = document.createElement('span');
    label.textContent = kind ? kind[1] : 'text';
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-label', 'Copy code');
    button.innerHTML = COPY_ICON + '<span>Copy</span>';
    let reset = 0;
    button.addEventListener('click', async () => {
      const done = await copyText(pre.textContent);
      button.classList.toggle('copied', done);
      button.lastChild.textContent = done ? 'Copied' : 'Copy failed';
      clearTimeout(reset);
      reset = setTimeout(() => {
        button.classList.remove('copied');
        button.lastChild.textContent = 'Copy';
      }, 1600);
    });
    head.append(label, button);
    box.replaceWith(figure);
    figure.append(head, box);
  }
}

// The progress line under the bar and the contents entry for the section being read.
const bar = document.querySelector('.bar.progress');
let tracked = [];
let current = null;
function track() {
  const end = document.documentElement.scrollHeight - innerHeight;
  if (bar) bar.style.setProperty('--progress', end > 0 ? Math.min(1, scrollY / end).toFixed(4) : '0');
  let found = tracked[0] || null;
  if (end > 0 && scrollY >= end - 2) found = tracked[tracked.length - 1] || null;
  else for (const item of tracked) {
    if (item.heading.getBoundingClientRect().top > 96) break;
    found = item;
  }
  if (found === current) return;
  if (current) current.link.removeAttribute('aria-current');
  current = found;
  if (!current) return;
  current.link.setAttribute('aria-current', 'location');
  if (toc && toc.scrollHeight > toc.clientHeight) {
    const top = current.link.offsetTop;
    if (top < toc.scrollTop || top > toc.scrollTop + toc.clientHeight - 40) toc.scrollTop = top - toc.clientHeight / 3;
  }
}
let tracking = false;
function scheduleTrack() {
  if (tracking) return;
  tracking = true;
  requestAnimationFrame(() => {
    tracking = false;
    track();
  });
}
addEventListener('scroll', scheduleTrack, { passive: true });
addEventListener('resize', scheduleTrack);
if (toc) {
  const wide = matchMedia('(min-width:1240px)');
  const openRail = () => { if (wide.matches) toc.open = true; };
  wide.addEventListener('change', openRail);
  openRail();
}

function show(content) {
  if (poub) {
    for (const image of content.querySelectorAll('img[src]')) {
      const found = local(image.getAttribute('src'));
      if (found) image.src = poub + encodeURIComponent(found.name);
    }
    for (const link of content.querySelectorAll('a[href]')) {
      const found = local(link.getAttribute('href'));
      if (!found) continue;
      link.href = markdownName.test(found.name)
        ? md + encodeURIComponent(found.name) + found.hash
        : poub + encodeURIComponent(found.name);
    }
  }
  article.replaceChildren(content);

  const seen = new Map();
  const entries = [];
  for (const heading of article.querySelectorAll(':is(h1, h2, h3, h4, h5, h6):not(.sr-only)')) {
    const text = heading.textContent.trim();
    let slug = text.toLowerCase().replace(/[^\\p{L}\\p{N}\\s_-]/gu, '').replace(/\\s/g, '-') || 'section';
    const used = seen.get(slug) || 0;
    seen.set(slug, used + 1);
    if (used) slug += '-' + used;
    heading.id = slug;
    const anchor = document.createElement('a');
    anchor.className = 'anchor';
    anchor.href = '#' + slug;
    anchor.textContent = '#';
    anchor.setAttribute('aria-label', 'Link to ' + text);
    heading.prepend(anchor);
    const level = Number(heading.tagName[1]);
    if (level <= 3) entries.push({ slug: slug, text: text, level: level });
  }

  if (toc) {
    const list = toc.querySelector('ol');
    list.replaceChildren();
    tracked = [];
    current = null;
    const top = Math.min(...entries.map((entry) => entry.level));
    for (const entry of entries) {
      const item = document.createElement('li');
      item.style.paddingLeft = (entry.level - top) * 14 + 'px';
      const link = document.createElement('a');
      link.href = '#' + entry.slug;
      link.textContent = entry.text;
      item.append(link);
      list.append(item);
      tracked.push({ heading: document.getElementById(entry.slug), link: link });
    }
    toc.hidden = entries.length < 3;
  }
  frameCode();
  drawDiagrams();
  scheduleTrack();
}

show(renderLocal());

if (location.hash) {
  let target = null;
  try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch (error) { /* bad hash */ }
  if (target) target.scrollIntoView();
}

// GitHub's rendering is opt-in: the text only leaves the server when this button is pressed.
const toggle = document.getElementById('renderer');
const status = document.getElementById('render-notice');
let github = null;
function pressed(on) {
  const label = on ? 'Render locally' : 'Render with GitHub';
  toggle.setAttribute('aria-pressed', String(on));
  toggle.setAttribute('aria-label', label);
  toggle.title = label;
}
if (toggle) {
  toggle.hidden = false;
  toggle.addEventListener('click', async () => {
    status.hidden = true;
    if (toggle.getAttribute('aria-pressed') === 'true') {
      show(renderLocal());
      pressed(false);
      return;
    }
    toggle.disabled = true;
    try {
      if (github === null) {
        const response = await fetch('/markdown/github', {
          method: 'POST',
          headers: { 'Content-Type': 'text/plain; charset=utf-8' },
          body: source,
        });
        const answer = await response.json();
        if (!response.ok || typeof answer.html !== 'string') throw new Error(answer.error || response.statusText);
        github = answer.html;
      }
      show(sanitize(github));
      pressed(true);
    } catch (error) {
      status.textContent = 'GitHub rendering failed: ' + (error.message || error);
      status.hidden = false;
    } finally {
      toggle.disabled = false;
    }
  });
}
})();
"""


QR_CSS = """
  .qr-dialog { width:min(100% - 32px, 360px); padding:18px; border:1px solid var(--line, var(--borderColor-default)); border-radius:20px; background:var(--panel, var(--bgColor-default)); color:var(--ink, var(--fgColor-default)); font-family:system-ui,-apple-system,sans-serif; }
  .qr-dialog::backdrop { background:color-mix(in srgb, var(--base, var(--bgColor-default)) 40%, transparent); backdrop-filter:blur(3px); }
  .qr-dialog canvas { display:block; width:100%; height:auto; border-radius:12px; image-rendering:pixelated; }
  .qr-dialog p { margin:12px 0; color:var(--muted, var(--fgColor-muted)); font-size:12px; overflow-wrap:anywhere; }
  .qr-dialog .qr-actions { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; }
  .qr-dialog .qr-actions > * { display:grid; place-items:center; min-height:40px; border:1px solid var(--edge, var(--borderColor-default)); border-radius:12px; background:var(--field, var(--bgColor-muted)); color:var(--accent, var(--fgColor-accent)); font:inherit; font-size:13px; font-weight:650; text-decoration:none; cursor:pointer; }
  .qr-dialog .qr-actions > *:focus-visible { outline:3px solid var(--accent, var(--fgColor-accent)); outline-offset:2px; }
"""

QR_JS = """
(() => {
  const nonce = document.currentScript && document.currentScript.nonce;
  const loopback = /^(localhost|127(\\.\\d+){3}|\\[::1\\])$/.test(location.hostname);
  let library;
  let dialog;

  function target(raw) {
    const url = new URL(raw || location.href, location.href);
    if (url.origin === location.origin && loopback && window.shareiPublicUrl) {
      const base = new URL(window.shareiPublicUrl);
      return base.origin + base.pathname.replace(/\\/$/, '') + url.pathname + url.search + url.hash;
    }
    return url.href;
  }

  function load() {
    if (window.qrcode) return Promise.resolve();
    library = library || new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/vendor/qrcode.js';
      if (nonce) script.nonce = nonce;
      script.onload = resolve;
      script.onerror = () => { library = null; reject(new Error('could not load the QR library')); };
      document.head.append(script);
    });
    return library;
  }

  function draw(text) {
    qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8'];
    const code = qrcode(0, 'M');
    code.addData(text);
    code.make();
    const count = code.getModuleCount(), quiet = 4;
    const scale = Math.max(4, Math.floor(320 / (count + quiet * 2)));
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = (count + quiet * 2) * scale;
    const context = canvas.getContext('2d');
    // Scanners need dark modules on a light ground whatever the theme, so these two stay fixed.
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#000';
    for (let row = 0; row < count; row++) {
      for (let column = 0; column < count; column++) {
        if (code.isDark(row, column)) context.fillRect((column + quiet) * scale, (row + quiet) * scale, scale, scale);
      }
    }
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'QR code for ' + text);
    return canvas;
  }

  function open(text) {
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.className = 'qr-dialog';
      dialog.innerHTML = '<div class="qr-code"></div><p></p><div class="qr-actions"><a target="_blank" rel="noopener noreferrer">Open</a><button type="button" data-copy>Copy</button><button type="button" data-close>Close</button></div>';
      dialog.addEventListener('click', (event) => {
        if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
      });
      dialog.querySelector('[data-copy]').addEventListener('click', async (event) => {
        try {
          await navigator.clipboard.writeText(dialog.querySelector('p').textContent);
          event.target.textContent = 'Copied';
        } catch (error) {
          event.target.textContent = 'Blocked';
        }
      });
      document.body.append(dialog);
      const previousBusy = window.liveBusy;
      window.liveBusy = () => dialog.open || (previousBusy ? previousBusy() : false);
    }
    const holder = dialog.querySelector('.qr-code');
    try {
      holder.replaceChildren(draw(text));
    } catch (error) {
      holder.replaceChildren();
      text = 'Too long for a QR code: ' + text.slice(0, 120) + '…';
    }
    dialog.querySelector('p').textContent = text;
    const link = dialog.querySelector('a');
    link.hidden = !/^https?:/i.test(text);
    link.href = link.hidden ? '#' : text;
    dialog.querySelector('[data-copy]').textContent = 'Copy';
    dialog.showModal();
  }

  window.shareiQr = (raw) => load().then(() => open(target(raw)), (error) => alert(error.message));

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-qr]');
    if (!button) return;
    event.preventDefault();
    window.shareiQr(button.dataset.qr);
  });
})();
"""


def qr_script(nonce: str = "") -> str:
    attribute = f' nonce="{nonce}"' if nonce else ""
    base = json.dumps(PUBLIC_URL).replace("</", "<\\/")
    return f"<script{attribute}>window.shareiPublicUrl = {base};{QR_JS}</script>"


def markdown_page(
    title: str,
    text: str,
    notice: str | None,
    back: tuple[str, str],
    links: list[tuple[str, str]],
    project: str | None = None,
) -> tuple[bytes, str]:
    """The reader page and the nonce its scripts run under. The browser renders the markdown."""
    nonce = secrets.token_urlsafe(16)
    bases = (
        f' data-poub="/poub/{quote(project)}/" data-md="/md/{quote(project)}/"'
        if project
        else ""
    )
    actions = "".join(
        f'<a href="{html.escape(href)}"{" download" if label == "Download" else ""}>{html.escape(label)}</a>'
        for label, href in links
    )
    banner = (
        f'<p class="notice" role="status">{html.escape(notice)}</p>' if notice else ""
    )
    # Escaped so no "</script>" in the text can close the data block early.
    source = (
        json.dumps(text)
        .replace("<", "\\u003c")
        .replace(">", "\\u003e")
        .replace("&", "\\u0026")
    )
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
<link rel="icon" href="/icon-192.png">
<link rel="stylesheet" href="/vendor/github-markdown.css">
<style>{MARKDOWN_CSS}{READER_CSS}{THEME_READER_CSS}{QR_CSS}</style></head><body>
<header class="bar progress"><a href="{html.escape(back[1])}">← {html.escape(back[0])}</a><span class="name">{html.escape(title)}</span><nav>{actions}{RENDERER_BUTTON}<button type="button" data-qr aria-label="Show a QR code for this page">QR</button></nav></header>
<main class="page reader">{banner}<p class="notice" id="render-notice" role="status" hidden></p>
<details class="toc" id="toc" hidden><summary>Contents</summary><ol></ol></details>
<article class="markdown-body"{bases}><noscript><pre>{html.escape(text)}</pre></noscript></article></main>
<script type="application/json" id="markdown-source">{source}</script>
{scripts}
<script nonce="{nonce}">{MARKDOWN_JS}</script>
{qr_script(nonce)}
</body></html>"""
    return document.encode("utf-8"), nonce


CODE_CSS = """
  .page.code-page { width:min(100%, 1280px); }
  .code { position:relative; display:grid; grid-template-columns:auto minmax(0, 1fr); border:1px solid var(--borderColor-default); border-radius:6px; background:var(--bgColor-muted); font:12px/20px ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace; overflow:hidden; }
  .gutter { padding:8px 0; border-right:1px solid var(--borderColor-default); text-align:right; user-select:none; -webkit-user-select:none; }
  .gutter a { display:block; padding:0 10px 0 14px; color:var(--fgColor-muted); text-decoration:none; }
  .gutter a:hover { color:var(--fgColor-default); }
  .gutter a:target { color:var(--fgColor-default); font-weight:600; }
  .scroll { position:relative; overflow-x:auto; }
  .code pre { position:relative; margin:0; padding:8px 14px; overflow:visible; background:none; }
  .code code { display:block; padding:0; background:none; font:inherit; white-space:pre; tab-size:4; }
  .code code.hljs { padding:0; background:none; overflow:visible; }
  .line-mark { position:absolute; left:0; right:0; height:20px; background:var(--bgColor-attention-muted); pointer-events:none; }
  .line-mark[hidden] { display:none; }
"""

CODE_JS = """
(() => {
  const code = document.getElementById('code');
  const mark = document.getElementById('line-mark');
  function markLine() {
    const match = /^#L(\\d+)$/.exec(location.hash);
    mark.hidden = !match;
    if (match) mark.style.top = (8 + (Number(match[1]) - 1) * 20) + 'px';
  }
  addEventListener('hashchange', markLine);
  markLine();
  if (!window.hljs || !('lang' in code.dataset)) return;
  const text = code.textContent, language = code.dataset.lang;
  const result = language && hljs.getLanguage(language)
    ? hljs.highlight(text, { language, ignoreIllegals: true })
    : hljs.highlightAuto(text);
  code.innerHTML = result.value;
  code.classList.add('hljs');
})();
"""


def code_page(name: str, text: str, links: list[tuple[str, str]]) -> tuple[bytes, str]:
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
<header class="bar"><a href="/drop">← Drop</a><span class="name">{html.escape(name)}</span><nav>{actions}<button type="button" data-qr aria-label="Show a QR code for this page">QR</button></nav></header>
<main class="page code-page">{notice}
<div class="code"><div class="gutter">{gutter}</div><div class="scroll"><div class="line-mark" id="line-mark" hidden></div><pre><code id="code"{language}>{html.escape(text)}</code></pre></div></div>
</main>
{f'<script nonce="{nonce}" src="/vendor/highlight.min.js"></script>' if highlight else ""}
<script nonce="{nonce}">{CODE_JS}</script>
{qr_script(nonce)}
</body></html>"""
    return document.encode("utf-8"), nonce


def code_headers(nonce: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; img-src 'self'; style-src 'self' 'unsafe-inline'; "
            f"script-src 'nonce-{nonce}'; base-uri 'none'; form-action 'none'; "
            "frame-ancestors 'self'"
        ),
    }


PLAY_CSS = """
  .page.play-page { display:grid; place-items:center; width:min(100%, 1280px); min-height:calc(100vh - 120px); }
  .play-page video { display:block; width:100%; max-height:calc(100vh - 120px); border-radius:6px; background:#000; }
  .play-page audio { display:block; width:min(100%, 640px); }
"""


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
<header class="bar"><a href="/drop">← Drop</a><span class="name">{html.escape(name)}</span><nav><a href="{url}" download>Download</a><button type="button" data-qr aria-label="Show a QR code for this page">QR</button></nav></header>
<main class="page play-page">{player}</main>
{qr_script(nonce)}
</body></html>"""
    return document.encode("utf-8"), nonce


def play_headers(nonce: str) -> dict[str, str]:
    return {
        "Cache-Control": "no-cache",
        "X-Content-Type-Options": "nosniff",
        "Content-Security-Policy": (
            "default-src 'none'; img-src 'self'; media-src 'self'; "
            f"style-src 'self' 'unsafe-inline'; script-src 'nonce-{nonce}'; "
            "base-uri 'none'; form-action 'none'; frame-ancestors 'self'"
        ),
    }


PDF_CSS = """
  .page.pdf-page { display:grid; gap:14px; justify-items:center; width:min(100%, 1000px); }
  .pdf-page canvas { display:block; width:100%; height:auto; border-radius:4px; box-shadow:0 0 0 1px var(--borderColor-default); }
  .pdf-page .pdf-status { color:var(--fgColor-muted); font-size:14px; }
"""

PDF_JS = """
import * as pdfjs from '/vendor/pdf.min.mjs';

const main = document.querySelector('.pdf-page');
const status = main.querySelector('.pdf-status');
pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdf.worker.min.mjs';

async function draw(page, canvas) {
  const ratio = window.devicePixelRatio || 1;
  const base = page.getViewport({ scale: 1 });
  const scale = Math.min(main.clientWidth / base.width, 3) * ratio;
  const viewport = page.getViewport({ scale });
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  await page.render({ canvas, viewport }).promise;
}

try {
  const pdf = await pdfjs.getDocument({ url: main.dataset.url }).promise;
  status.textContent = pdf.numPages === 1 ? '1 page' : `${pdf.numPages} pages`;
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.unobserve(entry.target);
      pdf.getPage(Number(entry.target.dataset.page)).then((page) => draw(page, entry.target));
    }
  }, { rootMargin: '600px 0px' });
  for (let number = 1; number <= pdf.numPages; number++) {
    const page = number === 1 ? await pdf.getPage(1) : null;
    const canvas = document.createElement('canvas');
    canvas.dataset.page = number;
    canvas.setAttribute('aria-label', `Page ${number}`);
    if (page) {
      const view = page.getViewport({ scale: 1 });
      canvas.width = view.width;
      canvas.height = view.height;
    } else {
      const first = main.querySelector('canvas');
      canvas.width = first.width;
      canvas.height = first.height;
    }
    main.append(canvas);
    observer.observe(canvas);
  }
} catch (error) {
  status.textContent = 'This PDF could not be shown. Download it instead.';
  console.error(error);
}
"""


def pdf_page(project: str, name: str) -> tuple[bytes, str]:
    """A dropped PDF drawn page by page with pdf.js, fetched from /poub."""
    nonce = secrets.token_urlsafe(16)
    url = html.escape(f"/poub/{quote(project)}/{quote(name)}")
    document = f"""<!doctype html>
<html lang="en" data-theme-default="{THEME_DEFAULT}"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{html.escape(name)}</title>
{theme_script(nonce)}
<link rel="icon" href="/icon-192.png">
<style>{MARKDOWN_CSS}{PDF_CSS}{THEME_READER_CSS}{QR_CSS}</style></head><body>
<header class="bar"><a href="/drop">← Drop</a><span class="name">{html.escape(name)}</span><nav><a href="{url}" download>Download</a><button type="button" data-qr aria-label="Show a QR code for this page">QR</button></nav></header>
<main class="page pdf-page" data-url="{url}"><p class="pdf-status">Loading…</p></main>
<script type="module" nonce="{nonce}">{PDF_JS}</script>
{qr_script(nonce)}
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


CLIP_CSS = """
  .clip-card { display:grid; gap:12px; padding:16px; background:var(--panel); border:1px solid var(--line); border-radius:20px; }
  .clip-meta { display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .clip-meta strong { color:var(--soft); font-weight:600; }
  .clip-ttl { display:flex; flex-wrap:wrap; align-items:center; gap:6px; color:var(--muted); font-size:12px; }
  .clip-ttl>span { margin-right:2px; }
  .clip-ttl button { padding:7px 10px; border:1px solid var(--edge); border-radius:10px; background:var(--field); color:var(--muted); font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .clip-ttl button[aria-pressed=true] { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
  .clip-ttl button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  textarea { width:100%; min-height:36vh; padding:14px; resize:vertical; border:1px solid var(--edge); border-radius:14px; background:var(--field); color:var(--ink); font:16px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }
  textarea:focus-visible { outline:3px solid var(--accent); outline-offset:1px; }
  .clip-actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .clip-actions button { min-height:52px; border:1px solid var(--edge); border-radius:14px; background:var(--field); color:var(--ink); font:inherit; font-size:15px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .clip-actions button.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
  .clip-actions button.wide, .clip-actions a.wide { grid-column:span 2; }
  .clip-actions a { display:grid; place-items:center; min-height:44px; border:1px dashed var(--edge); border-radius:14px; color:var(--accent); font-size:14px; font-weight:650; text-decoration:none; -webkit-tap-highlight-color:transparent; }
  .clip-actions a:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .clip-actions button:active { transform:scale(.985); }
  .clip-actions button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .clip-status { min-height:20px; margin:0; color:var(--muted); font-size:13px; }
  .clip-status[data-tone=ok] { color:var(--accent); }
  .clip-status[data-tone=warn] { color:var(--warn); }
  .clip-note { margin:0; color:var(--faint); font-size:12px; line-height:1.6; }
  .clip-note code { color:var(--soft); overflow-wrap:anywhere; }
  .clip-link { display:flex; align-items:center; gap:10px; padding:10px 12px; border:1px solid var(--accent-line); border-radius:14px; background:color-mix(in srgb, var(--accent) 8%, var(--field)); }
  .clip-link[hidden] { display:none; }
  .clip-link a { flex:1; min-width:0; overflow:hidden; color:var(--accent); font-size:14px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
  .clip-entry pre a { color:var(--accent); }
  .clip-history { margin-top:18px; }
  .clip-history[hidden] { display:none; }
  .clip-history ol { display:grid; gap:8px; margin:0; padding:0; list-style:none; }
  .clip-entry { display:grid; grid-template-columns:1fr auto; align-items:center; gap:4px 10px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:14px; }
  .clip-entry pre { grid-column:1/-1; margin:0; overflow:hidden; color:var(--ink); font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; overflow-wrap:anywhere; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; }
  .clip-entry small { color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }
  .clip-entry .clip-ttl { justify-content:flex-end; }
"""

CLIP_JS = r"""
const field = document.getElementById('clip-text');
const status = document.getElementById('clip-status');
const meta = document.getElementById('clip-updated');
const expiry = document.getElementById('clip-expiry');
const count = document.getElementById('clip-count');
const reload = document.getElementById('reload');
let latest = JSON.parse(document.getElementById('clip-state').textContent);
let known = latest.version;
let dirty = false;

function setStatus(message, tone) {
  status.textContent = message;
  if (tone) status.dataset.tone = tone; else delete status.dataset.tone;
}

function expiryLabel(state) {
  if (!state.updated || !state.text) return 'in memory';
  if (!state.ttl) return 'never clears';
  const left = Math.max(0, Math.round(state.updated + state.ttl - Date.now() / 1000));
  return left > 0 ? 'clears in ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0') : 'clearing…';
}

function describe(state) {
  count.textContent = state.chars + (state.chars === 1 ? ' char' : ' chars');
  meta.textContent = state.updated ? new Date(state.updated * 1000).toLocaleTimeString() + ' · ' + state.chars + ' chars' : 'Nothing shared yet';
  expiry.textContent = expiryLabel(state);
}

function markButtons() {
  for (const button of document.querySelectorAll('[data-ttl]')) {
    button.setAttribute('aria-pressed', String(Number(button.dataset.ttl) === latest.ttl));
  }
}

describe(latest);
markButtons();
if (latest.text) field.value = latest.text;

field.addEventListener('input', () => {
  dirty = true;
  describe(Object.assign({}, latest, { chars: field.value.length }));
});

setInterval(() => {
  describe(Object.assign({}, latest, { chars: dirty ? field.value.length : latest.chars }));
  for (const [index, age] of historyList.querySelectorAll('small').entries()) {
    if (latest.history[index]) age.textContent = entryAge(latest.history[index]);
  }
}, 1000);

async function call(url, body) {
  const response = await fetch(url, { method: 'POST', body: body, cache: 'no-store' });
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

const linkBar = document.getElementById('clip-link');
const URL_PATTERN = /https?:\/\/[^\s<>"']+/g;

function singleUrl(text) {
  const trimmed = text.trim();
  return /^https?:\/\/\S+$/i.test(trimmed) ? trimmed : null;
}

function linkify(text) {
  const fragment = document.createDocumentFragment();
  let last = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    const url = match[0].replace(/[.,;:!?)\]]+$/, '');
    fragment.append(text.slice(last, match.index));
    const link = document.createElement('a');
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = url;
    fragment.append(link);
    last = match.index + url.length;
  }
  fragment.append(text.slice(last));
  return fragment;
}

function showLink(state) {
  const url = singleUrl(state.text);
  linkBar.hidden = !url;
  if (!url) return;
  const link = linkBar.querySelector('a');
  link.href = url;
  link.textContent = url;
  linkBar.querySelector('[data-qr]').dataset.qr = url;
}

const historyBox = document.getElementById('clip-history');
const historyList = historyBox.querySelector('ol');

function entryAge(entry) {
  const label = new Date(entry.updated * 1000).toLocaleTimeString() + ' · ' + entry.chars + (entry.chars === 1 ? ' char' : ' chars');
  if (!entry.expires_at) return label;
  const left = Math.max(0, Math.round(entry.expires_at - Date.now() / 1000));
  return label + ' · clears in ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
}

function renderHistory(state) {
  historyBox.hidden = !state.history.length;
  historyList.replaceChildren(...state.history.map((entry) => {
    const row = document.createElement('li');
    row.className = 'clip-entry';
    const text = document.createElement('pre');
    text.append(linkify(entry.text));
    const age = document.createElement('small');
    age.textContent = entryAge(entry);
    const tools = document.createElement('span');
    tools.className = 'clip-ttl';
    const url = singleUrl(entry.text);
    if (url) {
      const qr = document.createElement('button');
      qr.type = 'button';
      qr.textContent = 'QR';
      qr.dataset.qr = url;
      tools.append(qr);
    }
    for (const [label, action] of [['Copy', 'copy'], ['Use', 'restore'], ['✕', 'delete']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.dataset.historyAction = action;
      button.dataset.id = entry.id;
      if (action === 'delete') button.setAttribute('aria-label', 'Delete this entry');
      tools.append(button);
    }
    row.append(text, age, tools);
    return row;
  }));
}

function adopt(state) {
  latest = state;
  known = state.version;
  describe(state);
  markButtons();
  renderHistory(state);
  showLink(state);
}

historyList.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-history-action]');
  if (!button) return;
  const entry = latest.history.find((item) => String(item.id) === button.dataset.id);
  if (!entry) return;
  if (button.dataset.historyAction === 'copy') {
    try {
      await navigator.clipboard.writeText(entry.text);
      setStatus('Copied to this device.', 'ok');
    } catch (error) {
      setStatus('This browser blocks clipboard writes here. Use it, then Copy.', 'warn');
    }
    return;
  }
  try {
    adopt(await call('/clip/history/' + button.dataset.historyAction + '?id=' + entry.id, ''));
    if (button.dataset.historyAction === 'restore') {
      field.value = latest.text; dirty = false; reload.hidden = true;
      setStatus('Shared with every device.', 'ok');
    }
  } catch (error) {
    setStatus('Could not update the history: ' + error.message, 'warn');
  }
});

document.getElementById('history-clear').addEventListener('click', async () => {
  if (!confirm('Forget every older clipboard entry?')) return;
  try {
    adopt(await call('/clip/history/clear', ''));
  } catch (error) {
    setStatus('Could not clear the history: ' + error.message, 'warn');
  }
});

renderHistory(latest);
showLink(latest);

document.getElementById('copy').addEventListener('click', async () => {
  const text = field.value;
  if (!text) { setStatus('Nothing to copy.', 'warn'); return; }
  try {
    await navigator.clipboard.writeText(text);
    setStatus('Copied to this device.', 'ok');
  } catch (error) {
    field.focus(); field.select();
    setStatus(document.execCommand('copy') ? 'Copied to this device.' : 'Select the text and copy it manually.', 'warn');
  }
});

document.getElementById('send').addEventListener('click', async () => {
  try {
    adopt(await call('/clip', field.value));
    dirty = false;
    reload.hidden = true;
    setStatus('Shared with every device.', 'ok');
  } catch (error) {
    setStatus('Could not share: ' + error.message, 'warn');
  }
});

document.getElementById('paste').addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    field.value = text; dirty = true;
    describe(Object.assign({}, latest, { chars: text.length }));
    setStatus('Pasted. Hit Send to share it.', 'ok');
  } catch (error) {
    field.focus();
    setStatus('This browser blocks clipboard reads. Long-press the box and choose Paste.', 'warn');
  }
});

document.getElementById('clear').addEventListener('click', async () => {
  try {
    adopt(await call('/clip/clear', ''));
    field.value = ''; dirty = false; reload.hidden = true;
    setStatus('Clipboard cleared.', 'ok');
  } catch (error) {
    setStatus('Could not clear: ' + error.message, 'warn');
  }
});

reload.addEventListener('click', () => {
  field.value = latest.text; dirty = false; reload.hidden = true;
  describe(latest);
  setStatus('Loaded the newer text.', 'ok');
});

for (const button of document.querySelectorAll('[data-ttl]')) {
  button.addEventListener('click', async () => {
    try {
      adopt(await call('/clip/ttl?seconds=' + button.dataset.ttl, ''));
      setStatus(Number(button.dataset.ttl) === 0
        ? 'This text now stays until someone clears it.'
        : 'Will clear after ' + button.textContent.trim() + '.', 'ok');
    } catch (error) {
      setStatus('Could not change the timer: ' + error.message, 'warn');
    }
  });
}

setInterval(async () => {
  try {
    const response = await fetch('/clip/state', { cache: 'no-store' });
    const state = await response.json();
    if (state.version === known) return;
    const textChanged = state.text !== latest.text;
    latest = state;
    known = state.version;
    renderHistory(state);
    showLink(state);
    if (!textChanged) {
      describe(state);
      markButtons();
      return;
    }
    if (dirty) {
      reload.hidden = false;
      setStatus('Another device shared new text. Load it or Send to overwrite.', 'warn');
      return;
    }
    field.value = state.text;
    describe(state);
    markButtons();
    setStatus('Updated from another device.', 'ok');
  } catch (error) { /* polling is best effort */ }
}, 2000);
"""


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
    <div class="clip-link" id="clip-link" hidden><a target="_blank" rel="noopener noreferrer"></a><span class="clip-ttl"><button type="button" data-qr>QR</button></span></div>
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


DROP_CSS = """
  .drop-zone { padding:10px; background:var(--panel); border:2px dashed var(--dash); border-radius:20px; transition:border-color .15s ease,background .15s ease; }
  .drop-zone.over { background:color-mix(in srgb, var(--accent) 8%, var(--panel)); border-color:var(--accent); }
  .drop-button { display:grid; place-items:center; gap:7px; width:100%; min-height:168px; padding:20px; border:0; border-radius:14px; background:transparent; color:var(--ink); font:inherit; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .drop-button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .drop-icon { color:var(--accent); font-size:34px; line-height:1; }
  .drop-button strong { font-size:17px; }
  .drop-button small { color:var(--muted); font-size:12px; text-align:center; line-height:1.5; }
  .drop-zone.compact { padding:4px; border-radius:16px; }
  .drop-zone.compact .drop-button { display:flex; justify-content:center; gap:10px; min-height:56px; padding:8px 14px; }
  .drop-zone.compact .drop-icon { font-size:22px; }
  .drop-zone.compact .drop-button strong { font-size:15px; }
  .drop-zone.compact .drop-button small { display:none; }
  .upload-queue { display:grid; gap:8px; margin:12px 0 0; padding:0; list-style:none; }
  .upload-row { display:grid; grid-template-columns:1fr auto; align-items:center; gap:6px 12px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:12px; font-size:13px; }
  .upload-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .upload-note { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .upload-bar { grid-column:1/-1; height:4px; overflow:hidden; border-radius:2px; background:var(--chip); }
  .upload-bar i { display:block; width:0; height:100%; background:var(--accent); transition:width .15s ease; }
  .upload-row[data-state=fail] .upload-note, .upload-row[data-state=fail] .upload-name { color:var(--danger); }
  .file-list { display:grid; gap:8px; margin-top:13px; }
  .file { display:flex; align-items:center; gap:12px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:14px; color:inherit; text-decoration:none; -webkit-tap-highlight-color:transparent; transition:transform .15s ease,border-color .15s ease; }
  .file:active { transform:scale(.985); border-color:var(--accent-line); }
  .file:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .file-thumb { display:grid; place-items:center; flex:0 0 46px; height:46px; overflow:hidden; border-radius:10px; background:var(--chip); color:var(--accent); font-size:20px; }
  .file-thumb img, .file-thumb video { width:100%; height:100%; object-fit:cover; }
  .file-thumb video { position:absolute; inset:0; pointer-events:none; }
  .play-mark { position:relative; display:grid; place-items:center; width:24px; height:24px; padding-left:2px; border-radius:50%; background:rgba(0,0,0,.55); color:#fff; font-size:10px; }
  .file-thumb { position:relative; }
  .file-thumb .pdf-mark { font-size:12px; font-weight:800; letter-spacing:.04em; }
  .file-thumb:has(iframe) { background:#fff; }
  .file-thumb iframe { position:absolute; left:0; top:0; width:184px; height:184px; border:0; transform:scale(.25); transform-origin:0 0; pointer-events:none; }
  .file-copy { display:grid; flex:1; gap:3px; min-width:0; }
  .file-copy strong { overflow:hidden; font-size:14px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
  .file-copy small { color:var(--muted); font-size:11px; }
  .file-action { color:var(--accent); font-size:12px; font-weight:650; }
  .project-pick { display:flex; align-items:center; gap:8px; margin:0 2px 12px; color:var(--muted); font-size:13px; }
  .project-pick select { flex:1; min-height:40px; padding:0 10px; border:1px solid var(--line); border-radius:10px; background:var(--panel); color:var(--ink); font:inherit; font-size:14px; }
  .project-pick select:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
  .drop-group + .drop-group { margin-top:14px; }
  .drop-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 4px 8px; }
  .drop-group h2 { margin:0; color:var(--soft); font-size:13px; font-weight:650; }
"""

DROP_JS = """
const input = document.getElementById('file-input');
const zone = document.getElementById('zone');
const queue = document.getElementById('queue');
const picker = document.getElementById('project');
const remembered = localStorage.getItem('sharei.project');
if (remembered && [...picker.options].some((option) => option.value === remembered)) picker.value = remembered;
picker.addEventListener('change', () => {
  if (picker.value === '__new') {
    const name = (prompt('New project name (letters, digits, . _ -)') || '').trim();
    if (/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name)) {
      if (![...picker.options].some((option) => option.value === name)) {
        picker.add(new Option(name, name), picker.options.length - 1);
      }
      picker.value = name;
    } else {
      if (name) alert('Use letters, digits, dot, dash or underscore.');
      picker.value = localStorage.getItem('sharei.project') || picker.options[0].value;
      return;
    }
  }
  localStorage.setItem('sharei.project', picker.value);
});
let pending = 0;
window.liveBusy = () => pending > 0;

function uploadOne(file) {
  const row = document.createElement('li');
  row.className = 'upload-row';
  row.innerHTML = '<span class="upload-name"></span><span class="upload-note">0%</span><span class="upload-bar"><i></i></span>';
  row.querySelector('.upload-name').textContent = file.name;
  queue.append(row);
  const bar = row.querySelector('.upload-bar i');
  const note = row.querySelector('.upload-note');
  const request = new XMLHttpRequest();
  request.open('POST', '/upload?project=' + encodeURIComponent(picker.value) + '&name=' + encodeURIComponent(file.name));
  request.upload.onprogress = (event) => {
    if (!event.lengthComputable) return;
    const percent = Math.round(event.loaded / event.total * 100);
    bar.style.width = percent + '%';
    note.textContent = percent + '%';
  };
  request.onload = () => {
    if (request.status >= 200 && request.status < 300) {
      row.dataset.state = 'ok';
      bar.style.width = '100%';
      note.textContent = 'Saved';
    } else {
      row.dataset.state = 'fail';
      note.textContent = request.status === 413 ? 'Too large' : 'Failed';
    }
  };
  request.onerror = () => {
    row.dataset.state = 'fail';
    note.textContent = 'Network error';
  };
  request.onloadend = () => {
    pending -= 1;
    if (pending === 0) setTimeout(() => location.reload(), 900);
  };
  pending += 1;
  request.send(file);
}

function handleFiles(files) {
  for (const file of files) uploadOne(file);
}

input.addEventListener('change', () => handleFiles(input.files));
zone.addEventListener('click', (event) => {
  if (event.target.closest('button')) return;
  input.click();
});
document.getElementById('pick').addEventListener('click', () => input.click());
for (const name of ['dragenter', 'dragover']) {
  zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add('over'); });
}
for (const name of ['dragleave', 'dragend']) {
  zone.addEventListener(name, () => zone.classList.remove('over'));
}
zone.addEventListener('drop', (event) => {
  event.preventDefault();
  zone.classList.remove('over');
  if (event.dataTransfer) handleFiles(event.dataTransfer.files);
});
document.addEventListener('paste', (event) => {
  if (!event.clipboardData || !event.clipboardData.files.length) return;
  event.preventDefault();
  handleFiles(event.clipboardData.files);
});

async function remove(url, question) {
  if (!confirm(question)) return;
  try {
    const response = await fetch(url, { method: 'POST' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    location.reload();
  } catch (error) {
    alert('Could not delete: ' + error.message);
  }
}

for (const button of document.querySelectorAll('.file-delete')) {
  button.addEventListener('click', () => remove('/poub/delete/' + button.dataset.url, 'Delete this file?'));
}

for (const button of document.querySelectorAll('[data-wipe-project]')) {
  const project = button.dataset.wipeProject;
  button.addEventListener('click', () => remove('/poub/delete-all?project=' + encodeURIComponent(project), `Delete ${button.dataset.count === '1' ? 'the file' : 'all ' + button.dataset.count + ' files'} in ${project}? This cannot be undone.`));
}

const wipe = document.getElementById('delete-all');
if (wipe) wipe.addEventListener('click', () => remove('/poub/delete-all', 'Delete ALL dropped files in every project? This cannot be undone.'));
"""


def drop_page(files: list[PoubFile], tab_counts: Counts) -> bytes:
    groups: dict[str, list[str]] = {}
    for entry in files:
        name = html.escape(entry["name"])
        is_html = Path(entry["name"]).suffix.lower() in HTML_SUFFIXES
        href = f"/poub/{entry['url']}"
        if entry["image"]:
            thumb = f'<img src="/poub/{entry["url"]}" alt="" loading="lazy" decoding="async">'
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
            <span class="file-tools"><button class="file-qr" type="button" data-qr="{html.escape(href)}" aria-label="QR code for {name}">▦</button>{share}{annotate}<button class="file-expiry" type="button" data-expiry data-compact data-target="poub" data-key="{entry["url"]}" data-expires="{expires}" aria-label="Expiry for {name}">⏱</button><button class="file-delete" type="button" data-url="{entry["url"]}" aria-label="Delete {name}">✕</button></span>
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
      <small>or drop them here · paste a screenshot with Ctrl/⌘+V</small>
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
                **({"expires": when} if (when := expires_at(path)) else {}),
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


ANNOTATE_JS = """
(() => {
  // marker.js 3 is linkware: the markerjs.com credit line that open() renders under the editor is the
  // attribution its licence requires while the editor is in use. Keep it visible, do not hide it with CSS.
  const SOURCES = ['/vendor/markerjs3.js', '/vendor/markerjs-ui.js'];
  const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp' };
  const previousBusy = window.liveBusy || (() => false);
  let annotating = false, loading = null;
  // Auto-reload has to stay quiet while the editor is open, or a save elsewhere reloads the page under it.
  window.liveBusy = () => annotating || previousBusy();

  function load() {
    if (!loading) {
      loading = SOURCES.reduce((chain, src) => chain.then(() => new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) return resolve();
        const script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = () => reject(new Error('could not load ' + src));
        document.head.append(script);
      })), Promise.resolve());
    }
    // A failed load must be retried on the next tap, so drop the memoised promise.
    return loading.catch((error) => { loading = null; throw error; });
  }

  // Annotations read as red everywhere. The library already defaults most tools to #ff0000, so this only
  // catches the ones that do not: text, the yellow highlighter, the black cover box, the callout outline.
  // Text on a red bubble (callout, captioned frame) stays white, red on red would be unreadable.
  const RED = '#ff0000';

  // The library defaults text to 1rem, which on a phone screenshot rasterized at natural size is too small to
  // read once the image is scaled down to fit a chat bubble. Size the label off the image instead: 4% of the
  // short side, never under 1.5rem, so a 1080px capture reads the same as a 4000px desktop grab. Units stay rem
  // because the library's size panel writes rem back.
  function readableFontSize(image) {
    const short = Math.min(image.naturalWidth, image.naturalHeight) || 0;
    const pixels = Math.max(24, Math.round(short * 0.04));
    return { value: Math.round(pixels / 16 * 10) / 10, units: 'rem', step: 0.1 };
  }

  function tint(editor, image) {
    if (!editor) return;
    const onRed = String(editor.fillColor || '').toLowerCase() === RED;
    const paint = (property, value) => {
      try { editor[property] = value; } catch (error) { /* immutable on this marker type */ }
    };
    for (const property of ['strokeColor', 'fillColor', 'highlightColor']) {
      const current = String(editor[property] || '').toLowerCase();
      if (current && current !== 'transparent') paint(property, RED);
    }
    if (!onRed && editor.color && String(editor.color).toLowerCase() !== 'transparent') paint('color', RED);
    if ('fontSize' in editor && image) paint('fontSize', readableFontSize(image));
  }

  // On a phone the library folds every tool into one "All markers" dropdown and keeps a single square icon
  // beside it. Mirror the Text tool next to that square so labelling something needs no dropdown; the rest
  // stays folded. The clone only forwards clicks to the library's own hidden button, which owns the state.
  function addTextShortcut(editor) {
    const root = editor.shadowRoot;
    const group = root?.querySelector('[aria-label="Text"].join');
    const folded = root?.querySelector('[aria-label="All markers"]');
    const button = group?.querySelector('.btn');
    if (!group || !folded || !button || !folded.parentElement) return;
    const shortcut = group.cloneNode(true);
    shortcut.querySelector('details')?.remove();
    const mirror = shortcut.querySelector('.btn');
    if (!mirror) return;
    shortcut.addEventListener('click', (event) => {
      event.preventDefault();
      button.click();
      mirror.className = button.className;
    });
    folded.parentElement.insertBefore(shortcut, folded);
  }

  function mimeOf(key) {
    const dot = key.lastIndexOf('.');
    return dot < 0 ? undefined : MIME[key.slice(dot).toLowerCase()];
  }

  function pathOf(value) {
    if (!value) return '';
    try { return new URL(value, location.href).pathname.replace(/^\\/(shot|thumb|poub)\\//, '/'); }
    catch (error) { return ''; }
  }

  // Rewrite every element still pointing at the previous pixels: the immutable ?v= URL the old image used is
  // cached forever, so new markup has to carry the new one.
  function refresh(key, url, stamps) {
    const wanted = pathOf(key);
    for (const image of document.images) {
      if (pathOf(image.getAttribute('src')) === wanted) image.src = url;
    }
    for (const link of document.querySelectorAll('a[href]')) {
      if (pathOf(link.getAttribute('href')) === wanted) link.href = url;
    }
    for (const button of document.querySelectorAll('[data-annotate]')) {
      if (pathOf(button.dataset.key) === wanted) button.dataset.url = url;
    }
    for (const script of document.querySelectorAll('script[data-kind]')) {
      if (stamps && stamps[script.dataset.kind]) script.dataset.stamp = stamps[script.dataset.kind];
    }
    document.dispatchEvent(new CustomEvent('sharei:annotated', { detail: { key: key, url: url } }));
  }

  async function save(editor, overlay, button, dataUrl) {
    const note = overlay.querySelector('.annotator-status');
    note.textContent = 'Saving…';
    try {
      const query = '?target=' + encodeURIComponent(button.dataset.target) + '&key=' + encodeURIComponent(button.dataset.key);
      const response = await fetch('/annotate' + query, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: dataUrl }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || 'HTTP ' + response.status);
      editor.remove();
      overlay.remove();
      annotating = false;
      refresh(payload.key || button.dataset.key, payload.url, payload.stamps);
    } catch (error) {
      note.textContent = 'Could not save: ' + error.message;
    }
  }

  async function annotate(button) {
    const mime = mimeOf(button.dataset.key || '');
    if (!mime || annotating) return;
    annotating = true;
    const overlay = document.createElement('div');
    overlay.className = 'annotator';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Annotate ' + (button.dataset.name || 'image'));
    overlay.innerHTML = '<div class="annotator-host"></div><p class="annotator-status" role="status"></p>';
    document.body.append(overlay);
    const close = () => { overlay.remove(); annotating = false; };
    try {
      await load();
      const image = new Image();
      image.src = button.dataset.url;
      await image.decode();
      const editor = new window.markerjsUI.AnnotationEditor();
      editor.theme = document.documentElement.dataset.mode === 'dark' ? 'dark' : 'light';
      editor.targetImage = image;
      // Natural size keeps an overwrite from downscaling the shot to whatever the phone screen showed.
      editor.settings.rendererSettings.naturalSize = true;
      editor.settings.rendererSettings.imageType = mime;
      if (mime !== 'image/png') editor.settings.rendererSettings.imageQuality = 0.92;
      editor.addEventListener('editorclose', close);
      editor.addEventListener('editorsave', (event) => save(editor, overlay, button, event.detail.dataUrl));
      overlay.querySelector('.annotator-host').append(editor);
      // The UI creates a marker the moment a tool is picked, so wrapping createMarker colours every new
      // marker before it is drawn. Doing it on markercreate instead would flash the library default first.
      const area = editor.markerArea;
      if (area) {
        const create = area.createMarker.bind(area);
        area.createMarker = (type) => {
          const created = create(type);
          tint(created, image);
          return created;
        };
        // A text marker opens its inline editor but never takes focus, so the first keystrokes go nowhere
        // until you tap the box a second time. Open it and focus it inside the same pointer gesture (mobile
        // browsers refuse a keyboard otherwise) with the placeholder preselected, so typing replaces it.
        area.addEventListener('markercreate', (event) => {
          const created = event.detail && event.detail.markerEditor;
          if (!created || typeof created.showEditor !== 'function') return;
          // markercreate fires just before the library opens the inline editor, so focus on the next
          // microtask: the textarea is attached by then and the pointer gesture is still the activation.
          Promise.resolve().then(() => {
            const field = created.textBlockEditor;
            if (!field) return;
            field.focus();
            field.textEditor?.select();
          });
        });
      }
      addTextShortcut(editor);
      editor.shadowRoot?.querySelector('button')?.focus({ preventScroll: true });
    } catch (error) {
      close();
      alert('Could not open the annotator: ' + error.message);
    }
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-annotate]');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    annotate(button);
  });
})();
"""


LIVE_JS = """
(() => {
  const script = document.currentScript;
  const kind = script.dataset.kind;
  setInterval(async () => {
    if (document.hidden || (window.liveBusy && window.liveBusy())) return;
    try {
      const response = await fetch('/state', { cache: 'no-store' });
      // Read the stamp every tick: a save updates it so the page keeps the state it already shows.
      if (response.ok && (await response.json())[kind] !== script.dataset.stamp) location.reload();
    } catch (error) {}
  }, 4000);
})();
"""


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
</main><script>{THEME_PICKER_JS}{PUSH_JS if PUSH_ENABLED else ""}</script>{qr_script()}</body></html>"""
    return document.encode("utf-8")


# Web Push. Enabled when the optional cryptography package is installed (the push extra);
# subscriptions and the VAPID key live in PUSH_DIR.
PUSH_ENABLED = False
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


SW_JS = """
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (error) { data = {}; }
  event.waitUntil(self.registration.showNotification(data.title || 'sharei', {
    body: data.body || '',
    tag: data.tag || 'sharei',
    renotify: true,
    icon: '/icon-192.png',
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL(event.notification.data.url, self.location.origin);
  if (url.origin !== self.location.origin) return;
  event.waitUntil((async () => {
    for (const client of await clients.matchAll({ type: 'window', includeUncontrolled: true })) {
      if (new URL(client.url).pathname === url.pathname && 'focus' in client) return client.focus();
    }
    return clients.openWindow(url.href);
  })());
});

self.addEventListener('pushsubscriptionchange', (event) => {
  const options = event.oldSubscription && event.oldSubscription.options;
  if (!options) return;
  event.waitUntil(self.registration.pushManager.subscribe(options).then((subscription) =>
    fetch('/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription.toJSON()),
    })));
});
"""

PUSH_JS = """
(() => {
  const item = document.querySelector('.theme-picker [data-push]');
  if (!item || !('serviceWorker' in navigator) || !('PushManager' in window) || !window.isSecureContext) return;
  item.hidden = false;
  const BLOCKED = 'Notifications blocked in the browser settings';

  function paint(on, note) {
    item.setAttribute('aria-pressed', String(on));
    item.dataset.state = note === BLOCKED ? 'blocked' : '';
    const label = note || (on ? 'Notifications on' : 'Turn on notifications');
    item.title = label;
    item.setAttribute('aria-label', label);
  }
  async function current() {
    const registration = await navigator.serviceWorker.getRegistration('/');
    return registration ? registration.pushManager.getSubscription() : null;
  }
  async function post(path, body) {
    const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
  }
  function bytes(text) {
    const raw = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - text.length % 4) % 4));
    return Uint8Array.from(raw, (char) => char.charCodeAt(0));
  }

  current().then((subscription) => paint(Boolean(subscription))).catch(() => paint(false));
  if (Notification.permission === 'denied') paint(false, BLOCKED);

  item.addEventListener('click', async () => {
    item.disabled = true;
    try {
      const existing = await current();
      if (existing) {
        await post('/push/unsubscribe', { endpoint: existing.endpoint }).catch(() => {});
        await existing.unsubscribe();
        paint(false);
        return;
      }
      if (await Notification.requestPermission() !== 'granted') {
        paint(false, BLOCKED);
        return;
      }
      const { key } = await (await fetch('/push/key')).json();
      await navigator.serviceWorker.register('/sw.js');
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(key) });
      await post('/push/subscribe', subscription.toJSON());
      paint(true);
    } catch (error) {
      console.error(error);
      paint(false, 'Could not turn notifications on');
    } finally {
      item.disabled = false;
    }
  });
})();
"""


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
            vendor_file = VENDOR / name
            if content_type is not None and vendor_file.is_file():
                self.send_file(
                    vendor_file,
                    content_type,
                    {"Cache-Control": "public, max-age=31536000, immutable"},
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
                )
                self.send_html(body, markdown_headers(nonce))
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
                body, nonce = pdf_page(path.parent.parent.name, path.name)
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
                if "raw" in parse_qs(parsed.query) and (
                    suffix in MARKDOWN_SUFFIXES or looks_like_text(path)
                ):
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
            path = shot_path(parsed.path.removeprefix("/thumb/"))
            if path is not None:
                self.send_thumbnail(path)
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

        if parsed.path == "/markdown/github":
            data = self.read_body(GITHUB_MARKDOWN_MAX_BYTES)
            if data is None:
                self.send_json(
                    {"error": "Too large for GitHub's renderer (400 KB)."}, 413
                )
                return
            rendered, error = github_markdown(data.decode("utf-8", errors="replace"))
            if rendered is None:
                self.send_json({"error": error}, 502)
            else:
                self.send_json({"html": rendered})
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
        try:
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
            }
        )

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

    def send_thumbnail(self, path: Path) -> None:
        immutable = {"Cache-Control": "public, max-age=31536000, immutable"}
        if path.suffix.lower() in VECTOR_SUFFIXES:
            # Nothing to rasterise or cache: the browser scales the vector itself.
            self.send_file(path, "image/svg+xml", vector_headers(immutable))
            return
        try:
            cached = thumbnail_cache_path(path)
            if cached.is_file():
                data = cached.read_bytes()
            else:
                data = render_thumbnail(path)
                try:
                    THUMBS.mkdir(parents=True, exist_ok=True)
                    temporary = cached.with_name(
                        f"{cached.name}.{secrets.token_hex(4)}.part"
                    )
                    temporary.write_bytes(data)
                    os.replace(temporary, cached)
                except OSError:
                    pass
        except (ImportError, OSError, ValueError) as error:
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
    "push_subject": str,
    "github_token": str,
    "github_token_pass": str,
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
        if not isinstance(value, types[key]) or isinstance(value, bool):
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
    global ARTIFACT_RULES, DEFAULT_PROJECT, ROOT, GITHUB_TOKEN, GITHUB_TOKEN_PASS
    global THEME_DEFAULT, PUBLIC_URL, PUSH_ENABLED, PUSH_SUBJECT
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
    parser.add_argument(
        "--github-token-pass",
        metavar="ENTRY",
        help="pass entry whose first line is a GitHub token for the on-demand GitHub "
        "markdown rendering, read on first use; $GITHUB_TOKEN and the config's "
        "github_token win over it",
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
    GITHUB_TOKEN = (
        os.environ.get("GITHUB_TOKEN") or str(config.get("github_token", "")) or None
    )
    GITHUB_TOKEN_PASS = str(setting("github_token_pass", "")) or None
    PUBLIC_URL = str(config.get("public_url", "")).rstrip("/")
    if PUBLIC_URL and urlparse(PUBLIC_URL).scheme not in ("http", "https"):
        raise SystemExit(
            f"sharei: public_url {PUBLIC_URL!r} must start with http(s)://"
        )
    if not PUBLIC_URL and not listens_on_loopback(host):
        address = phone_ip()
        PUBLIC_URL = f"http://{address}:{port}" if address else ""

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
