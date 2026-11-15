import csv
import re
from pathlib import Path

import pytest

from synthetic_data import write_group_schedule, write_match_result_text
from wc2026bet.constants import TEAM_RATING_ALIASES
from wc2026bet.parsers import parse_base_matches
from wc2026bet.text_odds import (
    parse_text_odds_file,
    promote_text_odds,
    write_text_odds_review,
)


@pytest.fixture
def real_match_result_source(real_base_data: Path) -> Path:
    return real_base_data / "match-result_oddschecker.txt"


def test_match_result_text_parser_maps_synthetic_group_matches_and_swaps_reversed_pairs(
    tmp_path: Path, synthetic_base_data: Path
) -> None:
    source = tmp_path / "match-result.txt"
    expected = write_match_result_text(source)

    rows = parse_text_odds_file(source, synthetic_base_data, "1X2")

    assert len(rows) == 216
    assert {row["mapping_status"] for row in rows} == {"matched"}
    assert {match_id: _odds_for_match(rows, match_id) for match_id in expected} == expected
    assert sum(row["reversed_order"] == "true" for row in rows) == 15 * 3


def test_write_text_odds_review_writes_synthetic_review_rows(tmp_path: Path, synthetic_base_data: Path) -> None:
    source = tmp_path / "match-result.txt"
    write_match_result_text(source)
    output = tmp_path / "odds_text_1x2.csv"

    count = write_text_odds_review(source, synthetic_base_data, "1X2", output)

    rows = _read_rows(output)
    assert count == len(rows) == 216
    assert rows[0]["source_team_home"] == "Team A2"
    assert rows[0]["team_home"] == "Team A1"


def test_text_parser_resolves_rating_source_names_to_schedule_names(tmp_path: Path) -> None:
    schedule_name, source_name = next(iter(TEAM_RATING_ALIASES.items()))
    base_data = write_group_schedule(tmp_path / "base-data", [(schedule_name, "Team X")])
    source = _write_one_match_text(
        tmp_path, "btts.txt", headers=("yes", "no"), home=source_name, away="Team X", odds=("1.81", "2.02")
    )

    rows = parse_text_odds_file(source, base_data, "btts", expected_matches=1)

    assert {row["team_home"] for row in rows} == {schedule_name}
    assert {row["source_team_home"] for row in rows} == {source_name}


@pytest.mark.real_data
def test_match_result_text_parser_maps_all_group_matches_by_team_pair(
    real_match_result_source: Path, real_base_data: Path
) -> None:
    rows = parse_text_odds_file(real_match_result_source, real_base_data, "1X2")

    assert len(rows) == 216
    assert {row["market"] for row in rows} == {"1X2"}
    assert len({row["match_id"] for row in rows}) == 72
    assert {row["mapping_status"] for row in rows} == {"matched"}
    assert _source_order_odds(rows) == _raw_1x2_blocks(real_match_result_source)
    for home, draw, away in _raw_1x2_blocks(real_match_result_source).values():
        # The book has a plausible overround, so no price was misread.
        assert 1.0 <= 1 / float(home) + 1 / float(draw) + 1 / float(away) <= 1.18


@pytest.mark.real_data
def test_match_result_text_parser_regresses_congo_uzbekistan_mapping(
    real_match_result_source: Path, real_base_data: Path
) -> None:
    rows = parse_text_odds_file(real_match_result_source, real_base_data, "1X2")
    raw = _raw_1x2_blocks(real_match_result_source)

    # Each schedule match carries the source block of the same teams, located by names.
    for (home, away), source_pair in {
        ("Congo DR", "Uzbekistan"): ("DR Congo", "Uzbekistan"),
        ("Algeria", "Austria"): ("Algeria", "Austria"),
    }.items():
        match_rows = _rows_for_teams(rows, home, away, real_base_data)
        assert _source_order_odds(match_rows) == {source_pair: raw[source_pair]}


@pytest.mark.real_data
def test_match_result_text_parser_resolves_oddschecker_team_aliases(
    real_match_result_source: Path, real_base_data: Path
) -> None:
    rows = parse_text_odds_file(real_match_result_source, real_base_data, "1X2")
    raw = _raw_1x2_blocks(real_match_result_source)

    for (home, away), source_pair in {
        ("Korea Republic", "Czechia"): ("South Korea", "Czech Republic"),
        ("Egypt", "IR Iran"): ("Egypt", "Iran"),
    }.items():
        match_rows = _rows_for_teams(rows, home, away, real_base_data)
        assert _source_order_odds(match_rows) == {source_pair: raw[source_pair]}


def test_match_result_text_parser_swaps_reversed_1x2_pairs(tmp_path: Path, synthetic_base_data: Path) -> None:
    source = tmp_path / "reversed.txt"
    source.write_text(
        "\n".join(
            [
                "Matchday, 1st Month",
                "home",
                "draw",
                "away",
                "20:00",
                "Team A2 logo",
                "Team A2",
                "Team A1 logo",
                "Team A1",
                "8.5",
                "4.6",
                "1.42",
                "Compare odds",
            ]
        ),
        encoding="utf-8",
    )

    rows = parse_text_odds_file(source, synthetic_base_data, "1X2", expected_matches=1)

    assert _odds_for_match(rows, "1") == {
        "home": "1.42",
        "draw": "4.6",
        "away": "8.5",
    }
    assert {row["reversed_order"] for row in rows} == {"true"}


def test_match_result_text_parser_fails_on_unknown_team(tmp_path: Path, synthetic_base_data: Path) -> None:
    source = tmp_path / "unknown.txt"
    source.write_text(
        "\n".join(
            [
                "Matchday, 1st Month",
                "home",
                "draw",
                "away",
                "20:00",
                "Atlantis logo",
                "Atlantis",
                "Team A1 logo",
                "Team A1",
                "8.5",
                "4.6",
                "1.42",
                "Compare odds",
            ]
        ),
        encoding="utf-8",
    )

    with pytest.raises(ValueError, match="Unknown team"):
        parse_text_odds_file(source, synthetic_base_data, "1X2", expected_matches=1)


@pytest.mark.real_data
def test_write_text_odds_review_writes_extra_review_columns(
    tmp_path: Path, real_match_result_source: Path, real_base_data: Path
) -> None:
    output = tmp_path / "odds_text_1x2.csv"

    count = write_text_odds_review(real_match_result_source, real_base_data, "1X2", output)

    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    assert count == 216
    assert len(rows) == 216
    assert {"source_team_home", "source_team_away", "mapping_status", "reversed_order"}.issubset(rows[0])


def test_text_parser_handles_two_way_over_under_market(tmp_path: Path, synthetic_base_data: Path) -> None:
    source = _write_one_match_text(
        tmp_path,
        "ou25.txt",
        headers=("over", "under"),
        home="Team A1",
        away="Team A2",
        odds=("1.82", "2.04"),
    )

    rows = parse_text_odds_file(source, synthetic_base_data, "over_under_2_5", expected_matches=1)

    assert _odds_for_match(rows, "1") == {"over": "1.82", "under": "2.04"}
    assert {row["market"] for row in rows} == {"over_under_2_5"}


def test_text_parser_handles_btts_market(tmp_path: Path, synthetic_base_data: Path) -> None:
    source = _write_one_match_text(
        tmp_path,
        "btts_oddschecker.txt",
        headers=("yes", "no"),
        home="Team A1",
        away="Team A2",
        odds=("1.93", "1.89"),
    )

    rows = parse_text_odds_file(source, synthetic_base_data, "btts", expected_matches=1)

    assert _odds_for_match(rows, "1") == {"yes": "1.93", "no": "1.89"}
    assert {row["market"] for row in rows} == {"btts"}


def test_promote_text_odds_writes_final_odds_and_audit(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    manual_dir = work_dir / "manual"
    manual_dir.mkdir()
    output = work_dir / "odds.csv"
    audit = work_dir / "audit.csv"
    _write_text_review(manual_dir / "odds_text_1x2.csv", "1X2", ("home", "draw", "away"), ("2.10", "3.40", "3.90"))
    _write_text_review(manual_dir / "odds_text_o25.csv", "over_under_2_5", ("over", "under"), ("2.15", "1.72"))
    _write_text_review(manual_dir / "odds_text_o15.csv", "over_under_1_5", ("over", "under"), ("1.38", "3.05"))
    _write_text_review(manual_dir / "odds_text_o05.csv", "over_under_0_5", ("over", "under"), ("1.07", "8.80"))
    _write_text_review(manual_dir / "odds_text_btts.csv", "btts", ("yes", "no"), ("1.95", "1.95"))

    count = promote_text_odds(manual_dir, synthetic_base_data, output, audit, expected_matches=1)

    output_rows = _read_rows(output)
    audit_rows = _read_rows(audit)
    assert count == 11
    assert len(output_rows) == 11
    assert set(output_rows[0]) == {
        "match_id",
        "market",
        "selection",
        "decimal_odds",
        "source_file",
        "captured_at",
        "ocr_confidence",
        "manual_override",
    }
    assert {row["status"] for row in audit_rows} == {"ok"}
    assert {row["parsed_matches"] for row in audit_rows} == {"1"}


def test_promote_text_odds_rejects_missing_market(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    manual_dir = work_dir / "manual"
    manual_dir.mkdir()

    with pytest.raises(ValueError, match="Missing text odds review files"):
        promote_text_odds(manual_dir, synthetic_base_data, work_dir / "odds.csv", expected_matches=1)


def test_promote_text_odds_rejects_duplicate_selection(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    manual_dir = work_dir / "manual"
    manual_dir.mkdir()
    _write_text_review(manual_dir / "odds_text_1x2.csv", "1X2", ("home", "home", "away"), ("2.10", "3.40", "3.90"))
    _write_text_review(manual_dir / "odds_text_o25.csv", "over_under_2_5", ("over", "under"), ("2.15", "1.72"))
    _write_text_review(manual_dir / "odds_text_o15.csv", "over_under_1_5", ("over", "under"), ("1.38", "3.05"))
    _write_text_review(manual_dir / "odds_text_o05.csv", "over_under_0_5", ("over", "under"), ("1.07", "8.80"))
    _write_text_review(manual_dir / "odds_text_btts.csv", "btts", ("yes", "no"), ("1.95", "1.95"))

    with pytest.raises(ValueError, match="Duplicate text odds rows"):
        promote_text_odds(manual_dir, synthetic_base_data, work_dir / "odds.csv", expected_matches=1)


def test_promote_text_odds_rejects_suspicious_overround(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    manual_dir = work_dir / "manual"
    manual_dir.mkdir()
    _write_text_review(manual_dir / "odds_text_1x2.csv", "1X2", ("home", "draw", "away"), ("2.10", "3.40", "3.90"))
    _write_text_review(manual_dir / "odds_text_o25.csv", "over_under_2_5", ("over", "under"), ("9.00", "9.00"))
    _write_text_review(manual_dir / "odds_text_o15.csv", "over_under_1_5", ("over", "under"), ("1.38", "3.05"))
    _write_text_review(manual_dir / "odds_text_o05.csv", "over_under_0_5", ("over", "under"), ("1.07", "8.80"))
    _write_text_review(manual_dir / "odds_text_btts.csv", "btts", ("yes", "no"), ("1.95", "1.95"))

    with pytest.raises(ValueError, match="Suspicious overround"):
        promote_text_odds(manual_dir, synthetic_base_data, work_dir / "odds.csv", expected_matches=1)


def _odds_for_match(rows: list[dict[str, str]], match_id: str) -> dict[str, str]:
    return {row["selection"]: row["decimal_odds"] for row in rows if row["match_id"] == match_id}


def _raw_1x2_blocks(source: Path) -> dict[tuple[str, str], tuple[str, str, str]]:
    """Independent read of the copied text: two team blocks, three prices, then the compare link."""

    pattern = r"^(.+) logo\n\1\n\s*\n(.+) logo\n\2\n\s*\n(\S+)\n(\S+)\n(\S+)\nCompare odds$"
    blocks = re.findall(pattern, source.read_text(encoding="utf-8"), re.M)
    return {(home, away): (odd_home, draw, odd_away) for home, away, odd_home, draw, odd_away in blocks}


def _source_order_odds(rows: list[dict[str, str]]) -> dict[tuple[str, str], tuple[str, str, str]]:
    """Parsed 1X2 odds keyed by the source team pair, in the order the source lists them."""

    result = {}
    for match_id in dict.fromkeys(row["match_id"] for row in rows):
        match_rows = [row for row in rows if row["match_id"] == match_id]
        odds = _odds_for_match(match_rows, match_id)
        prices = (odds["home"], odds["draw"], odds["away"])
        if match_rows[0]["reversed_order"] == "true":
            prices = prices[::-1]
        result[(match_rows[0]["source_team_home"], match_rows[0]["source_team_away"])] = prices
    return result


def _rows_for_teams(rows: list[dict[str, str]], home: str, away: str, base_data: Path) -> list[dict[str, str]]:
    """Rows of the schedule match between two named teams, located by names rather than by match number."""

    match_id = next(
        str(m.match_id) for m in parse_base_matches(base_data) if (m.team_home, m.team_away) == (home, away)
    )
    match_rows = [row for row in rows if row["match_id"] == match_id]
    assert {(row["team_home"], row["team_away"]) for row in match_rows} == {(home, away)}
    return match_rows


def _write_one_match_text(
    tmp_path: Path,
    filename: str,
    *,
    headers: tuple[str, ...],
    home: str,
    away: str,
    odds: tuple[str, ...],
) -> Path:
    path = tmp_path / filename
    path.write_text(
        "\n".join(
            [
                "Matchday, 1st Month",
                *headers,
                "20:00",
                f"{home} logo",
                home,
                f"{away} logo",
                away,
                *odds,
                "Compare odds",
            ]
        ),
        encoding="utf-8",
    )
    return path


def _write_text_review(
    path: Path,
    market: str,
    selections: tuple[str, ...],
    odds: tuple[str, ...],
) -> None:
    rows = []
    for selection, decimal_odds in zip(selections, odds, strict=True):
        rows.append(
            {
                "match_id": "1",
                "market": market,
                "selection": selection,
                "decimal_odds": decimal_odds,
                "source_file": path.name,
                "captured_at": "2026-06-10T12:00:00",
                "ocr_confidence": "1",
                "manual_override": "true",
                "date": "Matchday, 1st Month",
                "time": "20:00",
                "team_home": "Team A1",
                "team_away": "Team A2",
                "source_team_home": "Team A1",
                "source_team_away": "Team A2",
                "mapping_status": "matched",
                "reversed_order": "false",
            }
        )
    _write_rows(path, rows)


def _read_rows(path: Path) -> list[dict[str, str]]:
    with path.open(newline="", encoding="utf-8") as handle:
        return list(csv.DictReader(handle))


def _write_rows(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)
