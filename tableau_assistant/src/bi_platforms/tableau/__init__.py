"""
Tableau 平台集成

提供与 Tableau 平台的集成能力。

模块：
- auth: 认证管理（API Token、JWT）
- metadata: 元数据 GraphQL API
- vizql_client: VizQL Data Service 客户端（生产级，带连接池和重试）
- models: LLM 模型选择和配置

使用示例：
    from tableau_assistant.src.bi_platforms.tableau.auth import get_tableau_token
    from tableau_assistant.src.bi_platforms.tableau.metadata import get_data_dictionary_async
    from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient
    from tableau_assistant.src.bi_platforms.tableau.models import select_model
"""
from tableau_assistant.src.bi_platforms.tableau.auth import (
    _get_tableau_context_from_env,
)
from tableau_assistant.src.bi_platforms.tableau.metadata import (
    get_data_dictionary_async,
    fetch_valid_max_date_async,
)
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.bi_platforms.tableau.models import select_model

__all__ = [
    "_get_tableau_context_from_env",
    "get_data_dictionary_async",
    "fetch_valid_max_date_async",
    "VizQLClient",
    "VizQLClientConfig",
    "select_model",
]
