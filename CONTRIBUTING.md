# Contributing

Issues and pull requests are welcome. For a larger change, open an issue first so the approach can be agreed before you write the code. Security problems go through [SECURITY.md](SECURITY.md), never through a public issue.

## Setup

Requirements: Python 3.13 and [uv](https://docs.astral.sh/uv/).

```bash
uv sync --locked --extra dev          # .venv with the locked runtime and development dependencies
git config core.hooksPath .githooks   # enable the committed git hooks
```

The hooks run `scripts/git_hooks.py` through uv:

- `pre-commit` checks that the commit author and committer are set, rejects an em dash (U+2014) or emoji in the staged lines, and runs `ruff check` and `ruff format --check` on the staged Python files;
- `commit-msg` checks the Conventional Commits format (subject at most 72 characters, body lines at most 100; subjects that git writes, such as `Merge ...`, `Revert "..."` and `fixup! ...`, are exempt), rejects co-author and other attribution or session trailers, and rejects an em dash or emoji in the message.

## Before opening a pull request

Run the same gate as CI:

```bash
uv run ruff check .
uv run ruff format --check .
uv run mypy
uv run python -m pytest
```

CI also runs the tests with `--cov` against the `fail_under` threshold in `pyproject.toml`; add it locally when your change touches `src/`.

Tests write only to `tmp_path` (the suite points it at `.test-artifacts/pytest`) and read data through paths computed from the repository root. The default suite uses generated synthetic data; tests marked `real_data` need the source snapshots and run only when `WC2026BET_DATA_DIR` is set (see the README).

New model behaviour comes with a test written first. The model specification and the data contracts are in [`docs/model-spec.md`](docs/model-spec.md) and [`docs/data-contracts.md`](docs/data-contracts.md).

## Pull requests

- Pull requests are merged by squash, so the pull request title becomes the commit on `main`. It must be a [Conventional Commit](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`, with type one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, a subject of at most 72 characters and no trailing period. CI checks the title.
- Fill in the pull request template: what changes, the checks you ran, and the checks you skipped with the reason.
- The maintainer reviews every pull request, and CI must be green before it is merged.
