# -*- coding: utf-8 -*-
"""Dimension Hierarchy Agent Models.

Data models for dimension hierarchy inference agent.

Note: Migrated from core/models/dimension_hierarchy.py per design document.
These are agent-specific models, not platform-agnostic core abstractions.
"""

from tableau_assistant.src.agents.dimension_hierarchy.models.hierarchy import (
    DimensionAttributes,
    DimensionHierarchyResult,
)


__all__ = [
    "DimensionAttributes",
    "DimensionHierarchyResult",
]
