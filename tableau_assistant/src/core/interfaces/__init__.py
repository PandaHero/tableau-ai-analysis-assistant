"""Core interfaces - Abstract base classes for platform adapters.

This module defines the contracts that platform-specific implementations must follow.
"""

from .field_mapper import BaseFieldMapper
from .platform_adapter import BasePlatformAdapter
from .query_builder import BaseQueryBuilder

__all__ = [
    "BaseFieldMapper",
    "BasePlatformAdapter",
    "BaseQueryBuilder",
]
