"""Convert a Markdown manuscript to a .docx Word document using pypandoc."""

from __future__ import annotations

from pathlib import Path

import pypandoc
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _fix_table_layout(docx_path: Path) -> None:
    """Post-process all tables in *docx_path* for correct rendering in Word and Google Docs.

    Steps applied to every table:
    1. Apply the built-in 'Table Grid' style for visible borders (ECMA-376 compliant,
       survives DOCX->Google Docs conversion without extra XML border manipulation).
    2. Force 100% page width via w:tblW type="pct" w="5000".
    3. Force fixed layout via w:tblLayout type="fixed" so Word respects explicit widths.
    4. Rescale w:gridCol widths so they sum to TEXT_WIDTH_TWIPS (6.5" text area),
       preserving the proportions pandoc derived from the markdown separator dashes.
    5. Sync each cell's w:tcW to its column's scaled width (cells override gridCol
       when tcW is present, so both must match).
    """
    TEXT_WIDTH_TWIPS = 9360  # 6.5" * 1440 twips/inch (Letter page, 1" margins)

    _BORDER_SIDES = ("top", "bottom", "start", "end", "insideH", "insideV")

    doc = Document(str(docx_path))
    for table in doc.tables:
        tbl = table._tbl
        tblPr = tbl.find(qn("w:tblPr"))
        if tblPr is None:
            tblPr = OxmlElement("w:tblPr")
            tbl.insert(0, tblPr)

        # Step 1: add visible borders via w:tblBorders (ECMA-376 OOXML, survives Google Docs)
        tblBorders = tblPr.find(qn("w:tblBorders"))
        if tblBorders is None:
            tblBorders = OxmlElement("w:tblBorders")
            tblPr.append(tblBorders)
        for side in _BORDER_SIDES:
            el = tblBorders.find(qn(f"w:{side}"))
            if el is None:
                el = OxmlElement(f"w:{side}")
                tblBorders.append(el)
            el.set(qn("w:val"), "single")
            el.set(qn("w:sz"), "6")       # 6/8 = 0.75 pt
            el.set(qn("w:space"), "0")
            el.set(qn("w:color"), "000000")

        # Step 2: 100% page width
        tblW = tblPr.find(qn("w:tblW"))
        if tblW is None:
            tblW = OxmlElement("w:tblW")
            tblPr.append(tblW)
        tblW.set(qn("w:w"), "5000")
        tblW.set(qn("w:type"), "pct")

        # Step 3: fixed layout
        tblLayout = tblPr.find(qn("w:tblLayout"))
        if tblLayout is None:
            tblLayout = OxmlElement("w:tblLayout")
            tblPr.append(tblLayout)
        tblLayout.set(qn("w:type"), "fixed")

        # Step 4: rescale gridCol widths proportionally to fill text area
        grid_cols = tbl.tblGrid.findall(qn("w:gridCol"))
        scaled: list[int] = []
        if grid_cols:
            total = sum(int(g.get(qn("w:w"), "0") or "0") for g in grid_cols)
            if total > 0:
                for col in grid_cols:
                    raw = int(col.get(qn("w:w"), "0") or "0")
                    new_w = int(round(raw / total * TEXT_WIDTH_TWIPS))
                    col.set(qn("w:w"), str(new_w))
                    scaled.append(new_w)

        # Step 5: sync each cell's tcW to its column's scaled width
        if scaled:
            for row in table.rows:
                for idx, cell in enumerate(row.cells):
                    if idx >= len(scaled):
                        break
                    tc = cell._tc
                    tcPr = tc.find(qn("w:tcPr"))
                    if tcPr is None:
                        tcPr = OxmlElement("w:tcPr")
                        tc.insert(0, tcPr)
                    tcW = tcPr.find(qn("w:tcW"))
                    if tcW is None:
                        tcW = OxmlElement("w:tcW")
                        tcPr.append(tcW)
                    tcW.set(qn("w:w"), str(scaled[idx]))
                    tcW.set(qn("w:type"), "dxa")

        # Step 6: explicitly bold the header row so it is visually distinct in all
        # renderers (Word, Google Docs, Cursor). Pandoc's embedded "Table" style
        # only adds a bottom border to the first row -- no bold, no background --
        # making the header visually identical to data rows without this step.
        if table.rows:
            for cell in table.rows[0].cells:
                for para in cell.paragraphs:
                    for run in para.runs:
                        rPr = run._r.find(qn("w:rPr"))
                        if rPr is None:
                            rPr = OxmlElement("w:rPr")
                            run._r.insert(0, rPr)
                        for tag in ("w:b", "w:bCs"):
                            if rPr.find(qn(tag)) is None:
                                el = OxmlElement(tag)
                                rPr.append(el)

    doc.save(str(docx_path))


def generate_docx(source_path: Path, output_path: Path) -> Path:
    """Convert the Markdown file at *source_path* to a Word .docx at *output_path*.

    Uses pypandoc.convert_file() so pandoc resolves relative image paths
    (e.g. fig_prisma_flow.png) against the source file's directory.
    This is the key difference from convert_text(): text strings have no
    directory anchor, so relative image references silently fail.

    Returns *output_path* on success; raises RuntimeError on failure.
    """
    output_path.parent.mkdir(parents=True, exist_ok=True)
    abs_source = source_path.resolve()
    pypandoc.convert_file(
        str(abs_source),
        "docx",
        outputfile=str(output_path),
        extra_args=["--standalone", "--resource-path", str(abs_source.parent)],
    )
    if not output_path.exists():
        raise RuntimeError(f"pypandoc did not produce output at {output_path}")
    _fix_table_layout(output_path)
    return output_path
