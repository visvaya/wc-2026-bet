import csv
from pathlib import Path

from wc2026bet.parsers import parse_base_matches
from wc2026bet.processed import build_processed_data, write_odds_template


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def test_build_processed_data_writes_canonical_source_csvs(tmp_path: Path, base_data: Path) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    manual_dir = work_dir / "manual"

    result = build_processed_data(base_data, processed_dir, manual_dir)

    assert result["matches"] == 104
    assert result["teams"] == 48
    assert result["stadiums"] == 16
    assert result["stadium_market_odds"] == 16
    assert result["opta_predictions"] == 48
    assert result["opta_standings"] == 60

    matches = read_csv(processed_dir / "matches.csv")
    teams = read_csv(processed_dir / "teams.csv")
    stadiums = read_csv(processed_dir / "stadiums.csv")
    market_odds = read_csv(processed_dir / "stadium_market_odds.csv")
    opta_predictions = read_csv(processed_dir / "opta_predictions.csv")
    opta_standings = read_csv(processed_dir / "opta_standings.csv")

    assert len(matches) == 104
    assert sum(row["is_group_stage"] == "true" for row in matches) == 72
    assert len(teams) == 48
    assert len(stadiums) == 16
    assert len(market_odds) == 16
    assert len(opta_predictions) == 48
    assert len(opta_standings) == 60
    assert sum(row["table_type"] == "group" for row in opta_standings) == 48
    assert sum(row["table_type"] == "third_place_snapshot" for row in opta_standings) == 12
    assert market_odds[0]["market"] == "highest_average_goals"
    assert set(opta_predictions[0]) == {
        "team",
        "top_group",
        "l32",
        "l16",
        "qf",
        "sf",
        "final",
        "champion",
        "source_file",
        "captured_at",
    }
    assert set(opta_standings[0]) == {
        "table_type",
        "group",
        "team",
        "source_team",
        "raw_pos",
        "row_rank",
        "xpts",
        "qual",
        "source_file",
        "captured_at",
    }


def test_write_odds_template_creates_all_group_market_selection_rows(tmp_path: Path, base_data: Path) -> None:
    work_dir = tmp_path
    output_path = work_dir / "odds_template.csv"
    first_match = parse_base_matches(base_data)[0]

    count = write_odds_template(base_data, output_path)

    rows = read_csv(output_path)
    assert count == 792
    assert len(rows) == 792
    assert {row["market"] for row in rows} == {
        "1X2",
        "over_under_0_5",
        "over_under_1_5",
        "over_under_2_5",
        "btts",
    }
    assert {row["selection"] for row in rows if row["market"] == "1X2"} == {
        "home",
        "draw",
        "away",
    }
    assert {row["selection"] for row in rows if row["market"] == "btts"} == {"yes", "no"}
    assert rows[0]["match_id"] == "1"
    assert rows[0]["team_home"] == first_match.team_home
    assert rows[0]["team_away"] == first_match.team_away


def test_build_processed_data_copies_valid_manual_odds(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    processed_dir = work_dir / "processed"
    manual_dir = work_dir / "manual"
    manual_dir.mkdir()
    template_path = manual_dir / "odds.csv"
    write_odds_template(synthetic_base_data, template_path)

    rows = read_csv(template_path)
    for row in rows:
        row["decimal_odds"] = _odds_for(row["market"], row["selection"])
        row["source_file"] = "manual-test"
        row["captured_at"] = "2026-06-09T12:00:00"
    _write_rows(template_path, rows)

    result = build_processed_data(synthetic_base_data, processed_dir, manual_dir)

    odds = read_csv(processed_dir / "odds.csv")
    assert result["odds"] == 792
    assert len(odds) == 792
    assert {row["manual_override"] for row in odds} == {"true"}


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


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
