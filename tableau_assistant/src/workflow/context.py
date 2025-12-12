# -*- coding: utf-8 -*-
"""
工作流上下文管理

提供统一的依赖容器 WorkflowContext，通过 RunnableConfig 传递给所有节点和工具。
消除全局变量和重复的认证获取。

使用示例:
    # 在 WorkflowExecutor 中创建上下文
    ctx = WorkflowContext(
        auth=auth_ctx,
        store=store,
        datasource_luid="ds_12345",
    )
    ctx = await ctx.ensure_metadata_loaded()
    config = create_workflow_config(thread_id, ctx)
    
    # 在节点中获取上下文
    async def my_node(state, config):
        ctx = get_context_or_raise(config)
        # 使用 ctx.auth, ctx.store, ctx.metadata 等
"""

import logging
from typing import Optional, Dict, Any, TYPE_CHECKING

from pydantic import BaseModel, Field, ConfigDict

# 运行时导入（Pydantic 需要这些类型来验证）
from tableau_assistant.src.bi_platforms.tableau import TableauAuthContext
from tableau_assistant.src.capabilities.storage import StoreManager
from tableau_assistant.src.models.metadata import Metadata

if TYPE_CHECKING:
    from langgraph.types import RunnableConfig

logger = logging.getLogger(__name__)


class MetadataLoadStatus:
    """元数据加载状态，用于通知用户"""
    
    def __init__(
        self,
        source: str,
        is_preloading: bool = False,
        waited_seconds: float = 0,
        hierarchy_inferred: bool = False,
        message: str = ""
    ):
        self.source = source  # "cache", "preload", "sync"
        self.is_preloading = is_preloading  # 是否正在预热
        self.waited_seconds = waited_seconds  # 等待预热的时间
        self.hierarchy_inferred = hierarchy_inferred  # 是否重新推断了维度层级
        self.message = message  # 状态消息
    
    def to_dict(self) -> Dict[str, Any]:
        return {
            "source": self.source,
            "is_preloading": self.is_preloading,
            "waited_seconds": self.waited_seconds,
            "hierarchy_inferred": self.hierarchy_inferred,
            "message": self.message,
        }


class WorkflowContext(BaseModel):
    """
    工作流上下文 - 统一的依赖容器
    
    通过 RunnableConfig["configurable"]["workflow_context"] 传递给所有节点和工具。
    这是唯一的依赖注入点，消除全局变量和重复获取。
    
    数据模型说明：
    - metadata: 完整的数据模型，包含：
      - fields: 字段元数据列表（FieldMetadata）
      - dimension_hierarchy: 维度层级结构
      - data_model: 逻辑表和表关系（DataModel）
      - datasource_name, datasource_description 等
    
    Attributes:
        auth: Tableau 认证上下文
        store: 持久化存储管理器
        datasource_luid: 数据源 LUID
        metadata: 完整的数据模型（在工作流启动时加载）
        max_replan_rounds: 最大重规划轮数
        user_id: 用户 ID（可选）
        metadata_load_status: 元数据加载状态（用于通知用户）
    """
    model_config = ConfigDict(arbitrary_types_allowed=True)
    
    # 认证（必需）
    auth: TableauAuthContext = Field(description="Tableau 认证上下文")
    
    # 存储（必需）
    store: StoreManager = Field(description="持久化存储管理器")
    
    # 数据源配置（必需）
    datasource_luid: str = Field(description="数据源 LUID")
    
    # 数据模型（在工作流启动时加载，所有节点共享）
    metadata: Optional[Metadata] = Field(default=None, description="完整的数据模型")
    
    # 工作流配置
    max_replan_rounds: int = Field(default=3, description="最大重规划轮数")
    user_id: Optional[str] = Field(default=None, description="用户 ID")
    
    # 元数据加载状态（用于通知用户）
    metadata_load_status: Optional[MetadataLoadStatus] = Field(
        default=None, 
        description="元数据加载状态"
    )
    
    def is_auth_valid(self, buffer_seconds: int = 60) -> bool:
        """
        检查认证是否有效
        
        Args:
            buffer_seconds: 提前多少秒认为过期（默认60秒）
        
        Returns:
            True 如果认证有效，False 如果即将过期或已过期
        """
        return not self.auth.is_expired(buffer_seconds)
    
    async def refresh_auth_if_needed(self) -> "WorkflowContext":  # noqa: F821
        """
        如果认证过期，刷新并返回新的上下文
        
        WorkflowContext 是不可变的，刷新时返回新实例。
        
        Returns:
            新的 WorkflowContext（如果刷新了）或 self（如果未过期）
        """
        if self.is_auth_valid():
            return self
        
        logger.info("Token 即将过期，正在刷新...")
        
        from tableau_assistant.src.bi_platforms.tableau import get_tableau_auth_async
        new_auth = await get_tableau_auth_async(force_refresh=True)
        
        logger.info("Token 刷新成功")
        
        return WorkflowContext(
            auth=new_auth,
            store=self.store,
            datasource_luid=self.datasource_luid,
            metadata=self.metadata,
            max_replan_rounds=self.max_replan_rounds,
            user_id=self.user_id,
        )

    async def ensure_metadata_loaded(self, timeout: float = 60.0) -> "WorkflowContext":
        """
        确保数据模型已加载（包含维度层级推断）
        
        流程:
        1. 如果 metadata 已存在，检查维度层级是否为空
        2. 检查预热服务状态:
           - 如果 READY，从缓存获取
           - 如果 LOADING，等待完成（带超时），并通知用户
           - 如果 PENDING/FAILED/EXPIRED，同步执行加载
        3. 如果维度层级为空，重新推断
        
        Args:
            timeout: 等待预热完成的超时时间（秒）
        
        Returns:
            新的 WorkflowContext（包含 metadata）或 self（如果已加载）
        """
        import asyncio
        
        # 如果 metadata 已存在，检查维度层级
        if self.metadata is not None:
            if self.metadata.dimension_hierarchy:
                return self
            # 维度层级为空，需要重新推断
            logger.info(f"维度层级为空，重新推断: {self.datasource_luid}")
            metadata = await self._ensure_hierarchy_exists(self.metadata)
            return self._with_metadata(
                metadata,
                MetadataLoadStatus(
                    source="cache",
                    hierarchy_inferred=True,
                    message="维度层级为空，已重新推断"
                )
            )
        
        logger.info(f"加载数据模型: {self.datasource_luid}")
        
        # 1. 检查预热服务状态
        from tableau_assistant.src.services.preload_service import (
            get_preload_service,
            PreloadStatus,
        )
        
        preload_service = get_preload_service()
        cache_status = preload_service.get_cache_status(self.datasource_luid)
        
        # 2. 如果缓存有效，直接从 store 获取
        if cache_status["is_valid"]:
            logger.info(f"从缓存获取数据模型: {self.datasource_luid}")
            metadata = await self._load_metadata_from_cache()
            if metadata:
                # 检查维度层级是否为空
                if not metadata.dimension_hierarchy:
                    logger.info(f"缓存中维度层级为空，重新推断")
                    metadata = await self._ensure_hierarchy_exists(metadata)
                    return self._with_metadata(
                        metadata,
                        MetadataLoadStatus(
                            source="cache",
                            hierarchy_inferred=True,
                            message="从缓存加载，维度层级已重新推断"
                        )
                    )
                return self._with_metadata(
                    metadata,
                    MetadataLoadStatus(
                        source="cache",
                        message="从缓存加载"
                    )
                )
        
        # 3. 检查是否有正在运行的预热任务
        task_id, status = await preload_service.start_preload(
            datasource_luid=self.datasource_luid,
            force=False
        )
        
        if status == PreloadStatus.READY:
            # 预热已完成，从缓存获取
            metadata = await self._load_metadata_from_cache()
            if metadata:
                if not metadata.dimension_hierarchy:
                    metadata = await self._ensure_hierarchy_exists(metadata)
                    return self._with_metadata(
                        metadata,
                        MetadataLoadStatus(
                            source="preload",
                            hierarchy_inferred=True,
                            message="预热完成，维度层级已重新推断"
                        )
                    )
                return self._with_metadata(
                    metadata,
                    MetadataLoadStatus(
                        source="preload",
                        message="预热完成"
                    )
                )
        
        elif status == PreloadStatus.LOADING and task_id:
            # 等待预热完成，并记录等待时间
            logger.info(f"正在等待预热完成: {self.datasource_luid}, task_id={task_id}")
            start_time = asyncio.get_event_loop().time()
            
            metadata = await self._wait_for_preload(task_id, timeout)
            
            waited_seconds = asyncio.get_event_loop().time() - start_time
            
            if metadata:
                if not metadata.dimension_hierarchy:
                    metadata = await self._ensure_hierarchy_exists(metadata)
                    return self._with_metadata(
                        metadata,
                        MetadataLoadStatus(
                            source="preload",
                            is_preloading=True,
                            waited_seconds=waited_seconds,
                            hierarchy_inferred=True,
                            message=f"等待预热 {waited_seconds:.1f}s，维度层级已重新推断"
                        )
                    )
                return self._with_metadata(
                    metadata,
                    MetadataLoadStatus(
                        source="preload",
                        is_preloading=True,
                        waited_seconds=waited_seconds,
                        message=f"等待预热 {waited_seconds:.1f}s 完成"
                    )
                )
        
        # 4. 预热失败或超时，同步加载
        logger.info(f"同步加载数据模型: {self.datasource_luid}")
        metadata = await self._load_metadata_sync()
        
        return self._with_metadata(
            metadata,
            MetadataLoadStatus(
                source="sync",
                hierarchy_inferred=True,
                message="同步加载完成（包含维度层级推断）"
            )
        )
    
    async def _load_metadata_from_cache(self) -> Optional["Metadata"]:
        """从缓存加载 metadata"""
        # 获取 metadata
        metadata = self.store.get_metadata(self.datasource_luid)
        if metadata is None:
            return None
        
        # 获取维度层级并注入
        hierarchy = self.store.get_dimension_hierarchy(self.datasource_luid)
        if hierarchy:
            # 过滤掉内部字段
            filtered = {k: v for k, v in hierarchy.items() if not k.startswith("_")}
            metadata.dimension_hierarchy = filtered
        
        return metadata
    
    async def _ensure_hierarchy_exists(self, metadata: "Metadata") -> "Metadata":
        """
        确保维度层级存在，如果为空则重新推断
        
        Args:
            metadata: Metadata 对象
        
        Returns:
            包含维度层级的 Metadata 对象
        """
        if metadata.dimension_hierarchy:
            return metadata
        
        logger.info(f"推断维度层级: {self.datasource_luid}")
        
        try:
            from tableau_assistant.src.agents.dimension_hierarchy.node import (
                dimension_hierarchy_node,
            )
            
            result = await dimension_hierarchy_node(
                metadata=metadata,
                datasource_luid=self.datasource_luid,
            )
            
            hierarchy_dict = {}
            for field_name, attrs in result.dimension_hierarchy.items():
                hierarchy_dict[field_name] = attrs.model_dump()
            
            # 缓存维度层级
            self.store.put_dimension_hierarchy(self.datasource_luid, hierarchy_dict)
            metadata.dimension_hierarchy = hierarchy_dict
            
            logger.info(f"维度层级推断完成: {len(hierarchy_dict)} 个维度")
            
        except Exception as e:
            logger.error(f"维度层级推断失败: {e}")
            # 设置为空字典，避免重复推断
            metadata.dimension_hierarchy = {}
        
        return metadata
    
    async def _wait_for_preload(
        self,
        task_id: str,
        timeout: float
    ) -> Optional["Metadata"]:
        """等待预热任务完成"""
        import asyncio
        from tableau_assistant.src.services.preload_service import (
            get_preload_service,
            PreloadStatus,
        )
        
        preload_service = get_preload_service()
        start_time = asyncio.get_event_loop().time()
        
        while True:
            status_info = preload_service.get_status(task_id)
            if status_info is None:
                logger.warning(f"预热任务不存在: {task_id}")
                return None
            
            status = status_info["status"]
            
            if status == PreloadStatus.READY:
                logger.info(f"预热完成: {task_id}")
                return await self._load_metadata_from_cache()
            
            if status == PreloadStatus.FAILED:
                logger.warning(f"预热失败: {task_id}, error={status_info.get('error')}")
                return None
            
            # 检查超时
            elapsed = asyncio.get_event_loop().time() - start_time
            if elapsed >= timeout:
                logger.warning(f"等待预热超时: {task_id}, elapsed={elapsed:.1f}s")
                return None
            
            # 等待一段时间后重试
            await asyncio.sleep(1.0)
    
    async def _load_metadata_sync(self) -> "Metadata":
        """同步加载 metadata（不使用预热服务）"""
        from tableau_assistant.src.capabilities.data_model.manager import (
            get_datasource_metadata,
        )
        from tableau_assistant.src.models.metadata import Metadata, FieldMetadata
        from tableau_assistant.src.agents.dimension_hierarchy.node import (
            dimension_hierarchy_node,
        )
        
        # 1. 获取元数据
        raw_metadata = await get_datasource_metadata(
            datasource_luid=self.datasource_luid,
            tableau_token=self.auth.api_key,
            tableau_site=self.auth.site,
            tableau_domain=self.auth.domain,
        )
        
        # 2. 转换为 Metadata 对象
        fields = [FieldMetadata(**f) for f in raw_metadata.get("fields", [])]
        metadata = Metadata(
            datasource_luid=self.datasource_luid,
            datasource_name=raw_metadata.get("datasource_name", "Unknown"),
            datasource_description=raw_metadata.get("datasource_description"),
            datasource_owner=raw_metadata.get("datasource_owner"),
            fields=fields,
            field_count=len(fields),
            data_model=raw_metadata.get("data_model"),
            raw_response=raw_metadata.get("raw_response"),
        )
        
        # 3. 缓存 metadata
        self.store.put_metadata(self.datasource_luid, metadata)
        
        # 4. 推断维度层级
        try:
            result = await dimension_hierarchy_node(
                metadata=metadata,
                datasource_luid=self.datasource_luid,
            )
            
            hierarchy_dict = {}
            for field_name, attrs in result.dimension_hierarchy.items():
                hierarchy_dict[field_name] = attrs.model_dump()
            
            # 缓存维度层级
            self.store.put_dimension_hierarchy(self.datasource_luid, hierarchy_dict)
            metadata.dimension_hierarchy = hierarchy_dict
            
        except Exception as e:
            logger.warning(f"维度层级推断失败: {e}")
            # 继续使用没有维度层级的 metadata
        
        return metadata
    
    def _with_metadata(
        self,
        metadata: "Metadata",
        load_status: Optional[MetadataLoadStatus] = None
    ) -> "WorkflowContext":
        """创建包含 metadata 的新 WorkflowContext"""
        hierarchy_count = len(metadata.dimension_hierarchy) if metadata.dimension_hierarchy else 0
        logger.info(
            f"数据模型加载完成: {metadata.field_count} 个字段, "
            f"{hierarchy_count} 个维度层级"
        )
        
        if load_status:
            logger.info(f"加载状态: {load_status.message}")
        
        return WorkflowContext(
            auth=self.auth,
            store=self.store,
            datasource_luid=self.datasource_luid,
            metadata=metadata,
            max_replan_rounds=self.max_replan_rounds,
            user_id=self.user_id,
            metadata_load_status=load_status,
        )
    
    @property
    def dimension_hierarchy(self) -> Optional[Dict[str, Any]]:
        """
        获取维度层级（从 metadata 中提取）
        
        Returns:
            维度层级字典，如果 metadata 未加载则返回 None
        """
        if self.metadata is None:
            return None
        return self.metadata.dimension_hierarchy


# ═══════════════════════════════════════════════════════════════════════════
# RunnableConfig 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def create_workflow_config(
    thread_id: str,
    context: WorkflowContext,
    **extra_configurable: object,
) -> Dict[str, Any]:
    """
    创建工作流配置
    
    所有节点和工具都可以通过 config["configurable"]["workflow_context"] 访问上下文。
    
    Args:
        thread_id: 线程/会话 ID
        context: WorkflowContext 实例
        **extra_configurable: 额外的配置项
    
    Returns:
        RunnableConfig 字典
    
    Example:
        config = create_workflow_config("thread_123", ctx)
        result = await workflow.ainvoke(state, config)
    """
    return {
        "configurable": {
            "thread_id": thread_id,
            "workflow_context": context,
            # 保持向后兼容：同时提供 tableau_auth
            "tableau_auth": context.auth.model_dump(),
            **extra_configurable,
        }
    }


def get_context(config: Optional["RunnableConfig"]) -> Optional[WorkflowContext]:
    """
    从 RunnableConfig 获取 WorkflowContext
    
    Args:
        config: RunnableConfig 配置
    
    Returns:
        WorkflowContext 或 None（如果不存在）
    
    Example:
        ctx = get_context(config)
        if ctx:
            auth = ctx.auth
            store = ctx.store
    """
    if config is None:
        return None
    
    configurable = config.get("configurable", {})
    return configurable.get("workflow_context")


def get_context_or_raise(config: Optional["RunnableConfig"]) -> WorkflowContext:
    """
    从 RunnableConfig 获取 WorkflowContext，如果不存在则抛出异常
    
    Args:
        config: RunnableConfig 配置
    
    Returns:
        WorkflowContext
    
    Raises:
        ValueError: 如果 config 为 None 或不包含 workflow_context
    
    Example:
        ctx = get_context_or_raise(config)
        # 安全使用 ctx.auth, ctx.store 等
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


# ═══════════════════════════════════════════════════════════════════════════
# 导出
# ═══════════════════════════════════════════════════════════════════════════

__all__ = [
    "WorkflowContext",
    "MetadataLoadStatus",
    "create_workflow_config",
    "get_context",
    "get_context_or_raise",
]
