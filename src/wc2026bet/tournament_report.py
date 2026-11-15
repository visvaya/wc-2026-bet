"""Aggregation and report rows for the tournament simulation outputs."""

from __future__ import annotations

import csv
import math
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

STADIUM_AVERAGE_FIELDS = (
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
)
STADIUM_TOTAL_FIELDS = (
    "stadium_fifa",
    "scheduled_matches",
    "expected_total_goals",
    "p05",
    "p25",
    "p50",
    "p75",
    "p95",
    "prob_highest_total",
    "mc_error",
)
TEAM_TOURNAMENT_FIELDS = (
    "team",
    "expected_gf",
    "expected_ga",
    "prob_l32",
    "prob_l16",
    "prob_qf",
    "prob_sf",
    "prob_final",
    "prob_champion",
)


@dataclass
class TeamTournamentStats:
    team: str
    gf_total: float = 0.0
    ga_total: float = 0.0
    l32_count: float = 0.0
    l16_count: float = 0.0
    qf_count: float = 0.0
    sf_count: float = 0.0
    final_count: float = 0.0
    champion_count: float = 0.0


def count_scheduled_stadium_matches(matches: list[dict[str, str]]) -> dict[str, int]:
    counts: dict[str, int] = defaultdict(int)
    for match in matches:
        counts[match["stadium_fifa"]] += 1
    return dict(counts)


def record_stadium_iteration(
    scheduled_matches: dict[str, int],
    stadium_goals: dict[str, int],
    average_values: dict[str, list[tuple[float, float]]],
    total_values: dict[str, list[tuple[float, float]]],
    highest_average_counts: dict[str, float],
    highest_total_counts: dict[str, float],
    weight: float,
) -> None:
    averages = {
        stadium: stadium_goals[stadium] / scheduled_count for stadium, scheduled_count in scheduled_matches.items()
    }
    totals = {stadium: stadium_goals[stadium] for stadium in scheduled_matches}
    for stadium, average in averages.items():
        average_values[stadium].append((average, weight))
        total_values[stadium].append((float(totals[stadium]), weight))
    _split_tied_winners(averages, highest_average_counts, weight)
    _split_tied_winners(totals, highest_total_counts, weight)


def _split_tied_winners(values: Mapping[str, float], counts: dict[str, float], weight: float) -> None:
    best = max(values.values())
    winners = [stadium for stadium, value in values.items() if value == best]
    increment = weight / len(winners)
    for winner in winners:
        counts[winner] += increment


def stadium_average_rows(
    values_by_stadium: dict[str, list[tuple[float, float]]],
    highest_counts: dict[str, float],
    scheduled_matches: dict[str, int],
    bookmaker_odds: dict[str, float],
    sample_size: float,
    total_weight: float,
) -> list[dict[str, str]]:
    rows = []
    for stadium, values in values_by_stadium.items():
        probability = highest_counts[stadium] / total_weight
        odds = bookmaker_odds.get(stadium)
        rows.append(
            {
                "stadium_fifa": stadium,
                "scheduled_matches": str(scheduled_matches[stadium]),
                "expected_average_goals": fmt(_weighted_mean(values)),
                "p05": fmt(_weighted_percentile(values, 0.05)),
                "p25": fmt(_weighted_percentile(values, 0.25)),
                "p50": fmt(_weighted_percentile(values, 0.50)),
                "p75": fmt(_weighted_percentile(values, 0.75)),
                "p95": fmt(_weighted_percentile(values, 0.95)),
                "prob_highest_average": fmt(probability),
                "mc_error": fmt(_mc_error(probability, sample_size)),
                "fair_odds": _fair_odds(probability),
                "bookmaker_odds": fmt(odds) if odds is not None else "",
                "ev": fmt(probability * odds - 1.0) if odds is not None else "",
            }
        )
    return sorted(rows, key=lambda row: (-float(row["prob_highest_average"]), row["stadium_fifa"]))


def stadium_total_rows(
    values_by_stadium: dict[str, list[tuple[float, float]]],
    highest_counts: dict[str, float],
    scheduled_matches: dict[str, int],
    sample_size: float,
    total_weight: float,
) -> list[dict[str, str]]:
    rows = []
    for stadium, values in values_by_stadium.items():
        probability = highest_counts[stadium] / total_weight
        rows.append(
            {
                "stadium_fifa": stadium,
                "scheduled_matches": str(scheduled_matches[stadium]),
                "expected_total_goals": fmt(_weighted_mean(values)),
                "p05": fmt(_weighted_percentile(values, 0.05)),
                "p25": fmt(_weighted_percentile(values, 0.25)),
                "p50": fmt(_weighted_percentile(values, 0.50)),
                "p75": fmt(_weighted_percentile(values, 0.75)),
                "p95": fmt(_weighted_percentile(values, 0.95)),
                "prob_highest_total": fmt(probability),
                "mc_error": fmt(_mc_error(probability, sample_size)),
            }
        )
    return sorted(rows, key=lambda row: (-float(row["prob_highest_total"]), row["stadium_fifa"]))


def team_tournament_rows(
    team_stats: dict[str, TeamTournamentStats],
    total_weight: float,
) -> list[dict[str, str]]:
    rows = []
    for stat in sorted(team_stats.values(), key=lambda item: item.team):
        rows.append(
            {
                "team": stat.team,
                "expected_gf": fmt(stat.gf_total / total_weight),
                "expected_ga": fmt(stat.ga_total / total_weight),
                "prob_l32": fmt(stat.l32_count / total_weight),
                "prob_l16": fmt(stat.l16_count / total_weight),
                "prob_qf": fmt(stat.qf_count / total_weight),
                "prob_sf": fmt(stat.sf_count / total_weight),
                "prob_final": fmt(stat.final_count / total_weight),
                "prob_champion": fmt(stat.champion_count / total_weight),
            }
        )
    return rows


def _weighted_mean(values: list[tuple[float, float]]) -> float:
    total_weight = sum(weight for _, weight in values)
    return sum(value * weight for value, weight in values) / total_weight


def _weighted_percentile(values: list[tuple[float, float]], quantile: float) -> float:
    ordered = sorted(values, key=lambda item: item[0])
    total_weight = sum(weight for _, weight in ordered)
    threshold = total_weight * quantile
    running = 0.0
    for value, weight in ordered:
        running += weight
        if running >= threshold:
            return value
    return ordered[-1][0]


def compute_effective_sample_size(
    values_by_stadium: dict[str, list[tuple[float, float]]],
) -> float:
    first_values = next(iter(values_by_stadium.values()))
    weights = [weight for _, weight in first_values]
    weight_sum = sum(weights)
    squared_sum = sum(weight**2 for weight in weights)
    if squared_sum == 0.0:
        return 0.0
    return (weight_sum**2) / squared_sum


def _mc_error(probability: float, sample_size: float) -> float:
    if sample_size <= 0.0:
        return 0.0
    return math.sqrt(probability * (1.0 - probability) / sample_size)


def _fair_odds(probability: float) -> str:
    if probability <= 0:
        return ""
    return fmt(1.0 / probability)


def write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def fmt(value: float) -> str:
    return f"{value:.6f}"
