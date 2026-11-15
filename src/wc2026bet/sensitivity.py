"""Sensitivity scenarios for the stadium average-goals market."""

from __future__ import annotations

import csv
from dataclasses import dataclass
from pathlib import Path

from wc2026bet.tournament_simulation import simulate_tournament

SENSITIVITY_FIELDS = (
    "stadium_fifa",
    "baseline_probability",
    "min_probability",
    "max_probability",
    "min_fair_odds",
    "max_fair_odds",
    "min_ev",
    "max_ev",
    "stable_top_candidate",
)
OPTA_CALIBRATION_IMPACT_FIELDS = (
    "stadium_fifa",
    "baseline_probability",
    "opta_calibrated_probability",
    "delta_probability",
    "baseline_ev",
    "opta_calibrated_ev",
)


@dataclass(frozen=True)
class SensitivityScenario:
    name: str
    extra_time_goal_multiplier: float = 0.30
    penalty_model: str = "coin_flip"
    use_score_tilts: bool = True
    calibration_model: str = "none"


DEFAULT_SCENARIOS = (
    SensitivityScenario("baseline"),
    SensitivityScenario("extra_time_0_20", extra_time_goal_multiplier=0.20),
    SensitivityScenario("extra_time_0_40", extra_time_goal_multiplier=0.40),
    SensitivityScenario("rating_weighted_penalties", penalty_model="rating_weighted"),
    SensitivityScenario("no_global_tilts", use_score_tilts=False),
    SensitivityScenario("opta_calibrated", calibration_model="opta_reweight"),
)


def run_sensitivity(
    processed_dir: Path,
    manual_dir: Path,
    output_dir: Path,
    *,
    simulations: int = 50_000,
    seed: int = 20260610,
    value_threshold: float = 0.05,
) -> dict[str, int]:
    """Run sensitivity scenarios and write an aggregate stadium range CSV."""

    if simulations <= 0:
        raise ValueError("simulations must be positive")

    output_dir.mkdir(parents=True, exist_ok=True)
    scenario_rows: dict[str, list[dict[str, str]]] = {}
    baseline_probabilities_path: Path | None = None
    for scenario in DEFAULT_SCENARIOS:
        scenario_dir = output_dir / scenario.name
        simulate_tournament(
            processed_dir,
            manual_dir,
            scenario_dir,
            simulations=simulations,
            seed=seed,
            extra_time_goal_multiplier=scenario.extra_time_goal_multiplier,
            penalty_model=scenario.penalty_model,
            use_score_tilts=scenario.use_score_tilts,
            value_threshold=value_threshold,
            calibration_model=scenario.calibration_model,
            baseline_probabilities_path=baseline_probabilities_path,
        )
        if scenario.name == "baseline":
            baseline_probabilities_path = scenario_dir / "team-tournament.csv"
        scenario_rows[scenario.name] = _read_csv(scenario_dir / "stadium-average-ranking.csv")

    aggregate_rows = _aggregate_sensitivity(scenario_rows)
    aggregate_path = output_dir / "stadium-average-sensitivity.csv"
    _write_csv(aggregate_path, SENSITIVITY_FIELDS, aggregate_rows)
    impact_rows = _opta_calibration_impact_rows(scenario_rows)
    _write_csv(output_dir / "opta-calibration-impact.csv", OPTA_CALIBRATION_IMPACT_FIELDS, impact_rows)
    return {
        "scenarios": len(DEFAULT_SCENARIOS),
        "stadium_average_sensitivity": len(aggregate_rows),
        "opta_calibration_impact": len(impact_rows),
    }


def _aggregate_sensitivity(
    scenario_rows: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    baseline = {row["stadium_fifa"]: row for row in scenario_rows["baseline"]}
    top_stadiums = {rows[0]["stadium_fifa"] for rows in scenario_rows.values()}
    rows = []
    for stadium, baseline_row in baseline.items():
        stadium_rows = [rows_by_scenario[stadium] for rows_by_scenario in _indexed_rows(scenario_rows).values()]
        probabilities = [float(row["prob_highest_average"]) for row in stadium_rows]
        fair_odds = [float(row["fair_odds"]) for row in stadium_rows if row["fair_odds"]]
        ev_values = [float(row["ev"]) for row in stadium_rows if row["ev"]]
        rows.append(
            {
                "stadium_fifa": stadium,
                "baseline_probability": baseline_row["prob_highest_average"],
                "min_probability": _fmt(min(probabilities)),
                "max_probability": _fmt(max(probabilities)),
                "min_fair_odds": _fmt(min(fair_odds)) if fair_odds else "",
                "max_fair_odds": _fmt(max(fair_odds)) if fair_odds else "",
                "min_ev": _fmt(min(ev_values)) if ev_values else "",
                "max_ev": _fmt(max(ev_values)) if ev_values else "",
                "stable_top_candidate": "true" if top_stadiums == {stadium} else "false",
            }
        )
    return sorted(rows, key=lambda row: (-float(row["baseline_probability"]), row["stadium_fifa"]))


def _opta_calibration_impact_rows(
    scenario_rows: dict[str, list[dict[str, str]]],
) -> list[dict[str, str]]:
    if "opta_calibrated" not in scenario_rows:
        return []
    baseline = {row["stadium_fifa"]: row for row in scenario_rows["baseline"]}
    calibrated = {row["stadium_fifa"]: row for row in scenario_rows["opta_calibrated"]}
    rows = []
    for stadium, baseline_row in baseline.items():
        calibrated_row = calibrated[stadium]
        baseline_probability = float(baseline_row["prob_highest_average"])
        calibrated_probability = float(calibrated_row["prob_highest_average"])
        rows.append(
            {
                "stadium_fifa": stadium,
                "baseline_probability": baseline_row["prob_highest_average"],
                "opta_calibrated_probability": calibrated_row["prob_highest_average"],
                "delta_probability": _fmt(calibrated_probability - baseline_probability),
                "baseline_ev": baseline_row["ev"],
                "opta_calibrated_ev": calibrated_row["ev"],
            }
        )
    return sorted(rows, key=lambda row: (-abs(float(row["delta_probability"])), row["stadium_fifa"]))


def _indexed_rows(
    scenario_rows: dict[str, list[dict[str, str]]],
) -> dict[str, dict[str, dict[str, str]]]:
    return {scenario: {row["stadium_fifa"]: row for row in rows} for scenario, rows in scenario_rows.items()}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _fmt(value: float) -> str:
    return f"{value:.6f}"
