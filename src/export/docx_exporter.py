"""Convert a Markdown manuscript to a .docx Word document using pypandoc."""

from __future__ import annotations

from pathlib import Path

import pypandoc
from docx import Document
from docx.oxml import OxmlElement
from docx.oxml.ns import qn


def _fix_table_layout(docx_path: Path) -> None:
    """Post-process all tables in *docx_path* to span 100% page width with fixed layout.

    Pandoc generates proportional column widths from the markdown separator dashes,
    but Office 365 can override them and snap to equal widths. Setting
    w:tblW type="pct" w="5000" (100% page width) and w:tblLayout type="fixed"
    forces Word to respect the proportional widths.
    """
    doc = Document(str(docx_path))
    for table in doc.tables:
        tbl = table._tbl
        tblPr = tbl.find(qn("w:tblPr"))
        if tblPr is None:
            tblPr = OxmlElement("w:tblPr")
            tbl.insert(0, tblPr)
        tblW = tblPr.find(qn("w:tblW"))
        if tblW is None:
            tblW = OxmlElement("w:tblW")
            tblPr.append(tblW)
        tblW.set(qn("w:w"), "5000")
        tblW.set(qn("w:type"), "pct")
        tblLayout = tblPr.find(qn("w:tblLayout"))
        if tblLayout is None:
            tblLayout = OxmlElement("w:tblLayout")
            tblPr.append(tblLayout)
        tblLayout.set(qn("w:type"), "fixed")
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
