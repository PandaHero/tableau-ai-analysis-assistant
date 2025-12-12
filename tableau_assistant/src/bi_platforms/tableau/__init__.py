"""
Tableau 平台集成

模块：
- auth: 认证管理（JWT、PAT）+ 认证上下文
- metadata: 元数据服务
- vizql_client: VizQL Data Service 客户端
"""
from tableau_assistant.src.bi_platforms.tableau.auth import (
    # 认证上下文
    TableauAuthContext,
    TableauAuthError,
    # 认证获取
    get_tableau_auth,
    get_tableau_auth_async,
    # RunnableConfig 集成
    create_config_with_auth,
    get_auth_from_config,
    ensure_valid_auth,
    ensure_valid_auth_async,
    # 底层函数
    _get_tableau_context_from_env,
)
from tableau_assistant.src.bi_platforms.tableau.metadata import (
    get_data_dictionary,
    get_data_dictionary_async,
    get_datasource_luid_by_name,
)
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig

# 模型管理（向后兼容）
from tableau_assistant.src.model_manager import select_model, select_embeddings

__all__ = [
    # Auth Context
    "TableauAuthContext",
    "TableauAuthError",
    "get_tableau_auth",
    "get_tableau_auth_async",
    "create_config_with_auth",
    "get_auth_from_config",
    "ensure_valid_auth",
    "ensure_valid_auth_async",
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
