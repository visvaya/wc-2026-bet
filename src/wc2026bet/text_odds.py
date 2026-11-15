"""Parse copied Oddschecker text into reviewable odds CSV rows."""

from __future__ import annotations

import csv
import re
import unicodedata
from collections import defaultdict
from datetime import datetime
from pathlib import Path

from wc2026bet.constants import TEAM_RATING_ALIASES
from wc2026bet.manual_odds import ODDS_FIELDS, REQUIRED_MARKET_SELECTIONS
from wc2026bet.models import Match
from wc2026bet.parsers import parse_base_matches

TEXT_ODDS_REVIEW_FIELDS = (
    *ODDS_FIELDS,
    "date",
    "time",
    "team_home",
    "team_away",
    "source_team_home",
    "source_team_away",
    "mapping_status",
    "reversed_order",
)
TEXT_ODDS_REVIEW_FILES = {
    "1X2": "odds_text_1x2.csv",
    "over_under_2_5": "odds_text_o25.csv",
    "over_under_1_5": "odds_text_o15.csv",
    "over_under_0_5": "odds_text_o05.csv",
    "btts": "odds_text_btts.csv",
}
TEXT_ODDS_AUDIT_FIELDS = (
    "market",
    "source_file",
    "expected_matches",
    "parsed_matches",
    "selection_rows",
    "overround_min",
    "overround_avg",
    "overround_max",
    "status",
    "warnings",
)

DATE_RE = re.compile(r"^[A-Za-z]+,\s+\d{1,2}(?:st|nd|rd|th)\s+[A-Za-z]+$")
TIME_RE = re.compile(r"^\d{2}:\d{2}$")
DECIMAL_RE = re.compile(r"^\d+(?:[.,]\d+)?$")
HEADER_LINES = {
    "home",
    "draw",
    "away",
    "over",
    "under",
    "yes",
    "no",
}


def parse_text_odds_file(
    source_path: Path,
    base_data: Path,
    market: str,
    *,
    expected_matches: int = 72,
) -> list[dict[str, str]]:
    """Parse copied Oddschecker text and return review CSV rows."""

    if market not in REQUIRED_MARKET_SELECTIONS:
        raise ValueError(f"Unknown odds market: {market}")

    selections = REQUIRED_MARKET_SELECTIONS[market]
    group_matches = [match for match in parse_base_matches(base_data) if match.phase == "Group"]
    resolver = _MatchResolver(group_matches)
    captured_at = _mtime_iso(source_path)
    rows: list[dict[str, str]] = []
    seen_matches: set[int] = set()

    for entry in _parse_entries(source_path, len(selections)):
        match, canonical_home, canonical_away = resolver.resolve(entry.team_home, entry.team_away)
        reversed_order = (canonical_home, canonical_away) == (match.team_away, match.team_home)
        if match.match_id in seen_matches:
            raise ValueError(f"Duplicate match pair in {source_path.name}: {match.team_home} v {match.team_away}")
        seen_matches.add(match.match_id)

        odds_by_selection = dict(zip(selections, entry.odds, strict=True))
        if market == "1X2" and reversed_order:
            odds_by_selection = {
                "home": odds_by_selection["away"],
                "draw": odds_by_selection["draw"],
                "away": odds_by_selection["home"],
            }

        for selection in selections:
            rows.append(
                {
                    "match_id": str(match.match_id),
                    "market": market,
                    "selection": selection,
                    "decimal_odds": odds_by_selection[selection],
                    "source_file": source_path.name,
                    "captured_at": captured_at,
                    "ocr_confidence": "1",
                    "manual_override": "true",
                    "date": entry.date,
                    "time": entry.time,
                    "team_home": match.team_home or "",
                    "team_away": match.team_away or "",
                    "source_team_home": entry.team_home,
                    "source_team_away": entry.team_away,
                    "mapping_status": "matched",
                    "reversed_order": "true" if reversed_order else "false",
                }
            )

    if len(seen_matches) != expected_matches:
        raise ValueError(f"Expected {expected_matches} matches for {market}, parsed {len(seen_matches)}")
    return rows


def write_text_odds_review(
    source_path: Path,
    base_data: Path,
    market: str,
    output_path: Path,
    *,
    expected_matches: int = 72,
) -> int:
    """Write a review CSV from copied Oddschecker text."""

    rows = parse_text_odds_file(
        source_path,
        base_data,
        market,
        expected_matches=expected_matches,
    )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=TEXT_ODDS_REVIEW_FIELDS)
        writer.writeheader()
        writer.writerows(rows)
    return len(rows)


def promote_text_odds(
    manual_dir: Path,
    base_data: Path,
    output_path: Path,
    audit_path: Path | None = None,
    *,
    expected_matches: int = 72,
) -> int:
    """Promote complete text review CSVs into canonical manual odds."""

    audit_output = audit_path or manual_dir / "odds_text_audit.csv"
    expected_files = {market: manual_dir / filename for market, filename in TEXT_ODDS_REVIEW_FILES.items()}
    missing_files = [str(path) for path in expected_files.values() if not path.exists()]
    if missing_files:
        raise ValueError(f"Missing text odds review files: {', '.join(missing_files)}")

    group_match_ids = {str(match.match_id) for match in parse_base_matches(base_data) if match.phase == "Group"}
    canonical_rows: list[dict[str, str]] = []
    audit_rows: list[dict[str, str]] = []
    seen_keys: set[tuple[str, str, str]] = set()

    for market, path in expected_files.items():
        rows = _read_csv(path)
        market_rows, audit_row = _validate_text_market_rows(
            market,
            path,
            rows,
            group_match_ids,
            seen_keys,
            expected_matches,
        )
        canonical_rows.extend(market_rows)
        audit_rows.append(audit_row)

    _write_csv(output_path, ODDS_FIELDS, canonical_rows)
    _write_csv(audit_output, TEXT_ODDS_AUDIT_FIELDS, audit_rows)
    return len(canonical_rows)


class _TextOddsEntry:
    def __init__(
        self,
        *,
        date: str,
        time: str,
        team_home: str,
        team_away: str,
        odds: tuple[str, ...],
    ) -> None:
        self.date = date
        self.time = time
        self.team_home = team_home
        self.team_away = team_away
        self.odds = odds


class _MatchResolver:
    def __init__(self, matches: list[Match]) -> None:
        self._team_lookup = _team_lookup(matches)
        self._matches_by_pair = {_pair_key(match.team_home or "", match.team_away or ""): match for match in matches}

    def resolve(self, team_home: str, team_away: str) -> tuple[Match, str, str]:
        canonical_home = self._resolve_team(team_home)
        canonical_away = self._resolve_team(team_away)
        key = _pair_key(canonical_home, canonical_away)
        try:
            match = self._matches_by_pair[key]
        except KeyError as exc:
            raise ValueError(f"Unknown group-stage pair: {team_home} v {team_away}") from exc
        return match, canonical_home, canonical_away

    def _resolve_team(self, team: str) -> str:
        key = _normalize_label(team)
        try:
            return self._team_lookup[key]
        except KeyError as exc:
            raise ValueError(f"Unknown team in copied odds text: {team}") from exc


def _parse_entries(source_path: Path, selection_count: int) -> list[_TextOddsEntry]:
    lines = [line.strip() for line in source_path.read_text(encoding="utf-8").splitlines()]
    entries: list[_TextOddsEntry] = []
    current_date = ""
    index = 0

    while index < len(lines):
        line = lines[index]
        if not line:
            index += 1
            continue
        if DATE_RE.match(line):
            current_date = line
            index += 1
            continue
        if _is_header(line):
            index += 1
            continue
        if not TIME_RE.match(line):
            index += 1
            continue

        if not current_date:
            raise ValueError(f"Missing date before match time {line} in {source_path.name}")
        block, index = _collect_match_block(lines, index + 1)
        entries.append(_parse_match_block(current_date, line, block, selection_count, source_path))

    return entries


def _collect_match_block(lines: list[str], index: int) -> tuple[list[str], int]:
    block: list[str] = []
    while index < len(lines):
        line = lines[index].strip()
        index += 1
        if line == "Compare odds":
            break
        if line:
            block.append(line)
    return block, index


def _parse_match_block(
    date: str,
    time: str,
    block: list[str],
    selection_count: int,
    source_path: Path,
) -> _TextOddsEntry:
    cleaned = [line for line in block if not _is_logo_line(line) and not _is_header(line)]
    odds_positions = [index for index, line in enumerate(cleaned) if _is_decimal(line)]
    if len(odds_positions) != selection_count:
        raise ValueError(
            f"Expected {selection_count} odds for {date} {time} in {source_path.name}, found {len(odds_positions)}"
        )

    first_odd_index = odds_positions[0]
    team_lines = cleaned[:first_odd_index]
    if len(team_lines) != 2:
        raise ValueError(f"Expected two teams for {date} {time} in {source_path.name}, found {team_lines!r}")

    odds = tuple(_format_decimal_odd(cleaned[index]) for index in odds_positions)
    return _TextOddsEntry(
        date=date,
        time=time,
        team_home=team_lines[0],
        team_away=team_lines[1],
        odds=odds,
    )


def _team_lookup(matches: list[Match]) -> dict[str, str]:
    lookup: dict[str, str] = {}
    for match in matches:
        for team in match.teams:
            lookup[_normalize_label(team)] = team
    for schedule_name, source_name in TEAM_RATING_ALIASES.items():
        if _normalize_label(schedule_name) in lookup:
            lookup[_normalize_label(source_name)] = schedule_name
    lookup[_normalize_label("DR Congo")] = "Congo DR"
    lookup[_normalize_label("Cape Verde")] = "Cabo Verde"
    lookup[_normalize_label("South Korea")] = "Korea Republic"
    lookup[_normalize_label("Iran")] = "IR Iran"
    lookup[_normalize_label("Turkey")] = "Türkiye"
    lookup[_normalize_label("Curacao")] = "Curaçao"
    lookup[_normalize_label("Ivory Coast")] = "Côte d'Ivoire"
    return lookup


def _pair_key(team_home: str, team_away: str) -> tuple[str, str]:
    first, second = sorted((_normalize_label(team_home), _normalize_label(team_away)))
    return first, second


def _normalize_label(value: str) -> str:
    normalized = unicodedata.normalize("NFKD", value)
    ascii_value = "".join(char for char in normalized if not unicodedata.combining(char))
    return re.sub(r"[^a-z0-9]+", "", ascii_value.casefold())


def _is_decimal(value: str) -> bool:
    return DECIMAL_RE.match(value) is not None


def _is_header(value: str) -> bool:
    return value.casefold() in HEADER_LINES


def _is_logo_line(value: str) -> bool:
    return value.casefold().endswith(" logo")


def _format_decimal_odd(value: str) -> str:
    return f"{float(value.replace(',', '.')):.6g}"


def _validate_text_market_rows(
    market: str,
    path: Path,
    rows: list[dict[str, str]],
    group_match_ids: set[str],
    seen_keys: set[tuple[str, str, str]],
    expected_matches: int,
) -> tuple[list[dict[str, str]], dict[str, str]]:
    if not rows:
        raise ValueError(f"Text odds review is empty: {path}")
    _validate_review_columns(rows[0], path)

    selections = REQUIRED_MARKET_SELECTIONS[market]
    selection_rows_by_match: dict[str, dict[str, dict[str, str]]] = defaultdict(dict)
    canonical_rows: list[dict[str, str]] = []
    warnings: list[str] = []

    for row in rows:
        if row["market"] != market:
            raise ValueError(f"Unexpected market in {path}: {row['market']}")
        if row.get("mapping_status") != "matched":
            raise ValueError(f"Unresolved text odds row in {path}: match {row.get('match_id', '')}")
        if row["match_id"] not in group_match_ids:
            raise ValueError(f"Unknown or non-group match_id in {path}: {row['match_id']}")
        if row["selection"] not in selections:
            raise ValueError(f"Unexpected selection in {path}: {row['selection']}")

        key = (row["match_id"], row["market"], row["selection"])
        if key in seen_keys or row["selection"] in selection_rows_by_match[row["match_id"]]:
            raise ValueError(f"Duplicate text odds rows for match {row['match_id']} {market} {row['selection']}")
        seen_keys.add(key)
        selection_rows_by_match[row["match_id"]][row["selection"]] = row
        canonical_rows.append(_canonical_odds_row(row))

    parsed_match_ids = set(selection_rows_by_match)
    if len(parsed_match_ids) != expected_matches:
        raise ValueError(f"Expected {expected_matches} matches for {market}, found {len(parsed_match_ids)} in {path}")
    if expected_matches == len(group_match_ids):
        missing = sorted(group_match_ids - parsed_match_ids, key=int)
        if missing:
            raise ValueError(f"Missing text odds matches for {market}: {', '.join(missing[:5])}")

    overrounds = []
    for match_id, selection_rows in selection_rows_by_match.items():
        missing_selections = set(selections) - set(selection_rows)
        if missing_selections:
            raise ValueError(
                f"Missing selections for match {match_id} {market}: {', '.join(sorted(missing_selections))}"
            )
        odds = {selection: float(selection_rows[selection]["decimal_odds"]) for selection in selections}
        overround = sum(1.0 / value for value in odds.values())
        if not 0.98 <= overround <= 1.18:
            raise ValueError(f"Suspicious overround for match {match_id} {market}: {overround:.3f}")
        overrounds.append(overround)

    if expected_matches != len(group_match_ids):
        warnings.append("partial_expected_matches")

    return canonical_rows, {
        "market": market,
        "source_file": path.name,
        "expected_matches": str(expected_matches),
        "parsed_matches": str(len(parsed_match_ids)),
        "selection_rows": str(len(canonical_rows)),
        "overround_min": f"{min(overrounds):.6f}",
        "overround_avg": f"{(sum(overrounds) / len(overrounds)):.6f}",
        "overround_max": f"{max(overrounds):.6f}",
        "status": "ok",
        "warnings": ";".join(warnings),
    }


def _validate_review_columns(row: dict[str, str], path: Path) -> None:
    required = (*ODDS_FIELDS, "mapping_status")
    missing = [field for field in required if field not in row]
    if missing:
        raise ValueError(f"Text odds review is missing columns in {path}: {', '.join(missing)}")


def _canonical_odds_row(row: dict[str, str]) -> dict[str, str]:
    return {
        "match_id": row["match_id"],
        "market": row["market"],
        "selection": row["selection"],
        "decimal_odds": _format_decimal_odd(row["decimal_odds"]),
        "source_file": row["source_file"],
        "captured_at": row["captured_at"],
        "ocr_confidence": row["ocr_confidence"],
        "manual_override": "true" if row["manual_override"].lower() != "false" else "false",
    }


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
