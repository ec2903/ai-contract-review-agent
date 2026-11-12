"""Command line entry point: python -m contract_review <command>."""
from __future__ import annotations

import argparse
import json
import shutil
import sys
from pathlib import Path

from .consolidate import consolidate
from .extract import extract_folder
from .review import run_review
from .rulebook import Rulebook

ROOT = Path(__file__).resolve().parents[2]


def cmd_extract(a) -> int:
    rules = Rulebook.load(a.rulebook)
    manifest = extract_folder(Path(a.pdf_dir), Path(a.out), rules.scanned_page_min_chars)
    for name, m in manifest.items():
        warn = f"  <- scanned pages {m['scanned_pages']}" if m["scanned_pages"] else ""
        print(f"{name}: {m['pages']} pages, {m['chars']} chars{warn}")
    return 0


def cmd_targets(a) -> int:
    """Print the reviewer's rows that still need review, as JSON, for the agent."""
    from openpyxl import load_workbook

    from .workbook import SHEET, owner_path, target_rows
    master = Path(a.workbook)
    src = owner_path(master, a.initials)
    ws = load_workbook(src if src.exists() else master, read_only=False)[SHEET]
    print(json.dumps(target_rows(ws, a.owner), indent=2, default=str))
    return 0


def cmd_review(a) -> int:
    rules = Rulebook.load(a.rulebook)
    rep = run_review(Path(a.workbook), a.owner, a.initials, Path(a.extracted), Path(a.text), rules)
    print(rep.render())
    return 1 if rep.audit_problems else 0


def cmd_consolidate(a) -> int:
    plan = consolidate(Path(a.workbook), dry_run=a.dry_run)
    print(plan.render(a.dry_run))
    return 0


def cmd_demo(a) -> int:
    """Run the whole month offline on the synthetic samples."""
    out = Path(a.out)
    if out.exists():
        shutil.rmtree(out)
    out.mkdir(parents=True)
    master = out / "Contract Review - Nov 2026.xlsx"
    shutil.copy(ROOT / "samples" / "workbook" / master.name, master)
    rules = Rulebook.load(a.rulebook)
    text = out / ".work" / "text"

    print("== 1. Extract PDFs to text ==")
    cmd_extract(argparse.Namespace(rulebook=a.rulebook, pdf_dir=ROOT / "samples" / "contracts", out=text))
    print("\n(Step 2 - reading each contract - is the agent's job. The demo uses the reference")
    print(" extractions in samples/extracted/ so it runs without a model.)")
    rc = 0
    for owner, initials in (("Alex Rivera", "AR"), ("Sam Patel", "SP")):
        print(f"\n== 3. Review rows owned by {owner} ==")
        rep = run_review(master, owner, initials, ROOT / "samples" / "extracted", text, rules)
        print(rep.render())
        rc |= bool(rep.audit_problems)
    print("\n== 4. Month end: consolidation preview (dry run) ==")
    print(consolidate(master, dry_run=True).render(True))
    print("\n== 5. Consolidate ==")
    print(consolidate(master).render(False))
    return rc


def main(argv=None) -> int:
    p = argparse.ArgumentParser(prog="contract_review", description=__doc__)
    p.add_argument("--rulebook", default=None, help="path to rulebook.yaml")
    sub = p.add_subparsers(dest="cmd", required=True)

    e = sub.add_parser("extract", help="convert every PDF in a folder to text")
    e.add_argument("pdf_dir")
    e.add_argument("--out", default=".work/text")
    e.set_defaults(fn=cmd_extract)

    t = sub.add_parser("targets", help="list a reviewer's rows that still need review")
    t.add_argument("workbook")
    t.add_argument("--owner", required=True)
    t.add_argument("--initials", required=True)
    t.set_defaults(fn=cmd_targets)

    r = sub.add_parser("review", help="apply extractions to a reviewer's rows")
    r.add_argument("workbook", help="master workbook (never modified)")
    r.add_argument("--owner", required=True)
    r.add_argument("--initials", required=True)
    r.add_argument("--extracted", default=".work/extracted")
    r.add_argument("--text", default=".work/text")
    r.set_defaults(fn=cmd_review)

    c = sub.add_parser("consolidate", help="merge owner files into a Consolidated copy")
    c.add_argument("workbook", help="master workbook (never modified)")
    c.add_argument("--dry-run", action="store_true")
    c.set_defaults(fn=cmd_consolidate)

    d = sub.add_parser("demo", help="run the full month on the synthetic samples")
    d.add_argument("--out", default="output")
    d.set_defaults(fn=cmd_demo)

    a = p.parse_args(argv)
    return a.fn(a)


if __name__ == "__main__":
    sys.exit(main())
