from wc2026bet.odds import power_devig, proportional_devig


def test_proportional_devig_normalizes_probabilities() -> None:
    probabilities = proportional_devig({"home": 2.0, "draw": 3.6, "away": 4.4})

    assert set(probabilities) == {"home", "draw", "away"}
    assert abs(sum(probabilities.values()) - 1.0) < 1e-12
    assert probabilities["home"] > probabilities["draw"] > probabilities["away"]


def test_proportional_devig_rejects_invalid_odds() -> None:
    try:
        proportional_devig({"over": 1.9, "under": 0.0})
    except ValueError as exc:
        assert "positive decimal odds" in str(exc)
    else:
        raise AssertionError("invalid odds should raise ValueError")


def test_power_devig_probabilities_sum_to_one() -> None:
    probabilities = power_devig({"home": 1.90, "draw": 3.40, "away": 4.80})

    assert abs(sum(probabilities.values()) - 1.0) < 1e-10
    assert probabilities["home"] > probabilities["draw"] > probabilities["away"]
