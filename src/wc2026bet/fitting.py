"""Fit group-stage score-grid parameters from betting odds."""

from __future__ import annotations

import csv
import math
from dataclasses import dataclass
from pathlib import Path

from wc2026bet.csv_io import write_csv
from wc2026bet.manual_odds import parse_manual_odds
from wc2026bet.odds import power_devig, proportional_devig
from wc2026bet.score_grid import ScoreGrid

MATCH_SCORE_PARAM_FIELDS = (
    "match_id",
    "lambda_home",
    "lambda_away",
    "weighted_rmse",
    "max_abs_error",
    "low_confidence",
    "bridge_weight",
)
SCORE_MODEL_CONFIG_FIELDS = (
    "max_goals",
    "total_dispersion_tilt",
    "btts_correlation_tilt",
    "weighted_rmse",
    "max_abs_error",
    "unique_market_shapes",
)

MARKET_WEIGHTS = {
    "over_under_2_5": 3.0,
    "over_under_1_5": 2.0,
    "btts": 2.0,
    "1X2": 1.5,
    "over_under_0_5": 1.0,
}


@dataclass(frozen=True)
class MatchFitResult:
    lambda_home: float
    lambda_away: float
    weighted_rmse: float
    max_abs_error: float
    low_confidence: bool
    bridge_weight: float


@dataclass(frozen=True)
class ScoreModelConfig:
    max_goals: int = 10
    total_dispersion_tilt: float = 0.0
    btts_correlation_tilt: float = 0.0
    weighted_rmse: float = 0.0
    max_abs_error: float = 0.0
    unique_market_shapes: int = 0


def fit_group_match_params(
    base_data: Path,
    odds_path: Path,
    output_path: Path,
    *,
    config_output_path: Path | None = None,
    fit_global_tilts: bool = True,
) -> int:
    """Fit and write one score-parameter row for each group-stage match."""

    rows = parse_manual_odds(odds_path, base_data)
    odds_by_match = _group_market_odds(rows)
    config = (
        fit_global_score_model(odds_by_match)
        if fit_global_tilts
        else ScoreModelConfig(
            unique_market_shapes=len({_market_odds_cache_key(value) for value in odds_by_match.values()})
        )
    )
    fit_cache: dict[tuple[tuple[str, tuple[tuple[str, float], ...]], ...], MatchFitResult] = {}
    output_rows = []
    for match_id in sorted(odds_by_match, key=int):
        cache_key = _market_odds_cache_key(odds_by_match[match_id])
        if cache_key not in fit_cache:
            fit_cache[cache_key] = fit_match_from_market_odds(
                odds_by_match[match_id],
                max_goals=config.max_goals,
                total_dispersion_tilt=config.total_dispersion_tilt,
                btts_correlation_tilt=config.btts_correlation_tilt,
            )
        result = fit_cache[cache_key]
        output_rows.append(
            {
                "match_id": match_id,
                "lambda_home": f"{result.lambda_home:.6f}",
                "lambda_away": f"{result.lambda_away:.6f}",
                "weighted_rmse": f"{result.weighted_rmse:.6f}",
                "max_abs_error": f"{result.max_abs_error:.6f}",
                "low_confidence": "true" if result.low_confidence else "false",
                "bridge_weight": f"{result.bridge_weight:.6f}",
            }
        )

    write_csv(output_path, MATCH_SCORE_PARAM_FIELDS, output_rows)
    if config_output_path is not None:
        write_score_model_config(config, config_output_path)
    return len(output_rows)


def fit_global_score_model(
    odds_by_match: dict[str, dict[str, dict[str, float]]],
    *,
    max_goals: int = 10,
) -> ScoreModelConfig:
    """Fit shared score-grid tilt parameters across all group-stage markets."""

    unique_market_odds = {_market_odds_cache_key(market_odds): market_odds for market_odds in odds_by_match.values()}
    best_config: ScoreModelConfig | None = None
    coarse_lambda_candidates = _lambda_candidates(step=0.4)
    for total_tilt in (-0.03, 0.0, 0.03):
        for btts_tilt in (-0.25, 0.0, 0.25):
            total_weighted_error = 0.0
            total_weight = 0.0
            max_abs_error = 0.0
            for market_odds in unique_market_odds.values():
                result = fit_match_from_market_odds(
                    market_odds,
                    max_goals=max_goals,
                    total_dispersion_tilt=total_tilt,
                    btts_correlation_tilt=btts_tilt,
                    lambda_candidates=coarse_lambda_candidates,
                )
                total_weighted_error += result.weighted_rmse**2
                total_weight += 1.0
                max_abs_error = max(max_abs_error, result.max_abs_error)
            weighted_rmse = math.sqrt(total_weighted_error / total_weight)
            candidate = ScoreModelConfig(
                max_goals=max_goals,
                total_dispersion_tilt=total_tilt,
                btts_correlation_tilt=btts_tilt,
                weighted_rmse=weighted_rmse,
                max_abs_error=max_abs_error,
                unique_market_shapes=len(unique_market_odds),
            )
            if best_config is None or candidate.weighted_rmse < best_config.weighted_rmse:
                best_config = candidate

    if best_config is None:
        raise ValueError("Could not fit global score model")
    return best_config


def write_score_model_config(config: ScoreModelConfig, output_path: Path) -> None:
    """Write fitted global score-grid configuration."""

    write_csv(
        output_path,
        SCORE_MODEL_CONFIG_FIELDS,
        [
            {
                "max_goals": str(config.max_goals),
                "total_dispersion_tilt": f"{config.total_dispersion_tilt:.6f}",
                "btts_correlation_tilt": f"{config.btts_correlation_tilt:.6f}",
                "weighted_rmse": f"{config.weighted_rmse:.6f}",
                "max_abs_error": f"{config.max_abs_error:.6f}",
                "unique_market_shapes": str(config.unique_market_shapes),
            }
        ],
    )


def read_score_model_config(path: Path) -> ScoreModelConfig:
    """Read a fitted global score-grid configuration, or return defaults if missing."""

    if not path.exists():
        return ScoreModelConfig()
    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if len(rows) != 1:
        raise ValueError(f"Expected one score model config row in {path}, found {len(rows)}")
    row = rows[0]
    return ScoreModelConfig(
        max_goals=int(row["max_goals"]),
        total_dispersion_tilt=float(row["total_dispersion_tilt"]),
        btts_correlation_tilt=float(row["btts_correlation_tilt"]),
        weighted_rmse=float(row.get("weighted_rmse") or 0.0),
        max_abs_error=float(row.get("max_abs_error") or 0.0),
        unique_market_shapes=int(row.get("unique_market_shapes") or 0),
    )


def fit_match_from_market_odds(
    market_odds: dict[str, dict[str, float]],
    *,
    max_goals: int = 10,
    total_dispersion_tilt: float = 0.0,
    btts_correlation_tilt: float = 0.0,
    lambda_candidates: list[tuple[float, float]] | None = None,
) -> MatchFitResult:
    """Fit lambda_home and lambda_away to devigged market probabilities."""

    targets = _market_targets(market_odds)
    best: tuple[float, float, float, float] | None = None
    for lambda_home, lambda_away in lambda_candidates or _lambda_candidates():
        grid = ScoreGrid(
            lambda_home=lambda_home,
            lambda_away=lambda_away,
            max_goals=max_goals,
            total_dispersion_tilt=total_dispersion_tilt,
            btts_correlation_tilt=btts_correlation_tilt,
        )
        weighted_rmse, max_abs_error = _loss(grid, targets)
        if best is None or weighted_rmse < best[0]:
            best = (weighted_rmse, max_abs_error, lambda_home, lambda_away)

    if best is None:
        raise ValueError("Could not fit score grid")

    weighted_rmse, max_abs_error, lambda_home, lambda_away = best
    low_confidence = weighted_rmse > 0.35 or max_abs_error > 0.18
    bridge_weight = max(0.15, min(1.0, 1.0 / (1.0 + weighted_rmse * 3.0)))
    if low_confidence:
        bridge_weight *= 0.5
    return MatchFitResult(
        lambda_home=lambda_home,
        lambda_away=lambda_away,
        weighted_rmse=weighted_rmse,
        max_abs_error=max_abs_error,
        low_confidence=low_confidence,
        bridge_weight=bridge_weight,
    )


def _group_market_odds(rows: list[dict[str, str]]) -> dict[str, dict[str, dict[str, float]]]:
    grouped: dict[str, dict[str, dict[str, float]]] = {}
    for row in rows:
        match_id = row["match_id"]
        market = row["market"]
        selection = row["selection"]
        grouped.setdefault(match_id, {}).setdefault(market, {})[selection] = float(row["decimal_odds"])
    return grouped


def _market_odds_cache_key(
    market_odds: dict[str, dict[str, float]],
) -> tuple[tuple[str, tuple[tuple[str, float], ...]], ...]:
    return tuple(
        (market, tuple(sorted((selection, round(odds, 6)) for selection, odds in selections.items())))
        for market, selections in sorted(market_odds.items())
    )


def _market_targets(market_odds: dict[str, dict[str, float]]) -> list[tuple[str, float, float]]:
    targets: list[tuple[str, float, float]] = []
    result_probabilities = power_devig(market_odds["1X2"])
    for selection in ("home", "draw", "away"):
        targets.append((f"1X2:{selection}", result_probabilities[selection], MARKET_WEIGHTS["1X2"]))

    for market, line in (
        ("over_under_0_5", 0.5),
        ("over_under_1_5", 1.5),
        ("over_under_2_5", 2.5),
    ):
        probabilities = proportional_devig(market_odds[market])
        targets.append((f"over:{line}", probabilities["over"], MARKET_WEIGHTS[market]))

    btts = proportional_devig(market_odds["btts"])
    targets.append(("btts:yes", btts["yes"], MARKET_WEIGHTS["btts"]))
    return targets


def _loss(grid: ScoreGrid, targets: list[tuple[str, float, float]]) -> tuple[float, float]:
    model_probabilities = _grid_market_probabilities(grid)
    weighted_error = 0.0
    weight_total = 0.0
    max_abs_error = 0.0
    for name, target, weight in targets:
        model_probability = model_probabilities[name]
        probability_error = abs(model_probability - target)
        max_abs_error = max(max_abs_error, probability_error)
        weighted_error += weight * (_logit(model_probability) - _logit(target)) ** 2
        weight_total += weight
    return math.sqrt(weighted_error / weight_total), max_abs_error


def _grid_market_probabilities(grid: ScoreGrid) -> dict[str, float]:
    results = grid.result_probabilities()
    return {
        "1X2:home": results["home"],
        "1X2:draw": results["draw"],
        "1X2:away": results["away"],
        "over:0.5": grid.prob_over(0.5),
        "over:1.5": grid.prob_over(1.5),
        "over:2.5": grid.prob_over(2.5),
        "btts:yes": grid.prob_btts(),
    }


def _lambda_candidates(*, step: float = 0.2, maximum: float = 5.0) -> list[tuple[float, float]]:
    steps = int(round((maximum - 0.2) / step)) + 1
    values = [0.2 + index * step for index in range(steps)]
    candidates = {(round(home, 3), round(away, 3)) for home in values for away in values}
    return sorted(candidates)


def _logit(probability: float) -> float:
    clipped = min(max(probability, 1e-6), 1.0 - 1e-6)
    return math.log(clipped / (1.0 - clipped))
