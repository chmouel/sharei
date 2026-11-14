---
name: sharei
description: Read or write the user's sharei service - what they shared from
  their phone, the clipboard text, the newest screenshot, or a file handed to
  their phone. Use when the user says "look at what I shared on sharei", "what
  did I send from my phone", asks for "the latest clip", "what's in my
  clipboard", "the latest screenshot", asks you to put text or a file on their
  phone or another device, or asks to share something with them. Also use
  whenever you take or save a screenshot or screen recording (emulator, device,
  browser, app) for the user to look at, since it decides where the file goes.
  Also use whenever you need to hand the user a markdown document (report,
  plan, review, write-up) instead of leaving it in /tmp.
---

# sharei

sharei is a small self-hosted server that moves things between a computer and
a phone: build artifacts, a clipboard with history, and per-project
screenshots and drop folders. The phone usually has it installed as an app,
so Android's Share menu sends text and links to the clipboard and files to
the `inbox` project.

Files live under `<root>/<project>/`: screenshots in `shots/`, dropped files
in `drop/`. The root is `~/tmp/sharei` unless `root` is set in
`~/.config/sharei/config.toml` (or `$SHAREI_CONFIG`); check it before
assuming. A project is the repository name, or `inbox` when there is none.

## Client

Use `sharec`, the official client, for everything. Run `sharec --help`,
`sharec get --help` or `sharec clip --help` when unsure of a flag.
`sharec notes [QUERY] [--json]` lists the shared vault or searches its text,
and `sharec cat PATH` prints any server route, such as a note's markdown with
`/notes-file/<path>`.

sharec reads its address and login from the environment:

- `SHAREI_URL`: the server. Unset, it uses `http://localhost:8000`, or
  `SHAREI_PUBLIC_URL` when nothing listens there.
- `SHAREI_PUBLIC_URL`: the base for the links it prints.
- `SHAREI_PASS_ENTRY`: a `pass` entry for basic auth (password on line 1,
  optional `user:` line). Without it sharec reads `~/.netrc`.

If sharec cannot reach the server or log in, tell the user which variable is
missing. Never print or pass the password yourself.

`sharec --json` returns links based on the public URL; give the user those
rather than building links by hand.

## Sharing documents with the user

Whenever you need to hand the user a markdown document (a report, plan,
design note, review summary, investigation write-up, or anything too long
for a chat reply), upload it to sharei instead of leaving it in `/tmp` or a
local path, and give the `view` link:

```bash
sharec report.md -p <project> -y --json | jq -r .view
```

Pass the same rule on to subagents whose output is meant for the user.

Write for a reader who wants the gist first. Lead with a high-level summary in
plain, everyday words: what changed, why it matters, what (if anything) the
user needs to do. Keep file paths, function names, hashes, logs and other
low-level detail out of that part; put them at the bottom in collapsed
sections so they are there when wanted but hidden by default:

```markdown
<details>
<summary>Technical details</summary>

...commits, files, test output, review findings...

</details>
```

When a flow, sequence, state machine, dependency graph or architecture is
easier to grasp as a picture, add a mermaid diagram (usually a `flowchart`,
`sequenceDiagram` or `stateDiagram-v2`) in a ```mermaid fence; the `/md`
view renders it. Keep diagrams small and labelled in plain words, and skip
them when a list or table says it just as well.

When a flowchart shows something that happens in order (a request going
through services, a pipeline run, a bot answering an issue), make it an
animated walkthrough with the `aniflow-diagrams` skill (from
https://github.com/chmouel/aniflow); the `/md` view plays it. Pictures
referenced by a relative path are uploaded by `sharec -y` only from the
document's git repository or, outside one, its own folder.
`/icons/` pictures need no upload. Open the `view` link once after sharing
and fix any steps listed under the diagram's warning badge.

### Review comments

The user can comment on lines of a shared markdown file from its `/md`
page. When they say they reviewed or commented on a document, read the
comments, revise the file, and upload the new version under the same name:

```bash
sharec get comments plan.md -p <project>          # ready-to-read prompt
sharec get comments plan.md -p <project> --json   # {lines, comments:[{start,end,quote,body,outdated?}]}
sharec plan.md -p <project> --replace -y --json   # same name, comments kept
```

Line numbers are source lines of the markdown file. After `--replace`,
comments whose lines moved follow them, and comments whose lines changed are
marked `outdated`. Without `--replace` the upload gets a new name
(`plan-1.md`) and starts with no comments. `/recent` drop items carry a
`comments` count.

Comments made on a diagram name what they point at: the prompt header reads
`plan.md:9 (diagram 1, box "Build")` or `(diagram 1, arrow "A → B")`, and the
JSON adds `target: {kind: node|edge|diagram, id, label, diagram}`. The quoted
line is the mermaid source line declaring that box or arrow.

## What the user shared

```bash
sharec get list 5 --json | jq -c '{clip: .clip | {chars, age_seconds},
  drop: [.drop[] | {project, name, bytes, age_seconds, url}],
  shots: [.shots[:2][] | {project, name, age_seconds, url}]}'
```

`clip` is metadata only, `drop` and `shots` are newest first across all
projects; `-p PROJECT` narrows them to one project, for "what I shared for
this repo". Take the most recent item across all three, then read it. The lists
mix every project, so check `age_seconds` before assuming an item is the
user's; a screenshot from an unrelated session can sit above their photo.

Read the item with:

```bash
sharec get                       # clipboard text
sharec get clip 1                # the clip before it (history)
sharec get drop -o /tmp/         # newest dropped file, saved under its name
sharec get shot 2 -p myapp -o /tmp/    # third newest myapp screenshot
```

Always pass `-o` for drops and shots: without it sharec opens a terminal
image viewer or writes the raw bytes to stdout. It never overwrites, so read
the saved path from its output. If nothing is recent, say so instead of
guessing from old items.

Before viewing a photo or screenshot, shrink it; phone images are often
several MB:

```bash
magick IMG -auto-orient -resize '1600x1600>' -quality 80 /tmp/view.jpg
# macOS without ImageMagick:
sips -s format jpeg -Z 1600 IMG --out /tmp/view.jpg
```

Convert in one tool call and view the result in the next. A read issued in
the same batch as the `magick` command runs before the file exists and fails
with `ENOENT`.

Files can be given an expiry from the Drop and Shots pages (1h to 30d); such
items carry `expires` (epoch seconds) in the list and are deleted after it.

## Write

```bash
sharec clip 'some text'          # set the clipboard
printf '%s' "$TEXT" | sharec clip
sharec clip --ttl 3600           # keep it an hour; 0 = until replaced, max 7 days
sharec clip --clear

sharec -f report.pdf --json      # upload as is
sharec notes.md -y --json        # markdown, with its local images
sharec main.go -p inbox --json   # text file, highlighted page
```

The clipboard keeps the replaced text in its history (`sharec get clip N`)
and expires after its TTL (default 600s). Uploads go to the current
repository's project, else `inbox`; run sharec from the repository the file
belongs to or pass `-p`. Uploading an existing name keeps both
(`name-1.ext`), so link the returned `url`. One file per command; loop for
several.

A `.md` or `.markdown` upload returns a `view` link to `/md/<project>/<name>`,
rendered like github.com (alerts, highlighted code, mermaid, table of
contents, light and dark). Give the user that link rather than `url`, which
downloads the file. `-y` uploads the images the document references (only
those inside its git repo, or its folder outside one) and points the document at them; without it
sharec asks first, which an agent cannot answer. Other text files (UTF-8, at
most 2 MB) return a `view` link to `/view/<project>/<name>` with line numbers
and highlighting; lines link as `#L12`. `/clip/md` renders the clipboard as
markdown.

## Screenshots you take

When the server runs on this machine, save screenshots for the user (for
example `adb exec-out screencap -p`) to `<root>/<project>/shots/<name>.png`,
where `<project>` is the repository name; create the folder first. Don't use
`/tmp`. They appear on the server's `/shots` page right away. When the
server runs elsewhere, upload with `sharec -f shot.png --json`; it lands in
that project's drop folder.

## Delete (destructive, ask first unless the user asked)

sharec has no delete command for agents. Where the server runs, `POST` to
its local address plus `/shots/delete/<project>/shots/<file>`,
`/shots/delete-all`, `/poub/delete/<project>/<name>`, or `/poub/delete-all`
(every project, or one with `?project=`). Each answers `{"deleted": n}`, 404
when missing. Otherwise ask the user to delete from the web page.

## Limits and traps

- Clipboard 1 MiB, uploads 2 GiB, Share-menu posts 200 MB. Bigger requests
  get 413.
- The systemd unit from `contrib/sharei.service` writes only under `~/tmp`
  and its cache (`~/.cache/sharei`); a root outside `~/tmp` also needs the
  unit's `ReadWritePaths` widened.
- If the service is down: `systemctl --user start sharei.service`,
  then `journalctl --user -u sharei.service -n 30`.
- Pipe JSON through `jq` and keep only what matters; never dump `/shots` or
  `/drop` HTML.
