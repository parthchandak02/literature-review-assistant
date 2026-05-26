"""Writing, manuscript sections/blocks/assemblies, and audit repository."""

from __future__ import annotations

import json
import logging
import re
from datetime import UTC, datetime
from hashlib import sha256
from typing import TYPE_CHECKING, Any

import aiosqlite

from src.models import (
    ManuscriptAssembly,
    ManuscriptAsset,
    ManuscriptAuditFinding,
    ManuscriptAuditResult,
    ManuscriptBlock,
    ManuscriptContractViolation,
    ManuscriptParityResult,
    ManuscriptSection,
    SectionDraft,
    SectionOutline,
    WritingManifestRecord,
)

if TYPE_CHECKING:
    from src.manuscript.contracts import ManuscriptContractResult

_logger = logging.getLogger(__name__)
_HEADING_RE = re.compile(r"^(#{2,6})\s+(.+)$")
_MARKER_RE = re.compile(r"^<!--\s*SECTION_BLOCK:([a-zA-Z0-9_.-]+)\s*-->$")
_CITE_RE = re.compile(r"\[(\d+|[A-Za-z][A-Za-z0-9_:-]*)\]")


class WritingRepo:
    def __init__(self, db: aiosqlite.Connection):
        self.db = db

    # ------------------------------------------------------------------
    # Writing generation helpers
    # ------------------------------------------------------------------

    async def get_writing_generation(self, workflow_id: str) -> int:
        cursor = await self.db.execute(
            "SELECT writing_generation FROM workflows WHERE workflow_id = ?",
            (workflow_id,),
        )
        row = await cursor.fetchone()
        if row and row[0] is not None:
            return max(1, int(row[0]))
        return 1

    async def bump_writing_generation(self, workflow_id: str) -> int:
        current = await self.get_writing_generation(workflow_id)
        next_generation = current + 1
        await self.db.execute(
            "UPDATE workflows SET writing_generation = ?, updated_at = CURRENT_TIMESTAMP WHERE workflow_id = ?",
            (next_generation, workflow_id),
        )
        await self.db.commit()
        return next_generation

    async def _resolve_writing_generation(self, workflow_id: str, generation: int | None) -> int:
        if generation is not None and generation > 0:
            return int(generation)
        return await self.get_writing_generation(workflow_id)

    # ------------------------------------------------------------------
    # Section outlines
    # ------------------------------------------------------------------

    async def get_completed_sections(self, workflow_id: str) -> set[str]:
        """Section names that have at least one draft (for writing phase resume)."""
        generation = await self.get_writing_generation(workflow_id)
        cursor = await self.db.execute(
            """
            SELECT DISTINCT section
            FROM section_drafts
            WHERE workflow_id = ? AND generation = ?
            """,
            (workflow_id, generation),
        )
        rows = await cursor.fetchall()
        return {str(row[0]) for row in rows}

    async def save_section_outline(
        self,
        workflow_id: str,
        outline: SectionOutline,
        generation: int | None = None,
    ) -> None:
        """Persist a section outline for the current writing generation."""
        resolved_generation = await self._resolve_writing_generation(workflow_id, generation)
        await self.db.execute(
            """
            INSERT INTO section_outlines (
                workflow_id, section_key, generation, outline_json, grounding_hash
            ) VALUES (?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, section_key, generation) DO UPDATE SET
                outline_json = excluded.outline_json,
                grounding_hash = excluded.grounding_hash,
                created_at = datetime('now')
            """,
            (
                workflow_id,
                outline.section_key,
                resolved_generation,
                outline.model_dump_json(),
                outline.grounding_hash,
            ),
        )
        await self.db.commit()

    async def load_section_outlines(
        self,
        workflow_id: str,
        generation: int | None = None,
    ) -> dict[str, SectionOutline]:
        """Load all persisted section outlines for a workflow generation."""
        resolved_generation = await self._resolve_writing_generation(workflow_id, generation)
        cursor = await self.db.execute(
            """
            SELECT section_key, outline_json
            FROM section_outlines
            WHERE workflow_id = ? AND generation = ?
            ORDER BY section_key
            """,
            (workflow_id, resolved_generation),
        )
        rows = await cursor.fetchall()
        outlines: dict[str, SectionOutline] = {}
        for section_key, outline_json in rows:
            try:
                outline = SectionOutline.model_validate_json(str(outline_json))
            except Exception as exc:
                _logger.warning(
                    "Skipping malformed section outline for workflow=%s section=%s: %s",
                    workflow_id,
                    section_key,
                    exc,
                )
                continue
            outlines[str(section_key)] = outline
        return outlines

    # ------------------------------------------------------------------
    # Section drafts
    # ------------------------------------------------------------------

    async def save_section_draft(self, draft: SectionDraft) -> None:
        """Persist a section draft for checkpoint/resume."""
        generation = await self._resolve_writing_generation(draft.workflow_id, draft.generation)
        await self.db.execute(
            """
            INSERT INTO section_drafts (
                workflow_id, section, version, generation, content, claims_used, citations_used, word_count
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, section, version, generation) DO UPDATE SET
                content = excluded.content,
                claims_used = excluded.claims_used,
                citations_used = excluded.citations_used,
                word_count = excluded.word_count
            """,
            (
                draft.workflow_id,
                draft.section,
                draft.version,
                generation,
                draft.content,
                json.dumps(draft.claims_used),
                json.dumps(draft.citations_used),
                draft.word_count,
            ),
        )
        await self.db.commit()

    async def delete_section_drafts(self, workflow_id: str, sections: set[str] | None = None) -> int:
        """Delete saved section drafts for a workflow.

        Returns number of rows deleted. When sections is None, removes all drafts
        for the workflow; otherwise only the specified section names.
        """
        if sections:
            placeholders = ",".join("?" for _ in sections)
            params = [workflow_id, *sorted(sections)]
            cursor = await self.db.execute(
                f"""
                DELETE FROM section_drafts
                WHERE workflow_id = ?
                  AND section IN ({placeholders})
                """,
                params,
            )
        else:
            cursor = await self.db.execute(
                """
                DELETE FROM section_drafts
                WHERE workflow_id = ?
                """,
                (workflow_id,),
            )
        await self.db.commit()
        return int(cursor.rowcount or 0)

    # ------------------------------------------------------------------
    # Manuscript sections / blocks
    # ------------------------------------------------------------------

    def _to_manuscript_blocks(
        self,
        workflow_id: str,
        section_key: str,
        section_version: int,
        generation: int,
        content: str,
    ) -> list[ManuscriptBlock]:
        """Parse section text into generic ordered blocks.

        Deterministic parser:
        1) explicit SECTION_BLOCK markers (highest priority),
        2) markdown heading boundaries,
        3) paragraph fallback.
        """
        blocks: list[ManuscriptBlock] = []
        order = 0
        lines = content.splitlines()
        para_buf: list[str] = []

        def _flush_para() -> None:
            nonlocal order, para_buf
            text = "\n".join(x for x in para_buf if x.strip()).strip()
            para_buf = []
            if not text:
                return
            blocks.append(
                ManuscriptBlock(
                    workflow_id=workflow_id,
                    section_key=section_key,
                    section_version=section_version,
                    generation=generation,
                    block_order=order,
                    block_type="paragraph",
                    text=text,
                )
            )
            order += 1

        for raw in lines:
            line = raw.rstrip()
            if _MARKER_RE.match(line.strip()):
                _flush_para()
                blocks.append(
                    ManuscriptBlock(
                        workflow_id=workflow_id,
                        section_key=section_key,
                        section_version=section_version,
                        generation=generation,
                        block_order=order,
                        block_type="marker",
                        text=line.strip(),
                    )
                )
                order += 1
                continue
            hm = _HEADING_RE.match(line.strip())
            if hm:
                _flush_para()
                blocks.append(
                    ManuscriptBlock(
                        workflow_id=workflow_id,
                        section_key=section_key,
                        section_version=section_version,
                        generation=generation,
                        block_order=order,
                        block_type="heading",
                        text=line.strip(),
                        meta_json=json.dumps({"level": len(hm.group(1)), "title": hm.group(2).strip()}),
                    )
                )
                order += 1
                continue
            if not line.strip():
                _flush_para()
                continue
            para_buf.append(line)
        _flush_para()
        if not blocks:
            blocks.append(
                ManuscriptBlock(
                    workflow_id=workflow_id,
                    section_key=section_key,
                    section_version=section_version,
                    generation=generation,
                    block_order=0,
                    block_type="paragraph",
                    text=content.strip(),
                )
            )
        return blocks

    async def save_manuscript_section_from_draft(self, draft: SectionDraft, section_order: int) -> None:
        """Dual-write section draft into DB-first manuscript section/block tables."""
        generation = await self._resolve_writing_generation(draft.workflow_id, draft.generation)
        section = ManuscriptSection(
            workflow_id=draft.workflow_id,
            section_key=draft.section,
            section_order=section_order,
            version=draft.version,
            generation=generation,
            title=draft.section.replace("_", " ").title(),
            source="parser",
            boundary_confidence=1.0,
            content_hash=sha256(draft.content.encode("utf-8")).hexdigest(),
            content=draft.content,
        )
        blocks = self._to_manuscript_blocks(
            workflow_id=draft.workflow_id,
            section_key=draft.section,
            section_version=draft.version,
            generation=generation,
            content=draft.content,
        )
        await self.db.execute(
            """
            DELETE FROM manuscript_sections
            WHERE workflow_id = ?
              AND version = ?
              AND generation = ?
              AND (section_key = ? OR section_order = ?)
            """,
            (draft.workflow_id, draft.version, generation, draft.section, section_order),
        )
        await self.db.execute(
            """
            INSERT INTO manuscript_sections
                (workflow_id, section_key, section_order, version, generation, title, status, source,
                 boundary_confidence, content_hash, content)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, section_key, version, generation) DO UPDATE SET
                section_order = excluded.section_order,
                title = excluded.title,
                status = excluded.status,
                source = excluded.source,
                boundary_confidence = excluded.boundary_confidence,
                content_hash = excluded.content_hash,
                content = excluded.content,
                updated_at = CURRENT_TIMESTAMP
            """,
            (
                section.workflow_id,
                section.section_key,
                section.section_order,
                section.version,
                generation,
                section.title,
                section.status,
                section.source,
                section.boundary_confidence,
                section.content_hash,
                section.content,
            ),
        )
        await self.db.execute(
            """
            DELETE FROM manuscript_blocks
            WHERE workflow_id = ? AND section_key = ? AND section_version = ? AND generation = ?
            """,
            (draft.workflow_id, draft.section, draft.version, generation),
        )
        await self.db.executemany(
            """
            INSERT INTO manuscript_blocks
                (workflow_id, section_key, section_version, generation, block_order, block_type, text, meta_json)
            VALUES (?, ?, ?, ?, ?, ?, ?, ?)
            """,
            [
                (
                    b.workflow_id,
                    b.section_key,
                    b.section_version,
                    generation,
                    b.block_order,
                    b.block_type,
                    b.text,
                    b.meta_json,
                )
                for b in blocks
            ],
        )
        await self.db.commit()

    async def save_section_artifacts_from_draft(self, draft: SectionDraft, section_order: int) -> None:
        """Persist one section through the canonical idempotent save path."""
        generation = await self._resolve_writing_generation(draft.workflow_id, draft.generation)
        resolved_draft = draft.model_copy(update={"generation": generation})
        await self.save_section_draft(resolved_draft)
        await self.save_manuscript_section_from_draft(resolved_draft, section_order=section_order)

    async def load_latest_manuscript_sections(self, workflow_id: str) -> list[ManuscriptSection]:
        generation = await self.get_writing_generation(workflow_id)
        cursor = await self.db.execute(
            """
            SELECT s.workflow_id, s.section_key, s.section_order, s.version, s.generation, s.title, s.status,
                   s.source, s.boundary_confidence, s.content_hash, s.content
            FROM manuscript_sections s
            JOIN (
                SELECT workflow_id, section_key, MAX(version) AS max_version
                FROM manuscript_sections
                WHERE workflow_id = ? AND generation = ?
                GROUP BY workflow_id, section_key
            ) lv
              ON s.workflow_id = lv.workflow_id
             AND s.section_key = lv.section_key
             AND s.version = lv.max_version
            WHERE s.workflow_id = ? AND s.generation = ?
            ORDER BY s.section_order ASC
            """,
            (workflow_id, generation, workflow_id, generation),
        )
        rows = await cursor.fetchall()
        out: list[ManuscriptSection] = []
        for row in rows:
            out.append(
                ManuscriptSection(
                    workflow_id=str(row[0]),
                    section_key=str(row[1]),
                    section_order=int(row[2]),
                    version=int(row[3]),
                    generation=int(row[4]),
                    title=str(row[5]),
                    status=str(row[6]),
                    source=str(row[7]),
                    boundary_confidence=float(row[8]),
                    content_hash=str(row[9]),
                    content=str(row[10]),
                )
            )
        return out

    # ------------------------------------------------------------------
    # Manuscript assemblies / assets
    # ------------------------------------------------------------------

    async def load_latest_manuscript_assembly(self, workflow_id: str, target_format: str) -> ManuscriptAssembly | None:
        generation = await self.get_writing_generation(workflow_id)
        cursor = await self.db.execute(
            """
            SELECT workflow_id, assembly_id, target_format, generation, content, manifest_json
            FROM manuscript_assemblies
            WHERE workflow_id = ? AND target_format = ? AND generation = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (workflow_id, target_format, generation),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return ManuscriptAssembly(
            workflow_id=str(row[0]),
            assembly_id=str(row[1]),
            target_format=str(row[2]),
            generation=int(row[3]),
            content=str(row[4]),
            manifest_json=str(row[5]),
        )

    async def save_manuscript_asset(self, asset: ManuscriptAsset) -> None:
        await self.db.execute(
            """
            INSERT INTO manuscript_assets
                (workflow_id, asset_key, asset_type, format, content, source_path, version)
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, asset_key, version) DO UPDATE SET
                asset_type = excluded.asset_type,
                format = excluded.format,
                content = excluded.content,
                source_path = excluded.source_path
            """,
            (
                asset.workflow_id,
                asset.asset_key,
                asset.asset_type,
                asset.format,
                asset.content,
                asset.source_path,
                asset.version,
            ),
        )
        await self.db.commit()

    async def load_latest_manuscript_asset(self, workflow_id: str, asset_key: str) -> ManuscriptAsset | None:
        cursor = await self.db.execute(
            """
            SELECT workflow_id, asset_key, asset_type, format, content, source_path, version
            FROM manuscript_assets
            WHERE workflow_id = ? AND asset_key = ?
            ORDER BY version DESC
            LIMIT 1
            """,
            (workflow_id, asset_key),
        )
        row = await cursor.fetchone()
        if not row:
            return None
        return ManuscriptAsset(
            workflow_id=str(row[0]),
            asset_key=str(row[1]),
            asset_type=str(row[2]),
            format=str(row[3]),
            content=str(row[4]),
            source_path=str(row[5]) if row[5] is not None else None,
            version=int(row[6]),
        )

    async def _validate_assembly_manifest(self, workflow_id: str, manifest_json: str) -> None:
        try:
            manifest = json.loads(manifest_json or "{}")
        except Exception as exc:
            raise RuntimeError("Invalid manuscript assembly manifest JSON") from exc
        generation = await self.get_writing_generation(workflow_id)
        sections = manifest.get("sections", [])
        if sections:
            declared_orders = [int(s.get("order", i)) for i, s in enumerate(sections)]
            if sorted(declared_orders) != list(
                range(min(declared_orders), min(declared_orders) + len(declared_orders))
            ):
                raise RuntimeError("Assembly manifest section order is not contiguous")
            for s in sections:
                key = str(s.get("section_key", ""))
                ver = int(s.get("version", 0))
                if not key or ver <= 0:
                    raise RuntimeError("Assembly manifest section reference is invalid")
                cur = await self.db.execute(
                    """
                    SELECT 1 FROM manuscript_sections
                    WHERE workflow_id = ? AND section_key = ? AND version = ? AND generation = ?
                    LIMIT 1
                    """,
                    (workflow_id, key, ver, generation),
                )
                row = await cur.fetchone()
                if row is None:
                    raise RuntimeError(f"Assembly manifest references missing section: {key}@v{ver}")
        assets = manifest.get("assets", [])
        for a in assets:
            key = str(a.get("asset_key", ""))
            ver = int(a.get("version", 0))
            if not key or ver <= 0:
                raise RuntimeError("Assembly manifest asset reference is invalid")
            cur = await self.db.execute(
                """
                SELECT 1 FROM manuscript_assets
                WHERE workflow_id = ? AND asset_key = ? AND version = ?
                LIMIT 1
                """,
                (workflow_id, key, ver),
            )
            row = await cur.fetchone()
            if row is None:
                raise RuntimeError(f"Assembly manifest references missing asset: {key}@v{ver}")

    async def save_manuscript_assembly(self, assembly: ManuscriptAssembly) -> None:
        if assembly.target_format not in {"md", "tex"}:
            raise RuntimeError(f"Unsupported manuscript assembly format: {assembly.target_format}")
        await self._validate_assembly_manifest(assembly.workflow_id, assembly.manifest_json)
        generation = await self._resolve_writing_generation(assembly.workflow_id, assembly.generation)
        await self.db.execute(
            """
            INSERT INTO manuscript_assemblies
                (workflow_id, assembly_id, target_format, generation, content, manifest_json)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, assembly_id, target_format, generation) DO UPDATE SET
                content = excluded.content,
                manifest_json = excluded.manifest_json
            """,
            (
                assembly.workflow_id,
                assembly.assembly_id,
                assembly.target_format,
                generation,
                assembly.content,
                assembly.manifest_json,
            ),
        )
        await self.db.commit()

    async def backfill_manuscript_sections_from_drafts(self, workflow_id: str) -> int:
        """Backfill DB-first section tables from latest section_drafts rows."""
        generation = await self.get_writing_generation(workflow_id)
        cursor = await self.db.execute(
            """
            SELECT sd.workflow_id, sd.section, sd.version, sd.generation, sd.content, sd.word_count
            FROM section_drafts sd
            JOIN (
                SELECT workflow_id, section, MAX(version) AS max_version
                FROM section_drafts
                WHERE workflow_id = ? AND generation = ?
                GROUP BY workflow_id, section
            ) latest
              ON sd.workflow_id = latest.workflow_id
             AND sd.section = latest.section
             AND sd.version = latest.max_version
            WHERE sd.workflow_id = ? AND sd.generation = ?
            ORDER BY sd.section
            """,
            (workflow_id, generation, workflow_id, generation),
        )
        rows = await cursor.fetchall()
        if not rows:
            return 0
        count = 0
        for order, row in enumerate(rows):
            draft = SectionDraft(
                workflow_id=str(row[0]),
                section=str(row[1]),
                version=int(row[2]),
                generation=int(row[3]),
                content=str(row[4]),
                claims_used=[],
                citations_used=[],
                word_count=int(row[5]) if row[5] is not None else len(str(row[4]).split()),
            )
            await self.save_section_artifacts_from_draft(draft, section_order=order)
            count += 1
        return count

    async def validate_manuscript_md_parity(self, workflow_id: str, legacy_md: str) -> ManuscriptParityResult:
        """Compare legacy markdown and latest DB markdown assembly for migration safety."""
        assembly = await self.load_latest_manuscript_assembly(workflow_id, "md")
        if assembly is None:
            return ManuscriptParityResult()

        legacy_hash = sha256(legacy_md.encode("utf-8")).hexdigest()
        assembly_hash = sha256(assembly.content.encode("utf-8")).hexdigest()
        legacy_cites = sorted(set(_CITE_RE.findall(legacy_md)))
        assembly_cites = sorted(set(_CITE_RE.findall(assembly.content)))
        legacy_sections = len(re.findall(r"^##\s+", legacy_md, flags=re.MULTILINE))
        assembly_sections = len(re.findall(r"^##\s+", assembly.content, flags=re.MULTILINE))
        return ManuscriptParityResult(
            has_assembly=True,
            hash_match=legacy_hash == assembly_hash,
            citation_set_match=legacy_cites == assembly_cites,
            section_count_match=legacy_sections == assembly_sections,
            legacy_hash=legacy_hash,
            assembly_hash=assembly_hash,
        )

    # ------------------------------------------------------------------
    # Writing manifests
    # ------------------------------------------------------------------

    async def save_writing_manifest(self, record: WritingManifestRecord) -> None:
        """Persist a per-section writing manifest row."""
        generation = await self._resolve_writing_generation(record.workflow_id, record.generation)
        await self.db.execute(
            """
            INSERT INTO writing_manifests (
                workflow_id, section_key, attempt_number, generation, grounding_hash,
                evidence_source_ids, citation_catalog_hash, contract_status,
                contract_issues, fallback_used, retry_count, word_count,
                meta_json, created_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(workflow_id, section_key, attempt_number, generation) DO UPDATE SET
                grounding_hash = excluded.grounding_hash,
                evidence_source_ids = excluded.evidence_source_ids,
                citation_catalog_hash = excluded.citation_catalog_hash,
                contract_status = excluded.contract_status,
                contract_issues = excluded.contract_issues,
                fallback_used = excluded.fallback_used,
                retry_count = excluded.retry_count,
                word_count = excluded.word_count,
                meta_json = excluded.meta_json
            """,
            (
                record.workflow_id,
                record.section_key,
                record.attempt_number,
                generation,
                record.grounding_hash,
                record.evidence_source_ids,
                record.citation_catalog_hash,
                record.contract_status,
                record.contract_issues,
                1 if record.fallback_used else 0,
                record.retry_count,
                record.word_count,
                record.meta_json,
                record.created_at.isoformat(),
            ),
        )
        await self.db.commit()

    async def get_writing_manifests(
        self, workflow_id: str, section_key: str | None = None
    ) -> list[WritingManifestRecord]:
        """Return writing manifests for a workflow, optionally filtered by section."""
        generation = await self.get_writing_generation(workflow_id)
        if section_key:
            cursor = await self.db.execute(
                """
                SELECT workflow_id, section_key, attempt_number, generation, grounding_hash,
                       evidence_source_ids, citation_catalog_hash, contract_status,
                       contract_issues, fallback_used, retry_count, word_count,
                       meta_json, created_at
                FROM writing_manifests
                WHERE workflow_id = ? AND section_key = ? AND generation = ?
                ORDER BY attempt_number DESC
                """,
                (workflow_id, section_key, generation),
            )
        else:
            cursor = await self.db.execute(
                """
                SELECT workflow_id, section_key, attempt_number, generation, grounding_hash,
                       evidence_source_ids, citation_catalog_hash, contract_status,
                       contract_issues, fallback_used, retry_count, word_count,
                       meta_json, created_at
                FROM writing_manifests
                WHERE workflow_id = ? AND generation = ?
                ORDER BY section_key, attempt_number DESC
                """,
                (workflow_id, generation),
            )
        rows = await cursor.fetchall()
        return [
            WritingManifestRecord(
                workflow_id=str(r[0]),
                section_key=str(r[1]),
                attempt_number=int(r[2]),
                generation=int(r[3]),
                grounding_hash=str(r[4]) if r[4] else None,
                evidence_source_ids=str(r[5] or "[]"),
                citation_catalog_hash=str(r[6]) if r[6] else None,
                contract_status=str(r[7]),
                contract_issues=str(r[8] or "[]"),
                fallback_used=bool(r[9]),
                retry_count=int(r[10]),
                word_count=int(r[11]) if r[11] is not None else None,
                meta_json=str(r[12] or "{}"),
                created_at=datetime.fromisoformat(str(r[13])) if r[13] else datetime.now(UTC),
            )
            for r in rows
        ]

    # ------------------------------------------------------------------
    # Manuscript audit
    # ------------------------------------------------------------------

    async def _table_columns(self, table: str) -> set[str]:
        try:
            async with self.db.execute(f"PRAGMA table_info({table})") as cur:
                rows = await cur.fetchall()
        except Exception:
            return set()
        return {str(row[1]) for row in rows}

    async def _ensure_manuscript_audit_columns(self) -> None:
        columns = await self._table_columns("manuscript_audit_runs")
        alter_statements = [
            (
                "gate_mode",
                "ALTER TABLE manuscript_audit_runs ADD COLUMN gate_mode TEXT NOT NULL DEFAULT 'strict'",
            ),
            (
                "gate_action",
                "ALTER TABLE manuscript_audit_runs ADD COLUMN gate_action TEXT NOT NULL DEFAULT 'strict_block'",
            ),
            (
                "top_recommendations_json",
                "ALTER TABLE manuscript_audit_runs ADD COLUMN top_recommendations_json TEXT NOT NULL DEFAULT '[]'",
            ),
        ]
        changed = False
        for column_name, statement in alter_statements:
            if column_name in columns:
                continue
            try:
                await self.db.execute(statement)
                changed = True
            except Exception:
                continue
        if changed:
            await self.db.commit()

    @staticmethod
    def _select_top_audit_recommendations(
        findings: list[ManuscriptAuditFinding],
        limit: int = 3,
    ) -> list[str]:
        recommendations: list[str] = []
        seen: set[str] = set()
        for finding in findings:
            recommendation = str(finding.recommendation or "").strip()
            if not recommendation or recommendation in seen:
                continue
            seen.add(recommendation)
            recommendations.append(recommendation)
            if len(recommendations) >= limit:
                break
        return recommendations

    @staticmethod
    def _decode_json_list(raw: object) -> list[object]:
        try:
            value = json.loads(str(raw or "[]"))
        except Exception:
            return []
        return value if isinstance(value, list) else []

    def _manuscript_audit_select_sql(self, include_workflow_id: bool) -> str:
        base_columns = ["audit_run_id"]
        if include_workflow_id:
            base_columns.append("workflow_id")
        base_columns.extend(
            [
                "mode",
                "verdict",
                "passed",
                "selected_profiles_json",
                "summary",
                "total_findings",
                "major_count",
                "minor_count",
                "note_count",
                "blocking_count",
                "total_cost_usd",
                "created_at",
            ]
        )
        return ", ".join(base_columns)

    def _decode_manuscript_audit_row(self, row: tuple[Any, ...], include_workflow_id: bool) -> ManuscriptAuditResult:
        idx = 0
        payload: dict[str, Any] = {"audit_run_id": str(row[idx])}
        idx += 1
        if include_workflow_id:
            payload["workflow_id"] = str(row[idx])
            idx += 1
        payload["mode"] = str(row[idx])
        idx += 1
        payload["verdict"] = str(row[idx])
        idx += 1
        payload["passed"] = bool(row[idx])
        idx += 1
        payload["selected_profiles"] = self._decode_json_list(row[idx])
        idx += 1
        payload["summary"] = str(row[idx] or "")
        idx += 1
        payload["total_findings"] = int(row[idx] or 0)
        idx += 1
        payload["major_count"] = int(row[idx] or 0)
        idx += 1
        payload["minor_count"] = int(row[idx] or 0)
        idx += 1
        payload["note_count"] = int(row[idx] or 0)
        idx += 1
        payload["blocking_count"] = int(row[idx] or 0)
        idx += 1
        payload["total_cost_usd"] = float(row[idx] or 0.0)
        idx += 1
        payload["created_at"] = str(row[idx] or "")
        idx += 1
        if len(row) > idx:
            payload["contract_mode"] = str(row[idx] or "observe")
            idx += 1
            payload["contract_passed"] = bool(row[idx])
            idx += 1
            payload["contract_violation_count"] = int(row[idx] or 0)
            idx += 1
            payload["contract_violations"] = [
                ManuscriptContractViolation.model_validate(item).model_dump()
                for item in self._decode_json_list(row[idx])
                if isinstance(item, dict)
            ]
            idx += 1
            payload["gate_blocked"] = bool(row[idx])
            idx += 1
            payload["gate_mode"] = str(row[idx] or "strict")
            idx += 1
            payload["gate_action"] = str(row[idx] or "strict_block")
            idx += 1
            payload["gate_failure_reasons"] = self._decode_json_list(row[idx])
            idx += 1
            payload["top_recommendations"] = self._decode_json_list(row[idx])
            idx += 1
        else:
            payload["contract_mode"] = "observe"
            payload["contract_passed"] = True
            payload["contract_violation_count"] = 0
            payload["contract_violations"] = []
            payload["gate_blocked"] = False
            payload["gate_mode"] = "strict"
            payload["gate_action"] = "strict_block"
            payload["gate_failure_reasons"] = []
            payload["top_recommendations"] = []
        payload["last_audited_at"] = payload["created_at"]
        return ManuscriptAuditResult.model_validate(payload)

    async def _manuscript_audit_optional_select_columns(self) -> str:
        cols = await self._table_columns("manuscript_audit_runs")
        wanted = [
            "contract_mode",
            "contract_passed",
            "contract_violation_count",
            "contract_violations_json",
            "gate_blocked",
            "gate_mode",
            "gate_action",
            "gate_failure_reasons_json",
            "top_recommendations_json",
        ]
        available = [name for name in wanted if name in cols]
        if not available:
            return ""
        return ", " + ", ".join(available)

    async def save_manuscript_audit(
        self,
        result: ManuscriptAuditResult,
        findings: list[ManuscriptAuditFinding],
        contract_result: ManuscriptContractResult | None = None,
        gate_blocked: bool = False,
        gate_mode: str = "strict",
        gate_action: str = "strict_block",
        gate_failure_reasons: list[str] | None = None,
    ) -> None:
        contract_payload = contract_result
        failure_reasons = gate_failure_reasons or []
        await self._ensure_manuscript_audit_columns()
        run_columns = await self._table_columns("manuscript_audit_runs")
        top_recommendations = self._select_top_audit_recommendations(findings)
        insert_columns = [
            "audit_run_id",
            "workflow_id",
            "mode",
            "verdict",
            "passed",
            "selected_profiles_json",
            "summary",
            "total_findings",
            "major_count",
            "minor_count",
            "note_count",
            "blocking_count",
        ]
        insert_values: list[object] = [
            result.audit_run_id,
            result.workflow_id,
            result.mode,
            result.verdict,
            1 if result.passed else 0,
            json.dumps(result.selected_profiles, ensure_ascii=True),
            result.summary,
            result.total_findings,
            result.major_count,
            result.minor_count,
            result.note_count,
            result.blocking_count,
        ]
        if "contract_mode" in run_columns:
            insert_columns.append("contract_mode")
            insert_values.append(str(contract_payload.mode) if contract_payload is not None else "observe")
        if "contract_passed" in run_columns:
            insert_columns.append("contract_passed")
            insert_values.append(1 if (contract_payload.passed if contract_payload is not None else True) else 0)
        if "contract_violation_count" in run_columns:
            insert_columns.append("contract_violation_count")
            insert_values.append(len(contract_payload.violations) if contract_payload is not None else 0)
        if "contract_violations_json" in run_columns:
            insert_columns.append("contract_violations_json")
            insert_values.append(
                json.dumps(
                    [v.model_dump() for v in contract_payload.violations] if contract_payload is not None else [],
                    ensure_ascii=True,
                )
            )
        if "gate_blocked" in run_columns:
            insert_columns.append("gate_blocked")
            insert_values.append(1 if gate_blocked else 0)
        if "gate_mode" in run_columns:
            insert_columns.append("gate_mode")
            insert_values.append(gate_mode)
        if "gate_action" in run_columns:
            insert_columns.append("gate_action")
            insert_values.append(gate_action)
        if "gate_failure_reasons_json" in run_columns:
            insert_columns.append("gate_failure_reasons_json")
            insert_values.append(json.dumps(failure_reasons, ensure_ascii=True))
        if "top_recommendations_json" in run_columns:
            insert_columns.append("top_recommendations_json")
            insert_values.append(json.dumps(top_recommendations, ensure_ascii=True))
        insert_columns.append("total_cost_usd")
        insert_values.append(result.total_cost_usd)
        placeholders = ", ".join("?" for _ in insert_columns)
        await self.db.execute(
            f"""
            INSERT INTO manuscript_audit_runs (
                {", ".join(insert_columns)}
            ) VALUES ({placeholders})
            """,
            tuple(insert_values),
        )
        for finding in findings:
            await self.db.execute(
                """
                INSERT INTO manuscript_audit_findings (
                    audit_run_id, workflow_id, finding_id, profile, severity, category, section,
                    evidence, recommendation, owner_module, blocking
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    result.audit_run_id,
                    result.workflow_id,
                    finding.finding_id,
                    finding.profile,
                    finding.severity,
                    finding.category,
                    finding.section,
                    finding.evidence,
                    finding.recommendation,
                    finding.owner_module,
                    1 if finding.blocking else 0,
                ),
            )
        await self.db.commit()

    async def get_latest_manuscript_audit(self, workflow_id: str) -> ManuscriptAuditResult | None:
        optional_columns = await self._manuscript_audit_optional_select_columns()
        row = await (
            await self.db.execute(
                f"""
                SELECT {self._manuscript_audit_select_sql(include_workflow_id=True)}{optional_columns}
                FROM manuscript_audit_runs
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (workflow_id,),
            )
        ).fetchone()
        if row is None:
            return None
        return self._decode_manuscript_audit_row(row, include_workflow_id=True)

    async def get_manuscript_audit_run(self, workflow_id: str, audit_run_id: str) -> ManuscriptAuditResult | None:
        optional_columns = await self._manuscript_audit_optional_select_columns()
        row = await (
            await self.db.execute(
                f"""
                SELECT {self._manuscript_audit_select_sql(include_workflow_id=True)}{optional_columns}
                FROM manuscript_audit_runs
                WHERE workflow_id = ? AND audit_run_id = ?
                LIMIT 1
                """,
                (workflow_id, audit_run_id),
            )
        ).fetchone()
        if row is None:
            return None
        return self._decode_manuscript_audit_row(row, include_workflow_id=True)

    async def get_manuscript_audit_history(self, workflow_id: str, limit: int = 20) -> list[ManuscriptAuditResult]:
        optional_columns = await self._manuscript_audit_optional_select_columns()
        rows = await (
            await self.db.execute(
                f"""
                SELECT {self._manuscript_audit_select_sql(include_workflow_id=True)}{optional_columns}
                FROM manuscript_audit_runs
                WHERE workflow_id = ?
                ORDER BY created_at DESC
                LIMIT ?
                """,
                (workflow_id, limit),
            )
        ).fetchall()
        out: list[ManuscriptAuditResult] = []
        for row in rows:
            out.append(self._decode_manuscript_audit_row(row, include_workflow_id=True))
        return out

    async def get_manuscript_audit_findings(self, audit_run_id: str) -> list[ManuscriptAuditFinding]:
        rows = await (
            await self.db.execute(
                """
                SELECT finding_id, profile, severity, category, section, evidence, recommendation, owner_module, blocking, created_at
                FROM manuscript_audit_findings
                WHERE audit_run_id = ?
                ORDER BY id ASC
                """,
                (audit_run_id,),
            )
        ).fetchall()
        out: list[ManuscriptAuditFinding] = []
        for row in rows:
            out.append(
                ManuscriptAuditFinding(
                    finding_id=str(row[0]),
                    profile=str(row[1]),
                    severity=str(row[2]),
                    category=str(row[3]),
                    section=str(row[4]) if row[4] else None,
                    evidence=str(row[5]),
                    recommendation=str(row[6]),
                    owner_module=str(row[7]),
                    blocking=bool(row[8]),
                    created_at=str(row[9] or ""),
                )
            )
        return out
