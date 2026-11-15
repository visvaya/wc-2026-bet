from wc2026bet.score_grid import ScoreGrid


def test_score_grid_probabilities_are_normalized() -> None:
    grid = ScoreGrid(lambda_home=1.4, lambda_away=1.1)

    assert abs(grid.total_probability() - 1.0) < 1e-10
    assert abs(sum(grid.result_probabilities().values()) - 1.0) < 1e-10


def test_score_grid_over_probabilities_are_monotonic() -> None:
    grid = ScoreGrid(lambda_home=1.7, lambda_away=1.3)

    assert grid.prob_over(0.5) >= grid.prob_over(1.5) >= grid.prob_over(2.5)


def test_score_grid_reports_btts_and_expected_goals() -> None:
    grid = ScoreGrid(lambda_home=1.2, lambda_away=1.0)

    assert 0.0 < grid.prob_btts() < 1.0
    assert abs(grid.expected_total_goals() - 2.2) < 0.01


def test_score_grid_tilts_keep_probabilities_normalized() -> None:
    baseline = ScoreGrid(lambda_home=1.2, lambda_away=1.0)
    tilted = ScoreGrid(lambda_home=1.2, lambda_away=1.0, btts_correlation_tilt=0.4)

    assert abs(tilted.total_probability() - 1.0) < 1e-10
    assert tilted.prob_btts() > baseline.prob_btts()
