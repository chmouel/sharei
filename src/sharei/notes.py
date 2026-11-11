"""Read-only access to chosen folders of an Obsidian vault.

Nothing here writes to the vault. A request path is never joined onto the vault: it is
looked up in the last scan, which only holds regular, non-hidden, non-symlinked files.
"""

import json
import os
import posixpath
import re
import threading
import time
import unicodedata
from collections.abc import Callable
from pathlib import Path
from typing import NamedTuple
from urllib.parse import quote, unquote

MAX_FILES = 20_000
# Notes larger than this are neither scanned for links nor rendered.
MAX_NOTE_BYTES = 2 * 1024 * 1024
CACHE_SECONDS = 30.0
FIRST_WAIT = 5.0

MARKDOWN_SUFFIXES = {".md", ".markdown"}
IMAGE_SUFFIXES = {".png", ".jpg", ".jpeg", ".gif", ".webp", ".svg", ".avif", ".bmp"}

WIKILINK = re.compile(r"!?\[\[([^\[\]\n|#^]*)(?:[#^][^\[\]\n|]*)?(?:\|[^\[\]\n]*)?\]\]")
MDLINK = re.compile(r"!?\[[^\]\n]*\]\(\s*(?:<([^>\n]+)>|([^)\s]+))")
FENCE = re.compile(r"^(`{3,}|~{3,})[^\n]*\n.*?^\1[ \t]*$", re.MULTILINE | re.DOTALL)
INLINE_CODE = re.compile(r"(`+)[^`\n].*?\1")
COMMENT = re.compile(r"%%.*?%%", re.DOTALL)
SCHEME = re.compile(r"^[a-z][a-z0-9+.-]*:", re.IGNORECASE)


class Vault(NamedTuple):
    root: Path
    folders: tuple[str, ...]
    strict_breaks: bool
    ignore: tuple[str, ...]


class Index(NamedTuple):
    files: dict[str, Path]
    by_name: dict[str, list[str]]
    shared: frozenset[str]
    attachments: frozenset[str]


VAULT: Vault | None = None
CACHE: dict[str, object] = {"at": 0.0, "index": None, "thread": None, "links": {}}
LOCK = threading.Lock()


def key(text: str) -> str:
    return unicodedata.normalize("NFC", text)


def configure(where: str, table: object) -> Vault:
    """Checks the [notes] table and reads the vault's own settings."""
    if not isinstance(table, dict):
        raise SystemExit(f"sharei: {where}: [notes] must be a table")
    unknown = set(table) - {"vault", "folders"}
    if unknown:
        raise SystemExit(
            f"sharei: {where}: notes: unknown key {min(unknown)!r} (known: vault, folders)"
        )
    vault, folders = table.get("vault"), table.get("folders")
    if not isinstance(vault, str) or not vault:
        raise SystemExit(f"sharei: {where}: notes.vault must be a path")
    if (
        not isinstance(folders, list)
        or not folders
        or not all(isinstance(folder, str) for folder in folders)
    ):
        raise SystemExit(f"sharei: {where}: notes.folders must be a list of folders")
    root = Path(vault).expanduser().resolve()
    if not root.is_dir():
        raise SystemExit(f"sharei: {where}: notes.vault {vault!r} is not a folder")
    cleaned = []
    for folder in folders:
        parts = folder.strip("/").split("/")
        if (
            folder.startswith("/")
            or any(part in ("", ".", "..") or part.startswith(".") for part in parts)
            or not (root / folder).is_dir()
            or (root / folder).resolve() != root.joinpath(*parts)
        ):
            raise SystemExit(
                f"sharei: {where}: notes.folders: {folder!r} must be a folder inside the "
                "vault, written relative to it, with no hidden, '.' or '..' parts or symlinks"
            )
        cleaned.append(key("/".join(parts)))
    settings: dict[str, object] = {}
    try:
        loaded = json.loads((root / ".obsidian" / "app.json").read_text("utf-8"))
        if isinstance(loaded, dict):
            settings = loaded
    except (OSError, ValueError):
        pass
    ignore = settings.get("userIgnoreFilters")
    return Vault(
        root,
        tuple(dict.fromkeys(cleaned)),
        settings.get("strictLineBreaks", False) is not False,
        tuple(item for item in ignore if isinstance(item, str) and item)
        if isinstance(ignore, list)
        else (),
    )


def ignored(vault: Vault, relative: str) -> bool:
    for rule in vault.ignore:
        if len(rule) > 2 and rule.startswith("/") and rule.endswith("/"):
            try:
                if re.search(rule[1:-1], relative):
                    return True
            except re.error:
                continue
        elif relative.startswith(rule):
            return True
    return False


def in_folders(vault: Vault, relative: str) -> bool:
    return any(
        relative == folder or relative.startswith(folder + "/")
        for folder in vault.folders
    )


def is_markdown(name: str) -> bool:
    return posixpath.splitext(name)[1].lower() in MARKDOWN_SUFFIXES


def scan(vault: Vault) -> Index:
    files: dict[str, Path] = {}
    for directory, dirs, names in os.walk(vault.root):
        base = Path(directory)
        relative_dir = key(base.relative_to(vault.root).as_posix())
        prefix = "" if relative_dir == "." else relative_dir + "/"
        dirs[:] = sorted(
            name
            for name in dirs
            if not name.startswith(".")
            and not (base / name).is_symlink()
            and not ignored(vault, prefix + key(name) + "/")
        )
        for name in sorted(names):
            relative = prefix + key(name)
            path = base / name
            if (
                name.startswith(".")
                or path.is_symlink()
                or not path.is_file()
                or ignored(vault, relative)
            ):
                continue
            files[relative] = path
            if len(files) >= MAX_FILES:
                break
        if len(files) >= MAX_FILES:
            break
    by_name: dict[str, list[str]] = {}
    for relative in files:
        by_name.setdefault(posixpath.basename(relative).lower(), []).append(relative)
    shared = frozenset(relative for relative in files if in_folders(vault, relative))
    partial = Index(files, by_name, shared, frozenset())
    attachments = set()
    links = CACHE.get("links")
    cached: dict[str, tuple[float, list[str]]] = (
        links if isinstance(links, dict) else {}
    )
    fresh: dict[str, tuple[float, list[str]]] = {}
    for relative in shared:
        if not is_markdown(relative):
            continue
        path = files[relative]
        try:
            info = path.stat()
            if info.st_size > MAX_NOTE_BYTES:
                continue
            seen = cached.get(relative)
            if seen and seen[0] == info.st_mtime:
                targets = seen[1]
            else:
                targets = link_targets(path.read_text("utf-8", errors="replace"))
            fresh[relative] = (info.st_mtime, targets)
        except OSError:
            continue
        for target in targets:
            found = resolve(partial, target, relative)
            if found and not is_markdown(found):
                attachments.add(found)
    CACHE["links"] = fresh
    return Index(files, by_name, shared, frozenset(attachments - shared))


def refresh() -> None:
    vault = VAULT
    index = scan(vault) if vault else None
    with LOCK:
        CACHE["index"] = index
        CACHE["at"] = time.monotonic()
        CACHE["thread"] = None


def index() -> Index | None:
    if VAULT is None:
        return None
    with LOCK:
        thread = CACHE["thread"]
        stale = time.monotonic() - float(CACHE["at"]) > CACHE_SECONDS  # type: ignore[arg-type]
        if stale and thread is None:
            thread = threading.Thread(target=refresh, daemon=True)
            CACHE["thread"] = thread
            thread.start()
        first = CACHE["index"] is None
    if first and isinstance(thread, threading.Thread):
        thread.join(FIRST_WAIT)
    with LOCK:
        return CACHE["index"]  # type: ignore[return-value]


def visible_text(text: str) -> str:
    """The note without code and %%comments%%, whose links Obsidian does not follow."""
    text = FENCE.sub("", text)
    text = COMMENT.sub("", text)
    return INLINE_CODE.sub("", text)


def link_targets(text: str) -> list[str]:
    """Every link target in a note, in the form the reader looks it up."""
    text = visible_text(text)
    targets = [match.group(1).strip() for match in WIKILINK.finditer(text)]
    for match in MDLINK.finditer(text):
        target = link_key(match.group(1) or match.group(2))
        if target:
            targets.append(target)
    return list(dict.fromkeys(target for target in targets if target))


def link_key(href: str) -> str:
    """A markdown link's path, decoded and without its query or fragment."""
    if SCHEME.match(href) or href.startswith("#"):
        return ""
    href = re.split(r"[?#]", href, maxsplit=1)[0]
    return unquote(href).strip()


def resolve(index: Index, target: str, note: str) -> str | None:
    """Where a link in the note points, found the way Obsidian looks it up."""
    target = key(target.strip())
    if not target:
        return None
    absolute = target.startswith("/")
    path = posixpath.normpath(target.lstrip("/"))
    if path.startswith("../") or path in (".", ".."):
        return None
    tries = [path] if absolute else []
    if not absolute:
        here = posixpath.dirname(note)
        near = posixpath.normpath(posixpath.join(here, path))
        if not near.startswith("../") and near != "..":
            tries.append(near)
        tries.append(path)
    for candidate in tries:
        for name in (candidate, candidate + ".md"):
            if name in index.files:
                return name
    name = posixpath.basename(path).lower()
    lowered = path.lower()
    for wanted in (name, name + ".md"):
        suffix = lowered if wanted == name else lowered + ".md"
        matches = [
            relative
            for relative in index.by_name.get(wanted, [])
            if relative.lower() == suffix or relative.lower().endswith("/" + suffix)
        ]
        if matches:
            here = posixpath.dirname(note)
            return min(
                matches,
                key=lambda relative: (
                    posixpath.dirname(relative) != here,
                    relative.count("/"),
                    relative,
                ),
            )
    return None


def allowed(index: Index, relative: str) -> Path | None:
    """The file behind a request path, if it is shared or a shared note links to it."""
    relative = key(relative)
    if relative not in index.shared and relative not in index.attachments:
        return None
    path = index.files.get(relative)
    if path is None or path.is_symlink() or not path.is_file():
        return None
    return path


def is_folder(index: Index, relative: str) -> bool:
    relative = key(relative.strip("/"))
    return not relative or any(path.startswith(relative + "/") for path in index.shared)


def url(prefix: str, relative: str) -> str:
    return prefix + "/".join(quote(part) for part in relative.split("/"))


def link_map(
    index: Index, text: str, note: str, readable: Callable[[Path], bool]
) -> dict[str, dict[str, str] | None]:
    """Each link target in the note mapped to its URLs, or None when it is not shared."""
    links: dict[str, dict[str, str] | None] = {}
    for target in link_targets(text):
        found = resolve(index, target, note)
        path = allowed(index, found) if found else None
        if found is None or path is None:
            links[target] = None
            continue
        suffix = posixpath.splitext(found)[1].lower()
        entry = {"href": url("/notes-file/", found)}
        if suffix in MARKDOWN_SUFFIXES or (
            suffix not in IMAGE_SUFFIXES and suffix != ".pdf" and readable(path)
        ):
            entry["href"] = url("/notes/", found)
        elif suffix == ".pdf":
            entry["href"] = url("/notes-pdf/", found)
        elif suffix in IMAGE_SUFFIXES:
            entry["src"] = url("/notes-file/", found)
        links[target] = entry
    return links
