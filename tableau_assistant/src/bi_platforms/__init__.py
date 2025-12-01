"""
BI 平台集成

提供与各种 BI 平台的集成能力。

支持的平台：
- tableau: Tableau 平台集成
  - auth: 认证管理
  - metadata: 元数据 API
  - vizql_data_service: VizQL Data Service API
  - models: LLM 模型选择

使用示例：
    from tableau_assistant.src.bi_platforms.tableau import auth, metadata, vizql_data_service
"""

__all__ = [
    "tableau",
]
