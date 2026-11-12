#!/usr/bin/env python3
"""A raffi script filter for sharei: notes, clipboard, drops and screenshots.

Raffi runs this with the text typed after its keyword and reads the Alfred JSON
subset it prints. Every sharei source is a view switched with Ctrl+Tab, and
everything goes through `sharec`, so the address, the login and ~/.netrc are
the ones sharec already knows.

Raffi also runs `--act` (Enter) and `--act-copy` (Ctrl+Enter) as the filter's
actions, with the selected row's variables in the environment; those two modes
open or copy what was picked.
"""

import hashlib
import json
import os
import re
import subprocess
import sys
import time
import unicodedata
from pathlib import Path
from urllib.parse import quote, urlsplit

# (view id, footer title) in Ctrl+Tab order.
VIEWS = (
    ("notes", "Notes"),
    ("clip", "Clipboard"),
    ("drop", "Drops"),
    ("shots", "Shots"),
)
LIST_LIMIT = 40  # items per kind, and the cap on notes in one listing
TITLE_MAX = 100
# Escape sequences and control characters, so a shared clipboard or a filename
# cannot move the cursor around raffi's window.
UNSAFE = re.compile(
    r"\x1b\[[0-9;?]*[ -/]*[@-~]|\x1b[@-_]|[\x00-\x08\x0b-\x1f\x7f-\x9f]"
)
ICON_ROUTE = re.compile(r"/notes-icon/([^/]+)$")

# Markdown drawn with the ANSI codes raffi supports, the same rendering as
# raffi's own scripts/github/pr.py previews.
FENCE = re.compile(r"\s*(```|~~~)")
FRONT_MATTER = re.compile(r"\A---\n(.*?)\n(?:---|\.\.\.)\s*\n", re.DOTALL)
HEADING = re.compile(r"#{1,6}\s+(.*?)[\s#]*$")
RULE = re.compile(r"\s*([-*_])(\s*\1){2,}\s*$")
LIST_ITEM = re.compile(r"(\s*)[-*+]\s+(?:\[([ xX])\]\s+)?(.*)")
QUOTE = re.compile(r"\s*>\s?(.*)")
ALERT = re.compile(r"\[!(\w+)\]\s*(.*)$")
TABLE_RULE = re.compile(r"\s*\|?(\s*:?-+:?\s*\|)+\s*(:?-+:?)?\s*$")
CODE_SPAN = re.compile(r"(`+)(.+?)\1")
HTML_TAG = re.compile(r"</?[a-zA-Z][^>]*>")
IMAGE = re.compile(r"!\[([^\]]*)\]\([^)]*\)")
COMMENT = re.compile(r"%%.*?%%", re.DOTALL)
EMBED = re.compile(r"!\[\[([^\]|#]+)(?:[|#][^\]]*)?\]\]")
WIKILINK = re.compile(r"\[\[([^\]|#]+)(?:[|#]([^\]]*))?\]\]")
MARK = re.compile(r"==(.+?)==")
LINK = re.compile(r"\[([^\]]+)\]\([^)]*\)")
STRONG = re.compile(r"(\*\*|__)(.+?)\1")
EMPHASIS = re.compile(r"(?<![\w*])([*_])(?!\s)(.+?)(?<!\s)\1(?![\w*])")
PREVIEW_MAX = 40000
IMAGE_SUFFIXES = (".png", ".jpg", ".jpeg", ".gif", ".webp", ".bmp", ".svg")
BINARY_SUFFIXES = (
    ".pdf",
    ".mp4",
    ".webm",
    ".mov",
    ".mkv",
    ".mp3",
    ".m4a",
    ".ogg",
    ".opus",
    ".wav",
    ".zip",
    ".gz",
    ".apk",
    ".heic",
    ".epub",
)


class Fail(Exception):
    """Something sharec could not do, reported as the filter's error."""


def sharec(*args: str, timeout: float = 20) -> bytes:
    try:
        done = subprocess.run(
            ["sharec", *args],
            check=True,
            capture_output=True,
            timeout=timeout,
            stdin=subprocess.DEVNULL,
        )
    except FileNotFoundError:
        raise Fail("sharec is not on PATH") from None
    except subprocess.TimeoutExpired:
        raise Fail(f"sharec {args[0]} timed out") from None
    except subprocess.CalledProcessError as error:
        detail = error.stderr.decode("utf-8", "replace").strip().splitlines()
        raise Fail(detail[-1] if detail else f"sharec {args[0]} failed") from None
    return done.stdout


def answer(*args: str) -> dict:
    """The JSON object a sharec subcommand prints, with --json."""
    try:
        return json.loads(sharec(*args))
    except ValueError:
        raise Fail(f"sharec {args[0]} printed something that is not JSON") from None


def route(path: str, timeout: float = 20) -> bytes:
    return sharec("cat", path, timeout=timeout)


def local(link: str) -> str:
    """The server route of a link sharei handed out, absolute or not."""
    parts = urlsplit(link)
    return parts.path + (f"?{parts.query}" if parts.query else "")


def image_suffix(data: bytes) -> str:
    """The extension of an image by its magic bytes: raffi decodes by name."""
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return ".webp"
    for magic, suffix in (
        (b"\x89PNG\r\n\x1a\n", ".png"),
        (b"\xff\xd8\xff", ".jpg"),
        (b"GIF8", ".gif"),
    ):
        if data.startswith(magic):
            return suffix
    head = data[:4096]
    if head.lstrip().startswith(b"<") and b"<svg" in head:
        return ".svg"
    # "BM" alone is also how a text file can start, so ask for the zero reserved
    # fields a bitmap header carries.
    if data[:2] == b"BM" and data[6:10] == b"\x00\x00\x00\x00":
        return ".bmp"
    return ""


def quietly(*args: str) -> None:
    """Run sharec without pipes: wl-copy leaves a daemon holding them open."""
    subprocess.run(
        ["sharec", *args],
        check=False,
        stdin=subprocess.DEVNULL,
        stdout=subprocess.DEVNULL,
        stderr=subprocess.DEVNULL,
    )


def cache_dir(*parts: str) -> Path:
    root = Path(os.environ.get("XDG_CACHE_HOME") or Path.home() / ".cache")
    folder = root / "raffi" / "sharei" / Path(*parts)
    folder.mkdir(parents=True, exist_ok=True)
    return folder


def fold(text: str) -> str:
    """Case and accents dropped, the way sharei compares text."""
    return "".join(
        char
        for char in unicodedata.normalize("NFKD", text.lower())
        if not unicodedata.combining(char)
    )


def flat(text: str, limit: int = TITLE_MAX) -> str:
    line = " ".join(UNSAFE.sub(" ", text).split())
    return line if len(line) <= limit else line[: limit - 1] + "…"


def sgr(text: str, on: str, off: str) -> str:
    return f"\033[{on}m{text}\033[{off}m"


def render_inline_text(text: str) -> str:
    text = COMMENT.sub("", text)
    text = HTML_TAG.sub("", text)
    text = IMAGE.sub(lambda m: sgr(f"[image: {m[1] or 'image'}]", "90", "39"), text)
    text = EMBED.sub(lambda m: sgr(f"[image: {m[1]}]", "90", "39"), text)
    text = WIKILINK.sub(lambda m: sgr(m[2] or m[1], "4;36", "24;39"), text)
    text = MARK.sub(lambda m: sgr(m[1], "1", "22"), text)
    text = LINK.sub(lambda m: sgr(m[1], "4;34", "24;39"), text)
    text = STRONG.sub(lambda m: sgr(m[2], "1", "22"), text)
    # Raffi has no italics, so emphasis only loses its markers.
    return EMPHASIS.sub(r"\2", text)


def render_inline(line: str) -> str:
    """Inline markdown, leaving code spans untouched."""
    parts, pos = [], 0
    for match in CODE_SPAN.finditer(line):
        parts.append(render_inline_text(line[pos : match.start()]))
        parts.append(sgr(match[2], "33", "39"))
        pos = match.end()
    parts.append(render_inline_text(line[pos:]))
    return "".join(parts)


def table_row(line: str, header: bool) -> str:
    """One row of a pipe table, its edge dimmed and its header bold."""
    cells = [render_inline(cell.strip()) for cell in line.strip().strip("|").split("|")]
    if header:
        cells = [sgr(cell, "1", "22") for cell in cells]
    edge = sgr("\u2502", "90", "39")
    return f"{edge} " + f" {edge} ".join(cells) + f" {edge}"


def render_markdown(text: str) -> str:
    """Markdown with colours, for the preview pane."""
    lines, in_code, in_table = [], False, False
    for line in text.splitlines():
        row = line.lstrip().startswith("|")
        if FENCE.match(line):
            in_code = not in_code
        elif in_code:
            lines.append(sgr(f"  {line}", "33", "39"))
        elif match := HEADING.match(line):
            lines.append(sgr(render_inline(match[1]), "1;35", "0"))
        elif RULE.match(line):
            lines.append(sgr("\u2500" * 40, "90", "39"))
        elif TABLE_RULE.match(line):
            continue
        elif row:
            lines.append(table_row(line, header=not in_table))
        elif match := LIST_ITEM.match(line):
            indent, box, entry = match.groups()
            marker = (
                "\u2022"
                if box is None
                else ("\u2610" if box == " " else sgr("\u2611", "32", "39"))
            )
            lines.append(f"{indent}{marker} {render_inline(entry)}")
        elif match := QUOTE.match(line):
            quoted = match[1]
            if alert := ALERT.match(quoted):
                quoted = sgr(alert[1].capitalize(), "1;33", "0")
                quoted += f" {render_inline(alert[2])}" if alert[2] else ""
            else:
                quoted = render_inline(quoted)
            lines.append(sgr("\u2502 ", "90", "39") + quoted)
        else:
            lines.append(render_inline(line))
        in_table = row
    return "\n".join(line.rstrip() for line in lines)


def rendered(text: str) -> str:
    """A note's text for the preview: front matter dimmed, markdown drawn."""
    text = text[:PREVIEW_MAX]
    head = ""
    if found := FRONT_MATTER.match(text):
        head = "\n".join(sgr(f"  {line}", "90", "39") for line in found[1].splitlines())
        head += "\n" + sgr("\u2500" * 40, "90", "39") + "\n"
        text = text[found.end() :]
    return head + render_markdown(text)


def ago(seconds: float) -> str:
    seconds = max(0, seconds)
    if seconds < 90:
        return f"{int(seconds)}s ago"
    if seconds < 5400:
        count = int(seconds // 60)
        return f"{count} min ago"
    if seconds < 172800:
        count = int(seconds // 3600)
        return f"{count}h ago"
    count = int(seconds // 86400)
    return f"{count} day{'' if count == 1 else 's'} ago"


def human(size: float) -> str:
    for unit in ("B", "KB", "MB", "GB"):
        if size < 1024 or unit == "GB":
            return f"{int(size)} B" if unit == "B" else f"{size:.1f} {unit}"
        size /= 1024
    return ""


def item(
    title: str,
    subtitle: str,
    arg: str,
    kind: str,
    *,
    icon: str | None = None,
    searched: str = "",
    **variables: str,
) -> dict:
    entry = {
        "title": flat(title),
        "subtitle": flat(subtitle),
        "arg": arg,
        "variables": {"SHAREI_KIND": kind, **variables},
        "_folded": fold(searched or f"{title} {subtitle}"),
    }
    if icon:
        entry["icon"] = {"path": icon}
    return entry


def matching(rows: list[dict], terms: list[str]) -> list[dict]:
    return [row for row in rows if all(term in row["_folded"] for term in terms)]


def note_icon(link: str, deadline: float) -> str | None:
    """A note's Icon Fairy picture, downloaded once into the cache."""
    found = ICON_ROUTE.search(urlsplit(link).path)
    name = os.path.basename(found.group(1)) if found else ""
    if not name or name.startswith("."):
        return None
    cached = cache_dir("icons") / name
    if cached.is_file():
        return str(cached)
    if time.monotonic() > deadline:
        return None
    try:
        cached.write_bytes(route(f"/notes-icon/{quote(name)}", timeout=1.5))
    except (Fail, OSError):
        return None
    return str(cached)


def note_item(entry: dict, deadline: float) -> dict:
    """One vault entry: a note, a folder or any other shared file."""
    path = entry["p"]
    folder = str(Path(path).parent)
    where = folder if folder != "." else "vault"
    kind = entry.get("k", "note")
    if kind == "folder":
        title, details = Path(path).name + "/", [where, "folder"]
    elif kind == "note":
        title, details = Path(path).stem, [where]
    else:
        title, details = (
            Path(path).name,
            [where, Path(path).suffix.lstrip(".") or "file"],
        )
    details.append(ago(time.time() - entry.get("t", 0)).removesuffix(" ago"))
    return item(
        title,
        " · ".join(part for part in details if part),
        entry["url"],
        kind if kind in ("folder", "file") else "note",
        icon=note_icon(entry.get("i", ""), deadline),
        searched=path,
        SHAREI_PATH=path,
    )


def truncation(shown: int, total: int) -> dict:
    return {
        "title": f"{shown} of {total} entries; type to search the rest",
        "subtitle": "every word you type must appear in a note's text or path",
        "valid": False,
    }


def vault_entries(terms: list[str], deadline: float) -> list[dict]:
    """Every shared note and file whose path holds all the terms, newest first."""
    entries = [
        entry
        for entry in answer("notes", "--json")["items"]
        if entry["k"] != "folder" and all(term in fold(entry["p"]) for term in terms)
    ]
    entries.sort(key=lambda entry: -entry.get("t", 0))
    return entries


def notes(terms: list[str], query: str, deadline: float) -> list[dict]:
    """The whole vault newest first, or what sharei finds for what is typed.

    One call either way: sharei searches the text of the markdown notes and the
    names of everything else, so the filter only draws what it is given.
    """
    if not query:
        entries = vault_entries(terms, deadline)
        rows = [note_item(entry, deadline) for entry in entries[:LIST_LIMIT]]
        if len(entries) > LIST_LIMIT:
            rows.append(truncation(LIST_LIMIT, len(entries)))
        return rows
    words = quote(query.strip(), safe="")
    rows = []
    for note in answer("notes", "--json", query)["results"][:LIST_LIMIT]:
        row = note_item(note, deadline)
        if hits := note.get("hits") or []:
            row["children"] = [
                item(
                    hit["s"],
                    f"line {hit['n']}",
                    f"{row['arg']}#find={hit['n']}:{words}",
                    "note",
                    SHAREI_PATH=note["p"],
                )
                for hit in hits
            ]
        rows.append(row)
    return rows


def clips(terms: list[str]) -> list[dict]:
    state = answer("get", "clip", "--json")
    now = time.time()
    rows = []

    def add(number: str, text: str, expires_at: float) -> None:
        if not text.strip():
            return
        timing = (
            f"expires in {ago(expires_at - now).removesuffix(' ago')}"
            if expires_at
            else ""
        )
        subtitle = " · ".join(
            part
            for part in (f"clipboard {number}", f"{len(text)} chars", timing)
            if part
        )
        rows.append(
            item(
                flat(text) or "(blank)",
                subtitle,
                state["url"],
                "clip",
                searched=text,
                SHAREI_CLIP="" if number == "now" else number,
            )
        )

    add("now", state.get("text", ""), state.get("expires_at", 0))
    for number, entry in enumerate(state.get("history", []), 1):
        add(str(number), entry.get("text", ""), entry.get("expires_at", 0))
    return matching(rows, terms)


def recent(terms: list[str], kinds: tuple[str, ...]) -> list[dict]:
    listed = answer("get", "list", str(LIST_LIMIT), "--json")
    rows = []
    for kind in kinds:
        for back, entry in enumerate(listed.get(kind, [])):
            if kind == "shots":
                title = "screenshot"
                subtitle = f"{entry['project']} · {ago(entry['age_seconds'])}"
                link, opened = entry["url"], entry["url"]
            else:
                details = [entry["project"]]
                if "bytes" in entry:
                    details.append(human(entry["bytes"]))
                if entry.get("comments"):
                    details.append(f"{entry['comments']} comments")
                details.append(ago(entry["age_seconds"]))
                title, subtitle = entry["name"], " · ".join(details)
                opened = entry.get("view") or entry["url"]
                link = entry["url"]
            rows.append(
                item(
                    title,
                    subtitle,
                    opened,
                    kind,
                    searched=f"{entry['name']} {entry['project']}",
                    SHAREI_BACK=str(back),
                    SHAREI_ROUTE=link,
                    SHAREI_THUMB=local(entry.get("thumb", "")),
                )
            )
    return matching(rows, terms)


SOURCES = {
    "notes": lambda terms, query, deadline: notes(terms, query, deadline),
    "clip": lambda terms, _query, _deadline: clips(terms),
    "drop": lambda terms, _query, _deadline: recent(terms, ("drop",)),
    "shots": lambda terms, _query, _deadline: recent(terms, ("shots",)),
}


def listing(argv: list[str]) -> dict:
    deadline = time.monotonic() + 2.5
    wanted = os.environ.get("RAFFI_VIEW", "")
    query = " ".join(argv)
    first, _, rest = query.partition(" ")
    if not wanted and first in SOURCES:
        wanted, query = first, rest
    views = list(VIEWS)
    terms = [fold(term) for term in query.split()]
    while True:
        view = wanted or views[0][0]
        try:
            rows = SOURCES[view](terms, query.strip(), deadline)
            break
        except Fail:
            # A sharei without a [notes] vault has no notes to offer: leave the
            # view out and land on the next one instead of showing its error.
            if view != "notes" or wanted or len(views) == 1:
                raise
            views = [pair for pair in views if pair[0] != "notes"]
    return {
        "views": [{"id": name, "title": title} for name, title in views],
        "view": view,
        "items": [public(row) for row in rows],
    }


def public(entry: dict) -> dict:
    entry.pop("_folded", None)
    if "children" in entry:
        entry["children"] = [public(child) for child in entry["children"]]
    return entry


def vault_preview(kind: str) -> dict:
    """A note or any other shared file, read through /notes-file."""
    path = os.environ.get("SHAREI_PATH", "")
    suffix = Path(path).suffix.lower()
    badge = "sharei note" if kind == "note" else "sharei file"
    meta = [["Path", path]]
    link = f"/notes-file/{quote(path)}"
    if suffix in IMAGE_SUFFIXES:
        saved = download(link, suffix)
        if saved:
            return {"badge": badge, "image": saved, "metadata": meta}
    if suffix in BINARY_SUFFIXES:
        return {"badge": badge, "text": badge, "metadata": meta}
    try:
        text = route(link, timeout=1.5).decode("utf-8")
    except (Fail, UnicodeDecodeError):
        return {
            "badge": badge,
            "text": "sharei cannot show this file as text",
            "metadata": meta,
        }
    drawn = rendered(text) if suffix in (".md", ".markdown") else text[:PREVIEW_MAX]
    return {
        "badge": badge,
        "metadata": meta,
        "sections": [{"type": "text", "heading": Path(path).name, "content": drawn}],
    }


def preview() -> dict:
    kind = os.environ.get("SHAREI_KIND", "note")
    value = os.environ.get("RAFFI_VALUE", "")
    if kind in ("note", "file"):
        return vault_preview(kind)
    if kind == "folder":
        path = os.environ.get("SHAREI_PATH", "")
        return {
            "badge": "sharei folder",
            "text": f"{value}\n\nEnter opens {path} in sharei.",
            "metadata": [["Folder", path]],
        }
    if kind == "clip":
        number = os.environ.get("SHAREI_CLIP", "")
        text = sharec("get", "clip", number or "0", timeout=1.5).decode(
            "utf-8", "replace"
        )
        return {
            "badge": "sharei clipboard",
            "metadata": [["Entry", number or "now"], ["Chars", str(len(text))]],
            "sections": [{"type": "text", "content": text[:PREVIEW_MAX]}],
        }
    link = os.environ.get("SHAREI_ROUTE", "")
    value = value or link
    if kind == "shots":
        key = local(link).removeprefix("/shot/")
        for candidate in (f"/thumb/{key}", f"/shot/{key}"):
            saved = download(candidate, ".png")
            if saved:
                return {
                    "badge": "sharei screenshot",
                    "image": saved,
                    "metadata": [["URL", value]],
                }
        return {
            "badge": "sharei screenshot",
            "text": value,
            "metadata": [["URL", value]],
        }
    thumb = os.environ.get("SHAREI_THUMB", "")
    saved = download(thumb or link, Path(local(link)).suffix)
    if saved and saved.lower().endswith(IMAGE_SUFFIXES):
        return {"badge": "sharei drop", "image": saved, "metadata": [["URL", value]]}
    try:
        text = route(f"{urlsplit(link).path}?raw", timeout=1.5).decode("utf-8")
    except (Fail, UnicodeDecodeError):
        text = ""
    found = {"badge": "sharei drop", "metadata": [["URL", value]]}
    if text:
        marked = Path(local(link)).suffix.lower() in (".md", ".markdown")
        found["sections"] = [
            {
                "type": "text",
                "heading": Path(local(link)).name,
                "content": rendered(text) if marked else text[:PREVIEW_MAX],
            }
        ]
    else:
        found["text"] = value
    return found


def download(link: str, suffix: str = "") -> str | None:
    """Fetch a route into the preview cache and return its local path.

    The file is named after what it holds, not after the route: raffi picks the
    decoder from the extension, so a webp screenshot saved as .png stays blank.
    """
    try:
        data = route(local(link), timeout=1.5)
    except Fail:
        return None
    suffix = image_suffix(data) or suffix or ".bin"
    digest = hashlib.sha1(link.encode()).hexdigest()[:16]
    target = cache_dir("previews") / f"{digest}{suffix.lower()}"
    try:
        target.write_bytes(data)
    except OSError:
        return None
    return str(target)


def act(copy_value: bool) -> int:
    kind = os.environ.get("SHAREI_KIND", "")
    value = os.environ.get("RAFFI_VALUE", "")
    if copy_value:
        quietly("cp", value)
    elif kind == "clip":
        quietly("get", "clip", os.environ.get("SHAREI_CLIP") or "0", "-c")
    else:
        subprocess.run(
            ["xdg-open", value],
            check=False,
            start_new_session=True,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
    return 0


def main(argv: list[str]) -> int:
    if argv[:1] == ["--act"]:
        return act(copy_value=False)
    if argv[:1] == ["--act-copy"]:
        return act(copy_value=True)
    if os.environ.get("RAFFI_PREVIEW") == "1":
        print(json.dumps(preview()))
    else:
        print(json.dumps(listing(argv)))
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main(sys.argv[1:]))
    except Fail as error:
        print(f"sharei: {error}", file=sys.stderr)
        # Raffi reads a list or a preview, so failure is a row, not a crash.
        if os.environ.get("RAFFI_PREVIEW") == "1":
            told = {"title": "sharei", "text": str(error)}
        else:
            told = {
                "items": [
                    {
                        "title": f"sharei: {error}",
                        "subtitle": "check SHAREI_URL, the login, and that sharec is installed",
                        "valid": False,
                    }
                ]
            }
        print(json.dumps(told))
        sys.exit(0)
