# -*- coding: utf-8 -*-
"""
预热服务 API 端点

提供维度层级预热相关的 API：
- POST /api/preload/dimension-hierarchy - 启动预热
- GET /api/preload/status/{task_id} - 查询任务状态
- POST /api/preload/invalidate - 使缓存失效
- GET /api/preload/cache-status/{datasource_luid} - 查询缓存状态

设计说明：
- 预热在 Tableau 看板打开时触发（前端调用）
- 维度层级推断耗时较长（30秒+），需要后台异步执行
- 缓存 TTL 为 24 小时
"""
import logging
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tableau_assistant.src.services.preload_service import (
    PreloadService,
    PreloadStatus,
    get_preload_service,
)

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/preload", tags=["preload"])


# ═══════════════════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════

class PreloadRequest(BaseModel):
    """预热请求"""
    datasource_luid: str = Field(..., description="数据源 LUID")
    force: bool = Field(default=False, description="是否强制刷新（忽略缓存）")


class PreloadResponse(BaseModel):
    """预热响应"""
    status: str = Field(..., description="预热状态: pending, loading, ready, failed, expired")
    task_id: Optional[str] = Field(default=None, description="任务 ID（如果启动了新任务）")
    message: Optional[str] = Field(default=None, description="状态消息")
    cached: bool = Field(default=False, description="是否从缓存返回")


class TaskStatusResponse(BaseModel):
    """任务状态响应"""
    task_id: str = Field(..., description="任务 ID")
    status: str = Field(..., description="任务状态")
    progress: Optional[float] = Field(default=None, description="进度百分比 (0-100)")
    message: Optional[str] = Field(default=None, description="状态消息")
    error: Optional[str] = Field(default=None, description="错误信息（如果失败）")


class InvalidateRequest(BaseModel):
    """缓存失效请求"""
    datasource_luid: str = Field(..., description="数据源 LUID")


class InvalidateResponse(BaseModel):
    """缓存失效响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="结果消息")


class CacheStatusResponse(BaseModel):
    """缓存状态响应"""
    datasource_luid: str = Field(..., description="数据源 LUID")
    is_valid: bool = Field(..., description="缓存是否有效")
    status: str = Field(..., description="缓存状态: valid, expired, not_found")
    remaining_ttl_seconds: Optional[float] = Field(default=None, description="剩余 TTL（秒）")
    cached_at: Optional[float] = Field(default=None, description="缓存时间戳")


# ═══════════════════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/dimension-hierarchy",
    response_model=PreloadResponse,
    summary="启动维度层级预热",
    description="在 Tableau 看板打开时调用，启动后台维度层级推断任务"
)
async def start_preload(request: PreloadRequest) -> PreloadResponse:
    """
    启动维度层级预热
    
    流程：
    1. 检查缓存是否有效
    2. 如果有效且 force=False，直接返回 ready
    3. 如果无效或 force=True，启动后台任务
    
    Args:
        request: 预热请求
    
    Returns:
        预热响应，包含状态和任务 ID
    """
    try:
        service = get_preload_service()
        
        # 启动预热（内部会检查缓存）
        task_id, status = await service.start_preload(
            datasource_luid=request.datasource_luid,
            force=request.force
        )
        
        # 构建响应
        if status == PreloadStatus.READY:
            return PreloadResponse(
                status=status.value,
                task_id=None,
                message="维度层级已就绪（从缓存获取）",
                cached=True
            )
        elif status == PreloadStatus.LOADING:
            return PreloadResponse(
                status=status.value,
                task_id=task_id,
                message="维度层级正在加载中",
                cached=False
            )
        elif status == PreloadStatus.EXPIRED:
            return PreloadResponse(
                status=status.value,
                task_id=task_id,
                message="缓存已过期，正在后台刷新",
                cached=False
            )
        else:
            return PreloadResponse(
                status=status.value,
                task_id=task_id,
                message="预热任务已启动",
                cached=False
            )
            
    except Exception as e:
        logger.exception(f"启动预热失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"启动预热失败: {str(e)}"
        )


@router.get(
    "/status/{task_id}",
    response_model=TaskStatusResponse,
    summary="查询预热任务状态",
    description="查询指定任务的执行状态"
)
async def get_task_status(task_id: str) -> TaskStatusResponse:
    """
    查询预热任务状态
    
    Args:
        task_id: 任务 ID
    
    Returns:
        任务状态响应
    """
    try:
        service = get_preload_service()
        status_info = service.get_status(task_id)
        
        if status_info is None:
            raise HTTPException(
                status_code=404,
                detail=f"任务不存在: {task_id}"
            )
        
        return TaskStatusResponse(
            task_id=task_id,
            status=status_info["status"].value,
            progress=status_info.get("progress"),
            message=status_info.get("message"),
            error=status_info.get("error")
        )
        
    except HTTPException:
        raise
    except Exception as e:
        logger.exception(f"查询任务状态失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"查询任务状态失败: {str(e)}"
        )


@router.post(
    "/invalidate",
    response_model=InvalidateResponse,
    summary="使缓存失效",
    description="手动使指定数据源的维度层级缓存失效"
)
async def invalidate_cache(request: InvalidateRequest) -> InvalidateResponse:
    """
    使缓存失效
    
    用于数据源结构变更后强制刷新缓存
    
    Args:
        request: 缓存失效请求
    
    Returns:
        缓存失效响应
    """
    try:
        service = get_preload_service()
        success = service.invalidate_cache(request.datasource_luid)
        
        if success:
            return InvalidateResponse(
                success=True,
                message=f"缓存已失效: {request.datasource_luid}"
            )
        else:
            return InvalidateResponse(
                success=False,
                message=f"缓存失效失败或缓存不存在: {request.datasource_luid}"
            )
            
    except Exception as e:
        logger.exception(f"缓存失效操作失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"缓存失效操作失败: {str(e)}"
        )


@router.get(
    "/cache-status/{datasource_luid}",
    response_model=CacheStatusResponse,
    summary="查询缓存状态",
    description="查询指定数据源的维度层级缓存状态"
)
async def get_cache_status(datasource_luid: str) -> CacheStatusResponse:
    """
    查询缓存状态
    
    Args:
        datasource_luid: 数据源 LUID
    
    Returns:
        缓存状态响应
    """
    try:
        service = get_preload_service()
        cache_info = service.get_cache_status(datasource_luid)
        
        return CacheStatusResponse(
            datasource_luid=datasource_luid,
            is_valid=cache_info["is_valid"],
            status=cache_info["status"],
            remaining_ttl_seconds=cache_info.get("remaining_ttl_seconds"),
            cached_at=cache_info.get("cached_at")
        )
        
    except Exception as e:
        logger.exception(f"查询缓存状态失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"查询缓存状态失败: {str(e)}"
        )
