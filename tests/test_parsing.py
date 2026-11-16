import re
from pathlib import Path

import pytest

from synthetic_data import opta_l32, stadium_market_odds
from wc2026bet.constants import BOOKMAKER_STADIUM_ALIASES, FIFA_STADIUMS, TEAM_RATING_ALIASES
from wc2026bet.parsers import (
    OPTA_TEAM_ALIASES,
    parse_base_matches,
    parse_base_opta_predictions,
    parse_base_soccer_ratings,
    parse_base_stadium_market_odds,
    parse_opta_predictions,
    parse_opta_standings,
    parse_soccer_ratings,
    parse_stadium_market_odds,
    resolve_base_data_file,
)


def test_match_parser_detects_expected_tournament_shape(base_data: Path) -> None:
    matches = parse_base_matches(base_data)

    assert len(matches) == 104
    assert sum(match.phase == "Group" for match in matches) == 72
    assert sum(match.phase == "R32" for match in matches) == 16
    assert sum(match.phase == "R16" for match in matches) == 8
    assert sum(match.phase == "QF" for match in matches) == 4
    assert sum(match.phase == "SF" for match in matches) == 2
    assert sum(match.phase == "Bronze" for match in matches) == 1
    assert sum(match.phase == "Final" for match in matches) == 1
    assert len({match.stadium for match in matches}) == 16
    assert len({team for match in matches if match.phase == "Group" for team in match.teams}) == 48


@pytest.mark.real_data
def test_match_parser_keeps_market_relevant_stadium_counts(real_base_data: Path) -> None:
    matches = parse_base_matches(real_base_data)
    stadium_counts: dict[str, int] = {}
    for match in matches:
        stadium_counts[match.stadium] = stadium_counts.get(match.stadium, 0) + 1

    assert stadium_counts["Dallas Stadium"] == 9
    assert stadium_counts["Atlanta Stadium"] == 8
    assert stadium_counts["Los Angeles Stadium"] == 8
    assert stadium_counts["New York New Jersey Stadium"] == 8


def test_ratings_cover_all_group_stage_teams_after_aliases(base_data: Path) -> None:
    matches = parse_base_matches(base_data)
    ratings = parse_base_soccer_ratings(base_data)
    group_teams = {team for match in matches if match.phase == "Group" for team in match.teams}

    missing = sorted(team for team in group_teams if team not in ratings)

    assert len(group_teams) == 48
    assert missing == []


def test_stadium_market_odds_map_to_fifa_stadiums(base_data: Path) -> None:
    odds, source_path = parse_base_stadium_market_odds(base_data)

    assert len(odds) == 16
    assert source_path.name == "stadiums_superbet.txt"
    assert {odd.market for odd in odds} == {"highest_average_goals"}
    assert {odd.stadium for odd in odds} == set(FIFA_STADIUMS)


def test_synthetic_stadium_market_odds_keep_written_values(synthetic_base_data: Path) -> None:
    odds, _ = parse_base_stadium_market_odds(synthetic_base_data)

    expected = {BOOKMAKER_STADIUM_ALIASES[label]: value for label, value in stadium_market_odds().items()}
    assert {odd.stadium: odd.decimal_odds for odd in odds} == expected


@pytest.mark.real_data
def test_real_stadium_market_odds_keep_snapshot_values(real_base_data: Path) -> None:
    odds, source_path = parse_base_stadium_market_odds(real_base_data)
    # Independent read: a label line followed by a decimal line.
    raw = {label: float(value) for label, value in re.findall(r"^(.+)\n(\d+\.\d+)$", _read(source_path), re.M)}

    assert {odd.bookmaker_stadium: odd.decimal_odds for odd in odds} == raw
    assert all(1.0 < odd.decimal_odds < 1000.0 for odd in odds)
    houston_label = next(label for label in raw if label.startswith("NRG Stadium"))
    assert next(odd.decimal_odds for odd in odds if odd.stadium == "Houston Stadium") == raw[houston_label]


def test_base_data_file_resolver_prefers_source_labeled_names(base_data: Path) -> None:
    assert resolve_base_data_file(base_data, "matches").name == "matches_fifa.txt"
    assert resolve_base_data_file(base_data, "ratings").name == "rating_soccer-rating.txt"
    assert resolve_base_data_file(base_data, "stadium_market").name == "stadiums_superbet.txt"


def test_base_data_file_resolver_falls_back_and_rejects_unknown_kinds(tmp_path: Path) -> None:
    (tmp_path / "stadiums.txt").write_text("", encoding="utf-8")

    assert resolve_base_data_file(tmp_path, "stadium_market").name == "stadiums.txt"
    with pytest.raises(ValueError, match="Unknown base-data file kind"):
        resolve_base_data_file(tmp_path, "weather")
    with pytest.raises(FileNotFoundError, match="matches_fifa.txt, matches.txt"):
        resolve_base_data_file(tmp_path, "matches")


def test_opta_predictions_cover_group_teams_after_aliases(base_data: Path) -> None:
    predictions, source_path = parse_base_opta_predictions(base_data)
    matches = parse_base_matches(base_data)
    group_teams = {team for match in matches if match.phase == "Group" for team in match.teams}

    assert source_path.name == "predictions-table_opta.txt"
    assert len(predictions) == 48
    assert {prediction.team for prediction in predictions} == group_teams


def test_synthetic_opta_files_keep_written_l32_and_qual(synthetic_base_data: Path) -> None:
    predictions, _ = parse_base_opta_predictions(synthetic_base_data)
    standings = parse_opta_standings(synthetic_base_data / "standings_opta.txt")

    expected = pytest.approx(opta_l32())
    assert {prediction.team: prediction.l32 for prediction in predictions} == expected
    assert {row.team: row.qual for row in standings if row.table_type == "group"} == expected


def test_opta_parsers_map_source_names_to_schedule_names(tmp_path: Path) -> None:
    source_name, schedule_name = next(iter(OPTA_TEAM_ALIASES.items()))
    stats = "0 0 0 0 0 0 0 0 4.00 60.00%"
    probabilities = "30.00% 60.00% 30.00% 15.00% 8.00% 4.00% 2.00%"

    predictions = parse_opta_predictions(_write_lines(tmp_path / "p.txt", f"team logo{source_name}", probabilities))
    standings = parse_opta_standings(
        _write_lines(
            tmp_path / "s.txt",
            "Group A",
            "1",
            f"team logo{source_name}",
            stats,
            "3rd Place Ranking",
            "1",
            f"team logo{source_name}",
            stats,
        )
    )

    assert [(p.team, p.source_team) for p in predictions] == [(schedule_name, source_name)]
    assert [(row.team, row.source_team, row.group) for row in standings] == [(schedule_name, source_name, "A")] * 2


@pytest.mark.real_data
def test_real_opta_predictions_keep_snapshot_values_and_aliases(real_base_data: Path) -> None:
    predictions, source_path = parse_base_opta_predictions(real_base_data)
    # Independent read: the second percentage after each team line is the L32 probability.
    raw = re.findall(r"^team logo(.+)\n\S+%\s+(\S+)%", _read(source_path), re.M)

    assert {p.source_team: p.l32 for p in predictions} == pytest.approx({t: float(v) / 100 for t, v in raw})
    for p in predictions:
        assert 0.0 <= p.champion <= p.final <= p.sf <= p.qf <= p.l16 <= p.l32 <= 1.0
        assert p.top_group <= p.l32
    assert (
        next(prediction.team for prediction in predictions if prediction.source_team == "Korea Rep") == "Korea Republic"
    )


def test_parse_opta_standings_reads_groups_and_third_place_snapshot(base_data: Path) -> None:
    rows = parse_opta_standings(base_data / "standings_opta.txt")

    group_rows = [row for row in rows if row.table_type == "group"]
    third_rows = [row for row in rows if row.table_type == "third_place_snapshot"]
    assert len(rows) == 60
    assert len(group_rows) == 48
    assert len(third_rows) == 12
    assert {row.group for row in group_rows} == set("ABCDEFGHIJKL")
    # A third-place row carries the group of the team's group-table row.
    groups_by_team = {row.team: row.group for row in group_rows}
    assert all(row.group == groups_by_team[row.team] for row in third_rows)


@pytest.mark.real_data
def test_real_opta_standings_keep_snapshot_values_and_aliases(real_base_data: Path) -> None:
    path = real_base_data / "standings_opta.txt"
    rows = parse_opta_standings(path)
    # Independent read: position line, team line, stats line ending in xPTS and QUAL%.
    raw = re.findall(r"^(\d+)\s*\nteam logo(.+)\n.*\s(\S+)\s+(\S+)%$", _read(path), re.M)

    # pytest.approx entries compare equal to floats, which mypy cannot see in the element types.
    expected: list[tuple[object, ...]] = [
        (int(pos), team, pytest.approx(float(xpts)), pytest.approx(float(qual) / 100)) for pos, team, xpts, qual in raw
    ]
    assert [(row.raw_pos, row.source_team, row.xpts, row.qual) for row in rows] == expected
    group_rows = [row for row in rows if row.table_type == "group"]
    # 32 of the 48 teams reach the round of 32, so the QUAL column sums to 32 up to rounding.
    assert sum(row.qual for row in group_rows) == pytest.approx(32, abs=0.05)
    assert {row.team for row in group_rows} >= {
        "Korea Republic",
        "USA",
        "IR Iran",
        "Bosnia and Herzegovina",
    }
    assert next(row.group for row in group_rows if row.team == "Mexico") == "A"
    # Row counts and third-place groups: test_parse_opta_standings_reads_groups_and_third_place_snapshot.
    third_rows = [row for row in rows if row.table_type == "third_place_snapshot"]
    assert [row.row_rank for row in third_rows] == list(range(1, len(third_rows) + 1))
    assert all(row.row_rank in range(1, 5) for row in group_rows)


def test_soccer_ratings_expose_schedule_aliases(tmp_path: Path) -> None:
    schedule_name, rating_name = next(iter(TEAM_RATING_ALIASES.items()))
    path = _write_lines(tmp_path / "ratings.txt", "Header", f"1.  {rating_name}  EU  1999.50", "not a rating row")

    ratings = parse_soccer_ratings(path)

    assert set(ratings) == {rating_name, schedule_name}
    assert ratings[schedule_name].rating == 1999.5
    assert ratings[schedule_name].source_team == rating_name
    assert ratings[schedule_name].team == schedule_name


def test_stadium_market_parser_rejects_unknown_labels_and_missing_odds(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Unknown bookmaker stadium label"):
        parse_stadium_market_odds(_write_lines(tmp_path / "unknown.txt", "Unknown Arena", "5.00"))
    with pytest.raises(ValueError, match="Missing odds for stadium"):
        parse_stadium_market_odds(_write_lines(tmp_path / "missing.txt", "Unknown Arena"))


def test_opta_predictions_parser_requires_seven_probabilities(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Expected 7 Opta probabilities"):
        parse_opta_predictions(_write_lines(tmp_path / "short.txt", "team logoTeam X", "10.00% 20.00%"))
    with pytest.raises(ValueError, match="Missing Opta probabilities"):
        parse_opta_predictions(_write_lines(tmp_path / "missing.txt", "team logoTeam X"))


def test_opta_standings_parser_rejects_malformed_rows(tmp_path: Path) -> None:
    stats = "0 0 0 0 0 0 0 0 1.00 50.00%"
    with pytest.raises(ValueError, match="before table header"):
        parse_opta_standings(_write_lines(tmp_path / "headless.txt", "1", "team logoTeam X", stats))
    with pytest.raises(ValueError, match="Expected standings stats"):
        parse_opta_standings(_write_lines(tmp_path / "short.txt", "Group A", "1", "team logoTeam X", "0 1.00 50.00%"))


def _read(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def _write_lines(path: Path, *lines: str) -> Path:
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return path
