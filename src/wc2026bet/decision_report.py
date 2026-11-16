"""Decision-oriented markdown reporting for tournament simulations."""

from __future__ import annotations

from collections.abc import Iterable, Mapping
from pathlib import Path

from wc2026bet.csv_io import read_csv


def build_decision_report(
    processed_dir: Path,
    output_dir: Path,
    output_path: Path,
    *,
    simulations: int,
    seed: int,
    extra_time_goal_multiplier: float,
    penalty_model: str,
    value_threshold: float = 0.05,
) -> int:
    """Build a markdown report with provenance, diagnostics, and value verdict."""

    average_rows = read_csv(output_dir / "stadium-average-ranking.csv")
    total_rows = read_csv(output_dir / "stadium-total-ranking.csv")
    score_config = _single_row(processed_dir / "score_model_config.csv")
    bridge = _single_row(processed_dir / "rating_goal_bridge.csv")
    match_params = read_csv(processed_dir / "match_score_params.csv")
    source_rows = _source_rows(processed_dir)
    value_rows = [
        row for row in average_rows if _float_or_none(row["ev"]) is not None and float(row["ev"]) >= value_threshold
    ]
    opta_rows = read_csv(output_dir / "opta-calibration.csv") if (output_dir / "opta-calibration.csv").exists() else []
    opta_standing_path = output_dir / "opta-standings-calibration.csv"
    opta_standing_rows = read_csv(opta_standing_path) if opta_standing_path.exists() else []
    sensitivity_path = output_dir / "sensitivity" / "stadium-average-sensitivity.csv"
    sensitivity_rows = read_csv(sensitivity_path) if sensitivity_path.exists() else []
    opta_impact_path = output_dir / "sensitivity" / "opta-calibration-impact.csv"
    opta_impact_rows = read_csv(opta_impact_path) if opta_impact_path.exists() else []

    lines = [
        "# Tournament Betting Decision Report",
        "",
        "## Verdict",
        "",
        _value_verdict(value_rows, value_threshold),
        "",
        "## Simulation Setup",
        "",
        f"- simulations: {simulations}",
        f"- seed: {seed}",
        f"- extra_time_goal_multiplier: {extra_time_goal_multiplier:.2f}",
        f"- penalty_model: {penalty_model}",
        "- market: highest average goals by stadium",
        "- settlement: extra-time goals included; penalty shoot-out goals excluded",
        "- group tie-break simplification: points, goal difference, goals for, seeded random fallback",
        "",
        "## Source Snapshots",
        "",
        "| Dataset | Source files | Captured at |",
        "| --- | --- | --- |",
    ]
    lines.extend(f"| {row['dataset']} | {row['source_files']} | {row['captured_at']} |" for row in source_rows)
    lines.extend(
        [
            "",
            "## Model Diagnostics",
            "",
            f"- score_grid_max_goals: {score_config['max_goals']}",
            f"- total_dispersion_tilt: {score_config['total_dispersion_tilt']}",
            f"- btts_correlation_tilt: {score_config['btts_correlation_tilt']}",
            f"- score_grid_weighted_rmse: {score_config['weighted_rmse']}",
            f"- score_grid_max_abs_error: {score_config['max_abs_error']}",
            f"- low_confidence_matches: {_low_confidence_count(match_params)} / {len(match_params)}",
            f"- bridge_ridge_alpha: {bridge['ridge_alpha']}",
            f"- bridge_training_rmse: {bridge['training_rmse']}",
            f"- bridge_cv_rmse: {bridge['cv_rmse']}",
            f"- bridge_observations: {bridge['observations']}",
        ]
    )
    lines.extend(_warning_lines(match_params, score_config, bridge, opta_rows, opta_standing_rows))
    lines.extend(
        [
            "",
            "## Highest Average Goals Market",
            "",
            "| Stadium | P(highest avg) | MC error | Fair odds | Bookmaker odds | EV | Median avg | P05 | P95 |",
            "| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        _table_row(
            row,
            "stadium_fifa",
            "prob_highest_average",
            "mc_error",
            "fair_odds",
            "bookmaker_odds",
            "ev",
            "p50",
            "p05",
            "p95",
        )
        for row in average_rows[:8]
    )
    lines.extend(
        [
            "",
            "## Highest Total Goals Cross-Check",
            "",
            "| Stadium | P(highest total) | Expected total | Median total | P05 | P95 |",
            "| --- | ---: | ---: | ---: | ---: | ---: |",
        ]
    )
    lines.extend(
        "| {stadium_fifa} | {prob_highest_total} | {expected_total_goals} | {p50} | {p05} | {p95} |".format(**row)
        for row in total_rows[:5]
    )
    lines.extend(_opta_section(opta_rows))
    lines.extend(_opta_standings_section(opta_standing_rows))
    lines.extend(_sensitivity_section(sensitivity_rows))
    lines.extend(_opta_calibrated_sensitivity_section(opta_impact_rows, value_threshold))
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return 1


def _value_verdict(rows: list[dict[str, str]], value_threshold: float) -> str:
    if not rows:
        return f"No value bet: no stadium has EV >= {value_threshold:.2f} in the current snapshot."
    best = max(rows, key=lambda row: float(row["ev"]))
    return (
        "Value candidate: "
        f"{best['stadium_fifa']} has EV {best['ev']} at bookmaker odds {best['bookmaker_odds']} "
        f"against fair odds {best['fair_odds']}."
    )


def _source_rows(processed_dir: Path) -> list[dict[str, str]]:
    specs = (
        ("match odds", processed_dir / "odds.csv"),
        ("stadium market odds", processed_dir / "stadium_market_odds.csv"),
        ("Opta predictions", processed_dir / "opta_predictions.csv"),
        ("Opta standings", processed_dir / "opta_standings.csv"),
    )
    rows = []
    for dataset, path in specs:
        if not path.exists():
            continue
        source_rows = read_csv(path)
        rows.append(
            {
                "dataset": dataset,
                "source_files": _joined_unique(row.get("source_file", "") for row in source_rows),
                "captured_at": _joined_unique(row.get("captured_at", "") for row in source_rows),
            }
        )
    return rows


def _warning_lines(
    match_params: list[dict[str, str]],
    score_config: dict[str, str],
    bridge: dict[str, str],
    opta_rows: list[dict[str, str]],
    opta_standing_rows: list[dict[str, str]],
) -> list[str]:
    warnings = []
    if _low_confidence_count(match_params):
        warnings.append(
            f"- warning: {_low_confidence_count(match_params)} low-confidence score fits feed the bridge"
            " at reduced weight"
        )
    if float(score_config["max_abs_error"]) > 0.15:
        warnings.append("- warning: score-grid max_abs_error is elevated; inspect per-match fit before staking")
    if float(bridge["cv_rmse"]) > 0.20:
        warnings.append("- warning: bridge CV RMSE is elevated; KO lambdas may be unstable")
    opta_delta = _max_opta_delta(opta_rows)
    if opta_delta is not None and opta_delta >= 0.15:
        warnings.append(f"- warning: largest model-vs-Opta advancement delta is {opta_delta:.3f}")
    opta_xpts_delta = _max_abs_value(opta_standing_rows, "diff_xpts")
    if opta_xpts_delta is not None and opta_xpts_delta >= 0.75:
        warnings.append(f"- warning: largest model-vs-Opta xPTS delta is {opta_xpts_delta:.3f}")
    opta_qual_delta = _max_abs_value(opta_standing_rows, "diff_qual")
    if opta_qual_delta is not None and opta_qual_delta >= 0.15:
        warnings.append(f"- warning: largest model-vs-Opta standings QUAL delta is {opta_qual_delta:.3f}")
    if not warnings:
        warnings.append("- warning: no hard model guard is currently triggered")
    return ["", "## Warnings", "", *warnings]


def _opta_section(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return [
            "",
            "## Opta Calibration",
            "",
            "- Opta calibration output is unavailable; run simulate-groups to refresh it.",
        ]
    ranked = sorted(
        rows,
        key=lambda row: max(abs(float(row["diff_top_group"])), abs(float(row["diff_l32"]))),
        reverse=True,
    )[:5]
    lines = [
        "",
        "## Opta Calibration",
        "",
        "| Team | Top group diff | L32 diff |",
        "| --- | ---: | ---: |",
    ]
    lines.extend(f"| {row['team']} | {row['diff_top_group']} | {row['diff_l32']} |" for row in ranked)
    return lines


def _opta_standings_section(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return [
            "",
            "## Opta Standings Calibration",
            "",
            "- Opta standings calibration output is unavailable; run simulate-groups after build-data.",
        ]
    ranked = sorted(
        rows,
        key=lambda row: max(abs(float(row["diff_xpts"])), abs(float(row["diff_qual"]))),
        reverse=True,
    )[:8]
    lines = [
        "",
        "## Opta Standings Calibration",
        "",
        "- `3rd Place Ranking` is treated as a snapshot/diagnostic, not a full probability target.",
        "",
        "| Team | Group | Model xPTS | Opta xPTS | Diff xPTS | Model L32 | Opta QUAL | Diff QUAL |",
        "| --- | --- | ---: | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        _table_row(
            row,
            "team",
            "group",
            "model_expected_points",
            "opta_xpts",
            "diff_xpts",
            "model_prob_l32",
            "opta_qual",
            "diff_qual",
        )
        for row in ranked
    )
    return lines


def _sensitivity_section(rows: list[dict[str, str]]) -> list[str]:
    if not rows:
        return [
            "",
            "## Sensitivity",
            "",
            "- Sensitivity output is unavailable; run run-sensitivity to compare scenario ranges.",
        ]
    ranked = sorted(rows, key=lambda row: float(row["baseline_probability"]), reverse=True)[:8]
    lines = [
        "",
        "## Sensitivity",
        "",
        "| Stadium | Baseline P | Min P | Max P | Min fair odds | Max fair odds | EV range | Stable top |",
        "| --- | ---: | ---: | ---: | ---: | ---: | ---: | --- |",
    ]
    lines.extend(
        _table_row(
            {**row, "ev_range": f"{row['min_ev']}..{row['max_ev']}"},
            "stadium_fifa",
            "baseline_probability",
            "min_probability",
            "max_probability",
            "min_fair_odds",
            "max_fair_odds",
            "ev_range",
            "stable_top_candidate",
        )
        for row in ranked
    )
    return lines


def _opta_calibrated_sensitivity_section(
    rows: list[dict[str, str]],
    value_threshold: float,
) -> list[str]:
    if not rows:
        return [
            "",
            "## Opta-Calibrated Sensitivity",
            "",
            "- Opta-calibrated sensitivity output is unavailable; run run-sensitivity.",
        ]
    value_rows = [
        row for row in rows if row["opta_calibrated_ev"] and float(row["opta_calibrated_ev"]) >= value_threshold
    ]
    verdict = (
        f"No value bet under Opta reweighting: no stadium has EV >= {value_threshold:.2f}."
        if not value_rows
        else "Opta reweighting creates at least one value candidate."
    )
    ranked = sorted(rows, key=lambda row: abs(float(row["delta_probability"])), reverse=True)[:8]
    lines = [
        "",
        "## Opta-Calibrated Sensitivity",
        "",
        f"- {verdict}",
        "- This scenario reweights tournament paths toward Opta advancement probabilities"
        " without changing goal lambdas.",
        "",
        "| Stadium | Baseline P | Opta P | Delta P | Baseline EV | Opta EV |",
        "| --- | ---: | ---: | ---: | ---: | ---: |",
    ]
    lines.extend(
        _table_row(
            row,
            "stadium_fifa",
            "baseline_probability",
            "opta_calibrated_probability",
            "delta_probability",
            "baseline_ev",
            "opta_calibrated_ev",
        )
        for row in ranked
    )
    return lines


def _low_confidence_count(rows: list[dict[str, str]]) -> int:
    return sum(row.get("low_confidence", "").lower() == "true" for row in rows)


def _max_opta_delta(rows: list[dict[str, str]]) -> float | None:
    if not rows:
        return None
    return max(max(abs(float(row["diff_top_group"])), abs(float(row["diff_l32"]))) for row in rows)


def _max_abs_value(rows: list[dict[str, str]], field: str) -> float | None:
    if not rows:
        return None
    return max(abs(float(row[field])) for row in rows)


def _single_row(path: Path) -> dict[str, str]:
    rows = read_csv(path)
    if len(rows) != 1:
        raise ValueError(f"Expected one row in {path}, found {len(rows)}")
    return rows[0]


def _joined_unique(values: Iterable[object]) -> str:
    unique = sorted({str(value) for value in values if str(value)})
    return ", ".join(unique)


def _float_or_none(value: str) -> float | None:
    if value == "":
        return None
    return float(value)


def _table_row(row: Mapping[str, str], *columns: str) -> str:
    """One Markdown table row holding the given columns of a CSV row."""

    return "| " + " | ".join(row[column] for column in columns) + " |"
