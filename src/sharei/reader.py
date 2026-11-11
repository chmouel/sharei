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
        const match = ALERT_MARK.exec(inline.content);
        if (!match) continue;
        const kind = match[1].toLowerCase();
        let depth = 0, close = index;
        for (; close < tokens.length; close++) {
          if (tokens[close].type === 'blockquote_open') depth++;
          else if (tokens[close].type === 'blockquote_close' && --depth === 0) break;
        }
        token.meta = { alert: kind };
        tokens[close].meta = { alert: kind };
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
    const kind = tokens[index].meta && tokens[index].meta.alert;
    if (!kind) return self.renderToken(tokens, index, options);
    const [title, icon, path] = ALERTS[kind];
    return '<div class="markdown-alert markdown-alert-' + kind + '"><p class="markdown-alert-title"><svg class="octicon octicon-' + icon + ' mr-2" viewBox="0 0 16 16" width="16" height="16" aria-hidden="true"><path d="' + path + '"></path></svg>' + title + '</p>\\n';
  };
  rules.blockquote_close = (tokens, index, options, env, self) =>
    tokens[index].meta && tokens[index].meta.alert ? '</div>\\n' : self.renderToken(tokens, index, options);
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

let markdown = null;
function renderLocal() {
  try {
    if (!markdown) {
      markdown = window.markdownit({ html: true, linkify: true });
      // Without a scheme, README.md would become a link to a Moldovan domain.
      markdown.linkify.set({ fuzzyLink: false });
      if (window.markdownitFootnote) markdown.use(window.markdownitFootnote);
      if (window.markdownitEmoji) markdown.use(window.markdownitEmoji);
      frontMatterPlugin(markdown);
      githubFlavour(markdown);
    }
    return sanitize(markdown.render(source));
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
    for (const block of diagrams) {
      const id = 'mermaid-' + diagramCount++;
      try {
        const result = await mermaid.render(id, block.textContent);
        const holder = document.createElement('div');
        holder.className = 'mermaid-diagram';
        if (block.dataset.line) {
          holder.dataset.line = block.dataset.line;
          holder.dataset.lineEnd = block.dataset.lineEnd;
        }
        holder.innerHTML = result.svg;
        block.replaceWith(holder);
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
