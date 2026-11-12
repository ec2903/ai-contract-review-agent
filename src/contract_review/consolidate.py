"""Consolidation: merge every reviewer's finished owner file into one copy.

Pure, deterministic code - no model involved. Merging finished rows needs no
judgement, so an LLM would only add risk (e.g. "helpfully" re-analysing a
row a reviewer already signed off).

Guarantees:
  * never modifies the master or any owner file - writes a new "- Consolidated" copy
  * takes from each owner file only the rows that owner owns
  * a row is complete only when its Notes cell is filled
  * matches by File Name, falling back to Customer
  * never overwrites a value with a blank
  * duplicate ownership: first file wins, conflict reported
  * every written cell is highlighted, as in Review Mode
"""
from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List, Optional

from openpyxl import load_workbook

from .workbook import AGENT_COLS, SHEET, YELLOW, check_not_open, header_map


@dataclass
class OwnerFile:
    path: Path
    owner: Optional[str]
    completed: int


@dataclass
class MergePlan:
    master: Path
    output: Path
    owner_files: List[OwnerFile]
    merged: Dict[str, List[str]] = field(default_factory=dict)
    skipped_other_owner: Dict[str, List[str]] = field(default_factory=dict)
    conflicts: List[str] = field(default_factory=list)
    unmatched: List[str] = field(default_factory=list)
    not_completed: List[str] = field(default_factory=list)

    def render(self, dry_run: bool) -> str:
        out = [f"Master: {self.master.name}"]
        for f in self.owner_files:
            out.append(f"  owner file {f.path.name}: owner={f.owner!r}, completed rows={f.completed}")
        out.append(("Would merge" if dry_run else "Merged") + ":")
        for name, rows in self.merged.items():
            out.append(f"  - {name}: {len(rows)} row(s)")
        for title, items in (("Skipped (row belongs to another owner)",
                              [f"{k}: {', '.join(v)}" for k, v in self.skipped_other_owner.items()]),
                             ("Conflicts (first owner kept)", self.conflicts),
                             ("Unmatched (no master row)", self.unmatched),
                             ("Assigned but not completed", self.not_completed)):
            out.append(f"{title}:" + ("" if items else " none"))
            out += [f"  - {i}" for i in items]
        out.append(("Output (not written - dry run): " if dry_run else "Output: ") + str(self.output))
        return "\n".join(out)


def _rows(ws):
    h = header_map(ws)
    for r in range(2, ws.max_row + 1):
        yield r, {k: ws.cell(r, c).value for k, c in h.items()}


def list_review_files(master: Path) -> List[OwnerFile]:
    files = []
    for p in sorted(master.parent.glob(f"{master.stem} - *.xlsx")):
        if p.name.startswith("~$") or p.stem.endswith("- Consolidated"):
            continue
        ws = load_workbook(p, read_only=True)[SHEET]
        owners = Counter(v["Owner"] for v in _rows_ro(ws) if v.get("Notes"))
        files.append(OwnerFile(p, owners.most_common(1)[0][0] if owners else None, sum(owners.values())))
    return files


def _rows_ro(ws):
    rows = ws.iter_rows(values_only=True)
    header = [str(h).strip() if h is not None else None for h in next(rows)]
    for vals in rows:
        yield dict(zip(header, vals))


def consolidate(master: Path, dry_run: bool = False) -> MergePlan:
    master = Path(master)
    out_path = master.with_name(f"{master.stem} - Consolidated.xlsx")
    plan = MergePlan(master, out_path, list_review_files(master))

    wb = load_workbook(master)          # loaded, never saved back to `master`
    ws = wb[SHEET]
    h = header_map(ws)
    by_file = {v["File Name"]: r for r, v in _rows(ws) if v.get("File Name")}
    by_customer = {v["Customer"]: r for r, v in _rows(ws) if v.get("Customer")}
    taken: Dict[int, str] = {}

    for f in plan.owner_files:
        if f.owner is None:
            continue
        check_not_open(f.path)
        src = load_workbook(f.path)[SHEET]
        for _, v in _rows(src):
            if not v.get("Notes"):
                continue
            key = v.get("File Name") or v.get("Customer")
            if v.get("Owner") != f.owner:
                plan.skipped_other_owner.setdefault(f.path.name, []).append(str(key))
                continue
            r = by_file.get(v.get("File Name")) or by_customer.get(v.get("Customer"))
            if r is None:
                plan.unmatched.append(f"{key} (from {f.path.name})")
                continue
            if r in taken:
                plan.conflicts.append(f"{key}: completed by {taken[r]} and {f.owner}")
                continue
            taken[r] = f.owner
            plan.merged.setdefault(f.owner, []).append(str(key))
            if dry_run:
                continue
            for col in AGENT_COLS:
                val = v.get(col)
                if val in (None, ""):
                    continue  # never overwrite with a blank
                cell = ws.cell(r, h[col])
                cell.value = val
                cell.fill = YELLOW

    for r, v in _rows(ws):
        if v.get("Owner") and r not in taken and not v.get("Notes"):
            plan.not_completed.append(f"{v.get('File Name')} (owner {v.get('Owner')})")

    if not dry_run:
        wb.save(out_path)
    return plan
