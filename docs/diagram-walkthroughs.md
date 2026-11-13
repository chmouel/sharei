# Diagram walkthroughs

sharei can play a mermaid flowchart or sequence diagram as a short story. A
labelled dot travels from box to box, the box it reaches lights up, finished
boxes get a check mark,
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
%% A -> B, C            one dot down each edge at the same time
%% A, B -> C            dots from A and from B meet at C
%% A -> B @ok           takes the edge declared as A ok@--> B
%% skip A B             fades these nodes until the story ends
%% skip A B | text      the same, with a sentence
%% wait 1500            holds the picture for 1.5 s before the next step
%% wait 1500 | text     the same, with a sentence shown while it waits
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

A step can list several boxes on one side, separated by commas or by `&` as
mermaid writes it. `A -> B, C` sends a dot down each edge at once, and
`A, B -> C` brings two dots into C together. Each dot moves at the pace its
own edge would have alone, so a short edge finishes first and its box lights
up while the longer one is still travelling. The step ends when the last dot
arrives. The label rides on the first dot only. Every listed box takes part:
if one pair has no edge, the whole step is skipped. Listing several boxes on
both sides (`A, B -> C, D`) is ambiguous, so sharei skips it the same way;
write one step per edge instead.

### Choosing between parallel edges

When two edges join the same boxes, a plain `A -> B` takes the first one
drawn. To pick another, give the edges ids in mermaid (`B ok@-->|pass| C`) and
name the id after the box in the step: `%% B -> C @ok`. The id can follow any
box in a list (`A -> B @ok, C`). It works either way round, so `C -> B @ok`
runs the dot backwards, but the named edge must join the two boxes in the
step. Edges with ids light up in the spotlight like any other. Sequence
diagrams have no edge ids, so a step there that names one is dropped.

```mermaid
flowchart LR
  P[Push] --> T[Tests]
  T ok@-->|pass| D[Deploy]
  T bad@-->|fail| D
  D --> N[Notify]

%% play: Green build
%% P -> T : commit
%% wait 1200 | The tests take a while
%% T -> D @ok : pass | Every test passes, so the deploy goes ahead
%% D -> N
%% play: Red build
%% P -> T : commit
%% T -> D @bad : fail | A test fails and the deploy step only reports it
%% D -> N : failure
```

### Waiting

`%% wait MS` holds the picture as it is for that many milliseconds before the
next step starts: the lit boxes stay lit and the dot is gone. Several waits in
a row add up, to at most 10 seconds. A wait after the last step holds the
finish before it settles. The time is at 1× and follows the speed button.
With a `| caption`, the sentence shows during the wait; the next step then
shows its own caption or hides it. Step mode does not stop on a wait. It runs
through it with the step that follows, and waits get no tick on the rail.

### Steps that cannot play

When a step names a node that does not exist, a pair with no edge, an
unknown edge id, or a `wait` without a number, sharei leaves it out and the
rest of the story plays. A warning badge with the count shows in the
toolbar, and opening it lists each dropped step with its story, its line in
the document and the reason. The same list goes to the browser console. A
wait in front of a dropped step moves on to the next one. A block whose
stories have no usable step gets no play button, only the badge.

Flowcharts (`flowchart` or `graph`) and sequence diagrams
(`sequenceDiagram`) play, after optional front matter. Other diagram types
keep pan and zoom.

## Sequence diagrams

In a sequence diagram the names are participant ids, and each step takes the
next message from the first to the second, counting from the message the
previous step used:

````markdown
```mermaid
sequenceDiagram
  participant Dev as Developer
  participant GH as GitHub
  actor P as PaC
  Dev->>GH: push
  GH-->>P: webhook
  P->>P: read .tekton
  P-)GH: status
  Dev->>GH: push again

%% play: Push
%% Dev -> GH | You push
%% GH -> P : event | GitHub calls PaC
%% P -> P | It reads the pipelines
%% P -> GH | The status goes back
%% Dev -> GH | Second push
```
````

The two `Dev -> GH` steps light up "push" and then "push again". When no
message is left below, the search starts again from the top, so a story can
also jump back. A step must follow the message's direction: `GH -> Dev` never
matches a `Dev->>GH` message. Self messages (`P -> P`) work, and notes, loops
and other boxes are left alone.

While a step plays, its message line and text light up and the dot travels
along the line. Participants behave like flowchart boxes: the top and bottom
boxes and the lifeline light up together, then turn green once done, and
`%% skip P` fades all three. The comma form sends dots down several messages
at once. Clicking a participant does not spotlight it; that stays a
flowchart feature.

## What playing looks like

Each step starts by lighting up its first node, then moves the dot along the
edge. The node it leaves gets a check mark and the node it reaches lights up.
When the story ends, the last lit node is marked done and the final picture
stays on screen until you play again, press stop or pick another story.

| Moment | Duration at 1× |
| --- | --- |
| Pause on a node before it sends the dot | 700 ms |
| Travel along an edge | about 5.3 ms per pixel of path, between 0.9 s and 2.8 s |
| A skip | 530 ms |

The speed button after stop cycles through 0.5×, 0.75×, 1×, 1.5× and
2×, and `<` and `>` step down and up with the diagram focused or while
presenting. The choice applies to every diagram and is remembered in the
browser. GIF and video exports play at the chosen speed.

A step's caption shows as soon as the step starts, in a bar under the
diagram, or floating at the bottom of the screen in full screen. Stopping the
story clears it. Like labels, captions are set with `textContent`.

A node that a later step reaches again clears its skip and its check mark, so
a story can loop back through the diagram.

The controls sit in the diagram's toolbar next to the zoom buttons: previous
step, play, next step, stop, speed and the story picker. Picking a story starts it.

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

## Drawing on a diagram

The pen button turns the pointer into a laser and a pen. Moving the mouse
leaves a short red trail that fades within a third of a second, so people
can follow what you point at. Pressing and dragging draws a stroke that
stays. Strokes live inside the diagram, so they move and scale with it when
you zoom or pan, at the same width on screen.

With the pen on, a one-finger or mouse drag draws instead of moving the
diagram. Two fingers still pinch and pan, and a drag that turns into a pinch
drops the stroke it started. Clicking a box without moving still puts it in
the spotlight. Escape wipes the strokes and leaves the pen on, and turning
the pen off wipes them too. While the pen is on, the page holds off its live
reload.

A PNG keeps the strokes, since it saves what you see. The laser trail never
reaches a picture, and GIF and video exports leave out the strokes too.

## Commenting on a diagram

In full screen, the speech bubble button opens a comments panel beside the
diagram (a sheet along the bottom on a phone). It only appears on pages that
take comments: shared markdown in sharei and every page in aniflow. With
the panel open, hovering outlines the box or arrow under the pointer, and a
click opens a draft for it. A click on the background comments on the whole
diagram. Ctrl+Enter saves, Escape drops the draft, and a second Escape
closes the panel.

Each comment gets a numbered pin on its box or arrow. The pins follow zoom
and pan at the same size on screen and never reach an export. Hovering a
card outlines what it points at, and clicking a pin opens its card. Cards
have Reply, Edit and Delete, and a comment whose source line changed is
marked outdated, like any line comment.

A diagram comment is an ordinary review comment on the line of the fence
that declares its box or arrow, with the box or arrow named in it. A box
anchors to the first line that uses its id, an arrow to the line that
declares it (its `id@`, or both ends), and the whole diagram to the opening
fence. So the line gutter, `sharec get comments` and Copy as prompt show
them too, with a header such as `plan.md:9 (diagram 1, box "Build")` or
`plan.md:12 (diagram 1, arrow "Build → Deploy (passed)")`.

"Copy for agent" puts this diagram's comments on the clipboard as that same
prompt, and "Copy all" copies every comment on the page.

## Linking to a moment

"Copy link" in the share menu copies the page address with a hash such as
`#diagram=2&story=1&step=3&focus=Agent,Logs`. Diagrams count from 1 in page
order, stories too, and `step` is the number of steps already played. Someone
who opens the link gets that diagram in full screen with the story stopped
after step 3 and the same boxes in the spotlight, so the next arrow press
plays step 4. Closing full screen leaves them at the diagram in the page. A
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

## Presenting a note

The Present button in the reader bar, or `p`, turns a note into slides and
asks the browser for full screen. Each `##` heading starts a slide, and
whatever comes before the first one (the title and intro) is slide one. A
note with no `##` but several `#` headings splits on those instead, and the
button stays hidden when there would be fewer than two slides.

A slide that holds one diagram and little else gives the diagram the whole
screen. The right arrow, `j` and Page Down play the slide's story one step
at a time and move to the next slide once it has finished; the left arrow,
`k` and Page Up go back the same way. On a slide with a story, Space plays
or pauses it, and elsewhere Space moves on. Home and End jump to the first
and last slide, and a swipe changes slide on a phone.

A rail along the bottom edge has one segment per slide, with the heading as
its tooltip; click a segment to jump there. The previous, next and close
buttons sit in the corner and fade with the pointer after a few seconds
still. The address carries `#slide=3`, so a link opens the talk on that
slide. Escape clears a drawing or spotlight first, then leaves, and so does
leaving full screen; the page scrolls to the slide you were on.

## How it fits on mermaid's output

All of this happens in the browser, in `MARKDOWN_JS` in
`src/sharei/reader.py`. The server does not change.

1. Before rendering, `playScript()` reads the stories out of the block's
   source, since mermaid drops comments from its output, and notes each
   step's line in the document. `diagramImages()` resolves and preloads the
   pictures and rewrites their URLs in the source it hands to mermaid.
   `diagramEdges()` asks mermaid's parser
   (`mermaidAPI.getDiagramFromText`) for the flowchart's edges with their
   ids and ends.
2. Mermaid renders with `securityLevel: 'strict'`.
3. `panZoom()` adds the toolbar and stage, and `playDiagram()` maps the
   stories onto the SVG. Dropped steps go to `diagramWarnings()`.

The mapping relies on how mermaid 12.3 names things:

- Nodes are `g.node`, or `g.image-shape` for picture nodes, with an id ending
  in `-flowchart-<nodeId>-<n>`.
- Edges are `path[data-edge]` whose `data-id` is the edge's id from the
  parser: `L_<from>_<to>_<n>` when mermaid makes one up, or the id written in
  the source (`A ok@--> B`), which names neither end. `diagramLinks()` pairs
  each path with its ends through that id, for playback and the spotlight
  alike. If the parser call fails, it falls back to splitting generated ids:
  node ids may contain `_` and `-`, so it matches the prefix `L_<from>_<to>_`
  with a numeric tail instead of splitting on underscores, and edges with
  their own ids are then unknown.
- A two-way edge is one path with markers at both ends.

In sequence diagrams, participants are `rect.actor` (top and bottom, each
inside its own `g` with the `text.actor`), `g.actor-man` for actors, and
`line.actor-line`, all carrying the participant id in `name`. Messages are
`line` or `path` elements with class `messageLine0` or `messageLine1`, in
source order, each preceded by its `text.messageText`. Mermaid insets message
ends from the lifelines, so `playDiagram()` gives each message the
participants whose lifelines are nearest to its two ends.

When mermaid is upgraded, play the demos above in both directions and in
every story, and check that no warning badge shows. If those names change,
steps start showing up there.

The playback is a list of timed segments driven by `requestAnimationFrame`.
Each segment has a start action and, for travel, a frame callback that places
the dot with `getPointAtLength`. A wait is a segment with only a duration.
The last segment of each step carries a
`stop` flag: step mode pauses there, and going back replays the timeline
instantly up to the wanted flag. The dot lives in the root SVG's coordinates
(the path's transform is folded in through `getScreenCTM`), so zooming, which
rewrites the `viewBox`, needs no recalculation. Node states are classes
(`play-active`, `play-done`, `play-skipped`, `play-edge`, `play-edge-done`)
styled from the theme's CSS variables. Mermaid's own rules are more specific,
so a few of these use `!important`.

## Security

The markdown is untrusted, and so is everything in a walkthrough.

- Story titles, step labels, warnings and tooltips reach the page through
  `textContent` and `createElementNS`, never as HTML.
- Picture URLs go through the allowlist above before mermaid sees them.
  Anything that does not pass is swapped for the built-in placeholder, which
  is a fixed data URL.
- The `/md` page keeps its nonce-based CSP. Its `img-src 'self' https: data:`
  already covered these pictures, so the policy did not change.
- `sharec` scans `img:` values inside mermaid fences only, and uploads them
  through the existing image checks.

## Not covered

- Autoplay or looping stories.
- State, class and other diagram types.
- Spotlighting participants in sequence diagrams.
- Mermaid icon packs (`icon: "fa:..."`). The built-in icons cover the same
  need through `img:`.

The icons in [`diagram-icons/`](diagram-icons/) were drawn for this document
and carry the repository's licence.
