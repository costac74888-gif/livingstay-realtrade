"""Render the three current MJ residence reports for visual print review."""
from pathlib import Path
import fitz

source = Path(".agents/outputs/mj-reports")
for mode in ("property", "rental", "operation"):
    pdf = source / f"mj-residence-{mode}.pdf"
    doc = fitz.open(pdf)
    if len(doc) != 1:
        raise ValueError(f"{mode}: {len(doc)} pages")
    page = doc[0]
    output = source / f"review-{mode}.png"
    page.get_pixmap(matrix=fitz.Matrix(1.6, 1.6), alpha=False).save(output)
    print(f"{mode}: {page.rect}, {output}")
    for block in page.get_text("blocks"):
        if block[1] > 700 and block[4].strip():
            print(f"  y={block[1]:.1f}..{block[3]:.1f}: {block[4][:75]!r}")