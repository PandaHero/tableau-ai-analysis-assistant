# -*- coding: utf-8 -*-
"""Field Mapper Agent Models.

Data models for field mapping agent.

Note: Migrated from core/models/field_mapping.py per design document.
These are agent-specific models, not platform-agnostic core abstractions.
"""

from tableau_assistant.src.agents.field_mapper.models.mapping import (
    SingleSelectionResult,
    BatchSelectionResult,
    AlternativeMapping,
    FieldMapping,
    MappedQuery,
)


__all__ = [
    "SingleSelectionResult",
    "BatchSelectionResult",
    "AlternativeMapping",
    "FieldMapping",
    "MappedQuery",
]
