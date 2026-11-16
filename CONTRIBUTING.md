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

Run the same gate as CI (jscpd and markdownlint need Node.js 22 or newer):

```bash
uv run python scripts/gate.py
```

It runs `ruff check`, `ruff format --check`, `mypy` (strict, on `src`, `tests` and `scripts`), the import contracts in `pyproject.toml` (import-linter), `vulture`, the em dash and emoji scan of the tracked files (`scripts/git_hooks.py scan`), `pytest --cov` against the `fail_under` threshold in `pyproject.toml`, jscpd with `.jscpd.json` and markdownlint. Every step runs even after a failure, and a summary lists the exit code and duration of each.

CI also checks the relative links and anchors in the Markdown files with [lychee](https://github.com/lycheeverse/lychee) (`lychee --offline --include-fragments`); run it locally if you have it installed.

Tests write only to `tmp_path` (the suite points it at `.test-artifacts/pytest`) and read data through paths computed from the repository root. The default suite uses generated synthetic data; tests marked `real_data` need the source snapshots and run only when `WC2026BET_DATA_DIR` is set (see the README).

New model behaviour comes with a test written first. The model specification and the data contracts are in [`docs/model-spec.md`](docs/model-spec.md) and [`docs/data-contracts.md`](docs/data-contracts.md).

## Pull requests

- Pull requests are merged by squash, so the pull request title becomes the commit on `main`. It must be a [Conventional Commit](https://www.conventionalcommits.org/): `<type>(<scope>): <subject>`, with type one of `feat`, `fix`, `docs`, `style`, `refactor`, `perf`, `test`, `build`, `ci`, `chore`, `revert`, a subject of at most 72 characters and no trailing period. CI checks the title.
- Fill in the pull request template: what changes, the checks you ran, and the checks you skipped with the reason.
- [CodeRabbit](https://www.coderabbit.ai/) reviews pull requests into `main` automatically once they are ready for review (not drafts); its comments are suggestions, and the maintainer decides which to apply.
- The maintainer reviews every pull request, and CI must be green before it is merged.
