import csv
from pathlib import Path

from wc2026bet.bridge import train_rating_goal_bridge
from wc2026bet.processed import build_processed_data
from wc2026bet.sensitivity import run_sensitivity


def test_run_sensitivity_writes_scenario_outputs_and_aggregate(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_dir = work_dir / "outputs" / "sensitivity"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    _write_score_params(processed_dir)
    _write_score_config(processed_dir)
    train_rating_goal_bridge(processed_dir)

    counts = run_sensitivity(
        processed_dir,
        synthetic_manual_data,
        output_dir,
        simulations=12,
        seed=2026,
    )

    aggregate = _read_rows(output_dir / "stadium-average-sensitivity.csv")
    impact = _read_rows(output_dir / "opta-calibration-impact.csv")
    assert counts == {
        "scenarios": 6,
        "stadium_average_sensitivity": 16,
        "opta_calibration_impact": 16,
    }
    assert len(aggregate) == 16
    assert len(impact) == 16
    assert (output_dir / "baseline" / "stadium-average-ranking.csv").exists()
    assert (output_dir / "no_global_tilts" / "stadium-average-ranking.csv").exists()
    assert (output_dir / "opta_calibrated" / "calibration-diagnostics.csv").exists()
    assert set(aggregate[0]) == {
        "stadium_fifa",
        "baseline_probability",
        "min_probability",
        "max_probability",
        "min_fair_odds",
        "max_fair_odds",
        "min_ev",
        "max_ev",
        "stable_top_candidate",
    }


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


def _write_score_config(processed_dir: Path) -> None:
    rows = [
        {
            "max_goals": "10",
            "total_dispersion_tilt": "0.000000",
            "btts_correlation_tilt": "0.000000",
            "weighted_rmse": "0.100000",
            "max_abs_error": "0.050000",
            "unique_market_shapes": "1",
        }
    ]
    with (processed_dir / "score_model_config.csv").open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
