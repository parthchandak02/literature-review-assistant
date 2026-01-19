"""
Caching layer for search results.
"""

import json
import hashlib
import sqlite3
import time
from typing import Optional, List, Dict, Any, TYPE_CHECKING
from pathlib import Path
import logging

if TYPE_CHECKING:
    from .database_connectors import Paper

logger = logging.getLogger(__name__)


class SearchCache:
    """
    Persistent cache for search results using SQLite.
    """

    def __init__(self, cache_dir: Optional[str] = None, ttl_hours: int = 24):
        """
        Initialize search cache.

        Args:
            cache_dir: Directory for cache database (default: data/cache)
            ttl_hours: Time-to-live for cache entries in hours (default: 24)
        """
        if cache_dir is None:
            cache_dir = Path(__file__).parent.parent.parent / "data" / "cache"

        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(parents=True, exist_ok=True)

        self.db_path = self.cache_dir / "search_cache.db"
        self.ttl_seconds = ttl_hours * 3600

        self._init_database()

    def _init_database(self):
        """Initialize the cache database."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("""
            CREATE TABLE IF NOT EXISTS cache_entries (
                cache_key TEXT PRIMARY KEY,
                query TEXT NOT NULL,
                database TEXT NOT NULL,
                results TEXT NOT NULL,
                created_at REAL NOT NULL,
                expires_at REAL NOT NULL
            )
        """)

        cursor.execute("""
            CREATE INDEX IF NOT EXISTS idx_expires_at ON cache_entries(expires_at)
        """)

        conn.commit()
        conn.close()

    def _generate_key(self, query: str, database: str) -> str:
        """
        Generate cache key from query and database.

        Args:
            query: Search query
            database: Database name

        Returns:
            Cache key string
        """
        key_string = f"{database}:{query}"
        return hashlib.sha256(key_string.encode()).hexdigest()

    def _serialize_papers(self, papers: List["Paper"]) -> str:
        """
        Serialize papers to JSON string.

        Args:
            papers: List of Paper objects

        Returns:
            JSON string
        """
        papers_dict = []
        for paper in papers:
            papers_dict.append(
                {
                    "title": paper.title,
                    "abstract": paper.abstract,
                    "authors": paper.authors,
                    "year": paper.year,
                    "doi": paper.doi,
                    "journal": paper.journal,
                    "database": paper.database,
                    "url": paper.url,
                    "keywords": paper.keywords,
                }
            )
        return json.dumps(papers_dict)

    def _deserialize_papers(self, json_str: str) -> List["Paper"]:
        """
        Deserialize JSON string to Paper objects.

        Args:
            json_str: JSON string

        Returns:
            List of Paper objects
        """
        from .database_connectors import Paper

        papers_dict = json.loads(json_str)
        papers = []
        for p in papers_dict:
            papers.append(
                Paper(
                    title=p["title"],
                    abstract=p["abstract"],
                    authors=p["authors"],
                    year=p["year"],
                    doi=p["doi"],
                    journal=p["journal"],
                    database=p["database"],
                    url=p["url"],
                    keywords=p["keywords"],
                )
            )
        return papers

    def get(self, query: str, database: str) -> Optional[List["Paper"]]:
        """
        Get cached results for a query.

        Args:
            query: Search query
            database: Database name

        Returns:
            List of Paper objects if found and not expired, None otherwise
        """
        cache_key = self._generate_key(query, database)
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = time.time()
        cursor.execute(
            """
            SELECT results, expires_at FROM cache_entries
            WHERE cache_key = ? AND expires_at > ?
        """,
            (cache_key, now),
        )

        row = cursor.fetchone()
        conn.close()

        if row:
            results_json, expires_at = row
            logger.debug(f"Cache hit for {database}: {query[:50]}...")
            return self._deserialize_papers(results_json)

        logger.debug(f"Cache miss for {database}: {query[:50]}...")
        return None

    def set(self, query: str, database: str, papers: List["Paper"]):
        """
        Cache search results.

        Args:
            query: Search query
            database: Database name
            papers: List of Paper objects to cache
        """
        cache_key = self._generate_key(query, database)
        now = time.time()
        expires_at = now + self.ttl_seconds

        results_json = self._serialize_papers(papers)

        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute(
            """
            INSERT OR REPLACE INTO cache_entries
            (cache_key, query, database, results, created_at, expires_at)
            VALUES (?, ?, ?, ?, ?, ?)
        """,
            (cache_key, query, database, results_json, now, expires_at),
        )

        conn.commit()
        conn.close()

        logger.debug(f"Cached {len(papers)} results for {database}: {query[:50]}...")

    def clear_expired(self):
        """Remove expired cache entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = time.time()
        cursor.execute("DELETE FROM cache_entries WHERE expires_at <= ?", (now,))
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        if deleted > 0:
            logger.debug(f"Cleared {deleted} expired cache entries")

    def clear_all(self):
        """Clear all cache entries."""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        cursor.execute("DELETE FROM cache_entries")
        deleted = cursor.rowcount

        conn.commit()
        conn.close()

        logger.info(f"Cleared all {deleted} cache entries")

    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.

        Returns:
            Dictionary with cache statistics
        """
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()

        now = time.time()

        cursor.execute("SELECT COUNT(*) FROM cache_entries")
        total = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cache_entries WHERE expires_at > ?", (now,))
        valid = cursor.fetchone()[0]

        cursor.execute("SELECT COUNT(*) FROM cache_entries WHERE expires_at <= ?", (now,))
        expired = cursor.fetchone()[0]

        conn.close()

        return {
            "total_entries": total,
            "valid_entries": valid,
            "expired_entries": expired,
            "cache_size_mb": self.db_path.stat().st_size / (1024 * 1024)
            if self.db_path.exists()
            else 0,
        }
