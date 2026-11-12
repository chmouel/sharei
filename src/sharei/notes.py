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
ICON_ID = re.compile(r"[A-Za-z0-9][A-Za-z0-9_-]{0,127}")
ICON_SUFFIXES = (".png", ".svg", ".jpg", ".jpeg", ".webp", ".gif")
ICON_MAX_BYTES = 1024 * 1024

# Full-text search over the shared notes.
SEARCH_QUERY_MAX = 200
SEARCH_TERMS_MAX = 8
SEARCH_NOTES_MAX = 50
SEARCH_HITS_PER_NOTE = 5
SEARCH_SNIPPET_CHARS = 200
# Folded note texts kept in memory between searches; past this they are read each time.
SEARCH_CACHE_MAX_CHARS = 64 * 1024 * 1024
COMBINING = re.compile("[\u0300-\u036f]")


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
    # Icon Fairy: shared note or folder path -> icon file name, and that name -> its file.
    icons: dict[str, str]
    icon_files: dict[str, Path]


VAULT: Vault | None = None
CACHE: dict[str, object] = {"at": 0.0, "index": None, "thread": None, "links": {}}
LOCK = threading.Lock()
# Note path -> (mtime, size, text, folded text), for search.
TEXTS: dict[str, tuple[float, int, str, str]] = {}
TEXTS_HELD = [0]
TEXTS_LOCK = threading.Lock()


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
    partial = Index(files, by_name, shared, frozenset(), {}, {})
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
    icons, icon_files = scan_icons(vault, shared)
    return Index(
        files, by_name, shared, frozenset(attachments - shared), icons, icon_files
    )


def scan_icons(
    vault: Vault, shared: frozenset[str]
) -> tuple[dict[str, str], dict[str, Path]]:
    """Icons the Icon Fairy plugin gives to shared notes and folders.

    Only the icon images those paths use are kept, so the rest of the plugin's folder,
    which sits under the hidden .obsidian, stays unreachable.
    """
    obsidian = vault.root / ".obsidian"
    plugin = obsidian / "plugins" / "icon-fairy"
    try:
        enabled = json.loads((obsidian / "community-plugins.json").read_text("utf-8"))
        data = json.loads((plugin / "data.json").read_text("utf-8"))
    except (OSError, ValueError):
        return {}, {}
    icon_map = data.get("iconMap") if isinstance(data, dict) else None
    if (
        not isinstance(enabled, list)
        or "icon-fairy" not in enabled
        or not isinstance(icon_map, dict)
    ):
        return {}, {}
    folders = set()
    for relative in shared:
        parts = relative.split("/")[:-1]
        folders.update("/".join(parts[:depth]) for depth in range(1, len(parts) + 1))
    icons: dict[str, str] = {}
    icon_files: dict[str, Path] = {}
    for path, entry in icon_map.items():
        if not isinstance(path, str) or not isinstance(entry, dict):
            continue
        relative = key(path.strip("/"))
        icon_id = entry.get("value")
        if (
            entry.get("type") not in (None, "custom")
            or not isinstance(icon_id, str)
            or not ICON_ID.fullmatch(icon_id)
            or (
                relative not in shared
                and not (relative in folders and in_folders(vault, relative))
            )
        ):
            continue
        for suffix in ICON_SUFFIXES:
            name = icon_id + suffix
            file = plugin / "icons" / name
            try:
                if (
                    not file.is_symlink()
                    and file.is_file()
                    and file.stat().st_size <= ICON_MAX_BYTES
                ):
                    icons[relative] = name
                    icon_files[name] = file
                    break
            except OSError:
                continue
    return icons, icon_files


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


def fold(text: str) -> str:
    """Lower case without accents, the way the search box compares text.

    Only the common combining marks are dropped, which keeps line breaks where they were.
    lower() rather than casefold() matches JavaScript's toLowerCase(), so the picker and
    the reader highlight what this matched.
    """
    return COMBINING.sub("", unicodedata.normalize("NFKD", text)).lower()


def note_text(relative: str, path: Path) -> tuple[str, str] | None:
    """A shared note's text and its folded form, cached until the file changes."""
    try:
        info = path.stat()
    except OSError:
        return None
    if info.st_size > MAX_NOTE_BYTES:
        return None
    with TEXTS_LOCK:
        cached = TEXTS.get(relative)
    if cached and cached[0] == info.st_mtime and cached[1] == info.st_size:
        return cached[2], cached[3]
    try:
        text = path.read_text("utf-8", errors="replace")
    except OSError:
        return None
    folded = fold(text)
    with TEXTS_LOCK:
        forget(relative)
        if TEXTS_HELD[0] + len(text) + len(folded) <= SEARCH_CACHE_MAX_CHARS:
            TEXTS[relative] = (info.st_mtime, info.st_size, text, folded)
            TEXTS_HELD[0] += len(text) + len(folded)
    return text, folded


def forget(relative: str) -> None:
    """Drops a cached note text. The caller holds TEXTS_LOCK."""
    entry = TEXTS.pop(relative, None)
    if entry:
        TEXTS_HELD[0] -= len(entry[2]) + len(entry[3])


def snippet(line: str, folded: str, terms: list[str]) -> str:
    """The line, cut down around its first match when it is long."""
    line = line.strip()
    if len(line) <= SEARCH_SNIPPET_CHARS:
        return line
    folded = fold(line)
    at = min((folded.find(term) for term in terms if term in folded), default=0)
    if len(folded) != len(line):
        # Folding changed the length: walk the line to the character the match starts in.
        seen = 0
        for index, char in enumerate(line):
            seen += len(fold(char))
            if seen > at:
                at = index
                break
    start = max(
        0, min(at - SEARCH_SNIPPET_CHARS // 4, len(line) - SEARCH_SNIPPET_CHARS)
    )
    end = start + SEARCH_SNIPPET_CHARS
    return ("…" if start else "") + line[start:end] + ("…" if end < len(line) else "")


def search(index: Index, query: str) -> tuple[list[str], list[dict[str, object]]]:
    """Shared notes holding every word of the query, in their text or their path.

    Each note comes with the lines that match the most words, best lines and notes first.
    """
    terms = list(dict.fromkeys(fold(query[:SEARCH_QUERY_MAX]).split()))[
        :SEARCH_TERMS_MAX
    ]
    if not terms:
        return [], []
    found: list[tuple[float, float, dict[str, object]]] = []
    for relative in index.shared:
        if not is_markdown(relative):
            continue
        # The same check as serving the note, so a file swapped for a symlink since
        # the scan is skipped.
        path = allowed(index, relative)
        if path is None:
            continue
        loaded = note_text(relative, path)
        if loaded is None:
            continue
        text, folded = loaded
        name = fold(posixpath.splitext(relative)[0])
        if not all(term in folded or term in name for term in terms):
            continue
        lines = []
        if any(term in folded for term in terms):
            for number, (line, lowered) in enumerate(
                zip(text.split("\n"), folded.split("\n"), strict=False), 1
            ):
                matched = sum(term in lowered for term in terms)
                if matched and line.strip():
                    lines.append((matched, number, line, lowered))
        best = sorted(lines, key=lambda item: (-item[0], item[1]))[
            :SEARCH_HITS_PER_NOTE
        ]
        title = fold(posixpath.basename(name))
        score = (
            sum(min(folded.count(term), 10) for term in terms)
            + 8 * sum(term in title for term in terms)
            + 3 * (best and max(item[0] for item in best) or 0)
        )
        try:
            changed = path.stat().st_mtime
        except OSError:
            changed = 0.0
        found.append(
            (
                score,
                changed,
                {
                    "p": relative,
                    "k": "note",
                    "h": url("/notes/", relative),
                    "i": url("/notes-icon/", index.icons[relative])
                    if relative in index.icons
                    else "",
                    "t": int(changed),
                    "hits": [
                        {"n": number, "s": snippet(line, lowered, terms)}
                        for _, number, line, lowered in best
                    ],
                },
            )
        )
    found.sort(key=lambda item: (-item[0], -item[1], item[2]["p"]))
    with TEXTS_LOCK:
        for gone in set(TEXTS) - index.shared:
            forget(gone)
    return terms, [entry for _, _, entry in found[:SEARCH_NOTES_MAX]]
