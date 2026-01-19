"""Platform registry and factory.

Provides centralized platform adapter registration and retrieval.
"""

from typing import Type

from tableau_assistant.src.core.interfaces import BasePlatformAdapter



class PlatformRegistry:
    """Registry for platform adapters.
    
    Singleton pattern for managing platform adapter registration.
    """
    
    _instance: "PlatformRegistry | None" = None
    _adapters: dict[str, Type[BasePlatformAdapter]]
    
    def __new__(cls) -> "PlatformRegistry":
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._adapters = {}
        return cls._instance
    
    def register(self, name: str, adapter_class: Type[BasePlatformAdapter]) -> None:
        """Register a platform adapter.
        
        Args:
            name: Platform name (e.g., "tableau", "powerbi")
            adapter_class: Adapter class implementing BasePlatformAdapter
        """
        self._adapters[name.lower()] = adapter_class
    
    def get(self, name: str, **kwargs) -> BasePlatformAdapter:
        """Get a platform adapter instance.
        
        Args:
            name: Platform name
            **kwargs: Arguments to pass to adapter constructor
            
        Returns:
            Platform adapter instance
            
        Raises:
            ValueError: If platform is not registered
        """
        name_lower = name.lower()
        if name_lower not in self._adapters:
            available = ", ".join(self._adapters.keys()) or "none"
            raise ValueError(
                f"Platform '{name}' not registered. Available: {available}"
            )
        return self._adapters[name_lower](**kwargs)
    
    def list_platforms(self) -> list[str]:
        """List all registered platform names."""
        return list(self._adapters.keys())
    
    def is_registered(self, name: str) -> bool:
        """Check if a platform is registered."""
        return name.lower() in self._adapters


# Module-level convenience functions
_registry = PlatformRegistry()


def register_adapter(name: str, adapter_class: Type[BasePlatformAdapter]) -> None:
    """Register a platform adapter."""
    _registry.register(name, adapter_class)


def get_adapter(name: str, **kwargs) -> BasePlatformAdapter:
    """Get a platform adapter instance."""
    return _registry.get(name, **kwargs)
