# sharei

sharei is a small web page that runs on your computer and that you open on
your phone. Use it to grab the app you just built, look at your screenshots,
pass text back and forth or drop a file from one device to the other, without
cables, a cloud drive or emailing yourself.

![sharei on a phone](docs/screenshots/hero.png)

## What you get

The page has four tabs, along the bottom on a phone and down the left side
on a computer.

Screenshots shows the screenshots you saved, grouped by project. You can swipe
through them, draw arrows and notes on them, and set them to disappear after a
while.

Drop holds files you send either way. Markdown opens formatted the way GitHub
shows it, code opens with colours and line numbers, pictures open full
screen, and videos play right in the page. Any file there can be set to expire too.

Clipboard is a shared note. Paste on one device and copy on the other.
It clears itself after ten minutes unless you change that. The last five
notes you replaced stay underneath, each on its own timer, so you can copy
one again or put it back. Clear forgets the current note for good.

Artifacts lists the files your projects build, newest first: Android APKs,
Python wheels, release archives, whatever you point it at. Tap one on your
phone to download it, or to install it if it is an APK.

| Screenshots | Drop | Clipboard |
|---|---|---|
| ![Screenshots](docs/screenshots/shots.png) | ![Drop](docs/screenshots/drop.png) | ![Clipboard](docs/screenshots/clip.png) |

| Artifacts | Markdown | Code |
|---|---|---|
| ![Artifacts](docs/screenshots/artifacts.png) | ![Markdown](docs/screenshots/markdown.png) | ![Code](docs/screenshots/code.png) |

The round button at the top right of each page picks a colour theme: light,
dark, Dracula, Tokyo Night, Rosé Pine or Rosé Pine Dawn. Auto, the default,
follows your device. Each browser remembers its own choice, and the `theme`
setting picks the default for browsers that haven't chosen yet.

If you add sharei to your Android home screen, it shows up in the Share menu,
so you can send a link, some text or a photo from any app to your computer.

## Install

You need Python 3.12 or newer and [uv](https://docs.astral.sh/uv/).

```sh
uv tool install git+https://github.com/chmouel/sharei
sharei
```

Open <http://localhost:8000> to check that it runs. For small thumbnails of
big screenshots, install `'sharei[thumbnails] @ git+https://github.com/chmouel/sharei'`
instead.

To start it with your session on Linux, copy
[`contrib/sharei.service`](contrib/sharei.service) to
`~/.config/systemd/user/` and run:

```sh
systemctl --user enable --now sharei
```

## Open it on your phone

sharei has no password of its own, and by default only your computer can reach
it. To use it from your phone, put it behind a reverse proxy that asks for a
password, such as Caddy or nginx with basic auth. Then tell sharei the address
you use, in `~/.config/sharei/config.toml`:

```toml
allow_hosts = ["share.example.com"]
allow_origins = ["https://share.example.com"]
```

A minimal Caddy setup:

```caddy
share.example.com {
    basic_auth {
        me <hash from `caddy hash-password`>
    }
    reverse_proxy localhost:8000
}
```

On a home network you fully trust, you can set `host = "0.0.0.0"` instead and
open `http://<your computer's address>:8000`. Anyone else on that network can
then use sharei too. [SECURITY.md](SECURITY.md) has more on this.

## Tell it where your builds are

Add an `[[artifacts]]` entry per project to the config, with the folder and the
files to show:

```toml
[[artifacts]]
name = "My app"
root = "~/src/my-app"
patterns = ["app/build/outputs/apk/**/*.apk"]
```

`**` stands for any number of folders. To cover every project in a folder at
once, give a wildcard as the root:

```toml
[[artifacts]]
root = "~/src/*"
patterns = ["dist/*.whl", "target/release/*.tar.gz"]
```

Precise patterns like `dist/*.whl` keep the page fast. A pattern starting with
`**` has to look through the whole project. sharei also picks up builds in your
git worktrees. [`config.example.toml`](config.example.toml) lists every other
setting.

## Share from the terminal

`sharec` comes with sharei and sends things to it:

```sh
sharec notes.md          # formatted markdown, with the pictures it uses
sharec main.go           # code, with colours and line numbers
sharec -s                # take a screenshot and send it
sharec -c                # send the clipboard text as a markdown note
sharec                   # pick from a menu
```

It prints the link to open on your phone. Set `SHAREI_PUBLIC_URL` to your
public address (for example `https://share.example.com`) so those links work
away from home. The menu needs [gum](https://github.com/charmbracelet/gum). Zsh
completion lives in [`contrib/_sharec`](contrib/_sharec).

It can fetch things back too:

```sh
sharec get               # print the shared clipboard
sharec get clip 1 -c     # put the previous clipboard note on this clipboard
sharec get drop          # download the newest dropped file here
sharec get shot          # same for the newest screenshot
sharec get drop 2 -o -   # the third newest file, to stdout
sharec get list          # what is on sharei right now
```

Downloads never overwrite a file; they become `name-1.ext` instead.

## Privacy

Everything stays on your computer except markdown: sharei asks GitHub to format
it, the same way github.com shows a README. Keep that in mind before opening a
private document in the markdown view. A GitHub token in the config raises
GitHub's hourly limit and needs no permissions.

## Licence

Apache 2.0. sharei bundles github-markdown-css, mermaid, highlight.js and
marker.js, with their licences next to them in `src/sharei/vendor/`.
