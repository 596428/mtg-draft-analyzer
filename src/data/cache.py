"""Local caching for API responses."""

import hashlib
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any, Optional


class CacheManager:
    """Manages local caching of API responses."""

    def __init__(self, cache_dir: str = ".cache", ttl_hours: int = 24):
        """
        Initialize cache manager.

        Args:
            cache_dir: Directory for cache files
            ttl_hours: Cache time-to-live in hours
        """
        self.cache_dir = Path(cache_dir)
        self.ttl = timedelta(hours=ttl_hours)
        self._ensure_cache_dir()

    def _ensure_cache_dir(self) -> None:
        """Create cache directory if it doesn't exist."""
        self.cache_dir.mkdir(parents=True, exist_ok=True)

    def _get_cache_key(self, *args: str) -> str:
        """Generate cache key from arguments."""
        key_string = "_".join(str(arg) for arg in args)
        return hashlib.md5(key_string.encode()).hexdigest()

    def _get_cache_path(self, key: str) -> Path:
        """Get file path for cache key."""
        return self.cache_dir / f"{key}.json"

    def _is_valid(self, cache_path: Path) -> bool:
        """Check if cache file exists and is not expired."""
        if not cache_path.exists():
            return False

        mtime = datetime.fromtimestamp(cache_path.stat().st_mtime)
        return datetime.now() - mtime < self.ttl

    def get(self, *args: str) -> Optional[Any]:
        """
        Retrieve cached data.

        Args:
            *args: Arguments used to generate cache key

        Returns:
            Cached data or None if not found/expired
        """
        key = self._get_cache_key(*args)
        cache_path = self._get_cache_path(key)

        if not self._is_valid(cache_path):
            return None

        with open(cache_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            return data.get("data")

    def set(self, data: Any, *args: str) -> None:
        """
        Store data in cache.

        Args:
            data: Data to cache
            *args: Arguments used to generate cache key
        """
        key = self._get_cache_key(*args)
        cache_path = self._get_cache_path(key)

        cache_entry = {
            "timestamp": datetime.now().isoformat(),
            "key_args": args,
            "data": data,
        }

        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_entry, f, ensure_ascii=False, indent=2)

    def invalidate(self, *args: str) -> bool:
        """
        Invalidate specific cache entry.

        Args:
            *args: Arguments used to generate cache key

        Returns:
            True if cache was invalidated, False if not found
        """
        key = self._get_cache_key(*args)
        cache_path = self._get_cache_path(key)

        if cache_path.exists():
            cache_path.unlink()
            return True
        return False

    def clear_all(self) -> int:
        """
        Clear all cached data.

        Returns:
            Number of cache files deleted
        """
        count = 0
        for cache_file in self.cache_dir.glob("*.json"):
            cache_file.unlink()
            count += 1
        return count

    def get_stats(self) -> dict:
        """Get cache statistics."""
        cache_files = list(self.cache_dir.glob("*.json"))
        total_size = sum(f.stat().st_size for f in cache_files)

        valid_count = sum(1 for f in cache_files if self._is_valid(f))

        return {
            "total_entries": len(cache_files),
            "valid_entries": valid_count,
            "expired_entries": len(cache_files) - valid_count,
            "total_size_bytes": total_size,
            "total_size_mb": round(total_size / (1024 * 1024), 2),
            "cache_dir": str(self.cache_dir),
        }
