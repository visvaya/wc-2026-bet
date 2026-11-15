# Data Contracts

## Folder Layout

```text
base-data/          # read-only source files
data/ocr/           # OCR raw JSON, confidence, crops
data/manual/        # human corrections
data/processed/     # canonical model inputs
outputs/            # final reports and rankings
src/wc2026bet/      # implementation
tests/              # automated tests
```

## Pipeline Commands

Use `run-all` for the final end-to-end workflow once manual odds and R32 mapping are ready:

```powershell
python -B -m wc2026bet.cli run-all --processed data\processed --manual data\manual --out outputs
```

The command runs these stages in order and stops on the first failed stage:

- `build-data`
- `validate`
- `fit-score-params`
- `train-goal-bridge`
- `group-reports`
- `simulate-groups`
- `simulate-tournament`
- `run-sensitivity`
- `build-decision-report`

Useful runtime knobs:

- `--simulations` controls the main full-tournament run.
- `--group-simulations` controls group-stage calibration diagnostics.
- `--sensitivity-simulations` controls each sensitivity scenario.
- `--seed` keeps runs reproducible.

## Source Files

`base-data/` must remain unchanged.

Expected source files:

- `matches_fifa.txt`
- `rating_soccer-rating.txt`
- `stadiums_superbet.txt`
- `match-result-World-Cup-Betting-Odds-2026-Oddschecker.png`
- `o25-World-Cup-Betting-Odds-2026-Oddschecker.png`
- `o15-World-Cup-Betting-Odds-2026-Oddschecker.png`
- `o05-World-Cup-Betting-Odds-2026-Oddschecker.png`
- `btts-World-Cup-Betting-Odds-2026-Oddschecker.png`
- `predictions-FIFA-World-Cup-Predictions-Opta-Analyst.png`

## Manual Files

`data/manual/` holds files that commands generate and a person reviews before the model reads them. All CSVs are UTF-8 with a header row.

### `data/manual/odds.csv`

Canonical group-stage odds, read by `build-data` and `run-all`. Written by `promote-odds` or `promote-text-odds`, or prepared by hand from `odds-template`.

Columns: `match_id`, `market`, `selection`, `decimal_odds`, `source_file`, `captured_at`, `ocr_confidence`, `manual_override`.

Validation:

- `match_id` is a group-stage match from `matches_fifa.txt`;
- `market` and `selection` pairs: `1X2` (`home`, `draw`, `away`), `over_under_0_5`, `over_under_1_5`, `over_under_2_5` (`over`, `under`), `btts` (`yes`, `no`);
- every group match has every selection of every market;
- `decimal_odds` is a positive decimal number;
- the overround of each match market is between 0.98 and 1.18;
- after devig, `P(over 0.5) >= P(over 1.5) >= P(over 2.5)` for every match.

### `data/manual/odds_review.csv`

OCR review file written by `ocr-odds` and read by `promote-odds`. It carries the `odds.csv` columns plus review context (`row_index`, `date`, `team_home`, `team_away`, `raw_text`, `status`, `warnings`, `crop_path`, `row_text`, `mapped_match_id`, `match_confidence` and further OCR diagnostics). `promote-odds` refuses rows whose `status` is not empty, `ok` or `reviewed`, then applies the `odds.csv` validation.

### `data/manual/odds_text_*.csv`

Text review files, one per market, written by `parse-text-odds` from copied Oddschecker text and read together by `promote-text-odds`: `odds_text_1x2.csv`, `odds_text_o05.csv`, `odds_text_o15.csv`, `odds_text_o25.csv`, `odds_text_btts.csv`. All five must exist.

Columns: the `odds.csv` columns plus `date`, `time`, `team_home`, `team_away`, `source_team_home`, `source_team_away`, `mapping_status`, `reversed_order`. Only rows with `mapping_status` = `matched` are promoted.

`promote-text-odds` also writes `data/manual/odds_text_audit.csv` (per market: parsed matches, selection rows, overround minimum, average and maximum, status, warnings).

### `data/manual/r32_third_place_mapping.csv`

Annex C mapping of third-placed teams to round-of-32 slots, written by `extract-r32-mapping` from the regulations PDF and read by `validate`, `simulate-tournament`, `run-sensitivity` and `run-all`.

Columns: `option`, `qualified_third_groups`, `vs_1A`, `vs_1B`, `vs_1D`, `vs_1E`, `vs_1G`, `vs_1I`, `vs_1K`, `vs_1L`, `source_file`, `source_page`.

Validation: exactly 495 rows with `option` 1 to 495; each `vs_*` value is a third place such as `3C`; the eight slots use eight different groups; `qualified_third_groups` is the sorted string of those groups.

`extract-r32-mapping` also writes `data/manual/annex_c_raw.txt`, the raw Annex C text for checking the extraction by eye; the pipeline does not read it.

## Processed CSVs

### `data/processed/matches.csv`

Required columns:

- `match_id`
- `phase`
- `group`
- `date`
- `team_home`
- `team_away`
- `slot_home`
- `slot_away`
- `stadium_fifa`
- `is_group_stage`

Required row counts:

- 104 total
- 72 group stage

### `data/processed/odds.csv`

Required columns:

- `match_id`
- `market`
- `selection`
- `decimal_odds`
- `source_file`
- `captured_at`
- `ocr_confidence`
- `manual_override`

Required group-stage market row coverage:

- 72 matches for `1X2`
- 72 matches for `over_under_0_5`
- 72 matches for `over_under_1_5`
- 72 matches for `over_under_2_5`
- 72 matches for `btts`

### `data/processed/stadium_market_odds.csv`

Required columns:

- `stadium_bookmaker`
- `stadium_fifa`
- `market`
- `decimal_odds`
- `source_file`
- `captured_at`

Required rows:

- 16 stadiums

### `data/processed/opta_predictions.csv`

Required columns:

- `team`
- `top_group`
- `l32`
- `l16`
- `qf`
- `sf`
- `final`
- `champion`
- `source_file`
- `captured_at`

Required rows:

- 48 teams

### `data/processed/opta_standings.csv`

Required columns:

- `table_type`
- `group`
- `team`
- `source_team`
- `raw_pos`
- `row_rank`
- `xpts`
- `qual`
- `source_file`
- `captured_at`

Required rows:

- 60 total
- 48 rows where `table_type=group`
- 12 rows where `table_type=third_place_snapshot`

### `data/processed/match_score_params.csv`

Required columns:

- `match_id`
- `lambda_home`
- `lambda_away`
- `weighted_rmse`
- `max_abs_error`
- `low_confidence`
- `bridge_weight`

### `data/processed/score_model_config.csv`

Required columns:

- `max_goals`
- `total_dispersion_tilt`
- `btts_correlation_tilt`
- `weighted_rmse`
- `max_abs_error`
- `unique_market_shapes`

Required rows:

- 1 global score-grid config

### `data/processed/rating_goal_bridge.csv`

Required columns:

- `ridge_alpha`
- `intercept`
- `rating_coefficient`
- `training_rmse`
- `cv_rmse`
- `observations`

Required rows:

- 1 trained bridge model

### `data/processed/team_goal_strengths.csv`

Required columns:

- `team`
- `rating`
- `attack`
- `defense`

Required rows:

- 48 teams

## Output CSVs

### `outputs/stadium-average-ranking.csv`

Required columns:

- `stadium_fifa`
- `scheduled_matches`
- `expected_average_goals`
- `p05`
- `p25`
- `p50`
- `p75`
- `p95`
- `prob_highest_average`
- `fair_odds`
- `bookmaker_odds`
- `ev`

### `outputs/stadium-total-ranking.csv`

Required columns:

- `stadium_fifa`
- `scheduled_matches`
- `expected_total_goals`
- `p05`
- `p25`
- `p50`
- `p75`
- `p95`
- `prob_highest_total`

### `outputs/group-goals.csv`

Required columns:

- `group`
- `expected_goals`
- `p05`
- `p50`
- `p95`

### `outputs/team-group.csv`

Required columns:

- `team`
- `group`
- `expected_points`
- `expected_gf`
- `expected_ga`
- `expected_gd`

### `outputs/opta-standings-calibration.csv`

Required columns:

- `team`
- `group`
- `model_expected_points`
- `opta_xpts`
- `diff_xpts`
- `model_prob_l32`
- `opta_qual`
- `diff_qual`
- `model_prob_third_place`
- `model_prob_best_third`

Required rows:

- 48 teams

### `outputs/opta-third-place-snapshot.csv`

Required columns:

- `team`
- `group`
- `opta_row_rank`
- `opta_raw_pos`
- `opta_xpts`
- `opta_qual`
- `model_prob_third_place`
- `model_prob_best_third`
- `model_prob_l32`

Required rows:

- 12 teams

### `outputs/team-tournament.csv`

Required columns:

- `team`
- `expected_gf`
- `expected_ga`
- `prob_l32`
- `prob_l16`
- `prob_qf`
- `prob_sf`
- `prob_final`
- `prob_champion`

### `outputs/tournament-summary.md`

Required content:

- simulation count and seed
- extra-time multiplier
- penalty model
- source snapshot metadata
- model diagnostics and warnings
- Opta standings calibration warning when xPTS or QUAL deltas are large
- market settlement note
- top stadium rows with fair odds, bookmaker odds, and EV
- explicit value/no-value verdict
- optional sensitivity table when available

### `outputs/sensitivity/stadium-average-sensitivity.csv`

Required columns:

- `stadium_fifa`
- `baseline_probability`
- `min_probability`
- `max_probability`
- `min_fair_odds`
- `max_fair_odds`
- `min_ev`
- `max_ev`
- `stable_top_candidate`

Required rows:

- 16 stadiums

### `outputs/sensitivity/opta-calibration-impact.csv`

Required columns:

- `stadium_fifa`
- `baseline_probability`
- `opta_calibrated_probability`
- `delta_probability`
- `baseline_ev`
- `opta_calibrated_ev`

Required rows:

- 16 stadiums

### `outputs/sensitivity/opta_calibrated/calibration-diagnostics.csv`

Required columns:

- `calibration_model`
- `total_weight`
- `effective_sample_size`
- `clipped_low`
- `clipped_high`

Required rows:

- 1 diagnostics row for the Opta-reweighted sensitivity run
