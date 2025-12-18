# -*- coding: utf-8 -*-
"""
维度层级预热服务

在 Tableau 看板打开时触发，后台异步执行维度层级推断。

设计说明：
- 预热任务使用 asyncio.create_task 在后台执行
- 缓存使用 StoreManager（SQLite），TTL 24 小时
- 支持强制刷新和手动失效

使用示例：
    service = get_preload_service()
    
    # 启动预热
    task_id, status = await service.start_preload("ds_12345")
    
    # 查询状态
    status_info = service.get_status(task_id)
    
    # 获取结果
    result = service.get_result("ds_12345")
"""
import asyncio
import logging
import time
import uuid
from enum import Enum
from typing import Dict, Any, Optional, Tuple

from tableau_assistant.src.infra.storage import (
    StoreManager,
    get_store_manager,
)

logger = logging.getLogger(__name__)


class PreloadStatus(str, Enum):
    """预热状态枚举"""
    PENDING = "pending"      # 等待开始
    LOADING = "loading"      # 正在加载
    READY = "ready"          # 已就绪
    FAILED = "failed"        # 失败
    EXPIRED = "expired"      # 已过期


class PreloadService:
    """
    维度层级预热服务
    
    负责：
    1. 管理预热任务的生命周期
    2. 检查和管理缓存状态
    3. 后台执行维度层级推断
    """
    
    # 维度层级缓存 TTL（秒）- 24 小时
    HIERARCHY_TTL = 86400
    
    def __init__(self, store: Optional[StoreManager] = None):
        """
        初始化预热服务
        
        Args:
            store: StoreManager 实例（可选，默认使用全局单例）
        """
        self._store = store or get_store_manager()
        
        # 任务状态缓存（内存中）
        # task_id -> {status, progress, message, error, datasource_luid, started_at}
        self._tasks: Dict[str, Dict[str, Any]] = {}
        
        # 正在执行的任务（防止重复启动）
        # datasource_luid -> task_id
        self._running_tasks: Dict[str, str] = {}
        
        # 锁（保护并发访问）
        self._lock = asyncio.Lock()
    
    async def start_preload(
        self,
        datasource_luid: str,
        force: bool = False
    ) -> Tuple[Optional[str], PreloadStatus]:
        """
        启动预热任务
        
        Args:
            datasource_luid: 数据源 LUID
            force: 是否强制刷新（忽略缓存）
        
        Returns:
            (task_id, status) 元组
            - 如果缓存有效且 force=False，返回 (None, READY)
            - 如果启动了新任务，返回 (task_id, LOADING)
            - 如果任务已在运行，返回 (existing_task_id, LOADING)
        """
        async with self._lock:
            # 1. 检查是否有正在运行的任务
            if datasource_luid in self._running_tasks:
                task_id = self._running_tasks[datasource_luid]
                logger.info(f"预热任务已在运行: {datasource_luid}, task_id={task_id}")
                return task_id, PreloadStatus.LOADING
            
            # 2. 检查缓存状态
            if not force:
                cache_status = self.get_cache_status(datasource_luid)
                
                if cache_status["status"] == "valid":
                    logger.info(f"缓存有效，跳过预热: {datasource_luid}")
                    return None, PreloadStatus.READY
                
                if cache_status["status"] == "expired":
                    logger.info(f"缓存已过期，启动后台刷新: {datasource_luid}")
                    # 继续启动任务，但返回 EXPIRED 状态
                    task_id = self._create_task(datasource_luid)
                    return task_id, PreloadStatus.EXPIRED
            
            # 3. 启动新任务
            task_id = self._create_task(datasource_luid)
            logger.info(f"启动预热任务: {datasource_luid}, task_id={task_id}")
            
            return task_id, PreloadStatus.LOADING
    
    def _create_task(self, datasource_luid: str) -> str:
        """创建并启动后台任务"""
        task_id = f"preload_{uuid.uuid4().hex[:8]}"
        
        # 初始化任务状态
        self._tasks[task_id] = {
            "status": PreloadStatus.LOADING,
            "progress": 0,
            "message": "正在初始化...",
            "error": None,
            "datasource_luid": datasource_luid,
            "started_at": time.time(),
        }
        
        # 记录正在运行的任务
        self._running_tasks[datasource_luid] = task_id
        
        # 启动后台任务
        asyncio.create_task(self._execute_preload(task_id, datasource_luid))
        
        return task_id
    
    async def _execute_preload(self, task_id: str, datasource_luid: str) -> None:
        """
        执行预热任务（后台）
        
        流程：
        1. 获取 Tableau 认证
        2. 调用 Metadata API 获取字段信息
        3. 调用 dimension_hierarchy_node Agent 推断
        4. 缓存结果到 StoreManager
        """
        try:
            # 更新进度
            self._update_task(task_id, progress=10, message="正在获取认证...")
            
            # 1. 获取 Tableau 认证
            from tableau_assistant.src.platforms.tableau import get_tableau_auth_async
            auth_ctx = await get_tableau_auth_async()
            
            self._update_task(task_id, progress=20, message="正在获取元数据...")
            
            # 2. 获取元数据
            from tableau_assistant.src.platforms.tableau.metadata import (
                get_datasource_metadata,
            )
            
            raw_metadata = await get_datasource_metadata(
                datasource_luid=datasource_luid,
                tableau_token=auth_ctx.api_key,
                tableau_site=auth_ctx.site,
                tableau_domain=auth_ctx.domain,
            )
            
            self._update_task(task_id, progress=50, message="正在推断维度层级...")
            
            # 3. 调用维度层级推断 Agent
            from tableau_assistant.src.agents.dimension_hierarchy.node import (
                dimension_hierarchy_node,
            )
            from tableau_assistant.src.core.models import Metadata, FieldMetadata
            
            # 转换为 Metadata 对象
            fields = [
                FieldMetadata(**f) for f in raw_metadata.get("fields", [])
            ]
            metadata = Metadata(
                datasource_luid=datasource_luid,
                datasource_name=raw_metadata.get("datasource_name", "Unknown"),
                fields=fields,
                field_count=len(fields),
            )
            
            # 执行推断
            result = await dimension_hierarchy_node(
                metadata=metadata,
                datasource_luid=datasource_luid,
            )
            
            self._update_task(task_id, progress=90, message="正在保存缓存...")
            
            # 4. 转换并缓存结果
            hierarchy_dict = {}
            for field_name, attrs in result.dimension_hierarchy.items():
                hierarchy_dict[field_name] = attrs.model_dump()
            
            self._store.put_dimension_hierarchy(datasource_luid, hierarchy_dict)
            
            # 5. 完成
            self._update_task(
                task_id,
                status=PreloadStatus.READY,
                progress=100,
                message="预热完成"
            )
            
            logger.info(f"预热完成: {datasource_luid}, task_id={task_id}")
            
        except Exception as e:
            logger.exception(f"预热失败: {datasource_luid}, task_id={task_id}, error={e}")
            self._update_task(
                task_id,
                status=PreloadStatus.FAILED,
                progress=0,
                message="预热失败",
                error=str(e)
            )
        
        finally:
            # 清理正在运行的任务记录
            async with self._lock:
                if datasource_luid in self._running_tasks:
                    del self._running_tasks[datasource_luid]
    
    def _update_task(
        self,
        task_id: str,
        status: Optional[PreloadStatus] = None,
        progress: Optional[float] = None,
        message: Optional[str] = None,
        error: Optional[str] = None
    ) -> None:
        """更新任务状态"""
        if task_id not in self._tasks:
            return
        
        if status is not None:
            self._tasks[task_id]["status"] = status
        if progress is not None:
            self._tasks[task_id]["progress"] = progress
        if message is not None:
            self._tasks[task_id]["message"] = message
        if error is not None:
            self._tasks[task_id]["error"] = error
    
    def get_status(self, task_id: str) -> Optional[Dict[str, Any]]:
        """
        获取任务状态
        
        Args:
            task_id: 任务 ID
        
        Returns:
            任务状态字典，如果任务不存在返回 None
        """
        return self._tasks.get(task_id)
    
    def get_result(self, datasource_luid: str) -> Optional[Dict[str, Any]]:
        """
        获取预热结果（从缓存）
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            维度层级字典，如果不存在返回 None
        """
        return self._store.get_dimension_hierarchy(datasource_luid)
    
    def invalidate_cache(self, datasource_luid: str) -> bool:
        """
        使缓存失效
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            是否成功
        """
        try:
            self._store.clear_dimension_hierarchy_cache(datasource_luid)
            logger.info(f"缓存已失效: {datasource_luid}")
            return True
        except Exception as e:
            logger.error(f"缓存失效失败: {datasource_luid}, error={e}")
            return False
    
    def is_cache_valid(self, datasource_luid: str) -> bool:
        """
        检查缓存是否有效
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            缓存是否有效
        """
        cache_status = self.get_cache_status(datasource_luid)
        return cache_status["is_valid"]
    
    def get_cache_status(self, datasource_luid: str) -> Dict[str, Any]:
        """
        获取缓存状态
        
        Args:
            datasource_luid: 数据源 LUID
        
        Returns:
            缓存状态字典：
            - is_valid: 是否有效
            - status: "valid", "expired", "not_found"
            - remaining_ttl_seconds: 剩余 TTL（秒）
            - cached_at: 缓存时间戳
        """
        hierarchy = self._store.get_dimension_hierarchy(datasource_luid)
        
        if hierarchy is None:
            return {
                "is_valid": False,
                "status": "not_found",
                "remaining_ttl_seconds": None,
                "cached_at": None,
            }
        
        # 检查 TTL
        cached_at = hierarchy.get("_cached_at", 0)
        elapsed = time.time() - cached_at
        remaining = self.HIERARCHY_TTL - elapsed
        
        if remaining <= 0:
            return {
                "is_valid": False,
                "status": "expired",
                "remaining_ttl_seconds": 0,
                "cached_at": cached_at,
            }
        
        return {
            "is_valid": True,
            "status": "valid",
            "remaining_ttl_seconds": remaining,
            "cached_at": cached_at,
        }


# ═══════════════════════════════════════════════════════════════════════════
# 全局实例管理
# ═══════════════════════════════════════════════════════════════════════════

_global_preload_service: Optional[PreloadService] = None


def get_preload_service() -> PreloadService:
    """
    获取全局 PreloadService 实例
    
    Returns:
        PreloadService 实例
    """
    global _global_preload_service
    
    if _global_preload_service is None:
        _global_preload_service = PreloadService()
    
    return _global_preload_service


def reset_preload_service() -> None:
    """重置全局实例（主要用于测试）"""
    global _global_preload_service
    _global_preload_service = None
