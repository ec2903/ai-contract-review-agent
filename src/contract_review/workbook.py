"""Read and write the review workbook.

The workbook layout is owned by the team that consumes it, so this module
adapts to it: columns are found by header name, input and formula columns
are never written, and only cells the tool wrote are highlighted.
"""
from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from openpyxl import Workbook, load_workbook
from openpyxl.styles import Alignment, Font, PatternFill

SHEET = "Review"
YELLOW = PatternFill("solid", start_color="FFFF00", end_color="FFFF00")
HEADER_FILL = PatternFill("solid", start_color="D9E1F2", end_color="D9E1F2")
AGENT_FILL = PatternFill("solid", start_color="E2EFDA", end_color="E2EFDA")  # "fill me in" columns

INPUT_COLS = ["Owner", "File Name", "Agreement ID", "Customer"]
AGENT_COLS = [
    "Start Date", "End Date", "Term (Months)", "Platform Discount %",
    "Year 1 Commitment", "Year 2 Commitment", "Year 3 Commitment",
    "Year 4 Commitment", "Year 5 Commitment", "Sum of Annual Commitments",
    "Term Commitment", "Avg Annual Commitment", "Commitment Tier",
    "Commitment Category", "Upfront Type", "Compute Discount %",
    "Storage Discount %", "Credits Total", "Termination for Convenience",
    "Zero Commitment", "Outlier", "Notes",
]
# Formula columns belong to the workbook owner. Never written by the tool.
FORMULA_COLS = {
    "Compute Variance to Platform": ("Compute Discount %", "Platform Discount %"),
    "Storage Variance to Platform": ("Storage Discount %", "Platform Discount %"),
}
ALL_COLS = INPUT_COLS + AGENT_COLS + list(FORMULA_COLS)


class WorkbookLocked(RuntimeError):
    pass


def header_map(ws) -> Dict[str, int]:
    return {str(c.value).strip(): c.column for c in ws[1] if c.value is not None}


def check_not_open(path: Path) -> None:
    lock = path.with_name("~$" + path.name)
    if lock.exists():
        raise WorkbookLocked(f"{path.name} is open in Excel ({lock.name} exists). Close it first.")


def owner_path(master: Path, initials: str) -> Path:
    return master.with_name(f"{master.stem} - {initials.upper()}.xlsx")


def create_template(path: Path, rows: List[Dict[str, str]]) -> None:
    """Build a blank review workbook (used for the synthetic sample)."""
    wb = Workbook()
    ws = wb.active
    ws.title = SHEET
    ws.append(ALL_COLS)
    for c in ws[1]:
        c.font = Font(bold=True)
        c.fill = AGENT_FILL if c.value in AGENT_COLS else HEADER_FILL
        c.alignment = Alignment(wrap_text=True, vertical="top")
    cols = {name: i + 1 for i, name in enumerate(ALL_COLS)}
    for r, row in enumerate(rows, start=2):
        for k in INPUT_COLS:
            ws.cell(r, cols[k], row[k])
        for name, (a, b) in FORMULA_COLS.items():
            ca = ws.cell(r, cols[a]).coordinate
            cb = ws.cell(r, cols[b]).coordinate
            ws.cell(r, cols[name], f'=IF({ca}="","",{ca}-{cb})')
    for name, col in cols.items():
        ws.column_dimensions[ws.cell(1, col).column_letter].width = 60 if name == "Notes" else 16
    ws.freeze_panes = "E2"
    wb.save(path)


def target_rows(ws, owner: str) -> List[Dict[str, Any]]:
    h = header_map(ws)
    out = []
    for r in range(2, ws.max_row + 1):
        if str(ws.cell(r, h["Owner"]).value or "").strip().lower() != owner.strip().lower():
            continue
        if ws.cell(r, h["Notes"]).value:
            continue
        out.append({"row": r, **{k: ws.cell(r, h[k]).value for k in INPUT_COLS}})
    return out


def _cell_value(v: Any) -> Any:
    if isinstance(v, date) and not isinstance(v, datetime):
        return datetime(v.year, v.month, v.day)
    return v


def write_row(ws, row: int, values: Dict[str, Any], expected_file: str) -> List[str]:
    """Write one row of agent values. Returns the headers written."""
    h = header_map(ws)
    if ws.cell(row, h["File Name"]).value != expected_file:
        raise ValueError(f"row {row} is not {expected_file!r}; refusing to write")
    written = []
    for k, v in values.items():
        if k in INPUT_COLS or k in FORMULA_COLS:
            raise ValueError(f"{k!r} is not an agent column")
        if k not in h:
            continue
        cell = ws.cell(row, h[k])
        cell.value = _cell_value(v)
        cell.fill = YELLOW
        if k in ("Start Date", "End Date") and v is not None:
            cell.number_format = "yyyy-mm-dd"
        elif isinstance(v, (int, float)) and ("Commitment" in k or k == "Credits Total"):
            cell.number_format = "#,##0"
        if k == "Notes":
            cell.alignment = Alignment(wrap_text=True, vertical="top")
        written.append(k)
    return written


def open_for_owner(master: Path, initials: str):
    """Open the owner's file if it exists, else the master (never saved over)."""
    dest = owner_path(master, initials)
    src = dest if dest.exists() else master
    check_not_open(src)
    wb = load_workbook(src)
    return wb, wb[SHEET], dest


def read_value(ws, row: int, header: str) -> Optional[Any]:
    return ws.cell(row, header_map(ws)[header]).value
