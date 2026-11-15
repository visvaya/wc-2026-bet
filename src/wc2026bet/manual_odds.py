"""Manual odds CSV parsing and validation."""

from __future__ import annotations

import csv
from collections import defaultdict
from pathlib import Path

from wc2026bet.odds import proportional_devig
from wc2026bet.parsers import parse_base_matches

REQUIRED_MARKET_SELECTIONS = {
    "1X2": ("home", "draw", "away"),
    "over_under_0_5": ("over", "under"),
    "over_under_1_5": ("over", "under"),
    "over_under_2_5": ("over", "under"),
    "btts": ("yes", "no"),
}

ODDS_FIELDS = (
    "match_id",
    "market",
    "selection",
    "decimal_odds",
    "source_file",
    "captured_at",
    "ocr_confidence",
    "manual_override",
)


def parse_manual_odds(path: Path, base_data: Path) -> list[dict[str, str]]:
    """Parse and validate manually curated odds rows."""

    rows = _read_rows(path)
    group_match_ids = {str(match.match_id) for match in parse_base_matches(base_data) if match.phase == "Group"}
    _validate_required_columns(rows, path)
    _validate_rows(rows, group_match_ids)
    return [_canonical_row(row) for row in rows]


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _validate_required_columns(rows: list[dict[str, str]], path: Path) -> None:
    if not rows:
        raise ValueError(f"Manual odds file is empty: {path}")
    missing = [field for field in ODDS_FIELDS if field not in rows[0]]
    if missing:
        raise ValueError(f"Manual odds file is missing columns: {', '.join(missing)}")


def _validate_rows(rows: list[dict[str, str]], group_match_ids: set[str]) -> None:
    seen: dict[tuple[str, str], set[str]] = defaultdict(set)
    odds_by_match_market: dict[tuple[str, str], dict[str, float]] = defaultdict(dict)

    for row in rows:
        match_id = row["match_id"]
        market = row["market"]
        selection = row["selection"]
        if match_id not in group_match_ids:
            raise ValueError(f"Unknown or non-group match_id in manual odds: {match_id}")
        if market not in REQUIRED_MARKET_SELECTIONS:
            raise ValueError(f"Unknown odds market: {market}")
        if selection not in REQUIRED_MARKET_SELECTIONS[market]:
            raise ValueError(f"Unknown selection {selection!r} for market {market!r}")

        try:
            decimal_odds = float(row["decimal_odds"])
        except ValueError as exc:
            raise ValueError(f"Invalid decimal odds for match {match_id} {market} {selection}") from exc
        if decimal_odds <= 0:
            raise ValueError("Manual odds must contain positive decimal odds")

        seen[(match_id, market)].add(selection)
        odds_by_match_market[(match_id, market)][selection] = decimal_odds

    missing = []
    for match_id in sorted(group_match_ids, key=int):
        for market, selections in REQUIRED_MARKET_SELECTIONS.items():
            key = (match_id, market)
            missing_selections = set(selections) - seen[key]
            if missing_selections:
                missing.append(f"match {match_id} {market}: {', '.join(sorted(missing_selections))}")
    if missing:
        raise ValueError(f"Missing odds rows: {'; '.join(missing[:5])}")

    _validate_overrounds(odds_by_match_market)
    _validate_over_monotonicity(odds_by_match_market, group_match_ids)


def _validate_overrounds(odds_by_match_market: dict[tuple[str, str], dict[str, float]]) -> None:
    for (match_id, market), odds in odds_by_match_market.items():
        overround = sum(1.0 / value for value in odds.values())
        lower, upper = (0.98, 1.18)
        if not lower <= overround <= upper:
            raise ValueError(f"Suspicious overround for match {match_id} {market}: {overround:.3f}")


def _validate_over_monotonicity(
    odds_by_match_market: dict[tuple[str, str], dict[str, float]],
    group_match_ids: set[str],
) -> None:
    for match_id in group_match_ids:
        over_05 = proportional_devig(odds_by_match_market[(match_id, "over_under_0_5")])["over"]
        over_15 = proportional_devig(odds_by_match_market[(match_id, "over_under_1_5")])["over"]
        over_25 = proportional_devig(odds_by_match_market[(match_id, "over_under_2_5")])["over"]
        if not over_05 >= over_15 >= over_25:
            raise ValueError(
                f"Over probabilities must be monotonic for match {match_id}: "
                f"{over_05:.3f}, {over_15:.3f}, {over_25:.3f}"
            )


def _canonical_row(row: dict[str, str]) -> dict[str, str]:
    canonical = {field: row.get(field, "") for field in ODDS_FIELDS}
    canonical["decimal_odds"] = f"{float(canonical['decimal_odds']):.6g}"
    canonical["manual_override"] = "true" if canonical["manual_override"].lower() != "false" else "false"
    return canonical
