"""Static CSS and JavaScript for the app pages and the file viewers."""

EXTRA_CSS = """
  .tabs { position:fixed; left:0; right:0; bottom:0; z-index:5; display:grid; grid-auto-flow:column; grid-auto-columns:1fr; padding:6px max(8px, env(safe-area-inset-left)) max(6px, env(safe-area-inset-bottom)) max(8px, env(safe-area-inset-right)); background:color-mix(in srgb, var(--base) 94%, transparent); border-top:1px solid var(--line); backdrop-filter:blur(14px); -webkit-backdrop-filter:blur(14px); }
  .tab { position:relative; display:flex; flex-direction:column; align-items:center; justify-content:center; gap:3px; min-width:0; min-height:52px; padding:4px 2px; border-radius:12px; color:var(--muted); text-decoration:none; font-size:11.5px; font-weight:650; line-height:1; white-space:nowrap; -webkit-tap-highlight-color:transparent; transition:background .15s ease,color .15s ease; }
  .tab:hover { color:var(--ink); }
  .tab-icon { display:grid; place-items:center; width:46px; height:26px; border-radius:13px; font-size:15px; line-height:1; transition:background .15s ease; }
  .tab-count { position:absolute; top:2px; left:calc(50% + 10px); min-width:17px; padding:2px 4px; border-radius:9px; background:var(--line); color:var(--ink); font-size:10px; font-weight:700; line-height:1.1; text-align:center; font-variant-numeric:tabular-nums; }
  .tab-count:empty { display:none; }
  .tab[aria-current] { color:var(--accent); }
  .tab[aria-current] .tab-icon { background:var(--accent); color:var(--accent-ink); }
  .tab:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
  .theme-picker { position:absolute; top:18px; right:0; z-index:6; display:flex; gap:8px; }
  .theme-button { display:grid; place-items:center; width:36px; height:36px; border:1px solid var(--edge); border-radius:12px; background:var(--field); color:var(--muted); font:inherit; font-size:17px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .theme-button:hover, .theme-button[aria-expanded=true] { color:var(--ink); border-color:var(--accent-line); }
  .theme-button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .theme-menu { position:absolute; top:44px; right:0; display:grid; gap:2px; min-width:196px; padding:6px; white-space:nowrap; border:1px solid var(--edge); border-radius:14px; background:var(--panel); box-shadow:0 12px 32px rgba(0,0,0,.3); }
  .theme-menu[hidden] { display:none; }
  .theme-menu button { display:flex; align-items:center; gap:10px; padding:8px 10px; border:0; border-radius:10px; background:none; color:var(--ink); font:inherit; font-size:14px; font-weight:600; text-align:left; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .theme-menu button:hover { background:var(--field); }
  .theme-menu button:focus-visible { outline:2px solid var(--accent); outline-offset:-2px; }
  .theme-menu button[aria-pressed=true] { background:color-mix(in srgb, var(--accent) 16%, var(--panel)); }
  .theme-menu button[aria-pressed=true]::after { content:"✓"; margin-left:auto; color:var(--accent); }
  .push-button[hidden] { display:none; }
  .push-button[aria-pressed=true] { color:var(--accent); border-color:var(--accent-line); }
  .push-button[aria-pressed=true] path:first-child { fill:currentColor; }
  .push-button:disabled { opacity:.6; cursor:progress; }
  .push-button .push-slash { display:none; }
  .push-button[data-state=blocked] .push-slash { display:inline; }
  .swatch { position:relative; flex:0 0 22px; height:22px; border:1px solid; border-radius:50%; }
  .swatch::after { content:""; position:absolute; inset:6px; border-radius:50%; background:currentColor; }
  .swatch.auto { border-color:#8a9590; background:linear-gradient(135deg, #f3f5f4 50%, #111820 50%); color:#0f7b56; }
  @media (min-width:600px) { .theme-picker { top:37px; } }
  @media (min-width:900px) {
    body { padding-left:96px; }
    .wrap { padding-bottom:48px; }
    .tabs { top:0; right:auto; width:96px; grid-auto-flow:row; grid-auto-columns:auto; grid-auto-rows:min-content; align-content:start; gap:10px; padding:28px 8px; border-top:0; border-right:1px solid var(--line); }
    .tab { min-height:64px; font-size:12px; gap:6px; }
    .tab-icon { width:56px; height:32px; border-radius:16px; font-size:17px; }
    .tab-count { top:0; left:calc(50% + 14px); }
    .tab:hover .tab-icon { background:var(--field); }
    .tab[aria-current]:hover .tab-icon { background:var(--accent); }
  }
  .shelf-actions { display:flex; align-items:center; gap:10px; }
  .wipe { padding:6px 10px; border:1px solid color-mix(in srgb, var(--danger) 25%, var(--base)); border-radius:9px; background:color-mix(in srgb, var(--danger) 8%, var(--base)); color:var(--danger); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .wipe:hover { border-color:color-mix(in srgb, var(--danger) 50%, var(--base)); background:color-mix(in srgb, var(--danger) 14%, var(--base)); }
  .wipe:focus-visible { outline:2px solid var(--danger); outline-offset:2px; }
  .tile-wrap { position:relative; display:grid; min-width:0; }
  .tile-delete, .file-delete { position:absolute; top:5px; right:5px; display:grid; place-items:center; width:26px; height:26px; border:1px solid color-mix(in srgb, var(--danger) 35%, transparent); border-radius:8px; background:color-mix(in srgb, var(--base) 72%, transparent); color:var(--danger); font:inherit; font-size:12px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .tile-delete:focus-visible, .file-delete:focus-visible { outline:2px solid var(--danger); outline-offset:1px; }
  .annotate { padding:6px 10px; border:1px solid color-mix(in srgb, var(--accent) 35%, var(--base)); border-radius:9px; background:color-mix(in srgb, var(--accent) 10%, var(--base)); color:var(--accent); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .annotate:hover { border-color:color-mix(in srgb, var(--accent) 60%, var(--base)); background:color-mix(in srgb, var(--accent) 16%, var(--base)); }
  .annotate:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .annotate[hidden] { display:none; }
  .annotator { position:fixed; inset:0; z-index:20; display:flex; flex-direction:column; background:var(--base); padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .annotator-host { flex:1; min-height:0; }
  .annotator-host mjsui-annotation-editor { display:block; width:100%; height:100%; }
  .annotator-status { margin:0; padding:2px 12px; color:var(--danger); font-size:11.5px; text-align:center; }
  .annotator-status:empty { display:none; }
  .annotator-credit { margin:0; padding:3px 0; color:var(--faint); font-size:10.5px; line-height:1.4; text-align:center; }
  .annotator-credit a { color:var(--soft); text-decoration:underline; text-underline-offset:2px; }
  .file-row { position:relative; display:flex; }
  .file-row .file { flex:1; padding-right:80px; }
  .file-row.has-tools .file { padding-right:144px; }
  .file-tools { position:absolute; top:50%; right:10px; transform:translateY(-50%); display:flex; gap:6px; }
  .file-tools .file-delete { position:static; }
  .file-annotate, .file-expiry, .file-share { display:grid; place-items:center; width:26px; height:26px; border:1px solid color-mix(in srgb, var(--accent) 35%, transparent); border-radius:8px; background:color-mix(in srgb, var(--base) 72%, transparent); color:var(--accent); font:inherit; font-size:12px; line-height:1; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .file-annotate:focus-visible, .file-expiry:focus-visible, .file-share:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
  .file-share[hidden] { display:none; }
  .file-qr { display:none; }
  @media (min-width:900px) {
    .file-qr { display:grid; place-items:center; width:26px; height:26px; border:1px solid color-mix(in srgb, var(--accent) 35%, transparent); border-radius:8px; background:color-mix(in srgb, var(--base) 72%, transparent); color:var(--accent); font:inherit; font-size:12px; line-height:1; cursor:pointer; }
    .file-qr:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
    .file-row .file { padding-right:112px; }
    .file-row.has-tools .file { padding-right:176px; }
  }
  .file-expiry { border-color:color-mix(in srgb, var(--warn) 30%, transparent); color:color-mix(in srgb, var(--warn) 70%, var(--muted)); }
  .file-expiry.set, .expiry-button.set { border-color:color-mix(in srgb, var(--warn) 60%, transparent); color:var(--warn); }
  .expires-left { color:var(--warn); }
  .expires-left[hidden] { display:none; }
  .expiry-button { padding:6px 10px; border:1px solid color-mix(in srgb, var(--warn) 25%, var(--base)); border-radius:9px; background:color-mix(in srgb, var(--warn) 8%, var(--base)); color:color-mix(in srgb, var(--warn) 70%, var(--muted)); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .expiry-button:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .tile-expiry { position:absolute; top:5px; left:5px; padding:4px 7px; border-radius:8px; background:color-mix(in srgb, var(--base) 78%, transparent); color:var(--warn); font-size:11px; font-weight:650; line-height:1; pointer-events:none; }
  .expiry-menu { position:fixed; z-index:40; display:grid; gap:8px; padding:10px 12px; border:1px solid var(--edge); border-radius:12px; background:var(--base); box-shadow:0 12px 32px rgba(0,0,0,.35); color:var(--muted); font-size:12px; }
  .expiry-menu[hidden] { display:none; }
  .expiry-menu div { display:flex; flex-wrap:wrap; gap:6px; }
  .expiry-menu button { padding:7px 10px; border:1px solid var(--edge); border-radius:10px; background:var(--field); color:var(--muted); font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .expiry-menu button[aria-pressed=true] { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
  .expiry-menu button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .viewer-tools { display:flex; align-items:center; gap:8px; }
  .share { padding:6px 10px; border:1px solid var(--line); border-radius:9px; background:var(--panel); color:var(--ink); font:inherit; font-size:11px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .share:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .share[hidden] { display:none; }
  .wrap.wide { width:min(100% - 36px, 1180px); }
  .gallery { display:grid; grid-template-columns:repeat(auto-fill, minmax(140px, 1fr)); gap:12px 10px; }
  .tile { display:grid; gap:6px; min-width:0; color:var(--muted); text-decoration:none; font-size:11px; -webkit-tap-highlight-color:transparent; }
  .tile img { display:block; width:100%; aspect-ratio:9/16; object-fit:cover; object-position:top; border-radius:12px; border:1px solid var(--edge); background:var(--field); transition:transform .15s ease,border-color .15s ease; }
  .tile:hover img { border-color:var(--accent-line); }
  .tile:active img { transform:scale(.97); }
  .tile:focus-visible { outline:none; } .tile:focus-visible img { outline:3px solid var(--accent); outline-offset:2px; }
  .tile span { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; padding:0 2px; }
  body.viewing { overflow:hidden; }
  .viewer { position:fixed; inset:0; z-index:10; display:grid; grid-template-rows:auto minmax(0, 1fr) auto; background:color-mix(in srgb, var(--base) 97%, transparent); padding:env(safe-area-inset-top) 0 env(safe-area-inset-bottom); }
  .viewer[hidden] { display:none; }
  .viewer-bar { display:flex; justify-content:space-between; align-items:center; padding:12px 16px; }
  .counter { color:var(--soft); font-size:13px; font-variant-numeric:tabular-nums; }
  .close, .nav { display:grid; place-items:center; width:42px; height:42px; border:1px solid var(--line); border-radius:12px; background:var(--panel); color:var(--ink); font:inherit; font-size:17px; cursor:pointer; }
  .close:focus-visible, .nav:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .nav { position:absolute; top:50%; z-index:1; transform:translateY(-50%); font-size:28px; }
  .prev { left:16px; } .next { right:16px; }
  .viewer.single .nav { display:none; }
  .stage { position:relative; min-height:0; overflow:hidden; touch-action:pinch-zoom; user-select:none; -webkit-user-select:none; }
  .stage img { position:absolute; inset:0; margin:auto; max-width:calc(100% - 24px); max-height:100%; border-radius:14px; transition:transform .2s ease; -webkit-user-drag:none; }
  .caption { display:grid; gap:4px; padding:12px 16px 18px; text-align:center; }
  .caption strong { font-size:14px; font-weight:650; overflow-wrap:anywhere; }
  .caption small { color:var(--muted); font-size:12px; }
  @media (max-width:599px) { .gallery { grid-template-columns:repeat(auto-fill, minmax(96px, 1fr)); gap:10px 8px; } .nav { display:none; } }
"""


SHARE_JS = """
window.shareiCanShareFiles = (() => {
  try {
    const probe = new File([""], "sharei.png", { type: "image/png" });
    return navigator.canShare({ files: [probe] });
  } catch (error) {
    return false;
  }
})();
window.shareiShare = async (url, name) => {
  try {
    if (window.shareiCanShareFiles) {
      const response = await fetch(url);
      if (!response.ok) throw new Error("HTTP " + response.status);
      const blob = await response.blob();
      const type = blob.type || "application/octet-stream";
      await navigator.share({ files: [new File([blob], name, { type })] });
      return;
    }
    if (typeof navigator.share === "function") {
      await navigator.share({ url: new URL(url, location.href).href });
      return;
    }
    const link = document.createElement("a");
    link.href = url;
    link.download = name;
    link.click();
  } catch (error) {
    if (error && error.name === "AbortError") return;
    alert("Could not share: " + (error && error.message ? error.message : error));
  }
};
if (typeof navigator.share === "function") {
  document.querySelectorAll("[data-share]").forEach((button) => {
    button.hidden = false;
    button.addEventListener("click", (event) => {
      event.preventDefault();
      event.stopPropagation();
      window.shareiShare(button.dataset.share, button.dataset.name || "file");
    });
  });
}
"""


EXPIRY_JS = """
(() => {
  const choices = [["1h", 3600], ["24h", 86400], ["7d", 604800], ["30d", 2592000], ["Never", 0]];
  const left = (when) => {
    const seconds = Number(when) - Date.now() / 1000;
    if (seconds < 60) return "under a minute";
    if (seconds < 3600) return Math.round(seconds / 60) + "m";
    if (seconds < 172800) return Math.round(seconds / 3600) + "h";
    return Math.round(seconds / 86400) + "d";
  };
  function paint() {
    document.querySelectorAll("[data-expiry]").forEach((button) => {
      const when = button.dataset.expires;
      button.classList.toggle("set", !!when);
      button.textContent = when && !("compact" in button.dataset) ? "⏱ " + left(when) : (button.dataset.label || "⏱");
      button.title = when ? "Expires in " + left(when) : "Set an expiry";
    });
    document.querySelectorAll("[data-expires-left]").forEach((label) => {
      const when = label.dataset.expiresLeft;
      label.hidden = !when;
      if (when) label.textContent = (label.dataset.prefix || "") + left(when);
    });
  }
  window.shareiExpiryPaint = paint;

  const menu = document.createElement("div");
  menu.className = "expiry-menu";
  menu.hidden = true;
  menu.setAttribute("role", "dialog");
  menu.setAttribute("aria-label", "Delete after");
  menu.innerHTML = '<span>Delete after</span><div></div>';
  const row = menu.querySelector("div");
  let owner = null;
  for (const [label, seconds] of choices) {
    const choice = document.createElement("button");
    choice.type = "button";
    choice.textContent = label;
    choice.dataset.seconds = seconds;
    choice.addEventListener("click", () => apply(seconds));
    row.append(choice);
  }
  document.body.append(menu);
  const previousBusy = window.liveBusy;
  window.liveBusy = () => !menu.hidden || (previousBusy ? previousBusy() : false);

  function close() { menu.hidden = true; owner = null; }
  function open(button) {
    owner = button;
    row.querySelectorAll("button").forEach((choice) => choice.setAttribute("aria-pressed", String(choice.dataset.seconds === "0" && !button.dataset.expires)));
    menu.hidden = false;
    const box = button.getBoundingClientRect(), width = menu.offsetWidth, height = menu.offsetHeight;
    menu.style.left = Math.max(8, Math.min(box.right - width, innerWidth - width - 8)) + "px";
    menu.style.top = (box.bottom + height + 12 > innerHeight ? Math.max(8, box.top - height - 6) : box.bottom + 6) + "px";
    row.querySelector("button").focus({ preventScroll: true });
  }
  async function apply(seconds) {
    const button = owner;
    close();
    if (!button) return;
    const query = "?target=" + encodeURIComponent(button.dataset.target) + "&key=" + encodeURIComponent(button.dataset.key) + "&seconds=" + seconds;
    try {
      const response = await fetch("/expiry" + query, { method: "POST" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      location.reload();
    } catch (error) {
      alert("Could not set the expiry: " + error.message);
    }
  }
  document.addEventListener("click", (event) => {
    const button = event.target.closest("[data-expiry]");
    if (button) {
      event.preventDefault();
      event.stopPropagation();
      if (owner === button) close(); else open(button);
    } else if (!menu.contains(event.target)) close();
  }, true);
  document.addEventListener("keydown", (event) => {
    if (event.key === "Escape" && !menu.hidden) { event.stopPropagation(); close(); }
  }, true);
  addEventListener("resize", close);
  paint();
  setInterval(paint, 60000);
})();
"""


CAROUSEL_JS = """
(() => {
  const shots = JSON.parse(document.getElementById("shots").textContent);
  const $ = (id) => document.getElementById(id);
  const viewer = $("viewer"), stage = $("stage"), photo = $("photo");
  let current = -1, loadToken = 0;
  window.liveBusy = () => !viewer.hidden;
  if (shots.length < 2) viewer.classList.add("single");

  function show(index) {
    current = (index + shots.length) % shots.length;
    const shot = shots[current];
    const token = ++loadToken;
    photo.src = shot.thumb || shot.url;
    photo.alt = shot.name;
    const full = new Image();
    full.onload = () => { if (token === loadToken) photo.src = shot.url; };
    full.src = shot.url;
    const annotate = $("annotate-shot");
    annotate.hidden = !/\\.(png|jpe?g|webp)$/i.test(shot.key);
    annotate.dataset.key = shot.key;
    annotate.dataset.url = shot.url;
    annotate.dataset.name = shot.name;
    const expiry = $("expiry-shot");
    expiry.dataset.key = shot.key;
    expiry.dataset.expires = shot.expires || "";
    if (window.shareiExpiryPaint) window.shareiExpiryPaint();
    $("counter").textContent = `${current + 1} / ${shots.length}`;
    $("caption-name").textContent = shot.name;
    $("caption-meta").textContent = `${shot.project} · ${shot.date}`;
    for (const offset of [-1, 1]) {
      const neighbour = shots[(current + offset + shots.length) % shots.length];
      new Image().src = neighbour.thumb || neighbour.url;
    }
  }
  function open(index, push) {
    show(index);
    viewer.hidden = false;
    document.body.classList.add("viewing");
    history[push ? "pushState" : "replaceState"]({ viewer: true }, "", "#shot=" + shots[current].key);
    $("close").focus({ preventScroll: true });
  }
  function step(offset) {
    show(current + offset);
    history.replaceState({ viewer: true }, "", "#shot=" + shots[current].key);
  }
  function hide() {
    viewer.hidden = true;
    document.body.classList.remove("viewing");
    const tile = document.querySelector(`.tile[data-index="${current}"]`);
    current = -1;
    if (tile) tile.focus({ preventScroll: true });
  }
  function close() {
    if (history.state && history.state.viewer && history.length > 1) return history.back();
    hide();
    history.replaceState(null, "", location.pathname);
  }
  function fromHash() {
    const index = shots.findIndex((shot) => location.hash === "#shot=" + shot.key);
    if (index >= 0) open(index, false); else if (current >= 0) hide();
  }

  document.querySelectorAll(".tile").forEach((tile) => tile.addEventListener("click", (event) => {
    if (event.metaKey || event.ctrlKey || event.shiftKey || event.altKey || event.button) return;
    event.preventDefault();
    open(Number(tile.dataset.index), true);
  }));
  $("close").addEventListener("click", close);
  $("share-shot").hidden = typeof navigator.share !== "function";
  $("share-shot").addEventListener("click", () => {
    if (current >= 0) window.shareiShare(shots[current].url, shots[current].name);
  });
  $("prev").addEventListener("click", () => step(-1));
  $("next").addEventListener("click", () => step(1));
  document.addEventListener("sharei:annotated", (event) => {
    const index = shots.findIndex((shot) => shot.key === event.detail.key);
    if (index < 0) return;
    shots[index].url = event.detail.url;
    shots[index].thumb = event.detail.url.replace("/shot/", "/thumb/");
    const tile = document.querySelector(`.tile[data-index="${index}"] img`);
    if (tile) tile.src = shots[index].thumb;
    if (current === index) show(current);
  });
  document.addEventListener("keydown", (event) => {
    if (viewer.hidden || document.querySelector(".annotator")) return;
    if (event.key === "ArrowLeft") step(-1);
    else if (event.key === "ArrowRight") step(1);
    else if (event.key === "Escape") close();
  });
  window.addEventListener("popstate", fromHash);

  async function remove(url, question) {
    if (!confirm(question)) return;
    try {
      const response = await fetch(url, { method: "POST" });
      if (!response.ok) throw new Error("HTTP " + response.status);
      location.reload();
    } catch (error) {
      alert("Could not delete: " + error.message);
    }
  }
  document.querySelectorAll(".tile-delete").forEach((button) => button.addEventListener("click", (event) => {
    event.preventDefault();
    event.stopPropagation();
    remove("/shots/delete/" + button.dataset.key, "Delete this screenshot?");
  }));
  $("delete-shot").addEventListener("click", () => {
    if (current >= 0) remove("/shots/delete/" + shots[current].key, "Delete this screenshot?");
  });
  const wipe = $("delete-all");
  if (wipe) wipe.addEventListener("click", () => remove("/shots/delete-all", `Delete ALL ${shots.length} screenshots? This cannot be undone.`));
  document.querySelectorAll("[data-wipe-project]").forEach((button) => button.addEventListener("click", () => {
    const project = button.dataset.wipeProject;
    remove("/shots/delete-all?project=" + encodeURIComponent(project), `Delete ${button.dataset.count === "1" ? "the screenshot" : "all " + button.dataset.count + " screenshots"} in ${project}? This cannot be undone.`);
  }));

  let startX = null, startY = 0, deltaX = 0;
  stage.addEventListener("pointerdown", (event) => {
    if (event.pointerType === "mouse" && event.button) return;
    startX = event.clientX; startY = event.clientY; deltaX = 0;
    photo.style.transition = "none";
  });
  stage.addEventListener("pointermove", (event) => {
    if (startX === null) return;
    deltaX = event.clientX - startX;
    if (Math.abs(deltaX) > Math.abs(event.clientY - startY)) photo.style.transform = `translateX(${deltaX}px)`;
  });
  const release = (event) => {
    if (startX === null) return;
    const travel = { x: deltaX, y: event.clientY - startY };
    startX = null;
    photo.style.transition = "";
    photo.style.transform = "";
    if (Math.abs(travel.x) > 50) return step(travel.x < 0 ? 1 : -1);
    // A tap pages like a book: left third back, right third forward, middle closes.
    if (event.type !== "pointerup" || Math.abs(travel.x) >= 6 || Math.abs(travel.y) >= 10) return;
    const box = stage.getBoundingClientRect();
    const side = (event.clientX - box.left) / box.width;
    if (side < 1 / 3) step(-1);
    else if (side > 2 / 3) step(1);
    else close();
  };
  stage.addEventListener("pointerup", release);
  stage.addEventListener("pointercancel", release);
  stage.addEventListener("pointerleave", release);

  fromHash();
})();
"""


QR_CSS = """
  .qr-dialog { width:min(100% - 32px, 360px); padding:18px; border:1px solid var(--line, var(--borderColor-default)); border-radius:20px; background:var(--panel, var(--bgColor-default)); color:var(--ink, var(--fgColor-default)); font-family:system-ui,-apple-system,sans-serif; }
  .qr-dialog::backdrop { background:color-mix(in srgb, var(--base, var(--bgColor-default)) 40%, transparent); backdrop-filter:blur(3px); }
  .qr-dialog canvas { display:block; width:100%; height:auto; border-radius:12px; image-rendering:pixelated; }
  .qr-dialog p { margin:12px 0; color:var(--muted, var(--fgColor-muted)); font-size:12px; overflow-wrap:anywhere; }
  .qr-dialog .qr-actions { display:grid; grid-template-columns:repeat(3, 1fr); gap:8px; }
  .qr-dialog .qr-actions > * { display:grid; place-items:center; min-height:40px; border:1px solid var(--edge, var(--borderColor-default)); border-radius:12px; background:var(--field, var(--bgColor-muted)); color:var(--accent, var(--fgColor-accent)); font:inherit; font-size:13px; font-weight:650; text-decoration:none; cursor:pointer; }
  .qr-dialog .qr-actions > *:focus-visible { outline:3px solid var(--accent, var(--fgColor-accent)); outline-offset:2px; }
"""


QR_JS = """
(() => {
  const nonce = document.currentScript && document.currentScript.nonce;
  const loopback = /^(localhost|127(\\.\\d+){3}|\\[::1\\])$/.test(location.hostname);
  let library;
  let dialog;

  function target(raw) {
    const url = new URL(raw || location.href, location.href);
    if (url.origin === location.origin && loopback && window.shareiPublicUrl) {
      const base = new URL(window.shareiPublicUrl);
      return base.origin + base.pathname.replace(/\\/$/, '') + url.pathname + url.search + url.hash;
    }
    return url.href;
  }

  function load() {
    if (window.qrcode) return Promise.resolve();
    library = library || new Promise((resolve, reject) => {
      const script = document.createElement('script');
      script.src = '/vendor/qrcode.js';
      if (nonce) script.nonce = nonce;
      script.onload = resolve;
      script.onerror = () => { library = null; reject(new Error('could not load the QR library')); };
      document.head.append(script);
    });
    return library;
  }

  function draw(text) {
    qrcode.stringToBytes = qrcode.stringToBytesFuncs['UTF-8'];
    const code = qrcode(0, 'M');
    code.addData(text);
    code.make();
    const count = code.getModuleCount(), quiet = 4;
    const scale = Math.max(4, Math.floor(320 / (count + quiet * 2)));
    const canvas = document.createElement('canvas');
    canvas.width = canvas.height = (count + quiet * 2) * scale;
    const context = canvas.getContext('2d');
    // Scanners need dark modules on a light ground whatever the theme, so these two stay fixed.
    context.fillStyle = '#fff';
    context.fillRect(0, 0, canvas.width, canvas.height);
    context.fillStyle = '#000';
    for (let row = 0; row < count; row++) {
      for (let column = 0; column < count; column++) {
        if (code.isDark(row, column)) context.fillRect((column + quiet) * scale, (row + quiet) * scale, scale, scale);
      }
    }
    canvas.setAttribute('role', 'img');
    canvas.setAttribute('aria-label', 'QR code for ' + text);
    return canvas;
  }

  function open(text) {
    if (!dialog) {
      dialog = document.createElement('dialog');
      dialog.className = 'qr-dialog';
      dialog.innerHTML = '<div class="qr-code"></div><p></p><div class="qr-actions"><a target="_blank" rel="noopener noreferrer">Open</a><button type="button" data-copy>Copy</button><button type="button" data-close>Close</button></div>';
      dialog.addEventListener('click', (event) => {
        if (event.target === dialog || event.target.closest('[data-close]')) dialog.close();
      });
      dialog.querySelector('[data-copy]').addEventListener('click', async (event) => {
        try {
          await navigator.clipboard.writeText(dialog.querySelector('p').textContent);
          event.target.textContent = 'Copied';
        } catch (error) {
          event.target.textContent = 'Blocked';
        }
      });
      document.body.append(dialog);
      const previousBusy = window.liveBusy;
      window.liveBusy = () => dialog.open || (previousBusy ? previousBusy() : false);
    }
    const holder = dialog.querySelector('.qr-code');
    try {
      holder.replaceChildren(draw(text));
    } catch (error) {
      holder.replaceChildren();
      text = 'Too long for a QR code: ' + text.slice(0, 120) + '…';
    }
    dialog.querySelector('p').textContent = text;
    const link = dialog.querySelector('a');
    link.hidden = !/^https?:/i.test(text);
    link.href = link.hidden ? '#' : text;
    dialog.querySelector('[data-copy]').textContent = 'Copy';
    dialog.showModal();
  }

  window.shareiQr = (raw) => load().then(() => open(target(raw)), (error) => alert(error.message));

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-qr]');
    if (!button) return;
    event.preventDefault();
    window.shareiQr(button.dataset.qr);
  });
})();
"""


CODE_CSS = """
  .page.code-page { width:min(100%, 1280px); }
  .code { position:relative; display:grid; grid-template-columns:auto minmax(0, 1fr); border:1px solid var(--borderColor-default); border-radius:6px; background:var(--bgColor-muted); font:12px/20px ui-monospace,SFMono-Regular,"SF Mono",Menlo,Consolas,monospace; overflow:hidden; }
  .gutter { padding:8px 0; border-right:1px solid var(--borderColor-default); text-align:right; user-select:none; -webkit-user-select:none; }
  .gutter a { display:block; padding:0 10px 0 14px; color:var(--fgColor-muted); text-decoration:none; }
  .gutter a:hover { color:var(--fgColor-default); }
  .gutter a:target { color:var(--fgColor-default); font-weight:600; }
  .scroll { position:relative; overflow-x:auto; }
  .code pre { position:relative; margin:0; padding:8px 14px; overflow:visible; background:none; }
  .code code { display:block; padding:0; background:none; font:inherit; white-space:pre; tab-size:4; }
  .code code.hljs { padding:0; background:none; overflow:visible; }
  .line-mark { position:absolute; left:0; right:0; height:20px; background:var(--bgColor-attention-muted); pointer-events:none; }
  .line-mark[hidden] { display:none; }
"""


CODE_JS = """
(() => {
  const code = document.getElementById('code');
  const mark = document.getElementById('line-mark');
  function markLine() {
    const match = /^#L(\\d+)$/.exec(location.hash);
    mark.hidden = !match;
    if (match) mark.style.top = (8 + (Number(match[1]) - 1) * 20) + 'px';
  }
  addEventListener('hashchange', markLine);
  markLine();
  if (!window.hljs || !('lang' in code.dataset)) return;
  const text = code.textContent, language = code.dataset.lang;
  const result = language && hljs.getLanguage(language)
    ? hljs.highlight(text, { language, ignoreIllegals: true })
    : hljs.highlightAuto(text);
  code.innerHTML = result.value;
  code.classList.add('hljs');
})();
"""


PLAY_CSS = """
  .page.play-page { display:grid; place-items:center; width:min(100%, 1280px); min-height:calc(100vh - 120px); }
  .play-page video { display:block; width:100%; max-height:calc(100vh - 120px); border-radius:6px; background:#000; }
  .play-page audio { display:block; width:min(100%, 640px); }
"""


PDF_CSS = """
  .page.pdf-page { display:grid; gap:14px; justify-items:center; width:min(100%, 1000px); }
  .pdf-page canvas { display:block; width:100%; height:auto; border-radius:4px; box-shadow:0 0 0 1px var(--borderColor-default); }
  .pdf-page .pdf-status { color:var(--fgColor-muted); font-size:14px; }
"""


PDF_JS = """
import * as pdfjs from '/vendor/pdf.min.mjs';

const main = document.querySelector('.pdf-page');
const status = main.querySelector('.pdf-status');
pdfjs.GlobalWorkerOptions.workerSrc = '/vendor/pdf.worker.min.mjs';

async function draw(page, canvas) {
  const ratio = window.devicePixelRatio || 1;
  const base = page.getViewport({ scale: 1 });
  const scale = Math.min(main.clientWidth / base.width, 3) * ratio;
  const viewport = page.getViewport({ scale });
  canvas.width = Math.floor(viewport.width);
  canvas.height = Math.floor(viewport.height);
  await page.render({ canvas, viewport }).promise;
}

try {
  const pdf = await pdfjs.getDocument({ url: main.dataset.url }).promise;
  status.textContent = pdf.numPages === 1 ? '1 page' : `${pdf.numPages} pages`;
  const observer = new IntersectionObserver((entries) => {
    for (const entry of entries) {
      if (!entry.isIntersecting) continue;
      observer.unobserve(entry.target);
      pdf.getPage(Number(entry.target.dataset.page)).then((page) => draw(page, entry.target));
    }
  }, { rootMargin: '600px 0px' });
  for (let number = 1; number <= pdf.numPages; number++) {
    const page = number === 1 ? await pdf.getPage(1) : null;
    const canvas = document.createElement('canvas');
    canvas.dataset.page = number;
    canvas.setAttribute('aria-label', `Page ${number}`);
    if (page) {
      const view = page.getViewport({ scale: 1 });
      canvas.width = view.width;
      canvas.height = view.height;
    } else {
      const first = main.querySelector('canvas');
      canvas.width = first.width;
      canvas.height = first.height;
    }
    main.append(canvas);
    observer.observe(canvas);
  }
} catch (error) {
  status.textContent = 'This PDF could not be shown. Download it instead.';
  console.error(error);
}
"""


CLIP_CSS = """
  .clip-card { display:grid; gap:12px; padding:16px; background:var(--panel); border:1px solid var(--line); border-radius:20px; }
  .clip-meta { display:flex; justify-content:space-between; gap:12px; color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .clip-meta strong { color:var(--soft); font-weight:600; }
  .clip-ttl { display:flex; flex-wrap:wrap; align-items:center; gap:6px; color:var(--muted); font-size:12px; }
  .clip-ttl>span { margin-right:2px; }
  .clip-ttl button { padding:7px 10px; border:1px solid var(--edge); border-radius:10px; background:var(--field); color:var(--muted); font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .clip-ttl button[aria-pressed=true] { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
  .clip-ttl button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  textarea { width:100%; min-height:36vh; padding:14px; resize:vertical; border:1px solid var(--edge); border-radius:14px; background:var(--field); color:var(--ink); font:16px/1.5 ui-monospace,SFMono-Regular,Menlo,monospace; }
  textarea:focus-visible { outline:3px solid var(--accent); outline-offset:1px; }
  .clip-actions { display:grid; grid-template-columns:1fr 1fr; gap:8px; }
  .clip-actions button { min-height:52px; border:1px solid var(--edge); border-radius:14px; background:var(--field); color:var(--ink); font:inherit; font-size:15px; font-weight:650; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .clip-actions button.primary { background:var(--accent); border-color:var(--accent); color:var(--accent-ink); }
  .clip-actions button.wide, .clip-actions a.wide { grid-column:span 2; }
  .clip-actions a { display:grid; place-items:center; min-height:44px; border:1px dashed var(--edge); border-radius:14px; color:var(--accent); font-size:14px; font-weight:650; text-decoration:none; -webkit-tap-highlight-color:transparent; }
  .clip-actions a:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .clip-actions button:active { transform:scale(.985); }
  .clip-actions button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .clip-status { min-height:20px; margin:0; color:var(--muted); font-size:13px; }
  .clip-status[data-tone=ok] { color:var(--accent); }
  .clip-status[data-tone=warn] { color:var(--warn); }
  .clip-note { margin:0; color:var(--faint); font-size:12px; line-height:1.6; }
  .clip-note code { color:var(--soft); overflow-wrap:anywhere; }
  .clip-link { display:flex; align-items:center; gap:10px; padding:10px 12px; border:1px solid var(--accent-line); border-radius:14px; background:color-mix(in srgb, var(--accent) 8%, var(--field)); }
  .clip-link[hidden] { display:none; }
  .clip-link a { flex:1; min-width:0; overflow:hidden; color:var(--accent); font-size:14px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
  .clip-entry pre a { color:var(--accent); }
  .clip-history { margin-top:18px; }
  .clip-history[hidden] { display:none; }
  .clip-history ol { display:grid; gap:8px; margin:0; padding:0; list-style:none; }
  .clip-entry { display:grid; grid-template-columns:1fr auto; align-items:center; gap:4px 10px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:14px; }
  .clip-entry pre { grid-column:1/-1; margin:0; overflow:hidden; color:var(--ink); font:13px/1.45 ui-monospace,SFMono-Regular,Menlo,monospace; white-space:pre-wrap; overflow-wrap:anywhere; display:-webkit-box; -webkit-line-clamp:3; -webkit-box-orient:vertical; }
  .clip-entry small { color:var(--muted); font-size:11px; font-variant-numeric:tabular-nums; }
  .clip-entry .clip-ttl { justify-content:flex-end; }
"""


CLIP_JS = r"""
const field = document.getElementById('clip-text');
const status = document.getElementById('clip-status');
const meta = document.getElementById('clip-updated');
const expiry = document.getElementById('clip-expiry');
const count = document.getElementById('clip-count');
const reload = document.getElementById('reload');
let latest = JSON.parse(document.getElementById('clip-state').textContent);
let known = latest.version;
let dirty = false;

function setStatus(message, tone) {
  status.textContent = message;
  if (tone) status.dataset.tone = tone; else delete status.dataset.tone;
}

function expiryLabel(state) {
  if (!state.updated || !state.text) return 'in memory';
  if (!state.ttl) return 'never clears';
  const left = Math.max(0, Math.round(state.updated + state.ttl - Date.now() / 1000));
  return left > 0 ? 'clears in ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0') : 'clearing…';
}

function describe(state) {
  count.textContent = state.chars + (state.chars === 1 ? ' char' : ' chars');
  meta.textContent = state.updated ? new Date(state.updated * 1000).toLocaleTimeString() + ' · ' + state.chars + ' chars' : 'Nothing shared yet';
  expiry.textContent = expiryLabel(state);
}

function markButtons() {
  for (const button of document.querySelectorAll('[data-ttl]')) {
    button.setAttribute('aria-pressed', String(Number(button.dataset.ttl) === latest.ttl));
  }
}

describe(latest);
markButtons();
if (latest.text) field.value = latest.text;

field.addEventListener('input', () => {
  dirty = true;
  describe(Object.assign({}, latest, { chars: field.value.length }));
});

setInterval(() => {
  describe(Object.assign({}, latest, { chars: dirty ? field.value.length : latest.chars }));
  for (const [index, age] of historyList.querySelectorAll('small').entries()) {
    if (latest.history[index]) age.textContent = entryAge(latest.history[index]);
  }
}, 1000);

async function call(url, body) {
  const response = await fetch(url, { method: 'POST', body: body, cache: 'no-store' });
  if (!response.ok) throw new Error('HTTP ' + response.status);
  return response.json();
}

const linkBar = document.getElementById('clip-link');
const URL_PATTERN = /https?:\/\/[^\s<>"']+/g;

function singleUrl(text) {
  const trimmed = text.trim();
  return /^https?:\/\/\S+$/i.test(trimmed) ? trimmed : null;
}

function linkify(text) {
  const fragment = document.createDocumentFragment();
  let last = 0;
  for (const match of text.matchAll(URL_PATTERN)) {
    const url = match[0].replace(/[.,;:!?)\]]+$/, '');
    fragment.append(text.slice(last, match.index));
    const link = document.createElement('a');
    link.href = url;
    link.target = '_blank';
    link.rel = 'noopener noreferrer';
    link.textContent = url;
    fragment.append(link);
    last = match.index + url.length;
  }
  fragment.append(text.slice(last));
  return fragment;
}

function showLink(state) {
  const url = singleUrl(state.text);
  linkBar.hidden = !url;
  if (!url) return;
  const link = linkBar.querySelector('a');
  link.href = url;
  link.textContent = url;
  const qr = linkBar.querySelector('[data-qr]');
  if (qr) qr.dataset.qr = url;
}

const historyBox = document.getElementById('clip-history');
const historyList = historyBox.querySelector('ol');

function entryAge(entry) {
  const label = new Date(entry.updated * 1000).toLocaleTimeString() + ' · ' + entry.chars + (entry.chars === 1 ? ' char' : ' chars');
  if (!entry.expires_at) return label;
  const left = Math.max(0, Math.round(entry.expires_at - Date.now() / 1000));
  return label + ' · clears in ' + Math.floor(left / 60) + ':' + String(left % 60).padStart(2, '0');
}

function renderHistory(state) {
  historyBox.hidden = !state.history.length;
  historyList.replaceChildren(...state.history.map((entry) => {
    const row = document.createElement('li');
    row.className = 'clip-entry';
    const text = document.createElement('pre');
    text.append(linkify(entry.text));
    const age = document.createElement('small');
    age.textContent = entryAge(entry);
    const tools = document.createElement('span');
    tools.className = 'clip-ttl';
    const url = singleUrl(entry.text);
    if (url) {
      const qr = document.createElement('button');
      qr.type = 'button';
      qr.textContent = 'QR';
      qr.dataset.qr = url;
      tools.append(qr);
    }
    for (const [label, action] of [['Copy', 'copy'], ['Use', 'restore'], ['✕', 'delete']]) {
      const button = document.createElement('button');
      button.type = 'button';
      button.textContent = label;
      button.dataset.historyAction = action;
      button.dataset.id = entry.id;
      if (action === 'delete') button.setAttribute('aria-label', 'Delete this entry');
      tools.append(button);
    }
    row.append(text, age, tools);
    return row;
  }));
}

function adopt(state) {
  latest = state;
  known = state.version;
  describe(state);
  markButtons();
  renderHistory(state);
  showLink(state);
}

historyList.addEventListener('click', async (event) => {
  const button = event.target.closest('[data-history-action]');
  if (!button) return;
  const entry = latest.history.find((item) => String(item.id) === button.dataset.id);
  if (!entry) return;
  if (button.dataset.historyAction === 'copy') {
    try {
      await navigator.clipboard.writeText(entry.text);
      setStatus('Copied to this device.', 'ok');
    } catch (error) {
      setStatus('This browser blocks clipboard writes here. Use it, then Copy.', 'warn');
    }
    return;
  }
  try {
    adopt(await call('/clip/history/' + button.dataset.historyAction + '?id=' + entry.id, ''));
    if (button.dataset.historyAction === 'restore') {
      field.value = latest.text; dirty = false; reload.hidden = true;
      setStatus('Shared with every device.', 'ok');
    }
  } catch (error) {
    setStatus('Could not update the history: ' + error.message, 'warn');
  }
});

document.getElementById('history-clear').addEventListener('click', async () => {
  if (!confirm('Forget every older clipboard entry?')) return;
  try {
    adopt(await call('/clip/history/clear', ''));
  } catch (error) {
    setStatus('Could not clear the history: ' + error.message, 'warn');
  }
});

renderHistory(latest);
showLink(latest);

document.getElementById('copy').addEventListener('click', async () => {
  const text = field.value;
  if (!text) { setStatus('Nothing to copy.', 'warn'); return; }
  try {
    await navigator.clipboard.writeText(text);
    setStatus('Copied to this device.', 'ok');
  } catch (error) {
    field.focus(); field.select();
    setStatus(document.execCommand('copy') ? 'Copied to this device.' : 'Select the text and copy it manually.', 'warn');
  }
});

document.getElementById('send').addEventListener('click', async () => {
  try {
    adopt(await call('/clip', field.value));
    dirty = false;
    reload.hidden = true;
    setStatus('Shared with every device.', 'ok');
  } catch (error) {
    setStatus('Could not share: ' + error.message, 'warn');
  }
});

document.getElementById('paste').addEventListener('click', async () => {
  try {
    const text = await navigator.clipboard.readText();
    field.value = text; dirty = true;
    describe(Object.assign({}, latest, { chars: text.length }));
    setStatus('Pasted. Hit Send to share it.', 'ok');
  } catch (error) {
    field.focus();
    setStatus('This browser blocks clipboard reads. Long-press the box and choose Paste.', 'warn');
  }
});

document.getElementById('clear').addEventListener('click', async () => {
  try {
    adopt(await call('/clip/clear', ''));
    field.value = ''; dirty = false; reload.hidden = true;
    setStatus('Clipboard cleared.', 'ok');
  } catch (error) {
    setStatus('Could not clear: ' + error.message, 'warn');
  }
});

reload.addEventListener('click', () => {
  field.value = latest.text; dirty = false; reload.hidden = true;
  describe(latest);
  setStatus('Loaded the newer text.', 'ok');
});

for (const button of document.querySelectorAll('[data-ttl]')) {
  button.addEventListener('click', async () => {
    try {
      adopt(await call('/clip/ttl?seconds=' + button.dataset.ttl, ''));
      setStatus(Number(button.dataset.ttl) === 0
        ? 'This text now stays until someone clears it.'
        : 'Will clear after ' + button.textContent.trim() + '.', 'ok');
    } catch (error) {
      setStatus('Could not change the timer: ' + error.message, 'warn');
    }
  });
}

setInterval(async () => {
  try {
    const response = await fetch('/clip/state', { cache: 'no-store' });
    const state = await response.json();
    if (state.version === known) return;
    const textChanged = state.text !== latest.text;
    latest = state;
    known = state.version;
    renderHistory(state);
    showLink(state);
    if (!textChanged) {
      describe(state);
      markButtons();
      return;
    }
    if (dirty) {
      reload.hidden = false;
      setStatus('Another device shared new text. Load it or Send to overwrite.', 'warn');
      return;
    }
    field.value = state.text;
    describe(state);
    markButtons();
    setStatus('Updated from another device.', 'ok');
  } catch (error) { /* polling is best effort */ }
}, 2000);
"""


DROP_CSS = """
  .drop-zone { padding:10px; background:var(--panel); border:2px dashed var(--dash); border-radius:20px; transition:border-color .15s ease,background .15s ease; }
  .drop-zone.over { background:color-mix(in srgb, var(--accent) 8%, var(--panel)); border-color:var(--accent); }
  .drop-button { display:grid; place-items:center; gap:7px; width:100%; min-height:168px; padding:20px; border:0; border-radius:14px; background:transparent; color:var(--ink); font:inherit; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .drop-button:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .drop-icon { color:var(--accent); font-size:34px; line-height:1; }
  .drop-button strong { font-size:17px; }
  .drop-button small { color:var(--muted); font-size:12px; text-align:center; line-height:1.5; }
  .drop-zone.compact { padding:4px; border-radius:16px; }
  .drop-zone.compact .drop-button { display:flex; justify-content:center; gap:10px; min-height:56px; padding:8px 14px; }
  .drop-zone.compact .drop-icon { font-size:22px; }
  .drop-zone.compact .drop-button strong { font-size:15px; }
  .drop-zone.compact .drop-button small { display:none; }
  .upload-queue { display:grid; gap:8px; margin:12px 0 0; padding:0; list-style:none; }
  .upload-row { display:grid; grid-template-columns:1fr auto; align-items:center; gap:6px 12px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:12px; font-size:13px; }
  .upload-name { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .upload-note { color:var(--muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .upload-bar { grid-column:1/-1; height:4px; overflow:hidden; border-radius:2px; background:var(--chip); }
  .upload-bar i { display:block; width:0; height:100%; background:var(--accent); transition:width .15s ease; }
  .upload-row[data-state=fail] .upload-note, .upload-row[data-state=fail] .upload-name { color:var(--danger); }
  .file-list { display:grid; gap:8px; margin-top:13px; }
  .file { display:flex; align-items:center; gap:12px; padding:10px 12px; background:var(--panel); border:1px solid var(--line); border-radius:14px; color:inherit; text-decoration:none; -webkit-tap-highlight-color:transparent; transition:transform .15s ease,border-color .15s ease; }
  .file:active { transform:scale(.985); border-color:var(--accent-line); }
  .file:focus-visible { outline:3px solid var(--accent); outline-offset:2px; }
  .file-thumb { display:grid; place-items:center; flex:0 0 46px; height:46px; overflow:hidden; border-radius:10px; background:var(--chip); color:var(--accent); font-size:20px; }
  .file-thumb img, .file-thumb video { width:100%; height:100%; object-fit:cover; }
  .file-thumb video { position:absolute; inset:0; pointer-events:none; }
  .play-mark { position:relative; display:grid; place-items:center; width:24px; height:24px; padding-left:2px; border-radius:50%; background:rgba(0,0,0,.55); color:#fff; font-size:10px; }
  .file-thumb { position:relative; }
  .file-thumb .pdf-mark { font-size:12px; font-weight:800; letter-spacing:.04em; }
  .file-thumb:has(iframe) { background:#fff; }
  .file-thumb iframe { position:absolute; left:0; top:0; width:184px; height:184px; border:0; transform:scale(.25); transform-origin:0 0; pointer-events:none; }
  .file-copy { display:grid; flex:1; gap:3px; min-width:0; }
  .file-copy strong { overflow:hidden; font-size:14px; font-weight:650; text-overflow:ellipsis; white-space:nowrap; }
  .file-copy small { color:var(--muted); font-size:11px; }
  .file-action { color:var(--accent); font-size:12px; font-weight:650; }
  .project-pick { display:flex; align-items:center; gap:8px; margin:0 2px 12px; color:var(--muted); font-size:13px; }
  .project-pick select { flex:1; min-height:40px; padding:0 10px; border:1px solid var(--line); border-radius:10px; background:var(--panel); color:var(--ink); font:inherit; font-size:14px; }
  .project-pick select:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
  .drop-group + .drop-group { margin-top:14px; }
  .drop-head { display:flex; align-items:center; justify-content:space-between; gap:12px; margin:0 4px 8px; }
  .drop-group h2 { margin:0; color:var(--soft); font-size:13px; font-weight:650; }
"""


DROP_JS = """
const input = document.getElementById('file-input');
const zone = document.getElementById('zone');
const queue = document.getElementById('queue');
const picker = document.getElementById('project');
const remembered = localStorage.getItem('sharei.project');
if (remembered && [...picker.options].some((option) => option.value === remembered)) picker.value = remembered;
picker.addEventListener('change', () => {
  if (picker.value === '__new') {
    const name = (prompt('New project name (letters, digits, . _ -)') || '').trim();
    if (/^[A-Za-z0-9][A-Za-z0-9._-]{0,63}$/.test(name)) {
      if (![...picker.options].some((option) => option.value === name)) {
        picker.add(new Option(name, name), picker.options.length - 1);
      }
      picker.value = name;
    } else {
      if (name) alert('Use letters, digits, dot, dash or underscore.');
      picker.value = localStorage.getItem('sharei.project') || picker.options[0].value;
      return;
    }
  }
  localStorage.setItem('sharei.project', picker.value);
});
let pending = 0;
window.liveBusy = () => pending > 0;

function uploadOne(file) {
  const row = document.createElement('li');
  row.className = 'upload-row';
  row.innerHTML = '<span class="upload-name"></span><span class="upload-note">0%</span><span class="upload-bar"><i></i></span>';
  row.querySelector('.upload-name').textContent = file.name;
  queue.append(row);
  const bar = row.querySelector('.upload-bar i');
  const note = row.querySelector('.upload-note');
  const request = new XMLHttpRequest();
  request.open('POST', '/upload?project=' + encodeURIComponent(picker.value) + '&name=' + encodeURIComponent(file.name));
  request.upload.onprogress = (event) => {
    if (!event.lengthComputable) return;
    const percent = Math.round(event.loaded / event.total * 100);
    bar.style.width = percent + '%';
    note.textContent = percent + '%';
  };
  request.onload = () => {
    if (request.status >= 200 && request.status < 300) {
      row.dataset.state = 'ok';
      bar.style.width = '100%';
      note.textContent = 'Saved';
    } else {
      row.dataset.state = 'fail';
      note.textContent = request.status === 413 ? 'Too large' : 'Failed';
    }
  };
  request.onerror = () => {
    row.dataset.state = 'fail';
    note.textContent = 'Network error';
  };
  request.onloadend = () => {
    pending -= 1;
    if (pending === 0) setTimeout(() => location.reload(), 900);
  };
  pending += 1;
  request.send(file);
}

function handleFiles(files) {
  for (const file of files) uploadOne(file);
}

input.addEventListener('change', () => handleFiles(input.files));
zone.addEventListener('click', (event) => {
  if (event.target.closest('button')) return;
  input.click();
});
document.getElementById('pick').addEventListener('click', () => input.click());
for (const name of ['dragenter', 'dragover']) {
  zone.addEventListener(name, (event) => { event.preventDefault(); zone.classList.add('over'); });
}
for (const name of ['dragleave', 'dragend']) {
  zone.addEventListener(name, () => zone.classList.remove('over'));
}
zone.addEventListener('drop', (event) => {
  event.preventDefault();
  zone.classList.remove('over');
  if (event.dataTransfer) handleFiles(event.dataTransfer.files);
});
function pastedName(extension) {
  const now = new Date();
  const pad = (value) => String(value).padStart(2, '0');
  return `pasted-${now.getFullYear()}-${pad(now.getMonth() + 1)}-${pad(now.getDate())}-${pad(now.getHours())}${pad(now.getMinutes())}${pad(now.getSeconds())}.${extension}`;
}
document.addEventListener('paste', (event) => {
  const data = event.clipboardData;
  if (!data || event.target.closest('input, textarea, select, [contenteditable]')) return;
  // A copied screenshot arrives with a generic name such as image.png.
  const files = [...data.files].map((file) => /^image\\.\\w+$/i.test(file.name) && file.type.startsWith('image/')
    ? new File([file], pastedName(file.type.split('/')[1].replace('jpeg', 'jpg')), { type: file.type })
    : file);
  const text = data.getData('text/plain');
  if (!files.length && !text.trim()) return;
  event.preventDefault();
  handleFiles(files.length ? files : [new File([text], pastedName('txt'), { type: 'text/plain' })]);
});

async function remove(url, question) {
  if (!confirm(question)) return;
  try {
    const response = await fetch(url, { method: 'POST' });
    if (!response.ok) throw new Error('HTTP ' + response.status);
    location.reload();
  } catch (error) {
    alert('Could not delete: ' + error.message);
  }
}

for (const button of document.querySelectorAll('.file-delete')) {
  button.addEventListener('click', () => remove('/poub/delete/' + button.dataset.url, 'Delete this file?'));
}

for (const button of document.querySelectorAll('[data-wipe-project]')) {
  const project = button.dataset.wipeProject;
  button.addEventListener('click', () => remove('/poub/delete-all?project=' + encodeURIComponent(project), `Delete ${button.dataset.count === '1' ? 'the file' : 'all ' + button.dataset.count + ' files'} in ${project}? This cannot be undone.`));
}

const wipe = document.getElementById('delete-all');
if (wipe) wipe.addEventListener('click', () => remove('/poub/delete-all', 'Delete ALL dropped files in every project? This cannot be undone.'));
"""


FOLDER_ICON = (
    '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" '
    'd="M3 6.5A2.5 2.5 0 0 1 5.5 4h3.6c.6 0 1.2.2 1.6.7L12 6h6.5A2.5 2.5 0 0 1 21 8.5v9a2.5 2.5 0 0 1-2.5 '
    '2.5h-13A2.5 2.5 0 0 1 3 17.5Z"/></svg>'
)

SORT_ICON = (
    '<svg viewBox="0 0 24 24" width="15" height="15" aria-hidden="true" fill="none" '
    'stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">'
    '<path d="M4 6h9M4 12h6M4 18h3M17 5v14m0 0-3-3m3 3 3-3"/></svg>'
)

NOTE_ICON = (
    '<svg viewBox="0 0 24 24" width="22" height="22" aria-hidden="true"><path fill="currentColor" '
    'fill-rule="evenodd" d="M7 2.5h7.2c.5 0 1 .2 1.4.6l3.3 3.3c.4.4.6.9.6 1.4v11.7a2 2 0 0 1-2 2H7a2 '
    '2 0 0 1-2-2v-15a2 2 0 0 1 2-2ZM8.5 11h7v1.5h-7Zm0 3.5h7V16h-7Zm0-7h3.5V9H8.5Z"/>'
    '<path fill="currentColor" opacity=".45" d="M14.5 2.6v3.4a1.5 1.5 0 0 0 1.5 1.5h3.4Z"/></svg>'
)


NOTES_CSS = """
  .notes-crumbs { display:flex; flex-wrap:wrap; gap:2px 6px; margin:0 0 8px; padding-right:48px; color:var(--muted); font-size:13px; }
  .notes-crumbs a { color:inherit; text-decoration:none; }
  .notes-crumbs a:hover { color:var(--accent); }
  .notes-crumbs span { opacity:.6; }
  .note-filter { display:block; width:100%; margin:0 0 4px; padding:11px 14px; border:1px solid var(--edge); border-radius:12px; background:var(--field); color:var(--ink); font:inherit; font-size:15px; }
  .note-filter:focus-visible { outline:2px solid var(--accent); outline-offset:1px; }
  .note-filter::placeholder { color:var(--faint); }
  .file .folder-mark { color:var(--accent); }
  .file-thumb img.note-icon { width:64%; height:64%; object-fit:contain; }
  h1 .note-icon { width:.9em; height:.9em; margin-right:.25em; object-fit:contain; vertical-align:-.08em; }
  .note-results[hidden], .note-tree[hidden] { display:none; }
  .note-sort { display:inline-flex; align-items:center; gap:5px; padding:5px 9px; border:1px solid var(--edge); border-radius:9px; background:var(--field); color:var(--soft); font:inherit; font-size:12px; font-weight:600; cursor:pointer; -webkit-tap-highlight-color:transparent; }
  .note-sort:hover { color:var(--accent); border-color:color-mix(in srgb, var(--accent) 40%, var(--edge)); }
  .note-sort:focus-visible { outline:2px solid var(--accent); outline-offset:2px; }
  .note-sort[hidden] { display:none; }
  .note-results .file[hidden] { display:none; }
"""


NOTES_JS = """
(() => {
  const input = document.getElementById('note-filter');
  const tree = document.getElementById('note-tree');
  const results = document.getElementById('note-results');
  const count = document.getElementById('note-count');
  if (!input) return;
  const rows = [...results.querySelectorAll('.file')];
  const total = count.textContent;
  function filter() {
    const words = input.value.trim().toLowerCase().split(/\\s+/).filter(Boolean);
    tree.hidden = words.length > 0;
    results.hidden = !words.length;
    let shown = 0;
    for (const row of rows) {
      const hit = words.every((word) => row.dataset.path.includes(word));
      row.hidden = !hit;
      if (hit) shown++;
    }
    count.textContent = words.length ? shown + ' found' : total;
  }
  input.addEventListener('input', filter);
  filter();
  const sort = document.getElementById('note-sort');
  const label = sort.querySelector('span');
  let mode = 'date';
  try { if (localStorage.getItem('sharei-notes-sort') === 'name') mode = 'name'; } catch (_) {}
  function order(list) {
    const items = [...list.children].filter((row) => row.classList.contains('file'));
    items.sort((a, b) =>
      ('folder' in b.dataset) - ('folder' in a.dataset) ||
      (mode === 'date' ? Number(b.dataset.time) - Number(a.dataset.time) : 0) ||
      a.dataset.name.localeCompare(b.dataset.name, undefined, { numeric: true }));
    list.append(...items);
  }
  function apply() {
    label.textContent = mode === 'date' ? 'Newest' : 'A to Z';
    sort.setAttribute('aria-label', mode === 'date' ? 'Sorted newest first, sort by name' : 'Sorted by name, sort newest first');
    order(tree);
    order(results);
  }
  sort.addEventListener('click', () => {
    mode = mode === 'date' ? 'name' : 'date';
    try { localStorage.setItem('sharei-notes-sort', mode); } catch (_) {}
    apply();
  });
  sort.hidden = false;
  apply();
})();
"""


ANNOTATE_JS = """
(() => {
  // marker.js 3 is linkware: the markerjs.com credit line that open() renders under the editor is the
  // attribution its licence requires while the editor is in use. Keep it visible, do not hide it with CSS.
  const SOURCES = ['/vendor/markerjs3.js', '/vendor/markerjs-ui.js'];
  const MIME = { '.png': 'image/png', '.jpg': 'image/jpeg', '.jpeg': 'image/jpeg', '.webp': 'image/webp' };
  const previousBusy = window.liveBusy || (() => false);
  let annotating = false, loading = null;
  // Auto-reload has to stay quiet while the editor is open, or a save elsewhere reloads the page under it.
  window.liveBusy = () => annotating || previousBusy();

  function load() {
    if (!loading) {
      loading = SOURCES.reduce((chain, src) => chain.then(() => new Promise((resolve, reject) => {
        if (document.querySelector(`script[src="${src}"]`)) return resolve();
        const script = document.createElement('script');
        script.src = src;
        script.onload = resolve;
        script.onerror = () => reject(new Error('could not load ' + src));
        document.head.append(script);
      })), Promise.resolve());
    }
    // A failed load must be retried on the next tap, so drop the memoised promise.
    return loading.catch((error) => { loading = null; throw error; });
  }

  // Annotations read as red everywhere. The library already defaults most tools to #ff0000, so this only
  // catches the ones that do not: text, the yellow highlighter, the black cover box, the callout outline.
  // Text on a red bubble (callout, captioned frame) stays white, red on red would be unreadable.
  const RED = '#ff0000';

  // The library defaults text to 1rem, which on a phone screenshot rasterized at natural size is too small to
  // read once the image is scaled down to fit a chat bubble. Size the label off the image instead: 4% of the
  // short side, never under 1.5rem, so a 1080px capture reads the same as a 4000px desktop grab. Units stay rem
  // because the library's size panel writes rem back.
  function readableFontSize(image) {
    const short = Math.min(image.naturalWidth, image.naturalHeight) || 0;
    const pixels = Math.max(24, Math.round(short * 0.04));
    return { value: Math.round(pixels / 16 * 10) / 10, units: 'rem', step: 0.1 };
  }

  function tint(editor, image) {
    if (!editor) return;
    const onRed = String(editor.fillColor || '').toLowerCase() === RED;
    const paint = (property, value) => {
      try { editor[property] = value; } catch (error) { /* immutable on this marker type */ }
    };
    for (const property of ['strokeColor', 'fillColor', 'highlightColor']) {
      const current = String(editor[property] || '').toLowerCase();
      if (current && current !== 'transparent') paint(property, RED);
    }
    if (!onRed && editor.color && String(editor.color).toLowerCase() !== 'transparent') paint('color', RED);
    if ('fontSize' in editor && image) paint('fontSize', readableFontSize(image));
  }

  // On a phone the library folds every tool into one "All markers" dropdown and keeps a single square icon
  // beside it. Mirror the Text tool next to that square so labelling something needs no dropdown; the rest
  // stays folded. The clone only forwards clicks to the library's own hidden button, which owns the state.
  function addTextShortcut(editor) {
    const root = editor.shadowRoot;
    const group = root?.querySelector('[aria-label="Text"].join');
    const folded = root?.querySelector('[aria-label="All markers"]');
    const button = group?.querySelector('.btn');
    if (!group || !folded || !button || !folded.parentElement) return;
    const shortcut = group.cloneNode(true);
    shortcut.querySelector('details')?.remove();
    const mirror = shortcut.querySelector('.btn');
    if (!mirror) return;
    shortcut.addEventListener('click', (event) => {
      event.preventDefault();
      button.click();
      mirror.className = button.className;
    });
    folded.parentElement.insertBefore(shortcut, folded);
  }

  function mimeOf(key) {
    const dot = key.lastIndexOf('.');
    return dot < 0 ? undefined : MIME[key.slice(dot).toLowerCase()];
  }

  function pathOf(value) {
    if (!value) return '';
    try { return new URL(value, location.href).pathname.replace(/^\\/(shot|thumb|poub)\\//, '/'); }
    catch (error) { return ''; }
  }

  // Rewrite every element still pointing at the previous pixels: the immutable ?v= URL the old image used is
  // cached forever, so new markup has to carry the new one.
  function refresh(key, url, stamps) {
    const wanted = pathOf(key);
    for (const image of document.images) {
      if (pathOf(image.getAttribute('src')) === wanted) image.src = url;
    }
    for (const link of document.querySelectorAll('a[href]')) {
      if (pathOf(link.getAttribute('href')) === wanted) link.href = url;
    }
    for (const button of document.querySelectorAll('[data-annotate]')) {
      if (pathOf(button.dataset.key) === wanted) button.dataset.url = url;
    }
    for (const script of document.querySelectorAll('script[data-kind]')) {
      if (stamps && stamps[script.dataset.kind]) script.dataset.stamp = stamps[script.dataset.kind];
    }
    document.dispatchEvent(new CustomEvent('sharei:annotated', { detail: { key: key, url: url } }));
  }

  async function save(editor, overlay, button, dataUrl) {
    const note = overlay.querySelector('.annotator-status');
    note.textContent = 'Saving…';
    try {
      const query = '?target=' + encodeURIComponent(button.dataset.target) + '&key=' + encodeURIComponent(button.dataset.key);
      const response = await fetch('/annotate' + query, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ data: dataUrl }),
      });
      const payload = await response.json().catch(() => ({}));
      if (!response.ok) throw new Error(payload.error || 'HTTP ' + response.status);
      editor.remove();
      overlay.remove();
      annotating = false;
      refresh(payload.key || button.dataset.key, payload.url, payload.stamps);
    } catch (error) {
      note.textContent = 'Could not save: ' + error.message;
    }
  }

  async function annotate(button) {
    const mime = mimeOf(button.dataset.key || '');
    if (!mime || annotating) return;
    annotating = true;
    const overlay = document.createElement('div');
    overlay.className = 'annotator';
    overlay.setAttribute('role', 'dialog');
    overlay.setAttribute('aria-modal', 'true');
    overlay.setAttribute('aria-label', 'Annotate ' + (button.dataset.name || 'image'));
    overlay.innerHTML = '<div class="annotator-host"></div><p class="annotator-status" role="status"></p>';
    document.body.append(overlay);
    const close = () => { overlay.remove(); annotating = false; };
    try {
      await load();
      const image = new Image();
      image.src = button.dataset.url;
      await image.decode();
      const editor = new window.markerjsUI.AnnotationEditor();
      editor.theme = document.documentElement.dataset.mode === 'dark' ? 'dark' : 'light';
      editor.targetImage = image;
      // Natural size keeps an overwrite from downscaling the shot to whatever the phone screen showed.
      editor.settings.rendererSettings.naturalSize = true;
      editor.settings.rendererSettings.imageType = mime;
      if (mime !== 'image/png') editor.settings.rendererSettings.imageQuality = 0.92;
      editor.addEventListener('editorclose', close);
      editor.addEventListener('editorsave', (event) => save(editor, overlay, button, event.detail.dataUrl));
      overlay.querySelector('.annotator-host').append(editor);
      // The UI creates a marker the moment a tool is picked, so wrapping createMarker colours every new
      // marker before it is drawn. Doing it on markercreate instead would flash the library default first.
      const area = editor.markerArea;
      if (area) {
        const create = area.createMarker.bind(area);
        area.createMarker = (type) => {
          const created = create(type);
          tint(created, image);
          return created;
        };
        // A text marker opens its inline editor but never takes focus, so the first keystrokes go nowhere
        // until you tap the box a second time. Open it and focus it inside the same pointer gesture (mobile
        // browsers refuse a keyboard otherwise) with the placeholder preselected, so typing replaces it.
        area.addEventListener('markercreate', (event) => {
          const created = event.detail && event.detail.markerEditor;
          if (!created || typeof created.showEditor !== 'function') return;
          // markercreate fires just before the library opens the inline editor, so focus on the next
          // microtask: the textarea is attached by then and the pointer gesture is still the activation.
          Promise.resolve().then(() => {
            const field = created.textBlockEditor;
            if (!field) return;
            field.focus();
            field.textEditor?.select();
          });
        });
      }
      addTextShortcut(editor);
      editor.shadowRoot?.querySelector('button')?.focus({ preventScroll: true });
    } catch (error) {
      close();
      alert('Could not open the annotator: ' + error.message);
    }
  }

  document.addEventListener('click', (event) => {
    const button = event.target.closest('[data-annotate]');
    if (!button) return;
    event.preventDefault();
    event.stopPropagation();
    annotate(button);
  });
})();
"""


LIVE_JS = """
(() => {
  const script = document.currentScript;
  const kind = script.dataset.kind;
  setInterval(async () => {
    if (document.hidden || (window.liveBusy && window.liveBusy())) return;
    try {
      const response = await fetch('/state', { cache: 'no-store' });
      // Read the stamp every tick: a save updates it so the page keeps the state it already shows.
      if (response.ok && (await response.json())[kind] !== script.dataset.stamp) location.reload();
    } catch (error) {}
  }, 4000);
})();
"""


SW_JS = """
self.addEventListener('push', (event) => {
  let data = {};
  try { data = event.data ? event.data.json() : {}; } catch (error) { data = {}; }
  event.waitUntil(self.registration.showNotification(data.title || 'sharei', {
    body: data.body || '',
    tag: data.tag || 'sharei',
    renotify: true,
    icon: '/icon-192.png',
    data: { url: data.url || '/' },
  }));
});

self.addEventListener('notificationclick', (event) => {
  event.notification.close();
  const url = new URL(event.notification.data.url, self.location.origin);
  if (url.origin !== self.location.origin) return;
  event.waitUntil((async () => {
    for (const client of await clients.matchAll({ type: 'window', includeUncontrolled: true })) {
      if (new URL(client.url).pathname === url.pathname && 'focus' in client) return client.focus();
    }
    return clients.openWindow(url.href);
  })());
});

self.addEventListener('pushsubscriptionchange', (event) => {
  const options = event.oldSubscription && event.oldSubscription.options;
  if (!options) return;
  event.waitUntil(self.registration.pushManager.subscribe(options).then((subscription) =>
    fetch('/push/subscribe', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(subscription.toJSON()),
    })));
});
"""


PUSH_JS = """
(() => {
  const item = document.querySelector('.theme-picker [data-push]');
  if (!item || !('serviceWorker' in navigator) || !('PushManager' in window) || !window.isSecureContext) return;
  item.hidden = false;
  const BLOCKED = 'Notifications blocked in the browser settings';

  function paint(on, note) {
    item.setAttribute('aria-pressed', String(on));
    item.dataset.state = note === BLOCKED ? 'blocked' : '';
    const label = note || (on ? 'Notifications on' : 'Turn on notifications');
    item.title = label;
    item.setAttribute('aria-label', label);
  }
  async function current() {
    const registration = await navigator.serviceWorker.getRegistration('/');
    return registration ? registration.pushManager.getSubscription() : null;
  }
  async function post(path, body) {
    const response = await fetch(path, { method: 'POST', headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body) });
    if (!response.ok) throw new Error(`${path}: ${response.status}`);
  }
  function bytes(text) {
    const raw = atob(text.replace(/-/g, '+').replace(/_/g, '/') + '='.repeat((4 - text.length % 4) % 4));
    return Uint8Array.from(raw, (char) => char.charCodeAt(0));
  }

  current().then((subscription) => paint(Boolean(subscription))).catch(() => paint(false));
  if (Notification.permission === 'denied') paint(false, BLOCKED);

  item.addEventListener('click', async () => {
    item.disabled = true;
    try {
      const existing = await current();
      if (existing) {
        await post('/push/unsubscribe', { endpoint: existing.endpoint }).catch(() => {});
        await existing.unsubscribe();
        paint(false);
        return;
      }
      if (await Notification.requestPermission() !== 'granted') {
        paint(false, BLOCKED);
        return;
      }
      const { key } = await (await fetch('/push/key')).json();
      await navigator.serviceWorker.register('/sw.js');
      const registration = await navigator.serviceWorker.ready;
      const subscription = await registration.pushManager.subscribe({ userVisibleOnly: true, applicationServerKey: bytes(key) });
      await post('/push/subscribe', subscription.toJSON());
      paint(true);
    } catch (error) {
      console.error(error);
      paint(false, 'Could not turn notifications on');
    } finally {
      item.disabled = false;
    }
  });
})();
"""


SEARCH_CSS = """
  .search-dialog { --s-ink:var(--ink, var(--fgColor-default)); --s-muted:var(--muted, var(--fgColor-muted)); --s-line:var(--line, var(--borderColor-default)); --s-panel:var(--panel, var(--bgColor-default)); --s-field:var(--field, var(--bgColor-muted)); --s-accent:var(--accent, var(--fgColor-accent));
    position:fixed; inset:min(12vh, 96px) 0 auto; width:min(100% - 20px, 680px); max-width:none; max-height:min(76dvh, 660px); margin:0 auto; padding:0; overflow:hidden; border:1px solid var(--s-line); border-radius:18px; background:var(--s-panel); color:var(--s-ink); font-family:system-ui,-apple-system,sans-serif; font-size:14px; box-shadow:0 24px 64px rgba(0,0,0,.35); }
  .search-dialog[open] { display:flex; flex-direction:column; }
  .search-dialog::backdrop { background:color-mix(in srgb, var(--base, var(--bgColor-default)) 45%, transparent); backdrop-filter:blur(3px); }
  .search-head { display:flex; align-items:center; gap:8px; padding:10px; border-bottom:1px solid var(--s-line); }
  .search-head input { flex:1; min-width:0; height:40px; padding:0 12px; border:1px solid var(--s-line); border-radius:12px; background:var(--s-field); color:var(--s-ink); font:inherit; font-size:16px; outline:none; }
  .search-head input:focus { border-color:var(--s-accent); }
  .search-modes { display:flex; flex:0 0 auto; padding:3px; border:1px solid var(--s-line); border-radius:12px; background:var(--s-field); }
  .search-modes button { padding:6px 10px; border:0; border-radius:9px; background:none; color:var(--s-muted); font:inherit; font-size:13px; font-weight:650; cursor:pointer; }
  .search-modes button[aria-pressed=true] { background:var(--s-accent); color:var(--accent-ink, var(--bgColor-default)); }
  .search-modes button:focus-visible { outline:2px solid var(--s-accent); outline-offset:1px; }
  .search-list:empty { display:none; }
  .search-list { flex:1; min-height:0; overflow-y:auto; overscroll-behavior:contain; padding:6px; }
  .search-row { display:flex; align-items:center; gap:10px; min-height:44px; padding:7px 10px; border-radius:10px; color:inherit; text-decoration:none; }
  .search-row[aria-selected=true] { background:color-mix(in srgb, var(--s-accent) 16%, transparent); }
  .search-kind { display:grid; place-items:center; flex:0 0 26px; height:26px; border-radius:8px; background:var(--s-field); color:var(--s-muted); font-size:13px; }
  .search-kind img { width:18px; height:18px; object-fit:contain; }
  .search-copy { display:grid; gap:2px; flex:1; min-width:0; }
  .search-copy strong, .search-copy small { overflow:hidden; text-overflow:ellipsis; white-space:nowrap; }
  .search-copy strong { font-weight:600; }
  .search-copy small { color:var(--s-muted); font-size:12px; }
  .search-copy b { color:var(--s-accent); font-weight:750; }
  .search-side { flex:0 0 auto; color:var(--s-muted); font-size:12px; font-variant-numeric:tabular-nums; }
  .search-foot { display:flex; align-items:center; justify-content:space-between; gap:12px; padding:8px 14px; border-top:1px solid var(--s-line); color:var(--s-muted); font-size:12px; }
  .search-keys kbd { display:inline-block; min-width:18px; margin:0 2px; padding:1px 5px; border:1px solid var(--s-line); border-radius:5px; background:var(--s-field); font:inherit; font-size:11px; text-align:center; }
  @media (hover:none), (max-width:520px) { .search-keys { display:none; } }
  @media (max-width:520px) { .search-dialog { inset:10px 0 auto; max-height:calc(100dvh - 20px); } }
  .bar nav [data-search] { display:inline-flex; align-items:center; }
  mark.find-hit { padding:0 1px; border-radius:3px; background:color-mix(in srgb, var(--fgColor-accent) 32%, transparent); color:inherit; }
  .find-target { border-radius:6px; box-shadow:0 0 0 6px color-mix(in srgb, var(--fgColor-accent) 10%, transparent); background:color-mix(in srgb, var(--fgColor-accent) 10%, transparent); }
"""


SEARCH_JS = """
(() => {
  // The notes picker: / or Ctrl/Cmd+K anywhere, fuzzy on names or a full-text search on the server.
  const LIMIT = 80;
  const MODE_KEY = 'sharei-search-mode';
  const BOUNDARY = /[\\/\\s_\\-.()\\[\\]]/;
  let dialog, input, list, status, modes;
  let items = null, loading = null, controller = null, timer = 0;
  let rows = [], selected = 0, mode = 'name';
  try { if (localStorage.getItem(MODE_KEY) === 'text') mode = 'text'; } catch (_) {}

  const fold = (text) => text.normalize('NFKD').replace(/[\\u0300-\\u036f]/g, '').toLowerCase();
  // The folded text, and for each of its characters the index of the character it came
  // from in the original. Plain lower-casing that keeps the length needs no map.
  function folding(text) {
    const whole = fold(text);
    if (whole === text.toLowerCase() && whole.length === text.length) return { text: whole, origin: null };
    let out = '';
    const origin = [];
    for (let index = 0; index < text.length;) {
      const character = String.fromCodePoint(text.codePointAt(index));
      const piece = fold(character);
      out += piece;
      for (let count = 0; count < piece.length; count++) origin.push(index);
      index += character.length;
    }
    return { text: out, origin };
  }

  function prepare(item) {
    const slash = item.p.lastIndexOf('/');
    const folder = slash < 0 ? '' : item.p.slice(0, slash);
    let title = item.p.slice(slash + 1);
    if (item.k === 'note') title = title.replace(/\\.(md|markdown)$/i, '');
    const shown = (folder ? folder + '/' : '') + title;
    const folded = folding(shown);
    const nameAt = folded.origin ? folded.origin.indexOf(folder ? folder.length + 1 : 0) : (folder ? folder.length + 1 : 0);
    return { ...item, folder, title, shown, folded: folded.text, origin: folded.origin, nameAt: Math.max(0, nameAt) };
  }

  // One word against the folded path: a substring on a word boundary beats a scattered match,
  // and a match in the name beats one in the folders.
  function matchWord(word, text, from) {
    let best = null;
    for (let at = text.indexOf(word, from); at >= 0; at = text.indexOf(word, at + 1)) {
      const edge = at === 0 || BOUNDARY.test(text[at - 1]);
      const score = word.length * 6 + (edge ? 10 : 0);
      if (!best || score > best.score) best = { score, positions: Array.from(word, (_, index) => at + index) };
      if (edge) break;
    }
    if (best) return best;
    let index = from, position = 0;
    for (; index < text.length && position < word.length; index++) if (text[index] === word[position]) position++;
    if (position < word.length) return null;
    const end = index;
    position = word.length - 1;
    let start = end - 1;
    for (let back = end - 1; back >= from; back--) {
      if (text[back] === word[position] && --position < 0) { start = back; break; }
    }
    const positions = [];
    let score = 0, previous = -2;
    position = 0;
    for (let at = start; at < end && position < word.length; at++) {
      if (text[at] !== word[position]) continue;
      score += 1 + (at === 0 || BOUNDARY.test(text[at - 1]) ? 6 : 0) + (previous === at - 1 ? 4 : 0);
      positions.push(at);
      previous = at;
      position++;
    }
    return { score: score - (end - start - word.length) * 0.5, positions };
  }

  function rank(query) {
    const words = fold(query).split(/\\s+/).filter(Boolean);
    if (!words.length) {
      return items.filter((item) => item.k === 'note')
        .sort((a, b) => b.t - a.t).slice(0, LIMIT).map((item) => ({ item, marks: [] }));
    }
    const found = [];
    for (const item of items) {
      let score = 0;
      const marks = [];
      for (const word of words) {
        const inName = matchWord(word, item.folded, item.nameAt);
        const match = inName || matchWord(word, item.folded, 0);
        if (!match) { score = -1; break; }
        score += match.score + (inName ? 12 : 0);
        marks.push(...match.positions);
      }
      if (score < 0) continue;
      if (item.k === 'note') score += 2;
      found.push({ item, score, marks });
    }
    found.sort((a, b) => b.score - a.score || a.item.shown.length - b.item.shown.length || b.item.t - a.item.t);
    return found.slice(0, LIMIT);
  }

  // Text with the characters starting at the given indexes in <b>, built without innerHTML.
  function marked(text, indexes, offset) {
    const fragment = document.createDocumentFragment();
    let run = '', bold = false;
    const flush = () => {
      if (!run) return;
      if (bold) { const b = document.createElement('b'); b.textContent = run; fragment.append(b); } else fragment.append(run);
      run = '';
    };
    for (let index = 0; index < text.length;) {
      const character = String.fromCodePoint(text.codePointAt(index));
      const hit = indexes.has(index + offset);
      if (hit !== bold) { flush(); bold = hit; }
      run += character;
      index += character.length;
    }
    flush();
    return fragment;
  }

  // Indexes in text where any of the folded words appear.
  function wordMarks(text, words) {
    words = words.filter(Boolean);
    const { text: folded, origin } = folding(text);
    const indexes = new Set();
    for (const word of words) {
      for (let at = folded.indexOf(word); at >= 0; at = folded.indexOf(word, at + word.length)) {
        for (let index = at; index < at + word.length; index++) indexes.add(origin ? origin[index] : index);
      }
    }
    return indexes;
  }

  const thisYear = new Date().getFullYear();
  function when(seconds) {
    if (!seconds) return '';
    const date = new Date(seconds * 1000);
    const options = date.getFullYear() === thisYear ? { month: 'short', day: 'numeric' } : { year: 'numeric', month: 'short' };
    return date.toLocaleDateString(undefined, options);
  }

  function row(href, kind, icon, title, titleMarks, below, belowMarks, side) {
    const link = document.createElement('a');
    link.className = 'search-row';
    link.href = href;
    link.setAttribute('role', 'option');
    link.id = 'search-row-' + rows.length;
    link.tabIndex = -1;
    const thumb = document.createElement('span');
    thumb.className = 'search-kind';
    thumb.setAttribute('aria-hidden', 'true');
    if (icon) {
      const image = document.createElement('img');
      image.src = icon;
      image.alt = '';
      thumb.append(image);
    } else thumb.textContent = kind === 'folder' ? '▸' : kind === 'note' ? '¶' : '▤';
    const copy = document.createElement('span');
    copy.className = 'search-copy';
    const strong = document.createElement('strong');
    strong.append(marked(title, titleMarks, 0));
    copy.append(strong);
    if (below) {
      const small = document.createElement('small');
      small.append(marked(below, belowMarks, 0));
      copy.append(small);
    }
    link.append(thumb, copy);
    if (side) {
      const meta = document.createElement('span');
      meta.className = 'search-side';
      meta.textContent = side;
      link.append(meta);
    }
    link.addEventListener('mousemove', () => select(rows.indexOf(link), false));
    link.addEventListener('click', (event) => {
      if (event.button === 0 && !event.ctrlKey && !event.metaKey && !event.shiftKey) dialog.close();
    });
    rows.push(link);
    return link;
  }

  function show(built, message) {
    list.replaceChildren(...built);
    status.textContent = message;
    select(0, true);
  }

  function select(index, scroll) {
    if (!rows.length) { input.removeAttribute('aria-activedescendant'); return; }
    selected = (index + rows.length) % rows.length;
    rows.forEach((link, at) => link.setAttribute('aria-selected', at === selected ? 'true' : 'false'));
    input.setAttribute('aria-activedescendant', rows[selected].id);
    if (scroll) rows[selected].scrollIntoView({ block: 'nearest' });
  }

  function names() {
    if (!items) {
      status.textContent = 'Loading notes…';
      loading = loading || fetch('/notes-search', { credentials: 'same-origin' })
        .then((response) => { if (!response.ok) throw new Error(response.status); return response.json(); })
        .then((data) => { items = data.items.map(prepare); })
        .catch(() => { loading = null; status.textContent = 'Could not load the notes'; });
      loading.then(() => { if (items && mode === 'name' && dialog.open) names(); });
      return;
    }
    rows = [];
    const found = rank(input.value);
    const built = found.map(({ item, marks }) => {
      const indexes = new Set(marks.map((at) => (item.origin ? item.origin[at] : at)));
      const titleAt = item.folder ? item.folder.length + 1 : 0;
      const titleMarks = new Set([...indexes].filter((at) => at >= titleAt).map((at) => at - titleAt));
      const folderMarks = new Set([...indexes].filter((at) => at < item.folder.length));
      return row(item.h, item.k, item.i, item.title + (item.k === 'folder' ? '/' : ''), titleMarks,
        item.folder, folderMarks, item.k === 'folder' ? 'Folder' : when(item.t));
    });
    const query = input.value.trim();
    show(built, query ? (found.length ? found.length + (found.length === LIMIT ? '+' : '') + ' found' : 'Nothing matches')
      : (found.length ? 'Recent notes' : 'No notes shared'));
  }

  function text() {
    clearTimeout(timer);
    if (controller) controller.abort();
    const query = input.value.trim();
    if (!query) { rows = []; show([], 'Type to search inside the notes'); return; }
    status.textContent = 'Searching…';
    timer = setTimeout(() => {
      controller = new AbortController();
      fetch('/notes-search?q=' + encodeURIComponent(query), { credentials: 'same-origin', signal: controller.signal })
        .then((response) => { if (!response.ok) throw new Error(response.status); return response.json(); })
        .then((data) => {
          if (mode !== 'text' || input.value.trim() !== query) return;
          rows = [];
          const built = [];
          const find = encodeURIComponent(data.terms.join(' '));
          for (const result of data.results) {
            const slash = result.p.lastIndexOf('/');
            const title = result.p.slice(slash + 1).replace(/\\.(md|markdown)$/i, '');
            const folder = slash < 0 ? '' : result.p.slice(0, slash);
            const titleMarks = wordMarks(title, data.terms);
            if (!result.hits.length) {
              built.push(row(result.h, 'note', result.i, title, titleMarks, folder, new Set(), when(result.t)));
              continue;
            }
            for (const hit of result.hits) {
              built.push(row(result.h + '#find=' + hit.n + ':' + find, 'note', result.i, title, titleMarks,
                hit.s, wordMarks(hit.s, data.terms), 'L' + hit.n));
            }
          }
          const notes = data.results.length;
          show(built, notes ? built.length + ' lines in ' + notes + (notes === 1 ? ' note' : ' notes') : 'Nothing matches');
        })
        .catch((error) => { if (error.name !== 'AbortError') status.textContent = 'Search failed'; });
    }, 160);
  }

  function update() { (mode === 'text' ? text : names)(); }

  function setMode(next) {
    mode = next;
    try { localStorage.setItem(MODE_KEY, mode); } catch (_) {}
    modes.forEach((button) => button.setAttribute('aria-pressed', button.dataset.mode === mode ? 'true' : 'false'));
    input.placeholder = mode === 'text' ? 'Search inside notes' : 'Find a note by name';
    update();
  }

  function go(newTab) {
    const link = rows[selected];
    if (!link) return;
    if (newTab) { window.open(link.href, '_blank', 'noopener'); return; }
    dialog.close();
    location.href = link.href;
  }

  function build() {
    dialog = document.createElement('dialog');
    dialog.className = 'search-dialog';
    dialog.setAttribute('aria-label', 'Search notes');
    dialog.innerHTML = '<div class="search-head"><input type="search" autocomplete="off" spellcheck="false" enterkeyhint="go" role="combobox" aria-expanded="true" aria-controls="search-list" aria-label="Search notes">'
      + '<div class="search-modes" role="group" aria-label="Search in"><button type="button" data-mode="name">Names</button><button type="button" data-mode="text">Text</button></div></div>'
      + '<div class="search-list" id="search-list" role="listbox" aria-label="Results"></div>'
      + '<div class="search-foot"><span class="search-status" role="status"></span><span class="search-keys"><kbd>↑</kbd><kbd>↓</kbd> move <kbd>Enter</kbd> open <kbd>Tab</kbd> names/text <kbd>Esc</kbd> close</span></div>';
    input = dialog.querySelector('input');
    list = dialog.querySelector('.search-list');
    status = dialog.querySelector('.search-status');
    modes = [...dialog.querySelectorAll('[data-mode]')];
    modes.forEach((button) => button.addEventListener('click', () => { setMode(button.dataset.mode); input.focus(); }));
    input.addEventListener('input', update);
    input.addEventListener('keydown', (event) => {
      const control = event.ctrlKey && !event.metaKey && !event.altKey;
      if (event.key === 'ArrowDown' || (control && (event.key === 'n' || event.key === 'j'))) { event.preventDefault(); select(selected + 1, true); }
      else if (event.key === 'ArrowUp' || (control && (event.key === 'p' || event.key === 'k'))) { event.preventDefault(); select(selected - 1, true); }
      else if (event.key === 'PageDown') { event.preventDefault(); select(Math.min(selected + 10, rows.length - 1), true); }
      else if (event.key === 'PageUp') { event.preventDefault(); select(Math.max(selected - 10, 0), true); }
      else if (event.key === 'Tab') { event.preventDefault(); setMode(mode === 'text' ? 'name' : 'text'); }
      else if (event.key === 'Enter' && !event.isComposing) { event.preventDefault(); go(event.ctrlKey || event.metaKey || event.shiftKey); }
    });
    dialog.addEventListener('click', (event) => { if (event.target === dialog) dialog.close(); });
    document.body.append(dialog);
    const previousBusy = window.liveBusy;
    window.liveBusy = () => dialog.open || (previousBusy ? previousBusy() : false);
  }

  function open() {
    if (!dialog) build();
    if (dialog.open) { input.focus(); input.select(); return; }
    dialog.showModal();
    setMode(mode);
    input.focus();
    input.select();
  }
  window.shareiSearch = open;

  document.addEventListener('click', (event) => {
    if (event.target.closest && event.target.closest('[data-search]')) { event.preventDefault(); open(); }
  });
  document.addEventListener('keydown', (event) => {
    if (event.defaultPrevented || (dialog && dialog.open)) return;
    const typing = event.target.closest && event.target.closest('input, textarea, select, [contenteditable]:not([contenteditable="false"])');
    const command = (event.ctrlKey || event.metaKey) && !event.altKey && !event.shiftKey;
    if ((command && event.key.toLowerCase() === 'k') || (event.key === '/' && !typing && !event.ctrlKey && !event.metaKey && !event.altKey)) {
      // Another overlay owns the keyboard: a native dialog, or the screenshot viewer and the
      // annotator, which are aria-modal divs.
      if ([...document.querySelectorAll('dialog[open], [aria-modal="true"]')].some((element) => !element.closest('[hidden]') && element.getClientRects().length)) return;
      event.preventDefault();
      open();
    }
  });
})();
"""
