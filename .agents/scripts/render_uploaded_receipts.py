import fitz
from pathlib import Path
files = [
    'attached_assets/Receipt-2305-3925_1789077815670.pdf',
    'attached_assets/Invoice-7T4YLLGB-0007_1789077815670.pdf',
    'attached_assets/Invoice-7T4YLLGB-0008_1789077815671.pdf',
    'attached_assets/Receipt-2107-8387_1789077815671.pdf',
]
out = Path('.agents/outputs/receipt-render')
out.mkdir(parents=True, exist_ok=True)
for path in files:
    doc = fitz.open(path)
    pix = doc[0].get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False)
    target = out / (Path(path).stem + '.png')
    pix.save(target)
    print(target, doc.page_count, doc.metadata.get('title'))
