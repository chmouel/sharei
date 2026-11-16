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

Markdown is formatted in your browser and never leaves your machine.

## Public links

A file you share publicly is the one exception to the password. Its link
holds 128 random bits and is the only key: anyone who has it can download
that one file, and nobody can guess it. A link lasts one day unless you
pick another duration (up to 30 days, or no end). It stops working as soon as
it runs out, as soon as you unshare, delete or replace an expired file, or
when the file expires. It
is also refused when another file shows up at the same place. Copies already
downloaded stay with whoever downloaded them.

Public files are sent with a `sandbox` Content-Security-Policy, so an HTML
or SVG file cannot run scripts, and with `no-store` and `no-referrer`.
sharei hides the links in its own request log. A markdown file is the
exception: it opens in the same reader as the private `/md` pages, under a
nonce-only script policy, with its HTML cleaned by DOMPurify and images
limited to sharei itself. Only sharei's own scripts run, never anything in
the file. The reader loads its bundled styles, scripts and icons from
`/public/_assets/`, which holds nothing but those built-in files.

The proxy decides which requests are public, by setting `X-Sharei-Public` on
`/public/*` and removing it everywhere else (see the README). With the
header present, sharei serves `GET /public/<token>` and
`/public/_assets/` and returns 404 for
everything else, uploads and deletes included. A proxy that forgets to strip
the header on private paths makes them unreachable, never public. A proxy
that lets other paths through without the password exposes them, as it
would without this feature.

If saving an unshare fails, sharei says so: the link is off right away but
comes back after a restart, so unshare it again.

Phone notifications, when turned on, go through the push service of the
phone's browser (Google, Mozilla or Apple). The message, a file name or the
first words of the clipboard, is encrypted for that browser, but the service
sees when it is sent and to which device.

## Supported versions

Only the latest release gets fixes.

## Reporting a vulnerability

Please report security problems privately through
[GitHub's private vulnerability reporting](https://github.com/chmouel/sharei/security/advisories/new),
not in a public issue. Include what you found, how to reproduce it and what
an attacker could do with it. You should hear back within a week.
