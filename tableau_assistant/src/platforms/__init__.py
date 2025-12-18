"""Platform layer - Platform-specific implementations.

This layer contains platform-specific adapters, query builders,
and field mappers that implement the core interfaces.

Supported platforms:
- Tableau: VizQL API integration
- (Future) Power BI: DAX integration
- (Future) Looker: LookML integration
"""

from .base import PlatformRegistry, get_adapter, register_adapter

__all__ = [
    "PlatformRegistry",
    "get_adapter",
    "register_adapter",
]
