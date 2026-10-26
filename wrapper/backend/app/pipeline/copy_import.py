"""Copy Push: parse user-supplied copy (an uploaded .xlsx/.docx/.txt, or pasted
text) into the structured shape each platform's API expects.

Deliberately NOT LLM-based - the copy already exists, written by a human, in a
predictable layout; this is direct parsing, not interpretation. No Anthropic
API call, no credit cost, no risk of silently rewriting someone's copy.

Expected layout, since multiple channels can share one file:
  .xlsx - one sheet per channel, sheet name matching the channel key
          ("smartlead" / "heyreach" / "interakt", case-insensitive).
  .docx / .txt / pasted text - one [CHANNEL] section header per channel
          (e.g. "[SMARTLEAD]"), each followed by that channel's own markers.

Per-channel columns (xlsx) / markers (docx/text):
  smartlead - columns: step, delay_days, subject, body, variant (variant optional, defaults "A")
              markers:  "Day N" (or "Step N") heading, then "Subject:" / "Body:" lines
  heyreach  - columns: slot, message, fallback  (slot one of dm1_connected/dm1_not_connected/dm2/dm3/dm4)
              markers:  "DM1 (connected):" / "DM1 (not connected):" / "DM2:" / "DM3:" / "DM4:"
                        heading, then "Message:" / "Fallback:" lines
  interakt  - columns: name, body, variables (variables comma-separated)
              markers:  "Name:" / "Body:" / "Variables:" lines

Target shapes (CLAUDE.md "Smartlead Details" / scripts/17_heyreach_push_campaign.py docstring):
  smartlead: {"sequences": [{"seq_number", "seq_delay_details", "seq_variants": [{"subject", "email_body", "variant_label"}]}]}
  heyreach:  {"dm1_connected", "dm1_not_connected", "dm2", "dm3", "dm4"} each {"message", "fallback"}
  interakt:  {"name", "body", "variables": [...]} - a template description, not a push
             (Interakt's API can only check an existing template's approval
             status, not submit a new one - see pipeline/interakt.check_template).

This is a first-draft layout, not a confirmed one - built before seeing a real
example file. Adjust the column/marker names below once a real doc/sheet is
shared, rather than asking the user to reformat their file to match.
"""
from __future__ import annotations

import io
import re

from .._lazy import pd

_HEYREACH_SLOTS = ["dm1_connected", "dm1_not_connected", "dm2", "dm3", "dm4"]
_HEYREACH_HEADING_TO_SLOT = {
    "dm1 (connected)": "dm1_connected", "dm1 connected": "dm1_connected",
    "dm1 (not connected)": "dm1_not_connected", "dm1 not connected": "dm1_not_connected",
    "dm2": "dm2", "dm3": "dm3", "dm4": "dm4",
}
_DEFAULT_DELAY_DAYS = [0, 3, 6, 9, 11]  # this kit's standard 5-step cadence, used when a sheet/doc omits delay_days


def is_excel(filename: str) -> bool:
    return filename.lower().endswith((".xlsx", ".xls"))


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


# ---------------------------------------------------------------------------
# Excel: one sheet per channel
# ---------------------------------------------------------------------------

def _sheet_for_channel(file_bytes: bytes, channel: str):
    xls = pd.ExcelFile(io.BytesIO(file_bytes))
    match = next((s for s in xls.sheet_names if s.strip().lower() == channel), None)
    if match is None and len(xls.sheet_names) == 1:
        match = xls.sheet_names[0]  # single-sheet file with no channel-named tab - use it for whichever channel was asked
    if match is None:
        return None
    return pd.read_excel(xls, sheet_name=match)


def _smartlead_from_excel(df) -> dict:
    sequences = []
    for i, row in df.iterrows():
        delay = row.get("delay_days")
        delay = int(delay) if pd.notna(delay) else _DEFAULT_DELAY_DAYS[min(i, len(_DEFAULT_DELAY_DAYS) - 1)]
        body = _s(row.get("body")) or _s(row.get("email_body"))
        paragraphs = "".join(f"<p>{line}</p>" for line in body.splitlines() if line.strip())
        variant = _s(row.get("variant")) or "A"
        sequences.append({
            "seq_number": int(row.get("step", i + 1)),
            "seq_delay_details": {"delay_in_days": delay},
            "seq_variants": [{"subject": _s(row.get("subject")), "email_body": paragraphs, "variant_label": variant}],
        })
    return {"sequences": sequences}


def _heyreach_from_excel(df) -> dict:
    copy = {}
    for _, row in df.iterrows():
        slot = _s(row.get("slot")).lower()
        if slot in _HEYREACH_SLOTS:
            copy[slot] = {"message": _s(row.get("message")), "fallback": _s(row.get("fallback"))}
    return copy


def _interakt_from_excel(df) -> dict:
    row = df.iloc[0] if len(df) else {}
    variables = [v.strip() for v in _s(row.get("variables")).split(",") if v.strip()]
    return {"name": _s(row.get("name")), "body": _s(row.get("body")), "variables": variables}


# ---------------------------------------------------------------------------
# Docx / text: [CHANNEL] sections with per-channel markers
# ---------------------------------------------------------------------------

_CHANNEL_HEADER_RE = re.compile(r"^\s*\[(smartlead|heyreach|interakt)\]\s*$", re.IGNORECASE)
_LABEL_RE = re.compile(r"^\s*(subject|body|message|fallback|name|variables)\s*:\s*(.*)$", re.IGNORECASE)
_SMARTLEAD_HEADING_RE = re.compile(r"^\s*(day|step)\s+(\d+)\s*:?\s*$", re.IGNORECASE)
_HEYREACH_HEADING_RE = re.compile(r"^\s*(dm1\s*\(connected\)|dm1\s*\(not connected\)|dm1 connected|dm1 not connected|dm2|dm3|dm4)\s*:?\s*$", re.IGNORECASE)


def extract_text(filename: str, file_bytes: bytes) -> str:
    """Plain text from an uploaded .docx/.txt copy file."""
    if filename.lower().endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)
    return file_bytes.decode("utf-8", errors="replace")


def _channel_sections(text: str) -> dict[str, list[str]]:
    """Split text into {channel: [lines]} by [CHANNEL] headers. If no headers
    are present at all, every line goes under a single implicit "_all" key,
    so a single-channel push doesn't require the [CHANNEL] header."""
    sections: dict[str, list[str]] = {}
    current = "_all"
    for line in text.splitlines():
        m = _CHANNEL_HEADER_RE.match(line)
        if m:
            current = m.group(1).lower()
            sections.setdefault(current, [])
        else:
            sections.setdefault(current, []).append(line)
    return sections


def _parse_smartlead_text(lines: list[str]) -> dict:
    sequences = []
    delay, subject, body_lines, current_label = None, "", [], None
    def _flush():
        if delay is not None or subject or body_lines:
            paragraphs = "".join(f"<p>{l}</p>" for l in body_lines if l.strip())
            d = delay if delay is not None else _DEFAULT_DELAY_DAYS[min(len(sequences), len(_DEFAULT_DELAY_DAYS) - 1)]
            sequences.append({"seq_number": len(sequences) + 1, "seq_delay_details": {"delay_in_days": d},
                              "seq_variants": [{"subject": subject, "email_body": paragraphs, "variant_label": "A"}]})

    for line in lines:
        heading = _SMARTLEAD_HEADING_RE.match(line)
        if heading:
            _flush()
            # "Day N" gives the delay directly; "Step N" leaves delay to the
            # positional default (_DEFAULT_DELAY_DAYS) - N there is the step's
            # 1-indexed position, not a day offset, and seq_number is always
            # assigned by position (len(sequences)+1) regardless of which
            # heading style or what number was written, so out-of-order or
            # repeated headings still number sequentially.
            kind, n = heading.group(1).lower(), int(heading.group(2))
            delay = n if kind == "day" else None
            subject, body_lines, current_label = "", [], None
            continue
        label = _LABEL_RE.match(line)
        if label and label.group(1).lower() in ("subject", "body"):
            current_label = label.group(1).lower()
            rest = label.group(2)
            if current_label == "subject":
                subject = rest
            elif rest:
                body_lines.append(rest)
            continue
        if current_label == "body":
            body_lines.append(line)
    _flush()
    return {"sequences": sequences}


def _parse_heyreach_text(lines: list[str]) -> dict:
    copy = {}
    slot, message, fallback, current_label = None, "", "", None
    def _flush():
        if slot:
            copy[slot] = {"message": message.strip(), "fallback": fallback.strip()}

    for line in lines:
        heading = _HEYREACH_HEADING_RE.match(line)
        if heading:
            _flush()
            slot = _HEYREACH_HEADING_TO_SLOT.get(heading.group(1).lower().replace(" ", " "))
            message, fallback, current_label = "", "", None
            continue
        label = _LABEL_RE.match(line)
        if label and label.group(1).lower() in ("message", "fallback"):
            current_label = label.group(1).lower()
            if current_label == "message":
                message = label.group(2)
            else:
                fallback = label.group(2)
            continue
        if current_label == "message":
            message += ("\n" + line if message else line)
        elif current_label == "fallback":
            fallback += ("\n" + line if fallback else line)
    _flush()
    return copy


def _parse_interakt_text(lines: list[str]) -> dict:
    name, body, variables = "", "", []
    current_label = None
    for line in lines:
        label = _LABEL_RE.match(line)
        if label:
            current_label = label.group(1).lower()
            rest = label.group(2)
            if current_label == "name":
                name = rest.strip()
            elif current_label == "variables":
                variables = [v.strip() for v in rest.split(",") if v.strip()]
            elif current_label == "body":
                body = rest
            continue
        if current_label == "body" and line.strip():
            body += ("\n" + line if body else line)
    return {"name": name, "body": body, "variables": variables}


_TEXT_PARSERS = {"smartlead": _parse_smartlead_text, "heyreach": _parse_heyreach_text, "interakt": _parse_interakt_text}
_EXCEL_PARSERS = {"smartlead": _smartlead_from_excel, "heyreach": _heyreach_from_excel, "interakt": _interakt_from_excel}
_REQUIRED_HEYREACH_KEYS = set(_HEYREACH_SLOTS)


def parse_copy(channel: str, *, text: str | None = None, filename: str | None = None, file_bytes: bytes | None = None) -> dict:
    """Parse one channel's copy out of either pasted text, a .docx/.txt upload
    (text/filename+file_bytes with a non-excel name), or an .xlsx upload
    (filename+file_bytes). Returns {"status": "done", "mapped": {...}} or
    {"status": "error", "message": ...} - never raises."""
    if channel not in _TEXT_PARSERS:
        return {"status": "error", "message": f"Unknown channel {channel!r}"}

    try:
        if filename and file_bytes is not None and is_excel(filename):
            df = _sheet_for_channel(file_bytes, channel)
            if df is None:
                return {"status": "error", "message": f"No sheet named {channel!r} found in the uploaded workbook."}
            mapped = _EXCEL_PARSERS[channel](df)
        else:
            source = text if text is not None else extract_text(filename or "copy.txt", file_bytes or b"")
            if not source or not source.strip():
                return {"status": "error", "message": "No copy text to parse"}
            sections = _channel_sections(source)
            lines = sections.get(channel) or sections.get("_all")
            if lines is None:
                return {"status": "error", "message": f"No [{channel.upper()}] section found in the uploaded copy."}
            mapped = _TEXT_PARSERS[channel](lines)
    except Exception as e:
        return {"status": "error", "message": f"Could not parse copy for {channel}: {e}"}

    if channel == "heyreach":
        missing = _REQUIRED_HEYREACH_KEYS - mapped.keys()
        if missing:
            return {"status": "parse_error",
                     "message": f"Parsed copy is missing required slot(s): {', '.join(sorted(missing))}"}
    if channel == "smartlead" and not mapped.get("sequences"):
        return {"status": "parse_error", "message": "No email steps found (expected 'Day N:' / 'Step N:' headings or a 'step' column)."}
    if channel == "interakt" and not mapped.get("body"):
        return {"status": "parse_error", "message": "No template body found (expected a 'Body:' line or a 'body' column)."}

    return {"status": "done", "mapped": mapped}
