# -*- coding: utf-8 -*-
"""Core 接口 - 平台适配器的抽象基类。

本模块定义了平台特定实现必须遵循的契约：
- BasePlatformAdapter: 平台适配器接口
- BaseQueryBuilder: 查询构建器接口
- BaseFieldMapper: 字段映射器接口
"""

from abc import ABC, abstractmethod
from typing import Any

from analytics_assistant.src.core.schemas import (
    ExecuteResult,
    SemanticQuery,
    ValidationResult,
)


# ═══════════════════════════════════════════════════════════════════════════
# 平台适配器接口
# ═══════════════════════════════════════════════════════════════════════════

class BasePlatformAdapter(ABC):
    """平台适配器抽象基类。
    
    平台适配器将 SemanticQuery 转换为平台特定的查询并执行。
    
    实现：
    - TableauAdapter: 转换为 VizQL API 调用
    - PowerBIAdapter: 转换为 DAX 查询（未来）
    - SupersetAdapter: 转换为 SQL 查询（未来）
    """
    
    @property
    @abstractmethod
    def platform_name(self) -> str:
        """返回平台名称（如 'tableau', 'powerbi', 'superset'）。"""
        pass
    
    @abstractmethod
    async def execute_query(
        self,
        semantic_query: SemanticQuery,
        datasource_id: str,
        **kwargs: Any,
    ) -> ExecuteResult:
        """对平台执行语义查询。
        
        这是查询执行的主入口。
        处理完整流程：验证 → 构建 → 执行。
        
        Args:
            semantic_query: 平台无关的语义查询
            datasource_id: 平台特定的数据源标识符
            **kwargs: 额外的平台特定参数
            
        Returns:
            包含列和数据的 ExecuteResult
            
        Raises:
            ValidationError: 查询验证失败
            ExecutionError: 查询执行失败
        """
        pass
    
    @abstractmethod
    def build_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> Any:
        """从 SemanticQuery 构建平台特定查询。
        
        将平台无关的 SemanticQuery 转换为平台的原生查询格式
        （如 VizQL 请求、DAX 查询、SQL）。
        
        Args:
            semantic_query: 平台无关的语义查询
            **kwargs: 额外的平台特定参数
            
        Returns:
            平台特定的查询对象
        """
        pass
    
    @abstractmethod
    def validate_query(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> ValidationResult:
        """验证此平台的语义查询。
        
        检查查询是否可以在此平台上执行。
        可能自动修复小问题（如填充默认值）。
        
        Args:
            semantic_query: 平台无关的语义查询
            **kwargs: 额外的平台特定参数
            
        Returns:
            包含 is_valid、errors、warnings、auto_fixed 的 ValidationResult
        """
        pass
    
    @abstractmethod
    async def get_field_values(
        self,
        field_name: str,
        datasource_id: str,
        **kwargs: Any,
    ) -> list[str]:
        """获取字段的唯一值列表。
        
        用于筛选值验证，查询指定字段的所有唯一值。
        
        Args:
            field_name: 字段名称（caption）
            datasource_id: 平台特定的数据源标识符
            **kwargs: 额外的平台特定参数（如认证信息）
            
        Returns:
            字段唯一值列表
            
        Raises:
            RuntimeError: 查询失败
        """
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 查询构建器接口
# ═══════════════════════════════════════════════════════════════════════════

class BaseQueryBuilder(ABC):
    """查询构建器抽象基类。
    
    查询构建器将 SemanticQuery 转换为平台特定的查询格式。
    处理以下转换：
    - 维度 → 平台维度语法
    - 度量 → 平台度量语法
    - 计算 → 平台计算语法（如 TableCalc、DAX、窗口函数）
    - 筛选器 → 平台筛选器语法
    
    关键转换是 Computation.partition_by：
    - Tableau: partition_by → 表计算中的分区/寻址
    - Power BI: partition_by → DAX 中的 ALL/ALLEXCEPT
    - SQL: partition_by → 窗口函数中的 PARTITION BY
    """
    
    @abstractmethod
    def build(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> Any:
        """从 SemanticQuery 构建平台特定查询。
        
        Args:
            semantic_query: 平台无关的语义查询
            **kwargs: 额外的平台特定参数
            
        Returns:
            平台特定的查询对象
        """
        pass
    
    @abstractmethod
    def validate(
        self,
        semantic_query: SemanticQuery,
        **kwargs: Any,
    ) -> ValidationResult:
        """验证此平台的语义查询。
        
        检查查询是否可以为此平台构建。
        可能自动修复小问题（如填充默认聚合）。
        
        Args:
            semantic_query: 平台无关的语义查询
            **kwargs: 额外的平台特定参数
            
        Returns:
            包含 is_valid、errors、warnings、auto_fixed 的 ValidationResult
        """
        pass


# ═══════════════════════════════════════════════════════════════════════════
# 字段映射器接口
# ═══════════════════════════════════════════════════════════════════════════

class BaseFieldMapper(ABC):
    """字段映射器抽象基类。
    
    字段映射器将业务术语（如"销售额"、"省份"）转换为
    平台特定的技术字段名（如"[Sales].[Amount]"）。
    
    保留现有的两阶段检索（RAG + LLM）方法：
    1. RAG 检索：使用向量相似度查找候选字段
    2. LLM 选择：从候选中选择最佳匹配
    """
    
    @abstractmethod
    async def map(
        self,
        semantic_query: SemanticQuery,
        datasource_id: str,
        **kwargs: Any,
    ) -> SemanticQuery:
        """将语义查询中的所有字段映射到技术字段名。
        
        映射以下位置的字段：
        - dimensions[].field_name
        - measures[].field_name
        - computations[].target
        - computations[].partition_by[]
        - filters[].field_name
        - sorts[].field_name
        
        Args:
            semantic_query: 包含业务术语的查询
            datasource_id: 平台特定的数据源标识符
            **kwargs: 额外参数
            
        Returns:
            包含技术字段名的 SemanticQuery
        """
        pass
    
    @abstractmethod
    async def map_single_field(
        self,
        field_name: str,
        datasource_id: str,
        **kwargs: Any,
    ) -> str:
        """将单个业务术语映射到技术字段名。
        
        Args:
            field_name: 业务术语（如"销售额"）
            datasource_id: 平台特定的数据源标识符
            **kwargs: 额外参数
            
        Returns:
            技术字段名（如"[Sales].[Amount]"）
        """
        pass


__all__ = [
    "BasePlatformAdapter",
    "BaseQueryBuilder",
    "BaseFieldMapper",
]
