"""Build deterministic group-stage reports from fitted match parameters."""

from __future__ import annotations

from collections import defaultdict
from pathlib import Path

from wc2026bet.csv_io import fmt, read_csv, write_csv
from wc2026bet.fitting import read_score_model_config
from wc2026bet.score_grid import ScoreGrid

GROUP_GOALS_FIELDS = ("group", "expected_goals", "p05", "p50", "p95")
TEAM_GROUP_FIELDS = ("team", "group", "expected_points", "expected_gf", "expected_ga", "expected_gd")
STADIUM_GROUP_FIELDS = (
    "stadium_fifa",
    "scheduled_group_matches",
    "expected_total_goals",
    "expected_average_goals",
)


def build_group_stage_reports(processed_dir: Path, output_dir: Path) -> dict[str, int]:
    """Write group-stage goal aggregates using fitted lambdas."""

    matches = {
        row["match_id"]: row for row in read_csv(processed_dir / "matches.csv") if row["is_group_stage"] == "true"
    }
    params = {row["match_id"]: row for row in read_csv(processed_dir / "match_score_params.csv")}
    score_config = read_score_model_config(processed_dir / "score_model_config.csv")
    missing = sorted(set(matches) - set(params), key=int)
    if missing:
        raise ValueError(f"Missing score params for group matches: {', '.join(missing[:5])}")

    group_totals: dict[str, float] = defaultdict(float)
    team_rows: dict[tuple[str, str], dict[str, float | str]] = {}
    stadium_totals: dict[str, float] = defaultdict(float)
    stadium_counts: dict[str, int] = defaultdict(int)

    for match_id, match in matches.items():
        param = params[match_id]
        lambda_home = float(param["lambda_home"])
        lambda_away = float(param["lambda_away"])
        grid = ScoreGrid(
            lambda_home,
            lambda_away,
            max_goals=score_config.max_goals,
            total_dispersion_tilt=score_config.total_dispersion_tilt,
            btts_correlation_tilt=score_config.btts_correlation_tilt,
        )
        result_probabilities = grid.result_probabilities()
        total_goals = lambda_home + lambda_away
        group = match["group"]
        home = match["team_home"]
        away = match["team_away"]
        stadium = match["stadium_fifa"]

        group_totals[group] += total_goals
        _add_team_projection(
            team_rows,
            home,
            group,
            3.0 * result_probabilities["home"] + result_probabilities["draw"],
            lambda_home,
            lambda_away,
        )
        _add_team_projection(
            team_rows,
            away,
            group,
            3.0 * result_probabilities["away"] + result_probabilities["draw"],
            lambda_away,
            lambda_home,
        )
        stadium_totals[stadium] += total_goals
        stadium_counts[stadium] += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    group_rows = [
        {
            "group": group,
            "expected_goals": fmt(total),
            "p05": "",
            "p50": "",
            "p95": "",
        }
        for group, total in sorted(group_totals.items())
    ]
    team_output_rows = [
        {
            "team": str(row["team"]),
            "group": str(row["group"]),
            "expected_points": fmt(float(row["expected_points"])),
            "expected_gf": fmt(float(row["expected_gf"])),
            "expected_ga": fmt(float(row["expected_ga"])),
            "expected_gd": fmt(float(row["expected_gf"]) - float(row["expected_ga"])),
        }
        for row in sorted(team_rows.values(), key=lambda item: (str(item["group"]), str(item["team"])))
    ]
    stadium_rows = [
        {
            "stadium_fifa": stadium,
            "scheduled_group_matches": str(stadium_counts[stadium]),
            "expected_total_goals": fmt(total),
            "expected_average_goals": fmt(total / stadium_counts[stadium]),
        }
        for stadium, total in sorted(
            stadium_totals.items(),
            key=lambda item: (-(item[1] / stadium_counts[item[0]]), item[0]),
        )
    ]

    write_csv(output_dir / "group-goals.csv", GROUP_GOALS_FIELDS, group_rows)
    write_csv(output_dir / "team-group.csv", TEAM_GROUP_FIELDS, team_output_rows)
    write_csv(output_dir / "stadium-group-ranking.csv", STADIUM_GROUP_FIELDS, stadium_rows)
    return {
        "group_goals": len(group_rows),
        "team_group": len(team_output_rows),
        "stadium_group": len(stadium_rows),
    }


def _add_team_projection(
    rows: dict[tuple[str, str], dict[str, float | str]],
    team: str,
    group: str,
    expected_points: float,
    goals_for: float,
    goals_against: float,
) -> None:
    key = (team, group)
    if key not in rows:
        rows[key] = {
            "team": team,
            "group": group,
            "expected_points": 0.0,
            "expected_gf": 0.0,
            "expected_ga": 0.0,
        }
    rows[key]["expected_points"] = float(rows[key]["expected_points"]) + expected_points
    rows[key]["expected_gf"] = float(rows[key]["expected_gf"]) + goals_for
    rows[key]["expected_ga"] = float(rows[key]["expected_ga"]) + goals_against
