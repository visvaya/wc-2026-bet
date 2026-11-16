"""Group-stage table and score sampling shared by the group and tournament simulations."""

from __future__ import annotations

import random
from bisect import bisect_left
from dataclasses import dataclass

from wc2026bet.score_grid import ScoreGrid


@dataclass
class TeamTableRow:
    team: str
    group: str
    points: int = 0
    gf: int = 0
    ga: int = 0
    random_tiebreaker: float = 0.0

    @property
    def gd(self) -> int:
        return self.gf - self.ga


class ScoreSampler:
    def __init__(
        self,
        lambda_home: float,
        lambda_away: float,
        *,
        max_goals: int,
        total_dispersion_tilt: float,
        btts_correlation_tilt: float,
    ) -> None:
        thresholds = []
        scorelines = []
        running = 0.0
        grid = ScoreGrid(
            lambda_home,
            lambda_away,
            max_goals=max_goals,
            total_dispersion_tilt=total_dispersion_tilt,
            btts_correlation_tilt=btts_correlation_tilt,
        )
        for home_goals, away_goals, probability in grid.score_probabilities():
            running += probability
            thresholds.append(running)
            scorelines.append((home_goals, away_goals))
        self._thresholds = thresholds
        self._scorelines = scorelines

    def sample(self, rng: random.Random) -> tuple[int, int]:
        index = bisect_left(self._thresholds, rng.random())
        if index >= len(self._scorelines):
            index = len(self._scorelines) - 1
        return self._scorelines[index]


def initial_table(matches: list[dict[str, str]], rng: random.Random) -> dict[tuple[str, str], TeamTableRow]:
    table: dict[tuple[str, str], TeamTableRow] = {}
    for match in matches:
        for key in ("team_home", "team_away"):
            team = match[key]
            group = match["group"]
            table.setdefault(
                (group, team),
                TeamTableRow(team=team, group=group, random_tiebreaker=rng.random()),
            )
    return table


def apply_match(home: TeamTableRow, away: TeamTableRow, home_goals: int, away_goals: int) -> None:
    home.gf += home_goals
    home.ga += away_goals
    away.gf += away_goals
    away.ga += home_goals
    if home_goals > away_goals:
        home.points += 3
    elif away_goals > home_goals:
        away.points += 3
    else:
        home.points += 1
        away.points += 1


def table_sort_key(row: TeamTableRow) -> tuple[int, int, int, float]:
    return row.points, row.gd, row.gf, row.random_tiebreaker
