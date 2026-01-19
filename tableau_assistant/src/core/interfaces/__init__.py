"""Core interfaces - Abstract base classes for platform adapters.

This module defines the contracts that platform-specific implementations must follow.
"""

from tableau_assistant.src.core.interfaces.field_mapper import BaseFieldMapper
from tableau_assistant.src.core.interfaces.platform_adapter import BasePlatformAdapter
from tableau_assistant.src.core.interfaces.query_builder import BaseQueryBuilder


__all__ = [
    "BaseFieldMapper",
    "BasePlatformAdapter",
    "BaseQueryBuilder",
]
