"""
Dynamic/Modular Prompt System

This module provides a dynamic prompt architecture that only includes relevant
modules based on question features, reducing context noise and improving accuracy.

Architecture:
1. FeatureTag - Question feature identifiers
2. PromptModule - Independent knowledge/rule units with tags
3. SchemaModule - Related field definitions  
4. FeatureDetector - Rule-based feature detection
5. DynamicPromptBuilder - Assembles prompt based on detected features

Design Principles:
- Minimal Context: Only include relevant modules
- Orthogonal Modules: Each module is independent
- Feature-Driven: Modules activated by detected features
"""

from .feature_tags import FeatureTag
from .prompt_module import PromptModule, SchemaModule
from .feature_detector import FeatureDetector
from .dynamic_builder import DynamicPromptBuilder

__all__ = [
    "FeatureTag",
    "PromptModule",
    "SchemaModule",
    "FeatureDetector",
    "DynamicPromptBuilder",
]
