import csv
from pathlib import Path

import pytest

from wc2026bet.bridge import load_rating_goal_bridge, train_rating_goal_bridge
from wc2026bet.csv_io import read_csv
from wc2026bet.processed import build_processed_data


@pytest.mark.slow
def test_train_rating_goal_bridge_writes_model_files(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    _write_score_params(processed_dir)

    bridge = train_rating_goal_bridge(processed_dir)
    loaded = load_rating_goal_bridge(processed_dir)

    strengths = read_csv(processed_dir / "team_goal_strengths.csv")
    model = read_csv(processed_dir / "rating_goal_bridge.csv")
    first_match = read_csv(processed_dir / "matches.csv")[0]
    home_lambda, away_lambda = loaded.predict_lambdas(first_match["team_home"], first_match["team_away"])
    assert len(strengths) == 48
    assert len(model) == 1
    assert bridge.observations == 144
    assert loaded.observations == 144
    assert 0.15 <= home_lambda <= 5.5
    assert 0.15 <= away_lambda <= 5.5


@pytest.mark.slow
def test_rating_goal_bridge_downweights_low_confidence_rows(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    _write_score_params(processed_dir, first_bridge_weight="0.10")

    train_rating_goal_bridge(processed_dir)

    model = read_csv(processed_dir / "rating_goal_bridge.csv")[0]
    assert int(model["observations"]) == 144
    assert float(model["training_rmse"]) >= 0.0


def _write_score_params(processed_dir: Path, first_bridge_weight: str = "1.0") -> None:
    matches = [row for row in read_csv(processed_dir / "matches.csv") if row["is_group_stage"] == "true"]
    rows = []
    for index, row in enumerate(matches):
        rows.append(
            {
                "match_id": row["match_id"],
                "lambda_home": "1.4",
                "lambda_away": "1.1",
                "weighted_rmse": "0.1",
                "max_abs_error": "0.05",
                "low_confidence": "false",
                "bridge_weight": first_bridge_weight if index == 0 else "1.0",
            }
        )
    with (processed_dir / "match_score_params.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
