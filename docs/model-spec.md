# Model Specification

## Markets

Primary market:

- Highest average goals by stadium.
- Extra-time goals count.
- Penalty shoot-out goals do not count.

Secondary analytics:

- Highest total goals by stadium.
- Total goals by group.
- Team GF/GA/GD in group stage.
- Team GF/GA across the tournament.

## Devig

Use power devig as the default for `1X2` and outright/stadium markets. Use proportional devig as a sensitivity check.

For two-way markets, proportional devig is acceptable unless the power method is already implemented consistently:

```text
p_i = (1 / odds_i) / sum_j(1 / odds_j)
```

Validate overround before devig. Flag OCR rows with suspicious overround before they enter modeling.

## Score Grid

Use a finite grid from 0 to 10 goals per team.

Base distribution:

```text
P(h, a) = Pois(h; lambda_home) * Pois(a; lambda_away)
```

Apply global tilts:

```text
P_tilted(h, a) proportional to P(h, a)
  * total_dispersion_tilt(h + a)
  * btts_correlation_tilt(h, a)
```

Renormalize after tilting.

Per match fit only:

- `lambda_home`
- `lambda_away`

Fit globally:

- total-dispersion tilt parameters
- BTTS-correlation tilt parameters

Do not fit dispersion and BTTS correlation per match; that is unstable with the available constraints.

## Loss Function

Minimize weighted logit-probability error against devigged market probabilities:

- `O/U 2.5`: weight 3
- `O/U 1.5`: weight 2
- `BTTS`: weight 2
- `1X2`: weight 1.5
- `O/U 0.5`: weight 1

Model fit is approximate. Do not require exact reproduction of all markets.

Fit outputs must include:

- weighted RMSE
- max absolute probability error
- `low_confidence` boolean
- row-level confidence weight for downstream bridge training

## Rating-To-Goals Bridge

Train a bridge from group-stage fitted lambdas to knockout lambdas.

Use a ridge-regularized attack/defense model with rating prior:

```text
log(lambda_for_i_vs_j) = base + attack_i - defense_j + rating_diff_term
```

Use group-stage fitted lambdas as training targets.

Weight observations by fit confidence:

- high-confidence rows get normal weight
- low-confidence or high-error rows get reduced weight

Use cross-validation to choose ridge strength. Treat team-level attack/defense coefficients as weak signals because each team has only three group matches.

## Opta Calibration

Use Opta only to calibrate advancement probabilities and tournament progression. Do not alter goal-total distributions to force Opta agreement.

Report stage-probability deltas between simulation and Opta. Large deviations should produce warnings, not silent model changes.

When Opta standings are available, use `xPTS` and `QUAL` as diagnostic targets for group-stage strength and advancement. Treat the `3rd Place Ranking` section as a snapshot/diagnostic of likely third-place teams, not a complete probability distribution.

Opta-calibrated sensitivity may reweight full tournament simulation paths toward Opta advancement probabilities. This must not change match goal lambdas or per-match score distributions. Baseline remains the primary model; Opta reweighting is a sensitivity layer.

## Knockout Simulation

Simulate 90 minutes first. If tied, simulate extra time as a separate 30-minute process with a lower tempo. If still tied, use penalties only to decide advancement; penalty shoot-out goals do not count.

The R32 mapping for third-place teams must be official and explicit. If it is missing, stop the knockout simulation.

## Monte Carlo

Default:

- `200_000` simulations
- fixed seed
- increase to `1_000_000` if top stadium probabilities are close

Report both Monte Carlo error and distribution percentiles. MC error is not the same as market uncertainty.

For reweighted simulations, compute MC error from the effective sample size implied by path weights, not from the nominal simulation count. The diagnostics file should expose that effective sample size so Opta-calibrated scenarios cannot hide weight degeneracy.
