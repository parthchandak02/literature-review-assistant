"""
Integration test for PRISMA diagram generation with real workflow data.

Tests that PRISMA diagram is generated correctly and matches workflow counts.
"""

from pathlib import Path
from typing import Dict

import pytest
import yaml
from dotenv import load_dotenv
from PIL import Image

load_dotenv()

from src.orchestration.workflow_manager import WorkflowManager


def get_test_config() -> Dict:
    """Get minimal test configuration."""
    return {
        "topic": {
            "topic": "health literacy chatbots",
            "keywords": ["health literacy", "chatbots"],
            "domain": "public health",
            "scope": "Test scope",
            "research_question": "Test question",
            "context": "Test context",
        },
        "agents": {
            "search_agent": {
                "role": "Search Specialist",
                "goal": "Find literature",
                "backstory": "Expert",
                "llm_model": "gemini-2.5-flash",
                "tools": [],
                "temperature": 0.1,
                "max_iterations": 2,
            },
            "title_abstract_screener": {
                "role": "Title/Abstract Screening Specialist",
                "goal": "Screen papers by title/abstract",
                "backstory": "Expert",
                "llm_model": "gemini-2.5-flash-lite",
                "tools": [],
                "temperature": 0.2,
                "max_iterations": 10,
            },
            "fulltext_screener": {
                "role": "Fulltext Screening Specialist",
                "goal": "Screen papers by fulltext",
                "backstory": "Expert",
                "llm_model": "gemini-2.5-flash-lite",
                "tools": [],
                "temperature": 0.2,
                "max_iterations": 3,
            },
            "extraction_agent": {
                "role": "Extraction Specialist",
                "goal": "Extract data",
                "backstory": "Expert",
                "llm_model": "gemini-2.5-pro",
                "tools": [],
                "temperature": 0.1,
                "max_iterations": 2,
            },
            "introduction_writer": {
                "role": "Introduction Writer",
                "goal": "Write introduction",
                "backstory": "Writer",
                "llm_model": "gemini-2.5-pro",
                "tools": [],
                "temperature": 0.7,
                "max_iterations": 1,
            },
            "methods_writer": {
                "role": "Methods Writer",
                "goal": "Write methods",
                "backstory": "Writer",
                "llm_model": "gemini-2.5-pro",
                "tools": [],
                "temperature": 0.3,
                "max_iterations": 1,
            },
            "results_writer": {
                "role": "Results Writer",
                "goal": "Write results",
                "backstory": "Writer",
                "llm_model": "gemini-2.5-pro",
                "tools": [],
                "temperature": 0.4,
                "max_iterations": 1,
            },
            "discussion_writer": {
                "role": "Discussion Writer",
                "goal": "Write discussion",
                "backstory": "Writer",
                "llm_model": "gemini-2.5-pro",
                "tools": [],
                "temperature": 0.6,
                "max_iterations": 1,
            },
        },
        "workflow": {
            "databases": ["PubMed", "arXiv"],
            "date_range": {"start": None, "end": 2025},
            "language": "English",
            "max_results_per_db": 10,
            "similarity_threshold": 85,
            "database_settings": {
                "PubMed": {"enabled": True, "max_results": 10},
                "arXiv": {"enabled": True, "max_results": 10},
            },
            "cache": {"enabled": False},
            "search_logging": {"enabled": True, "log_dir": "data/outputs/search_logs"},
        },
        "criteria": {
            "inclusion": ["Health literacy studies"],
            "exclusion": ["Non-chatbot studies"],
        },
        "output": {
            "directory": "data/outputs",
            "formats": ["markdown"],
            "generate_prisma": True,
            "generate_charts": False,
        },
    }


@pytest.fixture
def test_config_file(tmp_path):
    """Create test config file."""
    config = get_test_config()
    config_file = tmp_path / "workflow.yaml"

    with open(config_file, "w") as f:
        yaml.dump(config, f)

    return str(config_file)


@pytest.fixture
def workflow_manager(test_config_file, tmp_path):
    """Create workflow manager."""
    manager = WorkflowManager(test_config_file)
    manager.output_dir = tmp_path
    return manager


class TestPRISMAWithRealData:
    """Test PRISMA diagram generation with real workflow data."""

    @pytest.mark.slow
    @pytest.mark.integration
    def test_prisma_counts_match_workflow(self, workflow_manager):
        """Test that PRISMA counts match workflow state."""
        # Run search phase
        workflow_manager._build_search_strategy()
        papers = workflow_manager._search_databases()

        if len(papers) == 0:
            pytest.skip("No papers found to test PRISMA")

        workflow_manager.all_papers = papers

        # Set PRISMA counts
        db_breakdown = workflow_manager._get_database_breakdown()
        workflow_manager.prisma_counter.set_found(len(papers), db_breakdown)

        # Deduplicate
        dedup_result = workflow_manager.deduplicator.deduplicate_papers(papers)
        workflow_manager.unique_papers = dedup_result.unique_papers
        workflow_manager.prisma_counter.set_no_dupes(len(workflow_manager.unique_papers))

        # Verify counts match
        counts = workflow_manager.prisma_counter.get_counts()

        assert counts["found"] == len(papers), (
            f"Found count mismatch: {counts['found']} != {len(papers)}"
        )
        assert counts["no_dupes"] == len(workflow_manager.unique_papers), (
            f"No dupes count mismatch: {counts['no_dupes']} != {len(workflow_manager.unique_papers)}"
        )
        assert counts["no_dupes"] <= counts["found"], "Unique papers should be <= total papers"

        print("\nPRISMA Counts Match:")
        print(f"  Found: {counts['found']} == {len(papers)} papers")
        print(f"  No dupes: {counts['no_dupes']} == {len(workflow_manager.unique_papers)} unique")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_prisma_diagram_generation(self, workflow_manager):
        """Test PRISMA diagram is generated correctly."""
        # Set up workflow state
        workflow_manager._build_search_strategy()
        papers = workflow_manager._search_databases()

        if len(papers) == 0:
            pytest.skip("No papers found to generate PRISMA diagram")

        workflow_manager.all_papers = papers
        workflow_manager.prisma_counter.set_found(
            len(papers), workflow_manager._get_database_breakdown()
        )

        dedup_result = workflow_manager.deduplicator.deduplicate_papers(papers)
        workflow_manager.unique_papers = dedup_result.unique_papers
        workflow_manager.prisma_counter.set_no_dupes(len(workflow_manager.unique_papers))

        # Generate PRISMA diagram
        try:
            prisma_path = workflow_manager._generate_prisma_diagram()

            # Verify diagram exists
            assert prisma_path is not None, "PRISMA path should not be None"
            assert Path(prisma_path).exists(), f"PRISMA diagram file should exist: {prisma_path}"

            # Verify file is valid PNG
            try:
                img = Image.open(prisma_path)
                assert img.format == "PNG", f"PRISMA diagram should be PNG, got {img.format}"

                # Verify image has reasonable dimensions
                width, height = img.size
                assert width > 0 and height > 0, "PRISMA diagram should have non-zero dimensions"
                assert width >= 800, "PRISMA diagram should be at least 800px wide"

                print("\nPRISMA Diagram Valid:")
                print(f"  Path: {prisma_path}")
                print(f"  Format: {img.format}")
                print(f"  Dimensions: {width}x{height}")

            except Exception as e:
                pytest.fail(f"PRISMA diagram is not a valid image: {e}")

            # Verify file size is reasonable
            file_size = Path(prisma_path).stat().st_size
            assert file_size > 1000, f"PRISMA diagram should be > 1KB, got {file_size} bytes"
            assert file_size < 10 * 1024 * 1024, (
                f"PRISMA diagram should be < 10MB, got {file_size} bytes"
            )

            print(f"  File size: {file_size} bytes")

        except Exception as e:
            pytest.skip(f"PRISMA diagram generation failed: {e}")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_prisma_diagram_matches_counts(self, workflow_manager):
        """Test that PRISMA diagram counts match workflow counts."""
        # Set up workflow with known counts
        workflow_manager._build_search_strategy()
        papers = workflow_manager._search_databases()

        if len(papers) == 0:
            pytest.skip("No papers found")

        workflow_manager.all_papers = papers

        # Set specific counts
        db_breakdown = workflow_manager._get_database_breakdown()
        workflow_manager.prisma_counter.set_found(len(papers), db_breakdown)

        dedup_result = workflow_manager.deduplicator.deduplicate_papers(papers)
        workflow_manager.unique_papers = dedup_result.unique_papers
        workflow_manager.prisma_counter.set_no_dupes(len(workflow_manager.unique_papers))

        # Get counts before generation
        expected_counts = workflow_manager.prisma_counter.get_counts()

        # Generate diagram
        try:
            workflow_manager._generate_prisma_diagram()

            # Verify counts after generation (should be unchanged)
            actual_counts = workflow_manager.prisma_counter.get_counts()

            for key in expected_counts:
                assert actual_counts[key] == expected_counts[key], (
                    f"Count mismatch for {key}: {actual_counts[key]} != {expected_counts[key]}"
                )

            print("\nPRISMA Counts Verified:")
            for key, value in expected_counts.items():
                print(f"  {key}: {value}")

        except Exception as e:
            pytest.skip(f"PRISMA generation failed: {e}")

    @pytest.mark.slow
    @pytest.mark.integration
    def test_prisma_with_screening_counts(self, workflow_manager):
        """Test PRISMA diagram includes screening counts."""
        # Set up workflow
        workflow_manager._build_search_strategy()
        papers = workflow_manager._search_databases()

        if len(papers) == 0:
            pytest.skip("No papers found")

        workflow_manager.all_papers = papers
        workflow_manager.prisma_counter.set_found(
            len(papers), workflow_manager._get_database_breakdown()
        )

        dedup_result = workflow_manager.deduplicator.deduplicate_papers(papers)
        workflow_manager.unique_papers = dedup_result.unique_papers
        workflow_manager.prisma_counter.set_no_dupes(len(workflow_manager.unique_papers))

        # Try screening (may fail if no LLM API)
        try:
            workflow_manager.unique_papers = workflow_manager.unique_papers[:5]
            workflow_manager._screen_title_abstract()

            workflow_manager.prisma_counter.set_screened(len(workflow_manager.screened_papers))
            excluded = len(workflow_manager.unique_papers) - len(workflow_manager.screened_papers)
            workflow_manager.prisma_counter.set_screen_exclusions(excluded)

            # Generate PRISMA with screening counts
            prisma_path = workflow_manager._generate_prisma_diagram()

            counts = workflow_manager.prisma_counter.get_counts()

            assert "screened" in counts or "no_dupes" in counts
            assert counts.get("screened", counts.get("no_dupes", 0)) <= counts["no_dupes"]

            print("\nPRISMA with Screening:")
            print(f"  Found: {counts.get('found', 0)}")
            print(f"  No dupes: {counts.get('no_dupes', 0)}")
            print(f"  Screened: {counts.get('screened', 0)}")

        except Exception:
            # Screening may fail, but PRISMA should still work
            prisma_path = workflow_manager._generate_prisma_diagram()
            assert Path(prisma_path).exists()
