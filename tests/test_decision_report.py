from pathlib import Path

from synthetic_data import write_rows, write_score_config, write_score_params
from wc2026bet.bridge import train_rating_goal_bridge
from wc2026bet.decision_report import build_decision_report
from wc2026bet.processed import build_processed_data
from wc2026bet.tournament_simulation import simulate_tournament


def test_build_decision_report_includes_value_verdict_and_diagnostics(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_dir = work_dir / "outputs"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    write_score_params(processed_dir)
    write_score_config(processed_dir)
    train_rating_goal_bridge(processed_dir)
    simulate_tournament(processed_dir, synthetic_manual_data, output_dir, simulations=35, seed=123)
    write_rows(
        output_dir / "opta-standings-calibration.csv",
        [
            {
                "team": "Team A1",
                "group": "A",
                "model_expected_points": "5.000000",
                "opta_xpts": "5.500000",
                "diff_xpts": "-0.500000",
                "model_prob_l32": "0.900000",
                "opta_qual": "0.850000",
                "diff_qual": "0.050000",
                "model_prob_third_place": "0.100000",
                "model_prob_best_third": "0.080000",
            }
        ],
    )
    (output_dir / "sensitivity").mkdir()
    write_rows(
        output_dir / "sensitivity" / "opta-calibration-impact.csv",
        [
            {
                "stadium_fifa": "Houston Stadium",
                "baseline_probability": "0.100000",
                "opta_calibrated_probability": "0.120000",
                "delta_probability": "0.020000",
                "baseline_ev": "-0.350000",
                "opta_calibrated_ev": "-0.220000",
            }
        ],
    )

    count = build_decision_report(
        processed_dir,
        output_dir,
        output_dir / "decision.md",
        simulations=35,
        seed=123,
        extra_time_goal_multiplier=0.30,
        penalty_model="coin_flip",
        value_threshold=999.0,
    )

    report = (output_dir / "decision.md").read_text(encoding="utf-8")
    assert count == 1
    assert "No value bet" in report
    assert "Source Snapshots" in report
    assert "Model Diagnostics" in report
    assert "Highest Average Goals Market" in report
    assert "Highest Total Goals Cross-Check" in report
    assert "Opta Standings Calibration" in report
    assert "Opta-Calibrated Sensitivity" in report
