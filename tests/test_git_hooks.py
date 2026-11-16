import importlib.util
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
_spec = importlib.util.spec_from_file_location("git_hooks", REPO_ROOT / "scripts" / "git_hooks.py")
assert _spec is not None and _spec.loader is not None
hooks = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(hooks)

# Built at runtime so this file passes its own check.
EM_DASH = chr(0x2014)
EMOJI = chr(0x1F600)

OWNER = "Jane Doe <jane@example.com>"


def test_accepts_a_conventional_message_with_a_body() -> None:
    message = "feat(cli): add a run-all flag\n\nA body line that explains why.\n"
    assert hooks.commit_message_problems(message) == []


def test_ignores_comment_lines_and_the_verbose_diff() -> None:
    message = (
        "fix: handle an empty file\n"
        "# Please enter the commit message " + EM_DASH + "\n"
        "# ------------------------ >8 ------------------------\n"
        "+ a diff line that is far longer than one hundred characters " + "x" * 80 + " " + EMOJI + "\n"
    )
    assert hooks.commit_message_problems(message) == []


def test_rejects_a_subject_that_is_not_conventional() -> None:
    assert hooks.commit_message_problems("Add a feature\n")


def test_rejects_an_unknown_type() -> None:
    assert hooks.commit_message_problems("feature: add a thing\n")


def test_subject_limit_is_72_characters() -> None:
    assert hooks.commit_message_problems("fix: " + "a" * 72) == []
    assert hooks.commit_message_problems("fix: " + "a" * 73)


def test_rejects_a_trailing_period() -> None:
    assert hooks.commit_message_problems("fix: handle an empty file.\n")


def test_body_lines_are_limited_to_100_characters() -> None:
    assert hooks.commit_message_problems("fix: x\n\n" + "b" * 100) == []
    assert hooks.commit_message_problems("fix: x\n\n" + "b" * 101)


def test_rejects_attribution_and_session_trailers() -> None:
    for trailer in (
        "Co-authored-by: Someone <someone@example.com>",
        "co-authored-by: someone <someone@example.com>",
        "Tool-Session: 0123",
        "Generated-by: a tool",
        "Generated with a tool",
    ):
        assert hooks.commit_message_problems(f"fix: x\n\n{trailer}\n"), trailer


def test_accepts_subjects_that_git_writes() -> None:
    for subject in (
        "Merge branch 'main' into feature",
        'Revert "feat: x"',
        "fixup! feat: x",
        "squash! feat: x",
        "amend! feat: x",
    ):
        assert hooks.commit_message_problems(f"{subject}\n\nThis reverts commit abc1234.\n") == [], subject


def test_a_session_line_outside_the_trailer_block_passes() -> None:
    message = "fix(auth): renew tokens\n\nSession: tokens expire after an hour.\n\nRefs: #12\n"
    assert hooks.commit_message_problems(message) == []
    assert hooks.commit_message_problems("fix: x\n\nRefs: #12\nTool-Session: 0123\n")


def test_rejects_em_dash_and_emoji_in_the_message() -> None:
    assert hooks.commit_message_problems(f"fix: x {EM_DASH} y\n")
    assert hooks.commit_message_problems(f"fix: x\n\nbody {EMOJI}\n")


def test_allows_en_dash_and_middle_dot() -> None:
    assert hooks.commit_message_problems(f"fix: x {chr(0x2013)} y {chr(0xB7)} z\n") == []


DIFF = f"""diff --git a/docs/a.md b/docs/a.md
--- a/docs/a.md
+++ b/docs/a.md
@@ -1,0 +2,2 @@
+clean line
+bad {EM_DASH} line
diff --git a/src/b.py b/src/b.py
new file mode 100644
--- /dev/null
+++ b/src/b.py
@@ -0,0 +1 @@
+print("{EMOJI}")
diff --git a/c.png b/c.png
Binary files /dev/null and b/c.png differ
"""


def test_reports_only_added_lines_with_path_and_line_number() -> None:
    problems = hooks.diff_text_problems(DIFF)
    assert len(problems) == 2
    assert problems[0].startswith("docs/a.md:3: em dash")
    assert problems[1].startswith("src/b.py:1: emoji")


def test_removed_lines_do_not_count() -> None:
    diff = f"--- a/a.md\n+++ b/a.md\n@@ -1 +1 @@\n-old {EM_DASH}\n+new\n"
    assert hooks.diff_text_problems(diff) == []


def test_identity_only_needs_to_be_set_without_an_opt_in() -> None:
    ident = "Outside Contributor <someone@example.org> 1700000000 +0100"
    assert hooks.identity_problems(ident, ident, []) == []
    assert hooks.identity_problems("", ident, [])


def test_an_email_without_at_is_reported_as_invalid() -> None:
    ident = "Jane Doe <jane.example.com> 1700000000 +0100"
    assert hooks.identity_problems(ident, ident, []) == [
        "author email jane.example.com is not a valid address; fix git config user.email",
        "committer email jane.example.com is not a valid address; fix git config user.email",
    ]


def test_identity_must_be_an_owner_identity_after_an_opt_in() -> None:
    owner = OWNER + " 1700000000 +0100"
    other = "Someone Else <other@example.org> 1700000000 +0100"
    assert hooks.identity_problems(owner, owner, [OWNER]) == []
    assert hooks.identity_problems(other, owner, [OWNER])
    assert hooks.identity_problems(owner, other, [OWNER])


def test_python_files_keeps_only_python_sources() -> None:
    assert hooks.python_files(["a.py", "docs/b.md", "scripts/c.py", "d.pyi"]) == ["a.py", "scripts/c.py", "d.pyi"]


def test_the_diff_options_report_staged_lines_of_a_real_repository(tmp_path: Path) -> None:
    hooks.git(["init", "-q"], tmp_path)
    hooks.git(["config", "diff.noprefix", "true"], tmp_path)  # the options must override it
    (tmp_path / "notes.md").write_text(f"a {EM_DASH} b\n", encoding="utf-8")
    hooks.git(["add", "notes.md"], tmp_path)
    problems = hooks.diff_text_problems(hooks.git(["diff", "--cached", *hooks.DIFF_OPTIONS], tmp_path))
    assert problems == ["notes.md:1: em dash (U+2014); use an en dash (U+2013) or a middle dot (U+00B7)"]


def test_scan_reports_forbidden_characters_in_tracked_text_files(tmp_path: Path) -> None:
    hooks.git(["init", "-q"], tmp_path)
    (tmp_path / "clean.md").write_text("clean\n", encoding="utf-8")
    (tmp_path / "image.png").write_bytes(b"\x89PNG\x00" + EM_DASH.encode())
    (tmp_path / "uv.lock").write_text(f"a {EM_DASH} b\n", encoding="utf-8")
    (tmp_path / "untracked.md").write_text(f"a {EM_DASH} b\n", encoding="utf-8")
    hooks.git(["add", "clean.md", "image.png", "uv.lock"], tmp_path)
    assert hooks.scan(tmp_path) == []

    (tmp_path / "docs").mkdir()
    (tmp_path / "docs" / "bad.md").write_text(f"first\nsecond {EM_DASH}\nthird {EMOJI}\n", encoding="utf-8")
    hooks.git(["add", "docs/bad.md"], tmp_path)
    assert hooks.scan(tmp_path) == [
        "docs/bad.md:2: em dash (U+2014); use an en dash (U+2013) or a middle dot (U+00B7)",
        "docs/bad.md:3: emoji",
    ]


def _repository(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, user: str, email: str) -> None:
    hooks.git(["init", "-q"], tmp_path)
    hooks.git(["config", "user.name", user], tmp_path)
    hooks.git(["config", "user.email", email], tmp_path)
    hooks.git(["config", "--add", hooks.OWNER_KEY, OWNER], tmp_path)
    for variable in ("GIT_AUTHOR_NAME", "GIT_AUTHOR_EMAIL", "GIT_COMMITTER_NAME", "GIT_COMMITTER_EMAIL"):
        monkeypatch.delenv(variable, raising=False)
    monkeypatch.chdir(tmp_path)


def test_pre_commit_reads_the_owner_identities_of_the_checkout(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _repository(tmp_path, monkeypatch, "Jane Doe", "jane@example.com")
    assert hooks.pre_commit() == []
    hooks.git(["config", "user.email", "other@example.org"], tmp_path)
    assert hooks.pre_commit() == [
        f"author is Jane Doe <other@example.org>, not one of the identities in {hooks.OWNER_KEY}",
        f"committer is Jane Doe <other@example.org>, not one of the identities in {hooks.OWNER_KEY}",
    ]


def test_pre_commit_runs_ruff_on_the_staged_content(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _repository(tmp_path, monkeypatch, "Jane Doe", "jane@example.com")
    # Own ruff settings: the repository's pyproject.toml excludes `.test-artifacts`, where tmp_path lives.
    (tmp_path / "ruff.toml").write_text("", encoding="utf-8")
    module = tmp_path / "module.py"
    module.write_text("x=1\n", encoding="utf-8")
    hooks.git(["add", "module.py"], tmp_path)
    module.write_text("x = 1\n", encoding="utf-8")  # fixed only in the working tree
    problems = hooks.pre_commit()
    assert len(problems) == 1
    assert problems[0].startswith("ruff format --check module.py failed")


def test_main_dispatches_and_reports(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    message = tmp_path / "COMMIT_EDITMSG"
    message.write_text("fix: handle an empty file\n", encoding="utf-8")
    assert hooks.main(["commit-msg", str(message)]) == 0
    message.write_text("not conventional\n", encoding="utf-8")
    assert hooks.main(["commit-msg", str(message)]) == 1
    assert hooks.main(["unknown"]) == 1
    assert "usage:" in capsys.readouterr().err


def test_main_scan_checks_the_current_repository(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    hooks.git(["init", "-q"], tmp_path)
    (tmp_path / "a.md").write_text(f"a {EM_DASH} b\n", encoding="utf-8")
    hooks.git(["add", "a.md"], tmp_path)
    monkeypatch.chdir(tmp_path)
    assert hooks.main(["scan"]) == 1
    assert "a.md:1: em dash" in capsys.readouterr().err
