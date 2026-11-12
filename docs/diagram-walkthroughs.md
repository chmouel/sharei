# Diagram walkthroughs

sharei can play a mermaid flowchart as a short story. A labelled dot travels
from box to box, the box it reaches lights up, finished boxes get a check mark,
and boxes the story does not use fade out. One diagram can hold several
stories, and boxes can carry pictures.

This document describes how that works. It is also the demo: share it with
`sharec docs/diagram-walkthroughs.md` and press play on the diagram below. The
picker next to the button switches between the two stories.

GitHub draws the same diagram without playback. Paused halfway, sharei shows
this:

![The demo paused while the dot carries "prompt" to the agent](screenshots/walkthrough.png)

```mermaid
flowchart LR
  E@{ img: "diagram-icons/event.svg", label: "Issue or PR", w: 48, h: 48, constraint: "on" }
  L@{ img: "diagram-icons/listener.svg", label: "Listener", w: 48, h: 48, constraint: "on" }
  T@{ img: "diagram-icons/trigger.svg", label: "Trigger", w: 48, h: 48, constraint: "on" }
  F[Fetch context]
  R@{ img: "diagram-icons/pipeline.svg", label: "Run step", w: 48, h: 48, constraint: "on" }
  A@{ img: "diagram-icons/agent.svg", label: "Agent", w: 48, h: 48, constraint: "on" }
  M@{ img: "diagram-icons/model.svg", label: "Model", w: 48, h: 48, constraint: "on" }
  P@{ img: "diagram-icons/branch.svg", label: "Push branch", w: 48, h: 48, constraint: "on" }
  C@{ img: "diagram-icons/comment.svg", label: "Comment", w: 48, h: 48, constraint: "on" }
  E --> L --> T --> F --> R
  R <--> A
  A <--> M
  R --> P --> C
  R --> C

%% play: Issue opened
%% E -> L : Issue #42
%% L -> T
%% T -> F : Issue #42
%% F -> R
%% R -> A : prompt
%% A -> M : tokens
%% M -> A
%% A -> R : patch
%% R -> P : branch
%% P -> C : PR #44
%% play: Pull request review
%% E -> L : PR #44
%% L -> T
%% T -> F : PR #44
%% F -> R
%% R -> A : diff
%% A -> M
%% M -> A
%% A -> R : review
%% skip P
%% R -> C : review
```

## Writing a walkthrough

A walkthrough lives in the same mermaid block as the flowchart, written as
`%%` comment lines. Mermaid, GitHub and every other renderer ignore comments,
so the diagram still draws everywhere else and only sharei plays it.

```text
%% play: Title          starts a story; the title shows in the picker
%% A -> B               the dot travels from node A to node B
%% A -> B : label       the same, with a tag riding along with the dot
%% skip A B             fades these nodes until the story ends
```

Nodes are named by their mermaid id (the `R` in `R[Run step]`), never by their
label. Steps written before the first `play:` line form a story called
Walkthrough. Any other comment is left alone, so ordinary notes can sit next to
the script.

A step needs an edge between its two nodes. When the edge is drawn the other
way (`B --> A`, or a two-way `A <--> B`), the dot runs along it backwards.
`A -> B` and `A --> B` mean the same thing in a step.

When a step names a node that does not exist or a pair with no edge, sharei
skips it and lists it in the play button's tooltip. A block whose stories have
no usable step gets no play button.

Only flowcharts play (`flowchart` or `graph`, after optional front matter).
Other diagram types keep pan and zoom.

## What playing looks like

Each step starts by lighting up its first node, then moves the dot along the
edge. The node it leaves gets a check mark and the node it reaches lights up.
When the story ends, the last lit node is marked done and the final picture
stays on screen until you play again, press stop or pick another story.

| Moment | Duration |
| --- | --- |
| Pause on a node before it sends the dot | 420 ms |
| Travel along an edge | 3.2 ms per pixel of path, between 550 ms and 1.7 s |
| A skip | 320 ms |

A node that a later step reaches again clears its skip and its check mark, so
a story can loop back through the diagram.

The controls sit in the diagram's toolbar next to the zoom buttons: play,
pause, stop and the story picker. Picking a story starts it. In full screen,
the space bar plays and pauses. Pan, zoom and full screen keep working while a
story plays, because the dot is drawn inside the diagram and moves with it.
While a story plays, the page holds off its live reload so the story does not
vanish halfway.

With `prefers-reduced-motion` set, there is no travelling dot and no glow
pulse. Nodes and edges change state in plain steps of about half a second.

## Pictures in boxes

Mermaid 12 can put a picture in a node:

```text
A@{ img: "logo.png", label: "Build", w: 48, h: 48, constraint: "on" }
```

`w` and `h` size the picture, and `constraint: "on"` keeps its proportions.
`pos: "t"` moves the label above the picture.

sharei accepts four kinds of picture:

- A file next to the markdown, such as `logo.png` or `icons/logo.png`. The
  reader looks it up by name in the same drop folder, like an ordinary
  markdown image. `sharec` uploads it along with the markdown and rewrites the
  path, with the same checks it applies to markdown images: the file must sit
  inside the git checkout or the document's folder, with no hidden folder or
  symlink escape on the way, its contents must match its extension, and you
  confirm the upload.
- A path on the sharei server itself, starting with `/`. This is what
  `sharec` writes in place of a local file, and how the built-in icons below
  are used.
- An `https://` URL.
- A `data:image/...` URL for PNG, JPEG, GIF, WebP or SVG.

Any other scheme, `http:` included, is refused. Mermaid gives up on the whole
diagram when one picture fails, so the reader loads each picture first and
puts a grey placeholder in place of any that is refused, missing or slower
than eight seconds. The diagram's tooltip lists those pictures.

Picture nodes play like any other node: the frame lights up, the check mark
sits on the picture's corner, and skipped ones fade.

GitHub draws mermaid in a separate frame where a relative picture path does
not resolve. If a diagram has to look right on GitHub as well, use https URLs
for its pictures. On notes pages from the Obsidian vault, use https or data
pictures: the vault serves a file only when a note links to it with ordinary
markdown, and a picture inside a diagram does not count as such a link.
The built-in icons work everywhere sharei draws the diagram, notes included.

### Built-in icons

sharei serves a set of icons at `/icons/<name>.svg`, so a diagram can have
pictures without shipping any files:

```text
Bot@{ img: "/icons/agent.svg", label: "Agent", w: 48, h: 48, constraint: "on" }
```

They are 48×48 tiles in the same style as the demo above, built from
[Lucide](https://lucide.dev) (ISC licence) by `contrib/icons/make_icons.py`.
`sharec` leaves `/icons/` paths as they are, and `/icons/` on the server
returns the list as JSON. Other mermaid renderers, GitHub included, cannot
reach them; copy the SVG next to the document if it must render there too.

| Group | Names |
| --- | --- |
| People and agents | `user` `users` `reviewer` `agent` `model` `brain` `skill` `prompt` `sparkles` `tool` |
| Git and forges | `issue` `pull-request` `commit` `branch` `merge` `fork` `repository` `tag` `release` `comment` `review` `diff` `code` `file-code` |
| Events and CI | `event` `webhook` `listener` `trigger` `pipeline` `task` `step` `test` `build` `deploy` `rerun` `follow-up` `schedule` `queue` `wait` `timer` `clock` `check` `success` `fail` `warning` `bug` `fix` `stop` `play` `pause` |
| Platform | `cluster` `node` `pod` `container` `namespace` `service` `network` `ingress` `route` `load-balancer` `database` `storage` `cache` `cloud` `registry` `image` `config` `operator` `controller` `api` `terminal` `cli` `laptop` `phone` `browser` `globe` |
| Security and identity | `identity` `fingerprint` `key` `token` `secret` `unlock` `policy` `shield` `refuse` `audit` `certificate` |
| Data and output | `logs` `report` `document` `folder` `search` `inspect` `metrics` `monitor` `dashboard` `alert` `notification` `mail` `chat` `upload` `download` `link` `filter` `decision` `idea` |

Agents and models are violet, waiting and secrets amber, failures and refusals
red, success green, and everything else blue.

## How it fits on mermaid's output

All of this happens in the browser, in `MARKDOWN_JS` in
`src/sharei/reader.py`. The server does not change.

1. Before rendering, `playScript()` reads the stories out of the block's
   source, since mermaid drops comments from its output. `diagramImages()`
   resolves and preloads the pictures and rewrites their URLs in the source
   it hands to mermaid.
2. Mermaid renders with `securityLevel: 'strict'`.
3. `panZoom()` adds the toolbar and stage, and `playDiagram()` maps the
   stories onto the SVG.

The mapping relies on how mermaid 12.3 names things:

- Nodes are `g.node`, or `g.image-shape` for picture nodes, with an id ending
  in `-flowchart-<nodeId>-<n>`.
- Edges are `path[data-edge]` with `data-id="L_<from>_<to>_<n>"`. Node ids may
  contain `_` and `-`, so the lookup matches the prefix `L_<from>_<to>_` with a
  numeric tail instead of splitting on underscores.
- A two-way edge is one path with markers at both ends.

When mermaid is upgraded, play the demo above in both directions and in both
stories, and check that the tooltip lists no ignored step. If those names
change, steps start showing up as ignored.

The playback is a list of timed segments driven by `requestAnimationFrame`.
Each segment has a start action and, for travel, a frame callback that places
the dot with `getPointAtLength`. The dot lives in the root SVG's coordinates
(the path's transform is folded in through `getScreenCTM`), so zooming, which
rewrites the `viewBox`, needs no recalculation. Node states are classes
(`play-active`, `play-done`, `play-skipped`, `play-edge`, `play-edge-done`)
styled from the theme's CSS variables. Mermaid's own rules are more specific,
so a few of these use `!important`.

## Security

The markdown is untrusted, and so is everything in a walkthrough.

- Story titles, step labels and tooltips reach the page through
  `textContent` and `createElementNS`, never as HTML.
- Picture URLs go through the allowlist above before mermaid sees them.
  Anything that does not pass is swapped for the built-in placeholder, which
  is a fixed data URL.
- The `/md` page keeps its nonce-based CSP. Its `img-src 'self' https: data:`
  already covered these pictures, so the policy did not change.
- `sharec` scans `img:` values inside mermaid fences only, and uploads them
  through the existing image checks.

## Not covered

- Two dots moving at once, for parallel branches.
- Autoplay or looping stories.
- Sequence, state and other diagram types.
- Exporting a story as a video. A screen recording does the job for now.
- Mermaid icon packs (`icon: "fa:..."`). The built-in icons cover the same
  need through `img:`.

The icons in [`diagram-icons/`](diagram-icons/) were drawn for this document
and carry the repository's licence.
