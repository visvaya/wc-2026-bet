# wc-2026-bet

Data-driven goal model for FIFA World Cup 2026 betting analysis.

The primary target is the bookmaker market **"stadium with the highest average goals per match"** (extra time counts, penalty shoot-outs do not). The pipeline also reports total goals per stadium, goals per group, and team goals for and against in the group stage and across the full tournament.

The project estimates probabilities and expected value. It does not guarantee profit, and a pick is reported as value only when bookmaker odds beat fair odds by the configured safety margin.

## Status

As of 2026-11-15. The model was built before the FIFA World Cup 2026, played from 11 June to 19 July 2026. The tournament is over; the repository is kept as a portfolio project and as a base for the next tournament. It estimates probabilities and does not give betting advice.

## How it works

1. **Parse** the fixture list (104 matches, 72 group-stage, 48 teams, 16 stadiums), team ratings and the stadium market from the source snapshots in `base-data/`.
2. **Extract odds** for every group match (`1X2`, `O/U 0.5`, `O/U 1.5`, `O/U 2.5`, `BTTS`) from Oddschecker text copies or screenshots (OCR), with manual review files in `data/manual/`.
3. **Devig** bookmaker prices into probabilities.
4. **Fit a score-grid model**: per-match `lambda_home` and `lambda_away`, plus global total-dispersion and BTTS-correlation tilts (not a plain independent Poisson model).
5. **Train a rating-to-goals bridge** (ridge regression with rating priors) on the fitted group-stage lambdas, downweighting low-confidence matches, to price knockout matches.
6. **Simulate** the group stage and the full tournament with Monte Carlo, including the FIFA Annex C mapping of third-placed teams to the round of 32.
7. **Report** percentiles, win probabilities, fair odds, bookmaker odds, EV and sensitivity scenarios. Opta predictions are used only to calibrate advancement probabilities.

## Requirements

- Python 3.13 (`.python-version`) and [uv](https://docs.astral.sh/uv/) (exact dependency versions are locked in `uv.lock`)
- [Tesseract OCR](https://github.com/tesseract-ocr/tesseract) for the screenshot OCR stage (looked up on `PATH`, then in the default Windows install directory)

```bash
uv sync --locked          # creates .venv with the locked runtime dependencies
```

## Usage

The CLI runs from a checkout without installation:

```bash
python -m wc2026bet.cli --help
```

End-to-end pipeline, once manual odds and the round-of-32 mapping are ready:

```bash
python -B -m wc2026bet.cli run-all --processed data/processed --manual data/manual --out outputs
```

`run-all` executes `build-data`, `validate`, `fit-score-params`, `train-goal-bridge`, `group-reports`, `simulate-groups`, `simulate-tournament`, `run-sensitivity` and `build-decision-report` in order, stopping at the first failed stage. `--simulations`, `--group-simulations`, `--sensitivity-simulations` and `--seed` control run size and reproducibility.

The main outputs are `outputs/stadium-average-ranking.csv` and `outputs/tournament-summary.md`.

## Repository layout

```text
data/ocr/         OCR scratch output (ignored)
data/processed/   canonical model inputs (generated, ignored)
outputs/          reports and rankings (generated, ignored)
src/wc2026bet/    implementation
tests/            pytest suite
```

Two input folders are not part of the repository and are supplied by the user: `base-data/` (the read-only source snapshots) and `data/manual/` (human-reviewed odds and the round-of-32 mapping).

Data contracts and the model specification are documented in [`docs/data-contracts.md`](docs/data-contracts.md) and [`docs/model-spec.md`](docs/model-spec.md).

## Development

```bash
uv sync --locked --extra dev
uv run python -m pytest          # the tests alone
uv run python scripts/gate.py    # the whole gate CI runs (lint, types, tests with coverage, more)
```

`uv lock` refreshes `uv.lock` after a dependency change; it only picks versions published at least seven days ago (`exclude-newer` in `pyproject.toml`).

CI (GitHub Actions) runs the same checks on every push to `main`, on pull requests and weekly, in one job that also scans the full history for secrets (gitleaks) and checks the pull request title; pull requests that change only documentation skip the gate. A separate security job (pip-audit on the lockfile, zizmor and actionlint for the workflows) runs on `main`, weekly, and on pull requests that change dependencies or workflows. CodeQL (`security-and-quality` queries) analyses the Python code on `main`, on pull requests and weekly.

See [CONTRIBUTING.md](CONTRIBUTING.md) for the git hooks and the pull request rules, and [SECURITY.md](SECURITY.md) for reporting a vulnerability.

## Data sources

The source snapshots are not included: they are third-party material (FIFA fixtures and regulations, Oddschecker match odds, the Superbet stadium market, Opta Analyst predictions and a public team rating table) and remain the property of their owners. To run the pipeline, place your own snapshots in `base-data/` under the file names listed in [Source Files](docs/data-contracts.md#source-files), then generate and review the files in `data/manual/` as described in [Manual Files](docs/data-contracts.md#manual-files).

The default test suite runs on generated synthetic data (invented teams, stadiums and odds), so it needs no snapshots. Tests marked `real_data` run only when the environment variable `WC2026BET_DATA_DIR` names a directory that holds `base-data/` and `data/manual/`.

## License

[MIT](LICENSE) for the code in this repository. Dependencies keep their own licences; PyMuPDF, used to extract the Annex C table from the regulations PDF, is licensed under AGPL-3.0 (or a commercial licence from Artifex), so redistributing the project together with it must follow that licence.
