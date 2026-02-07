"""
Workflow Folder Cleanup Utility

Manages cleanup of old workflow checkpoint and output folders.
"""

import re
import shutil
from pathlib import Path
from typing import Dict, List, Optional, Tuple
from dataclasses import dataclass
from datetime import datetime

from .logging_config import get_logger

logger = get_logger(__name__)


@dataclass
class WorkflowFolder:
    """Represents a workflow folder with parsed metadata."""

    path: Path
    topic: str
    timestamp: str
    folder_type: str  # "checkpoint" or "output"
    size_bytes: int

    @property
    def size_mb(self) -> float:
        """Return size in megabytes."""
        return self.size_bytes / (1024 * 1024)

    @property
    def datetime(self) -> datetime:
        """Parse timestamp into datetime object."""
        return datetime.strptime(self.timestamp, "%Y%m%d_%H%M%S")


@dataclass
class CleanupReport:
    """Report of cleanup operation results."""

    topics_processed: int
    folders_deleted: int
    checkpoint_folders_deleted: int
    output_folders_deleted: int
    space_freed_bytes: int
    errors: List[str]
    warnings: List[str]
    topic_details: Dict[str, Dict]
    dry_run: bool

    @property
    def space_freed_mb(self) -> float:
        """Return space freed in megabytes."""
        return self.space_freed_bytes / (1024 * 1024)

    def __str__(self) -> str:
        """Format cleanup report for display."""
        lines = []
        lines.append("=" * 70)
        lines.append("Workflow Folder Cleanup Report")
        lines.append("=" * 70)
        lines.append("")

        if self.dry_run:
            lines.append("[DRY RUN MODE - No files will be deleted]")
            lines.append("")

        # Per-topic details
        for topic, details in self.topic_details.items():
            lines.append(f"Topic: {topic}")
            lines.append(f"  Latest folder: {details['latest_folder']}")
            lines.append(f"  Folders to delete: {details['folders_to_delete']}")
            lines.append(f"  Space to free: {details['space_to_free_mb']:.1f} MB")

            if details["checkpoint_folders"]:
                lines.append(f"  Checkpoint folders ({len(details['checkpoint_folders'])}):")
                # Show first 3
                for folder in details["checkpoint_folders"][:3]:
                    lines.append(f"    - {folder['name']} ({folder['size_mb']:.1f} MB)")
                if len(details["checkpoint_folders"]) > 3:
                    lines.append(f"    ... ({len(details['checkpoint_folders']) - 3} more)")

            if details["output_folders"]:
                lines.append(f"  Output folders ({len(details['output_folders'])}):")
                # Show first 3
                for folder in details["output_folders"][:3]:
                    lines.append(f"    - {folder['name']} ({folder['size_mb']:.1f} MB)")
                if len(details["output_folders"]) > 3:
                    lines.append(f"    ... ({len(details['output_folders']) - 3} more)")

            lines.append("")

        # Summary
        lines.append("=" * 70)
        lines.append(f"Total Topics: {self.topics_processed}")
        lines.append(
            f"Total Folders to Delete: {self.folders_deleted} "
            f"({self.checkpoint_folders_deleted} checkpoints + "
            f"{self.output_folders_deleted} outputs)"
        )
        lines.append(f"Total Space to Free: {self.space_freed_mb:.1f} MB")

        if self.warnings:
            lines.append("")
            lines.append(f"Warnings ({len(self.warnings)}):")
            for warning in self.warnings:
                lines.append(f"  - {warning}")

        if self.errors:
            lines.append("")
            lines.append(f"Errors ({len(self.errors)}):")
            for error in self.errors:
                lines.append(f"  - {error}")

        lines.append("=" * 70)

        if self.dry_run:
            lines.append("")
            lines.append("Run without --dry-run to perform actual deletion.")
        else:
            lines.append("")
            lines.append("Cleanup completed successfully!")

        return "\n".join(lines)


class WorkflowCleaner:
    """Manages cleanup of old workflow folders."""

    # Pattern for workflow folder names
    WORKFLOW_PATTERN = re.compile(r"^workflow_(.+)_(\d{8}_\d{6})$")

    def __init__(self, checkpoint_dir: Optional[Path] = None, output_dir: Optional[Path] = None):
        """
        Initialize workflow cleaner.

        Args:
            checkpoint_dir: Path to checkpoint directory (default: data/checkpoints)
            output_dir: Path to output directory (default: data/outputs)
        """
        self.checkpoint_dir = checkpoint_dir or Path("data/checkpoints")
        self.output_dir = output_dir or Path("data/outputs")

    def parse_folder_name(self, folder_name: str) -> Optional[Tuple[str, str]]:
        """
        Parse workflow folder name to extract topic and timestamp.

        Args:
            folder_name: Name of the folder (e.g., "workflow_topic_20260120_144424")

        Returns:
            Tuple of (topic, timestamp) or None if parsing fails
        """
        match = self.WORKFLOW_PATTERN.match(folder_name)
        if match:
            topic = match.group(1)
            timestamp = match.group(2)
            return (topic, timestamp)
        return None

    def get_folder_size(self, folder_path: Path) -> int:
        """
        Calculate total size of a folder in bytes.

        Args:
            folder_path: Path to the folder

        Returns:
            Total size in bytes
        """
        total_size = 0
        try:
            for item in folder_path.rglob("*"):
                if item.is_file():
                    total_size += item.stat().st_size
        except Exception as e:
            logger.warning(f"Error calculating size for {folder_path}: {e}")
        return total_size

    def scan_workflow_folders(self, base_dir: Path, folder_type: str) -> List[WorkflowFolder]:
        """
        Scan a directory for workflow folders.

        Args:
            base_dir: Directory to scan
            folder_type: Type of folders ("checkpoint" or "output")

        Returns:
            List of WorkflowFolder objects
        """
        folders = []

        if not base_dir.exists():
            logger.warning(f"Directory does not exist: {base_dir}")
            return folders

        for item in base_dir.iterdir():
            if not item.is_dir():
                continue

            # Parse folder name
            parsed = self.parse_folder_name(item.name)
            if not parsed:
                logger.debug(f"Skipping non-workflow folder: {item.name}")
                continue

            topic, timestamp = parsed
            size = self.get_folder_size(item)

            folder = WorkflowFolder(
                path=item,
                topic=topic,
                timestamp=timestamp,
                folder_type=folder_type,
                size_bytes=size,
            )
            folders.append(folder)
            logger.debug(f"Found {folder_type} folder: {item.name} ({folder.size_mb:.1f} MB)")

        return folders

    def group_by_topic(self, folders: List[WorkflowFolder]) -> Dict[str, List[WorkflowFolder]]:
        """
        Group workflow folders by topic.

        Args:
            folders: List of WorkflowFolder objects

        Returns:
            Dictionary mapping topic to list of folders
        """
        grouped = {}
        for folder in folders:
            if folder.topic not in grouped:
                grouped[folder.topic] = []
            grouped[folder.topic].append(folder)

        # Sort each topic's folders by timestamp (newest first)
        for topic in grouped:
            grouped[topic].sort(key=lambda f: f.datetime, reverse=True)

        return grouped

    def identify_deletable_folders(
        self, topic: str, folders: List[WorkflowFolder], keep_n: int = 1
    ) -> List[WorkflowFolder]:
        """
        Identify which folders should be deleted for a topic.

        Args:
            topic: Topic name
            folders: List of folders for this topic (should be sorted by timestamp)
            keep_n: Number of most recent folders to keep

        Returns:
            List of folders to delete
        """
        if len(folders) <= keep_n:
            logger.debug(f"Topic '{topic}': {len(folders)} folders, keeping all (keep_n={keep_n})")
            return []

        # Keep the first keep_n folders (most recent), delete the rest
        to_keep = folders[:keep_n]
        to_delete = folders[keep_n:]

        logger.info(
            f"Topic '{topic}': Keeping {len(to_keep)} folders, deleting {len(to_delete)} folders"
        )
        return to_delete

    def delete_folder(self, folder: WorkflowFolder, dry_run: bool = False) -> bool:
        """
        Delete a workflow folder.

        Args:
            folder: WorkflowFolder to delete
            dry_run: If True, don't actually delete

        Returns:
            True if successful (or dry_run), False otherwise
        """
        try:
            if dry_run:
                logger.info(f"[DRY RUN] Would delete: {folder.path}")
                return True

            logger.info(f"Deleting {folder.folder_type} folder: {folder.path}")
            shutil.rmtree(folder.path)
            return True
        except Exception as e:
            logger.error(f"Failed to delete {folder.path}: {e}")
            return False

    def cleanup(
        self, dry_run: bool = False, topic_filter: Optional[str] = None, keep_n: int = 1
    ) -> CleanupReport:
        """
        Perform cleanup of old workflow folders.

        Args:
            dry_run: If True, preview without deleting
            topic_filter: If provided, only clean this topic
            keep_n: Number of most recent folders to keep per topic

        Returns:
            CleanupReport with results
        """
        logger.info("=" * 60)
        logger.info(
            f"Starting workflow cleanup (dry_run={dry_run}, topic_filter={topic_filter}, keep_n={keep_n})"
        )
        logger.info("=" * 60)

        errors = []
        warnings = []
        topic_details = {}

        # Scan both directories
        checkpoint_folders = self.scan_workflow_folders(self.checkpoint_dir, "checkpoint")
        output_folders = self.scan_workflow_folders(self.output_dir, "output")

        # Combine and group by topic
        all_folders = checkpoint_folders + output_folders
        grouped = self.group_by_topic(all_folders)

        logger.info(f"Found {len(grouped)} unique topics with workflow folders")

        # Filter by topic if requested
        if topic_filter:
            if topic_filter in grouped:
                grouped = {topic_filter: grouped[topic_filter]}
                logger.info(f"Filtering to topic: {topic_filter}")
            else:
                logger.warning(f"Topic '{topic_filter}' not found in workflow folders")
                warnings.append(f"Topic '{topic_filter}' not found")
                grouped = {}

        # Process each topic
        total_deleted = 0
        checkpoint_deleted = 0
        output_deleted = 0
        space_freed = 0

        for topic, folders in grouped.items():
            logger.info(f"\nProcessing topic: {topic}")
            logger.info(f"  Total folders: {len(folders)}")

            # Separate by type
            topic_checkpoints = [f for f in folders if f.folder_type == "checkpoint"]
            topic_outputs = [f for f in folders if f.folder_type == "output"]

            # Sort by timestamp (newest first)
            topic_checkpoints.sort(key=lambda f: f.datetime, reverse=True)
            topic_outputs.sort(key=lambda f: f.datetime, reverse=True)

            # Identify latest folder name
            latest_folder = folders[0].path.name if folders else "N/A"

            # Identify deletable folders
            deletable_checkpoints = self.identify_deletable_folders(
                topic, topic_checkpoints, keep_n
            )
            deletable_outputs = self.identify_deletable_folders(topic, topic_outputs, keep_n)

            # Calculate space to free
            space_to_free = sum(f.size_bytes for f in deletable_checkpoints + deletable_outputs)

            # Store topic details
            topic_details[topic] = {
                "latest_folder": latest_folder,
                "folders_to_delete": len(deletable_checkpoints) + len(deletable_outputs),
                "space_to_free_mb": space_to_free / (1024 * 1024),
                "checkpoint_folders": [
                    {"name": f.path.name, "size_mb": f.size_mb} for f in deletable_checkpoints
                ],
                "output_folders": [
                    {"name": f.path.name, "size_mb": f.size_mb} for f in deletable_outputs
                ],
            }

            # Delete folders
            for folder in deletable_checkpoints + deletable_outputs:
                success = self.delete_folder(folder, dry_run)
                if success:
                    total_deleted += 1
                    space_freed += folder.size_bytes
                    if folder.folder_type == "checkpoint":
                        checkpoint_deleted += 1
                    else:
                        output_deleted += 1
                else:
                    errors.append(f"Failed to delete: {folder.path}")

        # Create report
        report = CleanupReport(
            topics_processed=len(grouped),
            folders_deleted=total_deleted,
            checkpoint_folders_deleted=checkpoint_deleted,
            output_folders_deleted=output_deleted,
            space_freed_bytes=space_freed,
            errors=errors,
            warnings=warnings,
            topic_details=topic_details,
            dry_run=dry_run,
        )

        logger.info("")
        logger.info("=" * 60)
        logger.info(f"Cleanup {'preview' if dry_run else 'completed'}")
        logger.info(f"  Topics processed: {report.topics_processed}")
        logger.info(f"  Folders deleted: {report.folders_deleted}")
        logger.info(f"  Space freed: {report.space_freed_mb:.1f} MB")
        logger.info("=" * 60)

        return report
