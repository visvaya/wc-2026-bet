from pathlib import Path

import pytest
from PIL import Image, ImageDraw

from synthetic_data import odds_for, write_group_schedule, write_rows
from wc2026bet import ocr
from wc2026bet.csv_io import read_csv
from wc2026bet.ocr import (
    BoundingBox,
    detect_odds_boxes,
    match_row_text_to_match,
    parse_decimal_odd,
    promote_review_odds,
    write_odds_ocr_outputs,
)
from wc2026bet.parsers import parse_base_matches
from wc2026bet.processed import write_odds_template


def test_parse_decimal_odd_accepts_dot_and_comma_formats() -> None:
    assert parse_decimal_odd("1.95") == "1.95"
    assert parse_decimal_odd(" 2,30 ") == "2.3"
    assert parse_decimal_odd("odds 12.5") == "12.5"
    assert parse_decimal_odd("1") == "1"


def test_parse_decimal_odd_rejects_ambiguous_or_invalid_text() -> None:
    assert parse_decimal_odd("") == ""
    assert parse_decimal_odd("abc") == ""
    assert parse_decimal_odd("1.95 2.10") == ""
    assert parse_decimal_odd("0.99") == ""


def test_detect_odds_boxes_on_synthetic_table() -> None:
    image = Image.new("RGB", (420, 260), "white")
    draw = ImageDraw.Draw(image)
    boxes = [
        (220, 30, 285, 58),
        (300, 30, 365, 58),
        (220, 90, 285, 118),
        (300, 90, 365, 118),
        (220, 150, 285, 178),
        (300, 150, 365, 178),
    ]
    for box in boxes:
        draw.rectangle(box, fill=(236, 238, 240))

    detected = detect_odds_boxes(image, min_x_ratio=0.45)

    assert detected == [BoundingBox(*box) for box in boxes]


def test_match_row_text_to_match_ignores_ocr_noise_around_team_names(synthetic_base_data: Path) -> None:
    result = match_row_text_to_match("00:30 6 team c3 ; @ TEAM-C4", synthetic_base_data)

    assert (result.match.team_home, result.match.team_away) == ("Team C3", "Team C4")
    assert result.reversed_order is False
    assert result.confidence == 1.0


def test_match_row_text_to_match_detects_reversed_order_in_synthetic_schedule(synthetic_base_data: Path) -> None:
    result = match_row_text_to_match("Team L3 v Team L1", synthetic_base_data)

    assert (result.match.team_home, result.match.team_away) == ("Team L1", "Team L3")
    assert result.reversed_order is True


def test_match_row_text_to_match_maps_rows_by_teams_not_by_position(synthetic_base_data: Path) -> None:
    group_matches = [match for match in parse_base_matches(synthetic_base_data) if match.phase == "Group"]
    picked = [group_matches[index] for index in (40, 3, 71, 0, 17)]

    results = [match_row_text_to_match(f"{match.team_home} {match.team_away}", synthetic_base_data) for match in picked]

    assert [result.match.match_id for result in results] == [match.match_id for match in picked]


def test_match_row_text_to_match_rejects_ambiguous_rows(synthetic_base_data: Path) -> None:
    with pytest.raises(ValueError, match="Ambiguous OCR match mapping"):
        match_row_text_to_match("Team C3 Tearn C4", synthetic_base_data)


def test_match_row_text_to_match_accepts_alternative_team_spellings(tmp_path: Path) -> None:
    # A schedule name and an alternative spelling from the alias table in ocr.py (U+00F4 built at runtime).
    schedule_name, spelling = f"C{chr(0xF4)}te d'Ivoire", "Ivory Coast"
    base_data = write_group_schedule(tmp_path / "base-data", [("Team Y", "Team X"), (schedule_name, "Team X")])

    result = match_row_text_to_match(f"{spelling} ; @ Team X", base_data)

    assert (result.match.team_home, result.match.team_away) == (schedule_name, "Team X")
    assert result.reversed_order is False


def test_resolve_image_row_matches_falls_back_to_the_broad_crop(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_data = write_group_schedule(tmp_path / "base-data", [("Team Y", "Team X"), ("Team W", "Team V")])
    texts = {(1, False): "Team Y ; @ Team X", (2, False): "Tea", (2, True): "Team W ; @ Team V"}
    rows = [[BoundingBox(0, 0, 1, 1)], [BoundingBox(0, 1, 1, 1)]]
    monkeypatch.setattr(ocr, "_ocr_row_text", lambda _image, row, *, broad: texts[(row[0].top + 1, broad)])

    row_texts, row_matches = ocr.resolve_image_row_matches(Image.new("L", (1, 2)), rows, base_data)

    assert row_texts == ["Team Y ; @ Team X", "Team W ; @ Team V"]
    assert [(m.match.team_home, m.match.team_away) for m in row_matches] == [("Team Y", "Team X"), ("Team W", "Team V")]


def test_resolve_image_row_matches_reports_the_row_when_both_crops_fail(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    base_data = write_group_schedule(tmp_path / "base-data", [("Team Y", "Team X")])
    monkeypatch.setattr(ocr, "_ocr_row_text", lambda _image, _row, *, broad: "Tea")

    with pytest.raises(ValueError, match="^row 1: "):
        ocr.resolve_image_row_matches(Image.new("L", (1, 1)), [[BoundingBox(0, 0, 1, 1)]], base_data)


@pytest.mark.real_data
def test_match_row_text_to_match_handles_noisy_team_aliases(real_base_data: Path) -> None:
    result = match_row_text_to_match(
        "00:30 6 DR Congo ; @ Uzbekistan",
        real_base_data,
    )

    assert result.match.match_id == 72
    assert result.reversed_order is False
    assert result.confidence >= 0.70


@pytest.mark.real_data
def test_match_row_text_to_match_detects_reversed_schedule_order(real_base_data: Path) -> None:
    result = match_row_text_to_match(
        "Congo DR v Portugal",
        real_base_data,
    )

    assert result.match.match_id == 23
    assert result.reversed_order is True


@pytest.mark.real_data
def test_match_row_text_to_match_does_not_use_schedule_index_order(real_base_data: Path) -> None:
    row_texts = [
        "Panama England",
        "Croatia Ghana",
        "Colombia Portugal",
        "DR Congo Uzbekistan",
        "Jordan Argentina",
        "Algeria Austria",
    ]

    results = [match_row_text_to_match(row_text, real_base_data) for row_text in row_texts]

    assert [result.match.match_id for result in results] == [67, 68, 71, 72, 70, 69]


@pytest.mark.slow
def test_write_odds_ocr_outputs_generates_raw_review_and_crops(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    source_path = work_dir / "market.png"
    _write_synthetic_market_image(source_path, rows=2, selections=2)

    raw_path = work_dir / "odds_raw.csv"
    review_path = work_dir / "odds_review.csv"
    crop_dir = work_dir / "crops"
    count = write_odds_ocr_outputs(
        synthetic_base_data,
        raw_path,
        review_path,
        crop_dir,
        specs=[
            {
                "market": "btts",
                "source_file": source_path,
                "selections": ("yes", "no"),
                "expected_matches": 2,
            }
        ],
        allow_schedule_order_fallback=True,
    )

    raw_rows = read_csv(raw_path)
    review_rows = read_csv(review_path)
    assert count == 4
    assert len(raw_rows) == 4
    assert len(review_rows) == 4
    assert raw_rows[0]["match_id"] == "1"
    assert raw_rows[0]["market"] == "btts"
    assert raw_rows[0]["status"] == "needs_review"
    assert (crop_dir / "btts_1_yes.png").exists()


def test_promote_review_odds_writes_canonical_manual_odds(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    review_path = work_dir / "odds_review.csv"
    output_path = work_dir / "odds.csv"
    write_odds_template(synthetic_base_data, review_path)
    rows = read_csv(review_path)
    for row in rows:
        row["decimal_odds"] = odds_for(row["market"], row["selection"])
        row["source_file"] = "manual-test"
        row["captured_at"] = "2026-06-09T12:00:00"
        row["ocr_confidence"] = "1.0"
    write_rows(review_path, rows)

    count = promote_review_odds(review_path, synthetic_base_data, output_path)

    output_rows = read_csv(output_path)
    assert count == 792
    assert len(output_rows) == 792
    assert set(output_rows[0]) == {
        "match_id",
        "market",
        "selection",
        "decimal_odds",
        "source_file",
        "captured_at",
        "ocr_confidence",
        "manual_override",
    }


def test_promote_review_odds_rejects_incomplete_review(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    review_path = work_dir / "odds_review.csv"
    output_path = work_dir / "odds.csv"
    write_odds_template(synthetic_base_data, review_path)
    rows = read_csv(review_path)[:10]
    for row in rows:
        row["decimal_odds"] = "2.0"
    write_rows(review_path, rows)

    with pytest.raises(ValueError, match="Missing odds rows"):
        promote_review_odds(review_path, synthetic_base_data, output_path)


def test_promote_review_odds_rejects_unresolved_review_status(tmp_path: Path, synthetic_base_data: Path) -> None:
    work_dir = tmp_path
    review_path = work_dir / "odds_review.csv"
    output_path = work_dir / "odds.csv"
    write_odds_template(synthetic_base_data, review_path)
    rows = read_csv(review_path)
    for row in rows:
        row["decimal_odds"] = odds_for(row["market"], row["selection"])
        row["source_file"] = "manual-test"
        row["captured_at"] = "2026-06-09T12:00:00"
        row["ocr_confidence"] = "1.0"
        row["status"] = "ok"
    rows[0]["status"] = "needs_review"
    write_rows(review_path, rows)

    with pytest.raises(ValueError, match="Unresolved OCR review rows"):
        promote_review_odds(review_path, synthetic_base_data, output_path)


def _write_synthetic_market_image(path: Path, rows: int, selections: int) -> None:
    image = Image.new("RGB", (420, 80 + rows * 60), "white")
    draw = ImageDraw.Draw(image)
    for row in range(rows):
        for selection in range(selections):
            left = 220 + selection * 80
            top = 30 + row * 60
            draw.rectangle((left, top, left + 65, top + 28), fill=(236, 238, 240))
    image.save(path)
