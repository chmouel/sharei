# sharei in raffi

A [raffi](https://github.com/chmouel/raffi) script filter for sharei: type a
keyword in raffi and search the Obsidian notes sharei serves, put back
something from the shared clipboard, or open a dropped file or a screenshot.

## Install

The filter is a single script that talks to sharei through `sharec`, so
[install sharei with its CLI](../..) first and copy the script somewhere
raffi can run it:

```sh
mkdir -p ~/.config/raffi/scripts/sharei
cp sharei_filter.py ~/.config/raffi/scripts/sharei/sharei_filter.py
chmod +x ~/.config/raffi/scripts/sharei/sharei_filter.py
```

Then add it to `~/.config/raffi/raffi.yaml`:

```yaml
addons:
  script_filters:
    - name: "sharei"
      keyword: "si"
      command: "~/.config/raffi/scripts/sharei/sharei_filter.py"
      icon: "send-to"
      action: "~/.config/raffi/scripts/sharei/sharei_filter.py --act"
      secondary_action: "~/.config/raffi/scripts/sharei/sharei_filter.py --act-copy"
      env:
        SHAREI_PUBLIC_URL: "https://share.example.com"
```

The `env` block is only needed for a sharei whose own `public_url` setting is
unset: links come from `SHAREI_PUBLIC_URL`, else the server's `public_url`,
else the address it is reached at. The address sharei listens on, the login
and `~/.netrc` are `sharec`'s: it reads `SHAREI_URL`, `SHAREI_PUBLIC_URL` and
`SHAREI_PASS_ENTRY` the same way.

## Using it

Type `si`, then a space, then what you are looking for. Ctrl+Tab switches the
view, Ctrl+Shift+Tab goes back, and the footer shows where you are:

| View | Rows |
| --- | --- |
| Notes | every shared note and file, newest first; typing searches the note text and the paths and lists the matching lines underneath the note |
| Clipboard | the current shared clipboard and its history, newest first |
| Drops | the dropped files, newest first |
| Shots | the screenshots, newest first |

Enter opens the note, the drop or the screenshot in the browser, and puts the
clipboard entry back on this machine's clipboard. Ctrl+Enter copies the note's
or the drop's link instead. Opening a note found by a text search puts you on
the matching line, highlighted.

Typing `si clip` or `si drop` jumps to that view with the rest of the line as
the query, which is quicker than Ctrl+Tab from a fresh window.

The Notes view lists 40 entries and ends with a line saying how many it left
out; keep typing to narrow it down. A sharei without a `[notes]` vault has no
Notes view at all, and the filter opens on the next one instead of showing an
error.

With the preview pane open (Ctrl+P), the selected note shows its text, a
clipboard entry its content, and a screenshot or an image drop the image
itself. Everything is fetched through `sharec cat`, so large images are only
downloaded when they are selected.

## Notes

- Notes and markdown drops are drawn in the preview pane the way raffi's
  own scripts draw them (`scripts/github/pr.py`): headings and bold, code
  spans and fences, task lists, callouts, pipe tables, wikilinks as links,
  `==mark==` in bold, `%%comments%%` dropped, and the YAML front matter
  dimmed above a rule.
- The notes, the clipboard and the drops come from sharei itself, so what the
  filter shows is exactly what the web page shows: unshared notes, hidden
  files and expired items stay out.
- There is no caching: sharei answers locally in milliseconds, and a stale
  clipboard is worse than a slow one. Drop `cache_seconds` from a copied
  config if it is there.
- The filter's icons come from the Icon Fairy plugin sharei reads; they are
  downloaded once into `$XDG_CACHE_HOME/raffi/sharei/icons/`. Preview images
  land next to them in `previews/`, and `raffi --refresh-cache` leaves both
  alone: they are only caches, delete them whenever you like.
- `--act` and `--act-copy` are what the two actions call, so a row's
  `variables` decide what happens; there is no shell quoting to get wrong.
