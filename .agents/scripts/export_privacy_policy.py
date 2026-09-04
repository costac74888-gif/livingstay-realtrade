#!/usr/bin/env python3
"""Create self-contained HTML and a portable DOCX from the privacy policy Markdown."""

from __future__ import annotations

import html
import re
import zipfile
from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]
SOURCE = ROOT / "docs/PUBLIC_DATA_PRIVACY_PROTECTION_POLICY_V01_0_2026-09-04.md"
OUT_DIR = ROOT / "exports"
STEM = "HOME_AND_STAY_PUBLIC_DATA_PRIVACY_POLICY_V01_0_2026-09-04"


def inline(text: str) -> str:
    value = html.escape(text.strip())
    value = re.sub(r"`([^`]+)`", r"<code>\1</code>", value)
    value = re.sub(r"\*\*([^*]+)\*\*", r"<strong>\1</strong>", value)
    return value


def markdown_to_html(markdown: str) -> str:
    lines = markdown.splitlines()
    body: list[str] = []
    i = 0
    list_tag: str | None = None

    def close_list() -> None:
        nonlocal list_tag
        if list_tag:
            body.append(f"</{list_tag}>")
            list_tag = None

    while i < len(lines):
        line = lines[i].rstrip()
        if not line:
            close_list()
            i += 1
            continue
        if line == "---":
            close_list()
            body.append("<hr>")
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", lines[i + 1]):
            close_list()
            headers = [inline(x) for x in line.strip("|").split("|")]
            body.append("<table><thead><tr>" + "".join(f"<th>{x}</th>" for x in headers) + "</tr></thead><tbody>")
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                cells = [inline(x) for x in lines[i].strip("|").split("|")]
                body.append("<tr>" + "".join(f"<td>{x}</td>" for x in cells) + "</tr>")
                i += 1
            body.append("</tbody></table>")
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            close_list()
            level = len(heading.group(1))
            body.append(f"<h{level}>{inline(heading.group(2))}</h{level}>")
            i += 1
            continue
        bullet = re.match(r"^-\s+(.+)$", line)
        numbered = re.match(r"^\d+\.\s+(.+)$", line)
        if bullet or numbered:
            wanted = "ul" if bullet else "ol"
            if list_tag != wanted:
                close_list()
                list_tag = wanted
                body.append(f"<{wanted}>")
            body.append(f"<li>{inline((bullet or numbered).group(1))}</li>")
            i += 1
            continue
        close_list()
        body.append(f"<p>{inline(line)}</p>")
        i += 1
    close_list()

    content = "\n".join(body)
    first_h1 = re.search(r"<h1>(.*?)</h1>", content)
    title = first_h1.group(1) if first_h1 else "공개 데이터·개인정보 보호 정책"
    content = re.sub(r"<h1>.*?</h1>", "", content, count=1)
    cover = f"""<section class="cover">
      <div class="kicker">HOME &amp; STAY · PRIVACY GOVERNANCE</div>
      <h1>{title}</h1>
      <div class="meta"><b>문서 ID</b> POL-EXPOSURE-001<br><b>버전</b> V.01.0<br>
      <b>기준일·시행일</b> 2026-09-04<br><b>상태</b> 현행<br>
      <b>적용</b> API · HTML · 다운로드 · 사진 · 로그 · 통계</div>
      <p class="footer-note">공개 여부가 불명확하면 공개하지 않습니다.</p>
    </section>"""
    css = """
    @font-face{font-family:PolicyKR;src:url("file:///nix/store/1wd0fbh9pwn9cna5vkj762b72yw974qp-nanum-20200506/share/fonts/NanumBarunGothic.ttf") format("truetype");font-weight:400}
    @font-face{font-family:PolicyKR;src:url("file:///nix/store/1wd0fbh9pwn9cna5vkj762b72yw974qp-nanum-20200506/share/fonts/NanumBarunGothicBold.ttf") format("truetype");font-weight:700}
    @page{size:A4;margin:15mm 14mm 16mm}
    *{box-sizing:border-box}
    body{font-family:PolicyKR,"Malgun Gothic",sans-serif;
      color:#18212f;font-size:9.3pt;line-height:1.55;word-break:keep-all}
    h1{font-size:27pt;color:#17324d;border-bottom:3px solid #c49745;padding-bottom:10px}
    h2{font-size:16pt;color:#17324d;border-bottom:1px solid #ccd5df;padding-bottom:5px;
      margin-top:25px;break-after:avoid}
    h3{font-size:12.5pt;color:#8a5b16;margin-top:18px;break-after:avoid}
    p{margin:5px 0 8px} ul,ol{margin:5px 0 11px;padding-left:21px} li{margin:2px 0}
    table{width:100%;border-collapse:collapse;margin:9px 0 16px;font-size:8.1pt}
    tr{break-inside:avoid} th{background:#17324d;color:white;font-weight:700}
    th,td{border:1px solid #b9c4cf;padding:4px 5px;vertical-align:top}
    tr:nth-child(even) td{background:#f5f7f9}
    code{font-family:monospace;background:#eef1f4;padding:1px 3px;border-radius:3px}
    hr{border:0;border-top:1px solid #ccd5df;margin:18px 0}
    strong{color:#102b46}
    .cover{height:250mm;display:flex;flex-direction:column;justify-content:center;break-after:page}
    .cover .kicker{color:#a57426;font-size:11pt;letter-spacing:2px}
    .cover h1{font-size:28pt}.cover .meta{margin-top:25px;padding:15px;border-left:5px solid #c49745;background:#f5f7f9}
    .footer-note{font-size:8.5pt;color:#687587;margin-top:18px}
    """
    return (
        '<!doctype html><html lang="ko"><head><meta charset="utf-8">'
        f"<title>{title}</title><style>{css}</style></head><body>{cover}{content}</body></html>"
    )


def xml_text(text: str) -> str:
    return html.escape(text, quote=False)


def paragraph(text: str, style: str | None = None) -> str:
    style_xml = f'<w:pStyle w:val="{style}"/>' if style else ""
    return (
        f"<w:p><w:pPr>{style_xml}</w:pPr><w:r><w:t xml:space=\"preserve\">"
        f"{xml_text(text)}</w:t></w:r></w:p>"
    )


def table_xml(rows: list[list[str]]) -> str:
    parts = ['<w:tbl><w:tblPr><w:tblStyle w:val="TableGrid"/><w:tblW w:w="0" w:type="auto"/></w:tblPr>']
    for row_index, row in enumerate(rows):
        parts.append("<w:tr>")
        for cell in row:
            shade = '<w:shd w:fill="17324D"/>' if row_index == 0 else ""
            color = '<w:color w:val="FFFFFF"/><w:b/>' if row_index == 0 else ""
            parts.append(
                f"<w:tc><w:tcPr>{shade}</w:tcPr><w:p><w:r><w:rPr>{color}</w:rPr>"
                f"<w:t>{xml_text(cell.strip())}</w:t></w:r></w:p></w:tc>"
            )
        parts.append("</w:tr>")
    parts.append("</w:tbl>")
    return "".join(parts)


def markdown_to_docx(markdown: str, output: Path) -> None:
    lines = markdown.splitlines()
    body: list[str] = []
    i = 0
    while i < len(lines):
        line = lines[i].strip()
        if not line or line == "---":
            i += 1
            continue
        if line.startswith("|") and i + 1 < len(lines) and re.match(r"^\|(?:\s*:?-+:?\s*\|)+$", lines[i + 1]):
            rows = [[re.sub(r"\*\*|`", "", x) for x in line.strip("|").split("|")]]
            i += 2
            while i < len(lines) and lines[i].startswith("|"):
                rows.append([re.sub(r"\*\*|`", "", x) for x in lines[i].strip("|").split("|")])
                i += 1
            body.append(table_xml(rows))
            continue
        heading = re.match(r"^(#{1,4})\s+(.+)$", line)
        if heading:
            body.append(paragraph(heading.group(2), f"Heading{len(heading.group(1))}"))
        elif re.match(r"^-\s+", line):
            body.append(paragraph("• " + re.sub(r"^-\s+", "", line), "ListParagraph"))
        elif re.match(r"^\d+\.\s+", line):
            body.append(paragraph(line, "ListParagraph"))
        else:
            body.append(paragraph(re.sub(r"\*\*|`", "", line)))
        i += 1

    document = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        "<w:body>" + "".join(body) +
        '<w:sectPr><w:pgSz w:w="11906" w:h="16838"/><w:pgMar w:top="850" w:right="850" '
        'w:bottom="850" w:left="850"/></w:sectPr></w:body></w:document>'
    )
    styles = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<w:styles xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">
<w:docDefaults><w:rPrDefault><w:rPr><w:rFonts w:ascii="Malgun Gothic" w:eastAsia="Malgun Gothic"/>
<w:sz w:val="19"/></w:rPr></w:rPrDefault></w:docDefaults>
<w:style w:type="paragraph" w:default="1" w:styleId="Normal"><w:name w:val="Normal"/></w:style>
<w:style w:type="paragraph" w:styleId="Heading1"><w:name w:val="heading 1"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="320" w:after="160"/></w:pPr><w:rPr><w:b/><w:color w:val="17324D"/><w:sz w:val="34"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading2"><w:name w:val="heading 2"/><w:basedOn w:val="Normal"/>
<w:pPr><w:spacing w:before="260" w:after="120"/></w:pPr><w:rPr><w:b/><w:color w:val="17324D"/><w:sz w:val="28"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading3"><w:name w:val="heading 3"/><w:basedOn w:val="Normal"/>
<w:rPr><w:b/><w:color w:val="8A5B16"/><w:sz w:val="24"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="Heading4"><w:name w:val="heading 4"/><w:basedOn w:val="Normal"/>
<w:rPr><w:b/><w:sz w:val="21"/></w:rPr></w:style>
<w:style w:type="paragraph" w:styleId="ListParagraph"><w:name w:val="List Paragraph"/><w:basedOn w:val="Normal"/>
<w:pPr><w:ind w:left="360"/></w:pPr></w:style>
<w:style w:type="table" w:styleId="TableGrid"><w:name w:val="Table Grid"/>
<w:tblPr><w:tblBorders><w:top w:val="single" w:sz="4" w:color="B9C4CF"/>
<w:left w:val="single" w:sz="4" w:color="B9C4CF"/><w:bottom w:val="single" w:sz="4" w:color="B9C4CF"/>
<w:right w:val="single" w:sz="4" w:color="B9C4CF"/><w:insideH w:val="single" w:sz="4" w:color="B9C4CF"/>
<w:insideV w:val="single" w:sz="4" w:color="B9C4CF"/></w:tblBorders></w:tblPr></w:style></w:styles>"""
    content_types = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Types xmlns="http://schemas.openxmlformats.org/package/2006/content-types">
<Default Extension="rels" ContentType="application/vnd.openxmlformats-package.relationships+xml"/>
<Default Extension="xml" ContentType="application/xml"/>
<Override PartName="/word/document.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.document.main+xml"/>
<Override PartName="/word/styles.xml" ContentType="application/vnd.openxmlformats-officedocument.wordprocessingml.styles+xml"/>
</Types>"""
    rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/officeDocument" Target="word/document.xml"/>
</Relationships>"""
    doc_rels = """<?xml version="1.0" encoding="UTF-8" standalone="yes"?>
<Relationships xmlns="http://schemas.openxmlformats.org/package/2006/relationships">
<Relationship Id="rId1" Type="http://schemas.openxmlformats.org/officeDocument/2006/relationships/styles" Target="styles.xml"/>
</Relationships>"""
    with zipfile.ZipFile(output, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr("[Content_Types].xml", content_types)
        archive.writestr("_rels/.rels", rels)
        archive.writestr("word/document.xml", document)
        archive.writestr("word/styles.xml", styles)
        archive.writestr("word/_rels/document.xml.rels", doc_rels)


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    markdown = SOURCE.read_text(encoding="utf-8")
    (OUT_DIR / f"{STEM}.html").write_text(markdown_to_html(markdown), encoding="utf-8")
    markdown_to_docx(markdown, OUT_DIR / f"{STEM}.docx")


if __name__ == "__main__":
    main()