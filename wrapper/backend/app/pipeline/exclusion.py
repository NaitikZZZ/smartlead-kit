"""Wraps the vendored check_exclusions logic (see backend/vendor/check_exclusions.py,
sourced from the abm-exclusion-check skill) against a master Account Mapping Sheet."""
from __future__ import annotations
import sys
from pathlib import Path

import pandas as pd

VENDOR_DIR = Path(__file__).resolve().parent.parent.parent / "vendor"
sys.path.insert(0, str(VENDOR_DIR))
import check_exclusions as _ce  # noqa: E402


def run_exclusion_check(df: pd.DataFrame, master_sheet_path: str, name_col: str, domain_col: str | None):
    master_rows, master_fields = _ce.read_csv_any_encoding(master_sheet_path)
    for required in (_ce.MASTER_NAME_COL, _ce.MASTER_DOMAIN_COL, _ce.MASTER_TYPE1_COL, _ce.MASTER_PARENT_STATUS_COL):
        if required not in master_fields:
            raise ValueError(f"Master sheet missing expected column {required!r}. Found: {master_fields}")

    index = _ce.build_master_index(master_rows)

    statuses, reasons = [], []
    for _, row in df.iterrows():
        name = row.get(name_col, "") if name_col else ""
        domain = row.get(domain_col, "") if domain_col else ""
        status, reason, _matched = _ce.evaluate_prospect(str(name or ""), str(domain or ""), index)
        statuses.append(status)
        reasons.append(reason)

    out = df.copy()
    out["Exclusion Status"] = statuses
    out["Exclusion Reason"] = reasons

    excluded = int((out["Exclusion Status"] == "Excluded").sum())
    ok = int((out["Exclusion Status"] == "OK to reach out").sum())
    return out, {"excluded": excluded, "ok_to_reach_out": ok, "total": len(out)}
