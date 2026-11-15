"""Odds normalization utilities."""

from __future__ import annotations

from collections.abc import Mapping


def proportional_devig(decimal_odds: Mapping[str, float]) -> dict[str, float]:
    """Convert decimal odds to no-vig probabilities with proportional devig."""

    inverse = _inverse_odds(decimal_odds)

    overround = sum(inverse.values())
    return {selection: probability / overround for selection, probability in inverse.items()}


def power_devig(decimal_odds: Mapping[str, float]) -> dict[str, float]:
    """Convert decimal odds to no-vig probabilities with the power method."""

    inverse = _inverse_odds(decimal_odds)
    if len(inverse) == 1:
        return {next(iter(inverse)): 1.0}

    low = 0.01
    high = 10.0
    for _ in range(100):
        midpoint = (low + high) / 2.0
        total = sum(probability**midpoint for probability in inverse.values())
        if total > 1.0:
            low = midpoint
        else:
            high = midpoint

    exponent = (low + high) / 2.0
    return {selection: probability**exponent for selection, probability in inverse.items()}


def _inverse_odds(decimal_odds: Mapping[str, float]) -> dict[str, float]:
    if not decimal_odds:
        raise ValueError("At least one odds selection is required")

    inverse: dict[str, float] = {}
    for selection, odds in decimal_odds.items():
        if odds <= 0:
            raise ValueError("All selections must have positive decimal odds")
        inverse[selection] = 1.0 / odds
    return inverse
