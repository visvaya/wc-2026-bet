"""Extract FIFA World Cup 2026 regulations data from the local PDF."""

from __future__ import annotations

import csv
import io
import re
from contextlib import redirect_stderr, redirect_stdout
from pathlib import Path
from typing import Any

R32_MAPPING_FIELDS = (
    "option",
    "qualified_third_groups",
    "vs_1A",
    "vs_1B",
    "vs_1D",
    "vs_1E",
    "vs_1G",
    "vs_1I",
    "vs_1K",
    "vs_1L",
    "source_file",
    "source_page",
)

SLOT_FIELDS = ("vs_1A", "vs_1B", "vs_1D", "vs_1E", "vs_1G", "vs_1I", "vs_1K", "vs_1L")
OPTION_RE = re.compile(r"^\d{1,3}$")
THIRD_PLACE_RE = re.compile(r"^3[A-L]$")


def extract_r32_third_place_mapping(pdf_path: Path) -> list[dict[str, str]]:
    """Extract Annex C R32 third-place assignment rows from the regulations PDF."""

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to extract regulations PDF tables") from exc

    doc = fitz.open(pdf_path)
    rows: list[dict[str, str]] = []
    seen_options: set[int] = set()

    for page_index, page in enumerate(doc, start=1):
        # Table detection is slow; run it only on pages whose text carries mapping rows.
        # A missed page cannot pass silently: validation below requires all 495 options.
        if not _looks_like_annex_c_page(page.get_text("text")):
            continue
        for table in _find_tables_quietly(page):
            for raw_row in table.extract():
                parsed = _parse_mapping_row(raw_row, pdf_path.name, page_index)
                if parsed is None:
                    continue
                option = int(parsed["option"])
                if option in seen_options:
                    raise ValueError(f"Duplicate Annex C option: {option}")
                seen_options.add(option)
                rows.append(parsed)

    rows.sort(key=lambda row: int(row["option"]))
    validate_r32_third_place_mapping(rows)
    return rows


def extract_annex_c_raw_text(pdf_path: Path) -> str:
    """Extract raw text from pages that contain Annex C mapping rows."""

    try:
        import fitz
    except ImportError as exc:
        raise RuntimeError("PyMuPDF is required to extract regulations PDF text") from exc

    doc = fitz.open(pdf_path)
    chunks = []
    for page_index, page in enumerate(doc, start=1):
        text = page.get_text("text")
        if _looks_like_annex_c_page(text):
            chunks.append(f"--- page {page_index} ---\n{text.strip()}")
    return "\n\n".join(chunks)


def write_r32_third_place_mapping(
    pdf_path: Path,
    output_path: Path,
    raw_output_path: Path | None = None,
) -> int:
    """Write Annex C mapping CSV and optional raw text extract."""

    rows = extract_r32_third_place_mapping(pdf_path)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with output_path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=R32_MAPPING_FIELDS)
        writer.writeheader()
        writer.writerows(rows)

    if raw_output_path is not None:
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output_path.write_text(extract_annex_c_raw_text(pdf_path), encoding="utf-8")

    return len(rows)


def parse_r32_third_place_mapping(path: Path) -> list[dict[str, str]]:
    """Read and validate a generated Annex C mapping CSV."""

    with path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    missing = [field for field in R32_MAPPING_FIELDS if rows and field not in rows[0]]
    if missing:
        raise ValueError(f"R32 mapping is missing columns: {', '.join(missing)}")
    validate_r32_third_place_mapping(rows)
    return rows


def validate_r32_third_place_mapping(rows: list[dict[str, str]]) -> None:
    """Validate extracted Annex C mapping rows."""

    if len(rows) != 495:
        raise ValueError(f"Expected 495 Annex C rows, found {len(rows)}")

    expected_options = list(range(1, 496))
    options = [int(row["option"]) for row in rows]
    if options != expected_options:
        raise ValueError("Annex C options must be contiguous from 1 to 495")

    qualified_sets = set()
    for row in rows:
        assignments = [row[field] for field in SLOT_FIELDS]
        if any(THIRD_PLACE_RE.match(value) is None for value in assignments):
            raise ValueError(f"Invalid third-place assignment in option {row['option']}")

        groups = [value[1] for value in assignments]
        if len(set(groups)) != 8:
            raise ValueError(f"Duplicate third-place group in option {row['option']}")

        qualified = "".join(sorted(groups))
        if row["qualified_third_groups"] != qualified:
            raise ValueError(f"Incorrect qualified_third_groups in option {row['option']}")
        qualified_sets.add(qualified)

    if len(qualified_sets) != 495:
        raise ValueError(f"Expected 495 unique qualified group sets, found {len(qualified_sets)}")


def _find_tables_quietly(page: Any) -> list[Any]:
    # PyMuPDF may print layout advisory text; keep CLI output deterministic.
    with redirect_stdout(io.StringIO()), redirect_stderr(io.StringIO()):
        tables = page.find_tables()
    return list(tables.tables)


def _parse_mapping_row(
    raw_row: list[str | None],
    source_file: str,
    page_index: int,
) -> dict[str, str] | None:
    cells = [(cell or "").strip() for cell in raw_row]
    if len(cells) != 9 or OPTION_RE.match(cells[0]) is None:
        return None
    if any(THIRD_PLACE_RE.match(cell) is None for cell in cells[1:]):
        return None

    groups = "".join(sorted(cell[1] for cell in cells[1:]))
    row = {
        "option": str(int(cells[0])),
        "qualified_third_groups": groups,
        "source_file": source_file,
        "source_page": str(page_index),
    }
    row.update(dict(zip(SLOT_FIELDS, cells[1:], strict=True)))
    return row


def _looks_like_annex_c_page(text: str) -> bool:
    return bool(re.search(r"\b\d{1,3}\s+3[A-L]\s+3[A-L]\s+3[A-L]", text))
