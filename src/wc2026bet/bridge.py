"""Rating-to-goals bridge for knockout-stage score parameters."""

from __future__ import annotations

import math
from dataclasses import dataclass
from pathlib import Path

from wc2026bet.csv_io import read_csv, write_csv

TEAM_GOAL_STRENGTH_FIELDS = ("team", "rating", "attack", "defense")
RATING_GOAL_BRIDGE_FIELDS = (
    "ridge_alpha",
    "intercept",
    "rating_coefficient",
    "training_rmse",
    "cv_rmse",
    "observations",
)

_RIDGE_CANDIDATES = (0.1, 1.0, 3.0, 10.0, 30.0, 100.0)
_MIN_LAMBDA = 0.15
_MAX_LAMBDA = 5.5


@dataclass(frozen=True)
class RatingGoalBridge:
    intercept: float
    rating_coefficient: float
    attacks: dict[str, float]
    defenses: dict[str, float]
    ratings: dict[str, float]
    ridge_alpha: float
    training_rmse: float
    cv_rmse: float
    observations: int

    def predict_lambdas(self, home_team: str, away_team: str) -> tuple[float, float]:
        """Predict ordered home and away expected goals."""

        return (
            self.predict_lambda(home_team, away_team),
            self.predict_lambda(away_team, home_team),
        )

    def predict_lambda(self, attacking_team: str, defending_team: str) -> float:
        """Predict goals for one team against one opponent."""

        if attacking_team not in self.ratings:
            raise ValueError(f"Missing rating for attacking team: {attacking_team}")
        if defending_team not in self.ratings:
            raise ValueError(f"Missing rating for defending team: {defending_team}")
        rating_diff = (self.ratings[attacking_team] - self.ratings[defending_team]) / 100.0
        log_lambda = (
            self.intercept
            + self.attacks.get(attacking_team, 0.0)
            - self.defenses.get(defending_team, 0.0)
            + self.rating_coefficient * rating_diff
        )
        return max(_MIN_LAMBDA, min(_MAX_LAMBDA, math.exp(log_lambda)))


@dataclass(frozen=True)
class _Observation:
    scorer: str
    defender: str
    rating_diff: float
    log_lambda: float
    weight: float


def train_rating_goal_bridge(processed_dir: Path) -> RatingGoalBridge:
    """Train and write a ridge-regularized rating-to-goals bridge."""

    teams = read_csv(processed_dir / "teams.csv")
    matches = {
        row["match_id"]: row for row in read_csv(processed_dir / "matches.csv") if row["is_group_stage"] == "true"
    }
    params = {row["match_id"]: row for row in read_csv(processed_dir / "match_score_params.csv")}
    ratings = {row["team"]: float(row["rating"]) for row in teams}
    team_names = sorted(ratings)
    observations = _training_observations(matches, params, ratings)
    bridge = _fit_bridge(team_names, ratings, observations)
    write_rating_goal_bridge(bridge, processed_dir)
    return bridge


def write_rating_goal_bridge(bridge: RatingGoalBridge, processed_dir: Path) -> None:
    """Write trained bridge coefficients to processed CSV files."""

    strength_rows = [
        {
            "team": team,
            "rating": f"{bridge.ratings[team]:.6f}",
            "attack": f"{bridge.attacks.get(team, 0.0):.9f}",
            "defense": f"{bridge.defenses.get(team, 0.0):.9f}",
        }
        for team in sorted(bridge.ratings)
    ]
    model_rows = [
        {
            "ridge_alpha": f"{bridge.ridge_alpha:.6f}",
            "intercept": f"{bridge.intercept:.9f}",
            "rating_coefficient": f"{bridge.rating_coefficient:.9f}",
            "training_rmse": f"{bridge.training_rmse:.9f}",
            "cv_rmse": f"{bridge.cv_rmse:.9f}",
            "observations": str(bridge.observations),
        }
    ]
    write_csv(processed_dir / "team_goal_strengths.csv", TEAM_GOAL_STRENGTH_FIELDS, strength_rows)
    write_csv(processed_dir / "rating_goal_bridge.csv", RATING_GOAL_BRIDGE_FIELDS, model_rows)


def load_rating_goal_bridge(processed_dir: Path) -> RatingGoalBridge:
    """Load trained bridge coefficients from processed CSV files."""

    strengths = read_csv(processed_dir / "team_goal_strengths.csv")
    model_rows = read_csv(processed_dir / "rating_goal_bridge.csv")
    if len(model_rows) != 1:
        raise ValueError("rating_goal_bridge.csv must contain exactly one row")
    model = model_rows[0]
    ratings = {row["team"]: float(row["rating"]) for row in strengths}
    attacks = {row["team"]: float(row["attack"]) for row in strengths}
    defenses = {row["team"]: float(row["defense"]) for row in strengths}
    return RatingGoalBridge(
        intercept=float(model["intercept"]),
        rating_coefficient=float(model["rating_coefficient"]),
        attacks=attacks,
        defenses=defenses,
        ratings=ratings,
        ridge_alpha=float(model["ridge_alpha"]),
        training_rmse=float(model["training_rmse"]),
        cv_rmse=float(model["cv_rmse"]),
        observations=int(model["observations"]),
    )


def _training_observations(
    matches: dict[str, dict[str, str]],
    params: dict[str, dict[str, str]],
    ratings: dict[str, float],
) -> list[_Observation]:
    missing_params = sorted(set(matches) - set(params), key=int)
    if missing_params:
        raise ValueError(f"Missing score params for group matches: {', '.join(missing_params[:5])}")

    observations = []
    for match_id, match in matches.items():
        param = params[match_id]
        home = match["team_home"]
        away = match["team_away"]
        weight = max(0.05, float(param.get("bridge_weight") or 1.0))
        observations.append(_make_observation(home, away, float(param["lambda_home"]), ratings, weight))
        observations.append(_make_observation(away, home, float(param["lambda_away"]), ratings, weight))
    return observations


def _make_observation(
    scorer: str,
    defender: str,
    lambda_value: float,
    ratings: dict[str, float],
    weight: float,
) -> _Observation:
    if scorer not in ratings or defender not in ratings:
        raise ValueError(f"Missing ratings for bridge observation: {scorer} vs {defender}")
    return _Observation(
        scorer=scorer,
        defender=defender,
        rating_diff=(ratings[scorer] - ratings[defender]) / 100.0,
        log_lambda=math.log(max(_MIN_LAMBDA, lambda_value)),
        weight=weight,
    )


def _fit_bridge(
    teams: list[str],
    ratings: dict[str, float],
    observations: list[_Observation],
) -> RatingGoalBridge:
    if not observations:
        raise ValueError("Cannot train rating bridge without observations")
    best_alpha = min(
        _RIDGE_CANDIDATES,
        key=lambda alpha: _cross_validated_rmse(teams, observations, alpha),
    )
    cv_rmse = _cross_validated_rmse(teams, observations, best_alpha)
    coefficients = _solve_coefficients(teams, observations, best_alpha)
    training_rmse = _rmse(teams, observations, coefficients)
    intercept, rating_coefficient, attacks, defenses = _unpack_coefficients(teams, coefficients)
    return RatingGoalBridge(
        intercept=intercept,
        rating_coefficient=rating_coefficient,
        attacks=attacks,
        defenses=defenses,
        ratings=ratings,
        ridge_alpha=best_alpha,
        training_rmse=training_rmse,
        cv_rmse=cv_rmse,
        observations=len(observations),
    )


def _cross_validated_rmse(
    teams: list[str],
    observations: list[_Observation],
    alpha: float,
    folds: int = 5,
) -> float:
    if len(observations) < folds:
        return _rmse(teams, observations, _solve_coefficients(teams, observations, alpha))
    squared_error = 0.0
    weight_total = 0.0
    for fold in range(folds):
        train = [obs for index, obs in enumerate(observations) if index % folds != fold]
        test = [obs for index, obs in enumerate(observations) if index % folds == fold]
        coefficients = _solve_coefficients(teams, train, alpha)
        for obs in test:
            error = _predict_log_lambda(teams, coefficients, obs.scorer, obs.defender, obs.rating_diff)
            squared_error += obs.weight * (error - obs.log_lambda) ** 2
            weight_total += obs.weight
    return math.sqrt(squared_error / weight_total)


def _solve_coefficients(
    teams: list[str],
    observations: list[_Observation],
    alpha: float,
) -> list[float]:
    dimension = 2 + len(teams) * 2
    team_index = {team: index for index, team in enumerate(teams)}
    xtx = [[0.0 for _ in range(dimension)] for _ in range(dimension)]
    xty = [0.0 for _ in range(dimension)]

    for obs in observations:
        features = _features(dimension, team_index, obs)
        weight = obs.weight
        for row_index, row_value in features:
            xty[row_index] += weight * row_value * obs.log_lambda
            for column_index, column_value in features:
                xtx[row_index][column_index] += weight * row_value * column_value

    for index in range(1, dimension):
        xtx[index][index] += alpha
    return _gaussian_solve(xtx, xty)


def _features(
    dimension: int,
    team_index: dict[str, int],
    obs: _Observation,
) -> list[tuple[int, float]]:
    attack_offset = 2
    defense_offset = 2 + len(team_index)
    return [
        (0, 1.0),
        (1, obs.rating_diff),
        (attack_offset + team_index[obs.scorer], 1.0),
        (defense_offset + team_index[obs.defender], -1.0),
    ]


def _rmse(teams: list[str], observations: list[_Observation], coefficients: list[float]) -> float:
    squared_error = 0.0
    weight_total = 0.0
    for obs in observations:
        prediction = _predict_log_lambda(teams, coefficients, obs.scorer, obs.defender, obs.rating_diff)
        squared_error += obs.weight * (prediction - obs.log_lambda) ** 2
        weight_total += obs.weight
    return math.sqrt(squared_error / weight_total)


def _predict_log_lambda(
    teams: list[str],
    coefficients: list[float],
    scorer: str,
    defender: str,
    rating_diff: float,
) -> float:
    team_index = {team: index for index, team in enumerate(teams)}
    attack_offset = 2
    defense_offset = 2 + len(teams)
    return (
        coefficients[0]
        + coefficients[1] * rating_diff
        + coefficients[attack_offset + team_index[scorer]]
        - coefficients[defense_offset + team_index[defender]]
    )


def _unpack_coefficients(
    teams: list[str],
    coefficients: list[float],
) -> tuple[float, float, dict[str, float], dict[str, float]]:
    attack_offset = 2
    defense_offset = 2 + len(teams)
    attacks = {team: coefficients[attack_offset + index] for index, team in enumerate(teams)}
    defenses = {team: coefficients[defense_offset + index] for index, team in enumerate(teams)}
    return coefficients[0], coefficients[1], attacks, defenses


def _gaussian_solve(matrix: list[list[float]], vector: list[float]) -> list[float]:
    size = len(vector)
    augmented = [row[:] + [vector[index]] for index, row in enumerate(matrix)]
    for column in range(size):
        pivot = max(range(column, size), key=lambda row: abs(augmented[row][column]))
        if abs(augmented[pivot][column]) < 1e-12:
            raise ValueError("Ridge system is singular")
        augmented[column], augmented[pivot] = augmented[pivot], augmented[column]
        pivot_value = augmented[column][column]
        for index in range(column, size + 1):
            augmented[column][index] /= pivot_value
        for row in range(size):
            if row == column:
                continue
            factor = augmented[row][column]
            if factor == 0.0:
                continue
            for index in range(column, size + 1):
                augmented[row][index] -= factor * augmented[column][index]
    return [augmented[row][size] for row in range(size)]
