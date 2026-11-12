from __future__ import annotations

import argparse
import hashlib
import html
import os
import secrets
import socket
from datetime import UTC, datetime
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from sharei import server
from sharei.aniflow_brand import BRAND, BRAND_CSS
from sharei.aniflow_ui import DIRECTORY_CSS, UI_CSS, UI_JS
from sharei.themes import theme_script, theme_select

FILES = "/files/"
HELP = Path(__file__).with_name("aniflow-help.md")
NEXT_ICON = '<svg viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="1.6" stroke-linecap="round" stroke-linejoin="round" aria-hidden="true"><path d="M5 12h14m-6-6 6 6-6 6"/></svg>'


def local_path(root: Path, key: str) -> Path | None:
    relative = Path(key)
    if relative.is_absolute() or "\\" in key or "\x00" in key:
        return None
    if any(part.startswith(".") for part in relative.parts):
        return None
    path = root / relative
    try:
        resolved = path.resolve().relative_to(root)
        if any(part.startswith(".") for part in resolved.parts):
            return None
        return path if path.is_file() or path.is_dir() else None
    except (OSError, ValueError, RuntimeError):
        return None


def file_url(root: Path, path: Path) -> str:
    relative = path.relative_to(root).as_posix()
    if relative == ".":
        return FILES
    return FILES + quote(relative) + ("/" if path.is_dir() else "")


def breadcrumbs(root: Path, path: Path) -> list[tuple[str, str]]:
    return [
        (
            root.name if parent == Path(".") else parent.name,
            file_url(root, root / parent),
        )
        for parent in reversed(path.relative_to(root).parents)
    ]


def directory_page(root: Path, path: Path) -> tuple[bytes, str]:
    entries = []
    for child in path.iterdir():
        try:
            folder = child.is_dir()
            if not folder and not server.is_markdown(child.name):
                continue
            if local_path(root, child.relative_to(root).as_posix()) is not None:
                entries.append((child, folder, child.stat()))
        except OSError:
            continue
    entries.sort(key=lambda entry: (not entry[1], entry[0].name.casefold()))
    folder_rows, document_rows = [], []
    for child, folder, stat in entries:
        name = html.escape(child.name)
        link = f'<a href="{html.escape(file_url(root, child))}" data-name="{name}">'
        attributes = f'data-modified="{stat.st_mtime}"'
        if folder:
            folder_rows.append(
                f'<li {attributes}>{link}<span class="folder-symbol" aria-hidden="true">{server.FOLDER_ICON}</span>'
                f'<span class="file-label">{name}</span><span class="entry-arrow">{NEXT_ICON}</span></a></li>'
            )
        else:
            modified = datetime.fromtimestamp(stat.st_mtime, UTC)
            document_rows.append(
                f'<li {attributes}>{link}<span class="document-symbol" aria-hidden="true">{server.NOTE_ICON}</span>'
                f'<span class="file-label">{html.escape(child.stem)}<span class="file-extension">{html.escape(child.suffix)}</span></span>'
                f'<time datetime="{modified.isoformat()}" class="file-modified">{modified.strftime("%d %b %Y")}</time>'
                f'<span class="file-size">{server.human_size(stat.st_size)}</span>'
                f'<span class="entry-arrow">{NEXT_ICON}</span></a></li>'
            )
    folders, documents = len(folder_rows), len(document_rows)
    groups = "".join(
        f'<section class="directory-group" aria-labelledby="{kind}-heading">'
        f'<h2 id="{kind}-heading">{label}<span class="group-count">{len(rows)}</span></h2>'
        + (
            '<div class="directory-columns" aria-hidden="true"><span>Document</span><span>Modified</span><span>Size</span></div>'
            if kind == "documents"
            else ""
        )
        + f'<ul class="directory-list {kind}-list">{"".join(rows)}</ul></section>'
        for kind, label, rows in (
            ("folders", "Folders", folder_rows),
            ("documents", "Documents", document_rows),
        )
        if rows
    )
    ancestors = breadcrumbs(root, path)
    trail = "".join(
        f'<li><a href="{html.escape(url)}">{html.escape("Files" if url == FILES else label)}</a></li>'
        for label, url in ancestors
    )
    title = html.escape(path.name or str(path))
    trail += f'<li aria-current="page">{title if ancestors else "Files"}</li>'
    parent = (
        f'<a class="folder-up" href="{html.escape(file_url(root, path.parent))}">{NEXT_ICON}Up one folder</a>'
        if path != root
        else ""
    )
    nonce = secrets.token_urlsafe(16)
    content = (
        f'<div class="browser-toolbar"><label class="folder-filter">{server.SEARCH_ICON}'
        '<span class="sr-only">Find in this folder</span>'
        '<input type="search" id="folder-search" placeholder="Find a file or folder…" autocomplete="off" aria-controls="directory-groups"></label>'
        '<label class="folder-sort"><span>Sort by</span><select id="folder-sort">'
        '<option value="name">Name</option><option value="modified">Last modified</option></select></label></div>'
        '<p class="folder-status sr-only" id="folder-status" role="status"></p>'
        f'<div id="directory-groups">{groups}</div>'
        '<div class="browser-empty" id="folder-no-results" hidden><span class="empty-symbol" aria-hidden="true">'
        f"{server.SEARCH_ICON}</span><h2>No matches in this folder</h2>"
        "<p>Try a shorter name, or clear the search to see everything.</p>"
        '<button type="button" id="folder-clear">Clear search</button></div>'
        if entries
        else f'<div class="browser-empty"><span class="empty-symbol" aria-hidden="true">{server.FOLDER_ICON}</span>'
        "<h2>No Markdown files or folders here.</h2><p>Save a .md file in this folder, then refresh to open it.</p>"
        '<a href="/help">Try the demo while you’re here</a></div>'
    )
    description = f'{folders} {"folder" if folders == 1 else "folders"} <span aria-hidden="true">/</span> {documents} {"document" if documents == 1 else "documents"}'
    body = f"""<!doctype html>
<html lang="en" data-theme-default="auto"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{title} · aniflow</title>
<link rel="icon" href="data:,">{theme_script(nonce)}
<link rel="stylesheet" href="/vendor/github-markdown.css">
<style>{server.MARKDOWN_CSS}{server.THEME_READER_CSS}{BRAND_CSS}{UI_CSS}{DIRECTORY_CSS}</style>
</head><body class="aniflow-local aniflow-browser"><header class="bar"><a href="{FILES}">aniflow</a><span class="name">{title}</span>
<nav><a href="/help">Demo &amp; help</a>{theme_select(nonce)}</nav></header>
<main class="browser-shell"><div class="browser-masthead">{BRAND}
<a class="browser-demo" href="/help"><span class="demo-play" aria-hidden="true"></span>
<span><strong>Try animated diagrams</strong><span>Play the demo, then make your own.</span></span>{NEXT_ICON}</a></div>
<nav class="browser-trail" aria-label="Folders"><ol>{trail}</ol></nav>
<div class="browser-heading"><div><h1>{title}</h1><p class="folder-summary">{description}</p></div>{parent}</div>
{content}</main><script nonce="{nonce}">{UI_JS}</script></body></html>"""
    return body.encode("utf-8"), nonce


def page_headers(nonce: str) -> dict[str, str]:
    headers = server.markdown_headers(nonce)
    headers["Content-Security-Policy"] = headers["Content-Security-Policy"].replace(
        "script-src 'self' ", "script-src "
    )
    return headers


class Server(ThreadingHTTPServer):
    def __init__(self, address: tuple[str, int], root: Path):
        self.root = root.resolve()
        identity = hashlib.sha256(os.fsencode(self.root)).hexdigest()
        cache = Path(os.environ.get("XDG_CACHE_HOME", Path.home() / ".cache"))
        self.comments_root = cache / "aniflow" / "comments" / identity
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, Handler)


class Handler(server.Handler):
    def comment_target(self, key: str) -> tuple[Path, Path] | None:
        if key == "help":
            path, identity = HELP, "help"
        elif key.startswith("file/"):
            path = local_path(self.server.root, unquote(key.removeprefix("file/")))
            if path is None or not path.is_file() or not server.is_markdown(path.name):
                return None
            identity = "file/" + path.resolve().relative_to(self.server.root).as_posix()
        else:
            return None
        digest = hashlib.sha256(identity.encode("utf-8")).hexdigest()
        return path, self.server.comments_root / f"{digest}.json"

    def do_GET(self) -> None:
        if not self.request_allowed():
            return
        parsed = urlsplit(self.path)
        raw = "raw" in parse_qs(parsed.query, keep_blank_values=True)
        if parsed.path == "/":
            self.send_response(302)
            self.send_header("Location", FILES)
            self.end_headers()
            return
        if parsed.path == "/help":
            if raw:
                self.send_file(
                    HELP,
                    "text/plain; charset=utf-8",
                    {"Cache-Control": "no-cache", "X-Content-Type-Options": "nosniff"},
                )
            else:
                body, nonce = server.markdown_page(
                    "aniflow help",
                    HELP.read_text("utf-8"),
                    None,
                    ("Files", FILES),
                    [("Raw", "/help?raw=1")],
                    local_root="/",
                    comments="/comments/help",
                )
                self.send_html(body, page_headers(nonce))
            return
        if parsed.path.startswith("/comments/"):
            target = self.comment_target(parsed.path.removeprefix("/comments/"))
            if target is None:
                self.send_json({"error": "not found"}, status=404)
                return
            path, storage = target
            try:
                view = server.comments_view(path, storage=storage)
            except OSError:
                self.send_json({"error": "Could not read comments"}, status=500)
                return
            if (parse_qs(parsed.query).get("format") or [""])[-1] == "prompt":
                self.send_bytes(
                    server.comments_prompt(view, "aniflow").encode("utf-8"),
                    "text/plain; charset=utf-8",
                    {"Cache-Control": "no-store", "X-Content-Type-Options": "nosniff"},
                )
            else:
                self.send_json(view)
            return
        if parsed.path.startswith("/vendor/"):
            name = parsed.path.removeprefix("/vendor/")
            if name in (
                *server.MARKDOWN_SCRIPTS,
                "github-markdown.css",
                "mermaid.min.js",
            ):
                self.send_file(server.VENDOR / name, server.VENDOR_TYPES[name], {})
                return
        if parsed.path.startswith("/icons/"):
            if parsed.path == "/icons/":
                self.send_json({"icons": sorted(server.ICON_NAMES)})
                return
            name = parsed.path.removeprefix("/icons/").removesuffix(".svg")
            if name in server.ICON_NAMES and parsed.path.endswith(".svg"):
                self.send_file(
                    server.ICONS_DIR / f"{name}.svg",
                    "image/svg+xml",
                    server.vector_headers({}),
                )
                return
        if parsed.path.startswith(FILES):
            root = self.server.root
            path = local_path(root, unquote(parsed.path.removeprefix(FILES)))
            if path is not None:
                try:
                    if path.is_dir():
                        if not parsed.path.endswith("/"):
                            self.send_response(302)
                            self.send_header("Location", file_url(root, path))
                            self.end_headers()
                            return
                        body, nonce = directory_page(root, path)
                    elif server.is_markdown(path.name) and not raw:
                        body, nonce = server.markdown_page(
                            path.name,
                            path.read_text("utf-8", errors="replace"),
                            None,
                            (
                                "Files",
                                file_url(root, path.parent),
                            ),
                            [
                                ("Help", "/help"),
                                ("Raw", file_url(root, path) + "?raw=1"),
                            ],
                            crumbs=breadcrumbs(root, path),
                            local_root=FILES,
                            comments="/comments/file/"
                            + quote(path.relative_to(root).as_posix()),
                        )
                    else:
                        self.send_shared_file(path, raw=raw)
                        return
                    self.send_html(body, page_headers(nonce))
                    return
                except OSError:
                    pass
        self.send_error(404)

    def do_POST(self) -> None:
        if not self.request_allowed():
            return
        parsed = urlsplit(self.path)
        if parsed.path.startswith("/comments/"):
            _, _, key = parsed.path.removeprefix("/comments/").partition("/")
            target = self.comment_target(key)
            if target is None:
                self.send_json({"error": "not found"}, status=404)
                return
            path, storage = target
            self.handle_comment(parsed, path=path, storage=storage)
            return
        self.send_response(405)
        self.send_header("Allow", "GET")
        self.send_header("Content-Length", "0")
        self.end_headers()


def main() -> None:
    parser = argparse.ArgumentParser(
        description="Browse local Markdown and interactive flowcharts."
    )
    parser.add_argument(
        "directory",
        nargs="?",
        type=Path,
        default=Path.cwd(),
        help="directory to serve (default: current directory)",
    )
    parser.add_argument(
        "--host", default="127.0.0.1", help="address to bind (default: 127.0.0.1)"
    )
    parser.add_argument(
        "--port",
        type=int,
        default=0,
        help="port to listen on (default: an available port)",
    )
    args = parser.parse_args()
    if not args.directory.is_dir():
        parser.error(f"not a directory: {args.directory}")
    try:
        httpd = Server((args.host, args.port), args.directory)
    except (OSError, OverflowError) as error:
        parser.error(str(error))
    host = f"[{args.host}]" if ":" in args.host else args.host
    print(
        f"aniflow: serving {httpd.root} at http://{host}:{httpd.server_address[1]}",
        flush=True,
    )
    try:
        httpd.serve_forever()
    except KeyboardInterrupt:
        pass
    finally:
        httpd.server_close()


if __name__ == "__main__":
    main()
