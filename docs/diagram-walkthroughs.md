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
%% E -> L : Issue #42 | Someone opens issue #42 and GitHub sends the event
%% L -> T
%% T -> F : Issue #42
%% F -> R
%% R -> A : prompt | The run hands the issue to the agent as a prompt
%% A -> M : tokens
%% M -> A
%% A -> R : patch
%% R -> P : branch
%% P -> C : PR #44 | The fix comes back as pull request #44
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
%% A -> B : label | text  the same, with a sentence shown under the diagram
%% skip A B             fades these nodes until the story ends
%% skip A B | text      the same, with a sentence
```

The sentence after `|` is the step's caption, for the part you would say out
loud while the dot moves. A step without one hides the caption, so the
sentence never lingers on a later step it does not describe. `A -> B | text`
works without a label too.

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

A step's caption shows as soon as the step starts, in a bar under the
diagram, or floating at the bottom of the screen in full screen. Stopping the
story clears it. Like labels, captions are set with `textContent`.

A node that a later step reaches again clears its skip and its check mark, so
a story can loop back through the diagram.

The controls sit in the diagram's toolbar next to the zoom buttons: previous
step, play, next step, stop and the story picker. Picking a story starts it.

When you talk over a diagram, the next step button plays one step and stops,
so the dot waits on its box until you move on. Pressing it during a normal
play makes the story stop at the end of the current step. Previous step
rebuilds the story from the start up to the step before, with no animation,
and from the middle of a step it goes back to that step's start. With the
diagram focused, or in full screen, the keyboard does the same: the right
arrow, `j` and Page Down go forward, the left arrow, `k` and Page Up go
back, and Space plays or pauses the whole story. Page Down and Page Up are
what most presentation clickers send.

A thin rail under the story controls has one tick per step. Played steps
fill in, the one playing is brighter, and hovering a tick shows its caption.
Clicking a tick rebuilds the story up to the step before and plays that one,
so you can jump to any point while you talk.

The camera button in the view controls makes the view follow the story. While
a story plays, it eases onto the arrow being drawn and the boxes at each end,
and it eases back to the whole diagram when the story ends or stops. It never
zooms in past a third of the diagram's width, so the neighbouring boxes stay
in sight, and on a short, wide diagram it may barely move. It is off by
default, the browser remembers the choice, and dragging or zooming by hand
takes over until the next step. With reduced motion it does nothing, and
exports always show the whole diagram.

Shift with an arrow still pans. Pan, zoom and full screen keep working while a
story plays, because the dot is drawn inside the diagram and moves with it.
While a story plays, the page holds off its live reload so the story does not
vanish halfway.

With `prefers-reduced-motion` set, there is no travelling dot and no glow
pulse. Nodes and edges change state in plain steps of about half a second.

## Pointing at a box

Any flowchart, with or without a story, lets you click a box to put it in the
spotlight while you talk about it. The box gets the accent outline and a
steady glow. Its arrows, their labels and the boxes at their other ends stay
as they are, and everything else fades to a fifth.

Shift, Ctrl or Cmd with a click adds or removes a box. A plain click on
another box moves the spotlight there. Clicking the only lit box, an empty part
of the diagram, or pressing Escape clears it. In full screen, the first Escape
clears the spotlight and the second closes the view. A drag that pans the
diagram and the second click of a double-click (which zooms) leave the
spotlight alone. A picture box counts as one target across its image, its label
and the gap between them.

A playing story is never dimmed by the spotlight: its lit box and the edge the
dot travels stay bright. A saved GIF or video keeps the spotlight as it was
when you started saving. Like a playing story, the spotlight holds off the
page's live reload.

## Linking to a moment

"Copy link" in the share menu copies the page address with a hash such as
`#diagram=2&story=1&step=3&focus=Agent,Logs`. Diagrams count from 1 in page
order, stories too, and `step` is the number of steps already played. Someone
who opens the link lands on that diagram with the story stopped after step 3
and the same boxes in the spotlight, so the next arrow press plays step 4. A
step past the end shows the story finished. Each part is optional: a link
with only `focus` lights boxes and leaves the story alone.

The copy replaces the current address without adding a history entry, and
editing the hash by hand applies it at once. Values that match no story or
no box are ignored.

## Saving a still picture

Every diagram has a share button, with or without a story. Its "Copy link"
keeps just the spotlight when there is no story, and "PNG" saves what the
diagram shows right now: the current
zoom and position, the spotlight, the dot and glow mid-step, and the caption
in a band underneath when one is showing. It comes out 2400 pixels on its
longer side, so a zoomed-in corner stays sharp enough for a slide. Like the
other exports, it is drawn in the browser and nothing goes to the server.

## Saving a story as a GIF or a video

The share button in the toolbar saves the selected story as a file to drop into a
pull request, a chat or slides. Everything happens in the browser and nothing
is sent to the server.

GIF replays the story off screen in 60 ms frames, with the glow and fades
turned off so every frame is stable. It comes out at most 960 pixels wide,
loops forever and holds the last frame for 2.4 seconds. Frames only store the
part of the picture that changed, so a short story stays a few hundred
kilobytes. Colours are cut to 256 per frame, so gradients band a little.

When a story has captions, both formats add a band under the diagram and
write the current caption in it, wrapped to two lines at most.

Video plays the story in real time and records it with `MediaRecorder`: MP4
(H.264) where the browser can write it, WebM otherwise. It goes up to 1920
pixels wide, keeps the glow and the smooth fades, and holds the last frame
for 1.5 seconds. It takes as long as the story does.

Both draw the diagram at its fitted size, whatever the zoom, on the page's
background colour and in the current theme. The button shows the progress
and a second press cancels. Pictures are copied into the file: same-origin
ones such as `/icons/` and dropped files are fetched, while pictures from
other sites cannot be read back and show as the placeholder. The video
option is hidden when the browser cannot record a canvas. Chrome writes both
formats. Safari may refuse to draw mermaid's HTML labels onto a canvas, and
the button then says the export failed.

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
the dot with `getPointAtLength`. The last segment of each step carries a
`stop` flag: step mode pauses there, and going back replays the timeline
instantly up to the wanted flag. The dot lives in the root SVG's coordinates
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
- Mermaid icon packs (`icon: "fa:..."`). The built-in icons cover the same
  need through `img:`.

The icons in [`diagram-icons/`](diagram-icons/) were drawn for this document
and carry the repository's licence.
