"""Command-line entrypoint: parses arguments and dispatches to the subcommands."""

from __future__ import annotations

from collections.abc import Callable
from pathlib import Path

from wc2026bet.cli_commands import (
    build_data_command,
    build_decision_report_command,
    extract_r32_mapping_command,
    fit_score_params_command,
    group_reports_command,
    ocr_odds_command,
    odds_template_command,
    parse_text_odds_command,
    promote_odds_command,
    promote_text_odds_command,
    run_sensitivity_command,
    simulate_groups_command,
    simulate_tournament_command,
    train_goal_bridge_command,
    validate_command,
)
from wc2026bet.cli_parser import build_parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.command == "validate":
        return validate_command(args.base_data, args.processed, args.manual)
    if args.command == "build-data":
        return build_data_command(args.base_data, args.out, args.manual)
    if args.command == "odds-template":
        return odds_template_command(args.base_data, args.out)
    if args.command == "fit-score-params":
        return fit_score_params_command(args.base_data, args.odds, args.out, args.config_out, args.no_global_tilts)
    if args.command == "train-goal-bridge":
        return train_goal_bridge_command(args.processed)
    if args.command == "group-reports":
        return group_reports_command(args.processed, args.out)
    if args.command == "simulate-groups":
        return simulate_groups_command(args.processed, args.out, args.simulations, args.seed)
    if args.command == "simulate-tournament":
        return simulate_tournament_command(
            args.processed,
            args.manual,
            args.out,
            args.simulations,
            args.seed,
            args.extra_time_goal_multiplier,
            args.penalty_model,
            args.no_score_tilts,
            args.value_threshold,
            args.calibration_model,
            args.baseline_probabilities,
            args.opta_strength,
        )
    if args.command == "build-decision-report":
        return build_decision_report_command(
            args.processed,
            args.out,
            args.report,
            args.simulations,
            args.seed,
            args.extra_time_goal_multiplier,
            args.penalty_model,
            args.value_threshold,
        )
    if args.command == "run-sensitivity":
        return run_sensitivity_command(
            args.processed,
            args.manual,
            args.out,
            args.simulations,
            args.seed,
            args.value_threshold,
        )
    if args.command == "run-all":
        return _run_all(
            args.base_data,
            args.processed,
            args.manual,
            args.out,
            args.simulations,
            args.group_simulations,
            args.sensitivity_simulations,
            args.seed,
            args.extra_time_goal_multiplier,
            args.penalty_model,
            args.no_global_tilts,
            args.no_score_tilts,
            args.value_threshold,
        )
    if args.command == "ocr-odds":
        return ocr_odds_command(
            args.base_data,
            args.raw,
            args.review,
            args.crops,
            args.match_order,
            args.ocr_workers,
        )
    if args.command == "parse-text-odds":
        return parse_text_odds_command(
            args.source,
            args.base_data,
            args.market,
            args.out,
            args.expected_matches,
        )
    if args.command == "promote-odds":
        return promote_odds_command(args.review, args.base_data, args.out)
    if args.command == "promote-text-odds":
        return promote_text_odds_command(
            args.manual,
            args.base_data,
            args.out,
            args.audit,
            args.expected_matches,
        )
    if args.command == "extract-r32-mapping":
        return extract_r32_mapping_command(args.pdf, args.out, args.raw)

    raise AssertionError(f"Unhandled command: {args.command}")


def _run_all(
    base_data: Path,
    processed: Path,
    manual: Path,
    out: Path,
    simulations: int,
    group_simulations: int,
    sensitivity_simulations: int,
    seed: int,
    extra_time_goal_multiplier: float,
    penalty_model: str,
    no_global_tilts: bool,
    no_score_tilts: bool,
    value_threshold: float,
) -> int:
    steps: tuple[tuple[str, Callable[[], int]], ...] = (
        (
            "build-data",
            lambda: build_data_command(base_data, processed, manual),
        ),
        (
            "validate",
            lambda: validate_command(base_data, processed, manual),
        ),
        (
            "fit-score-params",
            lambda: fit_score_params_command(
                base_data,
                processed / "odds.csv",
                processed / "match_score_params.csv",
                processed / "score_model_config.csv",
                no_global_tilts,
            ),
        ),
        (
            "train-goal-bridge",
            lambda: train_goal_bridge_command(processed),
        ),
        (
            "group-reports",
            lambda: group_reports_command(processed, out),
        ),
        (
            "simulate-groups",
            lambda: simulate_groups_command(processed, out, group_simulations, seed),
        ),
        (
            "simulate-tournament",
            lambda: simulate_tournament_command(
                processed,
                manual,
                out,
                simulations,
                seed,
                extra_time_goal_multiplier,
                penalty_model,
                no_score_tilts,
                value_threshold,
                "none",
                None,
                0.35,
            ),
        ),
        (
            "run-sensitivity",
            lambda: run_sensitivity_command(
                processed,
                manual,
                out / "sensitivity",
                sensitivity_simulations,
                seed,
                value_threshold,
            ),
        ),
        (
            "build-decision-report",
            lambda: build_decision_report_command(
                processed,
                out,
                out / "tournament-summary.md",
                simulations,
                seed,
                extra_time_goal_multiplier,
                penalty_model,
                value_threshold,
            ),
        ),
    )
    print("Running full pipeline:")
    for name, run_step in steps:
        print(f"- {name}")
        result = run_step()
        if result != 0:
            print(f"Full pipeline stopped at: {name}")
            return result
    print(f"Full pipeline completed: {out}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
