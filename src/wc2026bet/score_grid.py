"""Finite score-grid probabilities for football match goal markets."""

from __future__ import annotations

import math
from dataclasses import dataclass, field


@dataclass(frozen=True)
class ScoreGrid:
    lambda_home: float
    lambda_away: float
    max_goals: int = 10
    total_dispersion_tilt: float = 0.0
    btts_correlation_tilt: float = 0.0
    _grid: tuple[tuple[float, ...], ...] = field(init=False, repr=False)

    def __post_init__(self) -> None:
        if self.lambda_home <= 0 or self.lambda_away <= 0:
            raise ValueError("Lambdas must be positive")
        if self.max_goals < 1:
            raise ValueError("max_goals must be at least 1")

        rows = []
        total = 0.0
        for home_goals in range(self.max_goals + 1):
            row = []
            home_probability = _poisson_probability(home_goals, self.lambda_home)
            for away_goals in range(self.max_goals + 1):
                probability = (
                    home_probability
                    * _poisson_probability(away_goals, self.lambda_away)
                    * self._tilt_multiplier(home_goals, away_goals)
                )
                row.append(probability)
                total += probability
            rows.append(row)

        normalized = tuple(tuple(value / total for value in row) for row in rows)
        object.__setattr__(self, "_grid", normalized)

    def total_probability(self) -> float:
        return sum(sum(row) for row in self._grid)

    def expected_total_goals(self) -> float:
        expected = 0.0
        for home_goals, row in enumerate(self._grid):
            for away_goals, probability in enumerate(row):
                expected += (home_goals + away_goals) * probability
        return expected

    def prob_over(self, line: float) -> float:
        return sum(
            probability
            for home_goals, row in enumerate(self._grid)
            for away_goals, probability in enumerate(row)
            if home_goals + away_goals > line
        )

    def prob_btts(self) -> float:
        return sum(
            probability
            for home_goals, row in enumerate(self._grid)
            for away_goals, probability in enumerate(row)
            if home_goals > 0 and away_goals > 0
        )

    def result_probabilities(self) -> dict[str, float]:
        home = draw = away = 0.0
        for home_goals, row in enumerate(self._grid):
            for away_goals, probability in enumerate(row):
                if home_goals > away_goals:
                    home += probability
                elif home_goals == away_goals:
                    draw += probability
                else:
                    away += probability
        return {"home": home, "draw": draw, "away": away}

    def score_probabilities(self) -> list[tuple[int, int, float]]:
        """Return scoreline probabilities as home goals, away goals, probability."""

        return [
            (home_goals, away_goals, probability)
            for home_goals, row in enumerate(self._grid)
            for away_goals, probability in enumerate(row)
        ]

    def _tilt_multiplier(self, home_goals: int, away_goals: int) -> float:
        total_goals = home_goals + away_goals
        expected_total = self.lambda_home + self.lambda_away
        dispersion_scale = max(expected_total, 1.0)
        dispersion = math.exp(self.total_dispersion_tilt * ((total_goals - expected_total) ** 2) / dispersion_scale)
        btts = math.exp(self.btts_correlation_tilt) if home_goals > 0 and away_goals > 0 else 1.0
        return dispersion * btts


def _poisson_probability(goals: int, rate: float) -> float:
    return math.exp(-rate) * (rate**goals) / math.factorial(goals)
