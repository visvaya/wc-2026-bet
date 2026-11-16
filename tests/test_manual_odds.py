from pathlib import Path

import pytest

from synthetic_data import odds_for, write_rows
from wc2026bet.csv_io import read_csv
from wc2026bet.manual_odds import parse_manual_odds
from wc2026bet.processed import write_odds_template


def test_manual_odds_rejects_missing_required_market_rows(tmp_path: Path, synthetic_base_data: Path) -> None:
    odds_path = _valid_odds_csv(tmp_path, synthetic_base_data)
    rows = read_csv(odds_path)
    rows = [row for row in rows if not (row["match_id"] == "1" and row["market"] == "btts")]
    write_rows(odds_path, rows)

    with pytest.raises(ValueError, match="Missing odds rows"):
        parse_manual_odds(odds_path, synthetic_base_data)


def test_manual_odds_rejects_non_positive_decimal_odds(tmp_path: Path, synthetic_base_data: Path) -> None:
    odds_path = _valid_odds_csv(tmp_path, synthetic_base_data)
    rows = read_csv(odds_path)
    rows[0]["decimal_odds"] = "0"
    write_rows(odds_path, rows)

    with pytest.raises(ValueError, match="positive decimal odds"):
        parse_manual_odds(odds_path, synthetic_base_data)


def test_manual_odds_rejects_non_monotonic_over_markets(tmp_path: Path, synthetic_base_data: Path) -> None:
    odds_path = _valid_odds_csv(tmp_path, synthetic_base_data)
    rows = read_csv(odds_path)
    for row in rows:
        if row["match_id"] == "1" and row["market"] == "over_under_0_5":
            row["decimal_odds"] = {"over": "3.00", "under": "1.40"}[row["selection"]]
    write_rows(odds_path, rows)

    with pytest.raises(ValueError, match="monotonic"):
        parse_manual_odds(odds_path, synthetic_base_data)


def _valid_odds_csv(tmp_path: Path, synthetic_base_data: Path) -> Path:
    odds_path = tmp_path / "odds.csv"
    write_odds_template(synthetic_base_data, odds_path)
    rows = read_csv(odds_path)
    for row in rows:
        row["decimal_odds"] = odds_for(row["market"], row["selection"])
        row["source_file"] = "manual-test"
        row["captured_at"] = "2026-06-09T12:00:00"
    write_rows(odds_path, rows)
    return odds_path
