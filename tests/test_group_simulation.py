import csv
from pathlib import Path

from wc2026bet.group_simulation import simulate_group_stage
from wc2026bet.processed import build_processed_data


def test_simulate_group_stage_writes_group_reports(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_dir = work_dir / "outputs"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    _write_score_params(processed_dir)

    counts = simulate_group_stage(processed_dir, output_dir, simulations=200, seed=1234)

    assert counts == {
        "group_goals": 12,
        "team_group": 48,
        "stadium_group": 16,
        "opta_calibration": 48,
        "opta_standings_calibration": 48,
        "opta_third_place_snapshot": 12,
    }
    group_rows = _read_rows(output_dir / "group-goals.csv")
    team_rows = _read_rows(output_dir / "team-group.csv")
    opta_rows = _read_rows(output_dir / "opta-calibration.csv")
    opta_standings_rows = _read_rows(output_dir / "opta-standings-calibration.csv")
    third_rows = _read_rows(output_dir / "opta-third-place-snapshot.csv")
    assert all(row["p05"] for row in group_rows)
    assert all(0.0 <= float(row["expected_points"]) <= 9.0 for row in team_rows)
    assert all(0.0 <= float(row["prob_l32"]) <= 1.0 for row in team_rows)
    assert all(row["diff_l32"] for row in opta_rows)
    assert len(opta_standings_rows) == 48
    assert len(third_rows) == 12
    assert all(row["diff_xpts"] for row in opta_standings_rows)


def test_simulate_group_stage_is_seed_reproducible(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_a = work_dir / "outputs-a"
    output_b = work_dir / "outputs-b"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    _write_score_params(processed_dir)

    simulate_group_stage(processed_dir, output_a, simulations=100, seed=2026)
    simulate_group_stage(processed_dir, output_b, simulations=100, seed=2026)

    assert (output_a / "team-group.csv").read_text(encoding="utf-8") == (output_b / "team-group.csv").read_text(
        encoding="utf-8"
    )


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_score_params(processed_dir: Path) -> None:
    matches = [row for row in _read_rows(processed_dir / "matches.csv") if row["is_group_stage"] == "true"]
    rows = [
        {
            "match_id": row["match_id"],
            "lambda_home": "1.4",
            "lambda_away": "1.1",
            "weighted_rmse": "0.1",
            "max_abs_error": "0.05",
            "low_confidence": "false",
            "bridge_weight": "1.0",
        }
        for row in matches
    ]
    with (processed_dir / "match_score_params.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
