#!/usr/bin/env python3
"""Build and update the gold standard benchmark from reference/ PDFs.

Reads all systematic review PDFs in reference/, extracts structured
quality dimensions using the PDF vision LLM, computes derived thresholds,
and updates reference/gold_standard_benchmark.json.

Optionally fetches 2-3 additional high-quality published SRs from the web
(via Exa or Perplexity) to extend the benchmark corpus.

Usage:
    uv run python scripts/build_benchmark.py
    uv run python scripts/build_benchmark.py --fetch-web
    uv run python scripts/build_benchmark.py --fetch-web --topic "your review topic here"
    uv run python scripts/build_benchmark.py --dry-run   # show what would be extracted, no write
"""

from __future__ import annotations

import argparse
import asyncio
import json
import pathlib
import re
import sys
from datetime import date
from typing import Any

from dotenv import load_dotenv
from rich.console import Console
from rich.panel import Panel
from rich.table import Table

console = Console()

REFERENCE_DIR = pathlib.Path("reference")
BENCHMARK_FILE = REFERENCE_DIR / "gold_standard_benchmark.json"

# Extraction prompt: asks the LLM to return structured JSON from a PDF.
_EXTRACTION_PROMPT = """You are a systematic review methodology expert. Read the provided PDF text carefully.

Extract the following structured information. Return ONLY a valid JSON object -- no markdown, no commentary.

If a field cannot be determined from the text, use null.

Required JSON structure:
{
  "title": "<full title of the paper>",
  "authors": ["<Author1 Surname>", "<Author2 Surname>"],
  "journal": "<journal name>",
  "year": <integer year>,
  "doi": "<doi string or null>",
  "study_type": "<systematic_review | scoping_review | narrative_review | meta_analysis | qualitative | cross_sectional | cohort | RCT | other>",
  "pages": <integer page count or null>,
  "databases_searched": ["<db1>", "<db2>"],
  "n_databases": <integer>,
  "search_date_range": "<YYYY-YYYY or null>",
  "records_identified": <integer or null>,
  "records_after_dedup": <integer or null>,
  "full_texts_assessed": <integer or null>,
  "n_included_studies": <integer or null>,
  "n_total_references": <integer: count how many numbered references appear in the References section>,
  "prospero_registered": <true | false>,
  "prospero_id": "<id string or null>",
  "n_independent_reviewers": <integer or null>,
  "third_reviewer_conflict_resolution": <true | false>,
  "screening_tool": "<e.g. Rayyan, ASReview, Covidence, or null>",
  "rob_tools": ["<tool1>", "<tool2>"],
  "rob_design_specific": <true if multiple RoB tools used for different designs | false | null>,
  "grade_used": <true | false>,
  "theoretical_framework": ["<framework1>", "<framework2>"],
  "thematic_synthesis_software": "<NVivo | ATLAS.ti | MaxQDA | null>",
  "publication_bias_test": <true | false>,
  "eggers_test": <true | false>,
  "n_tables": <integer count of tables in the paper>,
  "n_figures": <integer count of figures in the paper>,
  "has_prisma_flow": <true | false>,
  "has_pico_table": <true | false>,
  "has_rob_table": <true | false>,
  "has_study_characteristics_table": <true | false>,
  "has_outcome_synthesis_table": <true | false>,
  "abstract_sections": ["<Background>", "<Methods>", "<Results>", "<Conclusion>", "<Keywords>"],
  "sections_present": ["<Introduction>", "<Methods>", "<Results>", "<Discussion>", "<Conclusion>"],
  "limitations_explicit": <true | false>,
  "future_directions_explicit": <true | false>,
  "author_contributions_cre_dit": <true | false>,
  "funding_statement": <true | false>,
  "competing_interests_statement": <true | false>,
  "open_access": <true | false>,
  "supplementary_material": <true | false>,
  "grey_literature_searched": <true | false>,
  "citation_chasing": <true | false>
}
"""


# ---------------------------------------------------------------------------
# PDF reading
# ---------------------------------------------------------------------------


def read_pdf_text(pdf_path: pathlib.Path) -> str:
    """Read PDF text using pypdf (fast, no LLM needed for text extraction)."""
    try:
        import pypdf  # type: ignore

        reader = pypdf.PdfReader(str(pdf_path))
        pages = []
        for page in reader.pages:
            text = page.extract_text() or ""
            pages.append(text)
        return "\n".join(pages)
    except ImportError:
        console.print("[yellow]pypdf not installed. Falling back to pdfminer.[/yellow]")
        return _read_pdf_pdfminer(pdf_path)
    except Exception as exc:
        console.print(f"[red]Failed to read {pdf_path.name}: {exc}[/red]")
        return ""


def _read_pdf_pdfminer(pdf_path: pathlib.Path) -> str:
    """Fallback PDF reader using pdfminer.six."""
    try:
        from pdfminer.high_level import extract_text  # type: ignore

        return extract_text(str(pdf_path))
    except ImportError:
        console.print("[red]Neither pypdf nor pdfminer.six is installed. Run: uv add pypdf[/red]")
        return ""
    except Exception as exc:
        console.print(f"[red]pdfminer failed for {pdf_path.name}: {exc}[/red]")
        return ""


# ---------------------------------------------------------------------------
# LLM extraction
# ---------------------------------------------------------------------------


async def extract_metrics_with_llm(pdf_text: str, filename: str) -> dict[str, Any]:
    """Use the configured PDF vision LLM to extract structured metrics from PDF text."""
    from src.config.loader import load_configs
    from src.llm.gemini_client import GeminiClient

    _, settings = load_configs()
    model = settings.extraction.pdf_vision_model

    client = GeminiClient(model=model)
    prompt = f"{_EXTRACTION_PROMPT}\n\nPDF TEXT:\n{pdf_text[:60000]}"

    try:
        response = await client.generate(prompt)
        # Strip markdown code fences if present
        text = response.strip()
        if text.startswith("```"):
            text = re.sub(r"^```[a-z]*\n?", "", text)
            text = re.sub(r"\n?```$", "", text)
        extracted = json.loads(text)
        extracted["filename"] = filename
        return extracted
    except json.JSONDecodeError as exc:
        console.print(f"[red]LLM returned non-JSON for {filename}: {exc}[/red]")
        return {"filename": filename, "error": "llm_json_parse_failed"}
    except Exception as exc:
        console.print(f"[red]LLM extraction failed for {filename}: {exc}[/red]")
        return {"filename": filename, "error": str(exc)}


def _determine_quality_tier(metrics: dict[str, Any]) -> str:
    """Classify paper quality tier based on extracted metrics."""
    prospero = metrics.get("prospero_registered", False)
    rob_tools = metrics.get("rob_tools") or []
    thematic_sw = metrics.get("thematic_synthesis_software")
    pub_bias = metrics.get("publication_bias_test", False)
    grade = metrics.get("grade_used", False)

    score = 0
    if prospero:
        score += 3
    if len(rob_tools) >= 2:
        score += 2
    if thematic_sw:
        score += 1
    if pub_bias:
        score += 1
    if grade:
        score += 1

    if score >= 6:
        return "tier_1"
    elif score >= 3:
        return "tier_2"
    else:
        return "tier_3"


# ---------------------------------------------------------------------------
# Web fetch (Exa/Perplexity)
# ---------------------------------------------------------------------------


async def fetch_web_srs(topic: str, n: int = 3) -> list[dict[str, Any]]:
    """Fetch additional published systematic reviews from the web via Exa or Perplexity.

    Returns a list of dicts with title, doi, abstract, and source metadata.
    These are added to gold_standard_benchmark.json under web_sourced_papers.
    """
    console.print(f"\n[cyan]Fetching {n} additional SRs from web for topic: '{topic}'[/cyan]")

    # Try Exa first (preferred for academic papers)
    try:
        return await _fetch_via_exa(topic, n)
    except Exception as exc:
        console.print(f"[yellow]Exa fetch failed ({exc}), trying Perplexity...[/yellow]")

    try:
        return await _fetch_via_perplexity(topic, n)
    except Exception as exc:
        console.print(f"[red]Perplexity fetch also failed: {exc}[/red]")
        return []


async def _fetch_via_exa(topic: str, n: int) -> list[dict[str, Any]]:
    """Fetch SRs via Exa academic search."""
    import aiohttp

    exa_api_key = __import__("os").environ.get("EXA_API_KEY", "")
    if not exa_api_key:
        raise RuntimeError("EXA_API_KEY not set")

    query = f'systematic review "{topic}" PRISMA 2020 PROSPERO site:bmj.com OR site:bmcmedicine.com OR site:pubmed.ncbi.nlm.nih.gov'
    headers = {"x-api-key": exa_api_key, "Content-Type": "application/json"}
    payload = {
        "query": query,
        "numResults": n,
        "type": "neural",
        "useAutoprompt": True,
        "includeDomains": ["bmj.com", "biomedcentral.com", "pubmed.ncbi.nlm.nih.gov"],
        "contents": {"text": {"maxCharacters": 5000}},
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.exa.ai/search", headers=headers, json=payload, timeout=aiohttp.ClientTimeout(total=30)
        ) as resp:
            data = await resp.json()

    results = data.get("results", [])
    papers = []
    for r in results:
        papers.append(
            {
                "source": "exa_web_fetch",
                "title": r.get("title", ""),
                "url": r.get("url", ""),
                "doi": r.get("doi"),
                "abstract": r.get("text", "")[:2000],
                "note": "Web-fetched SR -- add PDF to reference/ and re-run to extract full metrics",
            }
        )
    return papers


async def _fetch_via_perplexity(topic: str, n: int) -> list[dict[str, Any]]:
    """Fetch SRs via Perplexity search."""
    import aiohttp

    api_key = __import__("os").environ.get("PERPLEXITY_API_KEY", "")
    if not api_key:
        raise RuntimeError("PERPLEXITY_API_KEY not set")

    query = (
        f"List {n} recent (2023-2025) high-quality systematic reviews on '{topic}'. "
        "For each: provide title, DOI, journal, year, N included studies, PROSPERO ID if any. "
        "Focus on PRISMA 2020 compliant reviews published in BMC, JAMA, BMJ, Lancet, or Cochrane."
    )

    headers = {"Authorization": f"Bearer {api_key}", "Content-Type": "application/json"}
    payload = {
        "model": "sonar",
        "messages": [{"role": "user", "content": query}],
        "max_tokens": 2000,
    }

    async with aiohttp.ClientSession() as session:
        async with session.post(
            "https://api.perplexity.ai/chat/completions",
            headers=headers,
            json=payload,
            timeout=aiohttp.ClientTimeout(total=45),
        ) as resp:
            data = await resp.json()

    content = data.get("choices", [{}])[0].get("message", {}).get("content", "")
    return [
        {
            "source": "perplexity_web_fetch",
            "raw_content": content,
            "note": "Parse manually and add PDFs to reference/ to extract full structured metrics",
        }
    ]


# ---------------------------------------------------------------------------
# Threshold derivation
# ---------------------------------------------------------------------------


def _safe_min(values: list[Any]) -> Any:
    nums = [v for v in values if isinstance(v, (int, float))]
    return min(nums) if nums else None


def _safe_max(values: list[Any]) -> Any:
    nums = [v for v in values if isinstance(v, (int, float))]
    return max(nums) if nums else None


def _safe_any(values: list[Any]) -> bool:
    return any(bool(v) for v in values)


def derive_thresholds(source_papers: list[dict[str, Any]]) -> dict[str, Any]:
    """Compute derived thresholds from the source_papers list.

    Uses tier_1 papers as primary reference, tier_2 as floor.
    """
    tier1 = [p for p in source_papers if p.get("quality_tier") == "tier_1"]
    all_srs = [p for p in source_papers if p.get("study_type") in ("systematic_review", "scoping_review")]

    def field(papers: list[dict], key: str) -> list[Any]:
        return [p[key] for p in papers if key in p and p[key] is not None]

    pages = field(tier1, "pages")
    n_dbs = field(tier1, "n_databases")
    n_studies = field(tier1, "n_included_studies")
    n_refs = field(tier1, "n_total_references")
    n_tables = field(tier1, "n_tables")
    n_figures = field(tier1, "n_figures")

    all_db_lists = [p.get("databases_searched") or [] for p in tier1]
    common_dbs: list[str] = []
    if all_db_lists:
        first = set(all_db_lists[0])
        for lst in all_db_lists[1:]:
            first &= set(lst)
        common_dbs = sorted(first)

    return {
        "_derivation_note": f"Computed from {len(tier1)} tier_1 source paper(s). Update by running scripts/build_benchmark.py after adding more PDFs to reference/.",
        "pages": {
            "minimum": _safe_min(pages),
            "recommended": _safe_max(pages),
            "source_range": pages,
        },
        "n_databases": {
            "minimum": _safe_min(n_dbs),
            "recommended": _safe_max(n_dbs),
            "minimum_required_databases": common_dbs or ["PubMed", "Scopus", "Web of Science"],
        },
        "n_included_studies": {
            "minimum": _safe_min(n_studies),
            "typical_range": [_safe_min(n_studies), _safe_max(field(all_srs, "n_included_studies"))],
        },
        "n_total_references": {
            "minimum": _safe_min(n_refs),
            "recommended": _safe_max(n_refs),
        },
        "n_tables": {
            "minimum": _safe_min(n_tables),
            "recommended": _safe_max(n_tables),
            "required_tables": ["RoB assessment", "Study characteristics", "Outcome synthesis"],
        },
        "n_figures": {
            "minimum": _safe_min(n_figures),
            "recommended": _safe_max(n_figures),
            "required_figures": ["PRISMA 2020 flow diagram"],
        },
        "prospero_registration": {
            "required": _safe_any(field(tier1, "prospero_registered")),
        },
        "n_independent_reviewers": {
            "minimum": _safe_min(field(tier1, "n_independent_reviewers")),
            "required": True,
        },
        "third_reviewer_conflict_resolution": {
            "required": _safe_any(field(tier1, "third_reviewer_conflict_resolution")),
        },
        "rob_tools": {
            "required": True,
            "must_be_design_specific": _safe_any(field(tier1, "rob_design_specific")),
        },
        "grade": {
            "recommended": _safe_any(field(tier1, "grade_used")),
        },
        "thematic_synthesis_software": {
            "recommended": True,
            "examples": list(
                {p.get("thematic_synthesis_software") for p in tier1 if p.get("thematic_synthesis_software")}
            ),
        },
        "publication_bias_test": {
            "recommended": _safe_any(field(tier1, "publication_bias_test")),
        },
        "theoretical_framework": {
            "recommended": True,
            "examples": [fw for p in tier1 for fw in (p.get("theoretical_framework") or [])],
        },
        "required_manuscript_sections": [
            "Introduction",
            "Methods",
            "Results",
            "Discussion",
            "Conclusion",
            "Author Contributions",
            "Funding Statement",
            "Competing Interests Statement",
            "References",
        ],
        "recommended_manuscript_sections": [
            "PICO table (in Methods)",
            "Limitations subsection",
            "Future Research Directions",
            "Acknowledgements",
            "Supplementary Material",
        ],
        "word_count_body": {
            "minimum": 3500,
            "recommended": 4500,
            "note": "Estimated at ~400 words/page from BMC papers",
        },
    }


# ---------------------------------------------------------------------------
# Report output
# ---------------------------------------------------------------------------


def print_summary_table(source_papers: list[dict[str, Any]]) -> None:
    """Print a rich table summarizing extracted metrics."""
    table = Table(
        title="Benchmark Source Papers",
        box=__import__("rich.box", fromlist=["SIMPLE_HEAVY"]).SIMPLE_HEAVY,
        show_header=True,
    )
    table.add_column("File", style="cyan", no_wrap=True)
    table.add_column("Journal", style="green")
    table.add_column("Yr")
    table.add_column("N DB")
    table.add_column("N Inc")
    table.add_column("N Ref")
    table.add_column("N Tbl")
    table.add_column("N Fig")
    table.add_column("PROSPERO")
    table.add_column("Tier")

    for p in source_papers:
        table.add_row(
            p.get("filename", "")[:35],
            (p.get("journal") or "")[:20],
            str(p.get("year") or ""),
            str(p.get("n_databases") or ""),
            str(p.get("n_included_studies") or ""),
            str(p.get("n_total_references") or ""),
            str(p.get("n_tables") or ""),
            str(p.get("n_figures") or ""),
            "YES" if p.get("prospero_registered") else "no",
            p.get("quality_tier", "?"),
        )

    console.print(table)


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------


async def main(args: argparse.Namespace) -> None:
    load_dotenv()

    if not REFERENCE_DIR.exists():
        console.print("[red]reference/ directory not found. Run from project root.[/red]")
        sys.exit(1)

    # Load existing benchmark to preserve manually-curated source_papers
    existing: dict[str, Any] = {}
    if BENCHMARK_FILE.exists():
        with BENCHMARK_FILE.open("r", encoding="utf-8") as f:
            existing = json.load(f)

    existing_filenames: set[str] = {p.get("filename", "") for p in existing.get("source_papers", [])}

    # Find PDF files in reference/ that are systematic reviews
    pdf_files = sorted(REFERENCE_DIR.glob("*.pdf"))
    if not pdf_files:
        console.print("[yellow]No PDF files found in reference/.[/yellow]")

    console.print(Panel(f"Found {len(pdf_files)} PDF(s) in reference/", title="Build Benchmark"))

    # Extract metrics from each PDF
    new_papers: list[dict[str, Any]] = []
    for pdf_path in pdf_files:
        filename = pdf_path.name
        if filename in existing_filenames and not args.force:
            console.print(f"[dim]Skipping {filename} (already in benchmark). Use --force to re-extract.[/dim]")
            continue

        console.print(f"\n[cyan]Processing:[/cyan] {filename}")
        pdf_text = read_pdf_text(pdf_path)

        if not pdf_text.strip():
            console.print(f"[yellow]  Could not extract text from {filename}, skipping.[/yellow]")
            continue

        word_count = len(pdf_text.split())
        console.print(f"  Extracted {word_count:,} words from PDF")

        if args.dry_run:
            console.print("  [dim](dry-run: skipping LLM extraction)[/dim]")
            continue

        metrics = await extract_metrics_with_llm(pdf_text, filename)
        if "error" not in metrics:
            metrics["quality_tier"] = _determine_quality_tier(metrics)
            console.print(f"  Quality tier: [bold]{metrics['quality_tier']}[/bold]")
            new_papers.append(metrics)
        else:
            console.print(f"  [red]Extraction failed: {metrics.get('error')}[/red]")

    # Merge with existing source_papers (existing ones kept, new ones appended)
    merged_source_papers: list[dict[str, Any]] = list(existing.get("source_papers", []))
    new_filenames = {p.get("filename", "") for p in new_papers}
    # Remove stale entries for files that were re-extracted
    if args.force:
        merged_source_papers = [p for p in merged_source_papers if p.get("filename") not in new_filenames]
    merged_source_papers.extend(new_papers)

    # Fetch from web if requested
    web_papers: list[dict[str, Any]] = []
    if args.fetch_web:
        topic = args.topic or "systematic review healthcare"
        web_papers = await fetch_web_srs(topic, n=3)
        for wp in web_papers:
            console.print(f"  [green]Web:[/green] {wp.get('title', wp.get('url', ''))[:80]}")

    # Derive thresholds
    derived = derive_thresholds(merged_source_papers)

    # Assemble final benchmark
    benchmark: dict[str, Any] = {
        "metadata": {
            "description": "Gold standard benchmark for systematic review manuscript quality. Derived from published peer-reviewed systematic reviews in reference/. Run scripts/build_benchmark.py to update.",
            "last_updated": str(date.today()),
            "source_count": len(merged_source_papers),
            "extensible": True,
            "quality_tiers": {
                "tier_1": "BMC/top-journal Open Access (PROSPERO-registered, multi-tool RoB, NVivo synthesis, Egger's test)",
                "tier_2": "Indexed peer-reviewed journal (PRISMA-compliant, structured, no PROSPERO)",
                "tier_3": "Lower-tier journal (basic structure, limited methods reporting)",
            },
        },
        "source_papers": merged_source_papers,
        "web_sourced_papers": web_papers if web_papers else existing.get("web_sourced_papers", []),
        "non_sr_reference_papers": existing.get("non_sr_reference_papers", []),
        "derived_thresholds": derived,
    }

    if args.dry_run:
        console.print("\n[yellow]Dry run: no file written.[/yellow]")
        console.print(f"Would write {len(merged_source_papers)} source_papers to {BENCHMARK_FILE}")
    else:
        with BENCHMARK_FILE.open("w", encoding="utf-8") as f:
            json.dump(benchmark, f, indent=2, ensure_ascii=False)
        console.print(f"\n[green]Updated:[/green] {BENCHMARK_FILE}")

    # Print summary
    if merged_source_papers:
        print_summary_table(merged_source_papers)
    else:
        console.print("[yellow]No source papers to display.[/yellow]")

    console.print(
        Panel(
            f"Benchmark has [bold]{len(merged_source_papers)}[/bold] source paper(s).\n"
            f"Add more PDFs to reference/ and re-run to extend.\n"
            f"Use [bold]--fetch-web[/bold] to also pull web-sourced SRs.",
            title="Done",
        )
    )


if __name__ == "__main__":
    parser = argparse.ArgumentParser(description="Build/update the gold standard benchmark from reference/ PDFs.")
    parser.add_argument(
        "--fetch-web",
        action="store_true",
        help="Also fetch 2-3 additional SRs from web via Exa/Perplexity",
    )
    parser.add_argument(
        "--topic",
        type=str,
        default=None,
        help="Topic string for web fetch (e.g. 'exercise intervention sleep quality'). Reads config/review.yaml if not set.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Extract PDF text but skip LLM calls and file write",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Re-extract PDFs already present in gold_standard_benchmark.json",
    )
    args = parser.parse_args()

    # If --fetch-web and no --topic, try to read from config/review.yaml
    if args.fetch_web and not args.topic:
        try:
            import yaml

            with open("config/review.yaml") as f:
                review = yaml.safe_load(f)
            args.topic = review.get("topic") or review.get("research_question") or "systematic review healthcare"
        except Exception:
            args.topic = "systematic review healthcare"

    asyncio.run(main(args))
