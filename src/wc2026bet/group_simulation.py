"""Monte Carlo simulation for World Cup 2026 group-stage outputs."""

from __future__ import annotations

import random
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from wc2026bet.csv_io import fmt, read_csv, write_csv
from wc2026bet.fitting import read_score_model_config
from wc2026bet.group_table import ScoreSampler, apply_match, initial_table, table_sort_key

GROUP_GOALS_FIELDS = ("group", "expected_goals", "p05", "p50", "p95")
TEAM_GROUP_FIELDS = (
    "team",
    "group",
    "expected_points",
    "expected_gf",
    "expected_ga",
    "expected_gd",
    "prob_top_group",
    "prob_l32",
    "prob_third_place",
    "prob_best_third",
)
OPTA_STANDINGS_CALIBRATION_FIELDS = (
    "team",
    "group",
    "model_expected_points",
    "opta_xpts",
    "diff_xpts",
    "model_prob_l32",
    "opta_qual",
    "diff_qual",
    "model_prob_third_place",
    "model_prob_best_third",
)
OPTA_THIRD_PLACE_SNAPSHOT_FIELDS = (
    "team",
    "group",
    "opta_row_rank",
    "opta_raw_pos",
    "opta_xpts",
    "opta_qual",
    "model_prob_third_place",
    "model_prob_best_third",
    "model_prob_l32",
)
STADIUM_GROUP_FIELDS = (
    "stadium_fifa",
    "scheduled_group_matches",
    "expected_total_goals",
    "expected_average_goals",
)
OPTA_CALIBRATION_FIELDS = (
    "team",
    "model_prob_top_group",
    "opta_top_group",
    "diff_top_group",
    "model_prob_l32",
    "opta_l32",
    "diff_l32",
)


@dataclass
class TeamSimulationStats:
    team: str
    group: str
    points_total: int = 0
    gf_total: int = 0
    ga_total: int = 0
    top_group_count: int = 0
    l32_count: int = 0
    third_place_count: int = 0
    best_third_count: int = 0


def simulate_group_stage(
    processed_dir: Path,
    output_dir: Path,
    *,
    simulations: int = 50_000,
    seed: int = 20260610,
) -> dict[str, int]:
    """Run group-stage Monte Carlo and write aggregate reports."""

    if simulations <= 0:
        raise ValueError("simulations must be positive")

    matches = [row for row in read_csv(processed_dir / "matches.csv") if row["is_group_stage"] == "true"]
    params = {row["match_id"]: row for row in read_csv(processed_dir / "match_score_params.csv")}
    opta = {row["team"]: row for row in read_csv(processed_dir / "opta_predictions.csv")}
    opta_standings_path = processed_dir / "opta_standings.csv"
    opta_standings = read_csv(opta_standings_path) if opta_standings_path.exists() else []
    score_config = read_score_model_config(processed_dir / "score_model_config.csv")
    missing_params = sorted({match["match_id"] for match in matches} - set(params), key=int)
    if missing_params:
        raise ValueError(f"Missing score params for group matches: {', '.join(missing_params[:5])}")

    rng = random.Random(seed)  # noqa: S311 - seedable Monte Carlo sampling, not cryptography
    samplers = {
        match["match_id"]: ScoreSampler(
            float(params[match["match_id"]]["lambda_home"]),
            float(params[match["match_id"]]["lambda_away"]),
            max_goals=score_config.max_goals,
            total_dispersion_tilt=score_config.total_dispersion_tilt,
            btts_correlation_tilt=score_config.btts_correlation_tilt,
        )
        for match in matches
    }

    team_stats = _initial_team_stats(matches)
    group_goal_values: dict[str, list[int]] = defaultdict(list)
    stadium_totals: dict[str, int] = defaultdict(int)
    stadium_counts: dict[str, int] = defaultdict(int)

    for _ in range(simulations):
        table = initial_table(matches, rng)
        group_goals: dict[str, int] = defaultdict(int)

        for match in matches:
            home_goals, away_goals = samplers[match["match_id"]].sample(rng)
            home = match["team_home"]
            away = match["team_away"]
            group = match["group"]
            stadium = match["stadium_fifa"]
            apply_match(table[(group, home)], table[(group, away)], home_goals, away_goals)
            home_points, away_points = _match_points(home_goals, away_goals)
            team_stats[home].points_total += home_points
            team_stats[away].points_total += away_points
            group_goals[group] += home_goals + away_goals
            stadium_totals[stadium] += home_goals + away_goals
            stadium_counts[stadium] += 1
            team_stats[home].gf_total += home_goals
            team_stats[home].ga_total += away_goals
            team_stats[away].gf_total += away_goals
            team_stats[away].ga_total += home_goals

        third_rows = []
        for group in sorted({match["group"] for match in matches}):
            group_table = sorted(
                [row for (row_group, _), row in table.items() if row_group == group],
                key=table_sort_key,
                reverse=True,
            )
            team_stats[group_table[0].team].top_group_count += 1
            for row in group_table[:2]:
                team_stats[row.team].l32_count += 1
            team_stats[group_table[2].team].third_place_count += 1
            third_rows.append(group_table[2])
            group_goal_values[group].append(group_goals[group])

        best_thirds = sorted(third_rows, key=table_sort_key, reverse=True)[:8]
        for row in best_thirds:
            team_stats[row.team].best_third_count += 1
            team_stats[row.team].l32_count += 1

    output_dir.mkdir(parents=True, exist_ok=True)
    group_rows = _group_goal_rows(group_goal_values)
    team_rows = _team_group_rows(team_stats, simulations)
    stadium_rows = _stadium_rows(stadium_totals, stadium_counts, simulations)
    opta_rows = _opta_calibration_rows(team_rows, opta)
    opta_standing_rows = _opta_standings_calibration_rows(team_rows, opta_standings)
    opta_third_rows = _opta_third_place_snapshot_rows(team_rows, opta_standings)
    write_csv(output_dir / "group-goals.csv", GROUP_GOALS_FIELDS, group_rows)
    write_csv(output_dir / "team-group.csv", TEAM_GROUP_FIELDS, team_rows)
    write_csv(output_dir / "stadium-group-ranking.csv", STADIUM_GROUP_FIELDS, stadium_rows)
    write_csv(output_dir / "opta-calibration.csv", OPTA_CALIBRATION_FIELDS, opta_rows)
    if opta_standings:
        write_csv(
            output_dir / "opta-standings-calibration.csv",
            OPTA_STANDINGS_CALIBRATION_FIELDS,
            opta_standing_rows,
        )
        write_csv(
            output_dir / "opta-third-place-snapshot.csv",
            OPTA_THIRD_PLACE_SNAPSHOT_FIELDS,
            opta_third_rows,
        )
    return {
        "group_goals": len(group_rows),
        "team_group": len(team_rows),
        "stadium_group": len(stadium_rows),
        "opta_calibration": len(opta_rows),
        "opta_standings_calibration": len(opta_standing_rows),
        "opta_third_place_snapshot": len(opta_third_rows),
    }


def _initial_team_stats(matches: list[dict[str, str]]) -> dict[str, TeamSimulationStats]:
    stats = {}
    for match in matches:
        for key in ("team_home", "team_away"):
            team = match[key]
            if team not in stats:
                stats[team] = TeamSimulationStats(team=team, group=match["group"])
    return stats


def _match_points(home_goals: int, away_goals: int) -> tuple[int, int]:
    if home_goals > away_goals:
        return 3, 0
    if away_goals > home_goals:
        return 0, 3
    return 1, 1


def _group_goal_rows(group_goal_values: dict[str, list[int]]) -> list[dict[str, str]]:
    return [
        {
            "group": group,
            "expected_goals": fmt(sum(values) / len(values)),
            "p05": fmt(_percentile(values, 0.05)),
            "p50": fmt(_percentile(values, 0.50)),
            "p95": fmt(_percentile(values, 0.95)),
        }
        for group, values in sorted(group_goal_values.items())
    ]


def _team_group_rows(
    team_stats: dict[str, TeamSimulationStats],
    simulations: int,
) -> list[dict[str, str]]:
    rows = []
    for stat in sorted(team_stats.values(), key=lambda item: (item.group, item.team)):
        expected_gf = stat.gf_total / simulations
        expected_ga = stat.ga_total / simulations
        rows.append(
            {
                "team": stat.team,
                "group": stat.group,
                "expected_points": fmt(stat.points_total / simulations),
                "expected_gf": fmt(expected_gf),
                "expected_ga": fmt(expected_ga),
                "expected_gd": fmt(expected_gf - expected_ga),
                "prob_top_group": fmt(stat.top_group_count / simulations),
                "prob_l32": fmt(stat.l32_count / simulations),
                "prob_third_place": fmt(stat.third_place_count / simulations),
                "prob_best_third": fmt(stat.best_third_count / simulations),
            }
        )
    return rows


def _stadium_rows(
    stadium_totals: dict[str, int],
    stadium_counts: dict[str, int],
    simulations: int,
) -> list[dict[str, str]]:
    rows = []
    for stadium, total in stadium_totals.items():
        scheduled_matches = stadium_counts[stadium] // simulations
        expected_total = total / simulations
        rows.append(
            {
                "stadium_fifa": stadium,
                "scheduled_group_matches": str(scheduled_matches),
                "expected_total_goals": fmt(expected_total),
                "expected_average_goals": fmt(expected_total / scheduled_matches),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["expected_average_goals"]), row["stadium_fifa"]))


def _opta_calibration_rows(
    team_rows: list[dict[str, str]],
    opta: dict[str, dict[str, str]],
) -> list[dict[str, str]]:
    rows = []
    for row in sorted(team_rows, key=lambda item: item["team"]):
        prediction = opta.get(row["team"])
        if prediction is None:
            continue
        model_top = float(row["prob_top_group"])
        opta_top = float(prediction["top_group"])
        model_l32 = float(row["prob_l32"])
        opta_l32 = float(prediction["l32"])
        rows.append(
            {
                "team": row["team"],
                "model_prob_top_group": fmt(model_top),
                "opta_top_group": fmt(opta_top),
                "diff_top_group": fmt(model_top - opta_top),
                "model_prob_l32": fmt(model_l32),
                "opta_l32": fmt(opta_l32),
                "diff_l32": fmt(model_l32 - opta_l32),
            }
        )
    return rows


def _opta_standings_calibration_rows(
    team_rows: list[dict[str, str]],
    opta_standings: list[dict[str, str]],
) -> list[dict[str, str]]:
    standings = {row["team"]: row for row in opta_standings if row["table_type"] == "group"}
    rows = []
    for row in sorted(team_rows, key=lambda item: (item["group"], item["team"])):
        standing = standings.get(row["team"])
        if standing is None:
            continue
        model_xpts = float(row["expected_points"])
        opta_xpts = float(standing["xpts"])
        model_l32 = float(row["prob_l32"])
        opta_qual = float(standing["qual"])
        rows.append(
            {
                "team": row["team"],
                "group": row["group"],
                "model_expected_points": fmt(model_xpts),
                "opta_xpts": fmt(opta_xpts),
                "diff_xpts": fmt(model_xpts - opta_xpts),
                "model_prob_l32": fmt(model_l32),
                "opta_qual": fmt(opta_qual),
                "diff_qual": fmt(model_l32 - opta_qual),
                "model_prob_third_place": row["prob_third_place"],
                "model_prob_best_third": row["prob_best_third"],
            }
        )
    return rows


def _opta_third_place_snapshot_rows(
    team_rows: list[dict[str, str]],
    opta_standings: list[dict[str, str]],
) -> list[dict[str, str]]:
    team_lookup = {row["team"]: row for row in team_rows}
    third_rows = [row for row in opta_standings if row["table_type"] == "third_place_snapshot"]
    rows = []
    for standing in sorted(third_rows, key=lambda item: int(item["row_rank"])):
        model = team_lookup.get(standing["team"])
        if model is None:
            continue
        rows.append(
            {
                "team": standing["team"],
                "group": standing["group"],
                "opta_row_rank": standing["row_rank"],
                "opta_raw_pos": standing["raw_pos"],
                "opta_xpts": standing["xpts"],
                "opta_qual": standing["qual"],
                "model_prob_third_place": model["prob_third_place"],
                "model_prob_best_third": model["prob_best_third"],
                "model_prob_l32": model["prob_l32"],
            }
        )
    return rows


def _percentile(values: list[int], quantile: float) -> float:
    ordered = sorted(values)
    index = int(round((len(ordered) - 1) * quantile))
    return float(ordered[index])
