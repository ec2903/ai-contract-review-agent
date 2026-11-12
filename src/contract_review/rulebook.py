"""Load the rulebook and answer lookups against it.

The rulebook (rules/rulebook.yaml) is the policy; this module only reads it.
No range, threshold or definition is hard-coded here.
"""
from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple

import yaml

DEFAULT_RULEBOOK = Path(__file__).resolve().parents[2] / "rules" / "rulebook.yaml"

Band = Tuple[float, float]


def _pick_tier(value: float, tiers: List[Dict[str, Any]]) -> str:
    for t in tiers:
        if value >= t["min"] and (t["max"] is None or value <= t["max"]):
            return t["name"]
    raise ValueError(f"value {value} does not fall in any tier")


@dataclass
class Rulebook:
    data: Dict[str, Any]

    @classmethod
    def load(cls, path: Optional[Path] = None) -> "Rulebook":
        with open(path or DEFAULT_RULEBOOK, encoding="utf-8") as f:
            return cls(yaml.safe_load(f))

    @property
    def version(self) -> str:
        return str(self.data["version"])

    # --- lookups -----------------------------------------------------------
    @staticmethod
    def term_years(term_months: int) -> int:
        """Band key for a term: 1-12 months -> 1, 13-24 -> 2, 25+ -> 3."""
        if term_months <= 0:
            raise ValueError("term must be positive")
        return min(3, (term_months + 11) // 12)

    def commitment_tier(self, avg_annual_commitment: float) -> str:
        return _pick_tier(avg_annual_commitment, self.data["commitment_tiers"])

    def platform_band(self, term_months: int, tier: str) -> Band:
        lo, hi = self.data["platform_discount_bands"][self.term_years(term_months)][tier]
        return (lo, hi)

    def product_band(self, product: str, term_months: int, tier: str,
                     committed_tb: Optional[float] = None) -> Tuple[Band, str]:
        """Return (band, basis) where basis explains which cell of the table was used."""
        spec = self.data["product_bands"][product]
        if spec["by"] == "tier":
            lo, hi = spec["bands"][tier]
            return (lo, hi), f"tier {tier}"
        if spec["by"] == "term_and_volume":
            if committed_tb is None:
                raise ValueError(f"{product} band needs a committed volume")
            v = _pick_tier(committed_tb, spec["volume_tiers_tb"])
            years = self.term_years(term_months)
            lo, hi = spec["bands"][years][v]
            return (lo, hi), f"{years}-year term, {v} ({committed_tb:g} TB)"
        raise ValueError(f"unknown band basis {spec['by']!r}")

    @property
    def materiality_points(self) -> float:
        return self.data["outlier"]["materiality_points"]

    @property
    def commitment_categories(self) -> List[str]:
        return list(self.data["commitment_categories"])

    @property
    def upfront_types(self) -> List[str]:
        return list(self.data["upfront_types"])

    @property
    def scanned_page_min_chars(self) -> int:
        return int(self.data["scanned_page_min_chars"])
