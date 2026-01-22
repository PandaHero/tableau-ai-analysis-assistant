# -*- coding: utf-8 -*-
"""Tableau 平台适配器 - 实现 BasePlatformAdapter。

此适配器处理完整流程：
SemanticQuery → 验证 → 构建 VizQL → 执行 → ExecuteResult
"""

import logging
from typing import Any

from analytics_assistant.src.core.interfaces import BasePlatformAdapter
from analytics_assistant.src.core.models import (
    ColumnInfo,
    ExecuteResult,
    SemanticQuery,
    ValidationResult,
)
from analytics_assistant.src.platform.tableau.query_builder import TableauQueryBuilder


logger = logging.getLogger(__name__)


class TableauAdapter(BasePlatformAdapter):
    """Tableau 平台适配器。
    
    将 SemanticQuery 转换为 VizQL API 请求并执行。
    """
    
    def __init__(self, vizql_client: Any = None):
        """初始化 Tableau 适配器。
        
        Args:
            vizql_client: VizQL API 客户端（必须提供）
        """
        self._vizql_client = vizql_client
        self._query_builder = TableauQueryBuilder()
    
    @property
    def platform_name(self) -> str:
        """返回平台名称。"""
        return "tableau"
    
    async def execute_query(
        self,
        semantic_query: SemanticQuery,
        datasource_id: str,
        **kwargs: Any,
    ) -> ExecuteResult:
        """对 Tableau 执行语义查询。
        
        Args:
            semantic_query: 平台无关的语义查询
            datasource_id: Tableau 数据源 ID
            **kwargs: 额外参数
            
        Returns:
            包含列和数据的 ExecuteResult
            
        Raises:
            ValueError: 查询验证失败
            RuntimeError: VizQL 客户端未配置
        """
        if self._vizql_client is None:
            raise RuntimeError("VizQL 客户端未配置")
        
        # 验证查询
        validation = self.validate_query(semantic_query, **kwargs)
        if not validation.is_valid:
            error_msgs = [e.message for e in (validation.errors or [])]
            raise ValueError(f"查询验证失败: {'; '.join(error_msgs)}")
        
        # 构建 VizQL 请求
        vizql_request = self.build_query(
            semantic_query,
            datasource_id=datasource_id,
            **kwargs,
        )
        
        try:
            response = await self._vizql_client.query_datasource(
                datasource_id=datasource_id,
                request=vizql_request,
            )
            
            return self._convert_response(response)
            
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            raise
    
    def build_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> dict:
        """从 SemanticQuery 构建 VizQL 请求。
        
        Args:
            semantic_query: 平台无关的语义查询
            **kwargs: 额外参数
            
        Returns:
            VizQL API 请求字典
        """
        return self._query_builder.build(semantic_query, **kwargs)
    
    def validate_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> ValidationResult:
        """验证 Tableau 的语义查询。
        
        Args:
            semantic_query: 要验证的查询
            **kwargs: 额外参数
            
        Returns:
            ValidationResult
        """
        return self._query_builder.validate(semantic_query, **kwargs)
    
    def _convert_response(self, response: dict) -> ExecuteResult:
        """将 VizQL 响应转换为 ExecuteResult。"""
        columns = []
        for col in response.get("columns", []):
            columns.append(ColumnInfo(
                name=col.get("fieldCaption", col.get("name", "")),
                data_type=col.get("dataType", "STRING"),
                is_dimension=col.get("fieldRole") == "DIMENSION",
                is_measure=col.get("fieldRole") == "MEASURE",
                is_computation=col.get("columnClass") == "TABLE_CALCULATION",
            ))
        
        rows = response.get("data", [])
        row_count = response.get("rowCount", len(rows))
        execution_time = response.get("executionTimeMs", 0)
        
        return ExecuteResult(
            columns=columns,
            data=rows,
            row_count=row_count,
            execution_time_ms=execution_time,
        )
