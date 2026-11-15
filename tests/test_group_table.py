from wc2026bet.group_table import TeamTableRow, apply_match, table_sort_key


def test_apply_match_win_awards_three_points_and_goal_difference() -> None:
    home = TeamTableRow(team="Mexico", group="A", random_tiebreaker=0.1)
    away = TeamTableRow(team="Canada", group="A", random_tiebreaker=0.9)

    apply_match(home, away, 3, 1)

    assert (home.points, home.gf, home.ga, home.gd) == (3, 3, 1, 2)
    assert (away.points, away.gf, away.ga, away.gd) == (0, 1, 3, -2)
    assert table_sort_key(home) == (3, 2, 3, 0.1)
    assert sorted([away, home], key=table_sort_key, reverse=True) == [home, away]


def test_apply_match_draw_awards_one_point_each() -> None:
    home = TeamTableRow(team="Mexico", group="A", random_tiebreaker=0.1)
    away = TeamTableRow(team="Canada", group="A", random_tiebreaker=0.9)

    apply_match(home, away, 2, 2)

    assert (home.points, home.gd, away.points, away.gd) == (1, 0, 1, 0)
    assert table_sort_key(away) == (1, 0, 2, 0.9)
    assert sorted([home, away], key=table_sort_key, reverse=True) == [away, home]
