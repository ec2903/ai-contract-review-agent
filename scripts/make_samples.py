"""Generate the synthetic sample data: contract PDFs, the review workbook, and
the reference extractions used by the offline demo and the tests.

Every company, person, number and clause here is fictional.

    python scripts/make_samples.py
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

from reportlab.graphics.shapes import Drawing, Rect, Line
from reportlab.lib import colors
from reportlab.lib.pagesizes import LETTER
from reportlab.lib.styles import getSampleStyleSheet
from reportlab.platypus import PageBreak, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))
from contract_review.workbook import create_template  # noqa: E402

PROVIDER = "Tidewater Cloud Services, Inc."
SS = getSampleStyleSheet()
H, P = SS["Heading2"], SS["BodyText"]


def money(v):
    return f"${v:,.0f}"


def scanned_image():
    """A page that is only an image - no text layer, like a scanned exhibit."""
    d = Drawing(460, 600)
    d.add(Rect(0, 0, 460, 600, fillColor=colors.Color(0.93, 0.93, 0.9), strokeColor=colors.grey))
    for y in range(40, 580, 18):
        d.add(Line(30, y, 430, y, strokeColor=colors.Color(0.6, 0.6, 0.6)))
    return d


def build_pdf(path: Path, c: dict) -> None:
    s = []
    s.append(Paragraph(f"CLOUD RESOURCES AGREEMENT - {c['agreement_id']}", SS["Title"]))
    s.append(Paragraph(f"This Cloud Resources Agreement (the \"Agreement\") is entered into between "
                       f"{PROVIDER} (\"Provider\") and {c['customer_legal']} (\"Customer\").", P))
    s.append(Paragraph("1. Term", H))
    s.append(Paragraph(f"1.1 This Agreement begins on {c['start_text']} (the \"Effective Date\") and ends on "
                       f"{c['end_text']}, unless terminated earlier under Section 6.", P))
    s.append(Paragraph("2. Pricing", H))
    s.append(Paragraph(f"2.1 Provider will apply a discount of {c['platform']}% to all eligible services "
                       f"(the \"Platform Discount\") during the Term.", P))
    for clause in c.get("pricing_clauses", []):
        s.append(Paragraph(clause, P))
    s.append(Paragraph("3. Spend", H))
    for clause in c["spend_clauses"]:
        s.append(Paragraph(clause, P))
    if c.get("schedule"):
        t = Table([["Contract Year", "Committed Spend"]] +
                  [[f"Year {i}", money(v)] for i, v in enumerate(c["schedule"], 1)])
        t.setStyle(TableStyle([("GRID", (0, 0), (-1, -1), 0.5, colors.grey),
                               ("BACKGROUND", (0, 0), (-1, 0), colors.lightgrey)]))
        s += [Spacer(1, 6), t]
    s.append(Paragraph("4. Payment", H))
    s.append(Paragraph(c.get("payment_clause", "4.1 Customer will be invoiced monthly in arrears."), P))
    s.append(Paragraph("5. Credits", H))
    s.append(Paragraph(c.get("credit_clause", "5.1 No credits are granted under this Agreement."), P))
    s.append(PageBreak())
    s.append(Paragraph("6. Termination", H))
    s.append(Paragraph(c["termination_clause"], P))
    s.append(Paragraph("7. General", H))
    s.append(Paragraph("7.1 This Agreement is governed by the laws of the State of Delaware. Each party "
                       "may not assign this Agreement without the other's written consent, which will "
                       "not be unreasonably withheld.", P))
    s.append(Spacer(1, 30))
    s.append(Paragraph(f"Signed for {PROVIDER}: J. Morgan, VP Sales &nbsp;&nbsp; Signed for "
                       f"{c['customer_legal']}: {c['signer']}", P))
    if c.get("scanned_exhibit"):
        s += [PageBreak(), scanned_image()]
    SimpleDocTemplate(str(path), pagesize=LETTER, title=c["agreement_id"]).build(s)


CONTRACTS = [
    {   # Clean: everything within band.
        "row_id": "CRA-2026-0101", "agreement_id": "CRA-2026-0101", "owner": "Alex Rivera",
        "customer": "Bluefin Analytics", "customer_legal": "Bluefin Analytics LLC",
        "file": "CRA-2026-0101 - Bluefin Analytics.pdf",
        "start": "2026-10-01", "end": "2029-09-30",
        "start_text": "October 1, 2026", "end_text": "September 30, 2029", "platform": 7,
        "pricing_clauses": ["2.2 Compute instances receive a discount of 11% in place of the Platform Discount.",
                            "2.3 Object storage receives a discount of 15%, conditioned on Customer "
                            "maintaining at least 300 TB of stored data."],
        "spend_clauses": ["3.1 Customer agrees to the minimum commitment below for each Contract Year. "
                          "If spend in a Contract Year falls below its minimum commitment, Customer "
                          "shall pay any shortfall within 30 days."],
        "schedule": [800000, 1000000, 1200000],
        "credit_clause": "5.1 Provider grants Customer a one-time onboarding credit of $20,000.",
        "termination_clause": "6.1 Either party may terminate for material breach not cured within 30 "
                              "days of written notice. There is no right to terminate for convenience.",
        "signer": "R. Okafor, CFO",
        "x": {"platform_discount_pct": 7, "annual_commitments": [800000, 1000000, 1200000],
              "term_commitment": None, "commitment_language": "binding", "upfront_payments": [],
              "product_rates": [{"product": "compute", "discount_pct": 11, "committed_tb": None},
                                {"product": "storage", "discount_pct": 15, "committed_tb": 300}],
              "termination_for_convenience": False,
              "credits": [{"type": "Onboarding credit", "amount": 20000}],
              "evidence": {"start_date": "Section 1.1, p.1: \"begins on October 1, 2026\"",
                           "end_date": "Section 1.1, p.1: \"ends on September 30, 2029\"",
                           "platform_discount_pct": "Section 2.1, p.1: \"a discount of 7% to all eligible services\"",
                           "annual_commitments": "Section 3.1, p.1: \"minimum commitment ... shall pay any shortfall\" + Year 1-3 table",
                           "termination_for_convenience": "Section 6.1, p.2: \"There is no right to terminate for convenience.\""},
              "uncertain": [], "observations": ["Spend commitment steps up each year with a shortfall payment obligation."]},
    },
    {   # Outlier: compute discount far above band and platform discount.
        "row_id": "CRA-2026-0102", "agreement_id": "CRA-2026-0102", "owner": "Alex Rivera",
        "customer": "Cedar Ridge Health", "customer_legal": "Cedar Ridge Health Partners, Inc.",
        "file": "CRA-2026-0102 - Cedar Ridge Health.pdf",
        "start": "2026-11-01", "end": "2028-10-31",
        "start_text": "November 1, 2026", "end_text": "October 31, 2028", "platform": 6,
        "pricing_clauses": ["2.2 Compute instances receive a discount of 22% in place of the Platform Discount."],
        "spend_clauses": ["3.1 Customer commits to the committed spend below for each Contract Year, "
                          "subject to an annual true-up."],
        "schedule": [2500000, 2500000],
        "payment_clause": "4.1 Customer will prepay each Contract Year's committed spend in full: $2,500,000 "
                          "on the Effective Date and $2,500,000 on the first anniversary.",
        "termination_clause": "6.1 Either party may terminate for material breach. Customer may not "
                              "terminate for convenience.",
        "signer": "D. Whitfield, COO",
        "x": {"platform_discount_pct": 6, "annual_commitments": [2500000, 2500000],
              "term_commitment": None, "commitment_language": "binding",
              "upfront_payments": [{"year": 1, "amount": 2500000}, {"year": 2, "amount": 2500000}],
              "product_rates": [{"product": "compute", "discount_pct": 22, "committed_tb": None}],
              "termination_for_convenience": False, "credits": [],
              "evidence": {"start_date": "Section 1.1, p.1: \"begins on November 1, 2026\"",
                           "end_date": "Section 1.1, p.1: \"ends on October 31, 2028\"",
                           "platform_discount_pct": "Section 2.1, p.1: \"a discount of 6%\"",
                           "annual_commitments": "Section 3.1, p.1: \"commits to the committed spend ... annual true-up\"",
                           "termination_for_convenience": "Section 6.1, p.2: \"may not terminate for convenience\""},
              "uncertain": [], "observations": ["Each year's commitment is prepaid in full."]},
    },
    {   # Zero commitment: non-binding spend + termination for convenience + scanned exhibit.
        "row_id": "CRA-2026-0103", "agreement_id": "CRA-2026-0103", "owner": "Alex Rivera",
        "customer": "Lumen Public Library District", "customer_legal": "Lumen Public Library District",
        "file": "CRA-2026-0103 - Lumen Public Library District.pdf",
        "start": "2026-11-15", "end": "2027-11-14",
        "start_text": "November 15, 2026", "end_text": "November 14, 2027", "platform": 3,
        "spend_clauses": ["3.1 Customer anticipated spend of $150,000 during the Term is a good faith "
                          "estimate only and does not create any payment obligation."],
        "termination_clause": "6.1 Customer may terminate this Agreement for convenience on 60 days' "
                              "written notice, as required by public funding rules.",
        "signer": "P. Alvarez, Director", "scanned_exhibit": True,
        "x": {"platform_discount_pct": 3, "annual_commitments": [], "term_commitment": None,
              "commitment_language": "non_binding", "upfront_payments": [], "product_rates": [],
              "termination_for_convenience": True, "credits": [],
              "evidence": {"start_date": "Section 1.1, p.1: \"begins on November 15, 2026\"",
                           "end_date": "Section 1.1, p.1: \"ends on November 14, 2027\"",
                           "platform_discount_pct": "Section 2.1, p.1: \"a discount of 3%\"",
                           "commitment_language": "Section 3.1, p.1: \"anticipated spend ... good faith estimate only\"",
                           "termination_for_convenience": "Section 6.1, p.2: \"may terminate this Agreement for convenience on 60 days' written notice\""},
              "uncertain": [], "observations": ["Public-sector customer; spend figure is a non-binding estimate."]},
    },
    {   # Term + annual, partial upfront, compute above band but NOT material.
        "row_id": "CRA-2026-0104", "agreement_id": "CRA-2026-0104", "owner": "Sam Patel",
        "customer": "Orbit Freight", "customer_legal": "Orbit Freight Co.",
        "file": "CRA-2026-0104 - Orbit Freight.pdf",
        "start": "2027-01-01", "end": "2029-12-31",
        "start_text": "January 1, 2027", "end_text": "December 31, 2029", "platform": 12,
        "pricing_clauses": ["2.2 Compute instances receive a discount of 17%.",
                            "2.3 Object storage receives a discount of 19%, conditioned on at least "
                            "600 TB of committed storage."],
        "spend_clauses": ["3.1 Customer commits to a minimum commitment of $2,000,000 in each Contract Year.",
                          "3.2 In addition, Customer commits to total committed spend of $9,000,000 over "
                          "the Term. Any shortfall at the end of the Term is payable within 30 days."],
        "schedule": [2000000, 2000000, 2000000],
        "payment_clause": "4.1 Customer will pay $1,000,000 in advance on the Effective Date, applied "
                          "against Year 1 usage. All other usage is invoiced monthly in arrears.",
        "termination_clause": "6.1 Either party may terminate for material breach only.",
        "signer": "L. Chen, VP Finance",
        "x": {"platform_discount_pct": 12, "annual_commitments": [2000000, 2000000, 2000000],
              "term_commitment": 9000000, "commitment_language": "binding",
              "upfront_payments": [{"year": 1, "amount": 1000000}],
              "product_rates": [{"product": "compute", "discount_pct": 17, "committed_tb": None},
                                {"product": "storage", "discount_pct": 19, "committed_tb": 600}],
              "termination_for_convenience": False, "credits": [],
              "evidence": {"start_date": "Section 1.1, p.1: \"begins on January 1, 2027\"",
                           "end_date": "Section 1.1, p.1: \"ends on December 31, 2029\"",
                           "platform_discount_pct": "Section 2.1, p.1: \"a discount of 12%\"",
                           "annual_commitments": "Section 3.1, p.1: \"minimum commitment of $2,000,000 in each Contract Year\"",
                           "term_commitment": "Section 3.2, p.1: \"total committed spend of $9,000,000 over the Term\"",
                           "termination_for_convenience": "Section 6.1, p.2: \"terminate for material breach only\""},
              "uncertain": [], "observations": ["Term commitment exceeds the sum of the annual minimums."]},
    },
    {   # Wrong document filed under this row: agreement ID in the PDF does not match.
        "row_id": "CRA-2026-0105", "agreement_id": "CRA-2026-0117", "owner": "Sam Patel",
        "customer": "Harbor Studio", "customer_legal": "Harbor Studio Group Ltd.",
        "file": "CRA-2026-0105 - Harbor Studio.pdf",
        "start": "2026-12-01", "end": "2027-11-30",
        "start_text": "December 1, 2026", "end_text": "November 30, 2027", "platform": 4,
        "spend_clauses": ["3.1 Customer commits to a minimum commitment of $300,000 for the Term."],
        "termination_clause": "6.1 Either party may terminate for material breach only.",
        "signer": "M. Ito, Managing Director",
        "x": {"platform_discount_pct": 4, "annual_commitments": [], "term_commitment": 300000,
              "commitment_language": "binding", "upfront_payments": [], "product_rates": [],
              "termination_for_convenience": False, "credits": [],
              "evidence": {"start_date": "Section 1.1, p.1", "end_date": "Section 1.1, p.1",
                           "platform_discount_pct": "Section 2.1, p.1",
                           "termination_for_convenience": "Section 6.1, p.2"},
              "uncertain": ["Document title shows agreement CRA-2026-0117, not the row's agreement."],
              "observations": []},
    },
]
# Assigned in the workbook, but no contract was ever filed.
MISSING = {"row_id": "CRA-2026-0106", "owner": "Sam Patel", "customer": "Pine Valley Robotics",
           "file": "CRA-2026-0106 - Pine Valley Robotics.pdf"}


def main() -> None:
    cdir, xdir, wdir = (ROOT / "samples" / d for d in ("contracts", "extracted", "workbook"))
    for d in (cdir, xdir, wdir):
        d.mkdir(parents=True, exist_ok=True)
    for c in CONTRACTS:
        build_pdf(cdir / c["file"], c)
        x = {"file_name": c["file"], "agreement_id": c["agreement_id"],
             "customer_name": c["customer_legal"], "start_date": c["start"], "end_date": c["end"], **c["x"]}
        (xdir / f"{Path(c['file']).stem}.json").write_text(json.dumps(x, indent=2) + "\n", encoding="utf-8")
    rows = [{"Owner": c["owner"], "File Name": c["file"], "Agreement ID": c["row_id"],
             "Customer": c["customer"]} for c in CONTRACTS + [MISSING]]
    create_template(wdir / "Contract Review - Nov 2026.xlsx", rows)
    print(f"wrote {len(CONTRACTS)} PDFs, {len(CONTRACTS)} extractions, 1 workbook ({len(rows)} rows)")


if __name__ == "__main__":
    main()
