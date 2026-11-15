"""Argument parser for the command-line interface."""

from __future__ import annotations

import argparse
from pathlib import Path


def build_parser() -> argparse.ArgumentParser:
    """Build the parser with one subcommand per pipeline stage."""

    parser = argparse.ArgumentParser(prog="wc2026bet")
    subparsers = parser.add_subparsers(dest="command", required=True)

    validate_parser = subparsers.add_parser("validate", help="Validate immutable base-data inputs")
    validate_parser.add_argument("--base-data", default="base-data", type=Path)
    validate_parser.add_argument("--processed", default="data/processed", type=Path)
    validate_parser.add_argument("--manual", default="data/manual", type=Path)

    build_parser = subparsers.add_parser("build-data", help="Build canonical processed CSV files")
    build_parser.add_argument("--base-data", default="base-data", type=Path)
    build_parser.add_argument("--out", default="data/processed", type=Path)
    build_parser.add_argument("--manual", default="data/manual", type=Path)

    template_parser = subparsers.add_parser("odds-template", help="Write a manual odds CSV template")
    template_parser.add_argument("--base-data", default="base-data", type=Path)
    template_parser.add_argument("--out", default="data/manual/odds_template.csv", type=Path)

    fit_parser = subparsers.add_parser("fit-score-params", help="Fit group match score parameters")
    fit_parser.add_argument("--base-data", default="base-data", type=Path)
    fit_parser.add_argument("--odds", default="data/processed/odds.csv", type=Path)
    fit_parser.add_argument("--out", default="data/processed/match_score_params.csv", type=Path)
    fit_parser.add_argument("--config-out", default="data/processed/score_model_config.csv", type=Path)
    fit_parser.add_argument("--no-global-tilts", action="store_true")

    bridge_parser = subparsers.add_parser(
        "train-goal-bridge",
        help="Train the rating-to-goals bridge for knockout-stage lambdas",
    )
    bridge_parser.add_argument("--processed", default="data/processed", type=Path)

    reports_parser = subparsers.add_parser("group-reports", help="Build group-stage goal reports")
    reports_parser.add_argument("--processed", default="data/processed", type=Path)
    reports_parser.add_argument("--out", default="outputs", type=Path)

    simulate_groups_parser = subparsers.add_parser(
        "simulate-groups",
        help="Run group-stage Monte Carlo reports",
    )
    simulate_groups_parser.add_argument("--processed", default="data/processed", type=Path)
    simulate_groups_parser.add_argument("--out", default="outputs", type=Path)
    simulate_groups_parser.add_argument("--simulations", default=50_000, type=int)
    simulate_groups_parser.add_argument("--seed", default=20260610, type=int)

    simulate_tournament_parser = subparsers.add_parser(
        "simulate-tournament",
        help="Run full-tournament Monte Carlo reports",
    )
    simulate_tournament_parser.add_argument("--processed", default="data/processed", type=Path)
    simulate_tournament_parser.add_argument("--manual", default="data/manual", type=Path)
    simulate_tournament_parser.add_argument("--out", default="outputs", type=Path)
    simulate_tournament_parser.add_argument("--simulations", default=200_000, type=int)
    simulate_tournament_parser.add_argument("--seed", default=20260610, type=int)
    simulate_tournament_parser.add_argument("--extra-time-goal-multiplier", default=0.30, type=float)
    simulate_tournament_parser.add_argument(
        "--penalty-model",
        default="coin_flip",
        choices=("coin_flip", "rating_weighted"),
    )
    simulate_tournament_parser.add_argument("--no-score-tilts", action="store_true")
    simulate_tournament_parser.add_argument("--value-threshold", default=0.05, type=float)
    simulate_tournament_parser.add_argument(
        "--calibration-model",
        default="none",
        choices=("none", "opta_reweight"),
    )
    simulate_tournament_parser.add_argument("--baseline-probabilities", default=None, type=Path)
    simulate_tournament_parser.add_argument("--opta-strength", default=0.35, type=float)

    decision_report_parser = subparsers.add_parser(
        "build-decision-report",
        help="Build the decision markdown report from existing outputs",
    )
    decision_report_parser.add_argument("--processed", default="data/processed", type=Path)
    decision_report_parser.add_argument("--out", default="outputs", type=Path)
    decision_report_parser.add_argument("--report", default="outputs/tournament-summary.md", type=Path)
    decision_report_parser.add_argument("--simulations", default=200_000, type=int)
    decision_report_parser.add_argument("--seed", default=20260610, type=int)
    decision_report_parser.add_argument("--extra-time-goal-multiplier", default=0.30, type=float)
    decision_report_parser.add_argument(
        "--penalty-model",
        default="coin_flip",
        choices=("coin_flip", "rating_weighted"),
    )
    decision_report_parser.add_argument("--value-threshold", default=0.05, type=float)

    sensitivity_parser = subparsers.add_parser(
        "run-sensitivity",
        help="Run sensitivity scenarios for the stadium average-goals market",
    )
    sensitivity_parser.add_argument("--processed", default="data/processed", type=Path)
    sensitivity_parser.add_argument("--manual", default="data/manual", type=Path)
    sensitivity_parser.add_argument("--out", default="outputs/sensitivity", type=Path)
    sensitivity_parser.add_argument("--simulations", default=50_000, type=int)
    sensitivity_parser.add_argument("--seed", default=20260610, type=int)
    sensitivity_parser.add_argument("--value-threshold", default=0.05, type=float)

    run_all_parser = subparsers.add_parser("run-all", help="Run the full betting pipeline end-to-end")
    run_all_parser.add_argument("--base-data", default="base-data", type=Path)
    run_all_parser.add_argument("--processed", default="data/processed", type=Path)
    run_all_parser.add_argument("--manual", default="data/manual", type=Path)
    run_all_parser.add_argument("--out", default="outputs", type=Path)
    run_all_parser.add_argument("--simulations", default=200_000, type=int)
    run_all_parser.add_argument("--group-simulations", default=50_000, type=int)
    run_all_parser.add_argument("--sensitivity-simulations", default=50_000, type=int)
    run_all_parser.add_argument("--seed", default=20260610, type=int)
    run_all_parser.add_argument("--extra-time-goal-multiplier", default=0.30, type=float)
    run_all_parser.add_argument(
        "--penalty-model",
        default="coin_flip",
        choices=("coin_flip", "rating_weighted"),
    )
    run_all_parser.add_argument("--no-global-tilts", action="store_true")
    run_all_parser.add_argument("--no-score-tilts", action="store_true")
    run_all_parser.add_argument("--value-threshold", default=0.05, type=float)

    ocr_parser = subparsers.add_parser("ocr-odds", help="Extract OCR review files from odds screenshots")
    ocr_parser.add_argument("--base-data", default="base-data", type=Path)
    ocr_parser.add_argument("--raw", default="data/ocr/odds_raw.csv", type=Path)
    ocr_parser.add_argument("--review", default="data/manual/odds_review.csv", type=Path)
    ocr_parser.add_argument("--crops", default="data/ocr/crops", type=Path)
    ocr_parser.add_argument("--match-order", default="data/ocr/match_order.csv", type=Path)
    ocr_parser.add_argument("--ocr-workers", default=4, type=int)

    text_odds_parser = subparsers.add_parser(
        "parse-text-odds",
        help="Parse copied Oddschecker text into a review CSV",
    )
    text_odds_parser.add_argument("--base-data", default="base-data", type=Path)
    text_odds_parser.add_argument("--market", required=True)
    text_odds_parser.add_argument("--source", required=True, type=Path)
    text_odds_parser.add_argument("--out", required=True, type=Path)
    text_odds_parser.add_argument("--expected-matches", default=72, type=int)

    promote_parser = subparsers.add_parser("promote-odds", help="Validate reviewed OCR odds")
    promote_parser.add_argument("--base-data", default="base-data", type=Path)
    promote_parser.add_argument("--review", default="data/manual/odds_review.csv", type=Path)
    promote_parser.add_argument("--out", default="data/manual/odds.csv", type=Path)

    promote_text_parser = subparsers.add_parser(
        "promote-text-odds",
        help="Validate complete text odds review files",
    )
    promote_text_parser.add_argument("--base-data", default="base-data", type=Path)
    promote_text_parser.add_argument("--manual", default="data/manual", type=Path)
    promote_text_parser.add_argument("--out", default="data/manual/odds.csv", type=Path)
    promote_text_parser.add_argument("--audit", default="data/manual/odds_text_audit.csv", type=Path)
    promote_text_parser.add_argument("--expected-matches", default=72, type=int)

    r32_mapping_parser = subparsers.add_parser(
        "extract-r32-mapping",
        help="Extract Annex C R32 third-place mapping from FIFA regulations PDF",
    )
    r32_mapping_parser.add_argument(
        "--pdf",
        default="base-data/FWC26_regulations_EN.pdf",
        type=Path,
    )
    r32_mapping_parser.add_argument(
        "--out",
        default="data/manual/r32_third_place_mapping.csv",
        type=Path,
    )
    r32_mapping_parser.add_argument(
        "--raw",
        default="data/manual/annex_c_raw.txt",
        type=Path,
    )

    return parser
