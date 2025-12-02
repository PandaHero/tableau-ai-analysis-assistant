"""
Tableau 平台集成

提供与 Tableau 平台的集成能力。

模块：
- auth: 认证管理（API Token、JWT）
- metadata: 元数据服务（GraphQL + VizQL 统一服务）
- vizql_client: VizQL Data Service 客户端（生产级，带连接池和重试）
- models: LLM 模型选择和配置

使用示例：
    # 推荐：使用统一元数据服务
    from tableau_assistant.src.bi_platforms.tableau import TableauMetadataService
    service = TableauMetadataService(domain="https://10ax.online.tableau.com")
    fields = service.get_fields(datasource_luid, api_key, site)
    
    # 异步函数
    from tableau_assistant.src.bi_platforms.tableau import get_data_dictionary_async
"""
from tableau_assistant.src.bi_platforms.tableau.auth import (
    _get_tableau_context_from_env,
)
from tableau_assistant.src.bi_platforms.tableau.metadata import (
    get_data_dictionary_async,
    fetch_valid_max_date_async,
    # 统一元数据服务
    TableauMetadataService,
    ServiceFieldMetadata,
    DataModel,
    LogicalTable,
    LogicalTableRelationship,
)
from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
from tableau_assistant.src.bi_platforms.tableau.models import select_model

__all__ = [
    # Auth
    "_get_tableau_context_from_env",
    # Metadata (async)
    "get_data_dictionary_async",
    "fetch_valid_max_date_async",
    # Unified Metadata Service
    "TableauMetadataService",
    "ServiceFieldMetadata",
    "DataModel",
    "LogicalTable",
    "LogicalTableRelationship",
    # VizQL Client
    "VizQLClient",
    "VizQLClientConfig",
    # Models
    "select_model",
]
