"""
Unit tests for workflow_cleaner module.
"""

import pytest
from pathlib import Path
from datetime import datetime
import tempfile
import shutil

from src.utils.workflow_cleaner import WorkflowCleaner, WorkflowFolder, CleanupReport


class TestWorkflowCleaner:
    """Test WorkflowCleaner class."""
    
    @pytest.fixture
    def cleaner(self):
        """Create a WorkflowCleaner instance."""
        return WorkflowCleaner()
    
    @pytest.fixture
    def temp_dirs(self):
        """Create temporary checkpoint and output directories."""
        checkpoint_dir = Path(tempfile.mkdtemp())
        output_dir = Path(tempfile.mkdtemp())
        
        yield checkpoint_dir, output_dir
        
        # Cleanup
        shutil.rmtree(checkpoint_dir, ignore_errors=True)
        shutil.rmtree(output_dir, ignore_errors=True)
    
    def test_parse_folder_name_valid(self, cleaner):
        """Test parsing valid workflow folder names."""
        # Standard format
        result = cleaner.parse_folder_name("workflow_my_topic_20260120_144424")
        assert result is not None
        assert result[0] == "my_topic"
        assert result[1] == "20260120_144424"
        
        # Topic with underscores
        result = cleaner.parse_folder_name("workflow_financial_trading_system_integ_20260122_163807")
        assert result is not None
        assert result[0] == "financial_trading_system_integ"
        assert result[1] == "20260122_163807"
    
    def test_parse_folder_name_invalid(self, cleaner):
        """Test parsing invalid folder names."""
        # Missing workflow prefix
        assert cleaner.parse_folder_name("my_topic_20260120_144424") is None
        
        # Missing timestamp
        assert cleaner.parse_folder_name("workflow_my_topic") is None
        
        # Invalid timestamp format
        assert cleaner.parse_folder_name("workflow_my_topic_2026") is None
        assert cleaner.parse_folder_name("workflow_my_topic_20260120") is None
        
        # Random folder name
        assert cleaner.parse_folder_name("random_folder") is None
    
    def test_get_folder_size_empty(self, temp_dirs):
        """Test getting size of empty folder."""
        checkpoint_dir, _ = temp_dirs
        test_folder = checkpoint_dir / "test_folder"
        test_folder.mkdir()
        
        cleaner = WorkflowCleaner()
        size = cleaner.get_folder_size(test_folder)
        assert size == 0
    
    def test_get_folder_size_with_files(self, temp_dirs):
        """Test getting size of folder with files."""
        checkpoint_dir, _ = temp_dirs
        test_folder = checkpoint_dir / "test_folder"
        test_folder.mkdir()
        
        # Create test files
        (test_folder / "file1.txt").write_text("Hello" * 100)
        (test_folder / "file2.txt").write_text("World" * 100)
        
        cleaner = WorkflowCleaner()
        size = cleaner.get_folder_size(test_folder)
        assert size > 0
        assert size == 1000  # 500 + 500 bytes
    
    def test_scan_workflow_folders_empty(self, temp_dirs):
        """Test scanning empty directories."""
        checkpoint_dir, _ = temp_dirs
        cleaner = WorkflowCleaner(checkpoint_dir=checkpoint_dir)
        
        folders = cleaner.scan_workflow_folders(checkpoint_dir, "checkpoint")
        assert folders == []
    
    def test_scan_workflow_folders_with_workflows(self, temp_dirs):
        """Test scanning directories with workflow folders."""
        checkpoint_dir, _ = temp_dirs
        
        # Create workflow folders
        (checkpoint_dir / "workflow_topic1_20260120_144424").mkdir()
        (checkpoint_dir / "workflow_topic2_20260121_110225").mkdir()
        (checkpoint_dir / "random_folder").mkdir()  # Should be ignored
        
        cleaner = WorkflowCleaner(checkpoint_dir=checkpoint_dir)
        folders = cleaner.scan_workflow_folders(checkpoint_dir, "checkpoint")
        
        assert len(folders) == 2
        assert all(isinstance(f, WorkflowFolder) for f in folders)
        assert all(f.folder_type == "checkpoint" for f in folders)
        
        # Check topics
        topics = {f.topic for f in folders}
        assert topics == {"topic1", "topic2"}
    
    def test_group_by_topic(self, cleaner):
        """Test grouping folders by topic."""
        folders = [
            WorkflowFolder(
                path=Path("workflow_topic1_20260120_144424"),
                topic="topic1",
                timestamp="20260120_144424",
                folder_type="checkpoint",
                size_bytes=1000
            ),
            WorkflowFolder(
                path=Path("workflow_topic1_20260121_110225"),
                topic="topic1",
                timestamp="20260121_110225",
                folder_type="checkpoint",
                size_bytes=2000
            ),
            WorkflowFolder(
                path=Path("workflow_topic2_20260120_144424"),
                topic="topic2",
                timestamp="20260120_144424",
                folder_type="output",
                size_bytes=3000
            ),
        ]
        
        grouped = cleaner.group_by_topic(folders)
        
        assert len(grouped) == 2
        assert "topic1" in grouped
        assert "topic2" in grouped
        assert len(grouped["topic1"]) == 2
        assert len(grouped["topic2"]) == 1
        
        # Check sorting (newest first)
        assert grouped["topic1"][0].timestamp == "20260121_110225"
        assert grouped["topic1"][1].timestamp == "20260120_144424"
    
    def test_identify_deletable_folders_keep_one(self, cleaner):
        """Test identifying deletable folders (keep_n=1)."""
        folders = [
            WorkflowFolder(
                path=Path("workflow_topic1_20260121_110225"),
                topic="topic1",
                timestamp="20260121_110225",
                folder_type="checkpoint",
                size_bytes=2000
            ),
            WorkflowFolder(
                path=Path("workflow_topic1_20260120_144424"),
                topic="topic1",
                timestamp="20260120_144424",
                folder_type="checkpoint",
                size_bytes=1000
            ),
        ]
        
        deletable = cleaner.identify_deletable_folders("topic1", folders, keep_n=1)
        
        assert len(deletable) == 1
        assert deletable[0].timestamp == "20260120_144424"  # Older one
    
    def test_identify_deletable_folders_keep_multiple(self, cleaner):
        """Test identifying deletable folders (keep_n=2)."""
        folders = [
            WorkflowFolder(
                path=Path("workflow_topic1_20260122_163807"),
                topic="topic1",
                timestamp="20260122_163807",
                folder_type="checkpoint",
                size_bytes=3000
            ),
            WorkflowFolder(
                path=Path("workflow_topic1_20260121_110225"),
                topic="topic1",
                timestamp="20260121_110225",
                folder_type="checkpoint",
                size_bytes=2000
            ),
            WorkflowFolder(
                path=Path("workflow_topic1_20260120_144424"),
                topic="topic1",
                timestamp="20260120_144424",
                folder_type="checkpoint",
                size_bytes=1000
            ),
        ]
        
        deletable = cleaner.identify_deletable_folders("topic1", folders, keep_n=2)
        
        assert len(deletable) == 1
        assert deletable[0].timestamp == "20260120_144424"  # Oldest one
    
    def test_identify_deletable_folders_keep_all(self, cleaner):
        """Test when keep_n >= number of folders."""
        folders = [
            WorkflowFolder(
                path=Path("workflow_topic1_20260121_110225"),
                topic="topic1",
                timestamp="20260121_110225",
                folder_type="checkpoint",
                size_bytes=2000
            ),
        ]
        
        deletable = cleaner.identify_deletable_folders("topic1", folders, keep_n=2)
        
        assert len(deletable) == 0
    
    def test_delete_folder_dry_run(self, temp_dirs):
        """Test deleting folder in dry-run mode."""
        checkpoint_dir, _ = temp_dirs
        test_folder = checkpoint_dir / "workflow_topic1_20260120_144424"
        test_folder.mkdir()
        
        folder = WorkflowFolder(
            path=test_folder,
            topic="topic1",
            timestamp="20260120_144424",
            folder_type="checkpoint",
            size_bytes=0
        )
        
        cleaner = WorkflowCleaner()
        success = cleaner.delete_folder(folder, dry_run=True)
        
        assert success is True
        assert test_folder.exists()  # Should still exist in dry-run
    
    def test_delete_folder_actual(self, temp_dirs):
        """Test actually deleting a folder."""
        checkpoint_dir, _ = temp_dirs
        test_folder = checkpoint_dir / "workflow_topic1_20260120_144424"
        test_folder.mkdir()
        (test_folder / "test.txt").write_text("test")
        
        folder = WorkflowFolder(
            path=test_folder,
            topic="topic1",
            timestamp="20260120_144424",
            folder_type="checkpoint",
            size_bytes=4
        )
        
        cleaner = WorkflowCleaner()
        success = cleaner.delete_folder(folder, dry_run=False)
        
        assert success is True
        assert not test_folder.exists()  # Should be deleted
    
    def test_cleanup_dry_run(self, temp_dirs):
        """Test cleanup in dry-run mode."""
        checkpoint_dir, output_dir = temp_dirs
        
        # Create test folders
        (checkpoint_dir / "workflow_topic1_20260121_110225").mkdir()
        (checkpoint_dir / "workflow_topic1_20260120_144424").mkdir()
        (output_dir / "workflow_topic1_20260121_110225").mkdir()
        (output_dir / "workflow_topic1_20260120_144424").mkdir()
        
        cleaner = WorkflowCleaner(checkpoint_dir=checkpoint_dir, output_dir=output_dir)
        report = cleaner.cleanup(dry_run=True, keep_n=1)
        
        assert isinstance(report, CleanupReport)
        assert report.dry_run is True
        assert report.topics_processed == 1
        assert report.folders_deleted == 2  # 1 checkpoint + 1 output
        
        # Folders should still exist
        assert (checkpoint_dir / "workflow_topic1_20260121_110225").exists()
        assert (checkpoint_dir / "workflow_topic1_20260120_144424").exists()
    
    def test_cleanup_actual(self, temp_dirs):
        """Test actual cleanup."""
        checkpoint_dir, output_dir = temp_dirs
        
        # Create test folders
        (checkpoint_dir / "workflow_topic1_20260121_110225").mkdir()
        (checkpoint_dir / "workflow_topic1_20260120_144424").mkdir()
        (output_dir / "workflow_topic1_20260121_110225").mkdir()
        (output_dir / "workflow_topic1_20260120_144424").mkdir()
        
        cleaner = WorkflowCleaner(checkpoint_dir=checkpoint_dir, output_dir=output_dir)
        report = cleaner.cleanup(dry_run=False, keep_n=1)
        
        assert report.dry_run is False
        assert report.topics_processed == 1
        assert report.folders_deleted == 2
        
        # Latest folders should exist
        assert (checkpoint_dir / "workflow_topic1_20260121_110225").exists()
        assert (output_dir / "workflow_topic1_20260121_110225").exists()
        
        # Older folders should be deleted
        assert not (checkpoint_dir / "workflow_topic1_20260120_144424").exists()
        assert not (output_dir / "workflow_topic1_20260120_144424").exists()
    
    def test_cleanup_with_topic_filter(self, temp_dirs):
        """Test cleanup with topic filter."""
        checkpoint_dir, output_dir = temp_dirs
        
        # Create test folders for two topics
        (checkpoint_dir / "workflow_topic1_20260121_110225").mkdir()
        (checkpoint_dir / "workflow_topic1_20260120_144424").mkdir()
        (checkpoint_dir / "workflow_topic2_20260121_110225").mkdir()
        (checkpoint_dir / "workflow_topic2_20260120_144424").mkdir()
        
        cleaner = WorkflowCleaner(checkpoint_dir=checkpoint_dir, output_dir=output_dir)
        report = cleaner.cleanup(dry_run=False, topic_filter="topic1", keep_n=1)
        
        assert report.topics_processed == 1
        assert "topic1" in report.topic_details
        assert "topic2" not in report.topic_details
        
        # Only topic1 older folder should be deleted
        assert (checkpoint_dir / "workflow_topic1_20260121_110225").exists()
        assert not (checkpoint_dir / "workflow_topic1_20260120_144424").exists()
        
        # topic2 folders should remain untouched
        assert (checkpoint_dir / "workflow_topic2_20260121_110225").exists()
        assert (checkpoint_dir / "workflow_topic2_20260120_144424").exists()
    
    def test_cleanup_report_str(self):
        """Test CleanupReport string formatting."""
        report = CleanupReport(
            topics_processed=1,
            folders_deleted=2,
            checkpoint_folders_deleted=1,
            output_folders_deleted=1,
            space_freed_bytes=1024 * 1024 * 10,  # 10 MB
            errors=[],
            warnings=[],
            topic_details={
                "topic1": {
                    "latest_folder": "workflow_topic1_20260121_110225",
                    "folders_to_delete": 2,
                    "space_to_free_mb": 10.0,
                    "checkpoint_folders": [{"name": "workflow_topic1_20260120_144424", "size_mb": 5.0}],
                    "output_folders": [{"name": "workflow_topic1_20260120_144424", "size_mb": 5.0}],
                }
            },
            dry_run=True
        )
        
        report_str = str(report)
        assert "Workflow Folder Cleanup Report" in report_str
        assert "topic1" in report_str
        assert "10.0 MB" in report_str
        assert "DRY RUN" in report_str


class TestWorkflowFolder:
    """Test WorkflowFolder dataclass."""
    
    def test_size_mb_property(self):
        """Test size_mb property calculation."""
        folder = WorkflowFolder(
            path=Path("test"),
            topic="topic1",
            timestamp="20260120_144424",
            folder_type="checkpoint",
            size_bytes=1024 * 1024  # 1 MB
        )
        
        assert folder.size_mb == 1.0
    
    def test_datetime_property(self):
        """Test datetime property parsing."""
        folder = WorkflowFolder(
            path=Path("test"),
            topic="topic1",
            timestamp="20260120_144424",
            folder_type="checkpoint",
            size_bytes=0
        )
        
        dt = folder.datetime
        assert isinstance(dt, datetime)
        assert dt.year == 2026
        assert dt.month == 1
        assert dt.day == 20
        assert dt.hour == 14
        assert dt.minute == 44
        assert dt.second == 24
