"""
State Store for Distributed State Management

Provides interface for state persistence (file-based, Redis, etc.).
"""

import json
import logging
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Any, Dict, List, Optional

logger = logging.getLogger(__name__)


class StateStore(ABC):
    """Abstract base class for state stores."""

    @abstractmethod
    def save(self, key: str, value: Dict[str, Any]) -> bool:
        """
        Save state.

        Args:
            key: State key
            value: State value

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """
        Load state.

        Args:
            key: State key

        Returns:
            State value or None
        """
        pass

    @abstractmethod
    def delete(self, key: str) -> bool:
        """
        Delete state.

        Args:
            key: State key

        Returns:
            True if successful
        """
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """
        Check if state exists.

        Args:
            key: State key

        Returns:
            True if exists
        """
        pass


class FileStateStore(StateStore):
    """File-based state store."""

    def __init__(self, state_dir: str = "data/state"):
        """
        Initialize file state store.

        Args:
            state_dir: Directory to store state files
        """
        self.state_dir = Path(state_dir)
        self.state_dir.mkdir(parents=True, exist_ok=True)

    def save(self, key: str, value: Dict[str, Any]) -> bool:
        """Save state to file."""
        state_file = self.state_dir / f"{key}.json"

        try:
            with open(state_file, "w") as f:
                json.dump(value, f, indent=2, default=str)
            return True
        except Exception as e:
            logger.error(f"Failed to save state {key}: {e}", exc_info=True)
            return False

    def load(self, key: str) -> Optional[Dict[str, Any]]:
        """Load state from file."""
        state_file = self.state_dir / f"{key}.json"

        if not state_file.exists():
            return None

        try:
            with open(state_file) as f:
                return json.load(f)
        except Exception as e:
            logger.error(f"Failed to load state {key}: {e}", exc_info=True)
            return None

    def delete(self, key: str) -> bool:
        """Delete state file."""
        state_file = self.state_dir / f"{key}.json"

        if state_file.exists():
            try:
                state_file.unlink()
                return True
            except Exception as e:
                logger.error(f"Failed to delete state {key}: {e}", exc_info=True)
                return False

        return True

    def exists(self, key: str) -> bool:
        """Check if state file exists."""
        state_file = self.state_dir / f"{key}.json"
        return state_file.exists()

    def list_keys(self) -> List[str]:
        """List all state keys."""
        keys = []
        for state_file in self.state_dir.glob("*.json"):
            keys.append(state_file.stem)
        return keys
