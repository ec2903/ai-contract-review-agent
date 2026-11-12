"""Pre-save audit: re-open what was written and check it against the rules.

Each check exists because the mistake it catches is easy to make and hard
to see in a spreadsheet.
"""
from __future__ import annotations

from typing import List

from .rulebook import Rulebook
from .workbook import FORMULA_COLS, INPUT_COLS, YELLOW, header_map

ANNUAL_ONLY = {"Annual - All Years", "Annual - Some Years", "No Commitment"}
PCT_COLS = ["Platform Discount %", "Compute Discount %", "Storage Discount %"]


def _is_yellow(cell) -> bool:
    return cell.fill is not None and cell.fill.fgColor is not None and \
        str(cell.fill.fgColor.rgb).upper().endswith(YELLOW.fgColor.rgb[-6:].upper()) and \
        cell.fill.fill_type == "solid"


def audit_row(ws, row: int, rules: Rulebook) -> List[str]:
    h = header_map(ws)
    v = lambda k: ws.cell(row, h[k]).value  # noqa: E731
    p: List[str] = []
    tag = f"row {row}"

    cat, upfront = v("Commitment Category"), v("Upfront Type")
    if cat not in rules.commitment_categories:
        p.append(f"{tag}: Commitment Category {cat!r} is not a rulebook category")
    if upfront not in rules.upfront_types:
        p.append(f"{tag}: Upfront Type {upfront!r} is not a rulebook type")

    # Term Commitment rule
    years = [v(f"Year {i} Commitment") or 0 for i in range(1, 6)]
    if cat in ANNUAL_ONLY and v("Term Commitment"):
        p.append(f"{tag}: Term Commitment must be blank for {cat}")
    if cat == "Term Only" and years[0] and v("Term Commitment"):
        p.append(f"{tag}: Term Only commitment recorded twice (Year 1 and Term Commitment)")
    if cat == "Term + Annual" and not (any(years) and v("Term Commitment")):
        p.append(f"{tag}: Term + Annual needs both annual amounts and Term Commitment")
    if (v("Sum of Annual Commitments") or 0) != sum(years):
        p.append(f"{tag}: Sum of Annual Commitments does not equal Year 1-5")

    for k in PCT_COLS:
        x = v(k)
        if isinstance(x, (int, float)) and 0 < x < 1:
            p.append(f"{tag}: {k} looks like a fraction ({x}); use whole numbers")

    notes = v("Notes") or ""
    if not notes.startswith("This agreement gives"):
        p.append(f"{tag}: Notes must open with the summary sentence")
    if "\n\nNotes:\n1. " not in notes:
        p.append(f"{tag}: Notes must contain a numbered 'Notes:' list")
    last = notes.rstrip().splitlines()[-1] if notes.strip() else ""
    if not last.startswith("Outlier review:"):
        p.append(f"{tag}: Notes must end with the outlier conclusion")
    elif (v("Outlier") == "Yes") != last.startswith("Outlier review: OUTLIER"):
        p.append(f"{tag}: Outlier column disagrees with the Notes conclusion")

    for k in INPUT_COLS:
        if _is_yellow(ws.cell(row, h[k])):
            p.append(f"{tag}: input column {k!r} is highlighted (it must never be written)")
    for k in FORMULA_COLS:
        c = ws.cell(row, h[k])
        if not (isinstance(c.value, str) and c.value.startswith("=")):
            p.append(f"{tag}: formula column {k!r} was overwritten")
        if _is_yellow(c):
            p.append(f"{tag}: formula column {k!r} is highlighted")
    return p
