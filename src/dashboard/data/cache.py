"""Simple file-watching cache for dashboard data."""

import time
from pathlib import Path
from typing import Any, Callable


class FileCache:
    """Cache that invalidates when the source file changes."""

    def __init__(self, ttl_seconds: int = 30):
        self._cache: dict[str, tuple[float, float, Any]] = {}
        self._ttl = ttl_seconds

    def get(self, path: Path, loader: Callable[[], Any]) -> Any:
        """Get cached data, reloading if file changed or TTL expired."""
        key = str(path)
        now = time.time()

        if key in self._cache:
            cached_mtime, cached_time, data = self._cache[key]
            current_mtime = path.stat().st_mtime if path.exists() else 0

            if current_mtime == cached_mtime and (now - cached_time) < self._ttl:
                return data

        data = loader()
        mtime = path.stat().st_mtime if path.exists() else 0
        self._cache[key] = (mtime, now, data)
        return data


# Global cache instance
cache = FileCache(ttl_seconds=30)
