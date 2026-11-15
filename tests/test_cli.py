from pathlib import Path

from wc2026bet import cli


def test_run_all_executes_pipeline_in_order(monkeypatch) -> None:
    calls = []

    def record(name, return_value=0):
        def inner(*args, **kwargs):
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


def test_run_all_stops_on_first_failed_step(monkeypatch) -> None:
    calls = []

    def passing_step(*args, **kwargs):
        calls.append("build-data")
        return 0

    def failing_step(*args, **kwargs):
        calls.append("validate")
        return 1

    def unexpected_step(*args, **kwargs):
        raise AssertionError("run-all should stop after a failed step")

    monkeypatch.setattr(cli, "build_data_command", passing_step)
    monkeypatch.setattr(cli, "validate_command", failing_step)
    monkeypatch.setattr(cli, "fit_score_params_command", unexpected_step)

    result = cli.main(["run-all"])

    assert result == 1
    assert calls == ["build-data", "validate"]
