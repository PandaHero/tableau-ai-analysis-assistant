"""VizQL Client wrapper for the new platform layer.

This module provides a thin wrapper around the existing VizQL client
to integrate with the new platform adapter architecture.
"""

import logging
from typing import Any

logger = logging.getLogger(__name__)


class VizQLClientWrapper:
    """Wrapper for VizQL API client.
    
    Provides a consistent interface for the platform adapter
    while delegating to the existing VizQL client implementation.
    """
    
    def __init__(self, base_client: Any = None):
        """Initialize VizQL client wrapper.
        
        Args:
            base_client: Existing VizQL client instance (lazy loaded if None)
        """
        self._base_client = base_client
    
    def _get_client(self):
        """Get or create base VizQL client."""
        if self._base_client is None:
            try:
                from tableau_assistant.src.platforms.tableau.vizql_client import (
                    VizQLClient,
                )
                self._base_client = VizQLClient()
            except ImportError as e:
                logger.error(f"Failed to import VizQL client: {e}")
                raise ImportError(
                    "VizQL client not available. "
                    "Ensure tableau_assistant.src.bi_platforms.tableau is installed."
                ) from e
        return self._base_client
    
    async def query_datasource(
        self,
        datasource_id: str,
        request: dict,
        **kwargs: Any,
    ) -> dict:
        """Execute a query against a Tableau datasource.
        
        Args:
            datasource_id: Tableau datasource ID
            request: VizQL query request dictionary
            **kwargs: Additional parameters
            
        Returns:
            VizQL query response dictionary
        """
        client = self._get_client()
        
        # Add datasource to request if not present
        if "datasource" not in request:
            request["datasource"] = {"datasourceId": datasource_id}
        
        # Delegate to base client
        return await client.query_datasource(request)
    
    async def read_metadata(
        self,
        datasource_id: str,
        **kwargs: Any,
    ) -> dict:
        """Read metadata for a Tableau datasource.
        
        Args:
            datasource_id: Tableau datasource ID
            **kwargs: Additional parameters
            
        Returns:
            Datasource metadata dictionary
        """
        client = self._get_client()
        return await client.read_metadata(datasource_id)
    
    async def get_datasource_model(
        self,
        datasource_id: str,
        **kwargs: Any,
    ) -> dict:
        """Get data model for a Tableau datasource.
        
        Args:
            datasource_id: Tableau datasource ID
            **kwargs: Additional parameters
            
        Returns:
            Datasource model dictionary
        """
        client = self._get_client()
        return await client.get_datasource_model(datasource_id)


# Convenience function to get a client instance
def get_vizql_client(**kwargs: Any) -> VizQLClientWrapper:
    """Get a VizQL client wrapper instance.
    
    Args:
        **kwargs: Arguments to pass to VizQLClientWrapper
        
    Returns:
        VizQLClientWrapper instance
    """
    return VizQLClientWrapper(**kwargs)
