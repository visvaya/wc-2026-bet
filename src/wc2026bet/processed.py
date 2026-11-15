"""Build canonical processed CSV files from source and manual inputs."""

from __future__ import annotations

import csv
from collections.abc import Mapping, Sequence
from datetime import datetime
from pathlib import Path

from wc2026bet.manual_odds import ODDS_FIELDS, REQUIRED_MARKET_SELECTIONS, parse_manual_odds
from wc2026bet.models import Match, OptaPrediction, OptaStandingRow, StadiumMarketOdd, TeamRating
from wc2026bet.parsers import (
    parse_base_matches,
    parse_base_opta_predictions,
    parse_base_opta_standings,
    parse_base_soccer_ratings,
    parse_base_stadium_market_odds,
)

MATCH_FIELDS = (
    "match_id",
    "phase",
    "group",
    "date",
    "team_home",
    "team_away",
    "slot_home",
    "slot_away",
    "stadium_fifa",
    "is_group_stage",
)
TEAM_FIELDS = ("team", "confederation", "rating", "source_team")
STADIUM_FIELDS = ("stadium_fifa", "scheduled_matches", "group_stage_matches")
STADIUM_MARKET_FIELDS = (
    "stadium_bookmaker",
    "stadium_fifa",
    "market",
    "decimal_odds",
    "source_file",
    "captured_at",
)
OPTA_FIELDS = (
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
)
OPTA_STANDINGS_FIELDS = (
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
)
ODDS_TEMPLATE_FIELDS = (
    "match_id",
    "date",
    "team_home",
    "team_away",
    "market",
    "selection",
    "decimal_odds",
    "source_file",
    "captured_at",
    "ocr_confidence",
    "manual_override",
)


def build_processed_data(base_data: Path, out_dir: Path, manual_dir: Path) -> dict[str, int]:
    """Write canonical processed CSV files and optional validated manual odds."""

    out_dir.mkdir(parents=True, exist_ok=True)
    matches = parse_base_matches(base_data)
    ratings = parse_base_soccer_ratings(base_data)
    stadium_market_odds, stadium_market_source = parse_base_stadium_market_odds(base_data)
    opta_predictions, opta_source = parse_base_opta_predictions(base_data)
    opta_standings, opta_standings_source = parse_base_opta_standings(base_data)
    group_teams = sorted({team for match in matches if match.phase == "Group" for team in match.teams})
    _validate_opta_coverage(opta_predictions, group_teams)
    _validate_opta_standings(opta_standings, opta_predictions, group_teams)

    _write_csv(out_dir / "matches.csv", MATCH_FIELDS, [_match_row(match) for match in matches])
    _write_csv(out_dir / "teams.csv", TEAM_FIELDS, [_team_row(team, ratings[team]) for team in group_teams])
    _write_csv(out_dir / "stadiums.csv", STADIUM_FIELDS, _stadium_rows(matches))
    _write_csv(
        out_dir / "stadium_market_odds.csv",
        STADIUM_MARKET_FIELDS,
        [_stadium_market_row(odd, stadium_market_source) for odd in stadium_market_odds],
    )
    _write_csv(
        out_dir / "opta_predictions.csv",
        OPTA_FIELDS,
        [_opta_row(prediction, opta_source) for prediction in opta_predictions],
    )
    _write_csv(
        out_dir / "opta_standings.csv",
        OPTA_STANDINGS_FIELDS,
        [_opta_standing_row(row, opta_standings_source) for row in opta_standings],
    )

    result = {
        "matches": len(matches),
        "teams": len(group_teams),
        "stadiums": len({match.stadium for match in matches}),
        "stadium_market_odds": len(stadium_market_odds),
        "opta_predictions": len(opta_predictions),
        "opta_standings": len(opta_standings),
    }

    manual_odds_path = manual_dir / "odds.csv"
    if manual_odds_path.exists():
        odds_rows = parse_manual_odds(manual_odds_path, base_data)
        _write_csv(out_dir / "odds.csv", ODDS_FIELDS, odds_rows)
        result["odds"] = len(odds_rows)

    return result


def write_odds_template(base_data: Path, output_path: Path) -> int:
    """Create a manual odds template for all group-stage markets."""

    output_path.parent.mkdir(parents=True, exist_ok=True)
    matches = [match for match in parse_base_matches(base_data) if match.phase == "Group"]
    rows = []
    for match in matches:
        for market, selections in REQUIRED_MARKET_SELECTIONS.items():
            for selection in selections:
                rows.append(
                    {
                        "match_id": str(match.match_id),
                        "date": match.date,
                        "team_home": match.team_home or "",
                        "team_away": match.team_away or "",
                        "market": market,
                        "selection": selection,
                        "decimal_odds": "",
                        "source_file": "",
                        "captured_at": "",
                        "ocr_confidence": "",
                        "manual_override": "true",
                    }
                )
    _write_csv(output_path, ODDS_TEMPLATE_FIELDS, rows)
    return len(rows)


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: Sequence[Mapping[str, object]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _match_row(match: Match) -> dict[str, object]:
    return {
        "match_id": match.match_id,
        "phase": match.phase,
        "group": match.group or "",
        "date": match.date,
        "team_home": match.team_home or "",
        "team_away": match.team_away or "",
        "slot_home": match.slot_home or "",
        "slot_away": match.slot_away or "",
        "stadium_fifa": match.stadium,
        "is_group_stage": "true" if match.phase == "Group" else "false",
    }


def _team_row(team: str, rating: TeamRating) -> dict[str, object]:
    return {
        "team": team,
        "confederation": rating.confederation,
        "rating": f"{rating.rating:.2f}",
        "source_team": rating.source_team,
    }


def _stadium_rows(matches: list[Match]) -> list[dict[str, object]]:
    rows = []
    for stadium in sorted({match.stadium for match in matches}):
        stadium_matches = [match for match in matches if match.stadium == stadium]
        rows.append(
            {
                "stadium_fifa": stadium,
                "scheduled_matches": len(stadium_matches),
                "group_stage_matches": sum(match.phase == "Group" for match in stadium_matches),
            }
        )
    return rows


def _stadium_market_row(odd: StadiumMarketOdd, source_path: Path) -> dict[str, object]:
    return {
        "stadium_bookmaker": odd.bookmaker_stadium,
        "stadium_fifa": odd.stadium,
        "market": odd.market,
        "decimal_odds": f"{odd.decimal_odds:.6g}",
        "source_file": source_path.name,
        "captured_at": _mtime_iso(source_path),
    }


def _opta_row(prediction: OptaPrediction, source_path: Path) -> dict[str, object]:
    return {
        "team": prediction.team,
        "top_group": f"{prediction.top_group:.6f}",
        "l32": f"{prediction.l32:.6f}",
        "l16": f"{prediction.l16:.6f}",
        "qf": f"{prediction.qf:.6f}",
        "sf": f"{prediction.sf:.6f}",
        "final": f"{prediction.final:.6f}",
        "champion": f"{prediction.champion:.6f}",
        "source_file": source_path.name,
        "captured_at": _mtime_iso(source_path),
    }


def _opta_standing_row(row: OptaStandingRow, source_path: Path) -> dict[str, object]:
    return {
        "table_type": row.table_type,
        "group": row.group or "",
        "team": row.team,
        "source_team": row.source_team,
        "raw_pos": row.raw_pos,
        "row_rank": row.row_rank,
        "xpts": f"{row.xpts:.6f}",
        "qual": f"{row.qual:.6f}",
        "source_file": source_path.name,
        "captured_at": _mtime_iso(source_path),
    }


def _validate_opta_coverage(predictions: list[OptaPrediction], group_teams: list[str]) -> None:
    prediction_teams = {prediction.team for prediction in predictions}
    expected_teams = set(group_teams)
    if len(predictions) != 48 or prediction_teams != expected_teams:
        missing = sorted(expected_teams - prediction_teams)
        extra = sorted(prediction_teams - expected_teams)
        raise ValueError(f"Opta predictions do not cover group teams. Missing={missing}; extra={extra}")


def _validate_opta_standings(
    standings: list[OptaStandingRow],
    predictions: list[OptaPrediction],
    group_teams: list[str],
) -> None:
    group_rows = [row for row in standings if row.table_type == "group"]
    third_rows = [row for row in standings if row.table_type == "third_place_snapshot"]
    if len(standings) != 60 or len(group_rows) != 48 or len(third_rows) != 12:
        raise ValueError(
            "Opta standings row counts are invalid. "
            f"total={len(standings)}, group={len(group_rows)}, third={len(third_rows)}"
        )
    expected_teams = set(group_teams)
    standing_teams = {row.team for row in group_rows}
    if standing_teams != expected_teams:
        missing = sorted(expected_teams - standing_teams)
        extra = sorted(standing_teams - expected_teams)
        raise ValueError(f"Opta standings do not cover group teams. Missing={missing}; extra={extra}")

    prediction_l32 = {prediction.team: prediction.l32 for prediction in predictions}
    mismatches = [row.team for row in group_rows if abs(row.qual - prediction_l32.get(row.team, -1.0)) > 1e-6]
    if mismatches:
        raise ValueError(f"Opta standings QUAL differs from Opta l32 for: {', '.join(mismatches[:5])}")


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
