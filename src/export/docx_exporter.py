"""Convert a Markdown manuscript to a .docx Word document using pypandoc."""

from __future__ import annotations

from pathlib import Path

import pypandoc


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
    return output_path
