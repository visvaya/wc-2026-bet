from pathlib import Path

from synthetic_data import write_rows
from wc2026bet.csv_io import read_csv
from wc2026bet.reports import build_group_stage_reports


def test_build_group_stage_reports_writes_expected_aggregates(tmp_path: Path) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_dir = work_dir / "outputs"
    processed_dir.mkdir()
    write_rows(
        processed_dir / "matches.csv",
        [
            {
                "match_id": "1",
                "phase": "Group",
                "group": "A",
                "date": "2026-06-11",
                "team_home": "Mexico",
                "team_away": "South Africa",
                "slot_home": "",
                "slot_away": "",
                "stadium_fifa": "Estadio Azteca Mexico City",
                "is_group_stage": "true",
            }
        ],
    )
    write_rows(
        processed_dir / "match_score_params.csv",
        [
            {
                "match_id": "1",
                "lambda_home": "1.5",
                "lambda_away": "1.0",
                "weighted_rmse": "0.1",
                "max_abs_error": "0.05",
                "low_confidence": "false",
                "bridge_weight": "1.0",
            }
        ],
    )
    write_rows(
        processed_dir / "score_model_config.csv",
        [
            {
                "max_goals": "10",
                "total_dispersion_tilt": "0.000000",
                "btts_correlation_tilt": "0.000000",
                "weighted_rmse": "0.100000",
                "max_abs_error": "0.050000",
                "unique_market_shapes": "1",
            }
        ],
    )

    counts = build_group_stage_reports(processed_dir, output_dir)

    assert counts == {
        "group_goals": 1,
        "team_group": 2,
        "stadium_group": 1,
    }
    group_rows = read_csv(output_dir / "group-goals.csv")
    team_rows = read_csv(output_dir / "team-group.csv")
    stadium_rows = read_csv(output_dir / "stadium-group-ranking.csv")
    assert group_rows[0]["expected_goals"] == "2.500000"
    assert {row["team"] for row in team_rows} == {"Mexico", "South Africa"}
    assert all(row["expected_points"] for row in team_rows)
    assert stadium_rows[0]["expected_average_goals"] == "2.500000"
