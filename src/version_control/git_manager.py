"""
Git Manuscript Manager

Manages Git operations for manuscript version control.
"""

import logging
from pathlib import Path

try:
    import git
    GITPYTHON_AVAILABLE = True
except ImportError:
    GITPYTHON_AVAILABLE = False
    git = None

logger = logging.getLogger(__name__)


class GitManuscriptManager:
    """Manage Git operations for manuscripts."""

    def __init__(self, repo_path: Path):
        """
        Initialize Git manager.

        Args:
            repo_path: Path to repository directory

        Raises:
            ImportError: If gitpython is not installed
        """
        if not GITPYTHON_AVAILABLE:
            raise ImportError(
                "gitpython required. Install with: pip install gitpython"
            )

        self.repo_path = Path(repo_path)
        self.repo = None

    def initialize_repo(self) -> None:
        """
        Initialize Git repository if it doesn't exist.

        Raises:
            RuntimeError: If repository initialization fails
        """
        try:
            if (self.repo_path / ".git").exists():
                logger.info(f"Git repository already exists: {self.repo_path}")
                self.repo = git.Repo(self.repo_path)
            else:
                logger.info(f"Initializing Git repository: {self.repo_path}")
                self.repo = git.Repo.init(self.repo_path)
                logger.info("Git repository initialized")
        except Exception as e:
            logger.error(f"Failed to initialize Git repository: {e}")
            raise RuntimeError(f"Git initialization failed: {e}") from e

    def commit_changes(self, message: str) -> None:
        """
        Commit all changes in the repository.

        Args:
            message: Commit message

        Raises:
            RuntimeError: If commit fails
        """
        if not self.repo:
            self.initialize_repo()

        try:
            # Add all files
            self.repo.git.add(A=True)
            
            # Check if there are changes
            if self.repo.is_dirty() or self.repo.untracked_files:
                self.repo.index.commit(message)
                logger.info(f"Committed changes: {message}")
            else:
                logger.info("No changes to commit")
        except Exception as e:
            logger.error(f"Failed to commit changes: {e}")
            raise RuntimeError(f"Commit failed: {e}") from e

    def create_branch(self, branch_name: str) -> None:
        """
        Create and checkout a new branch.

        Args:
            branch_name: Name of the branch

        Raises:
            RuntimeError: If branch creation fails
        """
        if not self.repo:
            self.initialize_repo()

        try:
            if branch_name in [ref.name for ref in self.repo.heads]:
                logger.warning(f"Branch {branch_name} already exists")
                self.repo.git.checkout(branch_name)
            else:
                new_branch = self.repo.create_head(branch_name)
                new_branch.checkout()
                logger.info(f"Created and checked out branch: {branch_name}")
        except Exception as e:
            logger.error(f"Failed to create branch: {e}")
            raise RuntimeError(f"Branch creation failed: {e}") from e

    def get_status(self) -> dict:
        """
        Get Git repository status.

        Returns:
            Dictionary with status information
        """
        if not self.repo:
            self.initialize_repo()

        try:
            return {
                "is_dirty": self.repo.is_dirty(),
                "untracked_files": self.repo.untracked_files,
                "active_branch": str(self.repo.active_branch),
                "last_commit": str(self.repo.head.commit) if self.repo.head.commit else None,
            }
        except Exception as e:
            logger.error(f"Failed to get Git status: {e}")
            return {}
