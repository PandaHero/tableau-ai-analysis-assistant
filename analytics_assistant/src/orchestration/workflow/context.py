# -*- coding: utf-8 -*-
"""
工作流上下文管理

提供统一的依赖容器 WorkflowContext，通过 RunnableConfig 传递给所有节点和工具。

使用示例:
    # 创建上下文
    ctx = WorkflowContext(
        auth=auth,  # Tableau 认证上下文
        datasource_luid="ds_12345",
        data_model=data_model,
    )
    config = create_workflow_config(thread_id, ctx)
    
    # 在节点中获取上下文
    async def my_node(state, config):
        ctx = get_context_or_raise(config)
        # 使用 ctx.auth, ctx.data_model, ctx.current_time 等
"""

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field, ConfigDict

from analytics_assistant.src.platform.tableau.auth import (
    get_tableau_auth_async,
    TableauAuthContext,
)
from analytics_assistant.src.core.interfaces import BasePlatformAdapter
from analytics_assistant.src.agents.semantic_parser.components.query_cache import (
    compute_schema_hash,
    QueryCache,
)
from analytics_assistant.src.agents.field_semantic import infer_field_semantic

logger = logging.getLogger(__name__)

class WorkflowContext(BaseModel):
    """
    工作流上下文 - 统一的依赖容器
    
    通过 RunnableConfig["configurable"]["workflow_context"] 传递给所有节点和工具。
    
    Attributes:
        auth: 平台认证上下文（如 TableauAuthContext）
        datasource_luid: 数据源 LUID
        data_model: 完整的数据模型
        
        # 语义解析器需要的字段
        current_time: 当前时间（ISO 格式）
        timezone: 时区
        fiscal_year_start_month: 财年起始月份
        field_values_cache: 字段值缓存（用于筛选值验证）
        field_samples: 字段样例数据（用于 Prompt）
        platform_adapter: 平台适配器（用于查询字段值）
        
        # Schema Hash 相关
        schema_hash: 当前数据模型的 schema hash（用于缓存失效检测）
        previous_schema_hash: 上一次的 schema hash（用于检测变更）
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # 认证上下文（可选，用于需要认证的平台）
    auth: Optional[Any] = Field(
        default=None,
        description="平台认证上下文（如 TableauAuthContext）"
    )
    
    # 数据源配置（必需）
    datasource_luid: str = Field(description="数据源 LUID")
    
    # 数据模型
    data_model: Optional[Any] = Field(default=None, description="完整的数据模型")
    
    # 字段语义
    field_semantic: Optional[dict[str, Any]] = Field(
        default=None, 
        description="字段语义信息（包含维度层级和度量类别）"
    )
    
    # ========== Schema Hash 相关 ==========
    
    # 上一次的 schema hash（用于检测变更）
    previous_schema_hash: Optional[str] = Field(
        default=None,
        description="上一次的 schema hash（用于检测变更）"
    )
    
    # 缓存的 schema hash（不作为 Pydantic 字段，使用 __pydantic_private__）
    _cached_schema_hash: Optional[str] = None
    
    # ========== 语义解析器需要的字段 ==========
    
    # 时间配置
    current_time: Optional[str] = Field(
        default=None, 
        description="当前时间（ISO 格式），每次请求时设置"
    )
    timezone: str = Field(
        default="Asia/Shanghai", 
        description="时区"
    )
    fiscal_year_start_month: int = Field(
        default=1, 
        description="财年起始月份（1=1月, 4=4月）"
    )
    
    # 业务日历（可选）
    business_calendar: Optional[dict[str, Any]] = Field(
        default=None, 
        description="业务日历配置"
    )
    
    # 字段值缓存（用于筛选值验证）
    field_values_cache: dict[str, list[str]] = Field(
        default_factory=dict, 
        description="字段值缓存，key 为字段名，value 为字段值列表"
    )
    
    # 字段样例数据（用于 Prompt）
    field_samples: Optional[dict[str, dict[str, Any]]] = Field(
        default=None, 
        description="字段样例数据"
    )
    
    # 平台适配器（用于查询字段值）
    platform_adapter: Optional[Any] = Field(
        default=None,
        description="平台适配器，用于查询字段值等操作"
    )
    
    # 用户 ID（可选）
    user_id: Optional[str] = Field(default=None, description="用户 ID")

    @property
    def schema_hash(self) -> str:
        """获取当前数据模型的 schema hash。
        
        如果 data_model 有 schema_hash 属性，直接使用；
        否则使用 compute_schema_hash 函数计算。
        
        Returns:
            schema hash 字符串
        """
        # 检查是否已缓存（使用对象属性而非 Pydantic 字段）
        cached = getattr(self, '_cached_schema_hash', None)
        if cached is not None:
            return cached
        
        if self.data_model is None:
            result = hashlib.md5(b"empty").hexdigest()
            object.__setattr__(self, '_cached_schema_hash', result)
            return result
        
        # 优先使用 data_model 的 schema_hash 属性
        if hasattr(self.data_model, 'schema_hash'):
            result = self.data_model.schema_hash
            object.__setattr__(self, '_cached_schema_hash', result)
            return result
        
        # 否则使用 compute_schema_hash 函数
        result = compute_schema_hash(self.data_model)
        object.__setattr__(self, '_cached_schema_hash', result)
        return result
    
    def has_schema_changed(self) -> bool:
        """检测 schema 是否发生变更。
        
        比较当前 schema_hash 与 previous_schema_hash。
        
        Returns:
            True 如果 schema 发生变更，False 否则
        """
        if self.previous_schema_hash is None:
            return False  # 没有历史记录，视为未变更
        return self.schema_hash != self.previous_schema_hash
    
    def invalidate_cache_if_schema_changed(self) -> int:
        """如果 schema 发生变更，失效相关缓存。
        
        调用 QueryCache.invalidate_by_schema_change() 清理旧缓存。
        
        Returns:
            失效的缓存条目数量，如果未变更返回 0
        """
        if not self.has_schema_changed():
            return 0
        
        try:
            cache = QueryCache()
            count = cache.invalidate_by_schema_change(
                datasource_luid=self.datasource_luid,
                new_schema_hash=self.schema_hash,
            )
            logger.info(
                f"Schema 变更，已失效 {count} 条缓存: "
                f"datasource={self.datasource_luid}, "
                f"old_hash={self.previous_schema_hash[:8] if self.previous_schema_hash else 'None'}..., "
                f"new_hash={self.schema_hash[:8]}..."
            )
            return count
        except Exception as e:
            logger.error(f"Schema 变更缓存失效失败: {e}")
            return 0

    def is_auth_valid(self, buffer_seconds: int = 60) -> bool:
        """检查认证是否有效
        
        Args:
            buffer_seconds: 缓冲时间（秒），在过期前多少秒视为无效
            
        Returns:
            True 如果认证有效，False 否则
        """
        if self.auth is None:
            return False
        
        # 检查 auth 是否有 is_expired 方法（如 TableauAuthContext）
        if hasattr(self.auth, 'is_expired'):
            return not self.auth.is_expired(buffer_seconds)
        
        return True
    
    async def refresh_auth_if_needed(self) -> "WorkflowContext":
        """如果认证过期，通过平台适配器刷新并返回新的上下文。

        优先使用 platform_adapter.refresh_auth()，
        回退到 get_tableau_auth_async()（向后兼容）。

        Returns:
            更新了认证的 WorkflowContext（如果需要刷新）
        """
        if self.auth is None:
            return self

        if self.is_auth_valid():
            return self

        logger.info("Token 即将过期，正在刷新...")

        # 优先使用平台适配器
        if self.platform_adapter and hasattr(self.platform_adapter, 'refresh_auth'):
            new_auth = await self.platform_adapter.refresh_auth()
        else:
            # 回退到直接调用（向后兼容）
            logger.warning("无平台适配器，回退到 get_tableau_auth_async")
            new_auth = await get_tableau_auth_async(force_refresh=True)

        logger.info("Token 刷新成功")
        return self.model_copy(update={"auth": new_auth})

    def get_field_values(self, field_name: str) -> Optional[list[str]]:
        """获取字段的缓存值
        
        Args:
            field_name: 字段名
            
        Returns:
            字段值列表，如果未缓存则返回 None
        """
        return self.field_values_cache.get(field_name)
    
    def set_field_values(self, field_name: str, values: list[str]) -> None:
        """缓存字段值
        
        Args:
            field_name: 字段名
            values: 字段值列表
        """
        self.field_values_cache[field_name] = values
    
    def update_current_time(self) -> "WorkflowContext":
        """更新当前时间并返回新的上下文
        
        用于每次请求开始时更新时间戳。
        同时保留 schema_hash 以便检测变更。
        """
        return self.model_copy(update={
            "previous_schema_hash": self.schema_hash,
            "current_time": datetime.now().isoformat(),
        })
    
    async def load_field_semantic(
        self,
        force_refresh: bool = False,
    ) -> "WorkflowContext":
        """加载字段语义信息
        
        使用 infer_field_semantic 便捷函数（模块级单例）推断字段语义属性。
        优先检查 data_model 中是否已有缓存的语义结果。
        
        Args:
            force_refresh: 是否强制刷新（跳过缓存）
        
        Returns:
            更新了 field_semantic 的新 WorkflowContext
        """
        if self.data_model is None:
            logger.warning("无法加载字段语义：data_model 为空")
            return self
        
        # 如果已有语义信息且不强制刷新，直接返回
        if self.field_semantic is not None and not force_refresh:
            return self
        
        # 检查 data_model 中是否已有缓存的语义结果
        if not force_refresh and hasattr(self.data_model, '_field_semantic_cache'):
            cached = self.data_model._field_semantic_cache
            if cached:
                logger.info(f"复用 data_model 中缓存的语义结果: {len(cached)} 个字段")
                return self.model_copy(update={"field_semantic": cached})
        
        try:
            # 获取字段列表
            fields = []
            if hasattr(self.data_model, 'fields'):
                fields = self.data_model.fields
            
            if not fields:
                logger.warning("无法加载字段语义：字段列表为空")
                return self
            
            # 使用模块级单例推断字段语义
            result = await infer_field_semantic(
                datasource_luid=self.datasource_luid,
                fields=fields,
            )
            
            # 直接使用 FieldSemanticAttributes 对象，不转换为字典
            semantic_dict = {}
            if result and hasattr(result, 'field_semantic'):
                semantic_dict = result.field_semantic
            
            logger.info(f"字段语义推断完成: {len(semantic_dict)} 个字段")
            
            # 将结果缓存到 data_model 中，供后续复用
            if semantic_dict:
                try:
                    self.data_model._field_semantic_cache = semantic_dict
                except AttributeError:
                    pass  # data_model 不支持动态属性，忽略
            
            # 返回更新后的上下文
            return self.model_copy(update={"field_semantic": semantic_dict})
            
        except Exception as e:
            logger.error(f"字段语义推断失败: {e}")
            return self
    
    def enrich_field_candidates_with_hierarchy(
        self,
        field_candidates: list[Any],
    ) -> list[Any]:
        """使用字段语义信息丰富字段候选
        
        Property 28: Hierarchy Enrichment
        
        将 field_semantic 中的语义信息添加到 FieldCandidate 对象中，
        使 DynamicPromptBuilder 可以在 Prompt 中包含下钻选项。
        
        Args:
            field_candidates: 字段候选列表
        
        Returns:
            丰富了语义信息的字段候选列表
        """
        if not self.field_semantic or not field_candidates:
            return field_candidates
        
        for candidate in field_candidates:
            field_name = getattr(candidate, 'field_name', None)
            if not field_name:
                continue
            
            semantic_info = self.field_semantic.get(field_name)
            if not semantic_info:
                continue
            
            # 设置语义属性（semantic_info 可能是 FieldSemanticAttributes 或 dict）
            if hasattr(candidate, 'hierarchy_category'):
                candidate.hierarchy_category = getattr(semantic_info, 'category', None)
            if hasattr(candidate, 'hierarchy_level'):
                candidate.hierarchy_level = getattr(semantic_info, 'level', None)
            if hasattr(candidate, 'granularity'):
                candidate.granularity = getattr(semantic_info, 'granularity', None)
            if hasattr(candidate, 'parent_dimension'):
                candidate.parent_dimension = getattr(semantic_info, 'parent_dimension', None)
            if hasattr(candidate, 'child_dimension'):
                candidate.child_dimension = getattr(semantic_info, 'child_dimension', None)
            
            # 构建下钻选项
            child_dim = getattr(semantic_info, 'child_dimension', None)
            if hasattr(candidate, 'drill_down_options') and child_dim:
                candidate.drill_down_options = [child_dim]
        
        return field_candidates

def create_workflow_config(
    thread_id: str,
    context: WorkflowContext,
    **extra_configurable: object,
) -> dict[str, Any]:
    """创建工作流配置
    
    Args:
        thread_id: 线程 ID
        context: 工作流上下文
        **extra_configurable: 额外的配置项
        
    Returns:
        RunnableConfig 格式的配置字典
    """
    return {
        "configurable": {
            "thread_id": thread_id,
            "workflow_context": context,
            **extra_configurable,
        }
    }

def get_context(config: Optional[dict[str, Any]]) -> Optional[WorkflowContext]:
    """从 RunnableConfig 获取 WorkflowContext
    
    Args:
        config: RunnableConfig 配置
        
    Returns:
        WorkflowContext 实例，如果不存在则返回 None
    """
    if config is None:
        return None
    configurable = config.get("configurable", {})
    return configurable.get("workflow_context")

def get_context_or_raise(config: Optional[dict[str, Any]]) -> WorkflowContext:
    """从 RunnableConfig 获取 WorkflowContext，不存在则抛出异常
    
    Args:
        config: RunnableConfig 配置
        
    Returns:
        WorkflowContext 实例
        
    Raises:
        ValueError: 如果 config 为 None 或不包含 workflow_context
    """
    if config is None:
        raise ValueError("config is None, cannot get WorkflowContext")
    
    ctx = get_context(config)
    if ctx is None:
        raise ValueError(
            "WorkflowContext not found in config. "
            "Make sure to use create_workflow_config() to create the config."
        )
    return ctx

__all__ = [
    "WorkflowContext",
    "create_workflow_config",
    "get_context",
    "get_context_or_raise",
]
