from pathlib import Path

import pytest

from synthetic_data import odds_for, write_rows
from wc2026bet.csv_io import read_csv
from wc2026bet.fitting import fit_group_match_params, fit_match_from_market_odds, read_score_model_config
from wc2026bet.processed import write_odds_template


def test_fit_match_from_market_odds_recovers_reasonable_lambdas() -> None:
    result = fit_match_from_market_odds(
        {
            "1X2": {"home": 2.10, "draw": 3.40, "away": 3.90},
            "over_under_0_5": {"over": 1.07, "under": 8.80},
            "over_under_1_5": {"over": 1.38, "under": 3.05},
            "over_under_2_5": {"over": 2.15, "under": 1.72},
            "btts": {"yes": 1.95, "no": 1.95},
        }
    )

    assert 0.5 < result.lambda_home < 2.5
    assert 0.5 < result.lambda_away < 2.5
    assert result.weighted_rmse < 0.8
    assert 0.0 < result.bridge_weight <= 1.0


@pytest.mark.slow
def test_fit_group_match_params_writes_one_row_per_group_match(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    manual_dir = work_dir / "manual"
    processed_dir = work_dir / "processed"
    manual_dir.mkdir()
    processed_dir.mkdir()
    odds_path = manual_dir / "odds.csv"
    write_odds_template(synthetic_base_data, odds_path)

    rows = read_csv(odds_path)
    for row in rows:
        row["decimal_odds"] = odds_for(row["market"], row["selection"])
        row["source_file"] = "manual-test"
        row["captured_at"] = "2026-06-09T12:00:00"
    write_rows(odds_path, rows)

    output_path = processed_dir / "match_score_params.csv"
    config_path = processed_dir / "score_model_config.csv"
    count = fit_group_match_params(synthetic_base_data, odds_path, output_path, config_output_path=config_path)

    output_rows = read_csv(output_path)
    config = read_score_model_config(config_path)
    assert count == 72
    assert len(output_rows) == 72
    assert config.max_goals == 10
    assert config.unique_market_shapes == 1
    assert set(output_rows[0]) == {
        "match_id",
        "lambda_home",
        "lambda_away",
        "weighted_rmse",
        "max_abs_error",
        "low_confidence",
        "bridge_weight",
    }
