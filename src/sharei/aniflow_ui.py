DIRECTORY_CSS = """
  .aniflow-browser { --folder-color:var(--fgColor-attention); --document-color:var(--fgColor-accent); }
  .aniflow-browser .sr-only { position:absolute; width:1px; height:1px; padding:0; margin:-1px; overflow:hidden; clip:rect(0,0,0,0); white-space:nowrap; border:0; }
  .aniflow-browser .browser-shell { width:min(100%, 1120px); margin:0 auto; padding:34px 40px 80px; }
  .aniflow-browser .browser-masthead { display:flex; align-items:center; justify-content:space-between; gap:32px; padding-bottom:30px; margin-bottom:28px; border-bottom:1px solid var(--borderColor-default); }
  .aniflow-browser .aniflow-brand { width:330px; max-width:48%; margin:0; flex-shrink:0; }
  .aniflow-browser .browser-demo { display:flex; align-items:center; gap:14px; color:var(--fgColor-default); text-decoration:none; }
  .aniflow-browser .browser-demo strong { display:block; margin-bottom:4px; font-size:15px; font-weight:650; }
  .aniflow-browser .browser-demo strong + span { display:block; font-size:13px; color:var(--fgColor-muted); }
  .aniflow-browser .browser-demo > svg { width:20px; height:20px; margin-left:10px; color:var(--fgColor-muted); }
  .aniflow-browser .demo-play { display:grid; place-items:center; flex:0 0 42px; height:42px; border:1px solid color-mix(in srgb, var(--document-color) 35%, var(--borderColor-default)); border-radius:50%; background:color-mix(in srgb, var(--document-color) 9%, var(--bgColor-default)); color:var(--document-color); }
  .aniflow-browser .demo-play::before { content:''; margin-left:3px; border-top:6px solid transparent; border-bottom:6px solid transparent; border-left:9px solid currentColor; }
  .aniflow-browser .browser-demo:hover strong { color:var(--document-color); }
  .aniflow-browser .browser-trail ol { display:flex; flex-wrap:wrap; gap:6px 10px; list-style:none; margin:0; padding:0; color:var(--fgColor-muted); font-size:13px; }
  .aniflow-browser .browser-trail li { display:flex; align-items:center; gap:10px; overflow-wrap:anywhere; }
  .aniflow-browser .browser-trail li + li::before { content:'/'; color:var(--borderColor-default); }
  .aniflow-browser .browser-trail a { color:var(--fgColor-muted); text-decoration:none; }
  .aniflow-browser .browser-trail a:hover { color:var(--document-color); text-decoration:underline; }
  .aniflow-browser .browser-heading { display:flex; align-items:center; justify-content:space-between; gap:24px; margin:12px 0 30px; }
  .aniflow-browser h1 { margin:0; color:var(--fgColor-default); font-size:clamp(32px, 4vw, 54px); font-weight:750; line-height:1.12; letter-spacing:-.035em; overflow-wrap:anywhere; }
  .aniflow-browser .folder-summary { display:flex; flex-wrap:wrap; gap:12px; margin:12px 0 0; color:var(--fgColor-muted); font-size:14px; }
  .aniflow-browser .folder-summary > span { color:var(--borderColor-default); }
  .aniflow-browser .folder-up { display:inline-flex; align-items:center; gap:8px; padding:10px 0 10px 12px; color:var(--fgColor-muted); font-size:13px; text-decoration:none; white-space:nowrap; }
  .aniflow-browser .folder-up svg { width:18px; height:18px; transform:rotate(180deg); }
  .aniflow-browser .folder-up:hover { color:var(--document-color); }
  .aniflow-browser .browser-toolbar { display:flex; gap:16px; align-items:center; padding:8px; margin-bottom:30px; border:1px solid var(--borderColor-default); border-radius:12px; background:var(--bgColor-muted); }
  .aniflow-browser .folder-filter { display:flex; flex:1; align-items:center; min-width:0; gap:12px; padding-left:10px; color:var(--fgColor-muted); }
  .aniflow-browser .folder-filter svg { flex:0 0 20px; width:20px; height:20px; fill:currentColor; }
  .aniflow-browser .folder-filter input { width:100%; min-width:0; height:42px; border:0; outline:none; background:transparent; color:var(--fgColor-default); font:inherit; font-size:15px; }
  .aniflow-browser .folder-filter input::placeholder { color:var(--fgColor-muted); opacity:1; }
  .aniflow-browser .folder-filter:focus-within { color:var(--document-color); }
  .aniflow-browser .browser-toolbar:has(input:focus-visible) { outline:2px solid var(--document-color); outline-offset:2px; }
  .aniflow-browser .folder-sort { display:flex; flex-shrink:0; align-items:center; gap:8px; padding-left:16px; border-left:1px solid var(--borderColor-default); font-size:13px; color:var(--fgColor-muted); }
  .aniflow-browser .folder-sort select { max-width:155px; height:38px; padding:0 8px; border:0; border-radius:6px; background:var(--bgColor-muted); color:var(--fgColor-default); font:inherit; cursor:pointer; }
  .aniflow-browser .directory-group + .directory-group { margin-top:34px; }
  .aniflow-browser .directory-group h2 { display:flex; gap:10px; align-items:baseline; margin:0 0 18px; font-size:18px; letter-spacing:-.02em; font-weight:650; }
  .aniflow-browser .group-count { font-size:13px; color:var(--fgColor-muted); font-weight:400; }
  .aniflow-browser .directory-list { list-style:none; margin:0; padding:0; }
  .aniflow-browser .directory-list li { min-width:0; }
  .aniflow-browser .directory-list a { color:var(--fgColor-default); text-decoration:none; }
  .aniflow-browser .file-label { min-width:0; overflow-wrap:anywhere; font-weight:550; }
  .aniflow-browser .entry-arrow { display:grid; place-items:center; color:var(--fgColor-muted); }
  .aniflow-browser .entry-arrow svg { width:20px; height:20px; transition:transform .15s; }
  .aniflow-browser .directory-list a:hover .entry-arrow { color:var(--document-color); }
  .aniflow-browser .directory-list a:hover .entry-arrow svg { transform:translateX(3px); }
  .aniflow-browser .folders-list { display:grid; grid-template-columns:repeat(3, minmax(0, 1fr)); gap:22px 18px; padding-top:7px; }
  .aniflow-browser .folders-list a { position:relative; display:grid; grid-template-columns:1fr 22px; gap:18px 12px; align-items:center; min-height:124px; padding:18px 20px; border:1px solid color-mix(in srgb, var(--folder-color) 25%, var(--borderColor-default)); border-radius:0 12px 12px 12px; background:color-mix(in srgb, var(--folder-color) 4%, var(--bgColor-default)); }
  .aniflow-browser .folders-list a::before { content:''; position:absolute; left:-1px; top:-8px; width:38%; height:8px; border:1px solid color-mix(in srgb, var(--folder-color) 25%, var(--borderColor-default)); border-bottom:0; border-radius:6px 8px 0 0; background:color-mix(in srgb, var(--folder-color) 12%, var(--bgColor-default)); }
  .aniflow-browser .folders-list a:hover { border-color:var(--folder-color); background:color-mix(in srgb, var(--folder-color) 9%, var(--bgColor-default)); }
  .aniflow-browser .folders-list a:hover::before { border-color:var(--folder-color); }
  .aniflow-browser .folder-symbol { grid-column:1 / -1; display:flex; color:var(--folder-color); }
  .aniflow-browser .folder-symbol svg { width:28px; height:28px; }
  .aniflow-browser .folders-list .file-label { font-size:16px; }
  .aniflow-browser .directory-columns { display:grid; grid-template-columns:minmax(0,1fr) 140px 72px; column-gap:18px; padding:0 58px 10px 74px; color:var(--fgColor-muted); font-size:12px; }
  .aniflow-browser .directory-columns span:last-child { text-align:right; }
  .aniflow-browser .documents-list { border:1px solid var(--borderColor-default); border-radius:12px; overflow:hidden; }
  .aniflow-browser .documents-list li + li { border-top:1px solid var(--borderColor-muted); }
  .aniflow-browser .documents-list a { display:grid; grid-template-columns:36px minmax(0,1fr) 140px 72px 20px; align-items:center; gap:18px; min-height:78px; padding:16px 20px; }
  .aniflow-browser .documents-list a:hover { background:var(--bgColor-muted); }
  .aniflow-browser .document-symbol { display:grid; place-items:center; color:var(--document-color); }
  .aniflow-browser .document-symbol svg { width:26px; height:30px; }
  .aniflow-browser .documents-list .file-label { font-size:15px; }
  .aniflow-browser .file-extension { color:var(--fgColor-muted); font-weight:400; }
  .aniflow-browser .file-modified, .aniflow-browser .file-size { color:var(--fgColor-muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .aniflow-browser .file-size { text-align:right; }
  .aniflow-browser .browser-empty { display:flex; flex-direction:column; align-items:center; padding:52px 24px; border:1px dashed var(--borderColor-default); border-radius:12px; text-align:center; }
  .aniflow-browser .empty-symbol { display:grid; place-items:center; width:60px; height:60px; margin-bottom:16px; border-radius:50%; background:var(--bgColor-muted); color:var(--fgColor-muted); }
  .aniflow-browser .empty-symbol svg { width:28px; height:28px; }
  .aniflow-browser .browser-empty h2 { margin:0 0 8px; font-size:20px; font-weight:600; }
  .aniflow-browser .browser-empty p { max-width:32em; margin:0 0 20px; font-size:14px; line-height:1.6; color:var(--fgColor-muted); }
  .aniflow-browser .browser-empty :is(a, button) { padding:10px 16px; border:1px solid var(--borderColor-default); border-radius:8px; background:var(--bgColor-default); color:var(--document-color); font:600 14px/1.4 system-ui,sans-serif; text-decoration:none; cursor:pointer; }
  .aniflow-browser :is(.directory-group, .directory-list li, .browser-empty)[hidden] { display:none; }
  .aniflow-browser :is(a, select, button):focus-visible { outline:2px solid var(--document-color); outline-offset:3px; border-radius:6px; }
  @media (prefers-reduced-motion:reduce) { .aniflow-browser .entry-arrow svg { transition:none; } }
  @media (max-width:799px) {
    .aniflow-browser .browser-shell { padding:28px 24px 60px; }
    .aniflow-browser .browser-demo > svg, .aniflow-browser .browser-demo strong + span { display:none; }
    .aniflow-browser .browser-demo { gap:10px; }
    .aniflow-browser .browser-demo strong { max-width:9em; font-size:13px; line-height:1.5; margin:0; }
    .aniflow-browser .demo-play { flex-basis:34px; height:34px; }
    .aniflow-browser .folders-list { grid-template-columns:repeat(2, minmax(0, 1fr)); }
    .aniflow-browser .directory-columns { display:none; }
    .aniflow-browser .documents-list a { grid-template-columns:28px minmax(0, 1fr) auto 18px; gap:5px 12px; padding:16px; }
    .aniflow-browser .document-symbol { grid-row:1 / 3; }
    .aniflow-browser .file-modified { grid-column:2; grid-row:2; font-size:11px; }
    .aniflow-browser .file-size { grid-column:3; grid-row:1 / 3; font-size:11px; }
    .aniflow-browser .documents-list .entry-arrow { grid-column:4; grid-row:1 / 3; }
  }
  @media (max-width:499px) {
    .aniflow-browser .browser-shell { padding:24px 16px 48px; }
    .aniflow-browser .browser-masthead { gap:18px; margin-bottom:22px; padding-bottom:22px; }
    .aniflow-browser .aniflow-brand { max-width:62%; }
    .aniflow-browser .browser-demo { gap:8px; }
    .aniflow-browser .browser-demo strong { max-width:5.5em; font-size:11px; }
    .aniflow-browser .demo-play { flex-basis:28px; height:28px; }
    .aniflow-browser .browser-heading { align-items:flex-start; flex-direction:column; gap:10px; margin-bottom:22px; }
    .aniflow-browser .folder-up { padding:0; min-height:32px; }
    .aniflow-browser .browser-toolbar { flex-wrap:wrap; gap:0; margin-bottom:26px; }
    .aniflow-browser .folder-filter { flex-basis:100%; }
    .aniflow-browser .folder-sort { justify-content:space-between; width:100%; margin-top:4px; padding:4px 2px 0 10px; border:0; border-top:1px solid var(--borderColor-default); }
    .aniflow-browser .folder-sort select { text-align:right; }
    .aniflow-browser .folders-list { gap:20px 12px; }
    .aniflow-browser .folders-list a { min-height:94px; padding:14px 16px; gap:10px 8px; }
    .aniflow-browser .folders-list .file-label { font-size:14px; }
    .aniflow-browser .documents-list a { padding:14px 12px; gap:5px 10px; }
    .aniflow-browser .documents-list .file-label { font-size:14px; }
    .aniflow-browser .directory-group + .directory-group { margin-top:28px; }
  }
"""

UI_CSS = """
  .aniflow-local .bar { z-index:6; }
  .aniflow-local.presenting .aniflow-brand { display:none; }
  .aniflow-local .bar nav { align-items:center; gap:12px; }
  .aniflow-local .bar nav .review-toggle { gap:6px; min-height:36px; padding:6px 8px; }
  .aniflow-local .bar nav select { min-height:36px; }
  .aniflow-menu { position:relative; }
  .aniflow-menu summary { padding:8px 0; color:var(--fgColor-accent); font-weight:600; cursor:pointer; list-style:none; }
  .aniflow-menu summary::-webkit-details-marker { display:none; }
  .aniflow-menu summary::after { content:'⌄'; padding-left:5px; }
  .aniflow-menu .menu-items { position:absolute; top:100%; right:0; min-width:170px; padding:6px; border:1px solid var(--borderColor-default); border-radius:10px; background:var(--bgColor-default); box-shadow:0 8px 24px color-mix(in srgb, var(--fgColor-default) 12%, transparent); }
  .aniflow-menu .menu-items a { display:block; padding:10px; border-radius:6px; }
  .aniflow-menu .menu-items a:hover { background:var(--bgColor-muted); text-decoration:none; }
  .aniflow-local .reader-help { white-space:nowrap; }
  .aniflow-help .aniflow-brand { width:min(260px, 62%); margin:0 0 14px; }
  .aniflow-help .reader .markdown-body h1 { font-size:clamp(1.8rem, 4vw, 2.5rem); }
  .aniflow-help .reader .aniflow-demo { margin:20px 0 28px; }
  .aniflow-help .reader .aniflow-demo .diagram-stage > svg { width:100%; min-height:220px; }
  .aniflow-help .reader .aniflow-demo .diagram-tools { opacity:1; }
  .aniflow-help .reader .demo-actions { display:flex; flex-wrap:wrap; align-items:center; gap:8px; margin:0 0 14px; }
  .aniflow-help .reader .demo-actions button, .aniflow-help .reader .demo-actions a { min-height:42px; padding:8px 14px; border:1px solid var(--borderColor-default); border-radius:9px; background:var(--bgColor-default); color:var(--fgColor-accent); font:600 14px/1.4 system-ui,sans-serif; text-decoration:none; cursor:pointer; }
  .aniflow-help .reader .demo-actions .primary { background:var(--fgColor-accent); color:var(--bgColor-default); border-color:var(--fgColor-accent); }
  .aniflow-help .reader .demo-actions button:disabled { opacity:.5; cursor:wait; }
  .aniflow-help .reader .demo-actions :is(button,a):focus-visible { outline:2px solid var(--fgColor-accent); outline-offset:2px; }
  .aniflow-help .reader details.example-source { margin:16px 0 28px; }
  .aniflow-help .reader details.example-source > summary { color:var(--fgColor-accent); font-size:14px; }
  .aniflow-help .reader .help-step-picker { display:grid; gap:8px; margin:16px 0 24px; color:var(--fgColor-muted); font-size:14px; }
  .aniflow-help .reader .help-step-picker select { max-width:100%; min-height:44px; padding:8px; border:1px solid var(--borderColor-default); border-radius:8px; background:var(--bgColor-default); color:var(--fgColor-default); font:inherit; }
  @media (min-width:1240px) { .aniflow-help .reader .help-step-picker { display:none; } }
  @media (max-width:1239px) { .aniflow-help #toc { display:none; } }
  @media (max-width:599px) {
    .aniflow-local .bar { display:grid; grid-template-columns:auto minmax(0,1fr); gap:2px 12px; padding-top:5px; padding-bottom:5px; }
    .aniflow-local .bar > nav { grid-column:1 / -1; justify-content:space-between; gap:8px; }
    .aniflow-local .bar nav select { max-width:110px; }
    .aniflow-local .bar .name { font-size:12px; }
    .aniflow-local .aniflow-brand { margin-bottom:20px; }
    .aniflow-help .aniflow-brand { margin-bottom:10px; }
    .aniflow-local .mermaid-diagram .diagram-tools { position:static; flex-wrap:wrap; justify-content:flex-end; width:100%; gap:4px; margin-bottom:12px; }
    .aniflow-local .mermaid-diagram .diagram-tools .diagram-play { flex:1 0 100%; border:0; margin:0; padding-right:0; }
    .aniflow-local .mermaid-diagram .diagram-play select { flex:1; max-width:none; height:36px; }
    .aniflow-local .mermaid-diagram .diagram-tools button { width:36px; height:36px; }
  }
"""

UI_JS = """
(() => {
  const search = document.getElementById('folder-search');
  if (search) {
    const groups = [...document.querySelectorAll('.directory-group')];
    const lists = groups.map(group => group.querySelector('.directory-list'));
    const rows = lists.flatMap(list => [...list.children]);
    const status = document.getElementById('folder-status');
    const empty = document.getElementById('folder-no-results');
    const sort = document.getElementById('folder-sort');
    const fold = value => value.normalize('NFKD').replace(/\\p{M}/gu, '').toLowerCase();
    const filter = () => {
      const query = fold(search.value.trim());
      let count = 0;
      for (const row of rows) {
        row.hidden = !fold(row.querySelector('a').dataset.name).includes(query);
        if (!row.hidden) count++;
      }
      for (const group of groups) {
        const matches = group.querySelectorAll('li:not([hidden])').length;
        group.hidden = !matches;
        group.querySelector('.group-count').textContent = String(matches);
      }
      empty.hidden = count !== 0;
      status.textContent = query ? count + (count === 1 ? ' match' : ' matches') : '';
    };
    const clear = () => { search.value = ''; filter(); search.focus(); };
    search.addEventListener('input', filter);
    search.addEventListener('keydown', event => { if (event.key === 'Escape') clear(); });
    document.getElementById('folder-clear').addEventListener('click', clear);
    sort.addEventListener('change', () => {
      for (const list of lists) {
        const ordered = [...list.children].sort((a, b) => {
          const name = row => row.querySelector('a').dataset.name;
          return (sort.value === 'modified' && Number(b.dataset.modified) - Number(a.dataset.modified))
            || name(a).localeCompare(name(b), undefined, { numeric:true, sensitivity:'base' });
        });
        list.append(...ordered);
      }
    });
    const dateFormat = new Intl.DateTimeFormat(undefined, { month:'short', day:'numeric', year:'numeric' });
    for (const time of document.querySelectorAll('.file-modified')) {
      const date = new Date(time.dateTime);
      time.textContent = dateFormat.format(date);
      time.title = date.toLocaleString();
    }
  }
  const menu = document.querySelector('.aniflow-menu');
  if (menu) {
    document.addEventListener('click', event => { if (!menu.contains(event.target)) menu.open = false; });
    menu.addEventListener('keydown', event => { if (event.key === 'Escape') { menu.open = false; menu.querySelector('summary').focus(); } });
  }
  const copy = document.querySelector('[data-review="copy"]');
  if (copy) copy.textContent = 'Copy feedback';
  if (location.pathname !== '/help') return;
  document.body.classList.add('aniflow-help');
  const article = document.querySelector('article.markdown-body');
  const attached = new WeakSet();
  function enhance() {
    const demo = article.querySelector('.aniflow-demo');
    const stage = demo?.querySelector('.diagram-stage');
    if (stage?.diagramPlay) {
      let actions = demo.querySelector('.demo-actions');
      if (!actions) {
        actions = document.createElement('div');
        actions.className = 'demo-actions';
        for (const [text, selector, primary] of [
          ['Play demo', '.play-toggle', true], ['Next step', '.play-next', false],
          ['Full screen', 'button[aria-label="Full screen"]', false],
        ]) {
          const button = document.createElement('button');
          button.type = 'button';
          button.textContent = text;
          button.dataset.control = selector;
          if (primary) button.className = 'primary';
          button.addEventListener('click', () => demo.querySelector('.diagram-stage ' + selector)?.click());
          actions.append(button);
        }
        const learn = document.createElement('a');
        learn.href = '#build-your-own';
        learn.textContent = 'Build your own';
        actions.append(learn);
        demo.prepend(actions);
      }
      const controls = stage.querySelector('.diagram-play');
      if (controls) {
        const sync = () => {
          for (const button of actions.querySelectorAll('button')) {
            const native = stage.querySelector(button.dataset.control);
            button.disabled = !native || native.disabled;
          }
          const primary = actions.querySelector('.primary');
          const text = controls.classList.contains('playing') ? 'Pause demo' : 'Play demo';
          if (primary.textContent !== text) primary.textContent = text;
        };
        if (!attached.has(controls)) {
          attached.add(controls);
          new MutationObserver(sync).observe(controls, { attributes:true, subtree:true, attributeFilter:['class', 'disabled'] });
        }
        sync();
      }
    }
    const walkthrough = article.querySelector('#build-your-own');
    if (walkthrough && !article.querySelector('.help-step-picker')) {
      const label = document.createElement('label');
      label.className = 'help-step-picker';
      label.textContent = 'Jump to a step';
      const picker = document.createElement('select');
      const placeholder = new Option('Choose a step', '');
      placeholder.disabled = placeholder.selected = true;
      picker.add(placeholder);
      for (const heading of article.querySelectorAll('h2')) {
        if (!heading.textContent.includes('Step ')) continue;
        picker.add(new Option(heading.textContent.replace(/^#/, '').trim(), heading.id));
      }
      picker.addEventListener('change', () => { location.hash = picker.value; });
      label.append(picker);
      walkthrough.after(label);
    }
  }
  new MutationObserver(enhance).observe(article, { childList:true, subtree:true });
  enhance();
})();
"""
