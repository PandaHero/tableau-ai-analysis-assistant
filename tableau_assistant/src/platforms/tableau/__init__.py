"""
Tableau Platform Implementation

Provides Tableau-specific adapter, query builder, field mapper,
authentication, metadata services, and VizQL client.

This is the unified Tableau platform module that combines:
- Platform adapter (implements BasePlatformAdapter)
- Query builder (implements BaseQueryBuilder)
- Field mapper (implements BaseFieldMapper)
- Authentication (JWT, PAT)
- Metadata services
- VizQL Data Service client
"""

from tableau_assistant.src.platforms.tableau.adapter import TableauAdapter
from tableau_assistant.src.platforms.tableau.query_builder import TableauQueryBuilder
from tableau_assistant.src.platforms.tableau.field_mapper import TableauFieldMapper

# Authentication
from tableau_assistant.src.platforms.tableau.auth import (

    # Auth Context
    TableauAuthContext,
    TableauAuthError,
    # Auth Functions
    get_tableau_auth,
    get_tableau_auth_async,
    # RunnableConfig Integration
    create_config_with_auth,
    get_auth_from_config,
    ensure_valid_auth,
    ensure_valid_auth_async,
)

# Metadata Services
from tableau_assistant.src.platforms.tableau.data_model import (
    get_data_dictionary,
    get_data_dictionary_async,
    get_datasource_luid_by_name,
    fetch_dimension_samples_for_fields,
)

# VizQL Client
from tableau_assistant.src.platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig

# Data Model Loader
from tableau_assistant.src.platforms.tableau.data_model_loader import TableauDataModelLoader



# Register Tableau adapter with platform registry
def _register():
    """Register Tableau adapter with platform registry."""
    try:
        from tableau_assistant.src.platforms.base import register_adapter

        register_adapter("tableau", TableauAdapter)
    except ImportError:
        pass  # Registry not available


_register()

__all__ = [
    # Adapter
    "TableauAdapter",
    "TableauQueryBuilder",
    "TableauFieldMapper",
    # Auth
    "TableauAuthContext",
    "TableauAuthError",
    "get_tableau_auth",
    "get_tableau_auth_async",
    "create_config_with_auth",
    "get_auth_from_config",
    "ensure_valid_auth",
    "ensure_valid_auth_async",
    # Metadata
    "get_data_dictionary",
    "get_data_dictionary_async",
    "get_datasource_luid_by_name",
    "fetch_dimension_samples_for_fields",
    # VizQL Client
    "VizQLClient",
    "VizQLClientConfig",
    # Data Model Loader
    "TableauDataModelLoader",
]
