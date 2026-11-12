# sharei

A small self-hosted service to move things between a computer and a phone:
build artifacts from local repos, screenshots, dropped files, rendered
markdown, highlighted source and a throwaway clipboard. It has no login of its
own; it binds to 127.0.0.1 by default and is meant to sit behind a reverse
proxy with authentication (see SECURITY.md).

## Files

- `src/sharei/server.py`: the server (stdlib `http.server`; Pillow optional
  for thumbnails, pillow-heif optional for turning HEIC uploads into JPEG):
  settings, storage, the page builders, the request handler and `main`.
  Entry point `sharei` (`main`). HTML, CSS and JS are inline Python strings;
  there is no build step and no frontend toolchain. The static ones live in
  their own modules, which server.py imports by name:
  - `src/sharei/themes.py`: `THEMES`, `READER_THEMES` and the theme CSS/JS
  - `src/sharei/reader.py`: the markdown reader's CSS and `MARKDOWN_JS`
  - `src/sharei/assets.py`: CSS/JS for the app pages and the code, PDF and
    player viewers
  Code that reads a setting `main()` assigns (`ROOT`, `PUBLIC_URL`,
  `PUSH_ENABLED`, `QR_ENABLED`, `THEME_DEFAULT`...) stays in server.py, so
  tests can keep monkeypatching `server.*`.
- `src/sharei/push.py`: Web Push (RFC 8291 aes128gcm encryption, RFC 8292
  VAPID) on top of `cryptography`, the optional `push` extra. Without it
  `PUSH_ENABLED` stays false and every push route is a 404.
- `src/sharei/notes.py`: the read-only Obsidian vault behind the Notes tab
  (`[notes]` setting): config checks, the scanned index (refreshed in a
  background thread every `CACHE_SECONDS`), Obsidian link resolution and the
  per-note link map. `VAULT` is None without the setting.
- `src/sharei/client.py`: the CLI uploader, entry point `sharec` (`run`). It
  shares a screenshot, the clipboard, a markdown file with its local images,
  or any file. A FILE ending in `.md` or `.markdown` is shared as markdown,
  anything else as is. With no arguments it shows a `gum` menu.
  `sharec get [clip|drop|shot|list] [N]` reads back through `/clip/raw` and
  `/recent` (N is steps back from the newest) and never overwrites a file.
  `sharec get comments [NAME|N] [-p P] [--json]` prints a markdown drop's
  review comments from `/comments/...?format=prompt` (or the JSON). A name
  not among the 50 newest drops needs `-p`. `sharec FILE --replace` uploads
  with `replace=1` so a revised file keeps its name and comments.
  `sharec clip [TEXT|-] [--ttl S] [--clear]` writes `/clip`, `/clip/ttl` and
  `/clip/clear`; with `--ttl` and no TEXT only the expiry changes.
  `sharec get clip --json` prints `/clip/state` (the text and its history),
  `sharec notes [QUERY] [--json]` prints `/notes-search` or its `?q=` search
  through `client.payload()` (a result line starts with its kind, `note` or
  `file`), and `sharec cat PATH` prints the bytes of a server route, which is
  how `contrib/raffi/` reads notes and images.
  On a terminal, `drop`/`shot` draw images with the kitty graphics protocol
  (PNG as is, other raster formats through Pillow) on the alternate screen,
  sized to the window (`browse`: j/space/right and k/backspace/delete/left
  step through the last `BROWSE_MAX` items, wrapping and skipping
  non-images; D then D or y deletes the item through the server's delete
  routes; any other key quits), then delete the image by id
  (inline when stdin is not a terminal), and print text files with
  control characters stripped; anything else, `-f` or `-o` saves a file.
- `src/sharei/vendor/`: third-party assets served at `/vendor/`:
  github-markdown-css, markdown-it with its footnote and emoji plugins and
  DOMPurify (the `/md` renderer, `MARKDOWN_SCRIPTS`), mermaid, markerjs,
  highlight.js (common languages
  bundle), qrcode-generator (`qrcode.js`, loaded lazily by `QR_JS`, which
  every page includes through `qr_script()`; `[data-qr]` buttons open it,
  an empty value meaning the current page, and loopback URLs are rebased on
  `public_url`; with `qr = false`, `QR_ENABLED` drops the buttons, the
  script and the `qrcode.js` route), pdf.js (`pdf.min.mjs` and `pdf.worker.min.mjs`, the
  modern build of pdfjs-dist, Apache-2.0). Keep their licence files next to them;
  they ship in the wheel. marker.js is linkware: its credit line under the
  editor must stay visible.
- `src/sharei/icons/`: diagram icons served at `/icons/<name>.svg`, 48×48
  tiles built from Lucide (ISC, `LICENSE.lucide`) by
  `contrib/icons/make_icons.py`, which holds the name, glyph and colour
  table. Regenerate rather than edit: `npm pack lucide-static`, unpack, then
  `python contrib/icons/make_icons.py <package> src/sharei/icons`.
- `contrib/_sharec`: zsh completion. `contrib/sharei.service`: systemd user
  unit, expecting `~/.local/bin/sharei` from `uv tool install`.
- `contrib/raffi/`: a raffi script filter (`sharei_filter.py`) listing the
  notes, clipboard, drops and shots as views of one keyword. It only calls
  `sharec`, so it holds no address or login logic of its own.
- `contrib/skills/sharei/SKILL.md`: an agent skill for using sharei through
  `sharec` (reading shares, handing over `/md` documents, walkthrough
  diagrams with pictures). Keep it free of personal hosts and logins, and
  update it when `sharec` flags or the diagram syntax change.
- `config.example.toml`: every setting, with comments. Keep it in sync when you
  add a setting.
- `tests/`: pytest. `conftest.py` has a `live_server` fixture that runs the
  real handler on a random port against a temporary root.
- `README.md` is for users, in plain language with screenshots from
  `docs/screenshots/`. Keep internals out of it; they belong here.

For development, `uv tool install -e .` makes edits live after a restart of
the service.

## Data layout

- Root: `~/tmp/sharei` (`root` setting or `--root`).
  - `<root>/<project>/shots/**`: screenshots
  - `<root>/<project>/drop/*`: dropped files
  - `<root>/<project>/drop/.comments/<name>.json`: review comments on a
    markdown drop, a list of `{id, start, end, quote, body, created,
    updated}`; `quote` holds the source lines when the comment was written
  - `<root>/.expiry.json`: expiries set from the UI, mapping a path relative
    to the root to an epoch
- Project names must match `[A-Za-z0-9][A-Za-z0-9._-]{0,63}`. The default
  project is `inbox`.
- Cache: `~/.cache/sharei` (`$XDG_CACHE_HOME/sharei`). It holds `clip.json`
  (current text plus the last `CLIP_HISTORY_MAX` replaced ones, each keeping
  the TTL it had; Clear does not archive),
  `thumbs/` and `push/` (`vapid.pem` and
  `subs.json`, both 0600).
- Notes: the `[notes]` vault is only read, never written. Its
  `.obsidian/app.json` gives `strictLineBreaks` and `userIgnoreFilters`.
- Settings: `~/.config/sharei/config.toml`, or `$SHAREI_CONFIG`, or
  `--config`. Command-line flags take priority over the file.
- The systemd unit can only write under `~/tmp`. Don't move the root elsewhere
  without widening `ReadWritePaths`.

## Routes

Pages:

- `/`: redirects to `/shots`
- `/artifacts`: Artifacts, from the `[[artifacts]]` config entries
- `/shots`: screenshots
- `/clip`: clipboard
- `/drop`: dropped files
- `/md/<project>/<name>`: a dropped markdown file, rendered in the browser.
  The page carries the text as an escaped JSON block; `MARKDOWN_JS` renders
  it with markdown-it, writes GitHub's markup for task lists, alerts, tables,
  footnotes and code (`div.highlight.highlight-source-<lang>`, which the
  mermaid step looks for) so github-markdown.css styles it, then sanitizes
  with DOMPurify.
  `READER_CSS` styles the result on top of github-markdown.css, scoped under
  `.reader` so it wins on specificity. The page frames code blocks with a
  copy button, turns the contents into a sticky side rail from 1240px that
  follows the section being read, draws a progress line under the bar, and
  colours mermaid's base theme from the page's CSS variables.
  `panZoom()` gives each diagram drag to pan, Ctrl/Cmd+wheel or pinch to
  zoom and a full-screen `<dialog>` by rewriting the SVG's `viewBox`, so
  it stays sharp and its box never resizes. A one-finger touch at the
  fitted size is left to page scrolling.
  A flowchart's `%% play: title`, `%% A -> B : label` and `%% skip A B`
  comment lines are read from the source by `playScript()` (mermaid drops
  them) and played by `playDiagram()`: steps resolve to `g.node` ids
  (`<svg>-flowchart-<id>-<n>`) and `path[data-edge]` `data-id`s
  (`L_<from>_<to>_<n>`, walked backwards when only `B -> A` exists), a
  token moves along `getPointAtLength`, and state is `play-*` classes on the
  SVG. Step mode stops at segments flagged `stop` (one per step) and goes
  back by replaying instantly with `advance(Infinity, true)`; its key
  handler (arrows, j/k, Space, PageUp/PageDown) runs before panZoom's so a
  plain arrow steps and Shift+arrow pans.
  Labels are set with `textContent`. Unresolved steps are dropped and
  listed in the Play button's title. Picture nodes (`@{ img: ... }`) render
  as `g.image-shape` rather than `g.node`, so play styles and badges cover
  both. Before rendering, `diagramImages()` rewrites each `img:` value:
  local names go through `local()` to `/poub/`, https, same-origin paths
  and `data:image/` stay, anything else becomes `DIAGRAM_IMAGE_MISSING`.
  Each picture is preloaded with a timeout, because one failed load makes
  mermaid reject the whole diagram; failures get the placeholder and are
  listed in the diagram's title. `sharec` scans `img:` values in mermaid
  fences (`mermaid_blocks()`) with the same checks as markdown images, and
  leaves `/icons/` paths alone.
  `focusDiagram()` makes flowchart boxes clickable: it maps edges to their
  ends from `L_<from>_<to>_<n>` against the known node ids, and sets
  `focus-on`/`focus-near` with `.focusing` on the stage. Pointer capture
  makes the stage the click target, so it hit-tests with
  `elementFromPoint()` and node bounding boxes. Playback and the spotlight
  share `diagramBusy()` to pause the live reload.
  The record button saves a story client-side: `diagramCanvas()` draws a
  clone of the SVG with computed styles inlined and every `<image>` turned
  into a data URL (`diagramImageData()`, same-origin fetch only, since an
  SVG drawn as an image loads nothing external) at the home viewBox. GIF
  steps the timeline offline with `advance(60)` under `.recording` (no
  transitions or glow) and encodes with the built-in `gifWriter()`; video
  plays in real time into `captureStream()` and `MediaRecorder`
  (`diagramVideoType()`). The page CSP blocks `blob:` images, so frames go
  through `data:` URLs.
  `docs/diagram-walkthroughs.md` is the design spec and a live demo, with
  its icons in `docs/diagram-icons/`.
  Linkify ignores scheme-less links so `README.md` stays text.
  YAML front matter at line 1 (closed by `---` or `...` within 200 lines,
  with at least one `key:`) is claimed by the `sharei_frontmatter` block
  rule and drawn by `frontPanel()` as a `dl.frontmatter` properties panel
  covering its lines.
  A `sharei_lines` core rule copies markdown-it's `token.map` onto blocks as
  `data-line`/`data-line-end` (1-based, inclusive; a tight list item takes
  its hidden paragraph's range) and `data-code` on code blocks. The review
  button (`REVIEW_BUTTON`, `REVIEW_DOCK`) turns on a line gutter built from
  those attributes. Picking lines (shift-click, or a second tap on touch) sets
  `#Lx-Ly`, which also opens review on load. Comments are fetched from and
  posted to `data-comments` and drawn with `textContent`. On read,
  `comment_anchor()` keeps a comment whose lines still equal its `quote`,
  moves it to the single other place the quote appears, or marks it
  `outdated` at its clamped range.
- `/view/<project>/<name>`: a dropped text file with line numbers and
  highlight.js. A file counts as text when it is at most 2 MB, valid UTF-8 and
  has no NUL bytes (`looks_like_text`, `read_text_file`). Highlighting is
  skipped above 512 KB. Anything else returns 404 and downloads from `/poub`.
- `/play/<project>/<name>`: a dropped video (`VIDEO_SUFFIXES`) or audio
  file (`AUDIO_TYPES`) in the browser's player, under a nonce-only CSP with
  `media-src 'self'`
- `/pdf/<project>/<name>`: a dropped PDF drawn by pdf.js on canvases. The
  CSP keeps `script-src` nonce-only (module imports inherit the nonce) and
  allows `worker-src 'self'` and `connect-src 'self'` for the worker and
  the fetch of `/poub`
- `/clip/md`: the clipboard, rendered as markdown
- `/notes`, `/notes/<folder>/`: the shared vault folders, with a client-side
  name filter (`NOTES_JS`) over the whole tree, newest first (folders by their
  newest note) with a toggle to A to Z kept in localStorage `sharei-notes-sort`
- `/notes/<path>`: a note in the `/md` reader with breadcrumbs and no
  review, Raw or comments; a text file in the `/view` page; any other
  file as a download, like `/notes-file`. The page
  embeds `notes.link_map()` as `#notes-links`, and `obsidianFlavour()` in
  `MARKDOWN_JS` uses it for wikilinks, embeds and standard links (a null
  target becomes `.note-missing` text), plus `==mark==`, inline `#tags`,
  `%%comments%%`, and any callout type with `-`/`+` folding as `<details>`
- `/notes-pdf/<path>`: a vault PDF in the pdf.js page

Every page also carries the notes picker when a vault is set
(`search_button()`, `search_script()`, `SEARCH_JS`/`SEARCH_CSS` in
`assets.py`): `/` (outside a field) or Ctrl/Cmd+K opens a `<dialog>`. Names
mode fetches `/notes-search` once and ranks it on the client (fzf-like:
substrings on a word boundary first, a match in the name beats one in the
folders). Text mode queries `/notes-search?q=` with a debounce. Tab switches
mode, kept in localStorage `sharei-search-mode`. Both fold case and accents
the same way (NFKD, combining marks dropped). A text hit links to
`/notes/<path>#find=<line>:<words>`; `findLine()` in `MARKDOWN_JS` scrolls to
the innermost `data-line` block and wraps the words in `mark.find-hit`.
Pages with `default-src 'none'` (`/view`, `/play`, `/pdf`) allow
`connect-src 'self'` for that fetch.

Files:

- `/notes-file/<path>`: vault bytes, with the same inline/attachment and
  SVG rules as `/poub` (`send_shared_file`)
- `/notes-icon/<name>`: an Icon Fairy icon image (`notes.scan_icons()`),
  shown on rows, folder titles and the reader trail
- `/shot/<key>`, `/thumb/<key>`: an SVG is served as itself, since Pillow cannot
  rasterise one, so `/thumb` has nothing to cache for it. `/thumb` also takes a
  dropped image (`/thumb/<project>/<name>`), thumbnailed whole-frame (`style`
  `fit`) where a shot keeps the top 9:16 of its page (`top`), both cached and
  keyed by style; the Drop grid and `/recent` (`thumb`) use it.
- `/poub/<project>/<name>`: `?raw` serves text files inline as `text/plain`
  Images, videos and audio are served inline, everything else as an
  attachment. An SVG counts as an image (`IMAGE_LIKE_SUFFIXES`) and is served
  inline as `image/svg+xml` under the `sandbox` CSP, because opened in a tab it
  is a document that can carry scripts.
  `send_file` answers a single `Range` with 206, so players can seek.
- `/download/...` for APKs
- `/vendor/...`
- `/icons/<name>.svg`: a built-in diagram icon, looked up by name in
  `ICON_NAMES` (read from the folder at import), never joined from the
  request, and served with `vector_headers`. `/icons/` lists the names as
  JSON.

Data:

- `/state`: stamps for the live reload
- `/recent`: newest items as JSON with the server's `public_url`, used by the
  skill
- `/sw.js` (service worker), `/push/key` (VAPID public key): push only
- `/notes-search`: every shared note, folder and file for the picker,
  `{items: [{p, k, h, t, i}]}` (path, kind, link, mtime, icon), rebuilt per
  vault scan (`notes_entries()`). With `?q=`, a full-text search over the
  shared markdown notes (`notes.search()`): every word must appear in the
  text or the path: the markdown notes first, with up to `SEARCH_HITS_PER_NOTE`
  lines each (`notes.search()`), then the other shared files and the folders
  whose name matches (`name_matches()`), `hits: []` and their `k`, newest
  first, up to `SEARCH_NOTES_MAX` results in all. Folded texts are cached by
  mtime and size up to `SEARCH_CACHE_MAX_CHARS`. 404 without a vault.
- `/clip/raw[?n=]`: the clip, or history entry n (1 is the newest), `/clip/state`
- `/comments/<project>/<name>`: `{name, lines, comments}` for a markdown
  drop, or `?format=prompt` for the text `sharec get comments` prints

POST:

- `/upload?project=&name=`: raw body. Collisions are renamed `name-1.ext`.
  A HEIC/HEIF body, recognised by suffix or by its `ftyp` brand, is rewritten
  as JPEG (PNG when the image has alpha) with `convert_heic_upload()` before
  it is published, so the name that comes back carries the new suffix.
  `replace=1` overwrites an existing visible file of that name in place
  (`replace_poub()`, keeping its expiry and comments) and adds
  `"replaced": true`; with no such file it is a normal upload.
  Returns `{project, name, size, url, view?}`.
- `/share`: Android share target, converting HEIC the same way
- `/annotate`
- `/expiry?target=poub|shot&key=&seconds=`: `0` clears, maximum 30 days
- `/clip`, `/clip/clear`, `/clip/ttl`
- `/push/subscribe`, `/push/unsubscribe`: push only, JSON subscription body
- `/clip/history/restore?id=`, `/clip/history/delete?id=`, `/clip/history/clear`
- `/shots/delete/<key>`, `/shots/delete-all[?project=]`
- `/poub/delete/<project>/<name>`, `/poub/delete-all[?project=]`
- `/comments/add/<project>/<name>` (JSON `{start, end, body}`),
  `/comments/edit/...?id=` (`{body}`), `/comments/delete/...?id=`: return
  the comments view. Limits: `COMMENTS_MAX` per file, `COMMENT_MAX_CHARS`,
  `COMMENT_MAX_LINES` quoted

"poub" is the internal name for the drop folder.

## Security rules

These exist on purpose. Keep them when changing or adding code.

- Every request goes through `request_allowed()`. It checks the Host header
  (local names, non-global IPs and `allow_hosts`) and, for POSTs, the Origin
  (same origin or `allow_origins`). New routes must stay inside `do_GET` or
  `do_POST` after that check.
- Resolve user-supplied paths only through `shot_path()` / `poub_path()`, or
  the same pattern: `resolve()`, then `relative_to(ROOT)`, plus
  `under_root()`. Hidden names (leading `.`) are never listed or served.
- Expired files must return None from those helpers, so every route returns
  404 before the sweeper deletes them. A delete or a publish under the same
  name must call `expiry_forget()` so a new file never inherits an old expiry.
- Uploads are written to `.part-*` and published with a hard link (no
  overwrite). The limit is `UPLOAD_MAX_BYTES`. Only `replace=1` overwrites,
  with `os.replace`, and only a regular non-hidden file already in that
  drop folder.
- Comments live in the hidden `.comments` folder, so no route lists or
  serves it. Their file is found through `poub_path()` (markdown only), so
  an expired or missing file has none, and every delete, sweep or new
  publish under the name calls `comments_forget()`. Comment text is
  rendered with `textContent`, never as HTML.
- Artifacts: `/download/<key>` only serves a path found by the last scan
  (`available_artifacts()`), never a path from the request. The scanner
  (`artifact_files`) keeps only regular files whose resolved path stays
  inside the checkout, skips hidden parts, `node_modules`, `__pycache__` and
  `venv`, caps visits per walk (`ARTIFACT_MAX_VISITS`) and files per repo
  (`ARTIFACT_MAX_FILES`). Config patterns must be relative with no `.`/`..`
  parts. Scans run in a background thread and are cached
  (`ARTIFACT_CACHE_SECONDS`); a page waits at most `ARTIFACT_FIRST_WAIT`.
  A glob root only picks git repos whose `.git` is a folder, so linked
  worktrees appear once, under their main checkout.
- `/md` pages use a nonce-based CSP. The markdown and any raw HTML in it are
  untrusted: everything markdown-it produces goes through DOMPurify (no
  `style`, forms or event handlers) before it reaches the page, and the
  source is embedded with `<`, `>` and `&` escaped so it cannot close its
  `<script>` block. Don't add inline handlers or unnonced scripts there. `/view`
  pages use a nonce-only `script-src` (no `'self'`, so an uploaded `.js` can
  never run) and the file text is HTML-escaped on the server.
- An SVG is an image inside an `<img>` and a document with scripts in a tab,
  so `/poub`, `/shot`, `/thumb` and `/icons` serve one with `vector_headers`, which adds
  a `sandbox` Content-Security-Policy. Keep that on any new route that returns
  a vector, and keep SVG out of `ANNOTATE_TYPES`: a canvas will not take it.
- Push sends outbound requests only to subscription endpoints that pass
  `push.endpoint_allowed()`: https, port 443, a hostname (no IP literal, no
  userinfo) whose every address is global. Redirects are never followed, at
  most `PUSH_SUBS_MAX` subscriptions are kept, and 404/410 drops one. The
  `sharei-push` cookie (HttpOnly, SameSite=Strict) only names the sender's
  own subscription so it is skipped; it grants nothing. The service worker's
  notification click opens same-origin URLs only.
- Notes never join a request path onto the vault. `notes.allowed()` looks
  the exact key up in the scanned index and serves it only when it is under
  a configured folder or is an attachment a shared note links to. The scan
  skips hidden parts, symlinks and `userIgnoreFilters` paths; links inside
  code and `%%comments%%` grant nothing. Everything else is a 404,
  unshared notes included. The one thing read under `.obsidian` is the
  Icon Fairy plugin, when enabled: `/notes-icon` serves only the
  `icons/<id>.<ext>` files that a shared note or folder uses, by name,
  regular files up to `ICON_MAX_BYTES`.
- `sharec` checks a markdown file's local images before uploading them:
  - inside the git toplevel, or the file's directory, checked after realpath
  - no hidden path parts and no symlink escapes
  - an image extension and matching magic bytes
  - size limits per image and in total
  - a confirmation prompt
  Loosening any of these needs a good reason.

## Conventions

- Python 3.12+, stdlib first. Pillow and pillow-heif are the only optional
  imports, loaded lazily behind `heif_available()` and `render_thumbnail()`,
  so everything keeps working without them. Don't add runtime dependencies.
- Format and lint with `ruff format` and `ruff check`. `subprocess.run` needs
  an explicit `check=`.
- The UI is mobile first: a bottom tab bar on phones, a left rail from 900px
  wide. Reuse the existing CSS classes and patterns, such as `.clip-ttl`-style pills and absolutely positioned row
  tools. Pages reload themselves when the `/state` stamp changes.
  `window.liveBusy()` pauses that while a viewer or menu is open. The
  screenshot viewer pages on a left/right tap like a book (a middle tap closes
  it), and keeps swipe and the arrow keys working.
- Sharing out of the browser goes through `SHARE_JS` (`window.shareiShare`):
  the file bytes when `navigator.canShare({files})` allows it, else the URL,
  else a plain download. Any button with `data-share` and `data-name` is
  wired by it and stays `hidden` where the browser has no `navigator.share`,
  so a desktop without the API shows no half-broken button.
- Colours always come from CSS variables, never literals. A theme is an
  entry in `THEMES` (the `THEME_KEYS` palette plus `light` or `dark` mode),
  and every theme besides light and dark also needs a `READER_THEMES`
  entry that overrides GitHub's markdown and syntax variables for `/md`
  and `/view`.
  `theme_reader_css()` lifts GitHub's light and dark variables out of the
  vendored `github-markdown.css` media queries and keys them on
  `html[data-mode]`; a test guards that extraction. `THEME_JS` runs in the
  head of every page (with the nonce on `/md` and `/view`), reads the choice
  from localStorage `sharei-theme`, falls back to the `theme` setting, and
  sets `data-theme` and `data-mode` on `<html>`.
- `sharec` uses `gum` for menus and prompts, and `yazi` when present to
  pick files. Its environment variables:
  - `SHAREI_URL`: server for every request. Unset, `target()` uses
    `http://localhost:8000`, or `SHAREI_PUBLIC_URL` when that is set and
    nothing listens on port 8000.
  - `SHAREI_PUBLIC_URL`: base for printed links, default `SHAREI_URL`
  - `SHAREI_PROJECT`: default project. Uploads otherwise use the current
    git repository's name (`repo_project()`), then the server's default.
  - `SHAREI_PASS_ENTRY`: pass entry for basic auth on https servers
    (password on line 1, optional `user:` line). Without it `~/.netrc` is
    read. All requests go through `request()`, which sends the header
    unredirected so a redirect cannot carry it to another host.

## Testing

Run `uv run pytest`, `uv run ruff format .` and `uv run ruff check .`; CI runs
the same on Python 3.12 to 3.14. Add tests for new behaviour, preferably
through the `live_server` fixture. `.pre-commit-config.yaml` runs the same
three checks at the pre-push stage (`uvx pre-commit install --hook-type
pre-push`), never at commit time.

For manual checks use a throwaway instance, never a live one:

```sh
XDG_CACHE_HOME=/tmp/x/cache XDG_CONFIG_HOME=/tmp/x/cfg \
  uv run sharei --port 8791 --root /tmp/x/root
```

Exercise the routes with `curl`, including the 400/403/404 cases. For UI
changes, load the pages in headless Chrome:

```sh
google-chrome-stable --headless=new --window-size=430,900 --screenshot=out.png URL
```

If you need clicks, drive Chrome over CDP. Check the console for errors and
CSP violations.

For `sharec`, point `SHAREI_URL` at the throwaway server.

## Running

The service is `systemctl --user restart sharei`. Restart only when asked,
since it drops the in-memory state of open pages.
