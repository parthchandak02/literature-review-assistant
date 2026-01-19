"""
Stage Loader

Load stage data from checkpoints or test fixtures.
"""

import json
from pathlib import Path
from typing import Dict, Any, Optional
import logging

logger = logging.getLogger(__name__)


class StageLoader:
    """Load stage data from checkpoints or test fixtures."""

    def __init__(self, fixtures_dir: Optional[str] = None):
        """
        Initialize stage loader.
        
        Args:
            fixtures_dir: Directory containing test fixtures (default: tests/fixtures/stages)
        """
        if fixtures_dir:
            self.fixtures_dir = Path(fixtures_dir)
        else:
            self.fixtures_dir = Path("tests/fixtures/stages")
        self.fixtures_dir.mkdir(parents=True, exist_ok=True)

    def load_stage_data(
        self,
        source: str,
        stage_name: str,
        checkpoint_path: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Load data from checkpoint or fixture.
        
        Args:
            source: "checkpoint" or "fixture"
            stage_name: Stage name (e.g., "title_abstract_screening")
            checkpoint_path: Path to checkpoint file or directory (required if source="checkpoint")
        
        Returns:
            Dictionary containing stage data
        """
        if source == "checkpoint":
            if not checkpoint_path:
                raise ValueError("checkpoint_path required when source='checkpoint'")
            return self._load_from_checkpoint(checkpoint_path, stage_name)
        elif source == "fixture":
            return self._load_from_fixture(stage_name)
        else:
            raise ValueError(f"Unknown source: {source}. Must be 'checkpoint' or 'fixture'")

    def _load_from_checkpoint(
        self,
        checkpoint_path: str,
        stage_name: Optional[str] = None,
    ) -> Dict[str, Any]:
        """
        Load from checkpoint file.
        
        Args:
            checkpoint_path: Path to checkpoint file or directory
            stage_name: Stage name (required if checkpoint_path is a directory)
        
        Returns:
            Checkpoint data dictionary
        """
        checkpoint_file = Path(checkpoint_path)
        
        # If directory provided, look for stage-specific checkpoint
        if checkpoint_file.is_dir():
            if not stage_name:
                raise ValueError("stage_name required when checkpoint_path is a directory")
            checkpoint_file = checkpoint_file / f"{stage_name}_state.json"
        
        if not checkpoint_file.exists():
            raise FileNotFoundError(f"Checkpoint not found: {checkpoint_file}")
        
        try:
            with open(checkpoint_file, "r") as f:
                data = json.load(f)
            logger.info(f"Loaded checkpoint from: {checkpoint_file}")
            return data
        except Exception as e:
            logger.error(f"Failed to load checkpoint: {e}")
            raise

    def _load_from_fixture(self, stage_name: str) -> Dict[str, Any]:
        """
        Load from test fixture JSON.
        
        Args:
            stage_name: Stage name (e.g., "title_abstract_screening")
        
        Returns:
            Fixture data dictionary
        """
        # Map stage names to fixture file names
        stage_to_fixture = {
            "search_databases": "stage_01_search_results.json",
            "deduplication": "stage_02_deduplicated.json",
            "title_abstract_screening": "stage_03_title_screened.json",
            "fulltext_screening": "stage_04_fulltext_screened.json",
            "data_extraction": "stage_05_extracted_data.json",
            "article_writing": "stage_06_article_sections.json",
            "visualization_generation": "stage_07_visualizations.json",
        }
        
        fixture_file = self.fixtures_dir / stage_to_fixture.get(
            stage_name, f"{stage_name}.json"
        )
        
        if not fixture_file.exists():
            raise FileNotFoundError(
                f"Fixture not found: {fixture_file}. "
                f"Create it or use a checkpoint instead."
            )
        
        try:
            with open(fixture_file, "r") as f:
                data = json.load(f)
            logger.info(f"Loaded fixture from: {fixture_file}")
            return data
        except Exception as e:
            logger.error(f"Failed to load fixture: {e}")
            raise

    def list_available_checkpoints(self, checkpoint_dir: str) -> list:
        """
        List available checkpoint files in a directory.
        
        Args:
            checkpoint_dir: Directory containing checkpoints
        
        Returns:
            List of checkpoint file paths
        """
        checkpoint_path = Path(checkpoint_dir)
        if not checkpoint_path.exists():
            return []
        
        checkpoints = []
        for file in checkpoint_path.glob("*_state.json"):
            checkpoints.append(str(file))
        
        return sorted(checkpoints)

    def list_available_fixtures(self) -> list:
        """
        List available fixture files.
        
        Returns:
            List of fixture file paths
        """
        fixtures = []
        for file in self.fixtures_dir.glob("*.json"):
            fixtures.append(str(file))
        
        return sorted(fixtures)
