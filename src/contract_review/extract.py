"""PDF -> text. The only part of the system that knows what a PDF is.

Kept deliberately small and isolated: if contracts ever arrive as structured
data, this module is deleted and nothing else changes.
"""
from __future__ import annotations

import json
from pathlib import Path
from typing import Dict

from pypdf import PdfReader

MANIFEST = "manifest.json"


def extract_pdf(pdf_path: Path, min_chars: int = 40) -> Dict:
    reader = PdfReader(str(pdf_path))
    n = len(reader.pages)
    parts, scanned = [], []
    for i, page in enumerate(reader.pages, 1):
        # `or ""`: a page with no text layer yields empty text instead of raising,
        # so one bad page cannot abandon the whole batch.
        text = page.extract_text() or ""
        if len(text.strip()) < min_chars:
            scanned.append(i)
        parts.append(f"===== Page {i} of {n} =====\n{text}")
    full = "\n".join(parts)
    return {"text": full, "pages": n, "chars": len(full), "scanned_pages": scanned}


def extract_folder(pdf_dir: Path, out_dir: Path, min_chars: int = 40) -> Dict[str, Dict]:
    """Write <name>.txt for every PDF plus a manifest. Idempotent: safe to re-run."""
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest: Dict[str, Dict] = {}
    for pdf in sorted(Path(pdf_dir).glob("*.pdf")):
        result = extract_pdf(pdf, min_chars)
        (out_dir / f"{pdf.stem}.txt").write_text(result.pop("text"), encoding="utf-8")
        manifest[pdf.name] = result
    (out_dir / MANIFEST).write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    return manifest


def load_manifest(text_dir: Path) -> Dict[str, Dict]:
    p = Path(text_dir) / MANIFEST
    return json.loads(p.read_text(encoding="utf-8")) if p.exists() else {}
