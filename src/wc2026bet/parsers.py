"""Parsers for immutable files stored in base-data."""

from __future__ import annotations

import re
from pathlib import Path

from wc2026bet.constants import (
    BOOKMAKER_STADIUM_ALIASES,
    FIFA_STADIUMS,
    TEAM_RATING_ALIASES,
)
from wc2026bet.models import Match, OptaPrediction, OptaStandingRow, StadiumMarketOdd, TeamRating

DATE_RE = re.compile(r"^[A-Za-z]+,\s+\d{1,2}\s+[A-Za-z]+\s+\d{4}$")
RATING_RE = re.compile(r"^\s*\d+\.\s+(.+?)\s{2,}([A-Z]{2})\s+([0-9.]+)\s*$")
BASE_DATA_FILE_CANDIDATES = {
    "matches": ("matches_fifa.txt", "matches.txt"),
    "ratings": ("rating_soccer-rating.txt", "soccer-rating.txt"),
    "stadium_market": ("stadiums_superbet.txt", "stadiums.txt", "stadiony.txt"),
    "opta_predictions": ("predictions-table_opta.txt",),
    "opta_standings": ("standings_opta.txt",),
}
OPTA_TEAM_ALIASES = {
    "Bosnia": "Bosnia and Herzegovina",
    "Iran": "IR Iran",
    "Korea Rep": "Korea Republic",
    "United States": "USA",
}


def resolve_base_data_file(base_data: Path, kind: str) -> Path:
    """Return the preferred source file path for a base-data kind."""

    try:
        candidates = BASE_DATA_FILE_CANDIDATES[kind]
    except KeyError as exc:
        raise ValueError(f"Unknown base-data file kind: {kind}") from exc
    for filename in candidates:
        path = base_data / filename
        if path.exists():
            return path
    raise FileNotFoundError(f"Missing base-data file for {kind}. Tried: {', '.join(candidates)}")


def parse_base_matches(base_data: Path) -> list[Match]:
    """Parse the preferred FIFA schedule source in base-data."""

    return parse_matches(resolve_base_data_file(base_data, "matches"))


def parse_base_soccer_ratings(base_data: Path) -> dict[str, TeamRating]:
    """Parse the preferred soccer-rating source in base-data."""

    return parse_soccer_ratings(resolve_base_data_file(base_data, "ratings"))


def parse_base_stadium_market_odds(base_data: Path) -> tuple[list[StadiumMarketOdd], Path]:
    """Parse the preferred stadium market source and return its path."""

    source_path = resolve_base_data_file(base_data, "stadium_market")
    return parse_stadium_market_odds(source_path), source_path


def parse_base_opta_predictions(base_data: Path) -> tuple[list[OptaPrediction], Path]:
    """Parse the preferred Opta predictions source and return its path."""

    source_path = resolve_base_data_file(base_data, "opta_predictions")
    return parse_opta_predictions(source_path), source_path


def parse_base_opta_standings(base_data: Path) -> tuple[list[OptaStandingRow], Path]:
    """Parse the preferred Opta standings source and return its path."""

    source_path = resolve_base_data_file(base_data, "opta_standings")
    return parse_opta_standings(source_path), source_path


def parse_matches(path: Path) -> list[Match]:
    """Parse the FIFA schedule text into canonical match records."""

    matches: list[Match] = []
    phase = ""
    current_date = ""
    group_match_id = 1

    for raw_line in path.read_text(encoding="utf-8").splitlines():
        line = raw_line.strip()
        if not line:
            continue

        if "Group Stage" in line:
            phase = "Group"
            continue
        if "Round of 32" in line:
            phase = "R32"
            continue
        if "Round of 16" in line:
            phase = "R16"
            continue
        if "quarter-final" in line:
            phase = "QF"
            continue
        if "semi-final" in line:
            phase = "SF"
            continue
        if "bronze final" in line:
            phase = "Bronze"
            continue
        if "FIFA World Cup 2026 Final" in line:
            phase = "Final"
            continue
        if DATE_RE.match(line):
            current_date = line
            continue

        stadium = _stadium_suffix(line)
        if stadium is None:
            continue

        if phase == "Group":
            matches.append(_parse_group_match(group_match_id, current_date, line, stadium))
            group_match_id += 1
        else:
            matches.append(_parse_knockout_match(current_date, phase, line, stadium))

    return matches


def parse_soccer_ratings(path: Path) -> dict[str, TeamRating]:
    """Parse ratings and expose both source names and schedule aliases."""

    ratings: dict[str, TeamRating] = {}
    for line in path.read_text(encoding="utf-8").splitlines():
        match = RATING_RE.match(line)
        if not match:
            continue
        team, confederation, rating_text = match.groups()
        rating = TeamRating(
            team=team,
            confederation=confederation,
            rating=float(rating_text),
            source_team=team,
        )
        ratings[team] = rating

    for schedule_name, rating_name in TEAM_RATING_ALIASES.items():
        if rating_name in ratings:
            source = ratings[rating_name]
            ratings[schedule_name] = TeamRating(
                team=schedule_name,
                confederation=source.confederation,
                rating=source.rating,
                source_team=source.source_team,
            )

    return ratings


def parse_stadium_market_odds(path: Path) -> list[StadiumMarketOdd]:
    """Parse final-market stadium odds from the user-provided text file."""

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    odds: list[StadiumMarketOdd] = []
    index = 1 if lines and lines[0].lower().startswith("stadion z") else 0

    while index < len(lines):
        bookmaker_stadium = lines[index]
        if index + 1 >= len(lines):
            raise ValueError(f"Missing odds for stadium {bookmaker_stadium!r}")
        decimal_odds = float(lines[index + 1])
        try:
            stadium = BOOKMAKER_STADIUM_ALIASES[bookmaker_stadium]
        except KeyError as exc:
            raise ValueError(f"Unknown bookmaker stadium label: {bookmaker_stadium}") from exc
        odds.append(
            StadiumMarketOdd(
                stadium=stadium,
                bookmaker_stadium=bookmaker_stadium,
                decimal_odds=decimal_odds,
            )
        )
        index += 2

    return odds


def parse_opta_predictions(path: Path) -> list[OptaPrediction]:
    """Parse copied Opta stage-probability table text."""

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    predictions: list[OptaPrediction] = []
    index = 0
    while index < len(lines):
        line = lines[index]
        if not line.startswith("team logo"):
            index += 1
            continue
        source_team = line.removeprefix("team logo").strip()
        if index + 1 >= len(lines):
            raise ValueError(f"Missing Opta probabilities for team {source_team}")
        values = re.findall(r"\d+(?:\.\d+)?%", lines[index + 1])
        if len(values) != 7:
            raise ValueError(f"Expected 7 Opta probabilities for team {source_team}, found {len(values)}")
        probabilities = [_parse_percent(value) for value in values]
        predictions.append(
            OptaPrediction(
                team=OPTA_TEAM_ALIASES.get(source_team, source_team),
                source_team=source_team,
                top_group=probabilities[0],
                l32=probabilities[1],
                l16=probabilities[2],
                qf=probabilities[3],
                sf=probabilities[4],
                final=probabilities[5],
                champion=probabilities[6],
            )
        )
        index += 2

    return predictions


def parse_opta_standings(path: Path) -> list[OptaStandingRow]:
    """Parse copied Opta group standings and third-place ranking text."""

    lines = [line.strip() for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]
    rows: list[OptaStandingRow] = []
    current_group: str | None = None
    current_table_type = ""
    rank_by_table: dict[tuple[str, str], int] = {}
    team_groups: dict[str, str] = {}

    index = 0
    while index < len(lines):
        line = lines[index]
        group_match = re.match(r"^Group ([A-L])$", line)
        if group_match:
            current_group = group_match.group(1)
            current_table_type = "group"
            index += 1
            continue
        if line == "3rd Place Ranking":
            current_group = None
            current_table_type = "third_place_snapshot"
            index += 1
            continue
        if not line.startswith("team logo"):
            index += 1
            continue
        if current_table_type == "":
            raise ValueError(f"Opta standings team row found before table header: {line}")
        if index == 0 or index + 1 >= len(lines):
            raise ValueError(f"Incomplete Opta standings row near: {line}")

        raw_pos = _parse_int_token(lines[index - 1])
        source_team = line.removeprefix("team logo").strip()
        team = OPTA_TEAM_ALIASES.get(source_team, source_team)
        stats = re.split(r"\s+", lines[index + 1])
        if len(stats) < 10:
            raise ValueError(f"Expected standings stats for {source_team}, found: {lines[index + 1]}")
        xpts = float(stats[-2])
        qual = _parse_percent(stats[-1])
        table_key = (current_table_type, current_group or "")
        rank_by_table[table_key] = rank_by_table.get(table_key, 0) + 1
        row_group = current_group if current_table_type == "group" else team_groups.get(team)
        row = OptaStandingRow(
            table_type=current_table_type,
            group=row_group,
            team=team,
            source_team=source_team,
            raw_pos=raw_pos,
            row_rank=rank_by_table[table_key],
            xpts=xpts,
            qual=qual,
        )
        rows.append(row)
        if current_table_type == "group" and current_group is not None:
            team_groups[team] = current_group
        index += 2

    return rows


def _stadium_suffix(line: str) -> str | None:
    for stadium in sorted(FIFA_STADIUMS, key=len, reverse=True):
        if line.endswith(stadium):
            return stadium
    return None


def _parse_percent(value: str) -> float:
    return float(value.removesuffix("%")) / 100.0


def _parse_int_token(value: str) -> int:
    match = re.search(r"\d+", value)
    if match is None:
        raise ValueError(f"Expected integer token, found: {value}")
    return int(match.group(0))


def _parse_group_match(match_id: int, date: str, line: str, stadium: str) -> Match:
    before_stadium = line[: -len(stadium)].strip(" -\u2013")
    group_match = re.search(r"Group\s+([A-L])", before_stadium)
    if group_match is None:
        raise ValueError(f"Missing group marker in line: {line}")

    pair_text = before_stadium[: group_match.start()].strip(" -\u2013")
    teams = re.split(r"\s+v\s+", pair_text, maxsplit=1)
    if len(teams) != 2:
        raise ValueError(f"Cannot parse teams in line: {line}")

    return Match(
        match_id=match_id,
        phase="Group",
        date=date,
        group=group_match.group(1),
        team_home=teams[0],
        team_away=teams[1],
        stadium=stadium,
    )


def _parse_knockout_match(date: str, phase: str, line: str, stadium: str) -> Match:
    match_id_match = re.match(r"Match\s+(\d+)\s+[\u2013-]\s+(.+)$", line)
    if match_id_match is None:
        raise ValueError(f"Cannot parse knockout match id in line: {line}")

    match_id = int(match_id_match.group(1))
    before_stadium = line[: -len(stadium)].strip(" -\u2013")
    slot_text = re.sub(r"^Match\s+\d+\s+[\u2013-]\s+", "", before_stadium)
    slots = re.split(r"\s+v\s+", slot_text, maxsplit=1)
    if len(slots) != 2:
        raise ValueError(f"Cannot parse knockout slots in line: {line}")

    return Match(
        match_id=match_id,
        phase=phase,
        date=date,
        slot_home=slots[0],
        slot_away=slots[1],
        stadium=stadium,
    )
