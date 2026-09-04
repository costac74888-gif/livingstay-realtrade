#!/usr/bin/env python3
"""Render the generated policy PDF for visual verification."""

from pathlib import Path

import pymupdf


root = Path(__file__).resolve().parents[2]
source = root / "exports/HOME_AND_STAY_PUBLIC_DATA_PRIVACY_POLICY_V01_0_2026-09-04.pdf"
output = root / ".agents/outputs/privacy-policy-pdf"
output.mkdir(parents=True, exist_ok=True)

document = pymupdf.open(source)
for index, page in enumerate(document):
    pixmap = page.get_pixmap(matrix=pymupdf.Matrix(1.5, 1.5), alpha=False)
    pixmap.save(output / f"page-{index + 1:02d}.png")
print(f"rendered_pages={document.page_count}")