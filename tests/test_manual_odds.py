import csv
from pathlib import Path

import pytest

from wc2026bet.manual_odds import parse_manual_odds
from wc2026bet.processed import write_odds_template


def test_manual_odds_rejects_missing_required_market_rows(tmp_path: Path, synthetic_base_data: Path) -> None:
    odds_path = _valid_odds_csv(tmp_path, synthetic_base_data)
    rows = _read_rows(odds_path)
    rows = [row for row in rows if not (row["match_id"] == "1" and row["market"] == "btts")]
    _write_rows(odds_path, rows)

    with pytest.raises(ValueError, match="Missing odds rows"):
        parse_manual_odds(odds_path, synthetic_base_data)


def test_manual_odds_rejects_non_positive_decimal_odds(tmp_path: Path, synthetic_base_data: Path) -> None:
    odds_path = _valid_odds_csv(tmp_path, synthetic_base_data)
    rows = _read_rows(odds_path)
    rows[0]["decimal_odds"] = "0"
    _write_rows(odds_path, rows)

    with pytest.raises(ValueError, match="positive decimal odds"):
        parse_manual_odds(odds_path, synthetic_base_data)


def test_manual_odds_rejects_non_monotonic_over_markets(tmp_path: Path, synthetic_base_data: Path) -> None:
    odds_path = _valid_odds_csv(tmp_path, synthetic_base_data)
    rows = _read_rows(odds_path)
    for row in rows:
        if row["match_id"] == "1" and row["market"] == "over_under_0_5":
            row["decimal_odds"] = {"over": "3.00", "under": "1.40"}[row["selection"]]
    _write_rows(odds_path, rows)

    with pytest.raises(ValueError, match="monotonic"):
        parse_manual_odds(odds_path, synthetic_base_data)


def _valid_odds_csv(tmp_path: Path, synthetic_base_data: Path) -> Path:
    odds_path = tmp_path / "odds.csv"
    write_odds_template(synthetic_base_data, odds_path)
    rows = _read_rows(odds_path)
    for row in rows:
        row["decimal_odds"] = _odds_for(row["market"], row["selection"])
        row["source_file"] = "manual-test"
        row["captured_at"] = "2026-06-09T12:00:00"
    _write_rows(odds_path, rows)
    return odds_path


def _odds_for(market: str, selection: str) -> str:
    if market == "1X2":
        return {"home": "2.10", "draw": "3.40", "away": "3.90"}[selection]
    if market == "btts":
        return {"yes": "1.95", "no": "1.95"}[selection]
    return {
        "over_under_0_5": {"over": "1.07", "under": "8.80"},
        "over_under_1_5": {"over": "1.38", "under": "3.05"},
        "over_under_2_5": {"over": "2.15", "under": "1.72"},
    }[market][selection]


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
