import shutil
from collections.abc import Callable
from pathlib import Path

import pytest

from synthetic_data import odds_for, write_rows
from wc2026bet import cli
from wc2026bet.cli_commands import (
    build_decision_report_command,
    fit_score_params_command,
    group_reports_command,
    run_sensitivity_command,
    simulate_groups_command,
    simulate_tournament_command,
    train_goal_bridge_command,
    validate_command,
)
from wc2026bet.csv_io import read_csv
from wc2026bet.processed import write_odds_template


@pytest.mark.slow
def test_run_all_runs_the_real_pipeline_on_synthetic_data(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    manual = tmp_path / "manual"
    shutil.copytree(synthetic_manual_data, manual)
    write_odds_template(synthetic_base_data, manual / "odds.csv")
    odds = read_csv(manual / "odds.csv")
    for row in odds:
        row["decimal_odds"] = odds_for(row["market"], row["selection"])
    write_rows(manual / "odds.csv", odds)
    processed, out = tmp_path / "processed", tmp_path / "outputs"

    result = cli.main(
        [
            "run-all",
            *("--base-data", str(synthetic_base_data), "--processed", str(processed)),
            *("--manual", str(manual), "--out", str(out)),
            *("--simulations", "200", "--group-simulations", "100", "--sensitivity-simulations", "50", "--seed", "7"),
        ]
    )

    printed = capsys.readouterr().out
    assert result == 0, printed
    assert "Validation passed:" in printed
    assert f"Full pipeline completed: {out}" in printed
    assert len(read_csv(processed / "match_score_params.csv")) == 72
    assert len(read_csv(processed / "rating_goal_bridge.csv")) == 1
    assert len(read_csv(out / "stadium-average-ranking.csv")) == 16
    assert len(read_csv(out / "team-group.csv")) == 48
    summary = (out / "tournament-summary.md").read_text(encoding="utf-8")
    assert "- simulations: 200" in summary
    assert "- seed: 7" in summary


def test_validate_reports_the_missing_processed_files_and_mapping(
    tmp_path: Path, synthetic_base_data: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    processed = tmp_path / "processed"
    processed.mkdir()

    result = validate_command(synthetic_base_data, processed, tmp_path / "manual")

    printed = capsys.readouterr().out
    assert result == 1
    assert "- processed_matches.csv" in printed
    assert "- r32_third_place_mapping" in printed
    assert "Validation passed" not in printed


def test_fit_score_params_stops_without_the_odds_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    odds = tmp_path / "odds.csv"

    result = fit_score_params_command(tmp_path, odds, tmp_path / "params.csv", tmp_path / "config.csv", False)

    assert result == 1
    assert f"Odds file not found: {odds}" in capsys.readouterr().out
    assert not (tmp_path / "params.csv").exists()


@pytest.mark.parametrize(
    ("run", "message", "first_missing"),
    [
        (lambda p, m, o: train_goal_bridge_command(p), "Cannot train goal bridge", "matches.csv"),
        (lambda p, m, o: group_reports_command(p, o), "Cannot build group reports", "matches.csv"),
        (lambda p, m, o: simulate_groups_command(p, o, 10, 1), "Cannot simulate groups", "matches.csv"),
        (
            lambda p, m, o: simulate_tournament_command(
                p, m, o, 10, 1, 0.3, "coin_flip", False, 0.05, "none", None, 0.35
            ),
            "Cannot simulate tournament",
            "matches.csv",
        ),
        (
            lambda p, m, o: build_decision_report_command(p, o, o / "summary.md", 10, 1, 0.3, "coin_flip", 0.05),
            "Cannot build decision report",
            "match_score_params.csv",
        ),
        (lambda p, m, o: run_sensitivity_command(p, m, o, 10, 1, 0.05), "Cannot run sensitivity", "matches.csv"),
    ],
)
def test_commands_stop_and_list_missing_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    run: Callable[[Path, Path, Path], int],
    message: str,
    first_missing: str,
) -> None:
    processed, manual, out = tmp_path / "processed", tmp_path / "manual", tmp_path / "out"

    result = run(processed, manual, out)

    printed = capsys.readouterr().out
    assert result == 1
    assert f"{message}. Missing files:" in printed
    assert f"- {processed / first_missing}" in printed
    assert not out.exists()


def test_run_all_executes_pipeline_in_order(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[tuple[str, tuple[object, ...], dict[str, object]]] = []

    def record(name: str, return_value: int = 0) -> Callable[..., int]:
        def inner(*args: object, **kwargs: object) -> int:
            calls.append((name, args, kwargs))
            return return_value

        return inner

    monkeypatch.setattr(cli, "build_data_command", record("build-data"))
    monkeypatch.setattr(cli, "validate_command", record("validate"))
    monkeypatch.setattr(cli, "fit_score_params_command", record("fit-score-params"))
    monkeypatch.setattr(cli, "train_goal_bridge_command", record("train-goal-bridge"))
    monkeypatch.setattr(cli, "group_reports_command", record("group-reports"))
    monkeypatch.setattr(cli, "simulate_groups_command", record("simulate-groups"))
    monkeypatch.setattr(cli, "simulate_tournament_command", record("simulate-tournament"))
    monkeypatch.setattr(cli, "run_sensitivity_command", record("run-sensitivity"))
    monkeypatch.setattr(cli, "build_decision_report_command", record("build-decision-report"))

    result = cli.main(
        [
            "run-all",
            "--base-data",
            "base-data",
            "--processed",
            "data/processed",
            "--manual",
            "data/manual",
            "--out",
            "outputs",
            "--simulations",
            "123",
            "--group-simulations",
            "45",
            "--sensitivity-simulations",
            "67",
            "--seed",
            "2026",
            "--value-threshold",
            "0.07",
        ]
    )

    assert result == 0
    assert [call[0] for call in calls] == [
        "build-data",
        "validate",
        "fit-score-params",
        "train-goal-bridge",
        "group-reports",
        "simulate-groups",
        "simulate-tournament",
        "run-sensitivity",
        "build-decision-report",
    ]
    assert calls[0][1] == (Path("base-data"), Path("data/processed"), Path("data/manual"))
    assert calls[5][1] == (Path("data/processed"), Path("outputs"), 45, 2026)
    assert calls[6][1][2:5] == (Path("outputs"), 123, 2026)
    assert calls[7][1] == (Path("data/processed"), Path("data/manual"), Path("outputs/sensitivity"), 67, 2026, 0.07)


def test_run_all_stops_on_first_failed_step(monkeypatch: pytest.MonkeyPatch) -> None:
    calls: list[str] = []

    def passing_step(*args: object, **kwargs: object) -> int:
        calls.append("build-data")
        return 0

    def failing_step(*args: object, **kwargs: object) -> int:
        calls.append("validate")
        return 1

    def unexpected_step(*args: object, **kwargs: object) -> int:
        raise AssertionError("run-all should stop after a failed step")

    monkeypatch.setattr(cli, "build_data_command", passing_step)
    monkeypatch.setattr(cli, "validate_command", failing_step)
    monkeypatch.setattr(cli, "fit_score_params_command", unexpected_step)

    result = cli.main(["run-all"])

    assert result == 1
    assert calls == ["build-data", "validate"]
