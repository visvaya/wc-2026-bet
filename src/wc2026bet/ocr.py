"""OCR helpers for Oddschecker group-stage odds screenshots."""

from __future__ import annotations

import csv
import re
import shutil
import unicodedata
from collections.abc import Iterable, Sequence
from concurrent.futures import ThreadPoolExecutor
from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from pathlib import Path
from typing import Any

from PIL import Image, ImageOps

from wc2026bet.manual_odds import ODDS_FIELDS, parse_manual_odds
from wc2026bet.models import Match
from wc2026bet.parsers import parse_base_matches

RAW_ODDS_FIELDS = (
    "row_index",
    "match_id",
    "market",
    "selection",
    "raw_text",
    "decimal_odds",
    "ocr_confidence",
    "crop_path",
    "source_file",
    "captured_at",
    "status",
    "warnings",
    "row_text",
    "mapped_match_id",
    "match_confidence",
    "match_mapping_status",
)
REVIEW_ODDS_FIELDS = (
    "row_index",
    "match_id",
    "date",
    "team_home",
    "team_away",
    "market",
    "selection",
    "decimal_odds",
    "source_file",
    "captured_at",
    "ocr_confidence",
    "manual_override",
    "raw_text",
    "status",
    "warnings",
    "crop_path",
    "row_text",
    "mapped_match_id",
    "match_confidence",
    "match_mapping_status",
)
MATCH_ORDER_FIELDS = (
    "market",
    "row_index",
    "row_text",
    "mapped_match_id",
    "team_home",
    "team_away",
    "match_confidence",
    "match_mapping_status",
    "reversed_order",
)


@dataclass(frozen=True)
class BoundingBox:
    left: int
    top: int
    right: int
    bottom: int

    @property
    def width(self) -> int:
        return self.right - self.left + 1

    @property
    def height(self) -> int:
        return self.bottom - self.top + 1


@dataclass(frozen=True)
class OddsScreenSpec:
    market: str
    source_file: Path
    selections: tuple[str, ...]
    expected_matches: int = 72


@dataclass(frozen=True)
class MatchRowResolution:
    match: Match
    confidence: float
    reversed_order: bool
    status: str


DEFAULT_ODDS_SCREEN_SPECS = (
    OddsScreenSpec(
        market="1X2",
        source_file=Path("match-result-World-Cup-Betting-Odds-2026-Oddschecker.png"),
        selections=("home", "draw", "away"),
    ),
    OddsScreenSpec(
        market="over_under_2_5",
        source_file=Path("o25-World-Cup-Betting-Odds-2026-Oddschecker.png"),
        selections=("over", "under"),
    ),
    OddsScreenSpec(
        market="over_under_1_5",
        source_file=Path("o15-World-Cup-Betting-Odds-2026-Oddschecker.png"),
        selections=("over", "under"),
    ),
    OddsScreenSpec(
        market="over_under_0_5",
        source_file=Path("o05-World-Cup-Betting-Odds-2026-Oddschecker.png"),
        selections=("over", "under"),
    ),
    OddsScreenSpec(
        market="btts",
        source_file=Path("btts-World-Cup-Betting-Odds-2026-Oddschecker.png"),
        selections=("yes", "no"),
    ),
)

DECIMAL_RE = re.compile(r"(?<!\d)(\d{1,3}(?:[.,]\d{1,3})?)(?!\d)")


def write_odds_ocr_outputs(
    base_data: Path,
    raw_path: Path,
    review_path: Path,
    crop_dir: Path,
    *,
    specs: Sequence[OddsScreenSpec | dict[str, Any]] | None = None,
    workers: int = 4,
    match_order_path: Path | None = None,
    allow_schedule_order_fallback: bool = False,
) -> int:
    """Write OCR raw rows and a manual review CSV from Oddschecker screenshots."""

    raw_path.parent.mkdir(parents=True, exist_ok=True)
    review_path.parent.mkdir(parents=True, exist_ok=True)
    crop_dir.mkdir(parents=True, exist_ok=True)
    group_matches = [match for match in parse_base_matches(base_data) if match.phase == "Group"]
    all_raw_rows: list[dict[str, str]] = []
    all_review_rows: list[dict[str, str]] = []
    all_match_order_rows: list[dict[str, str]] = []

    for raw_spec in specs or DEFAULT_ODDS_SCREEN_SPECS:
        spec = _coerce_spec(raw_spec, base_data)
        source_path = _resolve_source_path(spec.source_file, base_data)
        expected_cells = spec.expected_matches * len(spec.selections)
        with Image.open(source_path) as image:
            min_y = 450 if image.height > 1000 else 0
            boxes = detect_odds_boxes(image.convert("RGB"), min_y=min_y)
            if len(boxes) != expected_cells:
                raise ValueError(
                    f"Expected {expected_cells} odds cells for {spec.market} in {source_path.name}, "
                    f"detected {len(boxes)}"
                )
            row_boxes = _group_boxes_by_row(boxes, len(spec.selections))
            if allow_schedule_order_fallback:
                row_texts = [_ocr_row_text(image.convert("RGB"), row) for row in row_boxes]
                row_matches = [
                    MatchRowResolution(
                        match=group_matches[row_index],
                        confidence=1.0,
                        reversed_order=False,
                        status="schedule_order_fallback",
                    )
                    for row_index in range(spec.expected_matches)
                ]
            else:
                try:
                    row_texts, row_matches = resolve_image_row_matches(
                        image.convert("RGB"),
                        row_boxes,
                        base_data,
                    )
                except ValueError as exc:
                    raise ValueError(f"{spec.market}: {exc}") from exc

            pending_rows = []
            for row_index, (row, row_match, row_text) in enumerate(
                zip(row_boxes, row_matches, row_texts, strict=True),
                start=1,
            ):
                match = row_match.match
                all_match_order_rows.append(
                    {
                        "market": spec.market,
                        "row_index": str(row_index),
                        "row_text": row_text,
                        "mapped_match_id": str(match.match_id),
                        "team_home": match.team_home or "",
                        "team_away": match.team_away or "",
                        "match_confidence": f"{row_match.confidence:.3f}",
                        "match_mapping_status": row_match.status,
                        "reversed_order": "true" if row_match.reversed_order else "false",
                    }
                )
                for source_selection, box in zip(spec.selections, row, strict=True):
                    selection = _canonical_selection(spec.market, source_selection, row_match.reversed_order)
                    crop_path = crop_dir / f"{spec.market}_{match.match_id}_{selection}.png"
                    image.crop((box.left, box.top, box.right + 1, box.bottom + 1)).save(crop_path)
                    pending_rows.append((row_index, row_text, row_match, match, selection, crop_path, source_path))

            ocr_results = _ocr_crops([crop_path for _, _, _, _, _, crop_path, _ in pending_rows], workers=workers)
            for (
                row_index,
                row_text,
                row_match,
                match,
                selection,
                crop_path,
                source_path,
            ), (raw_text, confidence) in zip(
                pending_rows,
                ocr_results,
                strict=True,
            ):
                decimal_odds = parse_decimal_odd(raw_text)
                warnings = _warnings_for_ocr(raw_text, decimal_odds, confidence)
                status = "ok" if not warnings else "needs_review"
                raw_row = {
                    "row_index": str(row_index),
                    "match_id": str(match.match_id),
                    "market": spec.market,
                    "selection": selection,
                    "raw_text": raw_text,
                    "decimal_odds": decimal_odds,
                    "ocr_confidence": f"{confidence:.3f}",
                    "crop_path": str(crop_path),
                    "source_file": source_path.name,
                    "captured_at": _mtime_iso(source_path),
                    "status": status,
                    "warnings": "; ".join(warnings),
                    "row_text": row_text,
                    "mapped_match_id": str(match.match_id),
                    "match_confidence": f"{row_match.confidence:.3f}",
                    "match_mapping_status": row_match.status,
                }
                all_raw_rows.append(raw_row)
                all_review_rows.append(
                    {
                        "row_index": str(row_index),
                        "match_id": str(match.match_id),
                        "date": match.date,
                        "team_home": match.team_home or "",
                        "team_away": match.team_away or "",
                        "market": spec.market,
                        "selection": selection,
                        "decimal_odds": decimal_odds,
                        "source_file": source_path.name,
                        "captured_at": _mtime_iso(source_path),
                        "ocr_confidence": f"{confidence:.3f}",
                        "manual_override": "true",
                        "raw_text": raw_text,
                        "status": status,
                        "warnings": "; ".join(warnings),
                        "crop_path": str(crop_path),
                        "row_text": row_text,
                        "mapped_match_id": str(match.match_id),
                        "match_confidence": f"{row_match.confidence:.3f}",
                        "match_mapping_status": row_match.status,
                    }
                )

    _write_csv(raw_path, RAW_ODDS_FIELDS, all_raw_rows)
    _write_csv(review_path, REVIEW_ODDS_FIELDS, all_review_rows)
    _write_csv(match_order_path or raw_path.parent / "match_order.csv", MATCH_ORDER_FIELDS, all_match_order_rows)
    return len(all_raw_rows)


def resolve_image_row_matches(
    image: Image.Image,
    row_boxes: Sequence[list[BoundingBox]],
    base_data: Path,
) -> tuple[list[str], list[MatchRowResolution]]:
    row_texts: list[str] = []
    row_matches: list[MatchRowResolution] = []
    for row_index, row in enumerate(row_boxes, start=1):
        text = _ocr_row_text(image, row, broad=False)
        try:
            resolution = match_row_text_to_match(text, base_data)
        except ValueError:
            # The tight crop can cut team names; retry on the broad crop and report its error.
            text = _ocr_row_text(image, row, broad=True)
            try:
                resolution = match_row_text_to_match(text, base_data)
            except ValueError as exc:
                raise ValueError(f"row {row_index}: {exc}") from exc
        row_texts.append(text)
        row_matches.append(resolution)

    seen: dict[int, int] = {}
    duplicates = []
    for row_index, result in enumerate(row_matches, start=1):
        match_id = result.match.match_id
        if match_id in seen:
            duplicates.append(f"rows {seen[match_id]} and {row_index}: match {match_id}")
        seen[match_id] = row_index
    if duplicates:
        raise ValueError(f"Duplicate OCR match mapping: {'; '.join(duplicates[:5])}")
    if len(row_matches) == 72 and len(seen) != 72:
        raise ValueError(f"Expected 72 unique OCR match mappings, got {len(seen)}")
    return row_texts, row_matches


def match_row_text_to_match(row_text: str, base_data: Path) -> MatchRowResolution:
    """Fuzzy-match one OCR row text to a group match."""

    matches = [match for match in parse_base_matches(base_data) if match.phase == "Group"]
    normalized_text = _normalize_text(row_text)
    scored: list[tuple[float, bool, Match]] = []
    for match in matches:
        home_score = _team_score(normalized_text, match.team_home or "")
        away_score = _team_score(normalized_text, match.team_away or "")
        direct_score = (home_score + away_score) / 2.0
        reversed_score = (away_score + home_score) / 2.0
        # Order signal is weak in OCR, but helps correctly swap 1X2 when the display order is reversed.
        direct_order = _ordered_pair_score(normalized_text, match.team_home or "", match.team_away or "")
        reversed_order = _ordered_pair_score(normalized_text, match.team_away or "", match.team_home or "")
        direct_total = max(direct_score, direct_order)
        reversed_total = max(reversed_score, reversed_order)
        if reversed_order > direct_order + 0.03:
            scored.append((reversed_total, True, match))
        elif direct_order > reversed_order + 0.03:
            scored.append((direct_total, False, match))
        elif reversed_total > direct_total + 0.03:
            scored.append((reversed_total, True, match))
        else:
            scored.append((direct_total, False, match))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_score, reversed_order, match = scored[0]
    runner_up_score = scored[1][0] if len(scored) > 1 else 0.0
    if best_score < 0.70 or best_score - runner_up_score < 0.04:
        raise ValueError(
            f"Ambiguous OCR match mapping for row {row_text!r}: "
            f"best match {match.match_id} confidence {best_score:.3f}, runner-up {runner_up_score:.3f}"
        )
    return MatchRowResolution(
        match=match,
        confidence=best_score,
        reversed_order=reversed_order,
        status="ok",
    )


def _group_boxes_by_row(boxes: list[BoundingBox], selections_per_row: int) -> list[list[BoundingBox]]:
    if len(boxes) % selections_per_row != 0:
        raise ValueError(f"Cannot group {len(boxes)} boxes into rows of {selections_per_row} selections")
    return [boxes[index : index + selections_per_row] for index in range(0, len(boxes), selections_per_row)]


def _ocr_row_text(image: Image.Image, row_boxes: list[BoundingBox], *, broad: bool = False) -> str:
    left_box = row_boxes[0]
    row_top = min(box.top for box in row_boxes)
    row_bottom = max(box.bottom for box in row_boxes)
    crop_left = 130
    crop_right = max(crop_left + 50, left_box.left - 35)
    top_margin = 55 if broad else 38
    bottom_margin = 30 if broad else 24
    crop_top = max(0, row_top - top_margin)
    crop_bottom = min(image.height, row_bottom + bottom_margin)
    crop = image.crop((crop_left, crop_top, crop_right, crop_bottom))
    return _ocr_text_crop(crop)


def _canonical_selection(market: str, selection: str, reversed_order: bool) -> str:
    if market == "1X2" and reversed_order:
        return {"home": "away", "away": "home"}.get(selection, selection)
    return selection


def _normalize_text(value: str) -> str:
    ascii_text = unicodedata.normalize("NFKD", value).encode("ascii", "ignore").decode("ascii")
    normalized = re.sub(r"[^a-z0-9]+", " ", ascii_text.lower())
    normalized = re.sub(r"\s+", " ", normalized).strip()
    replacements = {
        "alseria": "algeria",
        "cape verd": "cape verde",
        "cape verce": "cape verde",
        "czech republic": "czechia",
        "drcongo": "congo dr",
        "dr congo": "congo dr",
        "d r congo": "congo dr",
        "eevet": "egypt",
        "egyot": "egypt",
        "korea republic": "south korea",
        "ir iran": "iran",
        "lraq": "iraq",
        "lvucguyui": "tunisia",
        "onseey": "paraguay",
        "srain": "spain",
        "tran": "iran",
        "uss": "usa",
    }
    for source, target in replacements.items():
        normalized = normalized.replace(source, target)
    return normalized


def _team_score(normalized_text: str, team: str) -> float:
    return max(_alias_score(normalized_text, alias) for alias in _team_aliases(team))


def _alias_score(normalized_text: str, alias: str) -> float:
    normalized_alias = _normalize_text(alias)
    if not normalized_alias:
        return 0.0
    if normalized_alias in normalized_text:
        return 1.0
    alias_tokens = normalized_alias.split()
    text_tokens = normalized_text.split()
    if not text_tokens:
        return 0.0
    window_size = max(1, len(alias_tokens))
    candidates = []
    for index in range(0, max(1, len(text_tokens) - window_size + 1)):
        window = " ".join(text_tokens[index : index + window_size])
        candidates.append(SequenceMatcher(None, normalized_alias, window).ratio())
    candidates.append(SequenceMatcher(None, normalized_alias, normalized_text).ratio())
    return max(candidates)


def _ordered_pair_score(normalized_text: str, first_team: str, second_team: str) -> float:
    first_position = _best_alias_position(normalized_text, first_team)
    second_position = _best_alias_position(normalized_text, second_team)
    if first_position is None or second_position is None or first_position >= second_position:
        return 0.0
    first_score = _team_score(normalized_text, first_team)
    second_score = _team_score(normalized_text, second_team)
    return min(1.0, ((first_score + second_score) / 2.0) + 0.05)


def _best_alias_position(normalized_text: str, team: str) -> int | None:
    positions = []
    for alias in _team_aliases(team):
        normalized_alias = _normalize_text(alias)
        position = normalized_text.find(normalized_alias)
        if position >= 0:
            positions.append(position)
    return min(positions) if positions else None


def _team_aliases(team: str) -> tuple[str, ...]:
    aliases = {
        "Congo DR": ("Congo DR", "DR Congo", "D R Congo"),
        "Cabo Verde": ("Cabo Verde", "Cape Verde", "Cape Verd"),
        "Korea Republic": ("Korea Republic", "South Korea"),
        "IR Iran": ("IR Iran", "Iran"),
        "Czechia": ("Czechia", "Czech Republic"),
        "Türkiye": ("Türkiye", "Turkey"),
        "Bosnia and Herzegovina": (
            "Bosnia and Herzegovina",
            "Bosnia Herzegovina",
            "Bosnia-Herzegovina",
        ),
        "Côte d'Ivoire": ("Côte d'Ivoire", "Cote d'Ivoire", "Ivory Coast"),
        "Saudi Arabia": ("Saudi Arabia", "Saudi"),
    }
    return aliases.get(team, (team,))


def _ocr_crops(crop_paths: list[Path], *, workers: int) -> list[tuple[str, float]]:
    if workers <= 1:
        return [_ocr_crop(crop_path) for crop_path in crop_paths]
    with ThreadPoolExecutor(max_workers=workers) as executor:
        return list(executor.map(_ocr_crop, crop_paths))


def promote_review_odds(review_path: Path, base_data: Path, output_path: Path) -> int:
    """Validate a reviewed OCR CSV and write canonical manual odds."""

    _validate_review_statuses(review_path)
    rows = parse_manual_odds(review_path, base_data)
    output_path.parent.mkdir(parents=True, exist_ok=True)
    _write_csv(output_path, ODDS_FIELDS, rows)
    return len(rows)


def parse_decimal_odd(text: str) -> str:
    """Extract one decimal odd from OCR text; return empty string when uncertain."""

    matches = DECIMAL_RE.findall(text.replace("\n", " "))
    if len(matches) != 1:
        return ""
    try:
        value = float(matches[0].replace(",", "."))
    except ValueError:
        return ""
    if not 1.0 <= value <= 100.0:
        return ""
    return f"{value:.6g}"


def detect_odds_boxes(
    image: Image.Image,
    *,
    min_x_ratio: float = 0.42,
    min_y: int = 0,
) -> list[BoundingBox]:
    """Detect filled rectangular odds cells in the right side of an Oddschecker table."""

    rgb = image.convert("RGB")
    width, height = rgb.size
    pixels: Any = rgb.load()
    x_start = int(width * min_x_ratio)
    visited: set[tuple[int, int]] = set()
    boxes: list[BoundingBox] = []

    for y in range(min_y, height):
        for x in range(x_start, width):
            if (x, y) in visited or not _is_cell_pixel(pixels[x, y]):
                continue
            box, count = _flood_component(pixels, width, height, x, y, x_start, visited)
            if _is_plausible_odds_cell(box, count):
                boxes.append(box)

    return _sort_boxes_by_table_order(boxes)


def _flood_component(
    pixels: Any,
    width: int,
    height: int,
    start_x: int,
    start_y: int,
    min_x: int,
    visited: set[tuple[int, int]],
) -> tuple[BoundingBox, int]:
    stack = [(start_x, start_y)]
    visited.add((start_x, start_y))
    left = right = start_x
    top = bottom = start_y
    count = 0
    while stack:
        x, y = stack.pop()
        count += 1
        left = min(left, x)
        right = max(right, x)
        top = min(top, y)
        bottom = max(bottom, y)
        for next_x, next_y in ((x - 1, y), (x + 1, y), (x, y - 1), (x, y + 1)):
            if next_x < min_x or next_x >= width or next_y < 0 or next_y >= height:
                continue
            if (next_x, next_y) in visited or not _is_cell_pixel(pixels[next_x, next_y]):
                continue
            visited.add((next_x, next_y))
            stack.append((next_x, next_y))
    return BoundingBox(left=left, top=top, right=right, bottom=bottom), count


def _is_cell_pixel(pixel: tuple[int, int, int]) -> bool:
    red, green, blue = pixel
    brightness = (red + green + blue) / 3.0
    if brightness < 120 or brightness > 248:
        return False
    return min(red, green, blue) > 95


def _is_plausible_odds_cell(box: BoundingBox, count: int) -> bool:
    if not 35 <= box.width <= 220:
        return False
    if not 15 <= box.height <= 80:
        return False
    fill_ratio = count / (box.width * box.height)
    return fill_ratio >= 0.45


def _sort_boxes_by_table_order(boxes: Iterable[BoundingBox]) -> list[BoundingBox]:
    return sorted(boxes, key=lambda box: (box.top, box.left))


def _ocr_crop(crop_path: Path) -> tuple[str, float]:
    tesseract_cmd = _find_tesseract_cmd()
    if tesseract_cmd is None:
        return "", 0.0
    try:
        import pytesseract
    except ImportError:
        return "", 0.0

    try:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
        image = _prepare_crop_for_ocr(Image.open(crop_path))
        config = "--psm 7 -c tessedit_char_whitelist=0123456789.,"
        data = pytesseract.image_to_data(
            image,
            config=config,
            output_type=pytesseract.Output.DICT,
        )
    except Exception:
        return "", 0.0

    text_parts = [part.strip() for part in data.get("text", []) if part.strip()]
    confidences = []
    for value in data.get("conf", []):
        try:
            confidence = float(value)
        except (TypeError, ValueError):
            continue
        if confidence >= 0:
            confidences.append(confidence / 100.0)
    text = " ".join(text_parts)
    average_confidence = sum(confidences) / len(confidences) if confidences else 0.0
    return text, average_confidence


def _ocr_text_crop(image: Image.Image) -> str:
    tesseract_cmd = _find_tesseract_cmd()
    if tesseract_cmd is None:
        return ""
    try:
        import pytesseract
    except ImportError:
        return ""

    try:
        pytesseract.pytesseract.tesseract_cmd = str(tesseract_cmd)
        scale = 4
        prepared = image.resize((image.width * scale, image.height * scale))
        text = pytesseract.image_to_string(prepared, config="--psm 6")
    except Exception:
        return ""
    return " ".join(part.strip() for part in text.splitlines() if part.strip())


def _find_tesseract_cmd() -> Path | None:
    found = shutil.which("tesseract")
    if found:
        return Path(found)
    for candidate in (
        Path("C:/Program Files/Tesseract-OCR/tesseract.exe"),
        Path("C:/Program Files (x86)/Tesseract-OCR/tesseract.exe"),
    ):
        if candidate.exists():
            return candidate
    return None


def _prepare_crop_for_ocr(image: Image.Image) -> Image.Image:
    grayscale = ImageOps.grayscale(image)
    scale = 4
    resized = grayscale.resize((grayscale.width * scale, grayscale.height * scale))
    return resized.point(lambda value: 0 if value < 170 else 255)


def _warnings_for_ocr(raw_text: str, decimal_odds: str, confidence: float) -> list[str]:
    warnings = []
    if not raw_text:
        warnings.append("missing_ocr")
    if not decimal_odds:
        warnings.append("missing_decimal_odds")
    if confidence < 0.80:
        warnings.append("low_confidence")
    return warnings


def _validate_review_statuses(review_path: Path) -> None:
    with review_path.open(newline="", encoding="utf-8") as handle:
        rows = list(csv.DictReader(handle))
    if not rows or "status" not in rows[0]:
        return
    unresolved = [
        f"match {row.get('match_id', '')} {row.get('market', '')} {row.get('selection', '')}"
        for row in rows
        if row.get("status") not in ("", "ok", "reviewed")
    ]
    if unresolved:
        raise ValueError(f"Unresolved OCR review rows: {'; '.join(unresolved[:5])}")


def _coerce_spec(raw_spec: OddsScreenSpec | dict[str, Any], base_data: Path) -> OddsScreenSpec:
    if isinstance(raw_spec, OddsScreenSpec):
        return raw_spec
    source = Path(raw_spec["source_file"])
    return OddsScreenSpec(
        market=str(raw_spec["market"]),
        source_file=source,
        selections=tuple(raw_spec["selections"]),
        expected_matches=int(raw_spec.get("expected_matches", 72)),
    )


def _resolve_source_path(source_file: Path, base_data: Path) -> Path:
    if source_file.is_absolute() or source_file.exists():
        return source_file
    return base_data / source_file


def _write_csv(path: Path, fieldnames: tuple[str, ...], rows: list[dict[str, str]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def _mtime_iso(path: Path) -> str:
    return datetime.fromtimestamp(path.stat().st_mtime).isoformat(timespec="seconds")
