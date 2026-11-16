"""Implementations of the command-line subcommands; each returns a process exit code."""

from __future__ import annotations

from pathlib import Path

from wc2026bet.bridge import train_rating_goal_bridge
from wc2026bet.csv_io import read_csv
from wc2026bet.decision_report import build_decision_report
from wc2026bet.fitting import fit_group_match_params
from wc2026bet.group_simulation import simulate_group_stage
from wc2026bet.ocr import promote_review_odds, write_odds_ocr_outputs
from wc2026bet.parsers import (
    parse_base_matches,
    parse_base_soccer_ratings,
    parse_base_stadium_market_odds,
)
from wc2026bet.processed import build_processed_data, write_odds_template
from wc2026bet.regulations import parse_r32_third_place_mapping, write_r32_third_place_mapping
from wc2026bet.reports import build_group_stage_reports
from wc2026bet.sensitivity import run_sensitivity
from wc2026bet.text_odds import promote_text_odds, write_text_odds_review
from wc2026bet.tournament_simulation import simulate_tournament


def validate_command(base_data: Path, processed: Path, manual: Path) -> int:
    matches = parse_base_matches(base_data)
    ratings = parse_base_soccer_ratings(base_data)
    stadium_odds, stadium_source = parse_base_stadium_market_odds(base_data)

    group_matches = [match for match in matches if match.phase == "Group"]
    group_teams = {team for match in group_matches for team in match.teams}
    missing_ratings = sorted(team for team in group_teams if team not in ratings)

    checks = {
        "matches": len(matches) == 104,
        "group_matches": len(group_matches) == 72,
        "teams": len(group_teams) == 48,
        "stadiums": len({match.stadium for match in matches}) == 16,
        "stadium_market": len(stadium_odds) == 16,
        "ratings_cover_group_teams": not missing_ratings,
    }

    processed_checks = _processed_checks(processed)
    checks.update(processed_checks)
    r32_mapping_path = manual / "r32_third_place_mapping.csv"
    r32_mapping_count = 0
    if r32_mapping_path.exists():
        try:
            r32_mapping_count = len(parse_r32_third_place_mapping(r32_mapping_path))
            checks["r32_third_place_mapping"] = r32_mapping_count == 495
        except ValueError:
            checks["r32_third_place_mapping"] = False
    else:
        checks["r32_third_place_mapping"] = False

    failed = [name for name, passed in checks.items() if not passed]
    if failed:
        print("Validation failed:")
        for name in failed:
            print(f"- {name}")
        if missing_ratings:
            print(f"Missing ratings: {', '.join(missing_ratings)}")
        return 1

    print("Validation passed:")
    print(f"- matches: {len(matches)}")
    print(f"- group matches: {len(group_matches)}")
    print(f"- group teams: {len(group_teams)}")
    print(f"- stadiums: {len({match.stadium for match in matches})}")
    print(f"- stadium market odds: {len(stadium_odds)} from {stadium_source.name}")
    if processed.exists():
        print(f"- processed dir: {processed}")
    if (manual / "odds.csv").exists():
        print(f"- manual odds: {manual / 'odds.csv'}")
    print(f"- R32 third-place mapping: {r32_mapping_count}")
    return 0


def build_data_command(base_data: Path, out: Path, manual: Path) -> int:
    result = build_processed_data(base_data, out, manual)
    print("Processed data written:")
    for name, count in result.items():
        print(f"- {name}: {count}")
    return 0


def odds_template_command(base_data: Path, out: Path) -> int:
    count = write_odds_template(base_data, out)
    print(f"Odds template written: {out}")
    print(f"- rows: {count}")
    return 0


def fit_score_params_command(
    base_data: Path,
    odds: Path,
    out: Path,
    config_out: Path,
    no_global_tilts: bool,
) -> int:
    if not odds.exists():
        print(f"Odds file not found: {odds}")
        print("Run build-data after preparing data/manual/odds.csv, or pass --odds explicitly.")
        return 1
    count = fit_group_match_params(
        base_data,
        odds,
        out,
        config_output_path=config_out,
        fit_global_tilts=not no_global_tilts,
    )
    print(f"Match score params written: {out}")
    print(f"- score model config: {config_out}")
    print(f"- rows: {count}")
    return 0


def train_goal_bridge_command(processed: Path) -> int:
    required = (
        processed / "matches.csv",
        processed / "teams.csv",
        processed / "match_score_params.csv",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        print("Cannot train goal bridge. Missing files:")
        for path in missing:
            print(f"- {path}")
        return 1
    try:
        bridge = train_rating_goal_bridge(processed)
    except ValueError as exc:
        print(f"Goal bridge training failed: {exc}")
        return 1
    print("Goal bridge trained:")
    print(f"- processed: {processed}")
    print(f"- teams: {len(bridge.ratings)}")
    print(f"- observations: {bridge.observations}")
    print(f"- ridge alpha: {bridge.ridge_alpha:.6f}")
    print(f"- training rmse: {bridge.training_rmse:.6f}")
    print(f"- cv rmse: {bridge.cv_rmse:.6f}")
    return 0


def group_reports_command(processed: Path, out: Path) -> int:
    required = (processed / "matches.csv", processed / "match_score_params.csv")
    missing = [path for path in required if not path.exists()]
    if missing:
        print("Cannot build group reports. Missing files:")
        for path in missing:
            print(f"- {path}")
        return 1
    counts = build_group_stage_reports(processed, out)
    print(f"Group-stage reports written: {out}")
    for name, count in counts.items():
        print(f"- {name}: {count}")
    return 0


def simulate_groups_command(processed: Path, out: Path, simulations: int, seed: int) -> int:
    required = (
        processed / "matches.csv",
        processed / "match_score_params.csv",
        processed / "opta_predictions.csv",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        print("Cannot simulate groups. Missing files:")
        for path in missing:
            print(f"- {path}")
        return 1
    try:
        counts = simulate_group_stage(processed, out, simulations=simulations, seed=seed)
    except ValueError as exc:
        print(f"Group simulation failed: {exc}")
        return 1
    print(f"Group-stage simulation reports written: {out}")
    print(f"- simulations: {simulations}")
    print(f"- seed: {seed}")
    for name, count in counts.items():
        print(f"- {name}: {count}")
    return 0


def simulate_tournament_command(
    processed: Path,
    manual: Path,
    out: Path,
    simulations: int,
    seed: int,
    extra_time_goal_multiplier: float,
    penalty_model: str,
    no_score_tilts: bool,
    value_threshold: float,
    calibration_model: str,
    baseline_probabilities: Path | None,
    opta_strength: float,
) -> int:
    required = (
        processed / "matches.csv",
        processed / "match_score_params.csv",
        processed / "stadium_market_odds.csv",
        processed / "team_goal_strengths.csv",
        processed / "rating_goal_bridge.csv",
        manual / "r32_third_place_mapping.csv",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        print("Cannot simulate tournament. Missing files:")
        for path in missing:
            print(f"- {path}")
        return 1
    try:
        counts = simulate_tournament(
            processed,
            manual,
            out,
            simulations=simulations,
            seed=seed,
            extra_time_goal_multiplier=extra_time_goal_multiplier,
            penalty_model=penalty_model,
            use_score_tilts=not no_score_tilts,
            value_threshold=value_threshold,
            calibration_model=calibration_model,
            baseline_probabilities_path=baseline_probabilities,
            opta_strength=opta_strength,
        )
    except ValueError as exc:
        print(f"Tournament simulation failed: {exc}")
        return 1
    print(f"Tournament simulation reports written: {out}")
    print(f"- simulations: {simulations}")
    print(f"- seed: {seed}")
    print(f"- penalty model: {penalty_model}")
    print(f"- score tilts: {'disabled' if no_score_tilts else 'enabled'}")
    print(f"- calibration model: {calibration_model}")
    for name, count in counts.items():
        print(f"- {name}: {count}")
    return 0


def build_decision_report_command(
    processed: Path,
    out: Path,
    report: Path,
    simulations: int,
    seed: int,
    extra_time_goal_multiplier: float,
    penalty_model: str,
    value_threshold: float,
) -> int:
    required = (
        processed / "match_score_params.csv",
        processed / "score_model_config.csv",
        processed / "rating_goal_bridge.csv",
        out / "stadium-average-ranking.csv",
        out / "stadium-total-ranking.csv",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        print("Cannot build decision report. Missing files:")
        for path in missing:
            print(f"- {path}")
        return 1
    try:
        count = build_decision_report(
            processed,
            out,
            report,
            simulations=simulations,
            seed=seed,
            extra_time_goal_multiplier=extra_time_goal_multiplier,
            penalty_model=penalty_model,
            value_threshold=value_threshold,
        )
    except ValueError as exc:
        print(f"Decision report failed: {exc}")
        return 1
    print(f"Decision report written: {report}")
    print(f"- reports: {count}")
    return 0


def run_sensitivity_command(
    processed: Path,
    manual: Path,
    out: Path,
    simulations: int,
    seed: int,
    value_threshold: float,
) -> int:
    required = (
        processed / "matches.csv",
        processed / "match_score_params.csv",
        processed / "stadium_market_odds.csv",
        processed / "team_goal_strengths.csv",
        processed / "rating_goal_bridge.csv",
        manual / "r32_third_place_mapping.csv",
    )
    missing = [path for path in required if not path.exists()]
    if missing:
        print("Cannot run sensitivity. Missing files:")
        for path in missing:
            print(f"- {path}")
        return 1
    try:
        counts = run_sensitivity(
            processed,
            manual,
            out,
            simulations=simulations,
            seed=seed,
            value_threshold=value_threshold,
        )
    except ValueError as exc:
        print(f"Sensitivity run failed: {exc}")
        return 1
    print(f"Sensitivity reports written: {out}")
    print(f"- simulations per scenario: {simulations}")
    print(f"- seed: {seed}")
    for name, count in counts.items():
        print(f"- {name}: {count}")
    main_output = out.parent if out.name == "sensitivity" else None
    if main_output is not None and (main_output / "stadium-average-ranking.csv").exists():
        build_decision_report(
            processed,
            main_output,
            main_output / "tournament-summary.md",
            simulations=200_000,
            seed=20260610,
            extra_time_goal_multiplier=0.30,
            penalty_model="coin_flip",
            value_threshold=value_threshold,
        )
        print(f"- refreshed decision report: {main_output / 'tournament-summary.md'}")
    return 0


def ocr_odds_command(
    base_data: Path,
    raw: Path,
    review: Path,
    crops: Path,
    match_order: Path,
    workers: int,
) -> int:
    try:
        count = write_odds_ocr_outputs(
            base_data,
            raw,
            review,
            crops,
            workers=workers,
            match_order_path=match_order,
        )
    except ValueError as exc:
        print(f"OCR failed: {exc}")
        return 1
    print("Odds OCR outputs written:")
    print(f"- raw: {raw}")
    print(f"- review: {review}")
    print(f"- crops: {crops}")
    print(f"- match order: {match_order}")
    print(f"- rows: {count}")
    return 0


def promote_odds_command(review: Path, base_data: Path, out: Path) -> int:
    try:
        count = promote_review_odds(review, base_data, out)
    except ValueError as exc:
        print(f"Odds promotion failed: {exc}")
        return 1
    print(f"Manual odds written: {out}")
    print(f"- rows: {count}")
    return 0


def parse_text_odds_command(
    source: Path,
    base_data: Path,
    market: str,
    out: Path,
    expected_matches: int,
) -> int:
    try:
        count = write_text_odds_review(
            source,
            base_data,
            market,
            out,
            expected_matches=expected_matches,
        )
    except ValueError as exc:
        print(f"Text odds parsing failed: {exc}")
        return 1
    print("Text odds review written:")
    print(f"- source: {source}")
    print(f"- market: {market}")
    print(f"- out: {out}")
    print(f"- rows: {count}")
    return 0


def promote_text_odds_command(
    manual: Path,
    base_data: Path,
    out: Path,
    audit: Path,
    expected_matches: int,
) -> int:
    try:
        count = promote_text_odds(
            manual,
            base_data,
            out,
            audit,
            expected_matches=expected_matches,
        )
    except ValueError as exc:
        print(f"Text odds promotion failed: {exc}")
        return 1
    print("Text odds promoted:")
    print(f"- manual: {manual}")
    print(f"- out: {out}")
    print(f"- audit: {audit}")
    print(f"- rows: {count}")
    return 0


def extract_r32_mapping_command(pdf: Path, out: Path, raw: Path) -> int:
    try:
        count = write_r32_third_place_mapping(pdf, out, raw)
    except (RuntimeError, ValueError) as exc:
        print(f"R32 mapping extraction failed: {exc}")
        return 1
    print("R32 third-place mapping extracted:")
    print(f"- pdf: {pdf}")
    print(f"- out: {out}")
    print(f"- raw: {raw}")
    print(f"- rows: {count}")
    return 0


def _processed_checks(processed: Path) -> dict[str, bool]:
    if not processed.exists():
        return {}
    checks = {}
    expected = (
        "matches.csv",
        "teams.csv",
        "stadiums.csv",
        "stadium_market_odds.csv",
        "opta_predictions.csv",
        "opta_standings.csv",
    )
    checks.update({f"processed_{filename}": (processed / filename).exists() for filename in expected})
    if (processed / "odds.csv").exists():
        checks["processed_odds_rows"] = len(read_csv(processed / "odds.csv")) == 792
    if (processed / "opta_predictions.csv").exists():
        checks["processed_opta_predictions_rows"] = len(read_csv(processed / "opta_predictions.csv")) == 48
    if (processed / "opta_standings.csv").exists():
        rows = read_csv(processed / "opta_standings.csv")
        checks["processed_opta_standings_rows"] = len(rows) == 60
        checks["processed_opta_standings_group_rows"] = sum(row["table_type"] == "group" for row in rows) == 48
        checks["processed_opta_standings_third_rows"] = (
            sum(row["table_type"] == "third_place_snapshot" for row in rows) == 12
        )
    if (processed / "match_score_params.csv").exists():
        checks["processed_match_score_params_rows"] = len(read_csv(processed / "match_score_params.csv")) == 72
    if (processed / "score_model_config.csv").exists():
        checks["processed_score_model_config_rows"] = len(read_csv(processed / "score_model_config.csv")) == 1
    if (processed / "team_goal_strengths.csv").exists():
        checks["processed_team_goal_strengths_rows"] = len(read_csv(processed / "team_goal_strengths.csv")) == 48
    if (processed / "rating_goal_bridge.csv").exists():
        checks["processed_rating_goal_bridge_rows"] = len(read_csv(processed / "rating_goal_bridge.csv")) == 1
    return checks
