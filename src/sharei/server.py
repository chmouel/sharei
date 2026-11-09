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
from urllib.parse import parse_qs, quote, unquote, urlparse

IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".webp", ".gif"}
HTML_SUFFIXES = {".html", ".htm"}
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
PROJECT_NAME = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]{0,63}")

CLIP_MAX_BYTES = 1024 * 1024
CLIP_LOCK = threading.Lock()
CLIP_DEFAULT_TTL = 10 * 60
CLIP_MAX_TTL = 7 * 24 * 60 * 60
CLIP_TTL_CHOICES = (60, 600, 3600, 0)

EXPIRY_FILE = ".expiry.json"
EXPIRY_LOCK = threading.Lock()
EXPIRY: dict[str, float] = {}
EXPIRY_MAX = 30 * 24 * 60 * 60
EXPIRY_SWEEP_SECONDS = 60


class ClipState(TypedDict):
    text: str
    version: int
    updated: float
    ttl: int


CLIP: ClipState = {"text": "", "version": 0, "updated": 0.0, "ttl": CLIP_DEFAULT_TTL}

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
    "hljs-github.min.css": "text/css; charset=utf-8",
    "hljs-github-dark.min.css": "text/css; charset=utf-8",
    "markerjs3.js": "text/javascript; charset=utf-8",
    "markerjs-ui.js": "text/javascript; charset=utf-8",
    "github-markdown.css": "text/css; charset=utf-8",
    "mermaid.min.js": "text/javascript; charset=utf-8",
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
MARKDOWN_CACHE = cache_root() / "markdown"

# Markdown is rendered by GitHub's API so it looks exactly like on github.com. A token only raises the
# rate limit (60/h per IP without, 5000/h with); it needs no scopes.
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


EXTRA_CSS = """
  .tabs { position:sticky; top:0; z-index:5; display:flex; align-items:center; gap:2px; margin:0 -18px 14px; padding:4px 18px; overflow-x:auto; overflow-y:hidden; background:rgba(17,24,32,.92); border-bottom:1px solid rgba(43,57,64,.85); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); scrollbar-width:none; -webkit-overflow-scrolling:touch; scroll-snap-type:x proximity; }
  .tabs::-webkit-scrollbar { display:none; }
  .tab { display:inline-flex; flex:0 0 auto; align-items:center; min-height:44px; padding:0 10px; border:1px solid transparent; border-radius:9px; color:var(--muted); text-decoration:none; font-size:13.5px; font-weight:650; letter-spacing:-.01em; line-height:1; white-space:nowrap; scroll-snap-align:start; -webkit-tap-highlight-color:transparent; transition:background .15s ease,color .15s ease,border-color .15s ease; }
  .tab:hover { background:var(--panel); color:var(--ink); }
  .tab-icon { margin-right:4px; font-size:12.5px; line-height:1; opacity:.85; }
  .tab-count { margin-left:5px; padding:2px 5px; border-radius:6px; background:rgba(43,57,64,.55); color:var(--muted); font-size:11px; font-weight:600; line-height:1.1; font-variant-numeric:tabular-nums; }
  .tab[aria-current] { background:var(--mint); border-color:var(--mint); color:var(--mint-ink); }
  .tab[aria-current] .tab-icon { opacity:1; }
  .tab[aria-current] .tab-count { background:rgba(16,37,29,.14); color:var(--mint-ink); }
  .tab:focus-visible { outline:2px solid var(--mint); outline-offset:-2px; }
  .shelf-actions { display:flex; align-items:center; gap:10px; }
  .wipe { padding:6px 10px; border:1px solid #4a3a3a; border-radius:9px; background:#241c1c; color:#ffb4a8; font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .wipe:hover { border-color:#8a5a52; background:#2e2222; }
  .wipe:focus-visible { outline:2px solid #ffb4a8; outline-offset:2px; }
  .tile-wrap { position:relative; display:grid; min-width:0; }
  .tile-delete, .file-delete { position:absolute; top:5px; right:5px; display:grid; place-items:center; width:26px; height:26px; border:1px solid rgba(255,180,168,.35); border-radius:8px; background:rgba(17,24,32,.72); color:#ffb4a8; font:inherit; font-size:12px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .tile-delete:focus-visible, .file-delete:focus-visible { outline:2px solid #ffb4a8; outline-offset:1px; }
  .annotate { padding:6px 10px; border:1px solid #2f5a48; border-radius:9px; background:#162a22; color:#9fe3bf; font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .annotate:hover { border-color:#4f8f6f; background:#1b382c; }
  .annotate:focus-visible { outline:2px solid var(--mint); outline-offset:2px; }
  .annotate[hidden] { display:none; }
  .annotator { position:fixed; inset:0; z-index:20; display:flex; flex-direction:column; background:#0b1116; padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .annotator-host { flex:1; min-height:0; }
  .annotator-host mjsui-annotation-editor { display:block; width:100%; height:100%; }
  .annotator-status { margin:0; padding:2px 12px; color:#ffb4a8; font-size:11.5px; text-align:center; }
  .annotator-status:empty { display:none; }
  .annotator-credit { margin:0; padding:3px 0; color:#7f8f92; font-size:10.5px; line-height:1.4; text-align:center; }
  .annotator-credit a { color:#8fb7a4; text-decoration:underline; text-underline-offset:2px; }
  .file-row { position:relative; display:flex; }
  .file-row .file { flex:1; padding-right:80px; }
  .file-row.has-tools .file { padding-right:112px; }
  .file-tools { position:absolute; top:50%; right:10px; transform:translateY(-50%); display:flex; gap:6px; }
  .file-tools .file-delete { position:static; }
  .file-annotate, .file-expiry { display:grid; place-items:center; width:26px; height:26px; border:1px solid rgba(159,227,191,.35); border-radius:8px; background:rgba(17,24,32,.72); color:#9fe3bf; font:inherit; font-size:12px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .file-annotate:focus-visible, .file-expiry:focus-visible { outline:2px solid var(--mint); outline-offset:1px; }
  .file-expiry { border-color:rgba(255,214,140,.3); color:#c9b48a; }
  .file-expiry.set, .expiry-button.set { border-color:rgba(255,214,140,.6); color:#ffd68c; }
  .expires-left { color:#ffd68c; }
  .expires-left[hidden] { display:none; }
  .expiry-button { padding:6px 10px; border:1px solid #4a4434; border-radius:9px; background:#26231a; color:#c9b48a; font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .expiry-button:focus-visible { outline:2px solid var(--mint); outline-offset:2px; }
  .tile-expiry { position:absolute; top:5px; left:5px; padding:4px 7px; border-radius:8px; background:rgba(17,24,32,.78); color:#ffd68c; font-size:11px; font-weight:650; line-height:1; pointer-events:none; }
  .expiry-menu { position:fixed; z-index:40; display:grid; gap:8px; padding:10px 12px; border:1px solid #34434a; border-radius:12px; background:#111820; box-shadow:0 12px 32px rgba(0,0,0,.45); color:var(--muted); font-size:12px; }
  .expiry-menu[hidden] { display:none; }
  .expiry-menu div { display:flex; flex-wrap:wrap; gap:6px; }
  .expiry-menu button { padding:7px 10px; border:1px solid #34434a; border-radius:10px; background:#1d2931; color:var(--muted); font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .expiry-menu button[aria-pressed=true] { background:var(--mint); border-color:var(--mint); color:var(--mint-ink); }
  .expiry-menu button:focus-visible { outline:3px solid var(--mint); outline-offset:2px; }
  .viewer-tools { display:flex; align-items:center; gap:8px; }
  .wrap.wide { width:min(100% - 36px, 1180px); }
  .gallery { display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:12px 10px; }
  .tile { display:grid; gap:6px; min-width:0; color:var(--muted); text-decoration:none; font-size:11px; -webkit-tap-highlight-color:transparent; }
  .tile img { display:block; width:100%; aspect-ratio:9/16; object-fit:cover; object-position:top; border-radius:12px; border:1px solid #34434a; background:#1d2931; transition:transform .15s ease,border-color .15s ease; }
  .tile:hover img { border-color:#74bb99; }
  .tile:active img { transform:scale(.97); }
  .tile:focus-visible { outline:none; } .tile:focus-visible img { outline:3px solid var(--mint); outline-offset:2px; }
  .tile span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:0 2px; }
  body.viewing { overflow:hidden; }
  .viewer { position:fixed; inset:0; z-index:10; display:grid; grid-template-rows:auto minmax(0, 1fr) auto; background:rgba(8,12,16,.97); padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .viewer[hidden] { display:none; }
  .viewer-bar { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; }
  .counter { color:#bbc7c8; font-size:13px; font-variant-numeric:tabular-nums; }
  .close, .nav { display:grid; place-items:center; width:42px; height:42px; border:1px solid var(--line); border-radius:12px; background:var(--panel); color:var(--ink); font:inherit; font-size:17px; cursor:pointer; }
  .close:focus-visible, .nav:focus-visible { outline:3px solid var(--mint); outline-offset:2px; }
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
    startX = null;
    photo.style.transition = "";
    photo.style.transform = "";
    if (Math.abs(deltaX) > 50) step(deltaX < 0 ? 1 : -1);
    else if (Math.abs(deltaX) < 6 && event.type === "pointerup" && event.target === stage) close();
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
        if path.suffix.lower() in IMAGE_SUFFIXES
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
        f"{path.resolve()}:{path.stat().st_mtime_ns}:{THUMB_MAX}".encode()
    ).hexdigest()[:32]
    return THUMBS / f"{digest}.webp"


def render_thumbnail(path: Path) -> bytes:
    # Lazy import so a missing Pillow degrades to serving the original image.
    image_module = importlib.import_module("PIL.Image")
    with image_module.open(path) as image:
        image.draft("RGB", (THUMB_MAX, THUMB_MAX))
        image.thumbnail((THUMB_MAX, THUMB_MAX))
        buffer = io.BytesIO()
        image.convert("RGB").save(buffer, "WEBP", quality=72, method=4)
    return buffer.getvalue()


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


def delete_all_shots() -> int:
    deleted = 0
    for path in shot_files():
        try:
            forget_thumbnail(path)
            path.unlink()
        except OSError:
            continue
        expiry_forget(path)
        deleted += 1
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
        or path.suffix.lower() not in IMAGE_SUFFIXES
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
                image=path.suffix.lower() in IMAGE_SUFFIXES,
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
    """Reader page for a dropped file: /md for markdown, /view for other text, else None."""
    if is_markdown(path.name):
        return f"/md/{quote(project)}/{quote(path.name)}"
    if path.suffix.lower() not in IMAGE_SUFFIXES and looks_like_text(path):
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


def render_markdown(text: str) -> tuple[str, str | None]:
    """GitHub's HTML for text, or escaped source and the reason when GitHub cannot render it."""
    data = text.encode("utf-8")
    fallback = f"<pre>{html.escape(text)}</pre>"
    if len(data) > GITHUB_MARKDOWN_MAX_BYTES:
        return fallback, "Too large for GitHub's renderer (400 KB), showing the source."
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
        return (
            fallback,
            f"GitHub could not render it ({error.code} {error.reason}), showing the source.",
        )
    except (OSError, ValueError) as error:
        print(f"GitHub markdown API unreachable: {error}")
        return fallback, "GitHub is unreachable, showing the source."
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
  body { margin:0; background:#fff; color:#1f2328; font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif; }
  .bar { position:sticky; top:0; z-index:2; display:flex; align-items:center; gap:12px; padding:10px max(16px, env(safe-area-inset-left)); background:rgba(246,248,250,.92); border-bottom:1px solid #d1d9e0; backdrop-filter:blur(8px); font-size:14px; }
  .bar a { color:#0969da; text-decoration:none; font-weight:600; white-space:nowrap; }
  .bar a:hover { text-decoration:underline; }
  .bar .name { flex:1; min-width:0; overflow:hidden; color:#59636e; text-overflow:ellipsis; white-space:nowrap; }
  .bar nav { display:flex; gap:14px; }
  .page { width:min(100%, 980px); margin:0 auto; padding:24px 16px 64px; }
  .notice { margin:0 0 16px; padding:10px 14px; border:1px solid #d4a72c66; border-radius:6px; background:#fff8c5; color:#3b2300; font-size:14px; }
  .toc { margin:0 0 20px; padding:8px 14px; border:1px solid #d1d9e0; border-radius:6px; font-size:14px; }
  .toc summary { cursor:pointer; font-weight:600; padding:4px 0; }
  .toc ol { margin:6px 0 6px; padding:0; list-style:none; }
  .toc li { padding:3px 0; }
  .toc a { color:#0969da; text-decoration:none; }
  .toc a:hover { text-decoration:underline; }
  .markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5, .markdown-body h6 { position:relative; }
  .markdown-body .anchor { position:absolute; left:-1.1em; padding-right:.3em; color:#59636e; text-decoration:none; opacity:0; }
  .markdown-body :is(h1,h2,h3,h4,h5,h6):hover .anchor, .markdown-body .anchor:focus { opacity:1; }
  .mermaid-diagram { margin:0 0 16px; overflow-x:auto; text-align:center; }
  .mermaid-diagram svg { max-width:100%; height:auto; }
  @media (min-width:768px) { .page { padding:32px 32px 80px; } }
  @media (prefers-color-scheme:dark) {
    body { background:#0d1117; color:#f0f6fc; }
    .bar { background:rgba(1,4,9,.88); border-color:#3d444d; }
    .bar a, .toc a { color:#4493f8; }
    .bar .name, .markdown-body .anchor { color:#9198a1; }
    .toc { border-color:#3d444d; }
    .notice { background:#bb800926; border-color:#bb800966; color:#f0f6fc; }
  }
"""

MARKDOWN_JS = """
(() => {
const article = document.querySelector('article.markdown-body');
const poub = article.dataset.poub || '';
const md = article.dataset.md || '';
const outside = /^(?:[a-z][a-z0-9+.-]*:|#|\\/)/i;
const markdownName = /\\.(?:md|markdown)$/i;

// Files are flat in the drop folder, so a relative ./img/a.png is looked up as a.png next to this file.
function local(value) {
  if (!value || outside.test(value)) return null;
  const match = value.match(/^([^?#]*)(?:\\?[^#]*)?(#.*)?$/);
  let path = match[1];
  try { path = decodeURIComponent(path); } catch (error) { /* keep it encoded */ }
  const name = path.split('/').filter(Boolean).pop();
  return name ? { name: name, hash: match[2] || '' } : null;
}

if (poub) {
  for (const image of article.querySelectorAll('img[src]')) {
    const found = local(image.getAttribute('src'));
    if (found) image.src = poub + encodeURIComponent(found.name);
  }
  for (const link of article.querySelectorAll('a[href]')) {
    const found = local(link.getAttribute('href'));
    if (!found) continue;
    link.href = markdownName.test(found.name)
      ? md + encodeURIComponent(found.name) + found.hash
      : poub + encodeURIComponent(found.name);
  }
}

const seen = new Map();
const entries = [];
for (const heading of article.querySelectorAll('h1, h2, h3, h4, h5, h6')) {
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

const toc = document.getElementById('toc');
if (toc && entries.length >= 3) {
  const top = Math.min(...entries.map((entry) => entry.level));
  const list = toc.querySelector('ol');
  for (const entry of entries) {
    const item = document.createElement('li');
    item.style.paddingLeft = (entry.level - top) * 16 + 'px';
    const link = document.createElement('a');
    link.href = '#' + entry.slug;
    link.textContent = entry.text;
    item.append(link);
    list.append(item);
  }
  toc.hidden = false;
}

if (location.hash) {
  let target = null;
  try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch (error) { /* bad hash */ }
  if (target) target.scrollIntoView();
}

const diagrams = [...article.querySelectorAll('.highlight-source-mermaid')];
if (diagrams.length) {
  const script = document.createElement('script');
  script.src = '/vendor/mermaid.min.js';
  script.onload = async () => {
    const dark = matchMedia('(prefers-color-scheme: dark)').matches;
    mermaid.initialize({ startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'default' });
    for (const [index, block] of diagrams.entries()) {
      const id = 'mermaid-' + index;
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
  document.head.append(script);
}
})();
"""


def markdown_page(
    title: str,
    rendered: str,
    notice: str | None,
    back: tuple[str, str],
    links: list[tuple[str, str]],
    project: str | None = None,
) -> tuple[bytes, str]:
    """The reader page and the nonce its inline script runs under."""
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
    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{html.escape(title)}</title>
<link rel="icon" href="/icon-192.png">
<link rel="stylesheet" href="/vendor/github-markdown.css">
<style>{MARKDOWN_CSS}</style></head><body>
<header class="bar"><a href="{html.escape(back[1])}">← {html.escape(back[0])}</a><span class="name">{html.escape(title)}</span><nav>{actions}</nav></header>
<main class="page">{banner}
<details class="toc" id="toc" hidden><summary>Contents</summary><ol></ol></details>
<article class="markdown-body"{bases}>
{rendered}
</article></main>
<script nonce="{nonce}">{MARKDOWN_JS}</script>
</body></html>"""
    return document.encode("utf-8"), nonce


CODE_CSS = """
  .page.code-page { width:min(100%, 1280px); }
  .code { position:relative; display:grid; grid-template-columns:auto minmax(0, 1fr); border:1px solid #d1d9e0; border-radius:6px; background:#f6f8fa; font:12px/20px ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace; overflow:hidden; }
  .gutter { padding:8px 0; border-right:1px solid #d1d9e0; text-align:right; user-select:none; -webkit-user-select:none; }
  .gutter a { display:block; padding:0 10px 0 14px; color:#8c959f; text-decoration:none; }
  .gutter a:hover { color:#1f2328; }
  .gutter a:target { color:#1f2328; font-weight:600; }
  .scroll { position:relative; overflow-x:auto; }
  .code pre { position:relative; margin:0; padding:8px 14px; overflow:visible; background:none; }
  .code code { display:block; padding:0; background:none; font:inherit; white-space:pre; tab-size:4; }
  .code code.hljs { padding:0; background:none; overflow:visible; }
  .line-mark { position:absolute; left:0; right:0; height:20px; background:#fff8c5; pointer-events:none; }
  .line-mark[hidden] { display:none; }
  @media (prefers-color-scheme:dark) {
    .code { background:#151b23; border-color:#3d444d; }
    .gutter { border-color:#3d444d; }
    .gutter a { color:#656c76; }
    .gutter a:hover, .gutter a:target { color:#f0f6fc; }
    .line-mark { background:#bb800926; }
  }
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
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{html.escape(name)}</title>
<link rel="icon" href="/icon-192.png">
<link rel="stylesheet" href="/vendor/hljs-github.min.css" media="(prefers-color-scheme: light)">
<link rel="stylesheet" href="/vendor/hljs-github-dark.min.css" media="(prefers-color-scheme: dark)">
<style>{MARKDOWN_CSS}{CODE_CSS}</style></head><body>
<header class="bar"><a href="/drop">← Drop</a><span class="name">{html.escape(name)}</span><nav>{actions}</nav></header>
<main class="page code-page">{notice}
<div class="code"><div class="gutter">{gutter}</div><div class="scroll"><div class="line-mark" id="line-mark" hidden></div><pre><code id="code"{language}>{html.escape(text)}</code></pre></div></div>
</main>
{f'<script nonce="{nonce}" src="/vendor/highlight.min.js"></script>' if highlight else ""}
<script nonce="{nonce}">{CODE_JS}</script>
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
    except FileNotFoundError:
        return
    except (OSError, ValueError, TypeError, KeyError) as error:
        print(f"ignoring saved clipboard {CLIP_FILE}: {error}")
        return
    with CLIP_LOCK:
        CLIP.update(text=text, version=version, updated=updated, ttl=ttl)
        clip_expire_locked()


def clip_state_locked() -> ClipState:
    return ClipState(
        text=CLIP["text"],
        version=CLIP["version"],
        updated=CLIP["updated"],
        ttl=CLIP["ttl"],
    )


def clip_expire_locked() -> None:
    if CLIP["text"] and CLIP["ttl"] and CLIP["updated"] + CLIP["ttl"] <= time.time():
        CLIP["text"] = ""
        CLIP["version"] += 1
        CLIP["updated"] = 0.0
        clip_save_locked()


def clip_snapshot() -> ClipState:
    with CLIP_LOCK:
        clip_expire_locked()
        return clip_state_locked()


def clip_store(text: str) -> ClipState:
    with CLIP_LOCK:
        CLIP["text"] = text
        CLIP["version"] += 1
        CLIP["updated"] = time.time() if text else 0.0
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


CLIP_CSS = """
  .clip-card { display:grid; gap:12px; padding:16px; background:var(--panel); border:1px solid var(--line); border-radius:20px; }
  .clip-meta { display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .clip-meta strong { color:#bbc7c8; font-weight:600; }
  .clip-ttl { display:flex; flex-wrap:wrap; align-items:center; gap:6px; color:var(--muted); font-size:12px; }
  .clip-ttl>span { margin-right:2px; }
  .clip-ttl button { padding:7px 10px; border:1px solid #34434a; border-radius:10px; background:#1d2931; color:var(--muted); font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .clip-ttl button[aria-pressed=true] { background:var(--mint); border-color:var(--mint); color:var(--mint-ink); }
  .clip-ttl button:focus-visible { outline:3px solid var(--mint); outline-offset:2px; }
  textarea { width:100%; min-height:36vh; padding:14px; resize:vertical; border:1px solid #34434a; border-radius:14px; background:#1d2931; color:var(--ink); font:16px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }
  textarea:focus-visible { outline:3px solid var(--mint); outline-offset:1px; }
  .clip-actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .clip-actions button { min-height:52px; border:1px solid #34434a; border-radius:14px; background:#1d2931; color:var(--ink); font:inherit; font-size:15px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .clip-actions button.primary { background:var(--mint); border-color:var(--mint); color:var(--mint-ink); }
  .clip-actions button.wide, .clip-actions a.wide { grid-column:span 2; }
  .clip-actions a { display:grid; place-items:center; min-height:44px; border:1px dashed #34434a; border-radius:14px; color:var(--mint); font-size:14px; font-weight:650; text-decoration:none; -webkit-tap-highlight-color:transparent; }
  .clip-actions a:focus-visible { outline:3px solid var(--mint); outline-offset:2px; }
  .clip-actions button:active { transform:scale(.985); }
  .clip-actions button:focus-visible { outline:3px solid var(--mint); outline-offset:2px; }
  .clip-status { min-height:20px; margin:0; color:var(--muted); font-size:13px; }
  .clip-status[data-tone=ok] { color:var(--mint); }
  .clip-status[data-tone=warn] { color:#ffd08a; }
  .clip-note { margin:0; color:#849399; font-size:12px; line-height:1.6; }
  .clip-note code { color:#bbc7c8; overflow-wrap:anywhere; }
"""

CLIP_JS = """
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
}, 1000);

async function call(url, body) {
  const response = await fetch(url, { method: 'POST', body: body, cache: 'no-store' });
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

function adopt(state) {
  latest = state;
  known = state.version;
  describe(state);
  markButtons();
}

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
    setStatus('This browser blocks clipboard reads — long-press the box and choose Paste.', 'warn');
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
    payload = json.dumps(
        {
            "text": text,
            "version": state["version"],
            "updated": updated,
            "chars": characters,
            "ttl": state["ttl"],
            "expires_at": updated + state["ttl"] if updated and state["ttl"] else 0,
        }
    ).replace("</", "<\\/")
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
  <header><div class="brand"><span class="brand-mark" aria-hidden="true">⎘</span> Clipboard</div>
    <h1>Last copy,<br>every device.</h1><p class="intro">Text lives in this process only. It clears itself after a while — pick Never to keep it until you clear it.</p></header>
  <div class="shelf-label"><span>Shared clipboard</span><span class="count" id="clip-count">{characters} {"char" if characters == 1 else "chars"}</span></div>
  <section class="clip-card">
    <div class="clip-meta"><span id="clip-updated">{updated_label}</span><span id="clip-expiry">{expiry_label}</span></div>
    <div class="clip-ttl"><span>Clear after</span>{choices}</div>
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
    <p class="clip-note">From a terminal: <code>curl -H 'Content-Type: text/plain' --data-binary 'some text' http://HOST:PORT/clip</code> to send, <code>curl http://HOST:PORT/clip/raw</code> to read.</p>
  </section>
  <script id="clip-state" type="application/json">{payload}</script>
  <script>{CLIP_JS}</script>"""
    return layout("Clipboard", "clip", tab_counts, body, extra_css=CLIP_CSS)


DROP_CSS = """
  .drop-zone { padding:10px; background:var(--panel); border:2px dashed #405057; border-radius:20px; transition:border-color .15s ease,background .15s ease; }
  .drop-zone.over { background:#1d2f2a; border-color:var(--mint); }
  .drop-button { display:grid; place-items:center; gap:7px; width:100%; min-height:168px; padding:20px; border:0; border-radius:14px; background:transparent; color:var(--ink); font:inherit; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .drop-button:focus-visible { outline:3px solid var(--mint); outline-offset:2px; }
  .drop-icon { color:var(--mint); font-size:34px; line-height:1; }
  .drop-button strong { font-size:17px; }
  .drop-button small { color:var(--muted); font-size:12px; text-align:center; line-height:1.5; }
  .upload-queue { display:grid; gap:8px; margin:12px 0 0; padding:0; list-style:none; }
  .upload-row { display:grid; grid-template-columns:1fr auto; align-items:center; gap:6px 12px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:12px; font-size:13px; }
  .upload-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .upload-note { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .upload-bar { grid-column:1/-1; height:4px; overflow:hidden; border-radius:2px; background:#26333a; }
  .upload-bar i { display:block; width:0; height:100%; background:var(--mint); transition:width .15s ease; }
  .upload-row[data-state=fail] .upload-note, .upload-row[data-state=fail] .upload-name { color:#ff9b8a; }
  .file-list { display:grid; gap:8px; margin-top:13px; }
  .file { display:flex; align-items:center; gap:12px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:14px; color:inherit; text-decoration:none; -webkit-tap-highlight-color:transparent; transition:transform .15s ease,border-color .15s ease; }
  .file:active { transform:scale(.985); border-color:#74bb99; }
  .file:focus-visible { outline:3px solid var(--mint); outline-offset:2px; }
  .file-thumb { display:grid; place-items:center; flex:0 0 46px; height:46px; overflow:hidden; border-radius:10px; background:#26333a; color:var(--mint); font-size:20px; }
  .file-thumb img { width:100%; height:100%; object-fit:cover; }
  .file-thumb { position:relative; background:#fff; }
  .file-thumb iframe { position:absolute; left:0; top:0; width:184px; height:184px; border:0; transform:scale(.25); transform-origin:0 0; pointer-events:none; }
  .file-copy { display:grid; flex:1; gap:3px; min-width:0; }
  .file-copy strong { overflow:hidden; font-size:14px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
  .file-copy small { color:var(--muted); font-size:11px; }
  .file-action { color:var(--mint); font-size:12px; font-weight:650; }
  .project-pick { display:flex; align-items:center; gap:8px; margin:0 2px 12px; color:var(--muted); font-size:13px; }
  .project-pick select { flex:1; min-height:40px; padding:0 10px; border:1px solid var(--line); border-radius:10px; background:var(--panel); color:var(--ink); font:inherit; font-size:14px; }
  .project-pick select:focus-visible { outline:2px solid var(--mint); outline-offset:1px; }
  .drop-group + .drop-group { margin-top:14px; }
  .drop-group h2 { margin:0 4px 8px; color:#bbc7c8; font-size:13px; font-weight:650; }
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
        if Path(entry["name"]).suffix.lower() in ANNOTATE_TYPES:
            annotate = (
                f'<button class="file-annotate" type="button" data-annotate data-target="drop" '
                f'data-key="{entry["url"]}" data-url="/poub/{entry["url"]}" '
                f'aria-label="Annotate {name}">✎</button>'
            )
        expires = f"{entry['expires']:.0f}" if entry["expires"] else ""
        groups.setdefault(entry["project"], []).append(f"""
          <div class="file-row{" has-tools" if annotate else ""}">
            <a class="file" href="{href}"{download}>
              <span class="file-thumb">{thumb}</span>
              <span class="file-copy"><strong>{name}</strong><small>{entry["size"]} <i>·</i> {entry["date"]}<span class="expires-left" data-expires-left="{expires}" data-prefix=" · expires in " hidden></span></small></span>
              <span class="file-action">{action}</span>
            </a>
            <span class="file-tools">{annotate}<button class="file-expiry" type="button" data-expiry data-compact data-target="poub" data-key="{entry["url"]}" data-expires="{expires}" aria-label="Expiry for {name}">⏱</button><button class="file-delete" type="button" data-url="{entry["url"]}" aria-label="Delete {name}">✕</button></span>
          </div>""")
    wipe = (
        '<button class="wipe" id="delete-all" type="button">Delete all</button>'
        if groups
        else ""
    )
    listing = (
        "".join(
            f'<section class="drop-group"><h2>{html.escape(project)} <span class="checkout">{len(rows)}</span></h2>'
            f'<div class="file-list">{"".join(rows)}</div></section>'
            for project, rows in groups.items()
        )
        or '<div class="empty"><span>▤</span><h2>Nothing dropped yet</h2><p>Files you send land here for every device.</p></div>'
    )
    options = "".join(
        f'<option value="{html.escape(name)}">{html.escape(name)}</option>'
        for name in known_projects()
    )
    root = html.escape(pretty_path(ROOT))
    body = f"""
  <header><div class="brand"><span class="brand-mark" aria-hidden="true">⇪</span> Drop</div>
    <h1>Drop a file.<br>Grab it anywhere.</h1><p class="intro">Files land in {root}/&lt;project&gt;/drop on this machine; the Share menu uses {html.escape(DEFAULT_PROJECT)}.</p></header>
  <div class="shelf-label"><span>Shared files</span><span class="shelf-actions"><span class="count">{len(files)} {"file" if len(files) == 1 else "files"}</span>{wipe}</span></div>
  <label class="project-pick">Save to <select id="project">{options}<option value="__new">New project…</option></select></label>
  <section class="drop-zone" id="zone">
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
  <header><div class="brand"><span class="brand-mark" aria-hidden="true">↓</span> Artifacts</div>
    <h1>Fresh builds.<br>One tap away.</h1><p class="intro">Files your projects built on this machine, ready to grab on your phone.</p></header>
  <div class="shelf-label"><span>Latest first</span><span class="count">{len(artifacts)} {"file" if len(artifacts) == 1 else "files"}</span></div>
  {"".join(sections)}{empty}
  <footer>Android may ask you to allow installs from your browser the first time you open an APK.</footer>"""
    return layout("Artifacts", "artifacts", tab_counts, body)


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
            <div class="section-heading"><h2>{html.escape(project)}</h2><span class="checkout">{len(items)}</span></div>
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
  <header><div class="brand"><span class="brand-mark" aria-hidden="true">▣</span> Screenshots</div>
    <h1>Every capture,<br>newest first.</h1><p class="intro">Everything under {html.escape(pretty_path(ROOT))}/*/shots. Tap one to flip through them.</p></header>
  <div class="shelf-label"><span>Your gallery</span><span class="shelf-actions"><span class="count">{len(shots)} {"shot" if len(shots) == 1 else "shots"}</span>{wipe}</span></div>
  {"".join(sections)}{empty}
  <div class="viewer" id="viewer" hidden role="dialog" aria-modal="true" aria-label="Screenshot viewer">
    <div class="viewer-bar"><span class="counter" id="counter"></span>
      <span class="viewer-tools"><button class="annotate" id="annotate-shot" type="button" data-annotate
        data-target="shots" hidden>Annotate</button>
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
                "image": path.suffix.lower() in IMAGE_SUFFIXES,
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
      editor.theme = matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light';
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
            f'{label}<span class="tab-count">{count}</span></a>'
        )

    navigation = "".join(
        (
            tab("artifacts", "/", "Artifacts", tab_counts["artifacts"], "↓"),
            tab("shots", "/shots", "Screenshots", tab_counts["shots"], "▣"),
            tab("clip", "/clip", "Clipboard", tab_counts["clip"], "⎘"),
            tab("drop", "/drop", "Drop", tab_counts["drop"], "⇪"),
        )
    )

    document = f"""<!doctype html>
<html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="theme-color" content="#111820"><title>{title}</title>
<link rel="manifest" href="/manifest.webmanifest" crossorigin="use-credentials">
<link rel="icon" href="/icon-192.png">
<style>
  :root {{ color-scheme: dark; --ink:#eff5f3; --muted:#9aa9ad; --base:#111820; --panel:#19232b; --line:#2b3940; --mint:#a5f2d1; --mint-ink:#10251d; }}
  * {{ box-sizing:border-box }}
  body {{ margin:0; background:var(--base); color:var(--ink); font-family:ui-rounded,"SF Pro Rounded",system-ui,-apple-system,sans-serif; -webkit-font-smoothing:antialiased; }}
  .wrap {{ width:min(100% - 36px, 620px); margin:0 auto; padding:32px 0 max(42px, env(safe-area-inset-bottom)); }}
  header {{ padding:16px 2px 30px; }}
  .brand {{ display:flex; align-items:center; gap:11px; color:var(--mint); font-weight:700; font-size:14px; letter-spacing:.01em; }}
  .brand-mark {{ display:grid; place-items:center; width:32px; height:32px; border:1px solid #5c9d80; border-radius:11px 11px 11px 4px; font-size:18px; }}
  h1 {{ font-size:clamp(36px, 10vw, 52px); letter-spacing:-.055em; line-height:1.02; margin:25px 0 10px; font-weight:730; }}
  .intro {{ color:var(--muted); margin:0; font-size:16px; line-height:1.55; max-width:390px; }}
  .shelf-label {{ display:flex; align-items:center; justify-content:space-between; margin:9px 2px 12px; color:#bbc7c8; font-size:13px; }}
  .count {{ color:var(--muted); font-variant-numeric:tabular-nums; }}
  .app-section {{ background:var(--panel); border:1px solid var(--line); border-radius:20px; padding:17px 14px 14px; margin-bottom:13px; }}
  .section-heading {{ display:flex; align-items:center; justify-content:space-between; gap:12px; padding:0 3px 12px; }}
  h2 {{ margin:0; font-size:18px; letter-spacing:-.025em; }}
  .checkout {{ color:#b8c4c5; background:#26333a; border-radius:20px; padding:5px 9px; font-size:11px; max-width:58%; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .downloads {{ display:grid; gap:8px; }}
  .download {{ display:flex; align-items:center; gap:12px; min-height:72px; padding:11px 12px; border:1px solid #34434a; border-radius:14px; color:inherit; text-decoration:none; background:#1d2931; -webkit-tap-highlight-color:transparent; transition:background .15s ease,border-color .15s ease,transform .15s ease; }}
  .download:active {{ transform:scale(.985); background:#273a3a; border-color:#74bb99; }}
  .download:focus-visible {{ outline:3px solid var(--mint); outline-offset:2px; }}
  .button-icon {{ display:grid; place-items:center; flex:0 0 40px; height:40px; border-radius:12px; background:var(--mint); color:var(--mint-ink); font-size:23px; font-weight:700; }}
  .button-copy {{ min-width:0; flex:1; display:grid; gap:4px; }}
  .button-copy strong {{ font-size:15px; font-weight:650; }}
  .button-copy small {{ display:flex; align-items:baseline; min-width:0; color:var(--muted); font-size:11px; }}
  .button-copy .apk-path {{ flex:1 1 auto; min-width:0; overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }}
  .button-copy .apk-meta {{ flex:0 0 auto; white-space:nowrap; }}
  .button-copy i {{ font-style:normal; padding:0 3px; flex:0 0 auto; }}
  .button-action {{ color:var(--mint); font-size:13px; font-weight:650; padding:0 1px; }}
  .empty {{ text-align:center; padding:56px 20px; background:var(--panel); border:1px dashed #405057; border-radius:20px; }}
  .empty>span {{ color:var(--mint); font-size:30px; }} .empty h2 {{ margin:10px 0 7px; }} .empty p {{ margin:0; color:var(--muted); font-size:14px; }}
  footer {{ color:#849399; font-size:12px; line-height:1.5; padding:14px 3px; }}
  @media (min-width:600px) {{ .wrap {{ padding-top:56px }} .app-section {{ padding:19px }} }}
  @media (prefers-reduced-motion:reduce) {{ *,*::before,*::after {{ transition:none!important; scroll-behavior:auto!important }} }}
{EXTRA_CSS}
{extra_css}
</style></head><body><main class="wrap{" wide" if wide else ""}">
  <nav class="tabs" aria-label="Sections">{navigation}</nav>
  {body}
</main></body></html>"""
    return document.encode("utf-8")


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
                rendered, notice = render_markdown(text)
                body, nonce = markdown_page(
                    path.name,
                    rendered,
                    notice,
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

        if parsed.path == "/clip/md":
            text = clip_snapshot()["text"]
            rendered, notice = render_markdown(text) if text else ("", None)
            if not text:
                notice = "The clipboard is empty."
            body, nonce = markdown_page(
                "Clipboard",
                rendered,
                notice,
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
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream"
                )
                if "raw" in parse_qs(parsed.query) and (
                    suffix in MARKDOWN_SUFFIXES or looks_like_text(path)
                ):
                    content_type = "text/plain; charset=utf-8"
                elif suffix in HTML_SUFFIXES:
                    # Render in the browser, but in an opaque origin so the page
                    # cannot reach the sharei API or its storage.
                    headers["Content-Security-Policy"] = (
                        "sandbox allow-scripts allow-forms"
                    )
                elif suffix not in IMAGE_SUFFIXES:
                    headers["Content-Disposition"] = (
                        f"attachment; filename*=UTF-8''{quote(path.name)}"
                    )
                self.send_file(path, content_type, headers)
                return

        if parsed.path == "/clip/state":
            self.send_json(self.clip_payload(clip_snapshot()))
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
            body = clip_snapshot()["text"].encode("utf-8")
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
                self.send_file(
                    path,
                    mimetypes.guess_type(path.name)[0] or "application/octet-stream",
                    {"Cache-Control": "public, max-age=31536000, immutable"},
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
            self.send_json({"deleted": delete_all_shots()})
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

        if parsed.path == "/expiry":
            self.handle_expiry(parse_qs(parsed.query))
            return

        if parsed.path == "/annotate":
            self.handle_annotate()
            return

        if parsed.path == "/share":
            self.handle_share()
            return

        if parsed.path == "/clip/clear":
            self.send_json(self.clip_payload(clip_store("")))
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
            self.send_json(self.clip_payload(clip_set_ttl(seconds)))
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
        self.send_json(self.clip_payload(clip_store(text)))

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

        try:
            path = publish_poub(temporary, name)
        except OSError as error:
            temporary.unlink(missing_ok=True)
            self.send_json({"error": str(error)}, status=500)
            return

        self.send_json(
            {
                "project": project,
                "name": path.name,
                "size": length,
                "url": f"/poub/{quote(project)}/{quote(path.name)}",
                **({"view": view} if (view := view_url(project, path)) else {}),
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
        if shared or (not saved and fields.get("title")):
            clip_store(shared or fields["title"])

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
                publish_poub(temporary, safe)
            except OSError as error:
                if temporary is not None:
                    temporary.unlink(missing_ok=True)
                self.send_error(500, f"Could not save shared file: {error}")
                return None
            saved += 1
        return saved

    def clip_payload(self, state: ClipState) -> dict[str, object]:
        return {
            "text": state["text"],
            "version": state["version"],
            "updated": state["updated"],
            "chars": len(state["text"]),
            "ttl": state["ttl"],
            "expires_at": state["updated"] + state["ttl"]
            if state["updated"] and state["ttl"]
            else 0,
        }

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

    def send_json(self, payload: dict[str, object], status: int = 200) -> None:
        body = json.dumps(payload).encode("utf-8")
        self.send_response(status)
        self.send_header("Content-Type", "application/json; charset=utf-8")
        self.send_header("Content-Length", str(len(body)))
        self.send_header("Cache-Control", "no-store")
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
        self.send_response(200)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(path.stat().st_size))
        for name, value in headers.items():
            self.send_header(name, value)
        self.end_headers()
        with path.open("rb") as stream:
            while chunk := stream.read(128 * 1024):
                self.wfile.write(chunk)

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


CONFIG_TYPES: dict[str, type | tuple[type, ...]] = {
    "host": str,
    "port": int,
    "root": str,
    "default_project": str,
    "clip_ttl": int,
    "allow_hosts": list,
    "allow_origins": list,
    "artifacts": list,
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
        help="pass entry whose first line is a GitHub token for markdown rendering, read on "
        "first use; $GITHUB_TOKEN and the config's github_token win over it",
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
    ARTIFACT_RULES = parse_artifacts(str(path), config.get("artifacts", []))  # type: ignore[arg-type]
    clip_ttl = setting("clip_ttl", None)
    GITHUB_TOKEN = (
        os.environ.get("GITHUB_TOKEN") or str(config.get("github_token", "")) or None
    )
    GITHUB_TOKEN_PASS = str(setting("github_token_pass", "")) or None

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
    server = ThreadingHTTPServer((host, port), Handler)
    print(f"Config: {path if config else 'built-in defaults'}; files under {ROOT}")
    print(
        f"Open http://localhost:{port}  (screenshots: /shots, clipboard: /clip, drop: /drop)"
    )
    address = phone_ip()
    if host == "0.0.0.0" and address:
        print(f"On your phone: http://{address}:{port}")
    print("Press Ctrl+C to stop.")
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\nStopped.")
    finally:
        server.server_close()


if __name__ == "__main__":
    main()
