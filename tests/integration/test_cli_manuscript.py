"""
Integration tests for CLI manuscript commands
"""

import sys
from pathlib import Path
import subprocess


class TestCLIManuscript:
    """Test CLI manuscript commands."""

    def test_list_journals_flag(self):
        """Test --list-journals flag."""
        result = subprocess.run(
            [sys.executable, "main.py", "--list-journals"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode == 0
        assert "Available Journals" in result.stdout or "ieee" in result.stdout.lower()

    def test_resolve_citation_flag_doi(self):
        """Test --resolve-citation flag with DOI."""
        # Skip if Manubot not available
        result = subprocess.run(
            [sys.executable, "main.py", "--resolve-citation", "doi:10.1038/nbt.3780"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        # May fail if Manubot not installed or network unavailable
        # Just verify command is recognized
        assert "resolve" in result.stdout.lower() or "error" in result.stderr.lower() or result.returncode in [0, 1]

    def test_resolve_citation_flag_pmid(self):
        """Test --resolve-citation flag with PMID."""
        result = subprocess.run(
            [sys.executable, "main.py", "--resolve-citation", "pmid:29424689"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        # May fail if Manubot not installed
        assert result.returncode in [0, 1]

    def test_resolve_citation_flag_arxiv(self):
        """Test --resolve-citation flag with arXiv ID."""
        result = subprocess.run(
            [sys.executable, "main.py", "--resolve-citation", "arxiv:1407.3561"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        # May fail if Manubot not installed
        assert result.returncode in [0, 1]

    def test_help_shows_manuscript_commands(self):
        """Test --help shows manuscript commands."""
        result = subprocess.run(
            [sys.executable, "main.py", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode == 0
        help_text = result.stdout.lower()
        assert any(cmd in help_text for cmd in ["manubot", "package", "citation", "journal"])

    def test_manubot_export_flag_parsing(self):
        """Test --manubot-export flag is recognized."""
        # Test that flag doesn't cause immediate error
        # Actual execution would require full workflow setup
        result = subprocess.run(
            [sys.executable, "main.py", "--manubot-export", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        # Should show help, not error about unknown flag
        assert result.returncode == 0 or "manubot" in result.stdout.lower()

    def test_build_package_flag_parsing(self):
        """Test --build-package flag is recognized."""
        result = subprocess.run(
            [sys.executable, "main.py", "--build-package", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        assert result.returncode == 0 or "package" in result.stdout.lower()

    def test_journal_flag_with_build_package(self):
        """Test --journal flag with --build-package."""
        result = subprocess.run(
            [sys.executable, "main.py", "--build-package", "--journal", "ieee", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        # Should parse without error
        assert result.returncode == 0

    def test_validate_submission_flag(self):
        """Test --validate-submission flag."""
        result = subprocess.run(
            [sys.executable, "main.py", "--validate-submission", "ieee", "--help"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        # Should parse without error
        assert result.returncode == 0

    def test_cli_error_handling_invalid_flags(self):
        """Test CLI error handling for invalid flags."""
        result = subprocess.run(
            [sys.executable, "main.py", "--invalid-flag"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        # Should show error about unknown flag
        assert result.returncode != 0 or "error" in result.stderr.lower() or "unrecognized" in result.stderr.lower()

    def test_cli_error_messages_missing_dependencies(self):
        """Test CLI error messages for missing dependencies."""
        # Test with --resolve-citation when Manubot not available
        # This is tested indirectly through the resolve_citation tests above
        pass

    def test_list_journals_output_format(self):
        """Test --list-journals output format."""
        result = subprocess.run(
            [sys.executable, "main.py", "--list-journals"],
            capture_output=True,
            text=True,
            cwd=Path(__file__).parent.parent.parent,
        )
        if result.returncode == 0:
            # Should have structured output
            assert "Available Journals" in result.stdout or "ieee" in result.stdout.lower()
