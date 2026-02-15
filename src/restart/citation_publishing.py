"""CSL-first citation and publishing artifact configuration."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path


@dataclass(frozen=True)
class PublicationArtifact:
    """Output artifact metadata for publication exports."""

    path: str
    format_name: str


@dataclass
class CitationPublishingPipeline:
    """Defines source-of-truth files for CSL-first manuscript publishing."""

    output_dir: str
    bibliography_filename: str = "references.csl.json"
    manuscript_filename: str = "manuscript.md"
    csl_filename: str = "style.csl"
    render_formats: tuple[str, ...] = ("html", "docx", "pdf")
    include_manubot_manifest: bool = True

    def prepare_layout(self) -> list[PublicationArtifact]:
        Path(self.output_dir).mkdir(parents=True, exist_ok=True)
        artifacts: list[PublicationArtifact] = []
        artifacts.append(self._touch(self.manuscript_filename, "markdown"))
        artifacts.append(self._touch(self.bibliography_filename, "csl_json"))
        artifacts.append(self._touch(self.csl_filename, "csl_style"))
        if self.include_manubot_manifest:
            artifacts.append(self._touch("manubot.json", "manubot_manifest"))
        for fmt in self.render_formats:
            artifacts.append(
                PublicationArtifact(
                    path=str(Path(self.output_dir) / f"manuscript.{fmt}"),
                    format_name=f"pandoc_{fmt}",
                )
            )
        return artifacts

    def _touch(self, filename: str, format_name: str) -> PublicationArtifact:
        path = Path(self.output_dir) / filename
        if not path.exists():
            path.write_text("", encoding="utf-8")
        return PublicationArtifact(path=str(path), format_name=format_name)
