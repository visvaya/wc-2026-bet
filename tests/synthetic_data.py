"""Deterministic synthetic tournament snapshots for tests.

Writes files in the formats the parsers read, with invented team names and generated numbers,
so the default test run needs no third-party snapshots. Stadium labels come from
`wc2026bet.constants`, because the parsers only accept those.
"""

from __future__ import annotations

import csv
import itertools
import random
from pathlib import Path

import fitz  # PyMuPDF; the src modules use the same untyped name

from wc2026bet.constants import BOOKMAKER_STADIUM_ALIASES, FIFA_STADIUMS
from wc2026bet.regulations import R32_MAPPING_FIELDS, SLOT_FIELDS

SEED = 20260101
GROUPS = "ABCDEFGHIJKL"
TEAMS_BY_GROUP = {group: [f"Team {group}{index}" for index in range(1, 5)] for group in GROUPS}
# Six matchdays of round-robin pairs inside a group of four (indices into TEAMS_BY_GROUP).
ROUND_ROBIN = ((0, 1), (2, 3), (0, 2), (1, 3), (0, 3), (1, 2))
CONFEDERATIONS = ("AA", "BB", "CC", "DD")
THIRD_PLACE_WINNER_GROUPS = tuple(field[-1] for field in SLOT_FIELDS)


def group_matches() -> list[tuple[str, str, str]]:
    """Group-stage fixtures as (group, home, away) in schedule order."""

    return [
        (group, TEAMS_BY_GROUP[group][home], TEAMS_BY_GROUP[group][away])
        for home, away in ROUND_ROBIN
        for group in GROUPS
    ]


def write_base_data(base_data: Path) -> Path:
    """Write a synthetic `base-data` directory and return it."""

    rng = _rng()
    base_data.mkdir(parents=True, exist_ok=True)
    (base_data / "matches_fifa.txt").write_text(_schedule_text(), encoding="utf-8")
    (base_data / "rating_soccer-rating.txt").write_text(_ratings_text(rng), encoding="utf-8")
    (base_data / "stadiums_superbet.txt").write_text(_stadium_market_text(), encoding="utf-8")
    l32 = opta_l32()
    (base_data / "predictions-table_opta.txt").write_text(_opta_predictions_text(rng, l32), encoding="utf-8")
    (base_data / "standings_opta.txt").write_text(_opta_standings_text(rng, l32), encoding="utf-8")
    return base_data


def stadium_market_odds() -> dict[str, float]:
    """Decimal odds written for each bookmaker stadium label, rounded as the file shows them."""

    rng = _rng()
    return {label: round(rng.uniform(5, 30), 2) for label in BOOKMAKER_STADIUM_ALIASES}


def opta_l32() -> dict[str, float]:
    """Opta probability of reaching the round of 32 per team, rounded as the files show them (also QUAL)."""

    rng = _rng()
    return {team: round(rng.uniform(0.2, 0.99), 4) for teams in TEAMS_BY_GROUP.values() for team in teams}


def write_group_schedule(base_data: Path, pairs: list[tuple[str, str]]) -> Path:
    """Write a schedule holding only the given group-stage pairs, all in group A."""

    base_data.mkdir(parents=True, exist_ok=True)
    lines = ["Group Stage fixtures", "Matchday, 1 Month 2000"]
    lines += [f"{home} v {away} - Group A - {FIFA_STADIUMS[0]}" for home, away in pairs]
    (base_data / "matches_fifa.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")
    return base_data


def write_manual_data(manual_dir: Path) -> Path:
    """Write a synthetic `data/manual` directory holding a valid R32 third-place mapping."""

    manual_dir.mkdir(parents=True, exist_ok=True)
    write_r32_mapping_csv(manual_dir / "r32_third_place_mapping.csv", r32_mapping_rows())
    return manual_dir


def r32_mapping_rows() -> list[dict[str, str]]:
    """One row per set of 8 qualified third-placed groups, each group assigned to one slot."""

    rows = []
    for option, combination in enumerate(itertools.combinations(GROUPS, 8), start=1):
        assigned = combination[1:] + combination[:1]
        row = {
            "option": str(option),
            "qualified_third_groups": "".join(combination),
            "source_file": "synthetic",
            "source_page": "1",
        }
        row.update({field: f"3{group}" for field, group in zip(SLOT_FIELDS, assigned, strict=True)})
        rows.append(row)
    return rows


def write_match_result_text(path: Path) -> dict[str, dict[str, str]]:
    """Write copied-page 1X2 text for every group match; return the odds by match id in schedule orientation.

    Every fifth match is listed away team first, as the source pages sometimes do.
    """

    rng = _rng()
    expected: dict[str, dict[str, str]] = {}
    lines = []
    for index, (_, home, away) in enumerate(group_matches()):
        if index % 4 == 0:
            lines += [f"Matchday, {index // 4 + 1}th Month", "", "home", "draw", "away"]
        odds = {"home": f"{rng.uniform(1.3, 6):.2f}", "draw": f"{rng.uniform(3, 4.5):.2f}"}
        odds["away"] = f"{rng.uniform(1.3, 6):.2f}"
        expected[str(index + 1)] = {selection: f"{float(value):.6g}" for selection, value in odds.items()}
        shown = (away, home, odds["away"], odds["home"]) if index % 5 == 0 else (home, away, odds["home"], odds["away"])
        lines += [f"{12 + index % 10}:00", f"{shown[0]} logo", shown[0], "", f"{shown[1]} logo", shown[1], ""]
        lines += [shown[2], odds["draw"], shown[3], "Compare odds"]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")
    return expected


def write_r32_mapping_csv(path: Path, rows: list[dict[str, str]]) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=R32_MAPPING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)


def write_annex_c_pdf(path: Path, rows: list[dict[str, str]]) -> None:
    """Write a text page, then the mapping rows as ruled tables (option column, then one column per slot)."""

    cell_width, row_height, left, top, rows_per_page = 50, 13, 40, 40, 55
    doc = fitz.open()
    doc.new_page().insert_text((left, top), "Synthetic regulations without mapping rows")
    for start in range(0, len(rows), rows_per_page):
        table = [["Option", *(field.removeprefix("vs_") for field in SLOT_FIELDS)]]
        table += [
            [row["option"], *(row[field] for field in SLOT_FIELDS)] for row in rows[start : start + rows_per_page]
        ]
        right, bottom = left + len(table[0]) * cell_width, top + len(table) * row_height
        shape = doc.new_page().new_shape()
        for row_index, cells in enumerate(table):
            for column, text in enumerate(cells):
                position = (left + column * cell_width + 3, top + (row_index + 1) * row_height - 3)
                shape.insert_text(position, text, fontsize=8)
        for y in range(top, bottom + 1, row_height):
            shape.draw_line((left, y), (right, y))
        for x in range(left, right + 1, cell_width):
            shape.draw_line((x, top), (x, bottom))
        shape.finish(color=(0, 0, 0), width=0.5)
        shape.commit()
    doc.save(path)


def _rng() -> random.Random:
    return random.Random(SEED)  # noqa: S311 - reproducible test data, not cryptography


def _schedule_text() -> str:
    stadiums = list(FIFA_STADIUMS)
    lines = ["Synthetic schedule source", "", "Synthetic Group Stage fixtures"]
    for index, (group, home, away) in enumerate(group_matches()):
        if index % 4 == 0:
            lines += ["", f"Matchday, {index // 4 + 1} Month 2000"]
        lines.append(f"{home} v {away} - Group {group} - {stadiums[index % len(stadiums)]}")

    phases = (
        ("Synthetic Round of 32 fixtures", _round_of_32_slots()),
        ("Synthetic Round of 16 fixtures", _winner_pairs(73, 8)),
        ("Synthetic quarter-final fixtures", _winner_pairs(89, 4)),
        ("Synthetic semi-final fixtures", _winner_pairs(97, 2)),
        ("Synthetic bronze final", [("Runner-up match 101", "Runner-up match 102")]),
        ("FIFA World Cup 2026 Final", [("Winner match 101", "Winner match 102")]),
    )
    match_id = 73
    for header, slots in phases:
        lines += ["", header, f"Matchday, {match_id - 50} Month 2000"]
        for home, away in slots:
            lines.append(f"Match {match_id} - {home} v {away} - {stadiums[match_id % len(stadiums)]}")
            match_id += 1
    return "\n".join(lines) + "\n"


def _round_of_32_slots() -> list[tuple[str, str]]:
    slots = []
    for group in THIRD_PLACE_WINNER_GROUPS:
        candidates = "/".join(other for other in GROUPS if other != group)
        slots.append((f"Group {group} winners", f"Group {candidates} third place"))
    # The remaining four winners meet runners-up; both runner-up spellings appear in real schedules.
    slots += [
        ("Group C winners", "Group F runners-up"),
        ("Group F winners", "Group C runners up"),
        ("Group H winners", "Group J runners-up"),
        ("Group J winners", "Group H runners-up"),
    ]
    remaining = [group for group in GROUPS if group not in "CFHJ"]
    slots += [
        (f"Group {a} runners-up", f"Group {b} runners-up") for a, b in itertools.batched(remaining, 2, strict=True)
    ]
    return slots


def _winner_pairs(first_match: int, count: int) -> list[tuple[str, str]]:
    return [(f"Winner match {first_match + 2 * i}", f"Winner match {first_match + 2 * i + 1}") for i in range(count)]


def _ratings_text(rng: random.Random) -> str:
    teams = [team for teams in TEAMS_BY_GROUP.values() for team in teams] + ["Team Z1", "Team Z2"]
    ratings = sorted(((rng.uniform(1500, 2300), team) for team in teams), reverse=True)
    lines = [" Synthetic Ratings"]
    for rank, (rating, team) in enumerate(ratings, start=1):
        lines.append(f"{rank}.\t{team}\t\t{rng.choice(CONFEDERATIONS)}\t{rating:.2f}")
    return "\n".join(lines) + "\n"


def _stadium_market_text() -> str:
    lines = ["Stadion z synthetic header", ""]
    for label, odds in stadium_market_odds().items():
        lines += [label, f"{odds:.2f}", ""]
    return "\n".join(lines)


def _percent(value: float) -> str:
    return f"{value * 100:.2f}%"


def _opta_predictions_text(rng: random.Random, l32: dict[str, float]) -> str:
    lines = ["table", "team", "top group", "L32", "L16", "QF", "SF", "Final", "champ"]
    for team, qualify in l32.items():
        stages = [rng.uniform(0.05, qualify), qualify]
        for _ in range(5):
            stages.append(stages[-1] * rng.uniform(0.3, 0.7))
        lines += [f"team logo{team}", "\t".join(_percent(value) for value in stages)]
    return "\n".join(lines) + "\n"


def _opta_standings_text(rng: random.Random, l32: dict[str, float]) -> str:
    header = ["pos", "team", "p", "w", "d", "l", "gf", "ga", "gd", "pts", "xpts", "qual"]
    lines = []

    def team_row(position: int, team: str) -> list[str]:
        stats = ["0"] * 8 + [f"{rng.uniform(1, 7):.2f}", _percent(l32[team])]
        return [f"{position}\t", f"team logo{team}", "\t".join(stats)]

    for group, teams in TEAMS_BY_GROUP.items():
        lines += [f"Group {group}", "show viz", "", *header]
        for position, team in enumerate(teams, start=1):
            lines += team_row(position, team)
    lines += ["3rd Place Ranking", *header]
    for position, teams in enumerate(TEAMS_BY_GROUP.values(), start=1):
        lines += team_row(position, teams[2])
    return "\n".join(lines) + "\n"
