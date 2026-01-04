# -*- coding: utf-8 -*-
"""
工作流上下文管理

提供统一的依赖容器 WorkflowContext，通过 RunnableConfig 传递给所有节点和工具。

使用示例:
    # 在 WorkflowExecutor 中创建上下文
    ctx = WorkflowContext(
        auth=auth_ctx,
        datasource_luid="ds_12345",
        data_model=data_model,  # 由 DataModelCache 加载
    )
    config = create_workflow_config(thread_id, ctx)
    
    # 在节点中获取上下文
    async def my_node(state, config):
        ctx = get_context_or_raise(config)
        # 使用 ctx.auth, ctx.data_model 等
"""

import logging
from typing import Optional, Dict, Any

from pydantic import BaseModel, Field, ConfigDict
from langgraph.types import RunnableConfig

from tableau_assistant.src.platforms.tableau import TableauAuthContext
from tableau_assistant.src.infra.storage.data_model import DataModel

logger = logging.getLogger(__name__)


class MetadataLoadStatus:
    """元数据加载状态"""
    
    def __init__(
        self,
        source: str,
        hierarchy_inferred: bool = False,
        message: str = ""
    ):
        self.source = source  # "cache", "api"
        self.hierarchy_inferred = hierarchy_inferred
        self.message = message
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "hierarchy_inferred": self.hierarchy_inferred,
            "message": self.message,
        }


class WorkflowContext(BaseModel):
    """
    工作流上下文 - 统一的依赖容器
    
    通过 RunnableConfig["configurable"]["workflow_context"] 传递给所有节点和工具。
    
    Attributes:
        auth: Tableau 认证上下文
        datasource_luid: 数据源 LUID
        tableau_domain: Tableau 域名（多环境支持）
        data_model: 完整的数据模型（由 DataModelCache 加载）
        max_replan_rounds: 最大重规划轮数
        user_id: 用户 ID（可选）
        metadata_load_status: 元数据加载状态
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # 认证（必需）
    auth: TableauAuthContext = Field(description="Tableau 认证上下文")
    
    # 数据源配置（必需）
    datasource_luid: str = Field(description="数据源 LUID")
    
    # Tableau 环境（多环境支持）
    tableau_domain: Optional[str] = Field(default=None, description="Tableau 域名")
    
    # 数据模型（由 DataModelCache 加载）
    data_model: Optional[DataModel] = Field(default=None, description="完整的数据模型")
    
    # 工作流配置
    max_replan_rounds: int = Field(default=3, description="最大重规划轮数")
    user_id: Optional[str] = Field(default=None, description="用户 ID")
    
    # 元数据加载状态
    metadata_load_status: Optional[MetadataLoadStatus] = Field(default=None)
    
    def is_auth_valid(self, buffer_seconds: int = 60) -> bool:
        """检查认证是否有效"""
        return not self.auth.is_expired(buffer_seconds)
    
    async def refresh_auth_if_needed(self) -> "WorkflowContext":
        """如果认证过期，刷新并返回新的上下文"""
        if self.is_auth_valid():
            return self
        
        logger.info("Token 即将过期，正在刷新...")
        
        from tableau_assistant.src.platforms.tableau import get_tableau_auth_async
        new_auth = await get_tableau_auth_async(
            target_domain=self.tableau_domain,
            force_refresh=True
        )
        
        logger.info("Token 刷新成功")
        
        return WorkflowContext(
            auth=new_auth,
            datasource_luid=self.datasource_luid,
            tableau_domain=self.tableau_domain,
            data_model=self.data_model,
            max_replan_rounds=self.max_replan_rounds,
            user_id=self.user_id,
            metadata_load_status=self.metadata_load_status,
        )
    
    @property
    def dimension_hierarchy(self) -> Optional[Dict[str, Any]]:
        """获取维度层级（从 data_model 中提取）"""
        if self.data_model is None:
            return None
        return self.data_model.dimension_hierarchy


def create_workflow_config(
    thread_id: str,
    context: WorkflowContext,
    **extra_configurable: object,
) -> Dict[str, Any]:
    """创建工作流配置"""
    return {
        "configurable": {
            "thread_id": thread_id,
            "workflow_context": context,
            **extra_configurable,
        }
    }


def get_context(config: Optional[RunnableConfig]) -> Optional[WorkflowContext]:
    """从 RunnableConfig 获取 WorkflowContext"""
    if config is None:
        return None
    configurable = config.get("configurable", {})
    return configurable.get("workflow_context")


def get_context_or_raise(config: Optional[RunnableConfig]) -> WorkflowContext:
    """从 RunnableConfig 获取 WorkflowContext，不存在则抛出异常"""
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
    "MetadataLoadStatus",
    "create_workflow_config",
    "get_context",
    "get_context_or_raise",
]
