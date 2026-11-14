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

The same three commands run before every push if you install the hook:

```sh
uvx pre-commit install --hook-type pre-push
```

`.pre-commit-config.yaml` runs them at the pre-push stage only, so commits
stay instant.

sharei's only runtime dependency is
[aniflow](https://github.com/chmouel/aniflow), which provides the Markdown
reader, the diagram walkthroughs and the shared web helpers. Pillow is
optional, for thumbnails. Please don't add others. The web pages are written
inline in Python, and sharei itself has no frontend build step; reader and
diagram changes belong in the aniflow repository.

Read [AGENTS.md](AGENTS.md) before changing routes, file handling or anything
in the security rules. Security problems go through [SECURITY.md](SECURITY.md),
not public issues.
