#!/usr/bin/env python3
"""Upload a file, a screenshot or markdown to sharei.

Without FILE or a mode option, pick an action from a menu. FILE ending in .md
or .markdown is shared as markdown along with its local images; any other file
is uploaded as is, and text files get a syntax-highlighted page.

Environment: SHAREI_URL (upload target, default http://localhost:8000),
SHAREI_PUBLIC_URL (base of the printed links, default SHAREI_URL),
SHAREI_PROJECT (default project).
"""

import argparse
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path
from urllib.parse import quote, unquote, urlencode

SHAREI_URL = os.environ.get("SHAREI_URL", "http://localhost:8000").rstrip("/")
# Base for the links printed for other devices; uploads still go to SHAREI_URL.
PUBLIC_URL = (os.environ.get("SHAREI_PUBLIC_URL") or SHAREI_URL).rstrip("/")

UPLOAD_FILE = "Upload a file"
SCREENSHOT = "Capture and upload screenshot"
MARKDOWN_FILE = "Share markdown from file"
MARKDOWN_CLIPBOARD = "Share markdown from clipboard"
ACTIONS = [UPLOAD_FILE, SCREENSHOT, MARKDOWN_FILE, MARKDOWN_CLIPBOARD]
MARKDOWN_SUFFIXES = (".md", ".markdown")

MAX_IMAGE_BYTES = 20 * 1024 * 1024
MAX_IMAGES = 50
MAX_TOTAL_BYTES = 100 * 1024 * 1024
IMAGE_EXTENSIONS = {
    ".png": "png",
    ".jpg": "jpeg",
    ".jpeg": "jpeg",
    ".gif": "gif",
    ".webp": "webp",
    ".svg": "svg",
}

INLINE_IMAGE = re.compile(r"!\[(?:[^\]\\\n]|\\.)*\]\(\s*(<[^>\n]*>|[^\s()<>]+)")
REFERENCE = re.compile(r"^ {0,3}\[[^\]\n]+\]:[ \t]*(<[^>\n]*>|\S+)", re.MULTILINE)
HTML_TAG = re.compile(r"<(?:img|source)\b[^>]*>", re.IGNORECASE)
HTML_ATTRIBUTE = re.compile(
    r"""\b(src|srcset)\s*=\s*(?:"([^"]*)"|'([^']*)'|([^\s"'>]+))""", re.IGNORECASE
)
SCHEME = re.compile(r"^[a-zA-Z][a-zA-Z0-9+.-]*:")
FENCE = re.compile(r"^ {0,3}(`{3,}|~{3,})")
CODE_SPAN = re.compile(r"(`+)[^`].*?\1", re.DOTALL)


class Abort(Exception):
    pass


def human(size: int) -> str:
    if size < 1024:
        return f"{size} B"
    if size < 1024 * 1024:
        return f"{size / 1024:.1f} KB"
    return f"{size / 1024 / 1024:.1f} MB"


def gum(*args: str) -> str | None:
    """Run gum on the terminal and return its output, or None when cancelled."""
    if not shutil.which("gum"):
        raise Abort("Missing required command: gum")
    result = subprocess.run(
        ["gum", *args], check=False, stdout=subprocess.PIPE, text=True
    )
    return result.stdout.strip() if result.returncode == 0 else None


def confirm(question: str) -> bool:
    sys.stdout.flush()
    if shutil.which("gum"):
        return subprocess.run(["gum", "confirm", question], check=False).returncode == 0
    return input(f"{question} [y/N] ").strip().lower() in ("y", "yes")


def upload(name: str, data: bytes, project: str) -> dict:
    params = {"name": name, **({"project": project} if project else {})}
    request = urllib.request.Request(
        f"{SHAREI_URL}/upload?{urlencode(params)}", data=data, method="POST"
    )
    try:
        with urllib.request.urlopen(request, timeout=300) as response:
            return json.load(response)
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("error", error.reason)
        except ValueError:
            detail = error.reason
        raise Abort(f"Uploading {name} failed: {detail}") from error
    except (urllib.error.URLError, OSError, ValueError) as error:
        raise Abort(f"Uploading {name} failed: {error}") from error


def markdown_name(name: str) -> str:
    """Only .md and .markdown names are rendered, so README or notes.txt get .md added."""
    return name if name.lower().endswith(MARKDOWN_SUFFIXES) else f"{name}.md"


def pick_file() -> Path:
    if shutil.which("yazi"):
        with tempfile.TemporaryDirectory() as folder:
            chosen = Path(folder) / "chosen"
            subprocess.run(["yazi", f"--chooser-file={chosen}"], check=False)
            lines = chosen.read_text().splitlines() if chosen.exists() else []
        picked = lines[0] if lines else ""
    else:
        picked = gum("file") or ""
    if not picked or not Path(picked).is_file():
        raise Abort("No file selected.")
    return Path(picked)


def capture_screenshot(target: Path) -> None:
    for command in (
        ["grim", str(target)],
        ["gnome-screenshot", f"--file={target}"],
        ["scrot", str(target)],
        ["screencapture", str(target)],
    ):
        if shutil.which(command[0]):
            subprocess.run(command, check=True)
            return
    raise Abort(
        "No supported screenshot tool found (grim, gnome-screenshot, scrot, screencapture)."
    )


def read_clipboard() -> bytes:
    if shutil.which("wl-paste") and os.environ.get("WAYLAND_DISPLAY"):
        command = ["wl-paste", "--no-newline"]
    elif shutil.which("xclip"):
        command = ["xclip", "-o", "-selection", "clipboard"]
    elif shutil.which("pbpaste"):
        command = ["pbpaste"]
    else:
        raise Abort("No clipboard tool found (wl-paste, xclip, pbpaste).")
    data = subprocess.run(command, stdout=subprocess.PIPE, check=True).stdout
    if not data:
        raise Abort("The clipboard is empty.")
    return data


# Local images of a markdown file. The markdown decides which files get read,
# so only image files inside the document's git repository (or its directory)
# are accepted, and everything picked or refused is shown before uploading.


def mask_code(text: str) -> str:
    """Blank out fenced blocks and code spans, keeping offsets, so examples are left alone."""
    lines = text.splitlines(keepends=True)
    fence = None
    for index, line in enumerate(lines):
        match = FENCE.match(line)
        if fence is None:
            if not match:
                continue
            fence = match.group(1)
        elif match and match.group(1).startswith(fence):
            fence = None
        lines[index] = re.sub(r"[^\n]", " ", line)
    masked = "".join(lines)
    return CODE_SPAN.sub(lambda match: re.sub(r"[^\n]", " ", match.group(0)), masked)


def image_references(text: str) -> list[tuple[int, int, str]]:
    """Return (start, end, raw path) for every image destination in the document."""
    masked = mask_code(text)
    found = []

    def add(start: int, end: int) -> None:
        raw = text[start:end]
        if raw.startswith("<") and raw.endswith(">"):
            start, end, raw = start + 1, end - 1, raw[1:-1]
        found.append((start, end, raw))

    for match in INLINE_IMAGE.finditer(masked):
        add(*match.span(1))
    for match in REFERENCE.finditer(masked):
        raw = match.group(1).strip("<>")
        path = unquote(raw.split("#")[0].split("?")[0])
        if Path(path).suffix.lower() in IMAGE_EXTENSIONS:
            add(*match.span(1))
    for tag in HTML_TAG.finditer(masked):
        for attribute in HTML_ATTRIBUTE.finditer(tag.group(0)):
            group = next(g for g in (2, 3, 4) if attribute.group(g) is not None)
            start = tag.start() + attribute.start(group)
            value = attribute.group(group)
            if attribute.group(1).lower() == "src":
                found.append((start, start + len(value), value))
                continue
            for candidate in re.finditer(r"[^\s,]+(?:\s+[^\s,]+)?", value):
                url = candidate.group(0).split()[0]
                offset = start + candidate.start()
                found.append((offset, offset + len(url), url))
    return found


def allowed_root(document: Path) -> Path:
    folder = document.parent
    try:
        top = subprocess.run(
            ["git", "-C", str(folder), "rev-parse", "--show-toplevel"],
            capture_output=True,
            text=True,
            check=True,
            stdin=subprocess.DEVNULL,
        ).stdout.strip()
    except (OSError, subprocess.CalledProcessError):
        top = ""
    return Path(os.path.realpath(top or folder))


def image_kind(data: bytes) -> str | None:
    if data.startswith(b"\x89PNG\r\n\x1a\n"):
        return "png"
    if data.startswith(b"\xff\xd8\xff"):
        return "jpeg"
    if data[:6] in (b"GIF87a", b"GIF89a"):
        return "gif"
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return "webp"
    head = data[:65536].lstrip(b"\xef\xbb\xbf \t\r\n").lower()
    if head.startswith((b"<svg", b"<?xml", b"<!--", b"<!doctype svg")) and (
        b"<svg" in head
    ):
        return "svg"
    return None


def check_image(raw: str, document: Path, root: Path) -> tuple[Path | None, str]:
    """Resolve a reference to a file allowed to leave the machine, or explain why not."""
    path = unquote(raw.split("#", 1)[0].split("?", 1)[0])
    if not path:
        return None, "empty path"
    if path.startswith("/"):
        return None, "absolute path"
    if path.startswith("~"):
        return None, "home directory path"
    if "\\" in path or "\0" in path:
        return None, "unsupported characters"
    lexical = Path(path)
    if any(part.startswith(".") and part not in (".", "..") for part in lexical.parts):
        return None, "hidden file or directory"
    extension = lexical.suffix.lower()
    if extension not in IMAGE_EXTENSIONS:
        return None, "not an image extension"
    resolved = Path(os.path.realpath(document.parent / lexical))
    if not resolved.is_relative_to(root):
        return None, f"outside {root}"
    if any(part.startswith(".") for part in resolved.relative_to(root).parts):
        return None, "hidden file or directory"
    if resolved.suffix.lower() != extension:
        return None, "symlink to a different file type"
    try:
        info = resolved.stat()
    except OSError:
        return None, "not found"
    if not stat.S_ISREG(info.st_mode):
        return None, "not a regular file"
    return resolved, ""


def scan_images(document: Path, text: str) -> tuple[dict, list, dict, Path]:
    """Validate the local images and read them once, so what was checked is what gets sent."""
    root = allowed_root(document)
    images: dict[str, dict] = {}
    spans = []
    skipped: dict[str, str] = {}
    total = 0
    for start, end, raw in image_references(text):
        if SCHEME.match(raw) or raw.startswith(("//", "#")):
            continue
        resolved, reason = check_image(raw, document, root)
        if resolved is None:
            skipped.setdefault(raw, reason)
            continue
        key = str(resolved)
        if key not in images:
            if len(images) >= MAX_IMAGES:
                raise Abort(f"More than {MAX_IMAGES} local images, aborting.")
            try:
                descriptor = os.open(resolved, os.O_RDONLY | os.O_NOFOLLOW)
                with os.fdopen(descriptor, "rb") as stream:
                    data = stream.read(MAX_IMAGE_BYTES + 1)
            except OSError as error:
                skipped.setdefault(raw, f"unreadable: {error.strerror}")
                continue
            if len(data) > MAX_IMAGE_BYTES:
                raise Abort(f"{raw} is over {human(MAX_IMAGE_BYTES)}, aborting.")
            if image_kind(data) != IMAGE_EXTENSIONS[resolved.suffix.lower()]:
                skipped.setdefault(raw, "content is not that image type")
                continue
            total += len(data)
            if total > MAX_TOTAL_BYTES:
                raise Abort(
                    f"Local images add up to over {human(MAX_TOTAL_BYTES)}, aborting."
                )
            images[key] = {
                "name": resolved.name,
                "label": resolved.relative_to(root).as_posix(),
                "data": data,
            }
        spans.append((start, end, key))
    return images, spans, skipped, root


def share_markdown_file(document: Path, name: str, project: str) -> bytes:
    """Upload the document's local images and return the markdown pointing at them."""
    document = Path(os.path.realpath(document))
    text = document.read_text(encoding="utf-8", errors="replace")
    images, spans, skipped, root = scan_images(document, text)
    if images:
        print(f"Local images to upload (from {root}):")
        for image in images.values():
            print(f"  {image['label']}  {human(len(image['data']))}")
    if skipped:
        print("Image references left as is:")
        for raw, reason in skipped.items():
            print(f"  {raw}  ({reason})")
    if not images:
        return text.encode()
    if not confirm(f"Upload these images with {name}?"):
        raise SystemExit(0)
    urls = {}
    for key, image in images.items():
        url = upload(image["name"], image["data"], project)["url"]
        urls[key] = quote(url, safe="/%")
        print(f"Uploaded {image['label']} -> {url}")
    for start, end, key in sorted(spans, reverse=True):
        text = text[:start] + urls[key] + text[end:]
    return text.encode()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    mode = parser.add_mutually_exclusive_group()
    mode.add_argument(
        "-s",
        "--screenshot",
        dest="action",
        action="store_const",
        const=SCREENSHOT,
        help="capture the screen and upload it",
    )
    mode.add_argument(
        "-c",
        "--clipboard",
        dest="action",
        action="store_const",
        const=MARKDOWN_CLIPBOARD,
        help="share the clipboard text as markdown",
    )
    mode.add_argument(
        "-m",
        "--markdown",
        dest="action",
        action="store_const",
        const=MARKDOWN_FILE,
        help="share FILE as markdown whatever its name (or pick one)",
    )
    mode.add_argument(
        "-f",
        "--file",
        dest="action",
        action="store_const",
        const=UPLOAD_FILE,
        help="upload FILE as is, even a markdown file (or pick one)",
    )
    parser.add_argument("-n", "--name", help="name to upload under")
    parser.add_argument(
        "-p",
        "--project",
        default=os.environ.get("SHAREI_PROJECT", ""),
        help="sharei project (default: $SHAREI_PROJECT or the server's inbox)",
    )
    parser.add_argument("file", nargs="?", type=Path, metavar="FILE")
    args = parser.parse_args()
    if args.file is not None:
        if args.action in (SCREENSHOT, MARKDOWN_CLIPBOARD):
            parser.error("FILE cannot be used with --screenshot or --clipboard")
        if not args.file.is_file():
            parser.error(f"not a file: {args.file}")
        if args.action is None:
            markdown = args.file.name.lower().endswith(MARKDOWN_SUFFIXES)
            args.action = MARKDOWN_FILE if markdown else UPLOAD_FILE
    return args


def main() -> int:
    args = parse_args()
    action = args.action or gum("choose", *ACTIONS)
    if not action:
        return 0
    with tempfile.TemporaryDirectory() as workdir:
        if action == UPLOAD_FILE:
            file = args.file or pick_file()
            name = args.name or file.name
            data = file.read_bytes()
        elif action == SCREENSHOT:
            file = Path(workdir) / "screenshot.png"
            capture_screenshot(file)
            name = args.name or file.name
            data = file.read_bytes()
        elif action == MARKDOWN_FILE:
            file = args.file or pick_file()
            name = markdown_name(args.name or file.name)
            data = share_markdown_file(file, name, args.project)
        else:
            data = read_clipboard()
            name = args.name or gum(
                "input",
                "--prompt",
                "Name: ",
                "--value",
                f"note-{time.strftime('%Y%m%d-%H%M%S')}.md",
            )
            if name is None:
                return 0
            name = markdown_name(Path(name or "note.md").name)
    response = upload(name, data, args.project)
    print(f"Uploaded {response.get('name', name)} ({human(response.get('size', 0))})")
    print(f"Download: {PUBLIC_URL}{response['url']}")
    if response.get("view"):
        print(f"Open it:  {PUBLIC_URL}{response['view']}")
    return 0


def run() -> None:
    try:
        sys.exit(main())
    except Abort as error:
        print(error, file=sys.stderr)
        sys.exit(1)
    except KeyboardInterrupt:
        sys.exit(130)


if __name__ == "__main__":
    run()
