"""The quality gate: every check CI's `check` job runs on code, in one command.

Usage: uv run python scripts/gate.py

Runs each step from the repository root (or the directory the step names), prints its
name, exit code and duration, carries on after a failure so one run shows every problem,
and exits 1 if any step failed. The Python tools come from the project environment
(`uv sync --locked --extra dev`); jscpd and markdownlint run through npx (Node.js 22 or newer).
"""

from __future__ import annotations

import shutil
import sys
import time
from collections.abc import Sequence
from pathlib import Path

from git_hooks import run

ROOT = Path(__file__).resolve().parents[1]

# (name, working directory relative to the root, command); "python" is the interpreter running this script.
STEPS: tuple[tuple[str, str, tuple[str, ...]], ...] = (
    ("ruff check", ".", ("ruff", "check", ".")),
    ("ruff format", ".", ("ruff", "format", "--check", ".")),
    ("mypy", ".", ("mypy",)),
    # From `src`: at the root the `wc2026bet/` shim shadows the package and the contract modules go missing.
    ("import contracts", "src", ("lint-imports", "--no-cache", "--config", "../pyproject.toml")),
    ("vulture", ".", ("vulture",)),
    ("text scan", ".", ("python", "scripts/git_hooks.py", "scan")),
    ("pytest", ".", ("python", "-m", "pytest", "--cov")),
    ("jscpd", ".", ("npx", "--yes", "jscpd@5.4.2", "src", "tests", "scripts")),
    ("markdownlint", ".", ("npx", "--yes", "markdownlint-cli2@0.24.0", "**/*.md")),
)


def run_step(name: str, workdir: str, command: Sequence[str]) -> int:
    program = sys.executable if command[0] == "python" else shutil.which(command[0])
    if program is None:
        print(
            f"{name}: {command[0]} is not on PATH; npx comes with Node.js 22 or newer, "
            "the Python tools with `uv sync --locked --extra dev` (run the gate through `uv run`)",
            file=sys.stderr,
        )
        return 127
    result = run([program, *command[1:]], cwd=ROOT / workdir)
    print(result.stdout, end="")
    print(result.stderr, end="", file=sys.stderr)
    return result.returncode


def main() -> int:
    results: list[tuple[str, int, float]] = []
    for name, workdir, command in STEPS:
        print(f"==> {name}", flush=True)
        started = time.monotonic()
        code = run_step(name, workdir, command)
        results.append((name, code, time.monotonic() - started))
        print(f"<== {name}: exit {code} in {results[-1][2]:.1f} s", flush=True)
    print("\nSummary:")
    for name, code, seconds in results:
        print(f"  {'ok  ' if code == 0 else 'FAIL'} {name}: exit {code} in {seconds:.1f} s")
    failed = [name for name, code, _ in results if code != 0]
    print(f"Failed: {', '.join(failed)}" if failed else "All steps passed.")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
