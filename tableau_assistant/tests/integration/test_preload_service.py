# -*- coding: utf-8 -*-
"""
预热服务集成测试

使用真实 Tableau 环境测试预热服务的完整流程。

测试内容：
1. 预热服务启动和状态查询
2. 缓存命中/未命中场景
3. 强制刷新功能
4. 缓存失效功能
5. 并发预热请求处理

Requirements: 2.1, 2.3
"""

import pytest
import asyncio
import time
from typing import Dict, Any

from tableau_assistant.src.services.preload_service import (
    PreloadService,
    PreloadStatus,
    get_preload_service,
    reset_preload_service,
)
from tableau_assistant.src.capabilities.storage.store_manager import (
    StoreManager,
    get_store_manager,
)
from tableau_assistant.src.config.settings import Settings


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def settings() -> Settings:
    """加载应用配置"""
    return Settings()


@pytest.fixture(scope="module")
def datasource_luid(settings: Settings) -> str:
    """获取数据源 LUID"""
    luid = settings.datasource_luid
    if not luid:
        pytest.skip("DATASOURCE_LUID 未配置")
    return luid


@pytest.fixture(scope="function")
def preload_service() -> PreloadService:
    """创建新的预热服务实例"""
    reset_preload_service()
    return get_preload_service()


@pytest.fixture(scope="module")
def store_manager() -> StoreManager:
    """获取 StoreManager 实例"""
    return get_store_manager()


# ============================================================
# 预热服务基础测试
# ============================================================

class TestPreloadServiceBasic:
    """预热服务基础功能测试"""
    
    @pytest.mark.asyncio
    async def test_start_preload_returns_status(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试启动预热返回正确的状态"""
        task_id, status = await preload_service.start_preload(datasource_luid)
        
        # 状态应该是 READY, LOADING, 或 EXPIRED
        assert status in [
            PreloadStatus.READY,
            PreloadStatus.LOADING,
            PreloadStatus.EXPIRED,
        ], f"意外的状态: {status}"
        
        # 如果是 LOADING，应该返回 task_id
        if status == PreloadStatus.LOADING:
            assert task_id is not None
            print(f"✓ 预热任务已启动: task_id={task_id}")
        elif status == PreloadStatus.READY:
            print(f"✓ 缓存已就绪，无需预热")
        elif status == PreloadStatus.EXPIRED:
            assert task_id is not None
            print(f"✓ 缓存已过期，后台刷新中: task_id={task_id}")
    
    def test_get_cache_status(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试获取缓存状态"""
        cache_status = preload_service.get_cache_status(datasource_luid)
        
        assert "is_valid" in cache_status
        assert "status" in cache_status
        assert "remaining_ttl_seconds" in cache_status
        assert "cached_at" in cache_status
        
        print(f"✓ 缓存状态: {cache_status}")
    
    def test_is_cache_valid(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试缓存有效性检查"""
        is_valid = preload_service.is_cache_valid(datasource_luid)
        
        assert isinstance(is_valid, bool)
        print(f"✓ 缓存有效性: {is_valid}")


# ============================================================
# 预热流程完整测试
# ============================================================

class TestPreloadServiceFlow:
    """预热服务完整流程测试"""
    
    @pytest.mark.asyncio
    async def test_full_preload_flow(
        self,
        preload_service: PreloadService,
        datasource_luid: str,
        store_manager: StoreManager
    ):
        """测试完整的预热流程"""
        print(f"\n开始测试完整预热流程: {datasource_luid}")
        
        # 1. 启动预热
        task_id, status = await preload_service.start_preload(datasource_luid)
        print(f"  1. 启动预热: status={status}, task_id={task_id}")
        
        # 2. 如果正在加载，等待完成
        if status == PreloadStatus.LOADING and task_id:
            print(f"  2. 等待预热完成...")
            start_time = time.time()
            max_wait = 120  # 最多等待 120 秒
            
            while True:
                status_info = preload_service.get_status(task_id)
                if status_info is None:
                    pytest.fail(f"任务不存在: {task_id}")
                
                current_status = status_info["status"]
                progress = status_info.get("progress", 0)
                message = status_info.get("message", "")
                
                print(f"     进度: {progress}% - {message}")
                
                if current_status == PreloadStatus.READY:
                    print(f"  ✓ 预热完成!")
                    break
                elif current_status == PreloadStatus.FAILED:
                    error = status_info.get("error", "未知错误")
                    pytest.fail(f"预热失败: {error}")
                
                elapsed = time.time() - start_time
                if elapsed >= max_wait:
                    pytest.fail(f"预热超时: {elapsed:.1f}s")
                
                await asyncio.sleep(2)
        
        # 3. 验证结果已缓存
        result = preload_service.get_result(datasource_luid)
        assert result is not None, "预热结果应该已缓存"
        
        # 过滤掉内部字段
        filtered = {k: v for k, v in result.items() if not k.startswith("_")}
        print(f"  3. 维度层级已缓存: {len(filtered)} 个维度")
        
        # 4. 验证缓存状态
        cache_status = preload_service.get_cache_status(datasource_luid)
        assert cache_status["is_valid"], "缓存应该有效"
        print(f"  4. 缓存有效，剩余 TTL: {cache_status['remaining_ttl_seconds']:.0f}s")
    
    @pytest.mark.asyncio
    async def test_cache_hit_scenario(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试缓存命中场景"""
        # 先确保有缓存
        task_id1, status1 = await preload_service.start_preload(datasource_luid)
        
        if status1 == PreloadStatus.LOADING and task_id1:
            # 等待完成
            await self._wait_for_completion(preload_service, task_id1)
        
        # 再次请求，应该直接返回 READY
        task_id2, status2 = await preload_service.start_preload(datasource_luid)
        
        assert status2 == PreloadStatus.READY, f"缓存命中时应返回 READY，实际: {status2}"
        assert task_id2 is None, "缓存命中时不应返回 task_id"
        
        print(f"✓ 缓存命中测试通过")
    
    @pytest.mark.asyncio
    async def test_force_refresh(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试强制刷新功能"""
        # 先确保有缓存
        await preload_service.start_preload(datasource_luid)
        
        # 强制刷新
        task_id, status = await preload_service.start_preload(
            datasource_luid,
            force=True
        )
        
        # 强制刷新应该启动新任务
        assert status in [PreloadStatus.LOADING, PreloadStatus.EXPIRED]
        
        if task_id:
            print(f"✓ 强制刷新已启动: task_id={task_id}")
            # 等待完成
            await self._wait_for_completion(preload_service, task_id)
        
        print(f"✓ 强制刷新测试通过")
    
    async def _wait_for_completion(
        self,
        service: PreloadService,
        task_id: str,
        timeout: float = 120
    ):
        """等待任务完成"""
        start_time = time.time()
        
        while True:
            status_info = service.get_status(task_id)
            if status_info is None:
                return
            
            if status_info["status"] == PreloadStatus.READY:
                return
            elif status_info["status"] == PreloadStatus.FAILED:
                raise Exception(f"任务失败: {status_info.get('error')}")
            
            if time.time() - start_time >= timeout:
                raise TimeoutError(f"等待超时: {timeout}s")
            
            await asyncio.sleep(1)


# ============================================================
# 缓存失效测试
# ============================================================

class TestCacheInvalidation:
    """缓存失效功能测试"""
    
    @pytest.mark.asyncio
    async def test_invalidate_cache(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试手动使缓存失效"""
        # 先确保有缓存
        task_id, status = await preload_service.start_preload(datasource_luid)
        
        if status == PreloadStatus.LOADING and task_id:
            await self._wait_for_completion(preload_service, task_id)
        
        # 验证缓存存在
        assert preload_service.is_cache_valid(datasource_luid), "应该有有效缓存"
        
        # 使缓存失效
        success = preload_service.invalidate_cache(datasource_luid)
        assert success, "缓存失效应该成功"
        
        # 验证缓存已失效
        cache_status = preload_service.get_cache_status(datasource_luid)
        assert cache_status["status"] == "not_found", f"缓存应该已失效，实际: {cache_status}"
        
        print(f"✓ 缓存失效测试通过")
    
    async def _wait_for_completion(
        self,
        service: PreloadService,
        task_id: str,
        timeout: float = 120
    ):
        """等待任务完成"""
        start_time = time.time()
        
        while True:
            status_info = service.get_status(task_id)
            if status_info is None:
                return
            
            if status_info["status"] == PreloadStatus.READY:
                return
            elif status_info["status"] == PreloadStatus.FAILED:
                raise Exception(f"任务失败: {status_info.get('error')}")
            
            if time.time() - start_time >= timeout:
                raise TimeoutError(f"等待超时: {timeout}s")
            
            await asyncio.sleep(1)


# ============================================================
# 并发测试
# ============================================================

class TestConcurrentPreload:
    """并发预热请求测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_requests_same_datasource(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试同一数据源的并发请求"""
        # 先使缓存失效
        preload_service.invalidate_cache(datasource_luid)
        
        # 并发发起多个请求
        tasks = [
            preload_service.start_preload(datasource_luid)
            for _ in range(3)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 所有请求应该返回相同的 task_id（或都是 READY）
        task_ids = [r[0] for r in results if r[0] is not None]
        statuses = [r[1] for r in results]
        
        print(f"并发请求结果: task_ids={task_ids}, statuses={statuses}")
        
        # 如果有 task_id，应该都是同一个
        if task_ids:
            assert len(set(task_ids)) == 1, "并发请求应该复用同一个任务"
            print(f"✓ 并发请求复用同一任务: {task_ids[0]}")
        else:
            # 所有请求都命中缓存
            assert all(s == PreloadStatus.READY for s in statuses)
            print(f"✓ 所有请求都命中缓存")


# ============================================================
# 维度层级结果验证
# ============================================================

class TestDimensionHierarchyResult:
    """维度层级结果验证测试"""
    
    @pytest.mark.asyncio
    async def test_hierarchy_structure(
        self,
        preload_service: PreloadService,
        datasource_luid: str
    ):
        """测试维度层级结构正确性"""
        # 确保有缓存
        task_id, status = await preload_service.start_preload(datasource_luid)
        
        if status == PreloadStatus.LOADING and task_id:
            await self._wait_for_completion(preload_service, task_id)
        
        # 获取结果
        result = preload_service.get_result(datasource_luid)
        assert result is not None, "应该有维度层级结果"
        
        # 过滤内部字段
        hierarchy = {k: v for k, v in result.items() if not k.startswith("_")}
        
        print(f"\n维度层级结构验证:")
        print(f"  总维度数: {len(hierarchy)}")
        
        # 验证每个维度的结构
        for field_name, attrs in hierarchy.items():
            assert isinstance(attrs, dict), f"{field_name} 应该是字典"
            
            # 验证必要字段
            assert "category" in attrs, f"{field_name} 缺少 category"
            assert "level" in attrs, f"{field_name} 缺少 level"
            
            print(f"  - {field_name}: category={attrs.get('category')}, level={attrs.get('level')}")
        
        print(f"✓ 维度层级结构验证通过")
    
    async def _wait_for_completion(
        self,
        service: PreloadService,
        task_id: str,
        timeout: float = 120
    ):
        """等待任务完成"""
        start_time = time.time()
        
        while True:
            status_info = service.get_status(task_id)
            if status_info is None:
                return
            
            if status_info["status"] == PreloadStatus.READY:
                return
            elif status_info["status"] == PreloadStatus.FAILED:
                raise Exception(f"任务失败: {status_info.get('error')}")
            
            if time.time() - start_time >= timeout:
                raise TimeoutError(f"等待超时: {timeout}s")
            
            await asyncio.sleep(1)
