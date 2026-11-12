"""The markdown reader: its styles, buttons and the script that renders markdown in the browser."""

MARKDOWN_CSS = """
  * { box-sizing:border-box }
  html { scroll-padding-top:64px; }
  body { margin:0; background:var(--bgColor-default, Canvas); color:var(--fgColor-default, CanvasText); font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","Noto Sans",Helvetica,Arial,sans-serif; }
  .bar { position:sticky; top:0; z-index:2; display:flex; align-items:center; gap:12px; padding:10px max(16px, env(safe-area-inset-left)); background:color-mix(in srgb, var(--bgColor-muted) 92%, transparent); border-bottom:1px solid var(--borderColor-default); backdrop-filter:blur(8px); font-size:14px; }
  .bar a { color:var(--fgColor-accent); text-decoration:none; font-weight:600; white-space:nowrap; }
  .bar a:hover { text-decoration:underline; }
  .bar .name { flex:1; min-width:0; overflow:hidden; color:var(--fgColor-muted); text-overflow:ellipsis; white-space:nowrap; }
  .bar nav { display:flex; gap:14px; }
  .bar nav button { padding:0; border:0; background:none; color:var(--fgColor-accent); font:inherit; font-weight:600; cursor:pointer; }
  .bar nav button:hover { text-decoration:underline; }
  .bar nav .renderer { display:inline-flex; align-items:center; gap:3px; margin:-4px 0; padding:4px 6px; border-radius:6px; color:var(--fgColor-muted); }
  .bar nav .renderer:hover { color:var(--fgColor-default); text-decoration:none; }
  .bar nav .renderer[aria-pressed="true"] { color:var(--fgColor-accent); background:color-mix(in srgb, var(--fgColor-accent) 18%, transparent); }
  .bar nav .renderer[hidden] { display:none; }
  .renderer svg { display:block; fill:currentColor; }
  .page { width:min(100%, 980px); margin:0 auto; padding:24px 16px 64px; }
  .notice { margin:0 0 16px; padding:10px 14px; border:1px solid color-mix(in srgb, var(--borderColor-attention-emphasis) 45%, transparent); border-radius:6px; background:var(--bgColor-attention-muted); color:var(--fgColor-default); font-size:14px; }
  .toc { margin:0 0 20px; padding:8px 14px; border:1px solid var(--borderColor-default); border-radius:6px; font-size:14px; }
  .toc summary { cursor:pointer; font-weight:600; padding:4px 0; }
  .toc ol { margin:6px 0 6px; padding:0; list-style:none; }
  .toc li { padding:3px 0; }
  .toc a { color:var(--fgColor-accent); text-decoration:none; }
  .toc a:hover { text-decoration:underline; }
  .markdown-body h1, .markdown-body h2, .markdown-body h3, .markdown-body h4, .markdown-body h5, .markdown-body h6 { position:relative; }
  .markdown-body .anchor { position:absolute; left:-1.1em; padding-right:.3em; color:var(--fgColor-muted); text-decoration:none; opacity:0; }
  .markdown-body :is(h1,h2,h3,h4,h5,h6):hover .anchor, .markdown-body .anchor:focus { opacity:1; }
  .markdown-body .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  .mermaid-diagram { margin:0 0 16px; overflow-x:auto; text-align:center; }
  .mermaid-diagram svg { max-width:100%; height:auto; }
  .diagram-stage { position:relative; touch-action:pan-y; }
  .diagram-stage > svg { display:block; margin:0 auto; user-select:none; -webkit-user-select:none; }
  .diagram-stage.zoomed { touch-action:none; cursor:grab; }
  .diagram-stage.zoomed:active { cursor:grabbing; }
  .diagram-tools { position:absolute; top:0; right:0; display:flex; gap:2px; padding:3px; border:1px solid var(--borderColor-default); border-radius:9px; background:var(--bgColor-default); opacity:0; transition:opacity .15s; }
  .mermaid-diagram:is(:hover, :focus-within) .diagram-tools, .diagram-dialog .diagram-tools { opacity:1; }
  @media (hover:none) { .diagram-tools { opacity:1; } .mermaid-diagram .diagram-tools { position:static; width:max-content; max-width:100%; box-sizing:border-box; margin:0 0 8px auto; } .diagram-tools > * { flex-shrink:0; } .diagram-tools > .diagram-play, .diagram-play select { flex-shrink:1; min-width:0; } }
  .diagram-tools button { display:grid; place-items:center; width:30px; height:30px; padding:0; border:0; border-radius:6px; background:none; color:var(--fgColor-muted); cursor:pointer; }
  .diagram-tools button:hover:not(:disabled) { background:var(--bgColor-muted); color:var(--fgColor-default); }
  .diagram-tools button:focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:-2px; }
  .diagram-tools button:disabled { opacity:.4; cursor:default; }
  .diagram-tools svg { fill:none; stroke:currentColor; stroke-width:1.6; stroke-linecap:round; stroke-linejoin:round; }
  .diagram-dialog { width:100vw; height:100dvh; max-width:none; max-height:none; margin:0; padding:0; border:0; background:var(--bgColor-default); color:var(--fgColor-default); }
  .diagram-dialog::backdrop { background:var(--bgColor-default); }
  .diagram-dialog .diagram-stage { width:100%; height:100%; touch-action:none; cursor:grab; }
  .diagram-dialog .diagram-stage:active { cursor:grabbing; }
  .diagram-dialog .diagram-stage > svg { width:100%; height:100%; max-width:none !important; padding:56px 16px 16px; }
  .diagram-dialog .diagram-tools { top:max(10px, env(safe-area-inset-top)); right:max(10px, env(safe-area-inset-right)); }
  .diagram-caption { max-width:46em; margin:10px auto 0; padding:8px 14px; border:1px solid var(--borderColor-muted); border-radius:9px; background:var(--bgColor-muted); color:var(--fgColor-default); font:500 15px/1.45 system-ui,-apple-system,sans-serif; text-align:center; }
  .diagram-caption[hidden] { display:none; }
  .diagram-dialog .diagram-caption { position:absolute; left:50%; bottom:max(16px, env(safe-area-inset-bottom)); width:max-content; max-width:min(46em, calc(100% - 32px)); margin:0; transform:translateX(-50%); font-size:17px; box-shadow:0 8px 24px color-mix(in srgb, var(--fgColor-default) 14%, transparent); pointer-events:none; }
  .diagram-play { position:relative; display:flex; align-items:center; gap:2px; margin-right:3px; padding-right:3px; border-right:1px solid var(--borderColor-muted); }
  .diagram-play select { max-width:14em; height:30px; padding:0 4px; border:0; border-radius:6px; background:none; color:var(--fgColor-default); font:500 12px/1 system-ui,-apple-system,sans-serif; cursor:pointer; }
  .diagram-play select:hover { background:var(--bgColor-muted); }
  .diagram-play button[hidden] { display:none; }
  .diagram-play .play-toggle svg { fill:currentColor; }
  .diagram-play .play-toggle { color:var(--fgColor-accent); }
  .diagram-play.playing .play-toggle svg { fill:none; }
  .diagram-play .play-stop svg { fill:currentColor; stroke:none; }
  .diagram-play .play-record svg { fill:var(--fgColor-danger); stroke:none; }
  .diagram-play .play-record.busy { width:auto; min-width:30px; padding:0 6px; color:var(--fgColor-default); font:600 11px/1 system-ui,-apple-system,sans-serif; font-variant-numeric:tabular-nums; }
  .diagram-export { position:absolute; top:calc(100% + 6px); right:0; z-index:3; display:flex; flex-direction:column; gap:2px; min-width:11em; padding:4px; border:1px solid var(--borderColor-default); border-radius:9px; background:var(--bgColor-default); box-shadow:0 8px 24px color-mix(in srgb, var(--fgColor-default) 18%, transparent); }
  .diagram-export[hidden] { display:none; }
  .diagram-tools .diagram-export button { display:flex; flex-direction:column; align-items:flex-start; gap:2px; width:100%; height:auto; padding:7px 10px; color:var(--fgColor-default); font:500 13px/1.2 system-ui,-apple-system,sans-serif; text-align:left; }
  .diagram-export button small { color:var(--fgColor-muted); font-size:11px; }
  .diagram-stage.recording :is(g.node, g.image-shape, g.node .label-container, g.node .label-container > *, g.image-shape > g:first-child > path) { transition:none !important; }
  .diagram-stage.recording :is(g.node, g.image-shape).play-active { animation:none; filter:drop-shadow(0 0 6px color-mix(in srgb, var(--fgColor-accent) 65%, transparent)); }
  .mermaid-diagram:has(.diagram-play.playing, .diagram-export:not([hidden]), .play-record.busy) .diagram-tools { opacity:1; }
  .diagram-stage :is(g.node, g.image-shape) { transition:opacity .25s; }
  .diagram-stage :is(g.node .label-container, g.node .label-container > *, g.image-shape > g:first-child > path) { transition:fill .25s, stroke .25s; }
  .diagram-stage g.node.play-active :is(.label-container, .label-container > *), .diagram-stage g.image-shape.play-active > g:first-child > path:first-child { fill:color-mix(in srgb, var(--fgColor-accent) 26%, var(--bgColor-default)) !important; }
  .diagram-stage g.node.play-active :is(.label-container, .label-container > *), .diagram-stage g.image-shape.play-active > g:first-child > path:last-child { stroke:var(--fgColor-accent) !important; stroke-width:2px !important; }
  .diagram-stage :is(g.node, g.image-shape).play-active { animation:play-glow 1.1s ease-in-out infinite alternate; }
  .diagram-stage g.node.play-done :is(.label-container, .label-container > *), .diagram-stage g.image-shape.play-done > g:first-child > path:first-child { fill:color-mix(in srgb, var(--fgColor-success) 14%, var(--bgColor-default)) !important; }
  .diagram-stage g.node.play-done :is(.label-container, .label-container > *), .diagram-stage g.image-shape.play-done > g:first-child > path:last-child { stroke:color-mix(in srgb, var(--fgColor-success) 70%, transparent) !important; }
  .diagram-stage :is(g.node, g.image-shape).play-skipped { opacity:.3; }
  .diagram-stage.focusable :is(g.node, g.image-shape) { cursor:pointer; }
  .diagram-stage :is(path[data-edge], g.edgeLabel) { transition:opacity .25s; }
  .diagram-stage.focusing :is(g.node, g.image-shape):not(.focus-on, .focus-near, .play-active) { opacity:.2; }
  .diagram-stage.focusing :is(path[data-edge], g.edgeLabel):not(.focus-near, .play-edge) { opacity:.15; }
  .diagram-stage g.node.focus-on :is(.label-container, .label-container > *), .diagram-stage g.image-shape.focus-on > g:first-child > path:first-child { fill:color-mix(in srgb, var(--fgColor-accent) 26%, var(--bgColor-default)) !important; }
  .diagram-stage g.node.focus-on :is(.label-container, .label-container > *), .diagram-stage g.image-shape.focus-on > g:first-child > path:last-child { stroke:var(--fgColor-accent) !important; stroke-width:2.5px !important; }
  .diagram-stage :is(g.node, g.image-shape).focus-on { filter:drop-shadow(0 0 8px color-mix(in srgb, var(--fgColor-accent) 70%, transparent)); }
  .diagram-stage path.focus-near:not(.play-edge) { stroke:var(--fgColor-accent) !important; stroke-width:2.5px !important; }
  .diagram-stage path.play-edge { stroke:var(--fgColor-accent) !important; stroke-width:2.5px !important; }
  .diagram-stage path.play-edge-done { stroke:color-mix(in srgb, var(--fgColor-success) 65%, var(--borderColor-default)) !important; }
  .diagram-stage .play-check circle { fill:var(--fgColor-success) !important; stroke:var(--bgColor-default) !important; stroke-width:1.5px !important; }
  .diagram-stage .play-check path { fill:none !important; stroke:var(--bgColor-default) !important; stroke-width:1.8px !important; stroke-linecap:round; stroke-linejoin:round; }
  .diagram-stage .play-token { pointer-events:none; }
  .diagram-stage .play-token > circle { fill:var(--fgColor-accent); stroke:var(--bgColor-default); stroke-width:2px; filter:drop-shadow(0 0 5px var(--fgColor-accent)); }
  .diagram-stage .play-tag rect { fill:var(--fgColor-accent); }
  .diagram-stage .play-tag text { fill:var(--bgColor-default); font:600 12px/1 system-ui,-apple-system,sans-serif; }
  @keyframes play-glow { from { filter:drop-shadow(0 0 2px color-mix(in srgb, var(--fgColor-accent) 45%, transparent)); } to { filter:drop-shadow(0 0 9px color-mix(in srgb, var(--fgColor-accent) 75%, transparent)); } }
  @media (prefers-reduced-motion:reduce) { .diagram-stage :is(g.node, g.image-shape).play-active { animation:none; filter:drop-shadow(0 0 5px color-mix(in srgb, var(--fgColor-accent) 60%, transparent)); } .diagram-stage :is(g.node, g.image-shape, g.node .label-container, g.node .label-container > *, g.image-shape > g:first-child > path) { transition:none; } }
  @media (min-width:768px) { .page { padding:32px 32px 80px; } }
"""


# The markdown reader only. Everything is scoped under .reader so it beats github-markdown.css
# by specificity rather than by source order.
READER_CSS = """
  @media (prefers-reduced-motion:no-preference) { html { scroll-behavior:smooth; } }
  ::selection { background:color-mix(in srgb, var(--fgColor-accent) 28%, transparent); }
  .bar.progress::after { content:""; position:absolute; left:0; right:0; bottom:-1px; height:2px; background:var(--fgColor-accent); transform:scaleX(var(--progress, 0)); transform-origin:left; pointer-events:none; }
  .page.reader { width:min(100%, 820px); }
  .reader .notice { border-radius:10px; }

  .reader .markdown-body { --measure:46rem; --mono:ui-monospace,"JetBrains Mono","SF Mono","Cascadia Code",Menlo,Consolas,monospace; max-width:var(--measure); margin:0 auto; font-family:ui-sans-serif,system-ui,-apple-system,"Segoe UI",Roboto,"Noto Sans",sans-serif; font-size:16px; line-height:1.7; font-feature-settings:"kern","liga","calt"; text-rendering:optimizeLegibility; -webkit-font-smoothing:antialiased; overflow-wrap:break-word; }
  .reader .markdown-body > :first-child { margin-top:0 !important; }
  .reader .markdown-body p, .reader .markdown-body li { text-wrap:pretty; }

  .reader .markdown-body :is(h1, h2, h3, h4, h5, h6) { color:var(--fgColor-default); font-weight:700; letter-spacing:-.015em; line-height:1.25; text-wrap:balance; border:0; padding:0; }
  .reader .markdown-body h1 { margin:.2em 0 .55em; font-size:clamp(2rem, 1.45rem + 2.4vw, 2.75rem); font-weight:800; letter-spacing:-.032em; line-height:1.1; }
  .reader .markdown-body h2 { margin:1.8em 0 .65em; padding-top:1.1em; border-top:1px solid var(--borderColor-muted); font-size:1.55rem; letter-spacing:-.022em; }
  .reader .markdown-body :is(h1 + h2, hr + h2, h2:first-child) { margin-top:.6em; padding-top:0; border-top:0; }
  .reader .markdown-body h3 { margin:1.6em 0 .5em; font-size:1.22rem; }
  .reader .markdown-body h4 { margin:1.6em 0 .5em; font-size:1.04rem; }
  .reader .markdown-body :is(h5, h6) { margin:1.5em 0 .4em; color:var(--fgColor-muted); font-size:.95rem; }
  .reader .markdown-body h1 + p { color:var(--fgColor-muted); font-size:1.13em; line-height:1.6; }
  .reader .markdown-body .anchor { left:-1em; color:var(--fgColor-accent); font-weight:500; }

  .reader .markdown-body a:not(.anchor) { color:var(--fgColor-accent); text-decoration:underline; text-decoration-color:color-mix(in srgb, var(--fgColor-accent) 35%, transparent); text-decoration-thickness:.08em; text-underline-offset:.2em; transition:text-decoration-color .15s; }
  .reader .markdown-body a:not(.anchor):hover { text-decoration-color:currentColor; }
  .reader .markdown-body a:focus-visible, .reader .toc a:focus-visible { outline:2px solid var(--focus-outlineColor, var(--fgColor-accent)); outline-offset:2px; border-radius:3px; }
  .reader .markdown-body strong { font-weight:650; color:var(--fgColor-default); }

  .reader .markdown-body :is(ul, ol) { padding-left:1.6em; }
  .reader .markdown-body li + li, .reader .markdown-body li > :is(ul, ol) { margin-top:.35em; }
  .reader .markdown-body li::marker { color:var(--fgColor-muted); }
  .reader .markdown-body ol > li::marker { font-variant-numeric:tabular-nums; font-weight:600; }

  .reader .markdown-body :not(pre) > code, .reader .markdown-body :not(pre) > tt { padding:.14em .4em; border:1px solid color-mix(in srgb, var(--fgColor-default) 7%, transparent); border-radius:6px; background:color-mix(in srgb, var(--fgColor-default) 7%, transparent); font-family:var(--mono); font-size:.85em; }
  .reader .markdown-body a > code { color:inherit; }

  .reader .code-block { margin:0 0 1.3em; border:1px solid var(--borderColor-default); border-radius:12px; background:var(--bgColor-muted); overflow:hidden; }
  .reader .code-block-head { display:flex; align-items:center; justify-content:space-between; gap:8px; min-height:36px; padding:4px 6px 4px 14px; border-bottom:1px solid var(--borderColor-muted); color:var(--fgColor-muted); font:12px/1 var(--mono); }
  .reader .code-block-head button { display:inline-flex; align-items:center; gap:6px; padding:5px 9px; border:1px solid transparent; border-radius:7px; background:none; color:inherit; font:600 12px/1 system-ui,sans-serif; cursor:pointer; }
  .reader .code-block-head button:hover { border-color:var(--borderColor-default); color:var(--fgColor-default); }
  .reader .code-block-head button:focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:1px; }
  .reader .code-block-head button.copied { color:var(--fgColor-success); }
  .reader .code-block-head svg { fill:currentColor; }
  .reader .code-block :is(.highlight, .snippet-clipboard-content) { margin:0; }
  .reader .markdown-body .code-block pre { margin:0; padding:14px 16px; border-radius:0; background:none; font-family:var(--mono); font-size:13.5px; line-height:1.65; tab-size:4; }
  .reader .markdown-body .code-block pre code { font-size:inherit; }

  .reader .markdown-body blockquote { margin:0 0 1.15em; padding:.15em 0 .15em 1.15em; border-left:3px solid color-mix(in srgb, var(--fgColor-accent) 45%, var(--borderColor-default)); color:var(--fgColor-muted); }

  .reader .markdown-body .markdown-alert { --alert:var(--borderColor-accent-emphasis); margin:0 0 1.3em; padding:.85em 1.15em; border:0; border-left:3px solid var(--alert); border-radius:4px 12px 12px 4px; background:color-mix(in srgb, var(--alert) 9%, transparent); color:var(--fgColor-default); }
  .reader .markdown-body .markdown-alert.markdown-alert-tip { --alert:var(--borderColor-success-emphasis); }
  .reader .markdown-body .markdown-alert.markdown-alert-important { --alert:var(--borderColor-done-emphasis); }
  .reader .markdown-body .markdown-alert.markdown-alert-warning { --alert:var(--borderColor-attention-emphasis); }
  .reader .markdown-body .markdown-alert.markdown-alert-caution { --alert:var(--borderColor-danger-emphasis); }
  .reader .markdown-body .markdown-alert .markdown-alert-title { margin-bottom:.35em; font-weight:650; }

  .reader .markdown-body table { border-collapse:separate; border-spacing:0; border:1px solid var(--borderColor-default); border-radius:12px; font-size:.93em; font-variant-numeric:tabular-nums; }
  .reader .markdown-body table :is(th, td) { padding:9px 14px; border:0; border-bottom:1px solid var(--borderColor-muted); }
  .reader .markdown-body table :is(th, td) + :is(th, td) { border-left:1px solid var(--borderColor-muted); }
  .reader .markdown-body table th { background:var(--bgColor-muted); font-weight:650; text-align:left; }
  .reader .markdown-body table th[align="center"], .reader .markdown-body table td[align="center"] { text-align:center; }
  .reader .markdown-body table th[align="right"], .reader .markdown-body table td[align="right"] { text-align:right; }
  .reader .markdown-body table :is(th, td):is([align="right"], [align="center"]) { white-space:nowrap; }
  .reader .markdown-body table tr { background:none; border:0; }
  .reader .markdown-body table tbody tr:nth-child(2n) { background:color-mix(in srgb, var(--bgColor-muted) 55%, transparent); }
  .reader .markdown-body table tr:last-child > :is(th, td) { border-bottom:0; }
  .reader .markdown-body table thead + tbody tr:first-child > * { border-top:0; }

  .reader .markdown-body .contains-task-list { padding-left:.2em; }
  .reader .markdown-body .task-list-item { list-style:none; }
  .reader .markdown-body .task-list-item + .task-list-item { margin-top:.45em; }
  .reader .markdown-body .task-list-item-checkbox { appearance:none; -webkit-appearance:none; width:1.1em; height:1.1em; margin:0 .55em 0 0; vertical-align:-.18em; border:1.5px solid var(--borderColor-default); border-radius:5px; background:var(--bgColor-default); }
  .reader .markdown-body .task-list-item-checkbox { display:inline-grid; place-content:center; }
  .reader .markdown-body .task-list-item-checkbox:checked { border-color:var(--fgColor-accent); background:var(--fgColor-accent); }
  .reader .markdown-body .task-list-item-checkbox:checked::before { content:""; width:.28em; height:.55em; margin-top:-.12em; border:solid var(--bgColor-default); border-width:0 .13em .13em 0; transform:rotate(45deg); }
  .reader .markdown-body .task-list-item:has(> .task-list-item-checkbox:checked) { color:var(--fgColor-muted); }

  .reader .markdown-body hr { width:5rem; height:3px; margin:2.6em auto; border:0; border-radius:3px; background:var(--borderColor-default); }
  .reader .markdown-body img { border-radius:10px; }
  .reader .markdown-body :is(a, p) > img:only-child { display:inline-block; }
  .reader .markdown-body details { margin:0 0 1.15em; padding:.55em 1em; border:1px solid var(--borderColor-default); border-radius:12px; }
  .reader .markdown-body details > summary { margin:-.55em -1em; padding:.55em 1em; font-weight:600; cursor:pointer; }
  .reader .markdown-body details[open] > summary { margin-bottom:.6em; border-bottom:1px solid var(--borderColor-muted); }
  .reader .markdown-body kbd { font-family:var(--mono); }
  .reader .markdown-body .footnotes { margin-top:3em; padding-top:1.2em; border-top:1px solid var(--borderColor-muted); color:var(--fgColor-muted); font-size:.88em; }
  .reader .mermaid-diagram { margin:0 0 1.3em; padding:20px 16px; border:1px solid var(--borderColor-muted); border-radius:12px; background:var(--bgColor-muted); }
  .reader .mermaid-diagram .diagram-tools { top:-14px; right:-10px; }
  @media (hover:hover) { .reader .mermaid-diagram:has(.diagram-play) { padding-top:40px; } .reader .mermaid-diagram:has(.diagram-play) .diagram-tools { top:-37px; right:-8px; } }
  .reader .markdown-body .frontmatter { display:grid; grid-template-columns:fit-content(40%) minmax(0, 1fr); align-items:baseline; gap:8px 24px; margin:0 0 2.2em; padding:14px 18px; border:1px solid var(--borderColor-muted); border-radius:12px; background:color-mix(in srgb, var(--bgColor-muted) 60%, transparent); font-size:.875em; line-height:1.55; font-variant-numeric:tabular-nums; }
  .reader .markdown-body .frontmatter dt { margin:0; padding:0; color:var(--fgColor-muted); font-size:inherit; font-style:normal; font-weight:500; }
  .reader .markdown-body .frontmatter dd { min-width:0; margin:0; padding:0; color:var(--fgColor-default); overflow-wrap:anywhere; }
  .reader .markdown-body .frontmatter time { white-space:nowrap; }
  .reader .markdown-body .frontmatter-list { display:flex; flex-wrap:wrap; gap:4px 6px; }
  .reader .markdown-body .frontmatter-pill { padding:0 9px; border-radius:999px; background:color-mix(in srgb, var(--fgColor-muted) 14%, transparent); }
  .reader .markdown-body .frontmatter-tag { background:color-mix(in srgb, var(--fgColor-accent) 14%, transparent); color:var(--fgColor-accent); font-weight:500; }
  .reader .markdown-body .frontmatter-empty { color:var(--fgColor-muted); font-style:italic; }
  .reader .markdown-body .frontmatter-text { white-space:pre-line; }
  .reader .markdown-body .frontmatter-code { display:block; padding:6px 10px; white-space:pre-wrap; }
  .reader .markdown-body .frontmatter-raw pre { margin:0 0 2.2em; }
  @media (max-width:540px) { .reader .markdown-body .frontmatter { gap:6px 16px; padding:12px 14px; } }

  .reader .crumbs { display:flex; flex-wrap:wrap; align-items:baseline; gap:2px 6px; max-width:46rem; margin:0 auto 18px; color:var(--fgColor-muted); font-size:13px; }
  .reader .crumbs a { color:inherit; text-decoration:none; }
  .reader .crumbs a:hover { color:var(--fgColor-accent); }
  .reader .crumbs a:focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:2px; border-radius:3px; }
  .reader .crumbs span { opacity:.6; }
  .reader .crumbs b { color:var(--fgColor-default); font-weight:500; }
  .reader .crumbs .note-icon { width:1.25em; height:1.25em; margin-right:5px; object-fit:contain; vertical-align:-.3em; }
  .reader .markdown-body mark { padding:.05em .2em; border-radius:3px; background:color-mix(in srgb, var(--fgColor-attention) 26%, transparent); color:inherit; }
  .reader .markdown-body .note-tag { padding:0 7px; border-radius:999px; background:color-mix(in srgb, var(--fgColor-accent) 14%, transparent); color:var(--fgColor-accent); font-size:.9em; font-weight:500; white-space:nowrap; }
  .reader .markdown-body .note-missing { color:var(--fgColor-muted); text-decoration:underline dotted color-mix(in srgb, var(--fgColor-muted) 50%, transparent); text-underline-offset:.2em; }
  .reader .markdown-body details.markdown-alert { padding:.85em 1.15em; }
  .reader .markdown-body details.markdown-alert > summary { margin:0; padding:0; border:0; list-style:none; }
  .reader .markdown-body details.markdown-alert > summary::-webkit-details-marker { display:none; }
  .reader .markdown-body details.markdown-alert > summary::after { content:"›"; display:inline-block; margin-left:.45em; transition:transform .15s ease; }
  .reader .markdown-body details.markdown-alert[open] > summary { margin-bottom:.35em; }
  .reader .markdown-body details.markdown-alert[open] > summary::after { transform:rotate(90deg); }
  .reader .markdown-body details.markdown-alert:not([open]) > summary { margin-bottom:0; }

  .reader .toc { margin:0 auto 28px; max-width:46rem; padding:6px 16px; border-color:var(--borderColor-muted); border-radius:12px; background:color-mix(in srgb, var(--bgColor-muted) 60%, transparent); }
  .reader .toc summary { color:var(--fgColor-muted); font-size:13px; }
  .reader .toc ol { margin:4px 0 10px; border-left:1px solid var(--borderColor-muted); }
  .reader .toc li { padding:0; }
  .reader .toc a { display:block; margin-left:-1px; padding:4px 0 4px 12px; border-left:2px solid transparent; color:var(--fgColor-muted); line-height:1.4; }
  .reader .toc a:hover { color:var(--fgColor-default); text-decoration:none; }
  .reader .toc a[aria-current="location"] { border-left-color:var(--fgColor-accent); color:var(--fgColor-default); font-weight:600; }

  .bar nav .review-toggle .count { min-width:16px; padding:0 4px; border-radius:8px; background:var(--fgColor-accent); color:var(--bgColor-default); font:700 11px/16px system-ui,-apple-system,sans-serif; text-align:center; }
  .bar nav .review-toggle .count[hidden] { display:none; }
  .reader .markdown-body { --review-tint:color-mix(in srgb, var(--fgColor-accent) 13%, transparent); }
  .reader .markdown-body.reviewing { position:relative; padding-left:2.9rem; }
  .reader .markdown-body.reviewing .anchor { display:none; }
  .reader .review-gutter { position:absolute; top:0; bottom:0; left:0; width:2.5rem; pointer-events:none; }
  .reader .review-line { position:absolute; left:0; width:2.4rem; height:24px; padding:0 7px 0 0; border:0; border-radius:6px; background:none; color:var(--fgColor-muted); font:12px/24px var(--mono); font-variant-numeric:tabular-nums; text-align:right; cursor:pointer; pointer-events:auto; }
  .reader .review-line:hover { color:var(--fgColor-accent); background:var(--review-tint); }
  .reader .review-line:focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:-2px; }
  .reader .review-line.commented { color:var(--fgColor-accent); font-weight:700; }
  .reader .review-line.selected { background:var(--fgColor-accent); color:var(--bgColor-default); }
  .reader .review-line[hidden] { display:none; }
  .reader .markdown-body .review-selected { border-radius:3px; background:var(--review-tint); box-shadow:0 0 0 6px var(--review-tint); }
  .reader .markdown-body tr.review-selected { background:none; box-shadow:none; }
  .reader .markdown-body .review-selected .review-selected { background:none; box-shadow:none; }
  .reader .markdown-body tr.review-selected > :is(td, th) { background:var(--review-tint); }

  .reader .code-body { position:relative; }
  .reader .code-gutter { display:none; }
  .reader .markdown-body.reviewing .code-body { display:grid; grid-template-columns:auto minmax(0, 1fr); }
  .reader .markdown-body.reviewing .code-gutter { display:block; padding:14px 0; border-right:1px solid var(--borderColor-muted); font-size:13.5px; line-height:1.65; user-select:none; }
  .reader .code-gutter .review-line { position:static; display:block; width:auto; min-width:2.8em; height:auto; padding:0 10px 0 12px; border-radius:0; font-size:inherit; line-height:inherit; }
  .reader .code-band { position:absolute; left:0; right:0; background:var(--review-tint); pointer-events:none; }

  .reader .markdown-body :is(.review-thread, .review-composer) { margin:.4em 0 1.4em; font-family:system-ui,-apple-system,"Segoe UI",sans-serif; font-size:15px; line-height:1.55; }
  .reader .markdown-body li > :is(.review-thread, .review-composer) { margin:.6em 0; }
  .reader .markdown-body .review-comment { padding:10px 14px 12px; border:1px solid var(--borderColor-default); border-left:3px solid var(--fgColor-accent); border-radius:4px 12px 12px 4px; background:var(--bgColor-muted); }
  .reader .markdown-body .review-comment + .review-comment { margin-top:8px; }
  .reader .markdown-body .review-comment.outdated { border-left-color:var(--fgColor-attention); }
  .reader .markdown-body .review-comment > header { display:flex; flex-wrap:wrap; align-items:center; gap:4px 10px; margin-bottom:6px; color:var(--fgColor-muted); font-size:13px; }
  .reader .markdown-body .review-where { padding:0; border:0; background:none; color:var(--fgColor-accent); font:600 12.5px/1.4 var(--mono); cursor:pointer; }
  .reader .markdown-body .review-where:hover { text-decoration:underline; }
  .reader .markdown-body .review-tools { display:flex; gap:2px; margin-left:auto; }
  .reader .markdown-body .review-body { margin:0; color:var(--fgColor-default); white-space:pre-wrap; overflow-wrap:anywhere; }
  .reader .markdown-body .review-note { margin:0 0 6px; color:var(--fgColor-attention); font-size:13px; font-weight:600; }
  .reader .markdown-body .review-quote { margin:0 0 8px; padding:8px 10px; border:1px solid var(--borderColor-muted); border-radius:8px; background:var(--bgColor-default); color:var(--fgColor-muted); font:12.5px/1.5 var(--mono); white-space:pre-wrap; overflow-wrap:anywhere; }
  .reader .markdown-body .review-composer { padding:12px; border:1px solid color-mix(in srgb, var(--fgColor-accent) 45%, var(--borderColor-default)); border-radius:12px; background:var(--bgColor-muted); }
  .reader .markdown-body .review-composer-title { margin:0 0 8px; color:var(--fgColor-muted); font-size:13px; font-weight:600; }
  .reader .markdown-body .review-comment .review-form { margin-top:4px; }
  .reader .review-form textarea { display:block; width:100%; min-height:6.5em; padding:10px 12px; border:1px solid var(--borderColor-default); border-radius:10px; background:var(--bgColor-default); color:var(--fgColor-default); font:inherit; font-size:16px; line-height:1.5; resize:vertical; }
  .reader .review-form textarea:focus { border-color:var(--fgColor-accent); outline:2px solid color-mix(in srgb, var(--fgColor-accent) 35%, transparent); outline-offset:0; }
  .reader .review-actions { display:flex; align-items:center; justify-content:flex-end; gap:8px; margin-top:8px; }
  .reader .review-hint { margin-right:auto; color:var(--fgColor-muted); font-size:12px; }
  @media (pointer:coarse) { .reader .review-hint { display:none; } }

  :is(.review-actions, .review-tools, .review-dock) button { display:inline-flex; align-items:center; min-height:32px; padding:0 12px; border:1px solid var(--borderColor-default); border-radius:8px; background:var(--bgColor-default); color:var(--fgColor-default); font:600 13px/1 system-ui,-apple-system,sans-serif; white-space:nowrap; cursor:pointer; }
  :is(.review-actions, .review-tools, .review-dock) button:hover { border-color:var(--fgColor-muted); }
  :is(.review-actions, .review-tools, .review-dock) button:focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:1px; }
  :is(.review-actions, .review-dock) button.primary { border-color:var(--fgColor-accent); background:var(--fgColor-accent); color:var(--bgColor-default); }
  :is(.review-actions, .review-tools, .review-dock) button:disabled { opacity:.55; cursor:progress; }
  :is(.review-actions, .review-tools, .review-dock) button[hidden] { display:none; }
  .review-tools button { min-height:26px; padding:0 8px; border-color:transparent; background:none; color:var(--fgColor-muted); }
  .review-tools button:hover { color:var(--fgColor-default); }
  .review-tools button.danger { border-color:var(--fgColor-danger); color:var(--fgColor-danger); }

  .review-dock { position:fixed; z-index:3; left:50%; bottom:max(16px, env(safe-area-inset-bottom)); display:flex; align-items:center; gap:8px; width:max-content; max-width:calc(100% - 24px); padding:8px 8px 8px 16px; border:1px solid var(--borderColor-default); border-radius:14px; background:color-mix(in srgb, var(--bgColor-default) 94%, transparent); box-shadow:0 12px 32px rgba(0,0,0,.3); backdrop-filter:blur(10px); color:var(--fgColor-default); font:14px/1.3 system-ui,-apple-system,sans-serif; transform:translateX(-50%); }
  .review-dock[hidden] { display:none; }
  .review-dock-text { flex:1; min-width:0; margin-right:4px; overflow:hidden; color:var(--fgColor-muted); text-overflow:ellipsis; white-space:nowrap; }
  .review-dock.error .review-dock-text { color:var(--fgColor-danger); }
  @media (prefers-reduced-motion:no-preference) {
    .review-dock { animation:review-dock-in .18s ease-out; }
    @keyframes review-dock-in { from { opacity:0; transform:translate(-50%, 10px); } }
  }
  body.reviewing .page.reader { padding-bottom:120px; }
  @media (min-width:768px) { .reader .markdown-body.reviewing .code-gutter { font-size:14px; } }

  @media (max-width:767px) { .reader .markdown-body table :is(th, td) { padding:8px 10px; } }
  @media (min-width:768px) { .reader .markdown-body { font-size:17px; } .reader .markdown-body .code-block pre { font-size:14px; } }
  @media (min-width:1240px) {
    .page.reader { width:100%; display:grid; grid-template-columns:minmax(0, 46rem) 232px; justify-content:center; column-gap:64px; align-items:start; }
    .page.reader > * { grid-column:1; }
    .reader .markdown-body { width:100%; margin:0; }
    .reader .toc { grid-column:2; grid-row:1 / span 3; position:sticky; top:76px; max-height:calc(100vh - 100px); margin:0; padding:0 0 0 2px; border:0; background:none; overflow:auto; scrollbar-width:thin; }
    .reader .toc summary { pointer-events:none; list-style:none; padding:0 0 6px; }
    .reader .toc summary::-webkit-details-marker { display:none; }
  }
"""


# Octicon comment-discussion. The count badge stays hidden until the file has comments.
REVIEW_BUTTON = (
    '<button type="button" class="renderer review-toggle" id="review" aria-pressed="false" '
    'aria-label="Review" title="Review" hidden>'
    '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="M1.75 1h8.5c.966 0 1.75.784 1.75 1.75v5.5A1.75 1.75 0 0 1 10.25 10H7.061l-2.574 2.573A1.458 1.458 0 0 1 2 11.543V10h-.25A1.75 1.75 0 0 1 0 8.25v-5.5C0 1.784.784 1 1.75 1ZM1.5 2.75v5.5c0 .138.112.25.25.25h1a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h3.5a.25.25 0 0 0 .25-.25v-5.5a.25.25 0 0 0-.25-.25h-8.5a.25.25 0 0 0-.25.25Zm13 2a.25.25 0 0 0-.25-.25h-.5a.75.75 0 0 1 0-1.5h.5c.966 0 1.75.784 1.75 1.75v5.5A1.75 1.75 0 0 1 14.25 12H14v1.543a1.458 1.458 0 0 1-2.487 1.03L9.22 12.28a.749.749 0 0 1 .326-1.275.749.749 0 0 1 .734.215l2.22 2.22v-2.19a.75.75 0 0 1 .75-.75h1a.25.25 0 0 0 .25-.25Z"></path></svg>'
    '<span class="count" hidden></span>'
    "</button>"
)


REVIEW_DOCK = (
    '<div class="review-dock" id="review-dock" role="region" aria-label="Review" hidden>'
    '<span class="review-dock-text" role="status"></span>'
    '<button type="button" class="primary" data-review="comment" hidden>Comment</button>'
    '<button type="button" data-review="clear" hidden>Clear</button>'
    '<button type="button" data-review="copy" hidden>Copy as prompt</button>'
    '<button type="button" data-review="done">Done</button>'
    "</div>"
)


MARKDOWN_SCRIPTS = (
    "highlight.min.js",
    "markdown-it.min.js",
    "markdown-it-footnote.min.js",
    "markdown-it-emoji.min.js",
    "purify.min.js",
)


MARKDOWN_JS = """
(() => {
const article = document.querySelector('article.markdown-body');
const toc = document.getElementById('toc');
const source = JSON.parse(document.getElementById('markdown-source').textContent);
const poub = article.dataset.poub || '';
const md = article.dataset.md || '';
const outside = /^(?:[a-z][a-z0-9+.-]*:|#|\\/)/i;
const markdownName = /\\.(?:md|markdown)$/i;
const notesData = document.getElementById('notes-links');
const noteLinks = notesData ? JSON.parse(notesData.textContent) : null;
// Obsidian callout types drawn with the closest of GitHub's five alert styles.
const CALLOUTS = {
  note: 'note', info: 'note', todo: 'note', abstract: 'note', summary: 'note', tldr: 'note',
  tip: 'tip', hint: 'tip', success: 'tip', check: 'tip', done: 'tip',
  important: 'important', question: 'important', help: 'important', faq: 'important',
  example: 'important', quote: 'important', cite: 'important',
  warning: 'warning', caution: 'warning', attention: 'warning', failure: 'warning',
  fail: 'warning', missing: 'warning', bug: 'warning',
  danger: 'caution', error: 'caution',
};
const CALLOUT_MARK = /^\\[!([\\w-]+)\\]([+-]?)[ \\t]*([^\\n]*)(?:\\n|$)/;

// GitHub's alert titles and octicons, so github-markdown.css styles them as on github.com.
const ALERTS = {
  note: ['Note', 'info', 'M0 8a8 8 0 1 1 16 0A8 8 0 0 1 0 8Zm8-6.5a6.5 6.5 0 1 0 0 13 6.5 6.5 0 0 0 0-13ZM6.5 7.75A.75.75 0 0 1 7.25 7h1a.75.75 0 0 1 .75.75v2.75h.25a.75.75 0 0 1 0 1.5h-2a.75.75 0 0 1 0-1.5h.25v-2h-.25a.75.75 0 0 1-.75-.75ZM8 6a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z'],
  tip: ['Tip', 'light-bulb', 'M8 1.5c-2.363 0-4 1.69-4 3.75 0 .984.424 1.625.984 2.304l.214.253c.223.264.47.556.673.848.284.411.537.896.621 1.49a.75.75 0 0 1-1.484.211c-.04-.282-.163-.547-.37-.847a8.456 8.456 0 0 0-.542-.68c-.084-.1-.173-.205-.268-.32C3.201 7.75 2.5 6.766 2.5 5.25 2.5 2.31 4.863 0 8 0s5.5 2.31 5.5 5.25c0 1.516-.701 2.5-1.328 3.259-.095.115-.184.22-.268.319-.207.245-.383.453-.541.681-.208.3-.33.565-.37.847a.751.751 0 0 1-1.485-.212c.084-.593.337-1.078.621-1.489.203-.292.45-.584.673-.848.075-.088.147-.173.213-.253.561-.679.985-1.32.985-2.304 0-2.06-1.637-3.75-4-3.75ZM5.75 12h4.5a.75.75 0 0 1 0 1.5h-4.5a.75.75 0 0 1 0-1.5ZM6 15.25a.75.75 0 0 1 .75-.75h2.5a.75.75 0 0 1 0 1.5h-2.5a.75.75 0 0 1-.75-.75Z'],
  important: ['Important', 'report', 'M0 1.75C0 .784.784 0 1.75 0h12.5C15.216 0 16 .784 16 1.75v9.5A1.75 1.75 0 0 1 14.25 13H8.06l-2.573 2.573A1.458 1.458 0 0 1 3 14.543V13H1.75A1.75 1.75 0 0 1 0 11.25Zm1.75-.25a.25.25 0 0 0-.25.25v9.5c0 .138.112.25.25.25h2a.75.75 0 0 1 .75.75v2.19l2.72-2.72a.749.749 0 0 1 .53-.22h6.5a.25.25 0 0 0 .25-.25v-9.5a.25.25 0 0 0-.25-.25Zm7 2.25v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 9a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z'],
  warning: ['Warning', 'alert', 'M6.457 1.047c.659-1.234 2.427-1.234 3.086 0l6.082 11.378A1.75 1.75 0 0 1 14.082 15H1.918a1.75 1.75 0 0 1-1.543-2.575Zm1.763.707a.25.25 0 0 0-.44 0L1.698 13.132a.25.25 0 0 0 .22.368h12.164a.25.25 0 0 0 .22-.368Zm.53 3.996v2.5a.75.75 0 0 1-1.5 0v-2.5a.75.75 0 0 1 1.5 0ZM9 11a1 1 0 1 1-2 0 1 1 0 0 1 2 0Z'],
  caution: ['Caution', 'stop', 'M4.47.22A.749.749 0 0 1 5 0h6c.199 0 .389.079.53.22l4.25 4.25c.141.14.22.331.22.53v6a.749.749 0 0 1-.22.53l-4.25 4.25A.749.749 0 0 1 11 16H5a.749.749 0 0 1-.53-.22L.22 11.53A.749.749 0 0 1 0 11V5c0-.199.079-.389.22-.53Zm.84 1.28L1.5 5.31v5.38l3.81 3.81h5.38l3.81-3.81V5.31L10.69 1.5ZM8 4a.75.75 0 0 1 .75.75v3.5a.75.75 0 0 1-1.5 0v-3.5A.75.75 0 0 1 8 4Zm0 8a1 1 0 1 1 0-2 1 1 0 0 1 0 2Z'],
};
const ALERT_MARK = /^\\[!(note|tip|important|warning|caution)\\][ \\t]*(?:\\n|$)/i;
const TASK_MARK = /^\\[([ xX])\\][ \\t]+/;

// Front matter: a YAML block between --- lines at the very top of the file, shown as a
// small properties panel. Only a subset of YAML is read; anything else is shown as written.
const FRONT_KEY = /^([A-Za-z0-9_][\\w .\\/-]*?)[ \\t]*:(?:[ \\t]+(.*?))?[ \\t]*$/;
const FRONT_DATE = /^(\\d{4})-(\\d{2})-(\\d{2})(?:[T ](\\d{2}):(\\d{2})(?::(\\d{2})(?:\\.\\d+)?)?(Z|[+-]\\d{2}:?\\d{2})?)?$/;
const FRONT_LIMIT = 200;

function readFrontMatter(text) {
  const lines = text.split('\\n', FRONT_LIMIT + 2);
  if (!/^---[ \\t]*$/.test(lines[0])) return null;
  let close = 1;
  while (close < lines.length && close <= FRONT_LIMIT && !/^(?:---|\\.\\.\\.)[ \\t]*$/.test(lines[close])) close++;
  if (close >= lines.length || close > FRONT_LIMIT) return null;
  const inner = lines.slice(1, close);
  const first = inner.find((line) => line.trim() && !/^\\s*#/.test(line));
  if (!first || /^\\s/.test(first) || !FRONT_KEY.test(first)) return null;
  return { lines: close + 1, yaml: inner.join('\\n'), entries: frontEntries(inner) };
}

function frontEntries(lines) {
  const entries = [];
  for (const line of lines) {
    const key = /^\\s/.test(line) ? null : FRONT_KEY.exec(line);
    if (key) entries.push({ key: key[1], inline: key[2] || '', rest: [] });
    else if (!line.trim() || /^\\s*#/.test(line)) entries.length && entries[entries.length - 1].rest.push(line);
    else if (entries.length) entries[entries.length - 1].rest.push(line);
    else return null;
  }
  return entries.map(frontValue);
}

function frontUnquote(text) {
  text = text.trim();
  if (/^"(?:[^"\\\\]|\\\\.)*"$/.test(text)) return text.slice(1, -1).replace(/\\\\(.)/g, (all, c) => (c === 'n' ? '\\n' : c === 't' ? '\\t' : c));
  if (/^'(?:[^']|'')*'$/.test(text)) return text.slice(1, -1).replace(/''/g, "'");
  return text.replace(/\\s+#.*$/, '');
}

function frontSplit(text) {
  const items = [];
  let current = '', quote = '';
  for (const c of text) {
    if (quote) { if (c === quote) quote = ''; current += c; }
    else if (c === '"' || c === "'") { quote = c; current += c; }
    else if (c === ',') { items.push(current); current = ''; }
    else current += c;
  }
  if (current.trim() || items.length) items.push(current);
  return items.map(frontUnquote).filter((item) => item !== '');
}

function frontValue({ key, inline, rest }) {
  const trimmed = inline.trim();
  const quoted = /^("(?:[^"\\\\]|\\\\.)*"|'(?:[^']|'')*')(?:\\s+#.*)?$/.exec(trimmed);
  const value = quoted ? quoted[1] : trimmed.replace(/(?:^|\\s+)#.*$/, '');
  const body = rest.filter((line) => line.trim() && !/^\\s*#/.test(line));
  const indent = body.length ? Math.min(...body.map((line) => /^\\s*/.exec(line)[0].length)) : 0;
  const block = rest.map((line) => line.slice(indent)).join('\\n').replace(/\\s+$/, '');
  const raw = () => ({ key, kind: 'raw', value: [value, block].filter(Boolean).join('\\n') });
  if (/^[|>][+-]?\\d*$/.test(value)) {
    return { key, kind: 'text', value: value[0] === '>' ? block.replace(/([^\\n])\\n(?=[^\\n])/g, '$1 ') : block };
  }
  if (!value.trim()) {
    if (!body.length) return { key, kind: 'empty' };
    if (body.every((line) => /^\\s*-(?:\\s+|$)/.test(line))) {
      return { key, kind: 'list', value: body.map((line) => frontUnquote(line.replace(/^\\s*-\\s*/, ''))).filter((item) => item !== '') };
    }
    return raw();
  }
  if (/^\\[.*\\]$/.test(value.trim()) && !body.length) return { key, kind: 'list', value: frontSplit(value.trim().slice(1, -1)) };
  if (/^[{&*!]/.test(value.trim())) return raw();
  if (body.length) {
    if (/^["']/.test(value.trim())) return raw();
    return { key, kind: 'scalar', value: [value, ...body].map((line) => line.trim()).join(' ') };
  }
  return { key, kind: 'scalar', value: frontUnquote(value) };
}

const frontEscape = (text) => String(text).replace(/[&<>"']/g, (c) => ({ '&': '&amp;', '<': '&lt;', '>': '&gt;', '"': '&quot;', "'": '&#39;' })[c]);

function frontDate(text) {
  const match = FRONT_DATE.exec(text);
  if (!match) return null;
  const [, year, month, day, hour, minute, second, zone] = match;
  const date = hour === undefined
    ? new Date(Number(year), Number(month) - 1, Number(day))
    : zone
      ? new Date(text.replace(' ', 'T'))
      : new Date(Number(year), Number(month) - 1, Number(day), Number(hour), Number(minute), Number(second || 0));
  if (Number.isNaN(date.getTime()) || date.getMonth() !== Number(month) - 1) return null;
  const style = hour === undefined ? { dateStyle: 'medium' } : { dateStyle: 'medium', timeStyle: 'short' };
  return '<time datetime="' + frontEscape(text.replace(' ', 'T')) + '" title="' + frontEscape(text) + '">' + frontEscape(new Intl.DateTimeFormat(undefined, style).format(date)) + '</time>';
}

function frontScalar(text) {
  if (text === '' || /^(?:null|~)$/i.test(text)) return '<span class="frontmatter-empty">empty</span>';
  if (/^(?:true|false)$/i.test(text)) return /^t/i.test(text) ? 'Yes' : 'No';
  const date = frontDate(text);
  if (date) return date;
  if (/^https?:\\/\\/\\S+$/i.test(text)) {
    const label = text.replace(/^https?:\\/\\//i, '').replace(/\\/$/, '');
    return '<a href="' + frontEscape(text) + '" title="' + frontEscape(text) + '">' + frontEscape(label) + '</a>';
  }
  return frontEscape(text.replace(/\\[\\[([^\\]|]+)(?:\\|([^\\]]+))?\\]\\]/g, (all, target, alias) => alias || target));
}

function frontPanel(front, map) {
  const where = map ? ' data-line="' + (map[0] + 1) + '" data-line-end="' + map[1] + '"' : '';
  if (!front.entries || !front.entries.length) {
    return '<div class="frontmatter frontmatter-raw"' + where + '><pre><code>' + frontEscape(front.yaml) + '</code></pre></div>\\n';
  }
  let html = '<dl class="frontmatter"' + where + '>';
  for (const entry of front.entries) {
    const tags = /^tags?$/i.test(entry.key);
    let items = entry.kind === 'list' ? entry.value : null;
    if (tags && entry.kind === 'scalar') items = entry.value.split(/[\\s,]+/).filter(Boolean);
    let value;
    if (items) {
      value = items.length
        ? '<span class="frontmatter-list">' + items.map((item) => '<span class="frontmatter-pill' + (tags ? ' frontmatter-tag' : '') + '">' + (tags ? frontEscape('#' + item.replace(/^#/, '')) : frontScalar(item)) + '</span>').join('') + '</span>'
        : '<span class="frontmatter-empty">empty</span>';
    } else if (entry.kind === 'text') value = '<span class="frontmatter-text">' + frontEscape(entry.value) + '</span>';
    else if (entry.kind === 'raw') value = '<code class="frontmatter-code">' + frontEscape(entry.value) + '</code>';
    else if (entry.kind === 'empty') value = '<span class="frontmatter-empty">empty</span>';
    else value = frontScalar(entry.value);
    html += '<dt>' + frontEscape(entry.key) + '</dt><dd>' + value + '</dd>';
  }
  return html + '</dl>\\n';
}

function frontMatterPlugin(markdown) {
  markdown.block.ruler.before('table', 'sharei_frontmatter', (state, startLine, endLine, silent) => {
    if (startLine !== 0 || state.parentType !== 'root' || state.sCount[0] !== 0) return false;
    const front = readFrontMatter(state.src);
    if (!front || front.lines > endLine) return false;
    if (silent) return true;
    const token = state.push('front_matter', '', 0);
    token.block = true;
    token.map = [0, front.lines];
    token.meta = front;
    state.line = front.lines;
    return true;
  });
  markdown.renderer.rules.front_matter = (tokens, index) => frontPanel(tokens[index].meta, tokens[index].map);
}

// Task lists, alerts and table alignment, written the way GitHub's renderer writes them.
function githubFlavour(markdown) {
  markdown.core.ruler.push('sharei_github', (state) => {
    const tokens = state.tokens;
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index];
      if ((token.type === 'th_open' || token.type === 'td_open') && token.attrGet('style')) {
        const align = /text-align:(left|right|center)/.exec(token.attrGet('style'));
        token.attrs = token.attrs.filter((attr) => attr[0] !== 'style');
        if (align) token.attrSet('align', align[1]);
      }
      const inline = tokens[index + 2];
      if (!inline || inline.type !== 'inline' || tokens[index + 1].type !== 'paragraph_open') continue;
      const children = inline.children || [];
      if (token.type === 'blockquote_open') {
        const match = (noteLinks ? CALLOUT_MARK : ALERT_MARK).exec(inline.content);
        if (!match) continue;
        const type = match[1].toLowerCase();
        const kind = noteLinks ? CALLOUTS[type] || 'note' : type;
        const title = noteLinks ? match[3].trim() || type[0].toUpperCase() + type.slice(1) : ALERTS[kind][0];
        const fold = noteLinks ? match[2] : '';
        let depth = 0, close = index;
        for (; close < tokens.length; close++) {
          if (tokens[close].type === 'blockquote_open') depth++;
          else if (tokens[close].type === 'blockquote_close' && --depth === 0) break;
        }
        token.meta = { alert: kind, title: title, fold: fold };
        tokens[close].meta = { alert: kind, fold: fold };
        const marker = match[0].trim();
        let consumed = '';
        while (children.length && children[0].type === 'text' && consumed.length < marker.length) consumed += children.shift().content;
        if (children.length && /^(soft|hard)break$/.test(children[0].type)) children.shift();
        if (!children.length) tokens[index + 1].hidden = tokens[index + 3].hidden = true;
      } else if (token.type === 'list_item_open') {
        const match = TASK_MARK.exec(inline.content);
        if (!match || !children.length || children[0].type !== 'text' || !children[0].content.startsWith(match[0])) continue;
        children[0].content = children[0].content.slice(match[0].length);
        const box = new state.Token('html_inline', '', 0);
        box.content = '<input type="checkbox" class="task-list-item-checkbox" disabled' + (match[1] === ' ' ? '' : ' checked') + '> ';
        children.unshift(box);
        token.attrJoin('class', 'task-list-item');
        for (let back = index - 1; back >= 0; back--) {
          const list = tokens[back];
          if (list.level === token.level - 1 && /^(bullet|ordered)_list_open$/.test(list.type)) {
            if (!(list.attrGet('class') || '').includes('contains-task-list')) list.attrJoin('class', 'contains-task-list');
            break;
          }
        }
      }
    }
  });
  // Source line ranges (1-based, inclusive) for review comments. A tight list hides its
  // paragraphs, so their range goes on the list item.
  markdown.core.ruler.push('sharei_lines', (state) => {
    const tokens = state.tokens;
    for (let index = 0; index < tokens.length; index++) {
      const token = tokens[index];
      if (!token.map || !/^(paragraph_open|heading_open|tr_open|hr)$/.test(token.type)) continue;
      const target = token.hidden ? tokens[index - 1] : token;
      if (!target || (token.hidden && target.type !== 'list_item_open')) continue;
      target.attrSet('data-line', String(token.map[0] + 1));
      target.attrSet('data-line-end', String(Math.max(token.map[1], token.map[0] + 1)));
    }
  });
  const lines = (token, first) => token.map
    ? ' data-line="' + (token.map[0] + 1) + '" data-line-end="' + token.map[1] + '" data-code="' + first + '"'
    : '';
  const rules = markdown.renderer.rules;
  rules.code_block = (tokens, index) => {
    const token = tokens[index];
    return '<pre' + lines(token, token.map ? token.map[0] + 1 : 0) + '><code>' + markdown.utils.escapeHtml(token.content.replace(/\\n$/, '')) + '</code></pre>\\n';
  };
  rules.blockquote_open = (tokens, index, options, env, self) => {
    const meta = tokens[index].meta;
    if (!meta || !meta.alert) return self.renderToken(tokens, index, options);
    const [, icon, path] = ALERTS[meta.alert];
    const svg = '<svg class="octicon octicon-' + icon + ' mr-2" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="' + path + '"></path></svg>';
    const title = markdown.utils.escapeHtml(meta.title);
    const classes = 'markdown-alert markdown-alert-' + meta.alert;
    // A foldable callout ([!type]- or [!type]+) opens closed or open.
    if (meta.fold) return '<details class="' + classes + '"' + (meta.fold === '+' ? ' open' : '') + '><summary class="markdown-alert-title">' + svg + title + '</summary>\\n';
    return '<div class="' + classes + '"><p class="markdown-alert-title">' + svg + title + '</p>\\n';
  };
  rules.blockquote_close = (tokens, index, options, env, self) => {
    const meta = tokens[index].meta;
    if (!meta || !meta.alert) return self.renderToken(tokens, index, options);
    return meta.fold ? '</details>\\n' : '</div>\\n';
  };
  rules.fence = (tokens, index) => {
    const token = tokens[index];
    const text = token.content.replace(/\\n$/, '');
    const language = (token.info.trim().split(/\\s+/)[0] || '').toLowerCase().replace(/[^a-z0-9_+#.-]/g, '');
    const where = lines(token, token.map ? token.map[0] + 2 : 0);
    if (!language) return '<pre class="notranslate"' + where + '><code>' + markdown.utils.escapeHtml(text) + '</code></pre>\\n';
    const body = language !== 'mermaid' && window.hljs && hljs.getLanguage(language)
      ? hljs.highlight(text, { language: language, ignoreIllegals: true }).value
      : markdown.utils.escapeHtml(text);
    // The highlight-source-* wrapper is what the mermaid step below looks for.
    return '<div class="highlight highlight-source-' + language + '"' + where + '><pre class="notranslate">' + body + '</pre></div>\\n';
  };
  if (rules.footnote_ref) {
    rules.footnote_caption = (tokens, index) => String(tokens[index].meta.id + 1);
    const footnoteRef = rules.footnote_ref;
    rules.footnote_ref = (...args) => footnoteRef(...args).replace('<a ', '<a data-footnote-ref aria-describedby="footnote-label" ');
    rules.footnote_block_open = () => '<section class="footnotes" data-footnotes>\\n<h2 id="footnote-label" class="sr-only">Footnotes</h2>\\n<ol>\\n';
    rules.footnote_block_close = () => '</ol>\\n</section>\\n';
  }
}

// Raw HTML in the file is untrusted: DOMPurify drops scripts, handlers and javascript: URLs,
// and the fragment stays in its inert document until its links are rewritten below.
function sanitize(markup) {
  return DOMPurify.sanitize(markup, {
    RETURN_DOM_FRAGMENT: true,
    FORBID_TAGS: ['style', 'form', 'button', 'textarea', 'select'],
    FORBID_ATTR: ['style'],
  });
}

function noteSlug(text) {
  return text.trim().toLowerCase().replace(/[^\\p{L}\\p{N}\\s_-]/gu, '').replace(/\\s/g, '-') || 'section';
}

function noteAnchor(heading) {
  if (!heading.startsWith('#') || heading.startsWith('#^')) return '';
  return '#' + noteSlug(heading.slice(1).split('#').pop());
}

// [[target#heading|alias]] and ![[file|300]]. The server resolved every target into
// noteLinks; one it left out, or mapped to null, is not shared and stays plain text.
function wikilink(inner, embed, escape) {
  const bar = inner.indexOf('|');
  const ref = bar < 0 ? inner : inner.slice(0, bar);
  const alias = bar < 0 ? '' : inner.slice(bar + 1).trim();
  const at = ref.search(/[#^]/);
  const target = (at < 0 ? ref : ref.slice(0, at)).trim();
  const heading = at < 0 ? '' : ref.slice(at);
  const anchor = noteAnchor(heading);
  const size = /^(\\d+)(?:x(\\d+))?$/.exec(alias);
  const parts = heading && !heading.startsWith('#^') ? heading.slice(1).split('#').filter(Boolean) : [];
  const label = (size ? '' : alias) || [target, ...parts].filter(Boolean).join(' › ');
  if (!target) return anchor ? '<a href="' + escape(anchor) + '">' + escape(label) + '</a>' : escape(label);
  const entry = noteLinks[target];
  if (!entry) return '<span class="note-missing">' + escape(label) + '</span>';
  if (embed && entry.src) {
    const dimensions = size ? ' width="' + size[1] + '"' + (size[2] ? ' height="' + size[2] + '"' : '') : '';
    return '<img src="' + escape(entry.src) + '" alt="' + escape(size ? target : alias || target) + '"' + dimensions + '>';
  }
  return '<a href="' + escape(entry.href + anchor) + '">' + escape(label) + '</a>';
}

// Obsidian comments are hidden in reading view; fenced code keeps its %% as written.
function stripComments(text) {
  return text.replace(/^(`{3,}|~{3,})[^\\n]*\\n[\\s\\S]*?^\\1[ \\t]*$|%%[\\s\\S]*?%%/gm, (all, fence) => (fence ? all : ''));
}

function obsidianFlavour(markdown) {
  const escape = markdown.utils.escapeHtml;
  markdown.inline.ruler.before('link', 'obsidian_wikilink', (state, silent) => {
    const start = state.pos;
    const embed = state.src.charCodeAt(start) === 0x21;
    const open = start + (embed ? 1 : 0);
    if (state.src.charCodeAt(open) !== 0x5b || state.src.charCodeAt(open + 1) !== 0x5b) return false;
    const close = state.src.indexOf(']]', open + 2);
    if (close < 0 || close + 2 > state.posMax) return false;
    const inner = state.src.slice(open + 2, close).replace(/\\\\\\|/g, '|');
    if (!inner.trim() || /[\\[\\]\\n]/.test(inner)) return false;
    if (!silent) state.push('html_inline', '', 0).content = wikilink(inner, embed, escape);
    state.pos = close + 2;
    return true;
  });
  markdown.inline.ruler.before('emphasis', 'obsidian_mark', (state, silent) => {
    const start = state.pos;
    if (state.src.charCodeAt(start) !== 0x3d || state.src.charCodeAt(start + 1) !== 0x3d) return false;
    const match = /^==(?=[^\\s=])([^\\n]*?[^\\s=])==/.exec(state.src.slice(start, state.posMax));
    if (!match) return false;
    if (!silent) {
      const max = state.posMax;
      state.push('mark_open', 'mark', 1);
      state.pos = start + 2;
      state.posMax = start + 2 + match[1].length;
      state.md.inline.tokenize(state);
      state.posMax = max;
      state.push('mark_close', 'mark', -1);
    }
    state.pos = start + match[0].length;
    return true;
  });
  markdown.inline.ruler.before('emphasis', 'obsidian_tag', (state, silent) => {
    const start = state.pos;
    if (state.src.charCodeAt(start) !== 0x23 || (start > 0 && !/\\s/.test(state.src[start - 1]))) return false;
    const match = /^#([\\p{L}\\p{N}_\\/-]+)/u.exec(state.src.slice(start, state.posMax));
    if (!match || /^[\\d\\/-]+$/.test(match[1])) return false;
    if (!silent) state.push('html_inline', '', 0).content = '<span class="note-tag">#' + escape(match[1]) + '</span>';
    state.pos = start + match[0].length;
    return true;
  });
  // Plain markdown links and images go through the same map, so /ZAttachments/x.png and
  // ../Other.md find their file, and anything unshared loses its link.
  markdown.core.ruler.push('obsidian_links', (state) => {
    for (const block of state.tokens) {
      for (const token of block.children || []) {
        if (token.type !== 'link_open' && token.type !== 'image') continue;
        const name = token.type === 'image' ? 'src' : 'href';
        const value = token.attrGet(name) || '';
        if (/^(?:[a-z][a-z0-9+.-]*:|#)/i.test(value)) continue;
        let path = value.split(/[?#]/)[0];
        const hash = value.includes('#') ? value.slice(value.indexOf('#')) : '';
        try { path = decodeURIComponent(path); } catch (error) { /* keep it encoded */ }
        const entry = noteLinks[path.trim()];
        if (!entry || (name === 'src' && !entry.src)) {
          token.meta = { unlinked: true };
          continue;
        }
        let heading = hash;
        try { heading = decodeURIComponent(hash); } catch (error) { /* keep it encoded */ }
        token.attrSet(name, name === 'src' ? entry.src : entry.href + noteAnchor(heading));
      }
    }
  });
  const rules = markdown.renderer.rules;
  const plain = (tokens, index, options, env, self) => self.renderToken(tokens, index, options);
  const linkOpen = rules.link_open || plain;
  const linkClose = rules.link_close || plain;
  const image = rules.image;
  rules.link_open = (tokens, index, options, env, self) => {
    const unlinked = Boolean(tokens[index].meta && tokens[index].meta.unlinked);
    (env.unlinked = env.unlinked || []).push(unlinked);
    return unlinked ? '<span class="note-missing">' : linkOpen(tokens, index, options, env, self);
  };
  rules.link_close = (tokens, index, options, env, self) =>
    (env.unlinked || []).pop() ? '</span>' : linkClose(tokens, index, options, env, self);
  rules.image = (tokens, index, options, env, self) =>
    tokens[index].meta && tokens[index].meta.unlinked
      ? escape(self.renderInlineAsText(tokens[index].children, options, env))
      : image(tokens, index, options, env, self);
}

let markdown = null;
function renderLocal() {
  try {
    if (!markdown) {
      markdown = window.markdownit({ html: true, linkify: true, breaks: 'breaks' in article.dataset });
      // Without a scheme, README.md would become a link to a Moldovan domain.
      markdown.linkify.set({ fuzzyLink: false });
      if (window.markdownitFootnote) markdown.use(window.markdownitFootnote);
      if (window.markdownitEmoji) markdown.use(window.markdownitEmoji);
      frontMatterPlugin(markdown);
      githubFlavour(markdown);
      if (noteLinks) obsidianFlavour(markdown);
    }
    return sanitize(markdown.render(noteLinks ? stripComments(source) : source));
  } catch (error) {
    console.error('markdown rendering failed', error);
    const pre = document.createElement('pre');
    pre.textContent = source;
    const fragment = document.createDocumentFragment();
    fragment.append(pre);
    return fragment;
  }
}

// Files are flat in the drop folder, so a relative ./img/a.png is looked up as a.png next to this file.
function local(value) {
  if (!value || outside.test(value)) return null;
  const match = value.match(/^([^?#]*)(?:\\?[^#]*)?(#.*)?$/);
  let path = match[1];
  try { path = decodeURIComponent(path); } catch (error) { /* keep it encoded */ }
  const name = path.split('/').filter(Boolean).pop();
  return name ? { name: name, hash: match[2] || '' } : null;
}

let diagramCount = 0;
// Mermaid's base theme recoloured from the page, so diagrams follow the picked theme.
function diagramColours(dark) {
  const style = getComputedStyle(article);
  const context = document.createElement('canvas').getContext('2d');
  const rgb = (name) => {
    context.fillStyle = '#808080';
    context.fillStyle = style.getPropertyValue(name).trim() || '#808080';
    const value = context.fillStyle;
    if (value[0] === '#') return [1, 3, 5].map((at) => parseInt(value.slice(at, at + 2), 16));
    return value.match(/[\\d.]+/g).slice(0, 3).map(Number);
  };
  const hex = (colour) => '#' + colour.map((part) => Math.round(part).toString(16).padStart(2, '0')).join('');
  const mix = (front, back, amount) => front.map((part, index) => part * amount + back[index] * (1 - amount));
  const back = rgb('--bgColor-muted');
  const ink = rgb('--fgColor-default');
  const muted = rgb('--fgColor-muted');
  const accent = rgb('--fgColor-accent');
  const line = rgb('--borderColor-default');
  const node = hex(mix(accent, back, dark ? 0.2 : 0.14));
  return {
    darkMode: dark,
    background: hex(back),
    mainBkg: node,
    primaryColor: node,
    primaryBorderColor: hex(mix(accent, back, 0.65)),
    primaryTextColor: hex(ink),
    secondaryColor: hex(mix(muted, back, 0.16)),
    secondaryBorderColor: hex(line),
    secondaryTextColor: hex(ink),
    tertiaryColor: hex(mix(ink, back, 0.05)),
    tertiaryBorderColor: hex(line),
    tertiaryTextColor: hex(ink),
    textColor: hex(ink),
    lineColor: hex(muted),
    clusterBkg: hex(mix(ink, back, 0.04)),
    clusterBorder: hex(line),
    edgeLabelBackground: hex(back),
    noteBkgColor: hex(mix(accent, back, 0.08)),
    noteBorderColor: hex(line),
    noteTextColor: hex(ink),
    fontFamily: style.fontFamily,
    fontSize: '15px',
    dropShadow: 'none',
    useGradient: false,
  };
}

const DIAGRAM_ICONS = {
  out: '<path d="M3 8h10"/>',
  in: '<path d="M3 8h10M8 3v10"/>',
  fit: '<path d="M13 8a5 5 0 1 1-1.46-3.54M13.5 2v3h-3"/>',
  full: '<path d="M6 2H2v4M10 2h4v4M6 14H2v-4M10 14h4v-4"/>',
  close: '<path d="M3.5 3.5l9 9M12.5 3.5l-9 9"/>',
  play: '<path d="M5 3.2v9.6L12.6 8z"/>',
  pause: '<path d="M5.5 3.5v9M10.5 3.5v9"/>',
  stop: '<rect x="4" y="4" width="8" height="8" rx="1.2"/>',
  record: '<circle cx="8" cy="8" r="4.6"/>',
  back: '<path d="M10.5 3.5L6 8l4.5 4.5M4 3.5v9"/>',
  next: '<path d="M5.5 3.5L10 8l-4.5 4.5M12 3.5v9"/>',
};
const diagramIcon = (name) => '<svg viewBox="0 0 16 16" width="16" height="16" aria-hidden="true">' + DIAGRAM_ICONS[name] + '</svg>';
let diagramDialog = null;

// Zooming and panning rewrite the viewBox, so the diagram stays sharp and keeps its place in the page.
function panZoom(holder, scenarios) {
  const svg = holder.querySelector(':scope > svg');
  const box = svg && svg.viewBox.baseVal;
  if (!box || !box.width || !box.height) return;
  const home = { x: box.x, y: box.y, w: box.width, h: box.height };
  const MAX = 12;
  let view = Object.assign({}, home);

  const stage = document.createElement('div');
  stage.className = 'diagram-stage';
  const tools = document.createElement('div');
  tools.className = 'diagram-tools';
  const button = (name, label) => {
    const element = document.createElement('button');
    element.type = 'button';
    element.title = label;
    element.setAttribute('aria-label', label);
    element.innerHTML = diagramIcon(name);
    tools.append(element);
    return element;
  };
  const outButton = button('out', 'Zoom out');
  const inButton = button('in', 'Zoom in');
  const fitButton = button('fit', 'Fit');
  const fullButton = button('full', 'Full screen');
  stage.append(tools, svg);
  holder.append(stage);
  stage.diagramPlay = scenarios.length ? playDiagram(stage, svg, tools, scenarios, home) : null;
  stage.diagramFocus = focusDiagram(stage, svg) || null;
  holder.title = 'Drag to move, Ctrl+scroll or pinch to zoom' + (stage.classList.contains('focusable') ? ', click a box to highlight it' : '');

  const full = () => Boolean(diagramDialog && diagramDialog.open && diagramDialog.contains(stage));
  const zoomed = () => view.w < home.w - 1e-9;
  function apply() {
    svg.setAttribute('viewBox', [view.x, view.y, view.w, view.h].join(' '));
    stage.classList.toggle('zoomed', zoomed());
    outButton.disabled = fitButton.disabled = !zoomed();
    inButton.disabled = view.w <= home.w / MAX + 1e-9;
  }
  function clamp() {
    view.x = Math.min(Math.max(view.x, home.x), home.x + home.w - view.w);
    view.y = Math.min(Math.max(view.y, home.y), home.y + home.h - view.h);
  }
  function center() {
    const rect = svg.getBoundingClientRect();
    return [rect.left + rect.width / 2, rect.top + rect.height / 2];
  }
  function zoomAt(factor, clientX, clientY) {
    const matrix = svg.getScreenCTM();
    if (!matrix) return;
    const point = new DOMPoint(clientX, clientY).matrixTransform(matrix.inverse());
    const width = Math.min(home.w, Math.max(home.w / MAX, view.w / factor));
    const ratio = width / view.w;
    view = { x: point.x - (point.x - view.x) * ratio, y: point.y - (point.y - view.y) * ratio, w: width, h: view.h * ratio };
    clamp();
    apply();
  }
  function panBy(dx, dy) {
    const matrix = svg.getScreenCTM();
    if (!matrix || !matrix.a) return;
    view.x -= dx / matrix.a;
    view.y -= dy / matrix.d;
    clamp();
    apply();
  }
  function reset() {
    view = Object.assign({}, home);
    apply();
  }

  outButton.addEventListener('click', () => zoomAt(1 / 1.5, ...center()));
  inButton.addEventListener('click', () => zoomAt(1.5, ...center()));
  fitButton.addEventListener('click', reset);
  fullButton.addEventListener('click', () => {
    if (full()) {
      diagramDialog.close();
      return;
    }
    if (!diagramDialog) {
      diagramDialog = document.createElement('dialog');
      diagramDialog.className = 'diagram-dialog';
      diagramDialog.setAttribute('aria-label', 'Diagram');
      document.body.append(diagramDialog);
      const previousBusy = window.liveBusy;
      window.liveBusy = () => diagramDialog.open || (previousBusy ? previousBusy() : false);
    }
    holder.style.minHeight = holder.offsetHeight + 'px';
    diagramDialog.append(stage);
    fullButton.innerHTML = diagramIcon('close');
    fullButton.title = 'Close';
    fullButton.setAttribute('aria-label', 'Close');
    diagramDialog.addEventListener('close', () => {
      holder.append(stage);
      holder.style.minHeight = '';
      fullButton.innerHTML = diagramIcon('full');
      fullButton.title = 'Full screen';
      fullButton.setAttribute('aria-label', 'Full screen');
      reset();
    }, { once: true });
    diagramDialog.showModal();
    reset();
    fullButton.focus();
  });

  stage.addEventListener('keydown', (event) => {
    if (!full() || event.ctrlKey || event.metaKey || event.altKey) return;
    const step = 60;
    const moves = { ArrowLeft: [step, 0], ArrowRight: [-step, 0], ArrowUp: [0, step], ArrowDown: [0, -step] };
    if (event.key === '+' || event.key === '=') zoomAt(1.5, ...center());
    else if (event.key === '-') zoomAt(1 / 1.5, ...center());
    else if (event.key === '0') reset();
    else if (moves[event.key]) panBy(...moves[event.key]);
    else return;
    event.preventDefault();
  });

  stage.addEventListener('wheel', (event) => {
    if (!full() && !event.ctrlKey && !event.metaKey) return;
    event.preventDefault();
    const delta = event.deltaY * (event.deltaMode === 1 ? 33 : event.deltaMode === 2 ? 400 : 1);
    zoomAt(Math.exp(-Math.max(-100, Math.min(100, delta)) * (event.ctrlKey ? 0.01 : 0.0025)), event.clientX, event.clientY);
  }, { passive: false });

  stage.addEventListener('dblclick', (event) => {
    if (event.target.closest('.diagram-tools')) return;
    zoomAt(event.shiftKey ? 1 / 2 : 2, event.clientX, event.clientY);
  });

  // One pointer drags, two pinch. Touch at the fitted size is left to the page so it still scrolls.
  const pointers = new Map();
  stage.addEventListener('pointerdown', (event) => {
    if (event.button !== 0 || event.target.closest('.diagram-tools')) return;
    if (event.pointerType === 'touch' && !zoomed() && !full() && !pointers.size) {
      pointers.set(event.pointerId, { x: event.clientX, y: event.clientY, passive: true });
      return;
    }
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    stage.setPointerCapture(event.pointerId);
    if (event.pointerType === 'mouse') event.preventDefault();
  });
  stage.addEventListener('pointermove', (event) => {
    const last = pointers.get(event.pointerId);
    if (!last) return;
    const others = [...pointers].filter(([id]) => id !== event.pointerId).map(([, point]) => point);
    pointers.set(event.pointerId, { x: event.clientX, y: event.clientY });
    if (others.length === 1) {
      const other = others[0];
      const before = Math.hypot(last.x - other.x, last.y - other.y);
      const after = Math.hypot(event.clientX - other.x, event.clientY - other.y);
      if (before > 0) zoomAt(after / before, (event.clientX + other.x) / 2, (event.clientY + other.y) / 2);
      panBy((event.clientX - last.x) / 2, (event.clientY - last.y) / 2);
    } else if (!others.length && !last.passive) {
      panBy(event.clientX - last.x, event.clientY - last.y);
    }
  });
  const release = (event) => pointers.delete(event.pointerId);
  stage.addEventListener('pointerup', release);
  stage.addEventListener('pointercancel', release);

  apply();
}

// Walkthroughs are written as mermaid comments, which every other renderer ignores:
//   %% play: Title        starts a scenario
//   %% A -> B : label     sends a token from node A to node B along the edge between them
//   %% skip A B           fades nodes for the rest of the scenario
function flowchartLines(source) {
  const lines = source.split(/\\r?\\n/);
  let at = 0;
  while (at < lines.length && !lines[at].trim()) at++;
  if (lines[at] && lines[at].trim() === '---') {
    at++;
    while (at < lines.length && lines[at].trim() !== '---') at++;
    at++;
  }
  const head = lines.slice(at).map((line) => line.trim()).find((line) => line && !line.startsWith('%%'));
  return head && /^(?:flowchart|graph)\\b/.test(head) ? lines.slice(at) : null;
}

function playScript(source) {
  const lines = flowchartLines(source);
  if (!lines) return [];
  const scenarios = [];
  let current = null;
  for (const line of lines) {
    const comment = /^\\s*%%(?!\\{)\\s*(.*?)\\s*$/.exec(line);
    if (!comment) continue;
    const text = comment[1];
    const title = /^play\\s*:\\s*(.*)$/i.exec(text);
    if (title) {
      current = { title: title[1] || 'Scenario ' + (scenarios.length + 1), steps: [] };
      scenarios.push(current);
      continue;
    }
    let step = null;
    // A sentence after | is the step's caption: A -> B : label | caption, or skip A B | caption.
    const bar = text.indexOf('|');
    const body = bar < 0 ? text : text.slice(0, bar).trim();
    const caption = bar < 0 ? '' : text.slice(bar + 1).trim();
    const move = /^([^\\s:]+?)\\s*-+>\\s*([^\\s:]+)\\s*(?::\\s*(.*))?$/.exec(body);
    const skip = /^skip\\s+(.+)$/i.exec(body);
    if (move) step = { from: move[1], to: move[2], label: move[3] || '', caption: caption, text: text };
    else if (skip) step = { skip: skip[1].split(/[\\s,]+/).filter(Boolean), caption: caption, text: text };
    if (!step) continue;
    if (!current) {
      current = { title: 'Walkthrough', steps: [] };
      scenarios.push(current);
    }
    current.steps.push(step);
  }
  return scenarios.filter((scenario) => scenario.steps.length);
}

// Pictures in flowchart nodes, A@{ img: "logo.png" }. Mermaid fails the whole diagram when one
// does not load, so each is checked first and a missing or refused one becomes a placeholder.
const DIAGRAM_IMAGE = /(\\bimg\\s*:\\s*)(?:(["'])(.*?)\\2|([^\\s,}"']+))/g;
const DIAGRAM_IMAGE_SAFE = /^(?:https:\\/\\/|\\/(?![\\/\\\\])|data:image\\/(?:png|jpe?g|gif|webp|svg\\+xml)[;,])/i;
const DIAGRAM_IMAGE_MISSING = 'data:image/svg+xml;base64,' + btoa('<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48" fill="none" stroke="#888" stroke-width="2" stroke-linejoin="round"><rect x="5" y="9" width="38" height="30" rx="4" stroke-dasharray="4 3"/><path d="M11 33l9-10 7 7 4-4 6 7"/><circle cx="31" cy="18" r="3"/></svg>');

function diagramImageUrl(value) {
  const found = poub ? local(value) : null;
  if (found) return poub + encodeURIComponent(found.name);
  return DIAGRAM_IMAGE_SAFE.test(value) && !/["'{}\\s]/.test(value) ? value : null;
}

function loadImage(url) {
  return new Promise((resolve, reject) => {
    const image = new Image();
    const timer = setTimeout(() => reject(new Error('timed out')), 8000);
    image.onload = () => { clearTimeout(timer); resolve(); };
    image.onerror = () => { clearTimeout(timer); reject(new Error('did not load')); };
    image.src = url;
  });
}

async function diagramImages(source) {
  const shapes = /@\\{[^}]*\\}/g;
  if (!flowchartLines(source)) return { source: source, problems: [] };
  const wanted = new Map();
  for (const shape of source.matchAll(shapes)) {
    for (const match of shape[0].matchAll(DIAGRAM_IMAGE)) {
      const value = match[3] ?? match[4];
      if (!wanted.has(value)) wanted.set(value, diagramImageUrl(value));
    }
  }
  if (!wanted.size) return { source: source, problems: [] };
  const problems = [];
  await Promise.all([...wanted].map(async ([value, url]) => {
    if (!url) {
      problems.push(value + ' (not allowed)');
      wanted.set(value, DIAGRAM_IMAGE_MISSING);
      return;
    }
    try { await loadImage(url); } catch (error) {
      problems.push(value + ' (' + error.message + ')');
      wanted.set(value, DIAGRAM_IMAGE_MISSING);
    }
  }));
  const rewritten = source.replace(shapes, (shape) => shape.replace(DIAGRAM_IMAGE,
    (match, key, quote, quoted, bare) => key + '"' + wanted.get(quoted ?? bare) + '"'));
  return { source: rewritten, problems: problems };
}

const SVG_NS = 'http://www.w3.org/2000/svg';
let diagramsBusy = 0;
let diagramBusyWrapped = false;

// A playing story or a highlighted box holds off the live reload, so neither vanishes mid-talk.
function diagramBusy(on) {
  diagramsBusy += on ? 1 : -1;
  if (diagramBusyWrapped) return;
  diagramBusyWrapped = true;
  const previousBusy = window.liveBusy;
  window.liveBusy = () => diagramsBusy > 0 || (previousBusy ? previousBusy() : false);
}

function diagramNodes(svg) {
  const nodes = new Map();
  for (const group of svg.querySelectorAll(':is(g.node, g.image-shape)[id]')) {
    const match = /-flowchart-(.+)-\\d+$/.exec(group.id);
    if (match && !nodes.has(match[1])) nodes.set(match[1], group);
  }
  return nodes;
}

// Clicking a box puts it in the spotlight: the box and its arrows stay bright, the rest dims.
// Shift, Ctrl or Cmd adds boxes; clicking the lone box, the background or Escape clears it.
function focusDiagram(stage, svg) {
  const nodes = diagramNodes(svg);
  if (!nodes.size) return;
  const names = new Map([...nodes].map(([name, group]) => [group, name]));
  const links = [];
  for (const path of svg.querySelectorAll('path[data-edge][data-id]')) {
    const id = path.dataset.id;
    for (const from of nodes.keys()) {
      if (!id.startsWith('L_' + from + '_')) continue;
      const rest = id.slice(from.length + 3);
      const to = [...nodes.keys()].find((name) => rest.startsWith(name + '_') && /^\\d+$/.test(rest.slice(name.length + 1)));
      if (!to) continue;
      const label = svg.querySelector('g.edgeLabels [data-id="' + CSS.escape(id) + '"]');
      links.push({ from: from, to: to, parts: [path, label && (label.closest('g.edgeLabel') || label)].filter(Boolean) });
      break;
    }
  }
  stage.classList.add('focusable');
  const selected = new Set();
  let held = false;
  function paint() {
    for (const element of svg.querySelectorAll('.focus-on, .focus-near')) element.classList.remove('focus-on', 'focus-near');
    for (const name of selected) nodes.get(name).classList.add('focus-on');
    for (const link of links) {
      if (!selected.has(link.from) && !selected.has(link.to)) continue;
      for (const part of link.parts) part.classList.add('focus-near');
      for (const end of [link.from, link.to]) if (!selected.has(end)) nodes.get(end).classList.add('focus-near');
    }
    stage.classList.toggle('focusing', selected.size > 0);
    if (held !== selected.size > 0) diagramBusy(held = !held);
  }
  let start = null;
  stage.addEventListener('pointerdown', (event) => { start = { x: event.clientX, y: event.clientY }; }, true);
  stage.addEventListener('click', (event) => {
    if (event.button !== 0 || event.detail > 1) return;
    if (start && Math.hypot(event.clientX - start.x, event.clientY - start.y) > 6) return;
    // Pointer capture makes the stage the click target, so look under the pointer instead.
    const under = document.elementFromPoint(event.clientX, event.clientY);
    if (!under || !stage.contains(under) || under.closest('.diagram-tools')) return;
    const inside = (element) => {
      const rect = element.getBoundingClientRect();
      return event.clientX >= rect.left && event.clientX <= rect.right && event.clientY >= rect.top && event.clientY <= rect.bottom;
    };
    // A picture box has a gap between its image and its label, which still counts as the box.
    const group = under.closest(':is(g.node, g.image-shape)') || [...names.keys()].find(inside);
    const name = group && names.get(group);
    if (!name) selected.clear();
    else if (event.shiftKey || event.ctrlKey || event.metaKey) selected.has(name) ? selected.delete(name) : selected.add(name);
    else if (selected.has(name) && selected.size === 1) selected.clear();
    else {
      selected.clear();
      selected.add(name);
    }
    paint();
  });
  document.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || !selected.size || !stage.isConnected) return;
    const dialog = stage.closest('dialog');
    if (!dialog && document.querySelector('dialog[open]')) return;
    event.preventDefault();
    selected.clear();
    paint();
  });
  return {
    get: () => [...selected],
    set(wanted) {
      selected.clear();
      for (const name of wanted) if (nodes.has(name)) selected.add(name);
      paint();
    },
  };
}

// A saved frame is the diagram as a standalone SVG image. Page CSS does not reach inside an
// image, so the computed styles that matter are copied inline, and pictures become data URLs.
const XLINK_NS = 'http://www.w3.org/1999/xlink';
const PICTURE_SHAPE = ['fill', 'fill-opacity', 'stroke', 'stroke-width', 'stroke-opacity', 'stroke-dasharray', 'opacity', 'filter', 'visibility'];
const PICTURE_TEXT = ['font-family', 'font-size', 'font-weight', 'font-style', 'line-height', 'letter-spacing', 'color', 'margin-top', 'margin-bottom'];

async function diagramImageData(svg) {
  const found = new Map();
  for (const image of svg.querySelectorAll('image')) {
    const href = image.getAttribute('href') || image.getAttributeNS(XLINK_NS, 'href');
    if (!href || found.has(href)) continue;
    if (href.startsWith('data:')) {
      found.set(href, href);
      continue;
    }
    try {
      const url = new URL(href, location.href);
      if (url.origin !== location.origin) throw new Error('other site');
      const response = await fetch(url);
      if (!response.ok) throw new Error(response.status);
      const blob = await response.blob();
      found.set(href, await new Promise((resolve, reject) => {
        const reader = new FileReader();
        reader.onload = () => resolve(reader.result);
        reader.onerror = reject;
        reader.readAsDataURL(blob);
      }));
    } catch (error) {
      found.set(href, DIAGRAM_IMAGE_MISSING);
    }
  }
  return found;
}

function diagramPicture(svg, home, size, images) {
  const copy = svg.cloneNode(true);
  const from = svg.querySelectorAll('*');
  const to = copy.querySelectorAll('*');
  for (let at = 0; at < from.length; at++) {
    const element = from[at];
    let names = null;
    if (element instanceof SVGTextContentElement) names = PICTURE_SHAPE.concat(PICTURE_TEXT);
    else if (element instanceof SVGGraphicsElement) names = PICTURE_SHAPE;
    else if (element instanceof HTMLElement) names = PICTURE_TEXT;
    if (!names) continue;
    const computed = getComputedStyle(element);
    for (const name of names) to[at].style.setProperty(name, computed.getPropertyValue(name), 'important');
  }
  copy.setAttribute('viewBox', [home.x, home.y, home.w, home.h].join(' '));
  copy.setAttribute('width', String(size.w));
  copy.setAttribute('height', String(size.h));
  copy.removeAttribute('style');
  for (const image of copy.querySelectorAll('image')) {
    const href = image.getAttribute('href') || image.getAttributeNS(XLINK_NS, 'href');
    image.removeAttributeNS(XLINK_NS, 'href');
    image.setAttribute('href', images.get(href) || DIAGRAM_IMAGE_MISSING);
  }
  const picture = new Image();
  picture.src = 'data:image/svg+xml;charset=utf-8,' + encodeURIComponent(new XMLSerializer().serializeToString(copy));
  return picture.decode().then(() => picture);
}

// limit caps the longer side; the area cap keeps H.264 inside the level it is asked for.
// With captioned, a band under the diagram keeps room for two lines of caption in every frame.
async function diagramCanvas(svg, home, limit, captioned) {
  const PAD = 24;
  const scale = Math.min(2, (limit - 2 * PAD) / Math.max(home.w, home.h), Math.sqrt(1900000 / (home.w * home.h)));
  const size = { w: home.w * scale, h: home.h * scale };
  const even = (value) => Math.max(2, Math.round(value / 2) * 2);
  const element = document.createElement('canvas');
  element.width = even(size.w + 2 * PAD);
  const fontSize = Math.round(Math.max(15, Math.min(30, element.width / 40)));
  const band = captioned ? Math.round(fontSize * 2 * 1.35 + PAD) : 0;
  element.height = even(size.h + 2 * PAD + band);
  const context = element.getContext('2d', { willReadFrequently: true });
  const style = getComputedStyle(article);
  const colour = (name, fallback) => style.getPropertyValue(name).trim() || fallback;
  const background = colour('--bgColor-default', getComputedStyle(document.body).backgroundColor);
  const ink = colour('--fgColor-default', getComputedStyle(document.body).color);
  const rule = colour('--borderColor-muted', ink);
  const font = '500 ' + fontSize + 'px system-ui, -apple-system, sans-serif';
  const images = await diagramImageData(svg);
  function lines(text) {
    const room = element.width - 2 * PAD;
    const result = [''];
    for (const word of text.split(/\\s+/)) {
      const last = result.length - 1;
      const joined = result[last] ? result[last] + ' ' + word : word;
      if (!result[last] || context.measureText(joined).width <= room) result[last] = joined;
      else result.push(word);
    }
    if (result.length > 2) {
      let second = result[1];
      while (second && context.measureText(second + '\\u2026').width > room) second = second.slice(0, -1);
      result.splice(1, result.length, second.trimEnd() + '\\u2026');
    }
    return result;
  }
  return {
    element: element,
    width: element.width,
    height: element.height,
    async draw(text) {
      const picture = await diagramPicture(svg, home, size, images);
      context.fillStyle = background;
      context.fillRect(0, 0, element.width, element.height);
      context.drawImage(picture, (element.width - size.w) / 2, (element.height - band - size.h) / 2, size.w, size.h);
      if (!band || !text) return;
      const top = element.height - band;
      context.fillStyle = rule;
      context.fillRect(PAD, top, element.width - 2 * PAD, 1);
      context.font = font;
      context.fillStyle = ink;
      context.textAlign = 'center';
      context.textBaseline = 'middle';
      const rows = lines(text);
      const height = fontSize * 1.35;
      const first = top + band / 2 - (rows.length - 1) * height / 2;
      rows.forEach((row, at) => context.fillText(row, element.width / 2, first + at * height));
    },
    pixels: () => context.getImageData(0, 0, element.width, element.height).data,
  };
}

function diagramVideoType() {
  if (typeof MediaRecorder === 'undefined' || !HTMLCanvasElement.prototype.captureStream) return '';
  const types = ['video/mp4;codecs=avc1.640028', 'video/mp4', 'video/webm;codecs=vp9', 'video/webm'];
  return types.find((type) => MediaRecorder.isTypeSupported(type)) || '';
}

function diagramExportName(title, extension) {
  const slug = (text) => text.normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase().replace(/[^a-z0-9]+/g, '-').replace(/^-+|-+$/g, '');
  let page = location.pathname.split('/').pop() || '';
  try { page = decodeURIComponent(page); } catch (error) { /* keep it encoded */ }
  page = page.replace(/\\.(md|markdown)$/i, '');
  return ([slug(page), slug(title || '')].filter(Boolean).join('-').slice(0, 120) || 'diagram') + '.' + extension;
}

function saveBlob(blob, name) {
  const url = URL.createObjectURL(blob);
  const link = document.createElement('a');
  link.href = url;
  link.download = name;
  link.hidden = true;
  document.body.append(link);
  link.click();
  link.remove();
  setTimeout(() => URL.revokeObjectURL(url), 60000);
}

// An animated GIF: each frame stores only the rectangle that changed, with its own palette of
// the 256 most common colours (5 bits per channel), and the rest mapped to the nearest one.
function gifWriter(width, height) {
  const parts = [];
  const bytes = (...values) => parts.push(Uint8Array.from(values));
  const word = (value) => [value & 255, (value >> 8) & 255];
  const ascii = (text) => [...text].map((letter) => letter.charCodeAt(0));
  bytes(...ascii('GIF89a'), ...word(width), ...word(height), 0, 0, 0);
  bytes(0x21, 0xff, 11, ...ascii('NETSCAPE2.0'), 3, 1, 0, 0, 0);
  let previous = null;
  let pending = null;

  function changed(after) {
    if (!previous) return { x: 0, y: 0, w: width, h: height };
    const before32 = new Uint32Array(previous.buffer, previous.byteOffset, width * height);
    const after32 = new Uint32Array(after.buffer, after.byteOffset, width * height);
    let top = -1;
    let bottom = -1;
    let left = width;
    let right = -1;
    for (let y = 0; y < height; y++) {
      const row = y * width;
      for (let x = 0; x < width; x++) {
        if (before32[row + x] === after32[row + x]) continue;
        if (top < 0) top = y;
        bottom = y;
        if (x < left) left = x;
        if (x > right) right = x;
      }
    }
    return top < 0 ? null : { x: left, y: top, w: right - left + 1, h: bottom - top + 1 };
  }

  function quantize(pixels, rect) {
    const count = rect.w * rect.h;
    const keys = new Uint16Array(count);
    const counts = new Uint32Array(32768);
    const sums = new Uint32Array(32768 * 3);
    let at = 0;
    for (let y = rect.y; y < rect.y + rect.h; y++) {
      for (let x = rect.x; x < rect.x + rect.w; x++) {
        const offset = (y * width + x) * 4;
        const red = pixels[offset];
        const green = pixels[offset + 1];
        const blue = pixels[offset + 2];
        const key = ((red >> 3) << 10) | ((green >> 3) << 5) | (blue >> 3);
        keys[at++] = key;
        counts[key]++;
        sums[key * 3] += red;
        sums[key * 3 + 1] += green;
        sums[key * 3 + 2] += blue;
      }
    }
    const used = [];
    for (let key = 0; key < 32768; key++) if (counts[key]) used.push(key);
    used.sort((first, second) => counts[second] - counts[first]);
    const kept = used.slice(0, 256);
    const bits = Math.max(1, Math.ceil(Math.log2(kept.length)));
    const palette = new Uint8Array(3 << bits);
    const lookup = new Int16Array(32768);
    kept.forEach((key, slot) => {
      for (let channel = 0; channel < 3; channel++) palette[slot * 3 + channel] = Math.round(sums[key * 3 + channel] / counts[key]);
      lookup[key] = slot;
    });
    for (const key of used.slice(256)) {
      const red = sums[key * 3] / counts[key];
      const green = sums[key * 3 + 1] / counts[key];
      const blue = sums[key * 3 + 2] / counts[key];
      let best = 0;
      let distance = Infinity;
      for (let slot = 0; slot < kept.length; slot++) {
        const dr = palette[slot * 3] - red;
        const dg = palette[slot * 3 + 1] - green;
        const db = palette[slot * 3 + 2] - blue;
        const here = dr * dr + dg * dg + db * db;
        if (here < distance) {
          distance = here;
          best = slot;
        }
      }
      lookup[key] = best;
    }
    const indices = new Uint8Array(count);
    for (let index = 0; index < count; index++) indices[index] = lookup[keys[index]];
    return { palette: palette, indices: indices, bits: bits };
  }

  function lzw(indices, minimum) {
    const out = [];
    const clear = 1 << minimum;
    const stop = clear + 1;
    let size = minimum + 1;
    let next = stop + 1;
    let dictionary = new Map();
    let buffer = 0;
    let filled = 0;
    const emit = (code) => {
      buffer |= code << filled;
      filled += size;
      while (filled >= 8) {
        out.push(buffer & 255);
        buffer >>>= 8;
        filled -= 8;
      }
    };
    emit(clear);
    let prefix = indices[0];
    for (let at = 1; at < indices.length; at++) {
      const symbol = indices[at];
      const key = (prefix << 8) | symbol;
      const known = dictionary.get(key);
      if (known !== undefined) {
        prefix = known;
        continue;
      }
      emit(prefix);
      if (next < 4096) {
        dictionary.set(key, next++);
        if (next > 1 << size && size < 12) size++;
      } else {
        emit(clear);
        dictionary = new Map();
        size = minimum + 1;
        next = stop + 1;
      }
      prefix = symbol;
    }
    emit(prefix);
    emit(stop);
    if (filled > 0) out.push(buffer & 255);
    return Uint8Array.from(out);
  }

  function write(frame) {
    const { palette, indices, bits } = quantize(frame.pixels, frame.rect);
    const delay = Math.max(2, Math.round(frame.delay / 10));
    bytes(0x21, 0xf9, 4, 0x04, ...word(delay), 0, 0);
    bytes(0x2c, ...word(frame.rect.x), ...word(frame.rect.y), ...word(frame.rect.w), ...word(frame.rect.h), 0x80 | (bits - 1));
    parts.push(palette);
    const minimum = Math.max(2, bits);
    const data = lzw(indices, minimum);
    bytes(minimum);
    for (let at = 0; at < data.length; at += 255) {
      const chunk = data.subarray(at, at + 255);
      bytes(chunk.length);
      parts.push(chunk);
    }
    bytes(0);
  }

  return {
    add(pixels, delay) {
      const rect = changed(pixels);
      if (!rect) {
        pending.delay += delay;
        return;
      }
      if (pending) write(pending);
      pending = { pixels: pixels, rect: rect, delay: delay };
      previous = pixels;
    },
    finish() {
      if (pending) write(pending);
      pending = null;
      bytes(0x3b);
      return new Blob(parts, { type: 'image/gif' });
    },
  };
}

function playDiagram(stage, svg, tools, scripts, home) {
  const nodes = diagramNodes(svg);
  const edges = [...svg.querySelectorAll('path[data-edge][data-id]')];
  const edgeBetween = (from, to) => edges.find((path) => {
    const id = path.dataset.id;
    const prefix = 'L_' + from + '_' + to + '_';
    return id.startsWith(prefix) && /^\\d+$/.test(id.slice(prefix.length));
  });

  // Steps that name an unknown node or an edge that is not drawn are dropped and listed in the title.
  const scenarios = scripts.map((script) => {
    const steps = [];
    const problems = [];
    for (const step of script.steps) {
      if (step.skip) {
        const found = step.skip.map((name) => nodes.get(name)).filter(Boolean);
        if (found.length < step.skip.length) problems.push(step.text);
        if (found.length) steps.push({ skip: found, caption: step.caption });
        continue;
      }
      const from = nodes.get(step.from);
      const to = nodes.get(step.to);
      const forward = from && to && edgeBetween(step.from, step.to);
      const path = forward || (from && to && edgeBetween(step.to, step.from));
      if (!path) {
        problems.push(step.text);
        continue;
      }
      steps.push({ from: from, to: to, path: path, reverse: !forward, label: step.label, caption: step.caption });
    }
    return { title: script.title, steps: steps, problems: problems };
  }).filter((scenario) => scenario.steps.length);
  if (!scenarios.length) return;

  const controls = document.createElement('div');
  controls.className = 'diagram-play';
  let picker = null;
  if (scenarios.length > 1) {
    picker = document.createElement('select');
    picker.name = 'scenario';
    picker.setAttribute('aria-label', 'Scenario');
    scenarios.forEach((scenario, index) => picker.add(new Option(scenario.title, String(index))));
    controls.append(picker);
  }
  const make = (icon, label, name) => {
    const element = document.createElement('button');
    element.type = 'button';
    element.className = name;
    element.innerHTML = diagramIcon(icon);
    element.title = label;
    element.setAttribute('aria-label', label);
    controls.append(element);
    return element;
  };
  const backButton = make('back', 'Previous step', 'play-back');
  const playButton = make('play', 'Play', 'play-toggle');
  const nextButton = make('next', 'Next step', 'play-next');
  const stopButton = make('stop', 'Stop', 'play-stop');
  const recordButton = make('record', 'Save as GIF or video', 'play-record');
  const exportMenu = document.createElement('div');
  exportMenu.className = 'diagram-export';
  exportMenu.hidden = true;
  const exportChoice = (kind, text, note) => {
    const element = document.createElement('button');
    element.type = 'button';
    element.dataset.kind = kind;
    element.textContent = text;
    const small = document.createElement('small');
    small.textContent = note;
    element.append(small);
    exportMenu.append(element);
    return element;
  };
  exportChoice('gif', 'GIF', 'Loops, plays anywhere');
  const linkChoice = exportChoice('link', 'Copy link', 'To this story, step and spotlight');
  const videoType = diagramVideoType();
  if (videoType) exportChoice('video', 'Video', videoType.startsWith('video/mp4') ? 'MP4, smaller and smoother' : 'WebM, smaller and smoother');
  controls.append(exportMenu);
  tools.prepend(controls);
  const caption = document.createElement('div');
  caption.className = 'diagram-caption';
  caption.setAttribute('aria-live', 'polite');
  caption.hidden = true;
  stage.append(caption);
  const say = (text) => {
    caption.textContent = text || '';
    caption.hidden = !text;
  };

  let timeline = [];
  let index = 0;
  let elapsed = 0;
  let playing = false;
  let finished = false;
  let frame = 0;
  let last = 0;
  let active = null;
  let token = null;
  // Step mode stops the timeline after each step. waiting means the next segment is not entered yet.
  let reached = 0;
  let waiting = false;
  let stepping = false;

  const scenario = () => scenarios[picker ? Number(picker.value) : 0];
  function label(icon, text) {
    playButton.innerHTML = diagramIcon(icon);
    const problems = scenario().problems;
    const title = problems.length ? text + ' (ignored: ' + problems.join('; ') + ')' : text;
    playButton.title = title;
    playButton.setAttribute('aria-label', title);
  }
  function sync() {
    label(playing ? 'pause' : 'play', playing ? 'Pause' : finished ? 'Replay' : timeline.length ? 'Resume' : 'Play');
    stopButton.hidden = !timeline.length;
    backButton.hidden = !timeline.length || (!reached && !index && !elapsed);
    const total = scenario().steps.length;
    const shown = Math.min(total, reached + 1);
    const next = finished ? 'Next step (from the start)' : 'Next step (' + shown + ' of ' + total + ')';
    nextButton.title = next;
    nextButton.setAttribute('aria-label', next);
    controls.classList.toggle('playing', playing);
  }

  function badge(node) {
    if (node.querySelector(':scope > .play-check')) return;
    const frame = node.classList.contains('image-shape') ? node.querySelector(':scope > g') : null;
    let box = node.getBBox();
    if (frame) {
      const corner = svg.createSVGPoint();
      const inner = frame.getBBox();
      corner.x = inner.x + inner.width;
      corner.y = inner.y;
      const at = corner.matrixTransform(node.getCTM().inverse().multiply(frame.getCTM()));
      box = { x: at.x - inner.width, y: at.y, width: inner.width };
    }
    const mark = document.createElementNS(SVG_NS, 'g');
    mark.setAttribute('class', 'play-check');
    mark.setAttribute('transform', 'translate(' + (box.x + box.width - 2) + ' ' + (box.y + 2) + ')');
    const circle = document.createElementNS(SVG_NS, 'circle');
    circle.setAttribute('r', '8');
    const tick = document.createElementNS(SVG_NS, 'path');
    tick.setAttribute('d', 'M-3.6 0.2l2.4 2.4 4.8-5');
    mark.append(circle, tick);
    node.append(mark);
  }
  function setActive(node) {
    node.classList.remove('play-done', 'play-skipped');
    node.querySelector(':scope > .play-check')?.remove();
    node.classList.add('play-active');
    active = node;
  }
  function setDone(node) {
    node.classList.remove('play-active');
    node.classList.add('play-done');
    badge(node);
    if (active === node) active = null;
  }
  function clearMarks() {
    for (const element of svg.querySelectorAll('.play-active, .play-done, .play-skipped, .play-edge, .play-edge-done')) {
      element.classList.remove('play-active', 'play-done', 'play-skipped', 'play-edge', 'play-edge-done');
    }
    for (const element of svg.querySelectorAll('.play-check')) element.remove();
    token?.remove();
    token = null;
    active = null;
    say('');
  }

  function makeToken(text) {
    const group = document.createElementNS(SVG_NS, 'g');
    group.setAttribute('class', 'play-token');
    const dot = document.createElementNS(SVG_NS, 'circle');
    dot.setAttribute('r', '6');
    group.append(dot);
    svg.append(group);
    if (text) {
      const tag = document.createElementNS(SVG_NS, 'g');
      tag.setAttribute('class', 'play-tag');
      const back = document.createElementNS(SVG_NS, 'rect');
      const words = document.createElementNS(SVG_NS, 'text');
      words.textContent = text;
      words.setAttribute('text-anchor', 'middle');
      words.setAttribute('y', '-14');
      tag.append(back, words);
      group.append(tag);
      const box = words.getBBox();
      back.setAttribute('x', String(box.x - 6));
      back.setAttribute('y', String(box.y - 3));
      back.setAttribute('width', String(box.width + 12));
      back.setAttribute('height', String(box.height + 6));
      back.setAttribute('rx', '5');
    }
    return group;
  }

  // The timeline is a list of segments that only advances while playing, so pausing is free.
  function build(calm) {
    const segments = [];
    let at = null;
    const DWELL = calm ? 650 : 420;
    for (const step of scenario().steps) {
      if (step.skip) {
        segments.push({ duration: calm ? 400 : 320, stop: true, start: () => {
          say(step.caption);
          for (const node of step.skip) {
            node.classList.remove('play-active', 'play-done');
            node.querySelector(':scope > .play-check')?.remove();
            node.classList.add('play-skipped');
            if (active === node) active = null;
          }
        } });
        continue;
      }
      if (at !== step.from) {
        segments.push({ duration: DWELL, start: () => {
          say(step.caption);
          if (active && active !== step.from) setDone(active);
          setActive(step.from);
        } });
      } else {
        segments.push({ duration: DWELL, start: () => say(step.caption) });
      }
      const length = step.path.getTotalLength();
      let matrix = null;
      segments.push({
        duration: calm ? 300 : Math.min(1700, Math.max(550, length * 3.2)),
        stop: true,
        start: () => {
          setDone(step.from);
          step.path.classList.remove('play-edge-done');
          step.path.classList.add('play-edge');
          if (calm) return;
          const own = step.path.getScreenCTM();
          const root = svg.getScreenCTM();
          matrix = own && root ? root.inverse().multiply(own) : new DOMMatrix();
          token = makeToken(step.label);
        },
        frame: (progress) => {
          if (!token) return;
          const eased = progress < 0.5 ? 2 * progress * progress : 1 - Math.pow(-2 * progress + 2, 2) / 2;
          const point = step.path.getPointAtLength(length * (step.reverse ? 1 - eased : eased));
          const placed = new DOMPoint(point.x, point.y).matrixTransform(matrix);
          token.setAttribute('transform', 'translate(' + placed.x + ' ' + placed.y + ')');
        },
        end: () => {
          token?.remove();
          token = null;
          step.path.classList.remove('play-edge');
          step.path.classList.add('play-edge-done');
          setActive(step.to);
        },
      });
      at = step.to;
    }
    segments.push({ duration: DWELL, start: () => { if (active) setDone(active); } });
    return segments;
  }

  function enter(segment) {
    segment.start();
    if (segment.frame) segment.frame(0);
  }
  // Moves the timeline on by a number of milliseconds and says whether it reached the end
  // (true), or, with toStep, the end of a step that is not the last one ('step').
  function advance(delta, toStep) {
    if (waiting) {
      waiting = false;
      if (index < timeline.length) enter(timeline[index]);
    }
    elapsed += delta;
    while (index < timeline.length && elapsed >= timeline[index].duration) {
      const done = timeline[index];
      elapsed -= done.duration;
      if (done.frame) done.frame(1);
      if (done.end) done.end();
      index++;
      if (done.stop) reached++;
      if (toStep && done.stop && reached < scenario().steps.length) {
        elapsed = 0;
        waiting = true;
        return 'step';
      }
      if (index < timeline.length) enter(timeline[index]);
    }
    if (index >= timeline.length) return true;
    const segment = timeline[index];
    if (segment.frame) segment.frame(elapsed / segment.duration);
    return false;
  }
  function restart(calm) {
    clearMarks();
    timeline = build(calm);
    index = 0;
    elapsed = 0;
    reached = 0;
    waiting = false;
    finished = false;
    enter(timeline[0]);
  }
  function tick(now) {
    frame = 0;
    if (!playing) return;
    const done = advance(Math.min(100, now - last), stepping);
    last = now;
    if (done === 'step') {
      pause();
      return;
    }
    if (done) {
      finished = true;
      pause();
      return;
    }
    frame = requestAnimationFrame(tick);
  }
  const busy = diagramBusy;
  function play(motion, step) {
    stepping = Boolean(step);
    if (playing) return;
    if (finished || !timeline.length) restart(!motion && matchMedia('(prefers-reduced-motion: reduce)').matches);
    playing = true;
    busy(true);
    last = performance.now();
    frame = requestAnimationFrame(tick);
    sync();
  }
  function pause() {
    if (playing) busy(false);
    playing = false;
    cancelAnimationFrame(frame);
    frame = 0;
    sync();
  }
  function stop() {
    pause();
    clearMarks();
    timeline = [];
    index = 0;
    elapsed = 0;
    reached = 0;
    waiting = false;
    finished = false;
    sync();
  }
  // Going back rebuilds the picture from the start, jumping over each step without animation.
  // From the middle of a step, back returns to that step's start.
  function stepBack() {
    if (!timeline.length) return;
    const target = finished ? scenario().steps.length - 1 : waiting || (!playing && !elapsed) ? reached - 1 : reached;
    pause();
    restart(matchMedia('(prefers-reduced-motion: reduce)').matches);
    for (let step = 0; step < target; step++) advance(Infinity, true);
    sync();
  }
  function stepNext() {
    if (playing && !stepping) {
      stepping = true;
      return;
    }
    play(false, true);
  }

  // Saving replays the scenario from the start and draws every frame onto a canvas. A GIF steps
  // the timeline by a fixed amount per frame; a video records while it plays in real time.
  let exporting = null;
  function exportProgress() {
    if (!exporting) return;
    const done = timeline.length ? Math.min(99, Math.floor(100 * index / timeline.length)) : 0;
    recordButton.textContent = done + '%';
  }
  function exportEnd(error) {
    if (!exporting) return;
    const kind = exporting.kind;
    exporting = null;
    busy(false);
    stage.classList.remove('recording');
    recordButton.classList.remove('busy');
    recordButton.innerHTML = diagramIcon('record');
    for (const element of [backButton, playButton, nextButton, stopButton]) element.disabled = false;
    if (picker) picker.disabled = false;
    const text = error ? 'Could not save the ' + (kind === 'gif' ? 'GIF' : 'video') + ': ' + (error.message || error) : 'Save as GIF or video';
    recordButton.title = text;
    recordButton.setAttribute('aria-label', text);
    sync();
  }
  async function exportScenario(kind) {
    if (exporting) return;
    exporting = { kind: kind, cancelled: false };
    const job = exporting;
    pause();
    busy(true);
    for (const element of [backButton, playButton, nextButton, stopButton]) element.disabled = true;
    if (picker) picker.disabled = true;
    recordButton.classList.add('busy');
    recordButton.textContent = '0%';
    recordButton.title = 'Cancel';
    recordButton.setAttribute('aria-label', 'Cancel saving');
    const name = diagramExportName(scenario().title, kind === 'gif' ? 'gif' : videoType.startsWith('video/mp4') ? 'mp4' : 'webm');
    try {
      const captioned = scenario().steps.some((step) => step.caption);
      const canvas = await diagramCanvas(svg, home, kind === 'gif' ? 960 : 1920, captioned);
      if (kind === 'gif') {
        stage.classList.add('recording');
        const STEP = 60;
        const gif = gifWriter(canvas.width, canvas.height);
        restart(false);
        for (;;) {
          await canvas.draw(caption.textContent);
          if (job.cancelled) break;
          const end = index >= timeline.length;
          gif.add(canvas.pixels(), end ? 2400 : STEP);
          if (end) break;
          advance(STEP);
          exportProgress();
          await new Promise((resolve) => setTimeout(resolve));
        }
        if (job.cancelled) stop();
        else {
          finished = true;
          saveBlob(gif.finish(), name);
        }
      } else {
        await canvas.draw(caption.textContent);
        const stream = canvas.element.captureStream(30);
        const recorder = new MediaRecorder(stream, { mimeType: videoType, videoBitsPerSecond: 6000000 });
        const chunks = [];
        recorder.addEventListener('dataavailable', (event) => { if (event.data.size) chunks.push(event.data); });
        const stopped = new Promise((resolve) => recorder.addEventListener('stop', resolve, { once: true }));
        recorder.start();
        stop();
        play(true);
        let hold = 0;
        while (!job.cancelled) {
          await canvas.draw(caption.textContent);
          exportProgress();
          if (finished) {
            hold = hold || performance.now() + 1500;
            if (performance.now() >= hold) break;
          }
          await new Promise((resolve) => requestAnimationFrame(resolve));
        }
        pause();
        recorder.stop();
        await stopped;
        for (const track of stream.getTracks()) track.stop();
        if (job.cancelled) stop();
        else saveBlob(new Blob(chunks, { type: recorder.mimeType || videoType }), name);
      }
      exportEnd();
    } catch (error) {
      exportEnd(error);
    }
  }

  function where() {
    const total = scenario().steps.length;
    return {
      story: (picker ? Number(picker.value) : 0) + 1,
      step: !timeline.length ? null : finished ? total : reached,
    };
  }
  // Puts a story at the end of a given number of steps, the way stepping back does.
  function restore(story, step) {
    if (exporting) return;
    if (picker && story >= 1 && story <= scenarios.length) picker.value = String(story - 1);
    stop();
    if (step === null) return;
    const total = scenario().steps.length;
    restart(matchMedia('(prefers-reduced-motion: reduce)').matches);
    if (step >= total) {
      while (advance(Infinity) !== true);
      finished = true;
    } else for (let at = 0; at < step; at++) advance(Infinity, true);
    sync();
  }

  playButton.addEventListener('click', () => (playing ? pause() : play()));
  backButton.addEventListener('click', stepBack);
  nextButton.addEventListener('click', stepNext);
  stopButton.addEventListener('click', stop);
  recordButton.addEventListener('click', () => {
    if (exporting) {
      exporting.cancelled = true;
      return;
    }
    exportMenu.hidden = !exportMenu.hidden;
  });
  exportMenu.addEventListener('click', async (event) => {
    const choice = event.target.closest('button[data-kind]');
    if (!choice) return;
    if (choice.dataset.kind === 'link') {
      const note = linkChoice.querySelector('small');
      const hash = diagramHash(stage);
      if (!hash) return;
      history.replaceState(history.state, '', location.pathname + location.search + hash);
      note.textContent = (await copyText(location.href)) ? 'Copied' : 'Could not copy, the address bar has it';
      setTimeout(() => {
        exportMenu.hidden = true;
        note.textContent = 'To this story, step and spotlight';
      }, 900);
      return;
    }
    exportMenu.hidden = true;
    exportScenario(choice.dataset.kind);
  });
  document.addEventListener('pointerdown', (event) => {
    if (!exportMenu.hidden && !controls.contains(event.target)) exportMenu.hidden = true;
  });
  controls.addEventListener('keydown', (event) => {
    if (event.key !== 'Escape' || exportMenu.hidden) return;
    event.stopPropagation();
    event.preventDefault();
    exportMenu.hidden = true;
    recordButton.focus();
  });
  if (picker) picker.addEventListener('change', () => {
    stop();
    play();
  });
  // Right/Left, j/k, Space/Shift+Space and the PageDown/PageUp that presentation clickers send walk
  // the story; Shift+arrows still pan, and Space leaves a focused button to the browser.
  stage.addEventListener('keydown', (event) => {
    const space = event.key === ' ' && !event.target.closest('button');
    const forward = event.key === 'PageDown' || event.key === 'j' || (space && !event.shiftKey) || (event.key === 'ArrowRight' && !event.shiftKey);
    const backward = event.key === 'PageUp' || event.key === 'k' || (space && event.shiftKey) || (event.key === 'ArrowLeft' && !event.shiftKey);
    if ((!forward && !backward) || exporting || event.ctrlKey || event.metaKey || event.altKey || event.target.closest('select')) return;
    event.preventDefault();
    event.stopImmediatePropagation();
    forward ? stepNext() : stepBack();
  });
  sync();
  return { where: where, restore: restore };
}

// #diagram=2&story=1&step=3&focus=A,B names the second diagram on the page, its first story
// after three steps, and the boxes in the spotlight. Heading ids never hold '=', so it cannot
// clash with them.
function diagramHash(stage) {
  const number = stage.dataset.diagram;
  if (!number) return '';
  const parts = ['diagram=' + number];
  const at = stage.diagramPlay?.where();
  if (at) {
    parts.push('story=' + at.story);
    if (at.step !== null) parts.push('step=' + at.step);
  }
  const lit = stage.diagramFocus?.get() || [];
  if (lit.length) parts.push('focus=' + lit.map(encodeURIComponent).join(','));
  return '#' + parts.join('&');
}

function diagramFromHash(stage) {
  if (!location.hash.startsWith('#diagram=')) return false;
  const wanted = new URLSearchParams(location.hash.slice(1));
  if (wanted.get('diagram') !== stage.dataset.diagram) return false;
  const number = (name) => (/^\\d+$/.test(wanted.get(name) || '') ? Number(wanted.get(name)) : null);
  if (stage.diagramPlay && (number('story') !== null || number('step') !== null)) stage.diagramPlay.restore(number('story') || 1, number('step'));
  if (stage.diagramFocus) stage.diagramFocus.set((wanted.get('focus') || '').split(',').filter(Boolean));
  stage.closest('.mermaid-diagram')?.scrollIntoView({ block: 'center' });
  return true;
}

function drawDiagrams() {
  const diagrams = [...article.querySelectorAll('.highlight-source-mermaid')];
  if (!diagrams.length) return;
  const draw = async () => {
    const dark = document.documentElement.dataset.mode === 'dark';
    let themeVariables = null;
    try { themeVariables = diagramColours(dark); } catch (error) { /* mermaid's own palette */ }
    mermaid.initialize(themeVariables
      ? { startOnLoad: false, securityLevel: 'strict', theme: 'base', themeVariables: themeVariables }
      : { startOnLoad: false, securityLevel: 'strict', theme: dark ? 'dark' : 'default' });
    for (const [position, block] of diagrams.entries()) {
      const id = 'mermaid-' + diagramCount++;
      try {
        const scenarios = playScript(block.textContent);
        const pictures = await diagramImages(block.textContent);
        const result = await mermaid.render(id, pictures.source);
        const holder = document.createElement('div');
        holder.className = 'mermaid-diagram';
        if (block.dataset.line) {
          holder.dataset.line = block.dataset.line;
          holder.dataset.lineEnd = block.dataset.lineEnd;
        }
        holder.innerHTML = result.svg;
        block.replaceWith(holder);
        panZoom(holder, scenarios);
        const stage = holder.querySelector(':scope > .diagram-stage');
        if (stage) {
          stage.dataset.diagram = String(position + 1);
          diagramFromHash(stage);
        }
        if (pictures.problems.length) holder.title += '\\nPictures not shown: ' + pictures.problems.join(', ');
        if (onDiagram) onDiagram();
      } catch (error) {
        document.getElementById('d' + id)?.remove();
        block.title = 'Mermaid: ' + (error.message || error);
      }
    }
  };
  if (window.mermaid) {
    draw();
    return;
  }
  const script = document.createElement('script');
  script.src = '/vendor/mermaid.min.js';
  script.onload = draw;
  document.head.append(script);
}

const COPY_ICON = '<svg viewBox="0 0 16 16" width="14" height="14" aria-hidden="true"><path d="M0 6.75C0 5.784.784 5 1.75 5h1.5a.75.75 0 0 1 0 1.5h-1.5a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-1.5a.75.75 0 0 1 1.5 0v1.5A1.75 1.75 0 0 1 9.25 16h-7.5A1.75 1.75 0 0 1 0 14.25Z"></path><path d="M5 1.75C5 .784 5.784 0 6.75 0h7.5C15.216 0 16 .784 16 1.75v7.5A1.75 1.75 0 0 1 14.25 11h-7.5A1.75 1.75 0 0 1 5 9.25Zm1.75-.25a.25.25 0 0 0-.25.25v7.5c0 .138.112.25.25.25h7.5a.25.25 0 0 0 .25-.25v-7.5a.25.25 0 0 0-.25-.25Z"></path></svg>';

async function copyText(text) {
  try {
    await navigator.clipboard.writeText(text);
    return true;
  } catch (error) {
    const area = document.createElement('textarea');
    area.value = text;
    area.setAttribute('readonly', '');
    area.style.position = 'fixed';
    area.style.opacity = '0';
    document.body.append(area);
    area.select();
    const done = document.execCommand('copy');
    area.remove();
    return done;
  }
}

// Each code block gets a header with its language and a copy button.
function frameCode() {
  for (const pre of article.querySelectorAll('pre')) {
    if (pre.closest('.code-block, .mermaid-diagram')) continue;
    const box = pre.closest('.highlight, .snippet-clipboard-content') || pre;
    if (box.classList.contains('highlight-source-mermaid')) continue;
    const kind = [...box.classList].map((name) => /^highlight-(?:source|text)-(.+)$/.exec(name)).find(Boolean);
    const figure = document.createElement('figure');
    figure.className = 'code-block';
    const head = document.createElement('div');
    head.className = 'code-block-head';
    const label = document.createElement('span');
    label.textContent = kind ? kind[1] : 'text';
    const button = document.createElement('button');
    button.type = 'button';
    button.setAttribute('aria-label', 'Copy code');
    button.innerHTML = COPY_ICON + '<span>Copy</span>';
    let reset = 0;
    button.addEventListener('click', async () => {
      const done = await copyText(pre.textContent);
      button.classList.toggle('copied', done);
      button.lastChild.textContent = done ? 'Copied' : 'Copy failed';
      clearTimeout(reset);
      reset = setTimeout(() => {
        button.classList.remove('copied');
        button.lastChild.textContent = 'Copy';
      }, 1600);
    });
    head.append(label, button);
    const body = document.createElement('div');
    body.className = 'code-body';
    box.replaceWith(figure);
    body.append(box);
    figure.append(head, body);
  }
}

// The progress line under the bar and the contents entry for the section being read.
const bar = document.querySelector('.bar.progress');
let tracked = [];
let current = null;
function track() {
  const end = document.documentElement.scrollHeight - innerHeight;
  if (bar) bar.style.setProperty('--progress', end > 0 ? Math.min(1, scrollY / end).toFixed(4) : '0');
  let found = tracked[0] || null;
  if (end > 0 && scrollY >= end - 2) found = tracked[tracked.length - 1] || null;
  else for (const item of tracked) {
    if (item.heading.getBoundingClientRect().top > 96) break;
    found = item;
  }
  if (found === current) return;
  if (current) current.link.removeAttribute('aria-current');
  current = found;
  if (!current) return;
  current.link.setAttribute('aria-current', 'location');
  if (toc && toc.scrollHeight > toc.clientHeight) {
    const top = current.link.offsetTop;
    if (top < toc.scrollTop || top > toc.scrollTop + toc.clientHeight - 40) toc.scrollTop = top - toc.clientHeight / 3;
  }
}
let tracking = false;
function scheduleTrack() {
  if (tracking) return;
  tracking = true;
  requestAnimationFrame(() => {
    tracking = false;
    track();
  });
}
addEventListener('scroll', scheduleTrack, { passive: true });
addEventListener('resize', scheduleTrack);
if (toc) {
  const wide = matchMedia('(min-width:1240px)');
  const openRail = () => { if (wide.matches) toc.open = true; };
  wide.addEventListener('change', openRail);
  openRail();
}

let onShow = null;
let onDiagram = null;
function show(content) {
  if (onShow) onShow();
  if (poub) {
    for (const image of content.querySelectorAll('img[src]')) {
      const found = local(image.getAttribute('src'));
      if (found) image.src = poub + encodeURIComponent(found.name);
    }
    for (const link of content.querySelectorAll('a[href]')) {
      const found = local(link.getAttribute('href'));
      if (!found) continue;
      link.href = markdownName.test(found.name)
        ? md + encodeURIComponent(found.name) + found.hash
        : poub + encodeURIComponent(found.name);
    }
  }
  article.replaceChildren(content);

  const seen = new Map();
  const entries = [];
  for (const heading of article.querySelectorAll(':is(h1, h2, h3, h4, h5, h6):not(.sr-only)')) {
    const text = heading.textContent.trim();
    let slug = text.toLowerCase().replace(/[^\\p{L}\\p{N}\\s_-]/gu, '').replace(/\\s/g, '-') || 'section';
    const used = seen.get(slug) || 0;
    seen.set(slug, used + 1);
    if (used) slug += '-' + used;
    heading.id = slug;
    const anchor = document.createElement('a');
    anchor.className = 'anchor';
    anchor.href = '#' + slug;
    anchor.textContent = '#';
    anchor.setAttribute('aria-label', 'Link to ' + text);
    heading.prepend(anchor);
    const level = Number(heading.tagName[1]);
    if (level <= 3) entries.push({ slug: slug, text: text, level: level });
  }

  if (toc) {
    const list = toc.querySelector('ol');
    list.replaceChildren();
    tracked = [];
    current = null;
    const top = Math.min(...entries.map((entry) => entry.level));
    for (const entry of entries) {
      const item = document.createElement('li');
      item.style.paddingLeft = (entry.level - top) * 14 + 'px';
      const link = document.createElement('a');
      link.href = '#' + entry.slug;
      link.textContent = entry.text;
      item.append(link);
      list.append(item);
      tracked.push({ heading: document.getElementById(entry.slug), link: link });
    }
    toc.hidden = entries.length < 3;
  }
  frameCode();
  drawDiagrams();
  scheduleTrack();
}

show(renderLocal());

if (location.hash && !/^#L\\d/.test(location.hash)) {
  let target = null;
  try { target = document.getElementById(decodeURIComponent(location.hash.slice(1))); } catch (error) { /* bad hash */ }
  if (target) target.scrollIntoView();
}

// #find=12:words, from the notes search: the innermost block holding source line 12, with
// the words marked the way the search matched them, ignoring case and accents.
function findLine() {
  const wanted = /^#find=(\\d+)(?::(.*))?$/.exec(location.hash);
  if (!wanted) return;
  const line = Number(wanted[1]);
  let words = [];
  try { words = decodeURIComponent(wanted[2] || '').split(/\\s+/).filter(Boolean); } catch (error) { /* bad hash */ }
  const fold = (text) => text.normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
  words = words.map(fold).filter(Boolean);
  let block = null, before = null;
  for (const element of article.querySelectorAll('[data-line]')) {
    const start = Number(element.dataset.line), end = Number(element.dataset.lineEnd || start);
    if (start <= line && line <= end && (!block || block.contains(element))) block = element;
    if (start <= line) before = element;
  }
  block = block || before;
  if (!block) return;
  article.querySelectorAll('mark.find-hit').forEach((mark) => {
    const parent = mark.parentNode;
    mark.replaceWith(...mark.childNodes);
    parent.normalize();
  });
  article.querySelectorAll('.find-target').forEach((element) => element.classList.remove('find-target'));
  const walker = document.createTreeWalker(block, NodeFilter.SHOW_TEXT);
  const nodes = [];
  while (walker.nextNode()) nodes.push(walker.currentNode);
  for (const node of nodes) {
    const text = node.nodeValue;
    let folded = '';
    const origin = [];
    const ends = [];
    for (let index = 0; index < text.length;) {
      const character = String.fromCodePoint(text.codePointAt(index));
      const piece = fold(character);
      folded += piece;
      for (let count = 0; count < piece.length; count++) { origin.push(index); ends.push(index + character.length); }
      index += character.length;
    }
    const found = [];
    for (const word of words) {
      for (let at = folded.indexOf(word); at >= 0; at = folded.indexOf(word, at + word.length)) {
        found.push([origin[at], ends[at + word.length - 1]]);
      }
    }
    found.sort((a, b) => a[0] - b[0] || b[1] - a[1]);
    const ranges = [];
    for (const range of found) {
      const previous = ranges[ranges.length - 1];
      if (previous && range[0] <= previous[1]) previous[1] = Math.max(previous[1], range[1]);
      else ranges.push(range);
    }
    let current = node, offset = 0;
    for (const [start, end] of ranges) {
      const hit = current.splitText(start - offset);
      current = hit.splitText(end - start);
      offset = end;
      const mark = document.createElement('mark');
      mark.className = 'find-hit';
      hit.replaceWith(mark);
      mark.append(hit);
    }
  }
  block.classList.add('find-target');
  (block.querySelector('mark.find-hit') || block).scrollIntoView({ block: 'center' });
}
findLine();
addEventListener('hashchange', findLine);
addEventListener('hashchange', () => {
  for (const stage of document.querySelectorAll('.diagram-stage[data-diagram]')) if (diagramFromHash(stage)) break;
});

// Review mode: numbers for the source lines behind each block, and comments kept on the server
// next to the file. Comment text only ever goes in through textContent.
const commentsUrl = article.dataset.comments || '';
const reviewToggle = document.getElementById('review');
const dock = document.getElementById('review-dock');
if (commentsUrl && reviewToggle && dock) {
  const coarse = matchMedia('(pointer: coarse)');
  const commentMax = Number(article.dataset.commentMax) || 4000;
  const badge = reviewToggle.querySelector('.count');
  const dockText = dock.querySelector('.review-dock-text');
  const commentButton = dock.querySelector('[data-review="comment"]');
  const clearButton = dock.querySelector('[data-review="clear"]');
  const copyButton = dock.querySelector('[data-review="copy"]');
  const gutter = document.createElement('div');
  gutter.className = 'review-gutter';
  let reviewing = false;
  let view = { lines: 0, comments: [] };
  let promptText = '';
  let selection = null;
  let marks = [];
  let composer = null;
  let message = '';
  let messageTimer = 0;

  const range = (start, end) => start === end ? 'Line ' + start : 'Lines ' + start + '–' + end;
  const plural = (count) => count + (count === 1 ? ' comment' : ' comments');
  const previousBusy = window.liveBusy;
  window.liveBusy = () => Boolean(composer) || Boolean(article.querySelector('.review-comment form'))
    || (previousBusy ? previousBusy() : false);

  function make(tag, className, text) {
    const element = document.createElement(tag);
    if (className) element.className = className;
    if (text !== undefined) element.textContent = text;
    if (tag === 'button') element.type = 'button';
    return element;
  }

  function ago(date) {
    const seconds = (date.getTime() - Date.now()) / 1000;
    const format = new Intl.RelativeTimeFormat(undefined, { numeric: 'auto' });
    for (const [unit, size] of [['day', 86400], ['hour', 3600], ['minute', 60]]) {
      if (Math.abs(seconds) >= size) return format.format(Math.round(seconds / size), unit);
    }
    return 'just now';
  }

  function notify(text) {
    message = text;
    clearTimeout(messageTimer);
    messageTimer = setTimeout(() => { message = ''; updateDock(); }, 3000);
    updateDock();
  }

  async function call(url, options) {
    const response = await fetch(url, Object.assign({ cache: 'no-store' }, options));
    const answer = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(answer.error || response.statusText);
    return answer;
  }

  async function loadPrompt() {
    const response = await fetch(commentsUrl + '?format=prompt', { cache: 'no-store' });
    promptText = response.ok ? await response.text() : '';
  }

  async function refresh() {
    view = await call(commentsUrl);
    await loadPrompt();
    redraw();
  }

  async function post(action, query, body) {
    view = await call(commentsUrl.replace('/comments/', '/comments/' + action + '/') + query, {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: body === undefined ? '' : JSON.stringify(body),
    });
    await loadPrompt();
    redraw();
  }

  function redraw() {
    const count = view.comments.length;
    badge.textContent = String(count);
    badge.hidden = !count;
    const label = count ? 'Review, ' + plural(count) : 'Review';
    reviewToggle.setAttribute('aria-label', label);
    reviewToggle.title = label;
    if (!reviewing) return;
    buildMarks();
    drawThreads();
    paint();
  }

  // Every block that maps to source lines, and each line of every code block.
  function collect() {
    const found = [];
    for (const element of article.querySelectorAll('[data-line]')) {
      if (element.closest('.code-body, .review-thread, .review-composer')) continue;
      const start = Number(element.dataset.line);
      if (start) found.push({ element: element, start: start, end: Number(element.dataset.lineEnd) || start, code: false });
    }
    for (const box of article.querySelectorAll('.code-body [data-code]')) {
      const first = Number(box.dataset.code);
      const pre = box.matches('pre') ? box : box.querySelector('pre');
      if (!first || !pre) continue;
      const count = pre.textContent.replace(/\\n$/, '').split('\\n').length;
      const last = Math.min(first + count - 1, Number(box.dataset.lineEnd) || Infinity);
      for (let line = first; line <= last; line++) {
        found.push({ element: box, start: line, end: line, code: true, body: box.closest('.code-body') });
      }
    }
    return found.sort((a, b) => a.start - b.start || a.end - b.end);
  }

  function buildMarks() {
    gutter.replaceChildren();
    for (const old of article.querySelectorAll('.code-gutter')) old.remove();
    const commented = view.comments.filter((comment) => !comment.outdated);
    marks = collect();
    const columns = new Map();
    for (const mark of marks) {
      const button = make('button', 'review-line', String(mark.start));
      button.dataset.start = mark.start;
      button.dataset.end = mark.end;
      button.setAttribute('aria-label', range(mark.start, mark.end));
      if (mark.end > mark.start) button.title = range(mark.start, mark.end);
      if (commented.some((comment) => comment.start <= mark.end && comment.end >= mark.start)) button.classList.add('commented');
      mark.button = button;
      if (mark.code) {
        let column = columns.get(mark.body);
        if (!column) {
          column = make('div', 'code-gutter');
          mark.body.prepend(column);
          columns.set(mark.body, column);
        }
        column.append(button);
      } else {
        gutter.append(button);
      }
    }
    article.append(gutter);
    place();
  }

  function place() {
    if (!reviewing) return;
    const top = article.getBoundingClientRect().top;
    for (const mark of marks) {
      if (mark.code) continue;
      const box = mark.element.getBoundingClientRect();
      mark.button.hidden = !box.height;
      if (!box.height) continue;
      const row = mark.element.tagName === 'TR';
      const style = getComputedStyle(row ? mark.element.cells[0] || mark.element : mark.element);
      const line = parseFloat(style.lineHeight) || parseFloat(style.fontSize) * 1.5;
      const offset = mark.element.tagName === 'HR'
        ? box.height / 2 - 12
        : (parseFloat(style.paddingTop) || 0) + (parseFloat(style.borderTopWidth) || 0) + (line - 24) / 2;
      mark.button.style.top = (box.top - top + offset) + 'px';
    }
    drawBands();
  }

  const inside = (mark) => Boolean(selection) && mark.start <= selection.end && mark.end >= selection.start;

  // Code lines are not elements, so their selection is a tinted band over the block.
  function drawBands() {
    for (const band of article.querySelectorAll('.code-band')) band.remove();
    const spans = new Map();
    for (const mark of marks) {
      if (!mark.code || !inside(mark)) continue;
      const span = spans.get(mark.body) || [mark.button, mark.button];
      span[1] = mark.button;
      spans.set(mark.body, span);
    }
    for (const [body, [first, last]] of spans) {
      const band = make('div', 'code-band');
      band.style.top = first.offsetTop + 'px';
      band.style.height = (last.offsetTop + last.offsetHeight - first.offsetTop) + 'px';
      body.append(band);
    }
  }

  function paint() {
    for (const element of article.querySelectorAll('.review-selected')) element.classList.remove('review-selected');
    for (const mark of marks) {
      const on = inside(mark);
      mark.button.classList.toggle('selected', on);
      mark.button.setAttribute('aria-pressed', String(on));
      if (on && !mark.code) mark.element.classList.add('review-selected');
    }
    drawBands();
    updateDock();
  }

  function remember() {
    const hash = selection ? '#L' + selection.start + (selection.end > selection.start ? '-L' + selection.end : '') : '';
    if (hash || /^#L\\d/.test(location.hash)) history.replaceState(null, '', location.pathname + location.search + hash);
  }

  function choose(start, end, extend) {
    if (extend && selection) {
      const anchor = selection.anchor;
      selection = { start: Math.min(anchor.start, start), end: Math.max(anchor.end, end), anchor: anchor };
    } else {
      selection = { start: start, end: end, anchor: { start: start, end: end } };
    }
    remember();
    paint();
  }

  function clear() {
    selection = null;
    remember();
    paint();
  }

  function updateDock() {
    const count = view.comments.length;
    dock.classList.toggle('error', message.startsWith('!'));
    if (message) dockText.textContent = message.replace(/^!/, '');
    else if (selection) dockText.textContent = range(selection.start, selection.end) + ' selected';
    else if (count) dockText.textContent = plural(count);
    else dockText.textContent = coarse.matches ? 'Tap a line number' : 'Click a line number, shift-click for a range';
    commentButton.hidden = !selection || Boolean(composer);
    clearButton.hidden = !selection;
    copyButton.hidden = Boolean(selection) || !count;
  }

  // The last mapped block or code line at or before the line: comments and the form go after it.
  function spot(line) {
    let best = null;
    for (const mark of marks) if (mark.start <= line) best = mark;
    return best || marks[0] || null;
  }

  const lineOf = (element) => Number(element?.dataset.line || element?.querySelector('[data-line]')?.dataset.line || 0);

  // Where comments for a range ending on this mark go: [node, 'after' | 'before' | 'append'].
  function slot(mark, start) {
    const element = mark.element;
    if (mark.code) return [element.closest('.code-block'), 'after'];
    if (element.tagName === 'TR') return [element.closest('table'), 'after'];
    const own = element.tagName === 'LI' ? element : element.parentElement?.tagName === 'LI' ? element.parentElement : null;
    if (!own) return [element, 'after'];
    // A range covering whole list items goes after their list, not inside the last item.
    let item = own;
    let list = null;
    while (item && start < lineOf(item) && lineOf(item.parentElement.firstElementChild) >= start) {
      list = item.parentElement;
      item = list.parentElement?.tagName === 'LI' ? list.parentElement : null;
    }
    if (list) return [list, 'after'];
    if (element !== own) return [element, 'after'];
    const nested = own.querySelector(':scope > ul, :scope > ol');
    return nested ? [nested, 'before'] : [own, 'append'];
  }

  function insertAt([node, how], content) {
    if (how === 'before') node.before(content);
    else if (how === 'append') node.append(content);
    else node.after(content);
  }

  function editor(text, label, action, save, cancel) {
    const form = make('form', 'review-form');
    const area = make('textarea');
    area.value = text;
    area.rows = 4;
    area.maxLength = commentMax;
    area.placeholder = 'Leave a comment';
    area.setAttribute('aria-label', label);
    const row = make('div', 'review-actions');
    const hint = make('span', 'review-hint', /Mac|iP/.test(navigator.platform) ? '⌘ Enter to save' : 'Ctrl+Enter to save');
    const cancelButton = make('button', '', 'Cancel');
    const submit = make('button', 'primary', action);
    submit.type = 'submit';
    row.append(hint, cancelButton, submit);
    form.append(area, row);
    form.addEventListener('submit', async (event) => {
      event.preventDefault();
      if (!area.value.trim()) {
        area.focus();
        return;
      }
      submit.disabled = true;
      try {
        await save(area.value);
      } catch (error) {
        submit.disabled = false;
        notify('!Saving failed: ' + (error.message || error));
      }
    });
    area.addEventListener('keydown', (event) => {
      if (event.key === 'Enter' && (event.ctrlKey || event.metaKey)) {
        event.preventDefault();
        form.requestSubmit();
      } else if (event.key === 'Escape') {
        event.preventDefault();
        cancel();
      }
    });
    cancelButton.addEventListener('click', cancel);
    return { form: form, area: area };
  }

  function closeComposer() {
    if (composer) composer.remove();
    composer = null;
    updateDock();
  }

  function compose() {
    if (!selection) return;
    closeComposer();
    const target = { start: selection.start, end: selection.end };
    const mark = spot(target.end);
    if (!mark) return;
    const holder = make('div', 'review-composer');
    holder.append(make('p', 'review-composer-title', 'Comment on ' + range(target.start, target.end).toLowerCase()));
    const { form, area } = editor('', 'Comment on ' + range(target.start, target.end).toLowerCase(), 'Comment', async (text) => {
      await post('add', '', { start: target.start, end: target.end, body: text });
      closeComposer();
      clear();
      notify('Comment added');
    }, closeComposer);
    holder.append(form);
    insertAt(slot(mark, target.start), holder);
    composer = holder;
    updateDock();
    area.focus({ preventScroll: true });
    holder.scrollIntoView({ block: 'nearest', behavior: 'smooth' });
  }

  function card(comment) {
    const item = make('section', 'review-comment' + (comment.outdated ? ' outdated' : ''));
    const head = make('header');
    const where = make('button', 'review-where', range(comment.start, comment.end));
    where.setAttribute('aria-label', 'Select ' + range(comment.start, comment.end).toLowerCase());
    where.addEventListener('click', () => choose(comment.start, comment.end, false));
    const stamp = new Date((comment.updated || comment.created) * 1000);
    const when = make('time', '', ago(stamp) + (comment.updated > comment.created + 1 ? ', edited' : ''));
    when.dateTime = stamp.toISOString();
    when.title = stamp.toLocaleString();
    const tools = make('span', 'review-tools');
    const edit = make('button', '', 'Edit');
    const remove = make('button', '', 'Delete');
    tools.append(edit, remove);
    head.append(where, when, tools);
    item.append(head);
    if (comment.outdated) {
      item.append(make('p', 'review-note', 'These lines changed after the comment. It was written on:'));
      item.append(make('pre', 'review-quote', comment.quote.join('\\n')));
    }
    const body = make('p', 'review-body', comment.body);
    item.append(body);
    edit.addEventListener('click', () => {
      if (item.querySelector('form')) return;
      const done = () => {
        form.remove();
        body.hidden = false;
        edit.disabled = false;
      };
      const { form, area } = editor(comment.body, 'Edit the comment on ' + range(comment.start, comment.end).toLowerCase(), 'Save', async (text) => {
        await post('edit', '?id=' + encodeURIComponent(comment.id), { body: text });
        notify('Comment saved');
      }, done);
      body.hidden = true;
      edit.disabled = true;
      body.after(form);
      area.focus();
    });
    let armed = 0;
    remove.addEventListener('click', async () => {
      if (!armed) {
        remove.textContent = 'Confirm delete';
        remove.classList.add('danger');
        armed = setTimeout(() => {
          armed = 0;
          remove.textContent = 'Delete';
          remove.classList.remove('danger');
        }, 3000);
        return;
      }
      clearTimeout(armed);
      remove.disabled = true;
      try {
        await post('delete', '?id=' + encodeURIComponent(comment.id));
        notify('Comment deleted');
      } catch (error) {
        remove.disabled = false;
        notify('!Deleting failed: ' + (error.message || error));
      }
    });
    return item;
  }

  function drawThreads() {
    for (const old of article.querySelectorAll('.review-thread')) old.remove();
    const groups = [];
    for (const comment of view.comments) {
      const mark = spot(comment.end);
      if (!mark) continue;
      const where = slot(mark, comment.start);
      let group = groups.find((other) => other.where[0] === where[0] && other.where[1] === where[1]);
      if (!group) groups.push((group = { where, end: 0, comments: [] }));
      group.end = Math.max(group.end, comment.end);
      group.comments.push(comment);
    }
    // Inserted from the bottom up, so threads after the same block keep their line order.
    for (const group of groups.sort((a, b) => b.end - a.end)) {
      const thread = make('div', 'review-thread');
      for (const comment of group.comments) thread.append(card(comment));
      insertAt(group.where, thread);
    }
  }

  function enter() {
    reviewing = true;
    article.classList.add('reviewing');
    document.body.classList.add('reviewing');
    dock.hidden = false;
    reviewToggle.setAttribute('aria-pressed', 'true');
    buildMarks();
    drawThreads();
    paint();
  }

  function leave() {
    reviewing = false;
    closeComposer();
    selection = null;
    remember();
    gutter.remove();
    for (const element of article.querySelectorAll('.code-gutter, .code-band, .review-thread')) element.remove();
    for (const element of article.querySelectorAll('.review-selected')) element.classList.remove('review-selected');
    marks = [];
    article.classList.remove('reviewing');
    document.body.classList.remove('reviewing');
    dock.hidden = true;
    reviewToggle.setAttribute('aria-pressed', 'false');
  }

  onShow = () => { if (reviewing) leave(); };
  onDiagram = () => {
    if (!reviewing) return;
    buildMarks();
    paint();
  };

  reviewToggle.hidden = false;
  reviewToggle.addEventListener('click', () => (reviewing ? leave() : enter()));
  article.addEventListener('mousedown', (event) => {
    if (event.shiftKey && event.target.closest('.review-line')) event.preventDefault();
  });
  article.addEventListener('click', (event) => {
    const button = event.target.closest('.review-line');
    if (!button || !reviewing) return;
    const start = Number(button.dataset.start), end = Number(button.dataset.end);
    const touch = coarse.matches && Boolean(selection);
    if (touch && start >= selection.start && end <= selection.end) clear();
    else choose(start, end, event.shiftKey || touch);
  });
  commentButton.addEventListener('click', compose);
  clearButton.addEventListener('click', clear);
  dock.querySelector('[data-review="done"]').addEventListener('click', leave);
  copyButton.addEventListener('click', async () => {
    const done = promptText ? await copyText(promptText) : false;
    notify(done ? 'Copied ' + plural(view.comments.length) + ' as a prompt' : '!Copy failed');
  });
  document.addEventListener('keydown', (event) => {
    if (reviewing && event.key === 'Escape' && selection && !composer && !event.target.closest('textarea')) clear();
  });
  new ResizeObserver(() => { if (reviewing) requestAnimationFrame(place); }).observe(article);

  // #L12 or #L12-L14 opens review mode with those lines selected, as on GitHub.
  function follow() {
    const wanted = /^#L(\\d+)(?:-L(\\d+))?$/.exec(location.hash);
    if (!wanted) return;
    if (!reviewing) enter();
    const start = Math.max(1, Math.min(Number(wanted[1]), view.lines || 1));
    choose(start, Math.max(start, Math.min(Number(wanted[2] || start), view.lines || start)), false);
    const first = marks.find(inside);
    if (first) (first.code ? first.button : first.element).scrollIntoView({ block: 'center' });
  }
  addEventListener('hashchange', follow);
  refresh().catch((error) => console.error('comments', error)).then(follow);
}
})();
"""
