from __future__ import annotations

import argparse
import html
import secrets
import socket
from http.server import ThreadingHTTPServer
from pathlib import Path
from urllib.parse import parse_qs, quote, unquote, urlsplit

from sharei import server
from sharei.themes import theme_script, theme_select

FILES = "/files/"
DIRECTORY_CSS = """
  .directory-list { list-style:none; padding:0; }
  .directory-list li { margin:0; border-bottom:1px solid var(--borderColor-muted); }
  .directory-list a { display:block; padding:14px 8px; overflow-wrap:anywhere; text-decoration:none; }
  .directory-list a:hover { background:var(--bgColor-muted); }
"""


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
        if (child.is_dir() or server.is_markdown(child.name)) and local_path(
            root, child.relative_to(root).as_posix()
        ) is not None:
            entries.append(child)
    entries.sort(key=lambda child: (not child.is_dir(), child.name.casefold()))
    rows = "".join(
        f'<li><a href="{html.escape(file_url(root, child))}">'
        f"{html.escape(child.name)}{'/' if child.is_dir() else ''}</a></li>"
        for child in entries
    )
    trail = " / ".join(
        f'<a href="{html.escape(url)}">{html.escape(label)}</a>'
        for label, url in breadcrumbs(root, path)
    )
    title = html.escape(path.name or str(path))
    nonce = secrets.token_urlsafe(16)
    content = (
        f'<ul class="directory-list">{rows}</ul>'
        if rows
        else "<p>No Markdown files or folders here.</p>"
    )
    body = f"""<!doctype html>
<html lang="en" data-theme-default="auto"><head><meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1, viewport-fit=cover">
<meta name="color-scheme" content="light dark"><title>{title} · aniflow</title>
<link rel="icon" href="data:,">{theme_script(nonce)}
<link rel="stylesheet" href="/vendor/github-markdown.css">
<style>{server.MARKDOWN_CSS}{server.READER_CSS}{server.THEME_READER_CSS}{DIRECTORY_CSS}</style>
</head><body><header class="bar"><a href="{FILES}">aniflow</a><span class="name">{title}</span>
<nav>{theme_select(nonce)}</nav></header><main class="page reader">
<nav class="crumbs" aria-label="Folders">{trail}</nav>
<section class="markdown-body"><h1>{title}</h1>{content}</section></main></body></html>"""
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
        if ":" in address[0]:
            self.address_family = socket.AF_INET6
        super().__init__(address, Handler)


class Handler(server.Handler):
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
                            [("Raw", file_url(root, path) + "?raw=1")],
                            crumbs=breadcrumbs(root, path),
                            local_root=FILES,
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
        if self.request_allowed():
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
