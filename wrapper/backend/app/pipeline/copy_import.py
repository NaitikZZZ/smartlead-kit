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
_INMAIL_SLOTS = ["inmail1", "inmail2"]  # extra slots for the Open Profile (Sales Navigator) workflow
_HEYREACH_HEADING_TO_SLOT = {
    "dm1 (connected)": "dm1_connected", "dm1 connected": "dm1_connected",
    "dm1 (not connected)": "dm1_not_connected", "dm1 not connected": "dm1_not_connected",
    "dm2": "dm2", "dm3": "dm3", "dm4": "dm4",
    "inmail 1": "inmail1", "inmail1": "inmail1", "inmail 2": "inmail2", "inmail2": "inmail2",
}
DEFAULT_DELAY_DAYS = [0, 3, 6, 9, 11]  # this kit's standard 5-step cadence, used when a sheet/doc omits delay_days


# Warnings collected while parsing one channel (e.g. a removed sign-off).
# parse_copy() resets it per call and runs synchronously, so a module-level
# list is safe here.
_WARN: list[str] = []


_DASH_RE = re.compile(r"\s*[\u2014\u2013]\s*")


def _replace_dashes(obj) -> int:
    """Swap every em/en dash in the parsed copy for a spaced hyphen, in place.
    Returns how many were replaced."""
    count = 0
    if isinstance(obj, dict):
        for k, v in obj.items():
            if isinstance(v, str):
                obj[k], c = _DASH_RE.subn(" - ", v)
                count += c
            else:
                count += _replace_dashes(v)
    elif isinstance(obj, list):
        for i, v in enumerate(obj):
            if isinstance(v, str):
                obj[i], c = _DASH_RE.subn(" - ", v)
                count += c
            else:
                count += _replace_dashes(v)
    return count


def is_excel(filename: str) -> bool:
    return filename.lower().endswith((".xlsx", ".xls"))


def _s(v) -> str:
    if v is None or (isinstance(v, float) and pd.isna(v)):
        return ""
    return str(v).strip()


_SIGNOFF_RE = re.compile(r"^\s*(thanks|thank you|best|best regards|kind regards|warm regards|regards|cheers|sincerely|"
                         r"talk soon|speak soon|many thanks)[,.!]?\s*$", re.IGNORECASE)


def strip_signoff(text: str) -> tuple[str, bool]:
    """Copy must not carry a signature (the sender's own is added by the
    platform). Drops a trailing sign-off line plus up to two short name/title
    lines after it, and reports whether it did. Only touches the very end of
    the text, and only when a recognised sign-off word is there."""
    lines = text.rstrip().splitlines()
    for i in range(len(lines) - 1, max(len(lines) - 4, -1), -1):
        if _SIGNOFF_RE.match(lines[i]) and all(len(l.strip()) <= 40 for l in lines[i + 1:]):
            return "\n".join(lines[:i]).rstrip(), True
    return text, False


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
        delay = int(delay) if pd.notna(delay) else DEFAULT_DELAY_DAYS[min(i, len(DEFAULT_DELAY_DAYS) - 1)]
        body = _s(row.get("body")) or _s(row.get("email_body"))
        body, stripped = strip_signoff(body)
        if stripped:
            _WARN.append(f"Email {i + 1}: removed a sign-off (copy should not include a signature).")
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
        if slot in _HEYREACH_SLOTS + _INMAIL_SLOTS:
            msg, stripped = strip_signoff(_s(row.get("message")))
            if stripped:
                _WARN.append(f"{slot}: removed a sign-off (copy should not include a signature).")
            copy[slot] = {"message": msg, "fallback": _s(row.get("fallback")), "subject": _s(row.get("subject"))}
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
_HEYREACH_HEADING_RE = re.compile(r"^\s*(dm1\s*\(connected\)|dm1\s*\(not connected\)|dm1 connected|dm1 not connected|dm2|dm3|dm4|inmail\s*1|inmail\s*2)\s*:?\s*$", re.IGNORECASE)


def extract_text(filename: str, file_bytes: bytes) -> str:
    """Plain text from an uploaded .docx/.txt copy file (paragraphs only -
    tables are read separately by _docx_tables)."""
    if filename.lower().endswith(".docx"):
        from docx import Document
        doc = Document(io.BytesIO(file_bytes))
        return "\n".join(p.text for p in doc.paragraphs)
    return file_bytes.decode("utf-8", errors="replace")


def _docx_tables(file_bytes: bytes) -> list:
    """Each Word table whose first row looks like a header, as a DataFrame -
    so a table with the template's column names reads exactly like an Excel
    sheet. Cell line breaks are kept."""
    from docx import Document
    frames = []
    for t in Document(io.BytesIO(file_bytes)).tables:
        rows = [[c.text.strip() for c in r.cells] for r in t.rows]
        if len(rows) >= 2:
            frames.append(pd.DataFrame(rows[1:], columns=[h.strip().lower() for h in rows[0]]))
    return frames


_TABLE_SIGNATURES = {
    "smartlead": ({"subject"}, {"body", "email_body"}),
    "heyreach": ({"slot"}, {"message"}),
    "interakt": ({"name"}, {"body", "variables"}),
}


def _table_for_channel(frames: list, channel: str):
    must, any_of = _TABLE_SIGNATURES[channel]
    for df in frames:
        cols = set(df.columns)
        if must <= cols and cols & any_of and not (channel == "smartlead" and "name" in cols):
            return df
    return None


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
            clean, stripped = strip_signoff("\n".join(body_lines))
            if stripped:
                _WARN.append(f"Email {len(sequences) + 1}: removed a sign-off (copy should not include a signature).")
            paragraphs = "".join(f"<p>{l}</p>" for l in clean.splitlines() if l.strip())
            d = delay if delay is not None else DEFAULT_DELAY_DAYS[min(len(sequences), len(DEFAULT_DELAY_DAYS) - 1)]
            sequences.append({"seq_number": len(sequences) + 1, "seq_delay_details": {"delay_in_days": d},
                              "seq_variants": [{"subject": subject, "email_body": paragraphs, "variant_label": "A"}]})

    for line in lines:
        heading = _SMARTLEAD_HEADING_RE.match(line)
        if heading:
            _flush()
            # "Day N" gives the delay directly; "Step N" leaves delay to the
            # positional default (DEFAULT_DELAY_DAYS) - N there is the step's
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
    slot, message, fallback, subject, current_label = None, "", "", "", None
    def _flush():
        if slot:
            msg, stripped = strip_signoff(message.strip())
            if stripped:
                _WARN.append(f"{slot}: removed a sign-off (copy should not include a signature).")
            copy[slot] = {"message": msg, "fallback": fallback.strip(), "subject": subject.strip()}

    for line in lines:
        heading = _HEYREACH_HEADING_RE.match(line)
        if heading:
            _flush()
            slot = _HEYREACH_HEADING_TO_SLOT.get(re.sub(r"\s+", " ", heading.group(1).lower()))
            message, fallback, subject, current_label = "", "", "", None
            continue
        label = _LABEL_RE.match(line)
        if label and label.group(1).lower() in ("message", "fallback", "subject"):
            current_label = label.group(1).lower()
            if current_label == "subject":
                subject = label.group(2)
            elif current_label == "message":
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
_REQUIRED_HEYREACH_KEYS = {"dm1_connected", "dm1_not_connected"}  # the rest are optional, see heyreach.build_sequence


def parse_copy(channel: str, *, text: str | None = None, filename: str | None = None, file_bytes: bytes | None = None,
               open_profile: bool = False) -> dict:
    """Parse one channel's copy out of either pasted text, a .docx/.txt upload
    (text/filename+file_bytes with a non-excel name), or an .xlsx upload
    (filename+file_bytes). Returns {"status": "done", "mapped": {...}} or
    {"status": "error", "message": ...} - never raises."""
    if channel not in _TEXT_PARSERS:
        return {"status": "error", "message": f"Unknown channel {channel!r}"}
    _WARN.clear()

    try:
        if filename and file_bytes is not None and is_excel(filename):
            df = _sheet_for_channel(file_bytes, channel)
            if df is None:
                return {"status": "error", "message": f"No sheet named {channel!r} found in the uploaded workbook."}
            mapped = _EXCEL_PARSERS[channel](df)
        elif filename and file_bytes is not None and filename.lower().endswith(".docx") and \
                (table := _table_for_channel(_docx_tables(file_bytes), channel)) is not None:
            mapped = _EXCEL_PARSERS[channel](table)
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
        # One opener is enough: reuse it for the other case rather than fail.
        for have, lack in (("dm1_connected", "dm1_not_connected"), ("dm1_not_connected", "dm1_connected")):
            if have in mapped and lack not in mapped:
                mapped[lack] = dict(mapped[have])
                _WARN.append(f"Only {have} was provided, so it is also used for {lack}.")
        missing = (_REQUIRED_HEYREACH_KEYS | ({"inmail1"} if open_profile else set())) - mapped.keys()
        if missing:
            return {"status": "parse_error",
                     "message": f"Parsed copy is missing required slot(s): {', '.join(sorted(missing))}"}
    if channel == "smartlead" and not mapped.get("sequences"):
        return {"status": "parse_error", "message": "No email steps found (expected 'Day N:' / 'Step N:' headings or a 'step' column)."}
    if channel == "interakt" and not mapped.get("body"):
        return {"status": "parse_error", "message": "No template body found (expected a 'Body:' line or a 'body' column)."}

    n = _replace_dashes(mapped)
    if n:
        _WARN.append(f"Replaced {n} em/en dash(es) with hyphens (copy should not use them).")
    return {"status": "done", "mapped": mapped, "warnings": list(_WARN)}


# ---------------------------------------------------------------------------
# Downloadable templates - the exact layout parse_copy() reads, pre-filled with
# example copy so a teammate can see what a finished file looks like.
# ---------------------------------------------------------------------------

_EX_SMARTLEAD = [
    (1, 0, "Quick question, {{first_name}}", "Hi {{first_name}},\nI work with teams like {{company_name}} on rewards and incentives.\nWould it be useful to compare notes?"),
    (2, 3, "Re: Quick question, {{first_name}}", "Hi {{first_name}},\nFollowing up on my note below. Worth a 15-min chat?"),
    (3, 6, "One idea for {{company_name}}", "Hi {{first_name}},\nOne idea that has worked for similar teams: ...\nOpen to a quick call?"),
]
_EX_HEYREACH = [
    ("dm1_connected", "Hi {FIRST_NAME}, since we're connected, wanted to share a quick idea for {COMPANY}.", ""),
    ("dm1_not_connected", "Thanks for connecting, {FIRST_NAME}. Quick idea for {COMPANY}...", ""),
    ("dm2", "Hi {FIRST_NAME}, following up with a bit more context on how this works.", ""),
    ("dm3", "{FIRST_NAME}, a quick proof point from a team similar to {COMPANY}...", ""),
    ("dm4", "{FIRST_NAME}, happy to share a short example if useful.", ""),
]
_EX_INMAIL = [
    ("inmail1", "Quick question, {FIRST_NAME}", "Hi {FIRST_NAME}, I work with teams like {COMPANY} on rewards. Worth a short conversation?"),
    ("inmail2", "Following up, {FIRST_NAME}", "Following up in case my last note got buried. Happy to share a quick example."),
]
_EX_INTERAKT = ("your_template_name", "Hi {{1}}, a quick note from Xoxoday about rewards for {{2}}.", "first_name, company_name")


def build_template_xlsx(channels: list[str], open_profile: bool = False) -> bytes:
    from openpyxl import Workbook
    from openpyxl.styles import Alignment, Font, PatternFill
    wb = Workbook()
    wb.remove(wb.active)
    head_fill, head_font = PatternFill("solid", fgColor="E8EFFD"), Font(bold=True)

    def sheet(name, headers, rows, widths):
        ws = wb.create_sheet(name)
        ws.append(headers)
        for r in rows:
            ws.append(list(r))
        for c in ws[1]:
            c.fill, c.font = head_fill, head_font
        for i, w in enumerate(widths):
            ws.column_dimensions[chr(65 + i)].width = w
        for row in ws.iter_rows(min_row=2):
            for c in row:
                c.alignment = Alignment(wrap_text=True, vertical="top")

    if "smartlead" in channels:
        sheet("smartlead", ["step", "delay_days", "subject", "body", "variant"],
              [(*r, "A") for r in _EX_SMARTLEAD], [8, 12, 34, 70, 10])
    if "heyreach" in channels:
        rows = [(slot, msg, fb, "") for slot, msg, fb in _EX_HEYREACH]
        if open_profile:
            rows += [(slot, msg, "", subj) for slot, subj, msg in _EX_INMAIL]
        sheet("heyreach", ["slot", "message", "fallback", "subject"], rows, [20, 80, 40, 30])
    if "interakt" in channels:
        sheet("interakt", ["name", "body", "variables"], [_EX_INTERAKT], [26, 70, 30])
    notes = wb.create_sheet("README")
    readme = {
        "smartlead": "smartlead: one row per email. step = order, delay_days = days after the previous email, body = line breaks become paragraphs, variant optional (A/B). Merge tags: {{first_name}} {{company_name}}.",
        "heyreach": "heyreach: slots dm1_connected and dm1_not_connected are required; dm2, dm3, dm4 are optional (the cadence ends after the last one you give)" + ("; inmail1 is required and inmail2 optional, both with a subject" if open_profile else "") + ". fallback is optional. Merge tags: {FIRST_NAME} {COMPANY} (single braces, uppercase).",
        "interakt": "interakt: one template. variables = comma-separated names, in order.",
    }
    for line in [
        "How this file is read",
        ("One sheet per platform, named " + " / ".join(c for c in ("smartlead", "heyreach", "interakt") if c in channels) + "." if len(channels) > 1
         else f"One sheet, named {channels[0]}."),
        *[readme[c] for c in ("smartlead", "heyreach", "interakt") if c in channels],
        "Replace the example copy. No signature or sign-off at the end (the platform adds the sender's own). No em or en dashes.",
    ]:
        notes.append([line])
    notes["A1"].font = head_font
    notes.column_dimensions["A"].width = 120
    import io as _io
    buf = _io.BytesIO()
    wb.save(buf)
    return buf.getvalue()


def build_template_text(channels: list[str], open_profile: bool = False) -> bytes:
    tags = {"smartlead": "Smartlead {{first_name}} {{company_name}}", "heyreach": "HeyReach {FIRST_NAME} {COMPANY}",
            "interakt": "Interakt {{1}} {{2}}"}
    out = ["# Replace the example copy below." + (" One [CHANNEL] block per platform." if len(channels) > 1 else ""),
           "# No signature or sign-off at the end of any message.",
           "# Merge tags: " + "; ".join(tags[c] for c in ("smartlead", "heyreach", "interakt") if c in channels) + ".", ""]
    if "smartlead" in channels:
        out.append("[SMARTLEAD]")
        for _, delay, subject, body in _EX_SMARTLEAD:
            out += [f"Day {delay}:", f"Subject: {subject}", "Body:", body, ""]
    if "heyreach" in channels:
        out.append("[HEYREACH]")
        headings = {"dm1_connected": "DM1 (connected):", "dm1_not_connected": "DM1 (not connected):",
                    "dm2": "DM2:", "dm3": "DM3:", "dm4": "DM4:"}
        for slot, message, _ in _EX_HEYREACH:
            out += [headings[slot], f"Message: {message}", "Fallback:", ""]
        if open_profile:
            for (slot, subj, msg), n in zip(_EX_INMAIL, (1, 2)):
                out += [f"InMail {n}:", f"Subject: {subj}", f"Message: {msg}", ""]
    if "interakt" in channels:
        name, body, variables = _EX_INTERAKT
        out += ["[INTERAKT]", f"Name: {name}", f"Body: {body}", f"Variables: {variables}", ""]
    return "\n".join(out).encode()


def build_claude_prompt(channels: list[str], open_profile: bool = False) -> str:
    """The brief a teammate pastes into Claude to get copy in exactly the
    layout Copy Push reads. Only layout, merge tags and the two hard rules
    (no signature, no em/en dashes) are prescribed - length, count and style
    of the copy are the writer's call. The workflow outline is generated from
    the real sequence builder so it can't drift from what gets pushed."""
    from . import heyreach
    L = ["You are writing outbound copy for Xoxoday. Write it in the exact layout at the bottom so it can be uploaded as-is.",
         "", "FIRST, ask me for anything not given below, then write:",
         "- Product: Plum, Empuls or Loyalife", "- Who we are writing to, and the region",
         "- The reason for reaching out", "- Any proof points you may use", "", "RULES FOR EVERY MESSAGE",
         "- No signature or sign-off at the end (no Thanks, Best, Regards, no name). The sender's own is added by the platform.",
         "- No em dashes or en dashes anywhere. Use commas, periods or hyphens.",
         "- Everything else (length, number of messages, tone) is up to you and the brief above.", ""]
    if "smartlead" in channels:
        L += ["EMAIL (Smartlead)", "- Write as many emails as the campaign needs. Give each a 'Day N:' heading, N being the day it is sent.",
              "- Merge tags use double braces: {{first_name}} {{company_name}}. Never {{sender_first_name}}.", ""]
    if "heyreach" in channels:
        L += ["LINKEDIN (HeyReach)", "- Connection requests carry no note, so there is nothing to write for that step.",
              "- Merge tags use single braces, uppercase: {FIRST_NAME} {COMPANY}. Never double braces.",
              "- Slots: dm1_connected and dm1_not_connected are required. dm2, dm3 and dm4 are optional, write only as many as you want (the cadence ends after the last one)."
              + (" Also inmail1 (required) and inmail2 (optional), each with a subject, under 1900 characters." if open_profile else ""),
              "- The workflow these messages sit in (each wait is hours or days):", ""]
        for n in heyreach.describe_default_sequence(open_profile):
            L.append("    " * n["depth"] + (f"[{n['branch']}] " if n["branch"] else "") + n["label"] + (f" (wait {n['wait']})" if n["wait"] else ""))
        L.append("")
    if "interakt" in channels:
        L += ["WHATSAPP (Interakt)", "- One template with numbered variables {{1}}, {{2}}. List the variable names in order.", ""]
    L += ["OUTPUT FORMAT (return exactly this, in one code block, no commentary; the example copy is only to show the layout)", "",
          build_template_text(channels, open_profile).decode()]
    return "\n".join(L)
