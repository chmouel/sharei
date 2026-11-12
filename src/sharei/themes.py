"""Colour themes: the palettes, their CSS and the script that applies the choice."""

import json
import re
from pathlib import Path

VENDOR = Path(__file__).resolve().parent / "vendor"

THEME_KEYS = (
    "base",
    "panel",
    "field",
    "line",
    "edge",
    "ink",
    "soft",
    "muted",
    "faint",
    "accent",
    "accent-ink",
    "danger",
    "warn",
)


# Values follow THEME_KEYS. "dark" comes first: it is also the no-JavaScript fallback.
THEMES: dict[str, tuple[str, str, tuple[str, ...]]] = {
    "dark": (
        "Dark",
        "dark",
        (
            "#111820",
            "#19232b",
            "#1d2931",
            "#2b3940",
            "#34434a",
            "#eff5f3",
            "#bbc7c8",
            "#9aa9ad",
            "#849399",
            "#a5f2d1",
            "#10251d",
            "#ffb4a8",
            "#ffd68c",
        ),
    ),
    "light": (
        "Light",
        "light",
        (
            "#f3f5f4",
            "#ffffff",
            "#f6f8f7",
            "#e1e6e4",
            "#cdd6d3",
            "#16211d",
            "#3d4a46",
            "#5c6a66",
            "#6c7a76",
            "#0f7b56",
            "#ffffff",
            "#c4372b",
            "#9a6200",
        ),
    ),
    "dracula": (
        "Dracula",
        "dark",
        (
            "#21222c",
            "#282a36",
            "#2e303e",
            "#393b4b",
            "#44475a",
            "#f8f8f2",
            "#d4d4e4",
            "#a3a9cc",
            "#8890bd",
            "#bd93f9",
            "#21222c",
            "#ff6e6e",
            "#f1fa8c",
        ),
    ),
    "tokyo-night": (
        "Tokyo Night",
        "dark",
        (
            "#1a1b26",
            "#1f2335",
            "#24283b",
            "#292e42",
            "#3b4261",
            "#c0caf5",
            "#a9b1d6",
            "#8a93bd",
            "#737aa2",
            "#7aa2f7",
            "#16161e",
            "#f7768e",
            "#e0af68",
        ),
    ),
    "rose-pine": (
        "Rosé Pine",
        "dark",
        (
            "#191724",
            "#1f1d2e",
            "#26233a",
            "#2a273f",
            "#403d52",
            "#e0def4",
            "#c8c5df",
            "#908caa",
            "#7f7b98",
            "#ebbcba",
            "#191724",
            "#eb6f92",
            "#f6c177",
        ),
    ),
    "rose-pine-dawn": (
        "Rosé Pine Dawn",
        "light",
        (
            "#faf4ed",
            "#fffaf3",
            "#f4ede8",
            "#e6dfdb",
            "#cecacd",
            "#575279",
            "#625e83",
            "#797593",
            "#8e89a0",
            "#286983",
            "#fffaf3",
            "#b4637a",
            "#b8741a",
        ),
    ),
}


# The markdown and code readers use GitHub's light or dark palette by mode. These themes
# recolour the page and the syntax on top of it.
READER_THEMES: dict[str, dict[str, str]] = {
    "dracula": {
        "bgColor-default": "#282a36",
        "bgColor-muted": "#21222c",
        "fgColor-default": "#f8f8f2",
        "fgColor-muted": "#a3a9cc",
        "fgColor-accent": "#bd93f9",
        "borderColor-default": "#44475a",
        "borderColor-muted": "#393b4b",
        "color-prettylights-syntax-comment": "#6272a4",
        "color-prettylights-syntax-constant": "#bd93f9",
        "color-prettylights-syntax-entity": "#50fa7b",
        "color-prettylights-syntax-entity-tag": "#ff79c6",
        "color-prettylights-syntax-keyword": "#ff79c6",
        "color-prettylights-syntax-string": "#f1fa8c",
        "color-prettylights-syntax-variable": "#ffb86c",
        "color-prettylights-syntax-storage-modifier-import": "#f8f8f2",
    },
    "tokyo-night": {
        "bgColor-default": "#1a1b26",
        "bgColor-muted": "#16161e",
        "fgColor-default": "#c0caf5",
        "fgColor-muted": "#9aa5ce",
        "fgColor-accent": "#7aa2f7",
        "borderColor-default": "#3b4261",
        "borderColor-muted": "#292e42",
        "color-prettylights-syntax-comment": "#565f89",
        "color-prettylights-syntax-constant": "#ff9e64",
        "color-prettylights-syntax-entity": "#7aa2f7",
        "color-prettylights-syntax-entity-tag": "#f7768e",
        "color-prettylights-syntax-keyword": "#bb9af7",
        "color-prettylights-syntax-string": "#9ece6a",
        "color-prettylights-syntax-variable": "#2ac3de",
        "color-prettylights-syntax-storage-modifier-import": "#c0caf5",
    },
    "rose-pine": {
        "bgColor-default": "#191724",
        "bgColor-muted": "#1f1d2e",
        "fgColor-default": "#e0def4",
        "fgColor-muted": "#908caa",
        "fgColor-accent": "#c4a7e7",
        "borderColor-default": "#403d52",
        "borderColor-muted": "#26233a",
        "color-prettylights-syntax-comment": "#6e6a86",
        "color-prettylights-syntax-constant": "#c4a7e7",
        "color-prettylights-syntax-entity": "#ebbcba",
        "color-prettylights-syntax-entity-tag": "#9ccfd8",
        "color-prettylights-syntax-keyword": "#31748f",
        "color-prettylights-syntax-string": "#f6c177",
        "color-prettylights-syntax-variable": "#eb6f92",
        "color-prettylights-syntax-storage-modifier-import": "#e0def4",
    },
    "rose-pine-dawn": {
        "bgColor-default": "#faf4ed",
        "bgColor-muted": "#f2e9e1",
        "fgColor-default": "#575279",
        "fgColor-muted": "#797593",
        "fgColor-accent": "#907aa9",
        "borderColor-default": "#dfdad9",
        "borderColor-muted": "#f2e9e1",
        "color-prettylights-syntax-comment": "#9893a5",
        "color-prettylights-syntax-constant": "#907aa9",
        "color-prettylights-syntax-entity": "#d7827e",
        "color-prettylights-syntax-entity-tag": "#56949f",
        "color-prettylights-syntax-keyword": "#286983",
        "color-prettylights-syntax-string": "#ea9d34",
        "color-prettylights-syntax-variable": "#b4637a",
        "color-prettylights-syntax-storage-modifier-import": "#575279",
    },
}


def theme_app_css() -> str:
    rules = [
        (
            "  :root { --chip:color-mix(in srgb, var(--field) 50%, var(--line)); "
            "--dash:color-mix(in srgb, var(--edge) 70%, var(--muted)); "
            "--accent-line:color-mix(in srgb, var(--accent) 60%, var(--edge)); }"
        )
    ]
    for index, (name, (_, mode, values)) in enumerate(THEMES.items()):
        selector = (
            f':root, html[data-theme="{name}"]'
            if index == 0
            else f'html[data-theme="{name}"]'
        )
        props = " ".join(
            f"--{key}:{value};" for key, value in zip(THEME_KEYS, values, strict=True)
        )
        rules.append(f"  {selector} {{ color-scheme:{mode}; {props} }}")
    return "\n".join(rules)


HLJS_CSS = """
  .hljs { color:var(--fgColor-default); }
  .hljs-doctag, .hljs-keyword, .hljs-meta .hljs-keyword, .hljs-template-tag, .hljs-template-variable, .hljs-type, .hljs-variable.language_ { color:var(--color-prettylights-syntax-keyword); }
  .hljs-title, .hljs-title.class_, .hljs-title.class_.inherited__, .hljs-title.function_ { color:var(--color-prettylights-syntax-entity); }
  .hljs-attr, .hljs-attribute, .hljs-literal, .hljs-meta, .hljs-number, .hljs-operator, .hljs-selector-attr, .hljs-selector-class, .hljs-selector-id, .hljs-variable { color:var(--color-prettylights-syntax-constant); }
  .hljs-meta .hljs-string, .hljs-regexp, .hljs-string { color:var(--color-prettylights-syntax-string); }
  .hljs-built_in, .hljs-symbol { color:var(--color-prettylights-syntax-variable); }
  .hljs-code, .hljs-comment, .hljs-formula { color:var(--color-prettylights-syntax-comment); }
  .hljs-name, .hljs-quote, .hljs-selector-pseudo, .hljs-selector-tag { color:var(--color-prettylights-syntax-entity-tag); }
  .hljs-subst { color:var(--fgColor-default); }
  .hljs-section { color:var(--color-prettylights-syntax-markup-heading); font-weight:700; }
  .hljs-bullet { color:var(--color-prettylights-syntax-markup-list); }
  .hljs-emphasis { font-style:italic; }
  .hljs-strong { font-weight:700; }
  .hljs-addition { color:var(--color-prettylights-syntax-markup-inserted-text); background:var(--color-prettylights-syntax-markup-inserted-bg); }
  .hljs-deletion { color:var(--color-prettylights-syntax-markup-deleted-text); background:var(--color-prettylights-syntax-markup-deleted-bg); }
"""


def theme_reader_css() -> str:
    """GitHub's light and dark palettes keyed on the picked theme instead of the OS setting."""
    try:
        source = (VENDOR / "github-markdown.css").read_text(encoding="utf-8")
    except OSError:
        return HLJS_CSS
    rules = []
    for mode, props in re.findall(
        r"@media \(prefers-color-scheme: (dark|light)\) \{\s*\.markdown-body, \[data-theme=\"\w+\"\] \{(.*?)\n  \}\n\}",
        source,
        re.DOTALL,
    ):
        rules.append(
            f'  html[data-mode="{mode}"], html[data-mode="{mode}"] .markdown-body {{{props}\n  }}'
        )
    for name, values in READER_THEMES.items():
        props = " ".join(f"--{key}:{value};" for key, value in values.items())
        rules.append(
            f'  html[data-theme="{name}"], html[data-theme="{name}"] .markdown-body {{ {props} }}'
        )
    return "\n".join(rules) + HLJS_CSS


THEME_READER_CSS = theme_reader_css()


THEME_JS = """
(() => {
  const root = document.documentElement, key = 'sharei-theme';
  const themes = %s;
  const media = matchMedia('(prefers-color-scheme: dark)');
  function picked() {
    let saved = null;
    try { saved = localStorage.getItem(key); } catch (error) {}
    if (saved === 'auto' || (saved && saved in themes)) return saved;
    const fallback = root.dataset.themeDefault;
    return fallback && fallback in themes ? fallback : 'auto';
  }
  function apply() {
    const choice = picked();
    const theme = choice === 'auto' ? (media.matches ? 'dark' : 'light') : choice;
    root.dataset.choice = choice;
    root.dataset.theme = theme;
    root.dataset.mode = themes[theme][0];
    const meta = document.querySelector('meta[name=theme-color]');
    if (meta) meta.content = themes[theme][1];
  }
  window.shareiTheme = (name) => {
    try { localStorage.setItem(key, name); } catch (error) {}
    apply();
  };
  media.addEventListener('change', apply);
  addEventListener('storage', (event) => { if (event.key === key) apply(); });
  apply();
})();
"""


def theme_script(nonce: str = "") -> str:
    themes = {name: [mode, values[0]] for name, (_, mode, values) in THEMES.items()}
    attribute = f' nonce="{nonce}"' if nonce else ""
    return f"<script{attribute}>{THEME_JS % json.dumps(themes)}</script>"


def theme_select(nonce: str) -> str:
    options = '<option value="auto">Auto</option>' + "".join(
        f'<option value="{name}">{label}</option>'
        for name, (label, _, _) in THEMES.items()
    )
    return (
        f'<select id="theme-select" aria-label="Theme">{options}</select>'
        f'<script nonce="{nonce}">'
        "const themeSelect = document.getElementById('theme-select');"
        "themeSelect.value = document.documentElement.dataset.choice;"
        "themeSelect.addEventListener('change', () => window.shareiTheme(themeSelect.value));"
        "</script>"
    )


THEME_PICKER_JS = """
(() => {
  const button = document.getElementById('theme-button');
  const menu = document.getElementById('theme-menu');
  function paint() {
    menu.querySelectorAll('button[data-theme]').forEach((item) => {
      item.setAttribute('aria-pressed', String(item.dataset.theme === document.documentElement.dataset.choice));
    });
  }
  function toggle(open) {
    menu.hidden = !open;
    button.setAttribute('aria-expanded', String(open));
    if (open) paint();
  }
  button.addEventListener('click', (event) => { event.stopPropagation(); toggle(menu.hidden); });
  menu.addEventListener('click', (event) => {
    const item = event.target.closest('button[data-theme]');
    if (!item) return;
    window.shareiTheme(item.dataset.theme);
    paint();
  });
  document.addEventListener('click', (event) => { if (!menu.hidden && !menu.contains(event.target)) toggle(false); });
  document.addEventListener('keydown', (event) => { if (event.key === 'Escape' && !menu.hidden) { toggle(false); button.focus(); } });
  const previousBusy = window.liveBusy;
  window.liveBusy = () => !menu.hidden || (previousBusy ? previousBusy() : false);
})();
"""
