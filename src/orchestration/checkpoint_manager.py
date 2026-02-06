"""
Checkpoint Manager

Manages workflow checkpoint saving and loading.
"""

import json
from pathlib import Path
from typing import Dict, List, Optional, Any
from datetime import datetime

from ..utils.logging_config import get_logger
from ..utils.state_serialization import StateSerializer

logger = get_logger(__name__)


class CheckpointManager:
    """Manages checkpoint saving and loading for workflow phases."""

    def __init__(self, workflow_manager):
        """
        Initialize checkpoint manager.

        Args:
            workflow_manager: WorkflowManager instance (for accessing state and methods)
        """
        self.workflow_manager = workflow_manager
        self.checkpoint_dir = workflow_manager.checkpoint_dir
        self.save_checkpoints = workflow_manager.save_checkpoints

    def save_phase(self, phase_name: str) -> Optional[str]:
        """
        Save phase checkpoint.

        Args:
            phase_name: Name of the phase to checkpoint

        Returns:
            Path to checkpoint file, or None if saving disabled or failed
        """
        if not self.save_checkpoints:
            return None

        try:
            # Get phase dependencies from registry
            phase = self.workflow_manager.phase_registry.get_phase(phase_name)
            dependencies = phase.dependencies if phase else []

            # Serialize phase data using workflow manager's method
            phase_data = self.workflow_manager._serialize_phase_data(phase_name)

            checkpoint_data = {
                "phase": phase_name,
                "timestamp": datetime.now().isoformat(),
                "workflow_id": self.workflow_manager.workflow_id,
                "topic_context": self.workflow_manager.topic_context.to_dict(),
                "data": phase_data,
                "dependencies": dependencies,
                "prisma_counts": self.workflow_manager.prisma_counter.get_counts(),
                "database_breakdown": self.workflow_manager.prisma_counter.get_database_breakdown(),
            }

            checkpoint_file = self.checkpoint_dir / f"{phase_name}_state.json"
            with open(checkpoint_file, "w") as f:
                json.dump(checkpoint_data, f, indent=2, default=str)

            logger.info(f"Saved checkpoint for phase: {phase_name}")
            return str(checkpoint_file)
        except Exception as e:
            logger.warning(f"Failed to save checkpoint for {phase_name}: {e}")
            return None

    def load_phase(self, checkpoint_path: str) -> Optional[Dict[str, Any]]:
        """
        Load phase checkpoint from file.

        Args:
            checkpoint_path: Path to checkpoint file

        Returns:
            Checkpoint data dictionary, or None if loading failed
        """
        checkpoint_file = Path(checkpoint_path)
        if not checkpoint_file.exists():
            logger.warning(f"Checkpoint file not found: {checkpoint_path}")
            return None

        try:
            with open(checkpoint_file, "r") as f:
                checkpoint_data = json.load(f)
            return checkpoint_data
        except Exception as e:
            logger.error(f"Failed to load checkpoint from {checkpoint_path}: {e}", exc_info=True)
            return None

    def _calculate_checkpoint_completeness(self, workflow_dir: Path, phase_order: List[str]) -> int:
        """
        Calculate checkpoint completeness score for a workflow.

        Args:
            workflow_dir: Path to workflow checkpoint directory
            phase_order: List of phases in order

        Returns:
            Completeness score (higher = more complete)
        """
        checkpoint_files = list(workflow_dir.glob("*_state.json"))
        phase_checkpoints = set()

        for checkpoint_file in checkpoint_files:
            try:
                cp_data = self.load_phase(str(checkpoint_file))
                if not cp_data:
                    continue
                phase = cp_data.get("phase", "")

                # Count phase-level checkpoints (not section-level)
                if phase in phase_order:
                    phase_checkpoints.add(phase)
            except Exception:
                continue

        return len(phase_checkpoints)

    def find_by_topic(self, topic: str) -> Optional[Dict[str, Any]]:
        """
        Find existing checkpoint for the same topic.

        Args:
            topic: Topic to search for

        Returns:
            Dictionary with checkpoint_dir, latest_phase, and workflow_id, or None if not found
        """
        checkpoint_base = Path("data/checkpoints")
        if not checkpoint_base.exists():
            logger.debug("Checkpoint directory does not exist")
            return None

        current_topic = topic.lower().strip()
        logger.debug(f"Looking for checkpoints matching topic: '{current_topic}'")

        workflow_dirs = [d for d in checkpoint_base.iterdir() if d.is_dir()]
        logger.debug(f"Found {len(workflow_dirs)} workflow directories to check")

        # Phase priority order (higher index = more progress)
        phase_order = [
            "search_databases",
            "deduplication",
            "title_abstract_screening",
            "fulltext_screening",
            "paper_enrichment",
            "data_extraction",
            "quality_assessment",
            "prisma_generation",
            "visualization_generation",
            "article_writing",
            "report_generation",
            "manubot_export",
            "submission_package",
        ]

        # Collect all matching directories
        matches = []

        # Look through all workflow directories
        for workflow_dir in workflow_dirs:
            # Check if this workflow matches our topic
            # Look for any checkpoint file to read topic_context
            checkpoint_files = list(workflow_dir.glob("*_state.json"))
            if not checkpoint_files:
                logger.debug(f"No checkpoint files found in {workflow_dir.name}")
                continue

            logger.debug(f"Checking workflow {workflow_dir.name} ({len(checkpoint_files)} checkpoint files)")

            # Try to find the latest checkpoint and check its topic
            latest_checkpoint = max(checkpoint_files, key=lambda p: p.stat().st_mtime)

            try:
                checkpoint_data = self.load_phase(str(latest_checkpoint))
                if not checkpoint_data:
                    continue

                # Check if topic matches
                checkpoint_topic = checkpoint_data.get("topic_context", {}).get("topic", "").lower().strip()
                logger.debug(f"  Checkpoint topic: '{checkpoint_topic}'")

                if checkpoint_topic == current_topic:
                    logger.info(f"  Topic match found in workflow {workflow_dir.name}!")
                    # Find the latest phase checkpoint (check all possible phases)
                    latest_phase = None
                    latest_phase_time = 0
                    article_sections_count = 0

                    for checkpoint_file in checkpoint_files:
                        try:
                            cp_data = self.load_phase(str(checkpoint_file))
                            if not cp_data:
                                continue
                            phase = cp_data.get("phase", "")

                            # Count article writing sections
                            if phase.startswith("article_writing_"):
                                article_sections_count += 1
                                # If we have article sections, consider this as article_writing phase
                                if latest_phase != "article_writing":
                                    latest_phase = "article_writing"
                                    latest_phase_time = checkpoint_file.stat().st_mtime
                                else:
                                    # Update time if this section is newer
                                    mtime = checkpoint_file.stat().st_mtime
                                    if mtime > latest_phase_time:
                                        latest_phase_time = mtime
                            elif phase in phase_order:
                                mtime = checkpoint_file.stat().st_mtime
                                if mtime > latest_phase_time:
                                    latest_phase_time = mtime
                                    latest_phase = phase
                        except Exception as e:
                            logger.debug(f"Error reading checkpoint file {checkpoint_file}: {e}")
                            continue

                    if latest_phase:
                        # Calculate completeness score
                        completeness = self._calculate_checkpoint_completeness(workflow_dir, phase_order)
                        logger.info(f"  Latest phase found: {latest_phase} (article sections: {article_sections_count}, completeness: {completeness})")
                        phase_index = phase_order.index(latest_phase) if latest_phase in phase_order else -1
                        matches.append({
                            "checkpoint_dir": str(workflow_dir),
                            "latest_phase": latest_phase,
                            "latest_phase_time": latest_phase_time,
                            "workflow_id": workflow_dir.name,
                            "phase_index": phase_index,
                            "article_sections_count": article_sections_count,
                            "completeness": completeness,
                        })
                else:
                    logger.debug(f"  Topic mismatch: '{checkpoint_topic}' != '{current_topic}'")
            except Exception as e:
                logger.debug(f"Error checking checkpoint {latest_checkpoint}: {e}")
                continue

        # Select the best match: completeness first (prefer complete chains),
        # then highest phase_index, then most article sections, then most recent time
        if matches:
            best_match = max(
                matches,
                key=lambda m: (
                    m["completeness"],
                    m["phase_index"],
                    m["article_sections_count"],
                    m["latest_phase_time"]
                )
            )
            logger.info(f"Selected best checkpoint: {best_match['workflow_id']} (phase: {best_match['latest_phase']}, completeness: {best_match['completeness']}, article sections: {best_match['article_sections_count']})")
            return {
                "checkpoint_dir": best_match["checkpoint_dir"],
                "latest_phase": best_match["latest_phase"],
                "workflow_id": best_match["workflow_id"],
            }

        logger.debug("No matching checkpoint found for this topic")
        return None

    def load_checkpoint_chain(
        self,
        checkpoint_dir: Path,
        phases_to_load: List[str],
        phase_dependencies: Dict[str, List[str]]
    ) -> Dict[str, Any]:
        """
        Load a chain of checkpoints in dependency order.

        Args:
            checkpoint_dir: Directory containing checkpoints
            phases_to_load: List of phase names to load
            phase_dependencies: Dictionary mapping phase names to their dependencies

        Returns:
            Accumulated state dictionary
        """
        StateSerializer()
        accumulated_state = {"data": {}}
        loaded_phases = []

        for phase in phases_to_load:
            checkpoint_file = checkpoint_dir / f"{phase}_state.json"
            if not checkpoint_file.exists():
                logger.debug(f"Missing checkpoint: {phase} (will skip, may use data from later phases)")
                continue

            logger.debug(f"Found checkpoint: {phase}")
            try:
                checkpoint_data = self.load_phase(str(checkpoint_file))
                if not checkpoint_data:
                    continue

                # Merge checkpoint data into accumulated state
                if "data" in checkpoint_data:
                    data_keys = list(checkpoint_data["data"].keys())
                    logger.debug(f"  Merging data keys from {phase}: {data_keys}")
                    for key, value in checkpoint_data["data"].items():
                        accumulated_state["data"][key] = value

                # Merge other top-level keys (use latest phase's values)
                for key in ["prisma_counts", "database_breakdown", "topic_context", "workflow_id"]:
                    if key in checkpoint_data:
                        accumulated_state[key] = checkpoint_data[key]

                loaded_phases.append(phase)
                logger.info(f"Loaded checkpoint data from: {phase}")
            except Exception as e:
                logger.error(f"Failed to load checkpoint file {phase}: {e}", exc_info=True)
                continue

        if not loaded_phases:
            logger.error("Failed to load any checkpoints!")
            return {}

        logger.info(f"Successfully loaded {len(loaded_phases)} checkpoint(s) out of {len(phases_to_load)} attempted: {', '.join(loaded_phases)}")
        if len(loaded_phases) < len(phases_to_load):
            missing = set(phases_to_load) - set(loaded_phases)
            logger.warning(f"Missing checkpoints (will use available data): {', '.join(missing)}")

        return accumulated_state
