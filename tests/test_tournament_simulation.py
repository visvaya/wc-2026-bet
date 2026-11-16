from pathlib import Path

import pytest

from synthetic_data import write_score_config, write_score_params
from wc2026bet.bridge import train_rating_goal_bridge
from wc2026bet.csv_io import read_csv
from wc2026bet.processed import build_processed_data
from wc2026bet.tournament_report import compute_effective_sample_size, stadium_average_rows
from wc2026bet.tournament_simulation import simulate_tournament

# Reports round probabilities to 6 decimals, so each row may be off by half a unit in the last place.
_ROUNDING_TOLERANCE = 5e-7


@pytest.mark.slow
def test_simulate_tournament_writes_stadium_and_team_reports(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_dir = work_dir / "outputs"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    write_score_params(processed_dir)
    write_score_config(processed_dir)
    train_rating_goal_bridge(processed_dir)

    counts = simulate_tournament(
        processed_dir,
        synthetic_manual_data,
        output_dir,
        simulations=40,
        seed=1234,
    )

    assert counts == {
        "stadium_average": 16,
        "stadium_total": 16,
        "team_tournament": 48,
    }
    average_rows = read_csv(output_dir / "stadium-average-ranking.csv")
    total_rows = read_csv(output_dir / "stadium-total-ranking.csv")
    team_rows = read_csv(output_dir / "team-tournament.csv")
    assert set(average_rows[0]) == {
        "stadium_fifa",
        "scheduled_matches",
        "expected_average_goals",
        "p05",
        "p25",
        "p50",
        "p75",
        "p95",
        "prob_highest_average",
        "mc_error",
        "fair_odds",
        "bookmaker_odds",
        "ev",
    }
    assert sum(float(row["prob_highest_average"]) for row in average_rows) == pytest.approx(
        1.0, abs=_ROUNDING_TOLERANCE * len(average_rows)
    )
    assert sum(float(row["prob_highest_total"]) for row in total_rows) == pytest.approx(
        1.0, abs=_ROUNDING_TOLERANCE * len(total_rows)
    )
    assert all(0.0 <= float(row["prob_champion"]) <= 1.0 for row in team_rows)
    assert (output_dir / "tournament-summary.md").exists()


@pytest.mark.slow
def test_simulate_tournament_is_seed_reproducible(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    output_a = work_dir / "outputs-a"
    output_b = work_dir / "outputs-b"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    write_score_params(processed_dir)
    write_score_config(processed_dir)
    train_rating_goal_bridge(processed_dir)

    simulate_tournament(processed_dir, synthetic_manual_data, output_a, simulations=25, seed=2026)
    simulate_tournament(processed_dir, synthetic_manual_data, output_b, simulations=25, seed=2026)

    assert (output_a / "stadium-average-ranking.csv").read_text(encoding="utf-8") == (
        output_b / "stadium-average-ranking.csv"
    ).read_text(encoding="utf-8")


@pytest.mark.slow
def test_simulate_tournament_supports_opta_reweighting(
    tmp_path: Path, synthetic_base_data: Path, synthetic_manual_data: Path
) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    baseline_output = work_dir / "baseline"
    calibrated_output = work_dir / "calibrated"
    build_processed_data(synthetic_base_data, processed_dir, synthetic_manual_data)
    write_score_params(processed_dir)
    write_score_config(processed_dir)
    train_rating_goal_bridge(processed_dir)
    simulate_tournament(processed_dir, synthetic_manual_data, baseline_output, simulations=30, seed=2026)

    simulate_tournament(
        processed_dir,
        synthetic_manual_data,
        calibrated_output,
        simulations=30,
        seed=2026,
        calibration_model="opta_reweight",
        baseline_probabilities_path=baseline_output / "team-tournament.csv",
    )

    average_rows = read_csv(calibrated_output / "stadium-average-ranking.csv")
    diagnostics = read_csv(calibrated_output / "calibration-diagnostics.csv")
    assert sum(float(row["prob_highest_average"]) for row in average_rows) == pytest.approx(
        1.0, abs=_ROUNDING_TOLERANCE * len(average_rows)
    )
    assert diagnostics[0]["calibration_model"] == "opta_reweight"
    assert float(diagnostics[0]["effective_sample_size"]) > 0.0


def test_stadium_average_rows_use_effective_sample_size_for_mc_error() -> None:
    values = {
        "A": [(2.0, 1.0), (4.0, 9.0)],
        "B": [(1.0, 1.0), (3.0, 9.0)],
    }
    sample_size = compute_effective_sample_size(values)

    rows = stadium_average_rows(
        values,
        {"A": 5.0, "B": 5.0},
        {"A": 4, "B": 4},
        {"A": 3.0, "B": 4.0},
        sample_size,
        10.0,
    )

    assert float(rows[0]["mc_error"]) == round((0.5 * 0.5 / sample_size) ** 0.5, 6)
    assert float(rows[0]["mc_error"]) > round((0.5 * 0.5 / 2) ** 0.5, 6)
