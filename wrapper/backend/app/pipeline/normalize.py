"""Wraps the vendored normalize_data logic (name-company-normalizer skill)."""
from __future__ import annotations

import sys
from pathlib import Path

from .._lazy import pd

VENDOR_DIR = Path(__file__).resolve().parent.parent.parent / "vendor"
sys.path.insert(0, str(VENDOR_DIR))
import normalize_data as _nd  # noqa: E402


def run_normalization(df: pd.DataFrame):
    normalized, report = _nd.process_dataframe(df.copy())
    return normalized, {"notes": report}
