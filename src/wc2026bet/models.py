"""Small domain models used by parser and validation code."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Match:
    match_id: int
    phase: str
    date: str
    stadium: str
    group: str | None = None
    team_home: str | None = None
    team_away: str | None = None
    slot_home: str | None = None
    slot_away: str | None = None

    @property
    def teams(self) -> tuple[str, ...]:
        if self.team_home is None or self.team_away is None:
            return ()
        return (self.team_home, self.team_away)


@dataclass(frozen=True)
class TeamRating:
    team: str
    confederation: str
    rating: float
    source_team: str


@dataclass(frozen=True)
class StadiumMarketOdd:
    stadium: str
    bookmaker_stadium: str
    decimal_odds: float
    market: str = "highest_average_goals"


@dataclass(frozen=True)
class OptaPrediction:
    team: str
    source_team: str
    top_group: float
    l32: float
    l16: float
    qf: float
    sf: float
    final: float
    champion: float


@dataclass(frozen=True)
class OptaStandingRow:
    table_type: str
    team: str
    source_team: str
    raw_pos: int
    row_rank: int
    xpts: float
    qual: float
    group: str | None = None
