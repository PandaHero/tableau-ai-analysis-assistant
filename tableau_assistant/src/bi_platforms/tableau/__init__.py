"""
Tableau 平台集成

模块：
- auth: 认证管理（JWT、PAT）
- metadata: 元数据服务
- vizql_client: VizQL Data Service 客户端
"""
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
from tableau_assistant.src.bi_platforms.tableau.metadata import (
    get_data_dictionary,
    get_data_dictionary_async,
    get_datasource_luid_by_name,
)
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig

# 模型管理（向后兼容）
from tableau_assistant.src.model_manager import select_model, select_embeddings

__all__ = [
    # Auth
    "_get_tableau_context_from_env",
    # Metadata
    "get_data_dictionary",
    "get_data_dictionary_async",
    "get_datasource_luid_by_name",
    # VizQL Client
    "VizQLClient",
    "VizQLClientConfig",
    # Models
    "select_model",
    "select_embeddings",
]
