"""Golden tests for the deterministic half of the system.

Run:  python -m unittest discover -s tests
"""
import copy
import json
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from openpyxl import load_workbook  # noqa: E402

from contract_review.analyze import ExtractionError, analyze, commitment_category, upfront_type  # noqa: E402
from contract_review.audit import audit_row  # noqa: E402
from contract_review.consolidate import consolidate  # noqa: E402
from contract_review.extract import extract_folder  # noqa: E402
from contract_review.review import run_review  # noqa: E402
from contract_review.rulebook import Rulebook  # noqa: E402
from contract_review.workbook import SHEET, WorkbookLocked, header_map, write_row  # noqa: E402

SAMPLES = ROOT / "samples"
MASTER_NAME = "Contract Review - Nov 2026.xlsx"
RULES = Rulebook.load()


def sample(stem):
    return json.loads((SAMPLES / "extracted" / f"{stem}.json").read_text())


BLUEFIN = sample("CRA-2026-0101 - Bluefin Analytics")
CEDAR = sample("CRA-2026-0102 - Cedar Ridge Health")
LUMEN = sample("CRA-2026-0103 - Lumen Public Library District")
ORBIT = sample("CRA-2026-0104 - Orbit Freight")


class RulebookTests(unittest.TestCase):
    def test_term_years(self):
        self.assertEqual([RULES.term_years(m) for m in (6, 12, 13, 24, 36, 60)], [1, 1, 2, 2, 3, 3])

    def test_tier_boundaries(self):
        self.assertEqual(RULES.commitment_tier(499999), "T1")
        self.assertEqual(RULES.commitment_tier(500000), "T2")
        self.assertEqual(RULES.commitment_tier(10_000_000), "T4")

    def test_storage_band_uses_term_and_volume(self):
        band, basis = RULES.product_band("storage", 36, "T2", committed_tb=300)
        self.assertEqual(band, (9, 18))
        self.assertIn("V2", basis)

    def test_storage_band_needs_volume(self):
        with self.assertRaises(ValueError):
            RULES.product_band("storage", 36, "T2", committed_tb=None)


class AnalyzeTests(unittest.TestCase):
    def test_clean_contract(self):
        r = analyze(BLUEFIN, RULES)
        self.assertEqual(r.outliers, [])
        self.assertEqual(r.values["Commitment Category"], "Annual - All Years")
        self.assertEqual(r.values["Commitment Tier"], "T2")
        self.assertEqual(r.values["Term (Months)"], 36)
        self.assertTrue(r.notes.startswith("This agreement gives Bluefin Analytics LLC"))
        self.assertTrue(r.notes.endswith("all rates are within approved bands."))

    def test_outlier_requires_band_breach_and_materiality(self):
        self.assertEqual(len(analyze(CEDAR, RULES).outliers), 1)       # 22% vs band max 16, +16 pts
        orbit = analyze(ORBIT, RULES)                                    # 17% vs band max 16, only +5 pts
        self.assertEqual(orbit.outliers, [])
        self.assertIn("not an outlier", orbit.notes)

    def test_term_commitment_blank_for_annual_only(self):
        # Repeating the annual sum as a term commitment would signal a deal term that does not exist.
        self.assertIsNone(analyze(BLUEFIN, RULES).values["Term Commitment"])
        self.assertEqual(analyze(ORBIT, RULES).values["Term Commitment"], 9_000_000)

    def test_non_binding_spend_is_no_commitment(self):
        r = analyze(LUMEN, RULES)
        self.assertEqual(r.values["Commitment Category"], "No Commitment")
        self.assertEqual(r.values["Zero Commitment"], "Yes")  # termination for convenience
        self.assertIsNone(r.values["Sum of Annual Commitments"])

    def test_scanned_pages_become_flags(self):
        r = analyze(LUMEN, RULES, scanned_pages=[3])
        self.assertTrue(any("Page 3" in f for f in r.flags))
        self.assertIn("FLAG:", r.notes)

    def test_categories(self):
        base = dict(commitment_language="binding", term_commitment=None)
        self.assertEqual(commitment_category({**base, "annual_commitments": [1, 0, 1]}), "Annual - Some Years")
        self.assertEqual(commitment_category({**base, "annual_commitments": [], "term_commitment": 5}), "Term Only")
        self.assertEqual(commitment_category({**base, "annual_commitments": [1], "term_commitment": 5}), "Term + Annual")
        self.assertEqual(commitment_category({**base, "commitment_language": "none", "annual_commitments": [1]}),
                         "No Commitment")

    def test_upfront_types(self):
        x = {"annual_commitments": [100, 100], "upfront_payments": []}
        self.assertEqual(upfront_type(x, 200), "None")
        self.assertEqual(upfront_type({**x, "upfront_payments": [{"year": 1, "amount": 200}]}, 200), "Full Upfront")
        self.assertEqual(upfront_type({**x, "upfront_payments": [{"year": 1, "amount": 100},
                                                                  {"year": 2, "amount": 100}]}, 200), "Annual Prepay")
        self.assertEqual(upfront_type({**x, "upfront_payments": [{"year": 1, "amount": 50}]}, 200), "Partial Upfront")

    def test_rejects_fraction_percent_and_missing_evidence(self):
        bad = copy.deepcopy(BLUEFIN)
        bad["platform_discount_pct"] = 0.07
        bad["evidence"].pop("end_date")
        with self.assertRaises(ExtractionError) as cm:
            analyze(bad, RULES)
        self.assertIn("whole number", str(cm.exception))
        self.assertIn("end_date", str(cm.exception))


class WorkflowTests(unittest.TestCase):
    def setUp(self):
        self.tmp = Path(tempfile.mkdtemp())
        self.master = self.tmp / MASTER_NAME
        shutil.copy(SAMPLES / "workbook" / MASTER_NAME, self.master)
        self.text = self.tmp / "text"
        extract_folder(SAMPLES / "contracts", self.text, RULES.scanned_page_min_chars)

    def tearDown(self):
        shutil.rmtree(self.tmp)

    def review(self, owner, initials):
        return run_review(self.master, owner, initials, SAMPLES / "extracted", self.text, RULES)

    def test_extract_detects_scanned_page(self):
        m = json.loads((self.text / "manifest.json").read_text())
        self.assertEqual(m["CRA-2026-0103 - Lumen Public Library District.pdf"]["scanned_pages"], [3])
        txt = (self.text / "CRA-2026-0101 - Bluefin Analytics.txt").read_text()
        self.assertIn("===== Page 1 of 2 =====", txt)

    def test_master_never_modified(self):
        before = self.master.read_bytes()
        self.review("Alex Rivera", "AR")
        consolidate(self.master)
        self.assertEqual(self.master.read_bytes(), before)

    def test_wrong_document_and_missing_contract_are_not_filled(self):
        rep = self.review("Sam Patel", "SP")
        self.assertIn("document mismatch", rep.not_filled["CRA-2026-0105 - Harbor Studio.pdf"])
        self.assertIn("no extraction", rep.not_filled["CRA-2026-0106 - Pine Valley Robotics.pdf"])
        ws = load_workbook(rep.owner_file)[SHEET]
        h = header_map(ws)
        self.assertIsNone(ws.cell(6, h["Notes"]).value)

    def test_only_written_cells_highlighted_and_audit_passes(self):
        rep = self.review("Alex Rivera", "AR")
        self.assertEqual(rep.audit_problems, [])
        ws = load_workbook(rep.owner_file)[SHEET]
        h = header_map(ws)
        self.assertEqual(ws.cell(2, h["Notes"]).fill.fgColor.rgb[-6:], "FFFF00")
        self.assertNotEqual(ws.cell(2, h["Customer"]).fill.fgColor.rgb[-6:], "FFFF00")
        self.assertTrue(str(ws.cell(2, h["Compute Variance to Platform"]).value).startswith("="))

    def test_rerun_only_touches_blank_rows(self):
        self.review("Alex Rivera", "AR")
        self.assertEqual(self.review("Alex Rivera", "AR").completed, [])

    def test_audit_catches_term_commitment_on_annual_deal(self):
        rep = self.review("Alex Rivera", "AR")
        wb = load_workbook(rep.owner_file)
        ws = wb[SHEET]
        write_row(ws, 2, {"Term Commitment": 3_000_000}, "CRA-2026-0101 - Bluefin Analytics.pdf")
        self.assertTrue(any("Term Commitment must be blank" in p for p in audit_row(ws, 2, RULES)))

    def test_refuses_to_write_input_columns(self):
        ws = load_workbook(self.master)[SHEET]
        with self.assertRaises(ValueError):
            write_row(ws, 2, {"Customer": "x"}, "CRA-2026-0101 - Bluefin Analytics.pdf")
        with self.assertRaises(ValueError):
            write_row(ws, 2, {"Notes": "x"}, "the wrong file.pdf")

    def test_locked_workbook(self):
        (self.tmp / f"~${MASTER_NAME}").write_text("")
        with self.assertRaises(WorkbookLocked):
            self.review("Alex Rivera", "AR")

    def test_consolidation_conflict_first_owner_wins(self):
        self.review("Alex Rivera", "AR")
        self.review("Sam Patel", "SP")
        # A second copy of Alex's file: same owner, same rows -> conflicts, not double-writes.
        shutil.copy(self.tmp / "Contract Review - Nov 2026 - AR.xlsx",
                    self.tmp / "Contract Review - Nov 2026 - AR2.xlsx")
        plan = consolidate(self.master)
        self.assertEqual(len(plan.merged["Alex Rivera"]), 3)
        self.assertEqual(len(plan.conflicts), 3)
        self.assertEqual(len(plan.not_completed), 2)
        ws = load_workbook(plan.output)[SHEET]
        h = header_map(ws)
        self.assertTrue(ws.cell(5, h["Notes"]).value.startswith("This agreement gives Orbit Freight"))

    def test_dry_run_writes_nothing(self):
        self.review("Alex Rivera", "AR")
        plan = consolidate(self.master, dry_run=True)
        self.assertFalse(plan.output.exists())


if __name__ == "__main__":
    unittest.main()
