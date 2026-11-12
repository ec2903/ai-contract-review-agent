"""Review Mode: apply agent extractions to a reviewer's rows and save their owner file."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Dict, List

from .analyze import ExtractionError, analyze
from .audit import audit_row
from .extract import load_manifest
from .rulebook import Rulebook
from .workbook import open_for_owner, target_rows, write_row


@dataclass
class ReviewReport:
    owner_file: Path
    completed: List[str] = field(default_factory=list)
    outliers: Dict[str, List[str]] = field(default_factory=dict)
    flags: Dict[str, List[str]] = field(default_factory=dict)
    not_filled: Dict[str, str] = field(default_factory=dict)
    audit_problems: List[str] = field(default_factory=list)

    def render(self) -> str:
        out = [f"Owner file: {self.owner_file}",
               f"Completed: {len(self.completed)} row(s) - {', '.join(self.completed) or 'none'}"]
        for title, d in (("Outliers", self.outliers), ("Flags for the reviewer", self.flags)):
            out.append(f"{title}:" + ("" if d else " none"))
            for k, items in d.items():
                out += [f"  - {k}: {i}" for i in items]
        out.append("Not filled (needs a person):" + ("" if self.not_filled else " none"))
        out += [f"  - {k}: {why}" for k, why in self.not_filled.items()]
        out.append("Audit: " + ("passed" if not self.audit_problems else "FAILED"))
        out += [f"  - {p}" for p in self.audit_problems]
        return "\n".join(out)


def load_extractions(extracted_dir: Path) -> Dict[str, Dict]:
    out = {}
    for p in sorted(Path(extracted_dir).glob("*.json")):
        x = json.loads(p.read_text(encoding="utf-8"))
        out[Path(x["file_name"]).stem] = x
    return out


def run_review(master: Path, owner: str, initials: str, extracted_dir: Path,
               text_dir: Path, rules: Rulebook) -> ReviewReport:
    wb, ws, dest = open_for_owner(master, initials)
    report = ReviewReport(owner_file=dest)
    extractions = load_extractions(extracted_dir)
    manifest = load_manifest(text_dir)
    written_rows = []

    for t in target_rows(ws, owner):
        key = t["File Name"]
        stem = Path(key).stem
        x = extractions.get(stem)
        if x is None:
            report.not_filled[key] = "no extraction found - the contract was not read"
            continue
        # Never fill a row from the wrong document.
        if x.get("agreement_id") != t["Agreement ID"]:
            report.not_filled[key] = (f"document mismatch - the PDF filed under this row is agreement "
                                      f"{x.get('agreement_id')!r}, the row expects {t['Agreement ID']!r}")
            continue
        scanned = manifest.get(f"{stem}.pdf", {}).get("scanned_pages", [])
        try:
            r = analyze(x, rules, scanned)
        except ExtractionError as e:
            report.not_filled[key] = f"extraction rejected: {e}"
            continue
        write_row(ws, t["row"], r.values, key)
        written_rows.append(t["row"])
        report.completed.append(key)
        if r.outliers:
            report.outliers[key] = r.outliers
        if r.flags:
            report.flags[key] = r.flags

    for row in written_rows:
        report.audit_problems += audit_row(ws, row, rules)
    if report.audit_problems:
        # Do not save output that fails its own audit.
        return report
    wb.save(dest)
    return report
