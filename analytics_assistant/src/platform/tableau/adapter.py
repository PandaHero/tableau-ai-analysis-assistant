# -*- coding: utf-8 -*-
"""Tableau 平台适配器 - 实现 BasePlatformAdapter。

此适配器处理完整流程：
SemanticOutput → 验证 → 构建 VizQL → 执行 → ExecuteResult

SemanticOutput 是语义解析器的输出，直接作为适配器的输入，
无需中间的 SemanticQuery 模型。
"""

import logging
from typing import Any

from analytics_assistant.src.core.interfaces import BasePlatformAdapter
from analytics_assistant.src.core.schemas import (
    ColumnInfo,
    ExecuteResult,
    ValidationResult,
)
from analytics_assistant.src.core.schemas.semantic_output import SemanticOutput
from analytics_assistant.src.platform.tableau.query_builder import TableauQueryBuilder

logger = logging.getLogger(__name__)

class TableauAdapter(BasePlatformAdapter):
    """Tableau 平台适配器。
    
    将 SemanticOutput（语义解析器输出）转换为 VizQL API 请求并执行。
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
        semantic_output: SemanticOutput,
        datasource_id: str,
        **kwargs: Any,
    ) -> ExecuteResult:
        """对 Tableau 执行语义查询。
        
        Args:
            semantic_output: 语义解析器的输出
            datasource_id: Tableau 数据源 ID
            **kwargs: 额外参数（data_model, api_key, site 等）
            
        Returns:
            包含列和数据的 ExecuteResult
            
        Raises:
            ValueError: 查询验证失败
            RuntimeError: VizQL 客户端未配置
        """
        if self._vizql_client is None:
            raise RuntimeError("VizQL 客户端未配置")
        
        # 验证查询
        validation = self.validate_query(semantic_output, **kwargs)
        if not validation.is_valid:
            error_msgs = [e.message for e in (validation.errors or [])]
            raise ValueError(f"查询验证失败: {'; '.join(error_msgs)}")
        
        # 构建 VizQL 请求（传递 data_model）
        vizql_request = self.build_query(
            semantic_output,
            datasource_id=datasource_id,
            **kwargs,
        )
        
        try:
            response = await self._vizql_client.query_datasource(
                datasource_luid=datasource_id,
                query=vizql_request,
                api_key=kwargs.get("api_key", ""),
                site=kwargs.get("site"),
            )
            
            return self._convert_response(response)
            
        except Exception as e:
            logger.error(f"查询执行失败: {e}")
            raise
    
    def build_query(
        self,
        semantic_output: SemanticOutput,
        **kwargs: Any,
    ) -> dict:
        """从 SemanticOutput 构建 VizQL 请求。
        
        Args:
            semantic_output: 语义解析器的输出
            **kwargs: 额外参数（data_model 等）
            
        Returns:
            VizQL API 请求字典
        """
        # 从 data_model 构建 field_metadata
        data_model = kwargs.get("data_model")
        if data_model:
            field_metadata = {}
            fields = data_model.fields if hasattr(data_model, 'fields') else []
            for field in fields:
                field_name = field.name if hasattr(field, 'name') else str(field)
                field_metadata[field_name] = {
                    "dataType": field.data_type if hasattr(field, 'data_type') else "STRING",
                    "caption": field.caption if hasattr(field, 'caption') else field_name,
                }
            kwargs["field_metadata"] = field_metadata
            logger.debug(f"构建 field_metadata: {len(field_metadata)} 个字段")
            # 调试：打印 dt 字段的元数据
            if "dt" in field_metadata:
                logger.info(f"dt 字段元数据: {field_metadata['dt']}")
        
        return self._query_builder.build(semantic_output, **kwargs)
    
    def validate_query(
        self,
        semantic_output: SemanticOutput,
        **kwargs: Any,
    ) -> ValidationResult:
        """验证 SemanticOutput 是否适用于 Tableau 平台。
        
        Args:
            semantic_output: 要验证的语义输出
            **kwargs: 额外参数
            
        Returns:
            ValidationResult
        """
        return self._query_builder.validate(semantic_output, **kwargs)
    
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
    
    async def get_field_values(
        self,
        field_name: str,
        datasource_id: str,
        **kwargs: Any,
    ) -> list[str]:
        """获取字段的唯一值列表。
        
        通过 VizQL API 查询单个维度字段，返回该字段的唯一值。
        VizQL 查询单个维度字段时会自动返回唯一值（类似 GROUP BY）。
        
        Args:
            field_name: 字段名称（caption）
            datasource_id: Tableau 数据源 LUID
            **kwargs: 额外参数，包括：
                - api_key: API 密钥
                - site: 站点名称
            
        Returns:
            字段唯一值列表
            
        Raises:
            RuntimeError: VizQL 客户端未配置或查询失败
        """
        if self._vizql_client is None:
            raise RuntimeError("VizQL 客户端未配置")
        
        # 构建查询单个字段的 VizQL 请求
        vizql_request = {
            "fields": [
                {"fieldCaption": field_name}
            ]
        }
        
        try:
            response = await self._vizql_client.query_datasource(
                datasource_luid=datasource_id,
                query=vizql_request,
                api_key=kwargs.get("api_key"),
                site=kwargs.get("site"),
            )
            
            # 解析响应，提取唯一值
            rows = response.get("data", [])
            unique_values = []
            seen = set()
            
            for row in rows:
                if isinstance(row, dict):
                    value = row.get(field_name)
                    if value is not None:
                        value_str = str(value).strip()
                        if value_str and value_str not in seen:
                            seen.add(value_str)
                            unique_values.append(value_str)
            
            return unique_values
            
        except Exception as e:
            logger.error(f"获取字段值失败: {field_name}, 错误: {e}")
            raise RuntimeError(f"获取字段值失败: {e}") from e
