"""
Field Mapping Cache

SQLite-based cache for field mappings with TTL support.

Features:
- TTL-based expiration (default: 1 hour)
- Datasource-scoped caching
- Thread-safe operations
"""

import logging
import time
from typing import Optional, Dict, Any
from dataclasses import dataclass

logger = logging.getLogger(__name__)


@dataclass
class CachedMapping:
    """Cached field mapping entry"""
    business_term: str
    technical_field: str
    confidence: float
    timestamp: float
    datasource_luid: str
    category: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None


class FieldMappingCache:
    """
    Field mapping cache with TTL support.
    
    Uses SQLite for persistence through StoreManager.
    
    Attributes:
        ttl: Time-to-live in seconds (default: 3600 = 1 hour)
        namespace: Cache namespace for isolation
    """
    
    def __init__(
        self,
        ttl: int = 3600,
        namespace: str = "field_mapping",
        store_manager: Optional[Any] = None
    ):
        """
        Initialize field mapping cache.
        
        Args:
            ttl: Time-to-live in seconds (default: 1 hour)
            namespace: Cache namespace for isolation
            store_manager: Optional StoreManager instance for SQLite persistence
        """
        self.ttl = ttl
        self.namespace = namespace
        self._store_manager = store_manager
        
        # In-memory cache for fast access
        self._memory_cache: Dict[str, CachedMapping] = {}
        
        # Statistics
        self._hits = 0
        self._misses = 0
    
    def _make_key(self, term: str, datasource_luid: str) -> str:
        """Create cache key from term and datasource"""
        return f"{datasource_luid}:{term.lower().strip()}"
    
    def get(
        self,
        term: str,
        datasource_luid: str
    ) -> Optional[CachedMapping]:
        """
        Get cached mapping for a business term.
        
        Args:
            term: Business term to look up
            datasource_luid: Datasource identifier
        
        Returns:
            CachedMapping if found and not expired, None otherwise
        """
        key = self._make_key(term, datasource_luid)
        
        # Check memory cache first
        if key in self._memory_cache:
            cached = self._memory_cache[key]
            if time.time() - cached.timestamp < self.ttl:
                self._hits += 1
                logger.debug(f"Cache hit (memory): {term} -> {cached.technical_field}")
                return cached
            else:
                # Expired, remove from memory
                del self._memory_cache[key]
        
        # Check SQLite cache if store_manager is available
        if self._store_manager:
            try:
                cached_data = self._store_manager.get(
                    namespace=self.namespace,
                    key=key
                )
                if cached_data:
                    timestamp = cached_data.get("timestamp", 0)
                    if time.time() - timestamp < self.ttl:
                        cached = CachedMapping(
                            business_term=cached_data["business_term"],
                            technical_field=cached_data["technical_field"],
                            confidence=cached_data["confidence"],
                            timestamp=timestamp,
                            datasource_luid=cached_data["datasource_luid"],
                            category=cached_data.get("category"),
                            level=cached_data.get("level"),
                            granularity=cached_data.get("granularity"),
                        )
                        # Populate memory cache
                        self._memory_cache[key] = cached
                        self._hits += 1
                        logger.debug(f"Cache hit (SQLite): {term} -> {cached.technical_field}")
                        return cached
                    else:
                        # Expired, delete from SQLite
                        self._store_manager.delete(namespace=self.namespace, key=key)
            except Exception as e:
                logger.warning(f"Failed to read from SQLite cache: {e}")
        
        self._misses += 1
        logger.debug(f"Cache miss: {term}")
        return None
    
    def set(
        self,
        term: str,
        datasource_luid: str,
        technical_field: str,
        confidence: float,
        category: Optional[str] = None,
        level: Optional[int] = None,
        granularity: Optional[str] = None
    ) -> None:
        """
        Cache a field mapping.
        
        Args:
            term: Business term
            datasource_luid: Datasource identifier
            technical_field: Mapped technical field name
            confidence: Mapping confidence score
            category: Optional dimension category
            level: Optional hierarchy level
            granularity: Optional granularity description
        """
        key = self._make_key(term, datasource_luid)
        timestamp = time.time()
        
        cached = CachedMapping(
            business_term=term,
            technical_field=technical_field,
            confidence=confidence,
            timestamp=timestamp,
            datasource_luid=datasource_luid,
            category=category,
            level=level,
            granularity=granularity,
        )
        
        # Store in memory cache
        self._memory_cache[key] = cached
        
        # Store in SQLite if store_manager is available
        if self._store_manager:
            try:
                self._store_manager.put(
                    namespace=self.namespace,
                    key=key,
                    value={
                        "business_term": term,
                        "technical_field": technical_field,
                        "confidence": confidence,
                        "timestamp": timestamp,
                        "datasource_luid": datasource_luid,
                        "category": category,
                        "level": level,
                        "granularity": granularity,
                    }
                )
                logger.debug(f"Cached mapping: {term} -> {technical_field}")
            except Exception as e:
                logger.warning(f"Failed to write to SQLite cache: {e}")
    
    def invalidate(self, term: str, datasource_luid: str) -> None:
        """
        Invalidate a cached mapping.
        
        Args:
            term: Business term to invalidate
            datasource_luid: Datasource identifier
        """
        key = self._make_key(term, datasource_luid)
        
        # Remove from memory cache
        if key in self._memory_cache:
            del self._memory_cache[key]
        
        # Remove from SQLite
        if self._store_manager:
            try:
                self._store_manager.delete(namespace=self.namespace, key=key)
            except Exception as e:
                logger.warning(f"Failed to delete from SQLite cache: {e}")
    
    def clear(self, datasource_luid: Optional[str] = None) -> None:
        """
        Clear cache entries.
        
        Args:
            datasource_luid: If provided, only clear entries for this datasource.
                           If None, clear all entries.
        """
        if datasource_luid:
            # Clear entries for specific datasource
            keys_to_remove = [
                k for k in self._memory_cache.keys()
                if k.startswith(f"{datasource_luid}:")
            ]
            for key in keys_to_remove:
                del self._memory_cache[key]
        else:
            # Clear all entries
            self._memory_cache.clear()
        
        logger.debug(f"Cache cleared (datasource={datasource_luid})")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        Get cache statistics.
        
        Returns:
            Dictionary with cache statistics
        """
        total = self._hits + self._misses
        hit_rate = self._hits / total if total > 0 else 0.0
        
        return {
            "hits": self._hits,
            "misses": self._misses,
            "total": total,
            "hit_rate": hit_rate,
            "memory_entries": len(self._memory_cache),
            "ttl_seconds": self.ttl,
        }
