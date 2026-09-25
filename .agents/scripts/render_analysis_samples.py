from pathlib import Path
import fitz


def main():
    output = Path(".agents/outputs/analysis-samples")
    output.mkdir(parents=True, exist_ok=True)
    for kind in ("임대수익", "부동산투자", "숙박운영"):
        candidates = list(Path("attached_assets").glob(f"*2026-09-25*{kind}보고서_179029386*.pdf"))
        if len(candidates) != 1:
            raise RuntimeError(f"{kind}: expected 1 PDF, found {len(candidates)}")
        with fitz.open(candidates[0]) as pdf:
            print(kind, len(pdf), pdf[0].rect)
            for i, page in enumerate(pdf):
                target = output / f"{kind}-{i + 1}.png"
                page.get_pixmap(matrix=fitz.Matrix(1.5, 1.5), alpha=False).save(target)
                print(target)


if __name__ == "__main__":
    main()