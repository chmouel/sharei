"""Build sharei's diagram icons from Lucide.

Usage: python contrib/icons/make_icons.py LUCIDE_STATIC_DIR src/sharei/icons

LUCIDE_STATIC_DIR is an unpacked lucide-static package (npm pack lucide-static).
Each icon becomes a 48x48 tile: a tinted rounded square with the Lucide glyph
stroked in one colour, so it reads the same on light and dark pages.
"""

import pathlib
import re
import sys

BLUE, GREEN, RED, AMBER, VIOLET = "#4f8ef7", "#3fb950", "#f85149", "#d29922", "#a371f7"
ICONS = {
    # people and agents
    "user": ("user", BLUE),
    "users": ("users", BLUE),
    "reviewer": ("user-check", BLUE),
    "agent": ("bot", VIOLET),
    "model": ("cpu", VIOLET),
    "brain": ("brain", VIOLET),
    "skill": ("book-open", VIOLET),
    "prompt": ("message-square-text", VIOLET),
    "sparkles": ("sparkles", VIOLET),
    "tool": ("wrench", VIOLET),
    # git and forges
    "issue": ("circle-dot", BLUE),
    "pull-request": ("git-pull-request", BLUE),
    "commit": ("git-commit-horizontal", BLUE),
    "branch": ("git-branch", BLUE),
    "merge": ("git-merge", BLUE),
    "fork": ("git-fork", BLUE),
    "repository": ("book-marked", BLUE),
    "tag": ("tag", BLUE),
    "release": ("package-check", BLUE),
    "comment": ("message-square", BLUE),
    "review": ("message-square-code", BLUE),
    "diff": ("file-diff", BLUE),
    "code": ("code", BLUE),
    "file-code": ("file-code", BLUE),
    # events and CI
    "event": ("bell", BLUE),
    "webhook": ("webhook", BLUE),
    "listener": ("radio", BLUE),
    "trigger": ("zap", AMBER),
    "pipeline": ("workflow", BLUE),
    "task": ("square-check-big", BLUE),
    "step": ("list-checks", BLUE),
    "test": ("flask-conical", BLUE),
    "build": ("hammer", BLUE),
    "deploy": ("rocket", BLUE),
    "rerun": ("refresh-cw", BLUE),
    "follow-up": ("redo-2", BLUE),
    "schedule": ("calendar-clock", BLUE),
    "queue": ("list-ordered", AMBER),
    "wait": ("hourglass", AMBER),
    "timer": ("timer", AMBER),
    "clock": ("clock", AMBER),
    "check": ("circle-check", GREEN),
    "success": ("badge-check", GREEN),
    "fail": ("circle-x", RED),
    "warning": ("triangle-alert", AMBER),
    "bug": ("bug", RED),
    "fix": ("bandage", GREEN),
    "stop": ("octagon-x", RED),
    "play": ("play", GREEN),
    "pause": ("pause", AMBER),
    # platform
    "cluster": ("server", BLUE),
    "node": ("server-cog", BLUE),
    "pod": ("box", BLUE),
    "container": ("container", BLUE),
    "namespace": ("boxes", BLUE),
    "service": ("network", BLUE),
    "network": ("waypoints", BLUE),
    "ingress": ("door-open", BLUE),
    "route": ("route", BLUE),
    "load-balancer": ("split", BLUE),
    "database": ("database", BLUE),
    "storage": ("hard-drive", BLUE),
    "cache": ("database-zap", BLUE),
    "cloud": ("cloud", BLUE),
    "registry": ("package", BLUE),
    "image": ("layers", BLUE),
    "config": ("settings", BLUE),
    "operator": ("cog", BLUE),
    "controller": ("sliders-horizontal", BLUE),
    "api": ("plug", BLUE),
    "terminal": ("terminal", BLUE),
    "cli": ("square-terminal", BLUE),
    "laptop": ("laptop", BLUE),
    "phone": ("smartphone", BLUE),
    "browser": ("app-window", BLUE),
    "globe": ("globe", BLUE),
    # security and identity
    "identity": ("id-card", BLUE),
    "fingerprint": ("fingerprint", BLUE),
    "key": ("key-round", AMBER),
    "token": ("ticket", AMBER),
    "secret": ("lock", AMBER),
    "unlock": ("lock-open", GREEN),
    "policy": ("scroll-text", BLUE),
    "shield": ("shield-check", GREEN),
    "refuse": ("ban", RED),
    "audit": ("file-search", BLUE),
    "certificate": ("file-badge", BLUE),
    # data and output
    "logs": ("logs", BLUE),
    "report": ("file-text", BLUE),
    "document": ("file", BLUE),
    "folder": ("folder", BLUE),
    "search": ("search", BLUE),
    "inspect": ("scan-search", BLUE),
    "metrics": ("chart-line", BLUE),
    "monitor": ("activity", BLUE),
    "dashboard": ("gauge", BLUE),
    "alert": ("siren", RED),
    "notification": ("bell-ring", BLUE),
    "mail": ("mail", BLUE),
    "chat": ("messages-square", BLUE),
    "upload": ("upload", BLUE),
    "download": ("download", BLUE),
    "link": ("link", BLUE),
    "filter": ("funnel", BLUE),
    "decision": ("signpost", AMBER),
    "idea": ("lightbulb", AMBER),
}


def tile(glyph: str, colour: str) -> str:
    inner = glyph[glyph.index(">", glyph.index("<svg")) + 1 : glyph.rindex("</svg>")]
    inner = re.sub(r"\s*\n\s*", "", inner).strip()
    return (
        '<svg xmlns="http://www.w3.org/2000/svg" width="48" height="48" viewBox="0 0 48 48">'
        f'<rect x="3" y="3" width="42" height="42" rx="11" fill="{colour}" fill-opacity=".12"/>'
        f'<g transform="translate(10.8 10.8) scale(1.1)" fill="none" stroke="{colour}" stroke-width="2" '
        f'stroke-linecap="round" stroke-linejoin="round">{inner}</g></svg>\n'
    )


def main() -> int:
    source = pathlib.Path(sys.argv[1]) / "icons"
    out = pathlib.Path(sys.argv[2])
    out.mkdir(parents=True, exist_ok=True)
    for old in out.glob("*.svg"):
        old.unlink()
    missing = [
        glyph for glyph, _ in ICONS.values() if not (source / f"{glyph}.svg").is_file()
    ]
    if missing:
        print("missing in Lucide:", ", ".join(missing), file=sys.stderr)
        return 1
    for name, (glyph, colour) in sorted(ICONS.items()):
        (out / f"{name}.svg").write_text(
            tile((source / f"{glyph}.svg").read_text(), colour)
        )
    print(f"wrote {len(ICONS)} icons to {out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
