from pathlib import Path

from synthetic_data import write_score_config, write_score_params
from wc2026bet.bridge import train_rating_goal_bridge
from wc2026bet.csv_io import read_csv
from wc2026bet.processed import build_processed_data
from wc2026bet.sensitivity import run_sensitivity


def test_run_sensitivity_writes_scenario_outputs_and_aggregate(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_dir = work_dir / "outputs" / "sensitivity"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    write_score_params(processed_dir)
    write_score_config(processed_dir)
    train_rating_goal_bridge(processed_dir)

    counts = run_sensitivity(
        processed_dir,
        synthetic_manual_data,
        output_dir,
        simulations=12,
        seed=2026,
    )

    aggregate = read_csv(output_dir / "stadium-average-sensitivity.csv")
    impact = read_csv(output_dir / "opta-calibration-impact.csv")
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
