"""
Tableau integration utilities.

This package contains utilities for interacting with Tableau Server/Online:
- Authentication (JWT Connected Apps)
- Metadata API queries
- VizQL Data Service queries
- LLM model selection
- HTTP utilities and data formatting
"""

from .auth import jwt_connected_app, jwt_connected_app_async
from .metadata import (
    get_data_dictionary,
    get_data_dictionary_async,
    get_datasource_luid_by_name,
    get_data_dictionary_by_name,
)
from .vizql_data_service import query_vds, query_vds_metadata
from .models import select_model, select_embeddings
from .utils import http_get, http_post, json_to_markdown_table

__all__ = [
    # Auth
    "jwt_connected_app",
    "jwt_connected_app_async",
    # Metadata
    "get_data_dictionary",
    "get_data_dictionary_async",
    "get_datasource_luid_by_name",
    "get_data_dictionary_by_name",
    # VizQL Data Service
    "query_vds",
    "query_vds_metadata",
    # Models
    "select_model",
    "select_embeddings",
    # Utils
    "http_get",
    "http_post",
    "json_to_markdown_table",
]
