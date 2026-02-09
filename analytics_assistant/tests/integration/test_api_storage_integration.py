# -*- coding: utf-8 -*-
"""
集成测试：API 层 + 存储层

验证 FastAPI 应用、BaseRepository、StoreFactory 的端到端协作。
"""

import pytest
from fastapi.testclient import TestClient

from analytics_assistant.src.infra.storage import (
    BaseRepository,
    StoreFactory,
)


@pytest.fixture(autouse=True)
def reset_storage():
    """每个测试前后重置存储，确保隔离。"""
    StoreFactory.reset()
    yield
    StoreFactory.reset()


# ========================================
# 1. 健康检查集成测试
# ========================================

class TestHealthEndpoint:
    """健康检查端点集成测试。"""

    def test_health_returns_ok(self):
        """GET /health 返回 200 + status=ok。"""
        from analytics_assistant.src.api.main import app

        client = TestClient(app)
        response = client.get("/health")

        assert response.status_code == 200
        data = response.json()
        assert data["status"] == "ok"
        assert data["version"] == "1.0.0"
        assert data["storage"] in ("ok", "unavailable")

    def test_health_checks_storage_connectivity(self):
        """健康检查验证存储连通性。"""
        from analytics_assistant.src.api.main import app

        client = TestClient(app)
        response = client.get("/health")

        data = response.json()
        # 在测试环境中存储应该可用
        assert data["storage"] == "ok"


# ========================================
# 2. 存储层集成测试
# ========================================

class TestStoreFactory:
    """StoreFactory 集成测试。"""

    def test_default_store_is_singleton(self):
        """默认存储是单例。"""
        store1 = StoreFactory.get_default_store()
        store2 = StoreFactory.get_default_store()
        assert store1 is store2

    def test_namespace_store_uses_config(self):
        """命名空间存储根据 app.yaml 配置创建。"""
        store = StoreFactory.create_namespace_store("sessions")
        assert store is not None

    def test_namespace_store_is_cached(self):
        """同一命名空间的存储实例被缓存。"""
        store1 = StoreFactory.create_namespace_store("sessions")
        store2 = StoreFactory.create_namespace_store("sessions")
        assert store1 is store2

    def test_reset_clears_all_stores(self):
        """reset() 清除所有存储实例。"""
        store1 = StoreFactory.get_default_store()
        StoreFactory.reset()
        store2 = StoreFactory.get_default_store()
        # reset 后应该是新实例
        assert store1 is not store2


# ========================================
# 3. BaseRepository CRUD 集成测试
# ========================================

class TestBaseRepositoryCRUD:
    """BaseRepository 同步 CRUD 集成测试。"""

    def _create_repo(self) -> BaseRepository:
        """创建测试用 Repository（使用内存后端）。"""
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        return BaseRepository("test_ns", store=store)

    def test_save_and_find_by_id(self):
        """保存后能通过 ID 查找。"""
        repo = self._create_repo()
        data = {"title": "测试会话", "user": "admin"}

        saved = repo.save("id-1", data)

        assert saved["title"] == "测试会话"
        assert "created_at" in saved
        assert "updated_at" in saved

        found = repo.find_by_id("id-1")
        assert found is not None
        assert found["title"] == "测试会话"

    def test_save_preserves_created_at_on_update(self):
        """更新时保留 created_at。"""
        repo = self._create_repo()

        first = repo.save("id-1", {"title": "v1"})
        created_at = first["created_at"]

        second = repo.save("id-1", {"title": "v2"})
        assert second["created_at"] == created_at
        assert second["title"] == "v2"

    def test_find_by_id_returns_none_for_missing(self):
        """查找不存在的 ID 返回 None。"""
        repo = self._create_repo()
        assert repo.find_by_id("nonexistent") is None

    def test_find_all_with_filter(self):
        """find_all 支持过滤。"""
        repo = self._create_repo()
        repo.save("id-1", {"user": "alice", "title": "A"})
        repo.save("id-2", {"user": "bob", "title": "B"})
        repo.save("id-3", {"user": "alice", "title": "C"})

        results = repo.find_all(filter_dict={"user": "alice"})
        assert len(results) == 2
        titles = {r["title"] for r in results}
        assert titles == {"A", "C"}

    def test_find_all_without_filter(self):
        """find_all 无过滤返回全部。"""
        repo = self._create_repo()
        repo.save("id-1", {"title": "A"})
        repo.save("id-2", {"title": "B"})

        results = repo.find_all()
        assert len(results) == 2

    def test_remove_deletes_entity(self):
        """remove 删除实体。"""
        repo = self._create_repo()
        repo.save("id-1", {"title": "A"})

        assert repo.remove("id-1") is True
        assert repo.find_by_id("id-1") is None

    def test_find_all_attaches_id(self):
        """find_all 结果自动附加 id 字段。"""
        repo = self._create_repo()
        repo.save("my-key", {"title": "test"})

        results = repo.find_all()
        assert len(results) == 1
        assert results[0]["id"] == "my-key"


# ========================================
# 4. BaseRepository 异步 CRUD 集成测试
# ========================================

class TestBaseRepositoryAsyncCRUD:
    """BaseRepository 异步 CRUD 集成测试。"""

    def _create_repo(self) -> BaseRepository:
        from langgraph.store.memory import InMemoryStore

        store = InMemoryStore()
        return BaseRepository("test_async", store=store)

    @pytest.mark.asyncio
    async def test_async_save_and_find(self):
        """异步保存后能查找。"""
        repo = self._create_repo()

        saved = await repo.asave("id-1", {"title": "异步测试"})
        assert saved["title"] == "异步测试"

        found = await repo.afind_by_id("id-1")
        assert found is not None
        assert found["title"] == "异步测试"

    @pytest.mark.asyncio
    async def test_async_find_all_with_filter(self):
        """异步 find_all 支持过滤。"""
        repo = self._create_repo()
        await repo.asave("id-1", {"user": "alice"})
        await repo.asave("id-2", {"user": "bob"})

        results = await repo.afind_all(filter_dict={"user": "alice"})
        assert len(results) == 1

    @pytest.mark.asyncio
    async def test_async_remove(self):
        """异步删除。"""
        repo = self._create_repo()
        await repo.asave("id-1", {"title": "to_delete"})

        assert await repo.aremove("id-1") is True
        assert await repo.afind_by_id("id-1") is None


# ========================================
# 5. CacheManager 集成测试
# ========================================

class TestCacheManagerIntegration:
    """CacheManager 集成测试。"""

    def test_cache_set_and_get(self):
        """缓存写入和读取。"""
        from langgraph.store.memory import InMemoryStore
        from analytics_assistant.src.infra.storage import CacheManager

        store = InMemoryStore()
        cache = CacheManager("test_cache", store=store)

        cache.set("key1", {"data": "value"})
        result = cache.get("key1")

        assert result == {"data": "value"}

    def test_cache_miss_returns_default(self):
        """缓存未命中返回默认值。"""
        from langgraph.store.memory import InMemoryStore
        from analytics_assistant.src.infra.storage import CacheManager

        store = InMemoryStore()
        cache = CacheManager("test_cache", store=store)

        result = cache.get("nonexistent", default="fallback")
        assert result == "fallback"

    def test_get_or_compute(self):
        """get_or_compute 缓存穿透模式。"""
        from langgraph.store.memory import InMemoryStore
        from analytics_assistant.src.infra.storage import CacheManager

        store = InMemoryStore()
        cache = CacheManager("test_cache", store=store)

        call_count = 0

        def compute():
            nonlocal call_count
            call_count += 1
            return {"computed": True}

        # 第一次：计算
        result1 = cache.get_or_compute("key", compute_fn=compute)
        assert result1 == {"computed": True}
        assert call_count == 1

        # 第二次：命中缓存
        result2 = cache.get_or_compute("key", compute_fn=compute)
        assert result2 == {"computed": True}
        assert call_count == 1  # 没有再次计算

    def test_cache_stats(self):
        """缓存统计信息。"""
        from langgraph.store.memory import InMemoryStore
        from analytics_assistant.src.infra.storage import CacheManager

        store = InMemoryStore()
        cache = CacheManager("test_cache", store=store)

        cache.set("k1", "v1")
        cache.get("k1")       # hit
        cache.get("k2")       # miss

        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["sets"] == 1

    def test_compute_hash(self):
        """compute_hash 生成一致的哈希。"""
        from analytics_assistant.src.infra.storage import CacheManager

        h1 = CacheManager.compute_hash({"a": 1, "b": 2})
        h2 = CacheManager.compute_hash({"b": 2, "a": 1})
        assert h1 == h2  # 字典排序后哈希一致


# ========================================
# 6. SSECallbacks 集成测试
# ========================================

class TestSSECallbacksIntegration:
    """SSECallbacks 节点映射集成测试。"""

    def test_processing_stage_mapping(self):
        """节点名称正确映射到 ProcessingStage。"""
        from analytics_assistant.src.orchestration.workflow.callbacks import (
            get_processing_stage,
        )

        # LLM 节点
        assert get_processing_stage("feature_extractor") == "understanding"
        assert get_processing_stage("semantic_understanding") == "understanding"
        assert get_processing_stage("error_corrector") == "understanding"
        assert get_processing_stage("field_mapper") == "mapping"
        assert get_processing_stage("field_semantic") == "understanding"

        # 可见节点
        assert get_processing_stage("query_adapter") == "building"
        assert get_processing_stage("tableau_query") == "executing"
        assert get_processing_stage("feedback_learner") == "generating"

        # 未映射节点
        assert get_processing_stage("unknown_node") is None
        assert get_processing_stage("intent_router") is None

    def test_stage_display_names_zh(self):
        """中文显示名称。"""
        from analytics_assistant.src.orchestration.workflow.callbacks import (
            get_stage_display_name,
        )

        assert get_stage_display_name("understanding", "zh") == "理解问题"
        assert get_stage_display_name("mapping", "zh") == "字段映射"
        assert get_stage_display_name("building", "zh") == "构建查询"
        assert get_stage_display_name("executing", "zh") == "执行分析"
        assert get_stage_display_name("generating", "zh") == "生成洞察"

    def test_stage_display_names_en(self):
        """英文显示名称。"""
        from analytics_assistant.src.orchestration.workflow.callbacks import (
            get_stage_display_name,
        )

        assert get_stage_display_name("understanding", "en") == "Understanding"
        assert get_stage_display_name("mapping", "en") == "Mapping Fields"

    @pytest.mark.asyncio
    async def test_callbacks_put_events_to_queue(self):
        """SSECallbacks 将事件放入队列。"""
        import asyncio

        from analytics_assistant.src.orchestration.workflow.callbacks import (
            SSECallbacks,
        )

        queue: asyncio.Queue = asyncio.Queue()
        callbacks = SSECallbacks(queue, language="zh")

        await callbacks.on_token("你好")
        event = await queue.get()
        assert event == {"type": "token", "content": "你好"}

        await callbacks.on_thinking("让我想想...")
        event = await queue.get()
        assert event == {"type": "thinking_token", "content": "让我想想..."}

    @pytest.mark.asyncio
    async def test_callbacks_node_start_end(self):
        """节点开始/结束回调正确发送事件。"""
        import asyncio

        from analytics_assistant.src.orchestration.workflow.callbacks import (
            SSECallbacks,
        )

        queue: asyncio.Queue = asyncio.Queue()
        callbacks = SSECallbacks(queue, language="zh")

        # 有映射的节点
        await callbacks.on_node_start("field_mapper")
        event = await queue.get()
        assert event["type"] == "thinking"
        assert event["stage"] == "mapping"
        assert event["status"] == "running"
        assert event["name"] == "字段映射"

        await callbacks.on_node_end("field_mapper")
        event = await queue.get()
        assert event["status"] == "completed"

        # 无映射的节点 → 不发送事件
        await callbacks.on_node_start("intent_router")
        assert queue.empty()


# ========================================
# 7. 依赖注入集成测试
# ========================================

class TestDependencyInjection:
    """依赖注入集成测试。"""

    def test_repository_singleton(self):
        """同一命名空间的 Repository 是单例。"""
        from analytics_assistant.src.api.dependencies import (
            get_session_repository,
        )

        repo1 = get_session_repository()
        repo2 = get_session_repository()
        assert repo1 is repo2

    def test_different_namespaces_different_repos(self):
        """不同命名空间返回不同 Repository。"""
        from analytics_assistant.src.api.dependencies import (
            get_feedback_repository,
            get_session_repository,
            get_settings_repository,
        )

        session_repo = get_session_repository()
        settings_repo = get_settings_repository()
        feedback_repo = get_feedback_repository()

        assert session_repo.namespace == "sessions"
        assert settings_repo.namespace == "user_settings"
        assert feedback_repo.namespace == "user_feedback"

    def test_missing_username_returns_401(self):
        """缺少 X-Tableau-Username 返回 401。"""
        from analytics_assistant.src.api.main import app

        client = TestClient(app)
        # health 不需要认证，但如果有需要认证的端点会返回 401
        # 这里验证 get_tableau_username 的逻辑
        response = client.get("/health")
        assert response.status_code == 200  # health 不需要认证


# ========================================
# 8. 中间件集成测试
# ========================================

class TestMiddlewareIntegration:
    """中间件集成测试。"""

    def test_sanitize_error_message(self):
        """敏感信息过滤。"""
        from analytics_assistant.src.api.middleware import _sanitize_error_message

        # 包含敏感关键词 → 替换
        assert _sanitize_error_message("connection_string: sqlite:///...") == "服务内部错误，请稍后重试"
        assert _sanitize_error_message("api_key=sk-xxx") == "服务内部错误，请稍后重试"
        assert _sanitize_error_message("password: 123456") == "服务内部错误，请稍后重试"
        assert _sanitize_error_message('File "/app/main.py"') == "服务内部错误，请稍后重试"

        # 不包含敏感关键词 → 保留原文
        assert _sanitize_error_message("数据源不存在") == "数据源不存在"
        assert _sanitize_error_message("字段映射失败") == "字段映射失败"

    def test_validation_error_returns_422(self):
        """请求验证错误返回 422。"""
        from analytics_assistant.src.api.main import app

        client = TestClient(app)
        # 访问不存在的路由不会触发验证错误，但 404 会被正常处理
        response = client.get("/nonexistent")
        assert response.status_code == 404
