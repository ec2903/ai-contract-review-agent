"""Turn one contract extraction into review determinations and Notes.

Division of labour:
  * The LLM agent READS the contract and fills a ContractExtraction (with
    quoted evidence). It never decides a tier, band or outlier.
  * This module DECIDES, deterministically, from the rulebook. Same input,
    same output, every run, for every reviewer.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any, Dict, List, Optional

from .rulebook import Rulebook

REQUIRED_KEYS = [
    "file_name", "agreement_id", "customer_name", "start_date", "end_date",
    "platform_discount_pct", "annual_commitments", "term_commitment",
    "commitment_language", "upfront_payments", "product_rates",
    "termination_for_convenience", "credits", "evidence", "uncertain", "observations",
]
# Key values that must carry a quoted clause when present.
EVIDENCE_REQUIRED = ["platform_discount_pct", "start_date", "end_date",
                     "annual_commitments", "termination_for_convenience"]


class ExtractionError(ValueError):
    pass


def validate_extraction(x: Dict[str, Any]) -> List[str]:
    """Return a list of problems; empty means the extraction is usable."""
    problems = [f"missing key: {k}" for k in REQUIRED_KEYS if k not in x]
    if problems:
        return problems
    if x["commitment_language"] not in ("binding", "non_binding", "none"):
        problems.append("commitment_language must be binding / non_binding / none")
    pct = x["platform_discount_pct"]
    if pct is not None and 0 < pct < 1:
        problems.append("platform_discount_pct must be a whole number (8, not 0.08)")
    for k in EVIDENCE_REQUIRED:
        v = x.get(k)
        if v not in (None, [], "") and not x["evidence"].get(k):
            problems.append(f"no evidence quoted for {k}")
    for r in x["product_rates"]:
        if r.get("product") not in ("compute", "storage"):
            problems.append(f"unknown product {r.get('product')!r}")
    return problems


def _months_between(start: date, end: date) -> int:
    """Whole months in an inclusive term: 2026-10-01..2029-09-30 -> 36."""
    stop = end + timedelta(days=1)
    months = (stop.year - start.year) * 12 + (stop.month - start.month)
    return months - (1 if stop.day < start.day else 0)


def _money(v: float) -> str:
    return f"${v:,.0f}"


def _band(b) -> str:
    return f"{b[0]:g}%-{b[1]:g}%"


@dataclass
class Review:
    """Everything the workbook needs for one row, plus the report items."""
    values: Dict[str, Any]
    notes: str
    outliers: List[str] = field(default_factory=list)
    flags: List[str] = field(default_factory=list)


def commitment_category(x: Dict[str, Any]) -> str:
    if x["commitment_language"] != "binding":
        return "No Commitment"
    annual = [a for a in x["annual_commitments"] if a]
    term = x["term_commitment"]
    if term and annual:
        return "Term + Annual"
    if term:
        return "Term Only"
    if not annual:
        return "No Commitment"
    if len(annual) == len(x["annual_commitments"]) and all(x["annual_commitments"]):
        return "Annual - All Years"
    return "Annual - Some Years"


def upfront_type(x: Dict[str, Any], total_committed: float) -> str:
    pays = [p for p in x["upfront_payments"] if p.get("amount")]
    if not pays:
        return "None"
    if len(pays) == 1 and pays[0]["year"] == 1 and total_committed and pays[0]["amount"] >= total_committed:
        return "Full Upfront"
    annual = x["annual_commitments"]
    if annual and len(pays) == len(annual) and all(
            p["amount"] >= annual[p["year"] - 1] for p in pays if p["year"] - 1 < len(annual)):
        return "Annual Prepay"
    return "Partial Upfront"


def analyze(x: Dict[str, Any], rules: Rulebook, scanned_pages: Optional[List[int]] = None) -> Review:
    problems = validate_extraction(x)
    if problems:
        raise ExtractionError("; ".join(problems))

    flags = list(x["uncertain"])
    if scanned_pages:
        flags.append(f"Page{'s' if len(scanned_pages) > 1 else ''} {', '.join(map(str, scanned_pages))} "
                     f"{'have' if len(scanned_pages) > 1 else 'has'} no text layer (scanned); "
                     "terms on those pages were not read - check them in the PDF.")

    start = date.fromisoformat(x["start_date"]) if x["start_date"] else None
    end = date.fromisoformat(x["end_date"]) if x["end_date"] else None
    term_months = _months_between(start, end) if start and end else None
    if term_months is None:
        flags.append("Term dates not found - band checks skipped.")

    annual = list(x["annual_commitments"])
    category = commitment_category(x)
    binding = x["commitment_language"] == "binding"
    sum_annual = sum(annual) if binding else 0
    term_commit = x["term_commitment"] if binding else None
    total_committed = max(sum_annual, term_commit or 0)
    years = max(1, round(term_months / 12)) if term_months else max(1, len(annual))
    avg_annual = total_committed / years if total_committed else 0
    tier = rules.commitment_tier(avg_annual)
    upfront = upfront_type(x, total_committed)
    pdisc = x["platform_discount_pct"] or 0
    tfc = bool(x["termination_for_convenience"])
    zero = tfc or (category == "No Commitment" and pdisc == 0)
    credits_total = sum(c["amount"] for c in x["credits"])

    notes: List[str] = []
    outliers: List[str] = []
    immaterial: List[str] = []

    # Platform discount vs band
    if term_months:
        pband = rules.platform_band(term_months, tier)
        within = pband[0] <= pdisc <= pband[1]
        notes.append(f"Platform-wide discount: {pdisc:g}% ({'within' if within else 'OUTSIDE'} the "
                     f"{_band(pband)} band for a {rules.term_years(term_months)}-year term, tier {tier}).")
        if pdisc > pband[1]:
            outliers.append(f"Platform-wide discount {pdisc:g}% exceeds the {_band(pband)} band.")

    # Commitments
    if category == "No Commitment":
        why = {"non_binding": " (spend language is non-binding)", "none": ""}.get(x["commitment_language"], "")
        notes.append(f"Commitment: No Commitment{why}.")
    else:
        yrs = "; ".join(f"Year {i + 1} {_money(a)}" for i, a in enumerate(annual)) or "none"
        line = f"Commitment: {category}. Annual: {yrs}."
        if term_commit:
            line += f" Separate term commitment: {_money(term_commit)}."
        notes.append(line + f" Average annual commitment {_money(avg_annual)} (tier {tier}).")

    notes.append("Upfront payments: " + (upfront if upfront == "None" else
                 f"{upfront} - " + "; ".join(f"Year {p['year']} {_money(p['amount'])}"
                                             for p in x["upfront_payments"])) + ".")
    if term_months:
        notes.append(f"Term: {x['start_date']} to {x['end_date']} ({term_months} months).")

    # Product-specific rates
    rate_cols: Dict[str, Optional[float]] = {"compute": None, "storage": None}
    for r in x["product_rates"]:
        prod, pct = r["product"], r["discount_pct"]
        rate_cols[prod] = pct
        if not term_months:
            notes.append(f"{prod.title()} discount: {pct:g}% (band not checked - no term).")
            continue
        try:
            band, basis = rules.product_band(prod, term_months, tier, r.get("committed_tb"))
        except ValueError as e:
            flags.append(f"{prod.title()} band not checked: {e}.")
            notes.append(f"{prod.title()} discount: {pct:g}%.")
            continue
        above = pct > band[1]
        gap = pct - pdisc
        material = gap > rules.materiality_points
        if not above:
            notes.append(f"{prod.title()} discount: {pct:g}% - within the {_band(band)} band ({basis}).")
        else:
            notes.append(f"{prod.title()} discount: {pct:g}% - ABOVE the {_band(band)} band ({basis}); "
                         f"{gap:g} points above the platform-wide discount"
                         f"{'' if material else ', not material'}.")
        if above and not material:
            immaterial.append(f"{prod.title()} discount {pct:g}% is above its {_band(band)} band but only "
                              f"{gap:g} points above the platform-wide discount, so it is not an outlier.")
        if above and material:
            outliers.append(f"{prod.title()} discount {pct:g}% exceeds the {_band(band)} band ({basis}) "
                            f"and is {gap:g} points above the platform-wide discount.")

    notes.append(f"Termination for convenience: {'Yes - zero-commitment agreement' if tfc else 'No'}.")
    notes.append("Credits: " + ("none" if not x["credits"] else
                 "; ".join(f"{c['type']} {_money(c['amount'])}" for c in x["credits"])) + ".")
    for f_ in flags:
        notes.append(f"FLAG: {f_}")

    summary = (f"This agreement gives {x['customer_name']} a platform-wide discount of {pdisc:g}%"
               + (f" from {x['start_date']} to {x['end_date']}." if term_months else "."))
    if x["observations"]:
        summary += " " + " ".join(x["observations"])
    if outliers:
        conclusion = "Outlier review: OUTLIER - " + " ".join(outliers)
    elif immaterial:
        conclusion = "Outlier review: no outliers. " + " ".join(immaterial)
    else:
        conclusion = "Outlier review: no outliers - all rates are within approved bands."
    notes_text = (summary + "\n\nNotes:\n" + "\n".join(f"{i}. {n}" for i, n in enumerate(notes, 1))
                  + "\n\n" + conclusion)

    padded = (annual + [None] * 5)[:5] if binding else [None] * 5
    values = {
        "Start Date": start, "End Date": end, "Term (Months)": term_months,
        "Platform Discount %": pdisc,
        **{f"Year {i + 1} Commitment": padded[i] for i in range(5)},
        "Sum of Annual Commitments": sum_annual or None,
        # Total Commitment is ONLY a separately negotiated term amount. When the
        # deal is annual-only it stays blank - repeating the sum would falsely
        # signal a term-level commitment that was never negotiated.
        "Term Commitment": term_commit or None,
        "Avg Annual Commitment": round(avg_annual) if avg_annual else None,
        "Commitment Tier": tier,
        "Commitment Category": category,
        "Upfront Type": upfront,
        "Compute Discount %": rate_cols["compute"],
        "Storage Discount %": rate_cols["storage"],
        "Credits Total": credits_total or None,
        "Termination for Convenience": "Yes" if tfc else "No",
        "Zero Commitment": "Yes" if zero else "No",
        "Outlier": "Yes" if outliers else "No",
        "Notes": notes_text,
    }
    return Review(values=values, notes=notes_text, outliers=outliers, flags=flags)
