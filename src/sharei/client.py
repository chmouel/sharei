#!/usr/bin/env python3
"""Upload a file, a screenshot or markdown to sharei, or get things back.

Without FILE or a mode option, pick an action from a menu. FILE ending in .md
or .markdown is shared as markdown along with its local images; any other file
is uploaded as is, and text files get a syntax-highlighted page.

"sharec get" fetches the shared clipboard, the newest dropped file or
screenshot, or lists what is there; see "sharec get --help".

Environment: SHAREI_URL (upload target, default http://localhost:8000),
SHAREI_PUBLIC_URL (base of the printed links, default SHAREI_URL),
SHAREI_PROJECT (default project).
"""

import argparse
import base64
import io
import json
import os
import re
import shutil
import stat
import struct
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
GET_CLIP = "Copy the shared clipboard here"
GET_DROP = "Download the newest dropped file"
ACTIONS = [
    UPLOAD_FILE,
    SCREENSHOT,
    MARKDOWN_FILE,
    MARKDOWN_CLIPBOARD,
    GET_CLIP,
    GET_DROP,
]
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


def fetch(path: str) -> bytes:
    try:
        with urllib.request.urlopen(f"{SHAREI_URL}{path}", timeout=300) as response:
            return response.read()
    except urllib.error.HTTPError as error:
        try:
            detail = json.load(error).get("error", error.reason)
        except ValueError:
            detail = error.reason
        raise Abort(f"Fetching {path} failed: {detail}") from error
    except (urllib.error.URLError, OSError) as error:
        raise Abort(f"Fetching {path} failed: {error}") from error


def recent(limit: int, project: str) -> dict:
    params = {"limit": str(limit), **({"project": project} if project else {})}
    try:
        return json.loads(fetch(f"/recent?{urlencode(params)}"))
    except ValueError as error:
        raise Abort(f"Unexpected answer from {SHAREI_URL}/recent") from error


def write_clipboard(data: bytes) -> None:
    if shutil.which("wl-copy") and os.environ.get("WAYLAND_DISPLAY"):
        command = ["wl-copy"]
    elif shutil.which("xclip"):
        command = ["xclip", "-selection", "clipboard"]
    elif shutil.which("pbcopy"):
        command = ["pbcopy"]
    else:
        raise Abort("No clipboard tool found (wl-copy, xclip, pbcopy).")
    subprocess.run(command, input=data, check=True)


def free_name(folder: Path, name: str) -> Path:
    """A path in folder for name that does not exist yet: name, name-1.ext, name-2.ext..."""
    name = Path(name).name.lstrip(".") or "download"
    stem, suffix = Path(name).stem, Path(name).suffix
    candidate, index = folder / name, 0
    while candidate.exists() or candidate.is_symlink():
        index += 1
        candidate = folder / f"{stem}-{index}{suffix}"
    return candidate


def ago(seconds: int) -> str:
    for unit, size in (("d", 86400), ("h", 3600), ("m", 60)):
        if seconds >= size:
            return f"{seconds // size}{unit} ago"
    return f"{seconds}s ago"


def get_clip(back: int, copy: bool) -> None:
    data = fetch(f"/clip/raw?n={back}")
    if copy:
        if not data:
            raise Abort("The shared clipboard is empty.")
        write_clipboard(data)
        print(f"Copied {human(len(data))} to the clipboard.", file=sys.stderr)
        return
    sys.stdout.buffer.write(data)
    if data and sys.stdout.isatty() and not data.endswith(b"\n"):
        sys.stdout.buffer.write(b"\n")
    sys.stdout.flush()


KITTY_CHUNK = 4096
# Control characters other than tab and newline, so a dropped file cannot send
# escape sequences to the terminal.
TERMINAL_UNSAFE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")


def terminal_size() -> tuple[int, int, int, int]:
    """Terminal columns and rows, and the pixel size of one cell (0 if unknown)."""
    columns, rows = shutil.get_terminal_size()
    try:
        import fcntl
        import termios

        packed = fcntl.ioctl(sys.stdout.fileno(), termios.TIOCGWINSZ, b"\0" * 8)
        rows, columns, xpixel, ypixel = struct.unpack("HHHH", packed)
    except (ImportError, OSError):
        return columns, rows, 0, 0
    if not columns or not rows:
        return *shutil.get_terminal_size(), 0, 0
    return columns, rows, xpixel // columns, ypixel // rows


def as_png(data: bytes) -> tuple[bytes, int, int] | None:
    """The image as PNG with its pixel size, converting with Pillow when it is
    installed; None when it cannot be shown."""
    if image_kind(data) == "png" and data[12:16] == b"IHDR":
        width, height = struct.unpack(">II", data[16:24])
        return data, width, height
    if image_kind(data) not in ("jpeg", "gif", "webp"):
        return None
    try:
        from PIL import Image
    except ImportError:
        return None
    try:
        with Image.open(io.BytesIO(data)) as image:
            out = io.BytesIO()
            image.save(out, "PNG")
            return out.getvalue(), image.width, image.height
    except (OSError, ValueError, Image.DecompressionBombError):
        return None


def kitty_image(
    png: bytes, width: int, height: int, max_rows: int = 0, image_id: int = 0
) -> bytes:
    """Kitty graphics protocol escapes drawing png at the cursor, scaled down
    to the terminal width and, with max_rows, to that many rows."""
    columns, _, cell_width, cell_height = terminal_size()
    cell_width, cell_height = cell_width or 8, cell_height or 16
    scale = min(1, columns * cell_width / max(width, 1))
    if max_rows:
        scale = min(scale, max_rows * cell_height / max(height, 1))
    fit = f",c={max(1, int(width * scale / cell_width))}" if scale < 1 else ""
    fit += f",i={image_id}" if image_id else ""
    encoded = base64.standard_b64encode(png)
    chunks = [
        encoded[i : i + KITTY_CHUNK] for i in range(0, len(encoded), KITTY_CHUNK)
    ] or [b""]
    out = []
    for index, chunk in enumerate(chunks):
        more = int(index < len(chunks) - 1)
        control = f"a=T,f=100,q=2{fit},m={more}" if index == 0 else f"m={more}"
        out.append(b"\x1b_G" + control.encode() + b";" + chunk + b"\x1b\\")
    return b"".join(out)


NEXT_KEYS = {b" ", b"j", b"\x1b[C", b"\x1bOC"}
PREVIOUS_KEYS = {b"k", b"\x7f", b"\x08", b"\x1b[3~", b"\x1b[D", b"\x1bOD"}
DELETE_KEYS = {b"\x04"}
BROWSE_MAX = 50


def delete_item(item: dict) -> None:
    """Delete a screenshot or dropped file listed by /recent on the server."""
    url = item["url"]
    if url.startswith("/shot/"):
        path = "/shots/delete/" + url.removeprefix("/shot/")
    else:
        path = "/poub/delete/" + url.removeprefix("/poub/")
    request = urllib.request.Request(f"{SHAREI_URL}{path}", data=b"", method="POST")
    try:
        urllib.request.urlopen(request, timeout=30).close()
    except (urllib.error.URLError, OSError) as error:
        raise Abort(f"Deleting {item['name']} failed: {error}") from error


def wait_key() -> bytes:
    """Wait for one key press on the terminal without echoing it; Ctrl-C reads
    as no key."""
    import termios
    import tty

    fd = sys.stdin.fileno()
    saved = termios.tcgetattr(fd)
    try:
        tty.setcbreak(fd)
        return os.read(fd, 32)
    except KeyboardInterrupt:
        return b""
    finally:
        termios.tcsetattr(fd, termios.TCSADRAIN, saved)


def browse(items: list[dict], index: int, image: tuple[bytes, int, int]) -> None:
    """Show items[index] full screen. Space or right goes to the next (older)
    image (also j), backspace, delete, left or k to the previous one, wrapping
    around and skipping what isn't an image; Ctrl-D deletes the image on the
    server after a y to confirm; any other key puts the terminal back."""
    out = sys.stdout.buffer
    cache: dict[int, tuple[bytes, int, int] | None] = {index: image}

    def load(position: int) -> tuple[bytes, int, int] | None:
        if position not in cache:
            try:
                cache[position] = as_png(fetch(items[position]["url"]))
            except Abort:
                cache[position] = None
        return cache[position]

    def say(text: str) -> None:
        columns, rows = terminal_size()[:2]
        text = TERMINAL_UNSAFE.sub("", text)[:columns]
        out.write(f"\x1b[{rows};1H\x1b[2K\x1b[2m{text}\x1b[0m".encode())
        out.flush()

    image_id = int.from_bytes(os.urandom(3)) | 1
    clear = f"\x1b_Ga=d,d=I,i={image_id},q=2\x1b\\".encode()
    out.write(b"\x1b[?1049h\x1b[?25l")
    try:
        while True:
            rows = terminal_size()[1]
            png, width, height = cache[index]
            out.write(clear + b"\x1b[H\x1b[2J")
            out.write(kitty_image(png, width, height, max(rows - 1, 1), image_id))
            hint = f"{items[index]['name']}  {index + 1}/{len(items)}"
            if len(items) > 1:
                hint += "  j/→ next  k/← previous"
            hint += "  ^D delete  q quit"

            say(hint)
            key = wait_key()
            if key in DELETE_KEYS:
                say(f"Delete {items[index]['name']} from sharei? y to confirm")
                if wait_key() not in (b"y", b"Y"):
                    continue
                try:
                    delete_item(items[index])
                except Abort as error:
                    say(f"{error}  any key")
                    wait_key()
                    continue
                del items[index]
                cache = {
                    position - (position > index): value
                    for position, value in cache.items()
                    if position != index
                }
                start = index - 1
                for offset in range(1, len(items) + 1):
                    candidate = (start + offset) % len(items)
                    if load(candidate):
                        index = candidate
                        break
                else:
                    break
                continue
            step = 1 if key in NEXT_KEYS else -1 if key in PREVIOUS_KEYS else 0
            if not step:
                break
            for offset in range(1, len(items)):
                candidate = (index + step * offset) % len(items)
                if load(candidate):
                    index = candidate
                    break
    finally:
        out.write(clear + b"\x1b[?25h\x1b[?1049l")
        out.flush()


def show_in_terminal(items: list[dict], index: int, data: bytes) -> bool:
    """Draw an image or print a text file; False when neither fits a terminal.
    On an interactive terminal images open in the full-screen browser."""
    image = as_png(data)
    if image and sys.stdin.isatty():
        browse(items, index, image)
        return True
    if image:
        sys.stdout.buffer.write(kitty_image(*image) + b"\n")
    elif b"\0" not in data[:65536]:
        try:
            text = TERMINAL_UNSAFE.sub("", data.decode())
        except UnicodeDecodeError:
            return False
        sys.stdout.write(text if text.endswith("\n") else text + "\n")
    else:
        return False
    sys.stdout.flush()
    return True


def get_file(
    kind: str, back: int, project: str, output: str | None, save: bool = True
) -> None:
    browsing = not save and not output and sys.stdout.isatty()
    items = recent(max(back + 1, BROWSE_MAX if browsing else 0), project)[kind]
    label = "dropped file" if kind == "drop" else "screenshot"
    if len(items) <= back:
        where = f" in {project}" if project else ""
        raise Abort(
            f"No {label}{where} {back} back." if back else f"No {label}{where}."
        )
    item = items[back]
    data = fetch(item["url"])
    if not save and not output:
        if not sys.stdout.isatty():
            output = "-"
        elif show_in_terminal(items, back, data):
            return
        else:
            print(f"{item['name']} can't be shown here, saving it.", file=sys.stderr)
    if output == "-":
        sys.stdout.buffer.write(data)
        sys.stdout.flush()
        return
    target = Path(output) if output else free_name(Path.cwd(), item["name"])
    if target.is_dir():
        target = free_name(target, item["name"])
    try:
        with target.open("xb") as stream:
            stream.write(data)
    except FileExistsError as error:
        raise Abort(f"{target} already exists.") from error
    print(f"Saved {item['project']}/{item['name']} to {target} ({human(len(data))})")


def get_list(limit: int, project: str) -> None:
    payload = recent(limit, project)
    clip = payload["clip"]
    if clip["chars"]:
        print(f"clip   {clip['chars']} chars, {ago(clip['age_seconds'])}")
    for entry in clip.get("history", []):
        print(f"clip {entry['n']} {entry['chars']} chars, {ago(entry['age_seconds'])}")
    for kind in ("drop", "shots"):
        for back, item in enumerate(payload[kind]):
            size = f"{human(item['bytes'])}, " if "bytes" in item else ""
            print(
                f"{kind[:4]} {back}  {item['project']}/{item['name']}  "
                f"{size}{ago(item['age_seconds'])}"
            )


def parse_get_args(argv: list[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        prog="sharec get",
        description="Fetch the shared clipboard, the newest dropped file or "
        "screenshot, or list what sharei holds.",
    )
    parser.add_argument(
        "what",
        nargs="?",
        choices=("clip", "drop", "shot", "list"),
        default="clip",
        help="what to fetch (default: clip)",
    )
    parser.add_argument(
        "back",
        nargs="?",
        type=int,
        default=0,
        metavar="N",
        help="how many steps back from the newest (default: 0, the newest); "
        "for list, how many items per kind (default: 5)",
    )
    parser.add_argument(
        "-c", "--copy", action="store_true", help="clip: put it on this clipboard"
    )
    where = parser.add_mutually_exclusive_group()
    where.add_argument(
        "-f",
        "--file",
        action="store_true",
        help="drop/shot: save to the current folder, never overwriting "
        "(default: show images and text in the terminal)",
    )
    where.add_argument(
        "-o",
        "--output",
        help="drop/shot: file or folder to save to, - for stdout",
    )
    parser.add_argument(
        "-p",
        "--project",
        default=os.environ.get("SHAREI_PROJECT", ""),
        help="drop/shot/list: only this project (default: $SHAREI_PROJECT)",
    )
    args = parser.parse_args(argv)
    if args.back < 0:
        parser.error("N must be 0 or more")
    if args.copy and args.what != "clip":
        parser.error("--copy only works with clip")
    if (args.output or args.file) and args.what not in ("drop", "shot"):
        parser.error("--file and --output only work with drop or shot")
    return args


def get_main(argv: list[str]) -> int:
    args = parse_get_args(argv)
    if args.what == "clip":
        get_clip(args.back, args.copy)
    elif args.what == "list":
        get_list(args.back or 5, args.project)
    else:
        get_file(
            "drop" if args.what == "drop" else "shots",
            args.back,
            args.project,
            args.output,
            save=args.file,
        )
    return 0


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
    if sys.argv[1:2] == ["get"]:
        return get_main(sys.argv[2:])
    args = parse_args()
    action = args.action or gum("choose", *ACTIONS)
    if not action:
        return 0
    if action == GET_CLIP:
        get_clip(0, copy=True)
        return 0
    if action == GET_DROP:
        get_file("drop", 0, args.project, None)
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
