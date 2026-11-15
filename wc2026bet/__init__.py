"""Import shim for running ``python -m wc2026bet.cli`` from a source checkout."""

from pathlib import Path

_SOURCE_PACKAGE = Path(__file__).resolve().parent.parent / "src" / "wc2026bet"
__path__.append(str(_SOURCE_PACKAGE))

__version__ = "0.1.0"
