from pathlib import Path

from wc2026bet.csv_io import fmt, read_csv, write_csv


def test_write_csv_creates_parent_and_round_trips(tmp_path: Path) -> None:
    path = tmp_path / "nested" / "dir" / "rows.csv"

    write_csv(path, ("team", "goals"), [{"team": "Mexico", "goals": 2}, {"team": "Curaçao", "goals": "0"}])

    assert read_csv(path) == [{"team": "Mexico", "goals": "2"}, {"team": "Curaçao", "goals": "0"}]
    assert path.read_bytes() == "team,goals\r\nMexico,2\r\nCuraçao,0\r\n".encode()


def test_fmt_rounds_to_six_decimals() -> None:
    assert fmt(1.23456789) == "1.234568"
    assert fmt(2) == "2.000000"
    assert fmt(-0.0000004) == "-0.000000"
