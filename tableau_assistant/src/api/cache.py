# -*- coding: utf-8 -*-
"""
缓存管理 API 端点

提供数据模型缓存相关的 API：
- POST /api/cache/invalidate - 使缓存失效
- GET /api/cache/status/{datasource_luid} - 查询缓存状态
- POST /api/cache/preload - 预加载数据模型（替代旧的预热服务）

设计说明：
- 使用 DataModelCache 和 LangGraph SqliteStore 实现持久化缓存
- 缓存 TTL 为 24 小时
- 支持手动失效和预加载

Requirements: 4.2, 4.3
"""
import logging
import time
from typing import Optional

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel, Field

from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
from tableau_assistant.src.platforms.tableau import TableauDataModelLoader

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/api/cache", tags=["cache"])


# ═══════════════════════════════════════════════════════════════════════════
# 请求/响应模型
# ═══════════════════════════════════════════════════════════════════════════

class InvalidateRequest(BaseModel):
    """缓存失效请求"""
    datasource_luid: str = Field(..., description="数据源 LUID")


class InvalidateResponse(BaseModel):
    """缓存失效响应"""
    success: bool = Field(..., description="是否成功")
    message: str = Field(..., description="结果消息")
    datasource_luid: str = Field(..., description="数据源 LUID")


class CacheStatusResponse(BaseModel):
    """缓存状态响应"""
    datasource_luid: str = Field(..., description="数据源 LUID")
    is_cached: bool = Field(..., description="是否已缓存")
    field_count: Optional[int] = Field(default=None, description="字段数量")
    has_hierarchy: bool = Field(default=False, description="是否有维度层级")
    hierarchy_count: Optional[int] = Field(default=None, description="维度层级数量")


class PreloadRequest(BaseModel):
    """预加载请求"""
    datasource_luid: str = Field(..., description="数据源 LUID")
    force: bool = Field(default=False, description="是否强制刷新（忽略缓存）")


class PreloadResponse(BaseModel):
    """预加载响应"""
    success: bool = Field(..., description="是否成功")
    is_cache_hit: bool = Field(..., description="是否命中缓存")
    datasource_luid: str = Field(..., description="数据源 LUID")
    field_count: int = Field(..., description="字段数量")
    hierarchy_count: int = Field(..., description="维度层级数量")
    duration_ms: float = Field(..., description="耗时（毫秒）")
    message: str = Field(..., description="结果消息")


# ═══════════════════════════════════════════════════════════════════════════
# API 端点
# ═══════════════════════════════════════════════════════════════════════════

@router.post(
    "/invalidate",
    response_model=InvalidateResponse,
    summary="使缓存失效",
    description="手动使指定数据源的数据模型缓存失效"
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
        store = get_langgraph_store()
        cache = DataModelCache(store)
        
        success = cache.invalidate(request.datasource_luid)
        
        if success:
            return InvalidateResponse(
                success=True,
                message=f"缓存已失效: {request.datasource_luid}",
                datasource_luid=request.datasource_luid
            )
        else:
            return InvalidateResponse(
                success=False,
                message=f"缓存失效失败: {request.datasource_luid}",
                datasource_luid=request.datasource_luid
            )
            
    except Exception as e:
        logger.exception(f"缓存失效操作失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"缓存失效操作失败: {str(e)}"
        )


@router.get(
    "/status/{datasource_luid}",
    response_model=CacheStatusResponse,
    summary="查询缓存状态",
    description="查询指定数据源的数据模型缓存状态"
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
        store = get_langgraph_store()
        cache = DataModelCache(store)
        
        # 尝试从缓存获取
        data_model = cache._get_from_cache(datasource_luid)
        
        if data_model is None:
            return CacheStatusResponse(
                datasource_luid=datasource_luid,
                is_cached=False,
                field_count=None,
                has_hierarchy=False,
                hierarchy_count=None
            )
        
        hierarchy_count = len(data_model.dimension_hierarchy) if data_model.dimension_hierarchy else 0
        
        return CacheStatusResponse(
            datasource_luid=datasource_luid,
            is_cached=True,
            field_count=data_model.field_count,
            has_hierarchy=hierarchy_count > 0,
            hierarchy_count=hierarchy_count
        )
        
    except Exception as e:
        logger.exception(f"查询缓存状态失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"查询缓存状态失败: {str(e)}"
        )


@router.post(
    "/preload",
    response_model=PreloadResponse,
    summary="预加载数据模型",
    description="预加载指定数据源的数据模型（包含维度层级推断）"
)
async def preload_data_model(request: PreloadRequest) -> PreloadResponse:
    """
    预加载数据模型
    
    流程：
    1. 如果 force=True，先使缓存失效
    2. 调用 DataModelCache.get_or_load() 加载数据模型
    3. 返回加载结果
    
    Args:
        request: 预加载请求
    
    Returns:
        预加载响应
    """
    try:
        from tableau_assistant.src.platforms.tableau import get_tableau_auth_async
        
        start_time = time.time()
        
        store = get_langgraph_store()
        cache = DataModelCache(store)
        
        # 如果强制刷新，先使缓存失效
        if request.force:
            cache.invalidate(request.datasource_luid)
            logger.info(f"强制刷新，已使缓存失效: {request.datasource_luid}")
        
        # 获取 Tableau 认证
        auth_ctx = await get_tableau_auth_async()
        
        # 创建加载器
        loader = TableauDataModelLoader(auth_ctx)
        
        # 加载数据模型
        data_model, is_cache_hit = await cache.get_or_load(
            request.datasource_luid,
            loader
        )
        
        duration_ms = (time.time() - start_time) * 1000
        hierarchy_count = len(data_model.dimension_hierarchy) if data_model.dimension_hierarchy else 0
        
        return PreloadResponse(
            success=True,
            is_cache_hit=is_cache_hit,
            datasource_luid=request.datasource_luid,
            field_count=data_model.field_count,
            hierarchy_count=hierarchy_count,
            duration_ms=duration_ms,
            message="从缓存加载" if is_cache_hit else "从 API 加载并缓存"
        )
        
    except Exception as e:
        logger.exception(f"预加载数据模型失败: {e}")
        raise HTTPException(
            status_code=500,
            detail=f"预加载数据模型失败: {str(e)}"
        )
