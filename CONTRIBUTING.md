# Contributing

Bug reports and pull requests are welcome. For anything bigger than a small
fix, open an issue first so we can agree on the approach.

To work on sharei you need Python 3.12 or newer and
[uv](https://docs.astral.sh/uv/).

```sh
uv sync
uv run sharei --port 8765 --root /tmp/sharei-dev
uv run pytest
uv run ruff format .
uv run ruff check .
```

sharei has no runtime dependencies on purpose (Pillow is optional, for
thumbnails). Please keep it that way. The server and the uploader are each a
single file, with the web pages written inline, and there is no frontend build
step.

Read [AGENTS.md](AGENTS.md) before changing routes, file handling or anything
in the security rules. Security problems go through [SECURITY.md](SECURITY.md),
not public issues.
