# Security policy

## How sharei is meant to run

sharei has no login of its own. Anyone who can reach it can see and download
everything it lists, read and change the clipboard, upload files and delete
them. It is built for one person and their own devices.

Keep it safe by:

- leaving it on the default address (`127.0.0.1`), so only your computer can
  reach it
- putting it behind a reverse proxy that asks for a password (Caddy, nginx,
  Tailscale Serve and the like) when you want to use it from your phone
- adding the proxy's public address to `allow_hosts` / `allow_origins` in the
  config
- setting `host = "0.0.0.0"` only on a network you trust, since everyone on
  it can then use sharei without a password

sharei also has built-in protections. It checks which address and page a
request comes from, keeps file access inside its own folder, never serves
hidden files and limits what uploaded pages and scripts can do in your
browser. These are a second line of defence, not a replacement for the
password in front.

Markdown you open in sharei is sent to GitHub's API to be rendered. Don't use
that view for text that must stay private.

## Supported versions

Only the latest release gets fixes.

## Reporting a vulnerability

Please report security problems privately through
[GitHub's private vulnerability reporting](https://github.com/chmouel/sharei/security/advisories/new),
not in a public issue. Include what you found, how to reproduce it and what
an attacker could do with it. You should hear back within a week.
