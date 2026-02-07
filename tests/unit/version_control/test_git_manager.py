"""
Tests for Git Manager
"""

from unittest.mock import patch

import pytest

from src.version_control.git_manager import GITPYTHON_AVAILABLE, GitManuscriptManager


class TestGitManuscriptManager:
    """Test GitManuscriptManager."""

    def test_manager_initialization(self, tmp_path):
        """Test manager initialization."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        assert manager.repo_path == tmp_path
        assert manager.repo is None

    def test_manager_initialization_without_gitpython(self, tmp_path):
        """Test manager initialization without gitpython."""
        with patch("src.version_control.git_manager.GITPYTHON_AVAILABLE", False):
            with pytest.raises(ImportError) as exc_info:
                GitManuscriptManager(tmp_path)
            assert "gitpython required" in str(exc_info.value)

    def test_initialize_repo_new(self, tmp_path):
        """Test initialize_repo creates new repository."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()
        assert manager.repo is not None
        assert (tmp_path / ".git").exists()

    def test_initialize_repo_existing(self, tmp_path):
        """Test initialize_repo with existing repository."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        # Create existing repo
        import git

        git.Repo.init(tmp_path)

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()
        assert manager.repo is not None

    def test_initialize_repo_error_handling(self, tmp_path):
        """Test initialize_repo error handling."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)

        with patch("src.version_control.git_manager.git.Repo.init") as mock_init:
            mock_init.side_effect = Exception("Git init failed")
            with pytest.raises(RuntimeError) as exc_info:
                manager.initialize_repo()
            assert "Git initialization failed" in str(exc_info.value)

    def test_commit_changes(self, tmp_path):
        """Test commit_changes."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        # Create a file to commit
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        manager.commit_changes("Test commit")
        assert manager.repo.head.commit.message == "Test commit"

    def test_commit_changes_no_changes(self, tmp_path):
        """Test commit_changes with no changes."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        # Should not raise exception, just log
        manager.commit_changes("No changes commit")

    def test_commit_changes_auto_initialize(self, tmp_path):
        """Test commit_changes auto-initializes repo."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)

        # Create a file
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test content")

        # Should auto-initialize
        manager.commit_changes("Test commit")
        assert manager.repo is not None

    def test_commit_changes_error_handling(self, tmp_path):
        """Test commit_changes error handling."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        with patch.object(manager.repo, "git") as mock_git:
            mock_git.add.side_effect = Exception("Git add failed")
            with pytest.raises(RuntimeError) as exc_info:
                manager.commit_changes("Test commit")
            assert "Commit failed" in str(exc_info.value)

    def test_create_branch(self, tmp_path):
        """Test create_branch."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        # Create initial commit
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")
        manager.commit_changes("Initial commit")

        manager.create_branch("feature-branch")
        assert str(manager.repo.active_branch) == "feature-branch"

    def test_create_branch_existing(self, tmp_path):
        """Test create_branch with existing branch."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        # Create initial commit
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")
        manager.commit_changes("Initial commit")

        # Create branch first time
        manager.create_branch("feature-branch")

        # Try to create again (should checkout existing)
        manager.create_branch("feature-branch")
        assert str(manager.repo.active_branch) == "feature-branch"

    def test_create_branch_auto_initialize(self, tmp_path):
        """Test create_branch auto-initializes repo."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)

        # Create initial commit
        test_file = tmp_path / "test.txt"
        test_file.write_text("Test")

        manager.initialize_repo()
        manager.commit_changes("Initial commit")

        # Reset repo to None to test auto-init
        manager.repo = None

        # Should auto-initialize
        manager.create_branch("feature-branch")
        assert manager.repo is not None

    def test_create_branch_error_handling(self, tmp_path):
        """Test create_branch error handling."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        with patch.object(manager.repo, "create_head") as mock_create:
            mock_create.side_effect = Exception("Branch creation failed")
            with pytest.raises(RuntimeError) as exc_info:
                manager.create_branch("feature-branch")
            assert "Branch creation failed" in str(exc_info.value)

    def test_get_status(self, tmp_path):
        """Test get_status."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        status = manager.get_status()
        assert isinstance(status, dict)
        assert "is_dirty" in status
        assert "untracked_files" in status
        assert "active_branch" in status

    def test_get_status_with_changes(self, tmp_path):
        """Test get_status with uncommitted changes."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        # Create uncommitted file
        test_file = tmp_path / "untracked.txt"
        test_file.write_text("Untracked")

        status = manager.get_status()
        assert len(status["untracked_files"]) > 0

    def test_get_status_auto_initialize(self, tmp_path):
        """Test get_status auto-initializes repo."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)

        # Should auto-initialize
        status = manager.get_status()
        assert manager.repo is not None
        assert isinstance(status, dict)

    def test_get_status_error_handling(self, tmp_path):
        """Test get_status error handling."""
        if not GITPYTHON_AVAILABLE:
            pytest.skip("gitpython not installed")

        manager = GitManuscriptManager(tmp_path)
        manager.initialize_repo()

        with patch.object(manager.repo, "is_dirty") as mock_dirty:
            mock_dirty.side_effect = Exception("Status check failed")
            status = manager.get_status()
            assert status == {}
