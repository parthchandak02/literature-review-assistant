"""
Database Connectors

Base classes for database connectors. Individual connector implementations
are in database_connectors.py for backward compatibility.
"""

from .base import Paper, DatabaseConnector

__all__ = [
    "Paper",
    "DatabaseConnector",
]
