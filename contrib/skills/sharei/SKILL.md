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
through services, a pipeline run, a bot answering an issue), make it a
walkthrough with pictures. The `/md` page plays it: a labelled dot travels
along the arrows, the box it reaches lights up and finished boxes get a tick.
GitHub and other renderers ignore the `%%` lines and draw a plain flowchart.
Static structure, such as a dependency graph or a class layout, gains nothing
from playback; leave it as a plain diagram.

````markdown
```mermaid
flowchart LR
  Issue@{ img: "/icons/issue.svg", label: "Issue opened", w: 48, h: 48, constraint: "on" }
  Bot@{ img: "/icons/agent.svg", label: "Bot", w: 48, h: 48, constraint: "on" }
  Fetch[Fetch context]
  PR@{ img: "/icons/pull-request.svg", label: "Pull request", w: 48, h: 48, constraint: "on" }
  Issue --> Bot --> Fetch --> Bot --> PR

%% play: New issue
%% Issue -> Bot : #42 | A user opens issue #42 and the bot picks it up
%% Bot -> Fetch
%% Fetch -> Bot : files | The bot reads the files the issue points at
%% Bot -> PR : fix | It opens a pull request with the fix
%% play: Question only
%% Issue -> Bot : question
%% skip Fetch PR
```
````

- Steps use node ids, never labels, and need an arrow between the two
  boxes (backwards works). `: text` is the label on the dot, keep it to a
  word or two. `| sentence` after it is a caption shown under the diagram
  while that step plays: one short plain sentence saying what happens, on
  the steps that need explaining. `%% play: Title` starts another scenario in the same
  diagram; `%% skip A B` fades boxes that scenario does not use.
- Give picture boxes to the actors and main stages, and keep plain boxes for
  small steps; four to eight pictures read best. Always set `w`, `h` and
  `constraint: "on"`, or the picture stretches.
- Use sharei's built-in icons first: `img: "/icons/<name>.svg"`. They need
  no upload and `sharec` leaves them alone. `sharec cat /icons/` prints the
  current list; the names are:
  - people and agents: user users reviewer agent model brain skill prompt
    sparkles tool
  - git: issue pull-request commit branch merge fork repository tag release
    comment review diff code file-code
  - events and CI: event webhook listener trigger pipeline task step test
    build deploy rerun follow-up schedule queue wait timer clock check
    success fail warning bug fix stop play pause
  - platform: cluster node pod container namespace service network ingress
    route load-balancer database storage cache cloud registry image config
    operator controller api terminal cli laptop phone browser globe
  - security: identity fingerprint key token secret unlock policy shield
    refuse audit certificate
  - data and output: logs report document folder search inspect metrics
    monitor dashboard alert notification mail chat upload download link
    filter decision idea
- When nothing fits, draw a small SVG in the same style (48×48 viewBox, a
  rounded square tinted at 12% opacity with a stroked symbol in one colour).
  Put it next to the markdown file, in a subfolder like `icons/`, and use a
  relative path: `sharec -y` uploads it only from the document's git
  repository or, outside a repository, its own folder. An https URL works
  too; no logos you don't have the right to use. `/icons/` paths do not
  render on GitHub, so a diagram that must look right there needs relative
  or https pictures.
- A picture that is missing or fails to load shows a placeholder, and the
  diagram's hover text names it. Hovering the play button lists steps that
  did not match a box or arrow. The full syntax is in sharei's
  `docs/diagram-walkthroughs.md`.

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
