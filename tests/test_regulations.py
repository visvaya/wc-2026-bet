import csv
from collections.abc import Callable
from itertools import combinations
from pathlib import Path

import pytest

from synthetic_data import r32_mapping_rows, write_annex_c_pdf, write_r32_mapping_csv
from wc2026bet.regulations import (
    SLOT_FIELDS,
    extract_annex_c_raw_text,
    extract_r32_third_place_mapping,
    parse_r32_third_place_mapping,
    validate_r32_third_place_mapping,
    write_r32_third_place_mapping,
)


@pytest.fixture(scope="module")
def pdf(real_base_data: Path) -> Path:
    return real_base_data / "FWC26_regulations_EN.pdf"


@pytest.fixture(scope="module")
def annex_c_rows(pdf: Path) -> list[dict[str, str]]:
    """Annex C mapping extracted once: reading the PDF takes seconds per call."""

    return extract_r32_third_place_mapping(pdf)


@pytest.fixture(scope="module")
def written_mapping(tmp_path_factory: pytest.TempPathFactory, pdf: Path) -> tuple[int, Path, Path]:
    """Row count, CSV and raw text written once by `write_r32_third_place_mapping`."""

    work_dir = tmp_path_factory.mktemp("r32-mapping")
    output = work_dir / "r32_third_place_mapping.csv"
    raw_output = work_dir / "annex_c_raw.txt"
    count = write_r32_third_place_mapping(pdf, output, raw_output)
    return count, output, raw_output


@pytest.mark.slow
def test_write_r32_mapping_extracts_synthetic_pdf_tables(tmp_path: Path) -> None:
    expected = r32_mapping_rows()
    pdf_path = tmp_path / "annex.pdf"
    write_annex_c_pdf(pdf_path, expected)
    output = tmp_path / "mapping.csv"
    raw_output = tmp_path / "annex_c_raw.txt"

    count = write_r32_third_place_mapping(pdf_path, output, raw_output)

    rows = parse_r32_third_place_mapping(output)
    ignored = ("source_file", "source_page")
    assert count == 495
    assert [{k: v for k, v in row.items() if k not in ignored} for row in rows] == [
        {k: v for k, v in row.items() if k not in ignored} for row in expected
    ]
    assert {row["source_file"] for row in rows} == {"annex.pdf"}
    assert rows[0]["source_page"] == "2"
    assert rows[-1]["source_page"] == "10"
    raw_text = raw_output.read_text(encoding="utf-8")
    assert "--- page 1 ---" not in raw_text
    assert "--- page 2 ---" in raw_text
    assert "--- page 10 ---" in raw_text


@pytest.mark.real_data
def test_extract_r32_third_place_mapping_reads_annex_c(
    annex_c_rows: list[dict[str, str]], real_manual_data: Path
) -> None:
    rows = annex_c_rows

    assert len(rows) == 495
    assert {row["qualified_third_groups"] for row in rows} == {
        "".join(groups) for groups in combinations("ABCDEFGHIJKL", 8)
    }
    assert [row["option"] for row in rows] == [str(option) for option in range(1, 496)]
    assert {row["source_file"] for row in rows} == {"FWC26_regulations_EN.pdf"}
    assert rows[0]["source_page"] == "80"
    # Regression against the reviewed extraction kept with the manual snapshots.
    assert rows == parse_r32_third_place_mapping(real_manual_data / "r32_third_place_mapping.csv")


def test_validate_r32_mapping_rejects_duplicate_qualified_groups() -> None:
    rows = r32_mapping_rows()
    rows[1] = {**rows[1], **{field: rows[0][field] for field in SLOT_FIELDS}}
    rows[1]["qualified_third_groups"] = rows[0]["qualified_third_groups"]

    with pytest.raises(ValueError, match="unique qualified group sets"):
        validate_r32_third_place_mapping(rows)


@pytest.mark.parametrize(
    ("corrupt", "message"),
    [
        (lambda rows: rows.pop(), "Expected 495 Annex C rows"),
        (lambda rows: rows[3].update(option="1"), "contiguous from 1 to 495"),
        (lambda rows: rows[0].update(vs_1A="4A"), "Invalid third-place assignment in option 1"),
        (lambda rows: rows[0].update(vs_1A=rows[0]["vs_1B"]), "Duplicate third-place group in option 1"),
        (lambda rows: rows[0].update(qualified_third_groups="EFGHIJKL"), "Incorrect qualified_third_groups"),
    ],
    ids=["row-count", "options", "assignment", "duplicate-group", "qualified-groups"],
)
def test_validate_r32_mapping_rejects_malformed_rows(
    corrupt: Callable[[list[dict[str, str]]], object], message: str
) -> None:
    rows = r32_mapping_rows()
    corrupt(rows)

    with pytest.raises(ValueError, match=message):
        validate_r32_third_place_mapping(rows)


def test_parse_r32_mapping_reads_valid_csv_and_rejects_missing_columns(tmp_path: Path) -> None:
    path = tmp_path / "mapping.csv"
    write_r32_mapping_csv(path, r32_mapping_rows())

    rows = parse_r32_third_place_mapping(path)

    assert len(rows) == 495
    assert rows[0]["qualified_third_groups"] == "ABCDEFGH"
    path.write_text("option,vs_1A" + chr(10) + "1,3A" + chr(10), encoding="utf-8")
    with pytest.raises(ValueError, match="missing columns: qualified_third_groups"):
        parse_r32_third_place_mapping(path)


@pytest.mark.real_data
def test_write_r32_mapping_writes_csv_and_raw_extract(written_mapping: tuple[int, Path, Path]) -> None:
    count, output, raw_output = written_mapping

    with output.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    raw_text = raw_output.read_text(encoding="utf-8")
    assert count == 495
    assert len(rows) == 495
    assert rows[0]["option"] == "1"
    assert "--- page 80 ---" in raw_text
    assert "Option" in raw_text


@pytest.mark.real_data
def test_parse_r32_mapping_reads_generated_csv(
    written_mapping: tuple[int, Path, Path], annex_c_rows: list[dict[str, str]]
) -> None:
    _, output, _ = written_mapping

    rows = parse_r32_third_place_mapping(output)

    assert len(rows) == 495
    assert rows == annex_c_rows


@pytest.mark.real_data
def test_extract_annex_c_raw_text_contains_mapping_pages(pdf: Path) -> None:
    raw_text = extract_annex_c_raw_text(pdf)

    assert "--- page 80 ---" in raw_text
    assert "--- page 97 ---" in raw_text
    assert "495" in raw_text
