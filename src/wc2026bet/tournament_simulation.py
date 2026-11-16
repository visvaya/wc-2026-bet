"""Full World Cup 2026 tournament Monte Carlo simulation."""

from __future__ import annotations

import math
import random
import re
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

from wc2026bet.bridge import RatingGoalBridge, load_rating_goal_bridge
from wc2026bet.csv_io import fmt, read_csv, write_csv
from wc2026bet.fitting import read_score_model_config
from wc2026bet.group_table import ScoreSampler, TeamTableRow, apply_match, initial_table, table_sort_key
from wc2026bet.regulations import parse_r32_third_place_mapping
from wc2026bet.tournament_report import (
    STADIUM_AVERAGE_FIELDS,
    STADIUM_TOTAL_FIELDS,
    TEAM_TOURNAMENT_FIELDS,
    TeamTournamentStats,
    compute_effective_sample_size,
    count_scheduled_stadium_matches,
    record_stadium_iteration,
    stadium_average_rows,
    stadium_total_rows,
    team_tournament_rows,
)

WINNER_RE = re.compile(r"^Group ([A-L]) winners$")
RUNNER_UP_RE = re.compile(r"^Group ([A-L]) runners(?:-up| up)$")
THIRD_PLACE_RE = re.compile(r"^Group [A-L/]+ third place$")
MATCH_RESULT_RE = re.compile(r"^(Winner|Runner-up) match (\d+)$")


@dataclass(frozen=True)
class KnockoutResult:
    winner: str
    runner_up: str
    home_goals: int
    away_goals: int


@dataclass
class TeamIterationStats:
    gf: int = 0
    ga: int = 0
    l32: bool = False
    l16: bool = False
    qf: bool = False
    sf: bool = False
    final: bool = False
    champion: bool = False


@dataclass(frozen=True)
class CalibrationConfig:
    model: str = "none"
    strength: float = 0.35
    min_weight: float = 0.05
    max_weight: float = 20.0


def simulate_tournament(
    processed_dir: Path,
    manual_dir: Path,
    output_dir: Path,
    *,
    simulations: int = 200_000,
    seed: int = 20260610,
    extra_time_goal_multiplier: float = 0.30,
    penalty_model: str = "coin_flip",
    use_score_tilts: bool = True,
    value_threshold: float = 0.05,
    calibration_model: str = "none",
    baseline_probabilities_path: Path | None = None,
    opta_strength: float = 0.35,
) -> dict[str, int]:
    """Run full-tournament Monte Carlo and write stadium/team reports."""

    if simulations <= 0:
        raise ValueError("simulations must be positive")
    if extra_time_goal_multiplier <= 0:
        raise ValueError("extra_time_goal_multiplier must be positive")
    if penalty_model not in {"coin_flip", "rating_weighted"}:
        raise ValueError("penalty_model must be coin_flip or rating_weighted")
    if calibration_model not in {"none", "opta_reweight"}:
        raise ValueError("calibration_model must be none or opta_reweight")

    matches = read_csv(processed_dir / "matches.csv")
    group_matches = [row for row in matches if row["is_group_stage"] == "true"]
    knockout_matches = [row for row in matches if row["is_group_stage"] != "true"]
    params = {row["match_id"]: row for row in read_csv(processed_dir / "match_score_params.csv")}
    bridge = load_rating_goal_bridge(processed_dir)
    score_config = read_score_model_config(processed_dir / "score_model_config.csv")
    total_dispersion_tilt = score_config.total_dispersion_tilt if use_score_tilts else 0.0
    btts_correlation_tilt = score_config.btts_correlation_tilt if use_score_tilts else 0.0
    r32_mapping = {
        row["qualified_third_groups"]: row
        for row in parse_r32_third_place_mapping(manual_dir / "r32_third_place_mapping.csv")
    }
    stadium_market_odds = {
        row["stadium_fifa"]: float(row["decimal_odds"]) for row in read_csv(processed_dir / "stadium_market_odds.csv")
    }
    calibration_config = CalibrationConfig(model=calibration_model, strength=opta_strength)
    calibration_targets = _load_calibration_targets(
        processed_dir,
        baseline_probabilities_path,
        calibration_config,
    )
    scheduled_stadium_matches = count_scheduled_stadium_matches(matches)

    missing_params = sorted({match["match_id"] for match in group_matches} - set(params), key=int)
    if missing_params:
        raise ValueError(f"Missing score params for group matches: {', '.join(missing_params[:5])}")

    rng = random.Random(seed)  # noqa: S311 - seedable Monte Carlo sampling, not cryptography
    group_samplers = {
        match["match_id"]: ScoreSampler(
            float(params[match["match_id"]]["lambda_home"]),
            float(params[match["match_id"]]["lambda_away"]),
            max_goals=score_config.max_goals,
            total_dispersion_tilt=total_dispersion_tilt,
            btts_correlation_tilt=btts_correlation_tilt,
        )
        for match in group_matches
    }
    knockout_sampler_cache: dict[tuple[float, float, float], ScoreSampler] = {}
    team_stats = {team: TeamTournamentStats(team=team) for team in bridge.ratings}
    stadium_average_values: dict[str, list[tuple[float, float]]] = {
        stadium: [] for stadium in scheduled_stadium_matches
    }
    stadium_total_values: dict[str, list[tuple[float, float]]] = {stadium: [] for stadium in scheduled_stadium_matches}
    highest_average_counts: dict[str, float] = defaultdict(float)
    highest_total_counts: dict[str, float] = defaultdict(float)
    total_weight = 0.0
    clipped_low = 0
    clipped_high = 0

    for _ in range(simulations):
        table = initial_table(group_matches, rng)
        stadium_goals: dict[str, int] = defaultdict(int)
        iteration_stats = {team: TeamIterationStats() for team in bridge.ratings}

        for match in group_matches:
            home_goals, away_goals = group_samplers[match["match_id"]].sample(rng)
            home = match["team_home"]
            away = match["team_away"]
            apply_match(table[(match["group"], home)], table[(match["group"], away)], home_goals, away_goals)
            _add_iteration_goals(iteration_stats, home, away, home_goals, away_goals)
            stadium_goals[match["stadium_fifa"]] += home_goals + away_goals

        group_rankings = _rank_groups(table)
        third_rows = [ranking[2] for ranking in group_rankings.values()]
        best_thirds = sorted(third_rows, key=table_sort_key, reverse=True)[:8]
        best_third_groups = "".join(sorted(row.group for row in best_thirds))
        if best_third_groups not in r32_mapping:
            raise ValueError(f"Missing R32 mapping for third-place groups: {best_third_groups}")
        mapping_row = r32_mapping[best_third_groups]
        third_by_group = {row.group: row for row in best_thirds}

        for ranking in group_rankings.values():
            for row in ranking[:2]:
                iteration_stats[row.team].l32 = True
        for row in best_thirds:
            iteration_stats[row.team].l32 = True

        knockout_results: dict[str, KnockoutResult] = {}
        for match in knockout_matches:
            home = _resolve_slot(
                match, match["slot_home"], group_rankings, third_by_group, mapping_row, knockout_results
            )
            away = _resolve_slot(
                match, match["slot_away"], group_rankings, third_by_group, mapping_row, knockout_results
            )
            result = _simulate_knockout_match(
                home,
                away,
                bridge,
                rng,
                knockout_sampler_cache,
                score_config.max_goals,
                total_dispersion_tilt,
                btts_correlation_tilt,
                extra_time_goal_multiplier,
                penalty_model,
            )
            knockout_results[match["match_id"]] = result
            _add_iteration_goals(iteration_stats, home, away, result.home_goals, result.away_goals)
            stadium_goals[match["stadium_fifa"]] += result.home_goals + result.away_goals
            _record_iteration_stage_win(iteration_stats[result.winner], match["phase"])

        weight, was_clipped_low, was_clipped_high = _iteration_weight(
            iteration_stats,
            calibration_targets,
            calibration_config,
        )
        clipped_low += int(was_clipped_low)
        clipped_high += int(was_clipped_high)
        total_weight += weight
        _apply_iteration_stats(team_stats, iteration_stats, weight)
        record_stadium_iteration(
            scheduled_stadium_matches,
            stadium_goals,
            stadium_average_values,
            stadium_total_values,
            highest_average_counts,
            highest_total_counts,
            weight,
        )

    output_dir.mkdir(parents=True, exist_ok=True)
    effective_sample_size = compute_effective_sample_size(stadium_average_values)
    average_rows = stadium_average_rows(
        stadium_average_values,
        highest_average_counts,
        scheduled_stadium_matches,
        stadium_market_odds,
        effective_sample_size,
        total_weight,
    )
    total_rows = stadium_total_rows(
        stadium_total_values,
        highest_total_counts,
        scheduled_stadium_matches,
        effective_sample_size,
        total_weight,
    )
    team_rows = team_tournament_rows(team_stats, total_weight)
    write_csv(output_dir / "stadium-average-ranking.csv", STADIUM_AVERAGE_FIELDS, average_rows)
    write_csv(output_dir / "stadium-total-ranking.csv", STADIUM_TOTAL_FIELDS, total_rows)
    write_csv(output_dir / "team-tournament.csv", TEAM_TOURNAMENT_FIELDS, team_rows)
    _write_summary(
        processed_dir,
        output_dir,
        simulations,
        seed,
        extra_time_goal_multiplier,
        penalty_model,
        value_threshold,
    )
    if calibration_model != "none":
        write_csv(
            output_dir / "calibration-diagnostics.csv",
            ("calibration_model", "total_weight", "effective_sample_size", "clipped_low", "clipped_high"),
            [
                {
                    "calibration_model": calibration_model,
                    "total_weight": fmt(total_weight),
                    "effective_sample_size": fmt(effective_sample_size),
                    "clipped_low": str(clipped_low),
                    "clipped_high": str(clipped_high),
                }
            ],
        )
    return {
        "stadium_average": len(average_rows),
        "stadium_total": len(total_rows),
        "team_tournament": len(team_rows),
    }


def _simulate_knockout_match(
    home: str,
    away: str,
    bridge: RatingGoalBridge,
    rng: random.Random,
    sampler_cache: dict[tuple[float, float, float], ScoreSampler],
    max_goals: int,
    total_dispersion_tilt: float,
    btts_correlation_tilt: float,
    extra_time_goal_multiplier: float,
    penalty_model: str,
) -> KnockoutResult:
    lambda_home, lambda_away = bridge.predict_lambdas(home, away)
    home_goals, away_goals = _sampler(
        sampler_cache,
        lambda_home,
        lambda_away,
        1.0,
        max_goals,
        total_dispersion_tilt,
        btts_correlation_tilt,
    ).sample(rng)
    if home_goals == away_goals:
        extra_home, extra_away = _sampler(
            sampler_cache,
            lambda_home,
            lambda_away,
            extra_time_goal_multiplier,
            max_goals,
            total_dispersion_tilt,
            btts_correlation_tilt,
        ).sample(rng)
        home_goals += extra_home
        away_goals += extra_away

    if home_goals > away_goals:
        winner, runner_up = home, away
    elif away_goals > home_goals:
        winner, runner_up = away, home
    else:
        winner = _penalty_winner(home, away, bridge, rng, penalty_model)
        runner_up = away if winner == home else home

    return KnockoutResult(
        winner=winner,
        runner_up=runner_up,
        home_goals=home_goals,
        away_goals=away_goals,
    )


def _penalty_winner(
    home: str,
    away: str,
    bridge: RatingGoalBridge,
    rng: random.Random,
    penalty_model: str,
) -> str:
    if penalty_model == "coin_flip":
        home_probability = 0.5
    else:
        rating_diff = bridge.ratings[home] - bridge.ratings[away]
        home_probability = 1.0 / (1.0 + math.exp(-(rating_diff / 250.0)))
    return home if rng.random() < home_probability else away


def _load_calibration_targets(
    processed_dir: Path,
    baseline_probabilities_path: Path | None,
    config: CalibrationConfig,
) -> dict[str, dict[str, float]]:
    if config.model == "none":
        return {}
    if baseline_probabilities_path is None:
        raise ValueError("baseline_probabilities_path is required for opta_reweight")
    opta = {row["team"]: row for row in read_csv(processed_dir / "opta_predictions.csv")}
    baseline = {row["team"]: row for row in read_csv(baseline_probabilities_path)}
    targets = {}
    for team, opta_row in opta.items():
        if team not in baseline:
            raise ValueError(f"Missing baseline tournament probability for {team}")
        targets[team] = {
            "opta_l32": float(opta_row["l32"]),
            "opta_l16": float(opta_row["l16"]),
            "opta_qf": float(opta_row["qf"]),
            "opta_sf": float(opta_row["sf"]),
            "opta_final": float(opta_row["final"]),
            "opta_champion": float(opta_row["champion"]),
            "baseline_l32": float(baseline[team]["prob_l32"]),
            "baseline_l16": float(baseline[team]["prob_l16"]),
            "baseline_qf": float(baseline[team]["prob_qf"]),
            "baseline_sf": float(baseline[team]["prob_sf"]),
            "baseline_final": float(baseline[team]["prob_final"]),
            "baseline_champion": float(baseline[team]["prob_champion"]),
        }
    return targets


def _iteration_weight(
    iteration_stats: dict[str, TeamIterationStats],
    calibration_targets: dict[str, dict[str, float]],
    config: CalibrationConfig,
) -> tuple[float, bool, bool]:
    if config.model == "none":
        return 1.0, False, False
    stage_weights = {
        "l32": 1.0,
        "l16": 0.75,
        "qf": 0.50,
        "sf": 0.35,
        "final": 0.25,
        "champion": 0.15,
    }
    log_weight = 0.0
    for team, stats in iteration_stats.items():
        target = calibration_targets[team]
        for stage, stage_weight in stage_weights.items():
            if not getattr(stats, stage):
                continue
            opta_probability = _clip_probability(target[f"opta_{stage}"])
            baseline_probability = _clip_probability(target[f"baseline_{stage}"])
            log_weight += stage_weight * math.log(opta_probability / baseline_probability)
    raw_weight = math.exp(config.strength * log_weight)
    clipped = max(config.min_weight, min(config.max_weight, raw_weight))
    return clipped, raw_weight < config.min_weight, raw_weight > config.max_weight


def _clip_probability(value: float) -> float:
    return max(0.02, min(0.98, value))


def _sampler(
    cache: dict[tuple[float, float, float], ScoreSampler],
    lambda_home: float,
    lambda_away: float,
    multiplier: float,
    max_goals: int,
    total_dispersion_tilt: float,
    btts_correlation_tilt: float,
) -> ScoreSampler:
    key = (round(lambda_home, 3), round(lambda_away, 3), round(multiplier, 3))
    if key not in cache:
        cache[key] = ScoreSampler(
            max(0.01, lambda_home * multiplier),
            max(0.01, lambda_away * multiplier),
            max_goals=max_goals,
            total_dispersion_tilt=total_dispersion_tilt,
            btts_correlation_tilt=btts_correlation_tilt,
        )
    return cache[key]


def _resolve_slot(
    match: dict[str, str],
    slot: str,
    group_rankings: dict[str, list[TeamTableRow]],
    third_by_group: dict[str, TeamTableRow],
    mapping_row: dict[str, str],
    knockout_results: dict[str, KnockoutResult],
) -> str:
    winner_match = WINNER_RE.match(slot)
    if winner_match:
        return group_rankings[winner_match.group(1)][0].team
    runner_up_match = RUNNER_UP_RE.match(slot)
    if runner_up_match:
        return group_rankings[runner_up_match.group(1)][1].team
    if THIRD_PLACE_RE.match(slot):
        winner_group = _winner_group_for_third_place_slot(match)
        assigned_group = mapping_row[f"vs_1{winner_group}"][1]
        return third_by_group[assigned_group].team
    match_result = MATCH_RESULT_RE.match(slot)
    if match_result:
        result = knockout_results[match_result.group(2)]
        return result.winner if match_result.group(1) == "Winner" else result.runner_up
    raise ValueError(f"Unsupported knockout slot: {slot}")


def _winner_group_for_third_place_slot(match: dict[str, str]) -> str:
    for slot in (match["slot_home"], match["slot_away"]):
        winner_match = WINNER_RE.match(slot)
        if winner_match:
            return winner_match.group(1)
    raise ValueError(f"Cannot infer R32 winner group for match {match['match_id']}")


def _rank_groups(table: dict[tuple[str, str], TeamTableRow]) -> dict[str, list[TeamTableRow]]:
    groups = sorted({group for group, _ in table})
    return {
        group: sorted(
            [row for (row_group, _), row in table.items() if row_group == group],
            key=table_sort_key,
            reverse=True,
        )
        for group in groups
    }


def _add_iteration_goals(
    team_stats: dict[str, TeamIterationStats],
    home: str,
    away: str,
    home_goals: int,
    away_goals: int,
) -> None:
    team_stats[home].gf += home_goals
    team_stats[home].ga += away_goals
    team_stats[away].gf += away_goals
    team_stats[away].ga += home_goals


def _apply_iteration_stats(
    aggregate: dict[str, TeamTournamentStats],
    iteration: dict[str, TeamIterationStats],
    weight: float,
) -> None:
    for team, stats in iteration.items():
        aggregate[team].gf_total += stats.gf * weight
        aggregate[team].ga_total += stats.ga * weight
        aggregate[team].l32_count += weight if stats.l32 else 0.0
        aggregate[team].l16_count += weight if stats.l16 else 0.0
        aggregate[team].qf_count += weight if stats.qf else 0.0
        aggregate[team].sf_count += weight if stats.sf else 0.0
        aggregate[team].final_count += weight if stats.final else 0.0
        aggregate[team].champion_count += weight if stats.champion else 0.0


def _record_iteration_stage_win(stat: TeamIterationStats, phase: str) -> None:
    if phase == "R32":
        stat.l16 = True
    elif phase == "R16":
        stat.qf = True
    elif phase == "QF":
        stat.sf = True
    elif phase == "SF":
        stat.final = True
    elif phase == "Final":
        stat.champion = True


def _write_summary(
    processed_dir: Path,
    output_dir: Path,
    simulations: int,
    seed: int,
    extra_time_goal_multiplier: float,
    penalty_model: str,
    value_threshold: float,
) -> None:
    from wc2026bet.decision_report import build_decision_report

    build_decision_report(
        processed_dir,
        output_dir,
        output_dir / "tournament-summary.md",
        simulations=simulations,
        seed=seed,
        extra_time_goal_multiplier=extra_time_goal_multiplier,
        penalty_model=penalty_model,
        value_threshold=value_threshold,
    )
