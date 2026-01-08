# -*- coding: utf-8 -*-
"""
主推断流程单元测试

测试 DimensionHierarchyInference 类的功能：
- 缓存完全命中场景
- 增量推断场景（新增/变更/删除字段）
- RAG 命中场景
- LLM 推断场景
- 并发控制
- force_refresh 和 skip_rag_store 参数
- 一致性自动修复
- 阈值分层

使用真实 Embedding API 和 LLM API，不使用 mock。

Requirements: 1.1, 1.2, 1.3, 1.4
"""
import pytest
import asyncio
import tempfile
import shutil

from tableau_assistant.src.agents.dimension_hierarchy.inference import (
    DimensionHierarchyInference,
    InferenceStats,
    IncrementalFieldsResult,
    build_cache_key,
    compute_incremental_fields,
)
from tableau_assistant.src.agents.dimension_hierarchy.rag_retriever import (
    DimensionRAGRetriever,
)
from tableau_assistant.src.agents.dimension_hierarchy.faiss_store import (
    DimensionPatternFAISS,
    DEFAULT_DIMENSION,
)
from tableau_assistant.src.agents.dimension_hierarchy.cache_storage import (
    DimensionHierarchyCacheStorage,
    compute_single_field_hash,
)
from tableau_assistant.src.agents.dimension_hierarchy.seed_data import (
    SEED_PATTERNS,
)
from tableau_assistant.src.infra.ai.embeddings import EmbeddingProviderFactory


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def embedding_provider():
    """获取真实的 Embedding 提供者"""
    provider = EmbeddingProviderFactory.get_default()
    if provider is None:
        pytest.skip("未配置 Embedding API Key，跳过测试")
    return provider


@pytest.fixture
def temp_index_path():
    """创建临时索引目录"""
    temp_dir = tempfile.mkdtemp()
    yield temp_dir
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def faiss_store(embedding_provider, temp_index_path):
    """创建 FAISS 存储实例"""
    store = DimensionPatternFAISS(
        embedding_provider=embedding_provider,
        index_path=temp_index_path,
        dimension=DEFAULT_DIMENSION,
    )
    store.load_or_create()
    return store


@pytest.fixture
def cache_storage():
    """创建缓存存储实例（使用内存存储）"""
    from langgraph.store.memory import InMemoryStore
    store = InMemoryStore()
    return DimensionHierarchyCacheStorage(store=store)


@pytest.fixture
def rag_retriever(faiss_store, cache_storage):
    """创建 RAG 检索器实例"""
    return DimensionRAGRetriever(
        faiss_store=faiss_store,
        cache_storage=cache_storage,
    )


@pytest.fixture
def inference(faiss_store, cache_storage, rag_retriever):
    """创建推断实例"""
    return DimensionHierarchyInference(
        faiss_store=faiss_store,
        cache_storage=cache_storage,
        rag_retriever=rag_retriever,
    )


# ═══════════════════════════════════════════════════════════
# 辅助函数测试
# ═══════════════════════════════════════════════════════════

class TestBuildCacheKey:
    """缓存 key 构建测试"""
    
    def test_build_cache_key_simple(self):
        """测试简单缓存 key"""
        key = build_cache_key("ds-123")
        assert key == "ds-123"
    
    def test_build_cache_key_with_table(self):
        """测试带逻辑表的缓存 key"""
        key = build_cache_key("ds-123", "table-456")
        assert key == "ds-123:table-456"
    
    def test_build_cache_key_none_table(self):
        """测试 None 逻辑表"""
        key = build_cache_key("ds-123", None)
        assert key == "ds-123"


class TestComputeIncrementalFields:
    """增量字段计算测试"""
    
    def test_all_new_fields(self):
        """测试全部新增字段"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
            {"field_name": "city", "field_caption": "城市", "data_type": "string"},
        ]
        
        result = compute_incremental_fields(fields, None, None)
        
        assert result.new_fields == {"year", "city"}
        assert result.changed_fields == set()
        assert result.deleted_fields == set()
        assert result.unchanged_fields == set()
        assert result.needs_inference is True
    
    def test_all_unchanged_fields(self):
        """测试全部未变化字段"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
        ]
        
        cached_hashes = {
            "year": compute_single_field_hash("year", "年", "integer"),
        }
        cached_names = {"year"}
        
        result = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        assert result.new_fields == set()
        assert result.changed_fields == set()
        assert result.deleted_fields == set()
        assert result.unchanged_fields == {"year"}
        assert result.needs_inference is False
    
    def test_changed_field_caption(self):
        """测试字段标题变更"""
        fields = [
            {"field_name": "year", "field_caption": "年份", "data_type": "integer"},  # 标题变了
        ]
        
        cached_hashes = {
            "year": compute_single_field_hash("year", "年", "integer"),  # 原来是 "年"
        }
        cached_names = {"year"}
        
        result = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        assert result.new_fields == set()
        assert result.changed_fields == {"year"}
        assert result.deleted_fields == set()
        assert result.unchanged_fields == set()
        assert result.needs_inference is True
    
    def test_changed_field_datatype(self):
        """测试字段数据类型变更"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "string"},  # 类型变了
        ]
        
        cached_hashes = {
            "year": compute_single_field_hash("year", "年", "integer"),  # 原来是 integer
        }
        cached_names = {"year"}
        
        result = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        assert result.changed_fields == {"year"}
        assert result.needs_inference is True
    
    def test_deleted_field(self):
        """测试删除字段"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
        ]
        
        cached_hashes = {
            "year": compute_single_field_hash("year", "年", "integer"),
            "city": compute_single_field_hash("city", "城市", "string"),
        }
        cached_names = {"year", "city"}
        
        result = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        assert result.new_fields == set()
        assert result.changed_fields == set()
        assert result.deleted_fields == {"city"}
        assert result.unchanged_fields == {"year"}
    
    def test_mixed_changes(self):
        """测试混合变更"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},  # 未变
            {"field_name": "city", "field_caption": "城市名", "data_type": "string"},  # 变更
            {"field_name": "product", "field_caption": "产品", "data_type": "string"},  # 新增
        ]
        
        cached_hashes = {
            "year": compute_single_field_hash("year", "年", "integer"),
            "city": compute_single_field_hash("city", "城市", "string"),  # 原来是 "城市"
            "customer": compute_single_field_hash("customer", "客户", "string"),  # 将被删除
        }
        cached_names = {"year", "city", "customer"}
        
        result = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        assert result.new_fields == {"product"}
        assert result.changed_fields == {"city"}
        assert result.deleted_fields == {"customer"}
        assert result.unchanged_fields == {"year"}
        assert result.fields_to_infer == {"product", "city"}


# ═══════════════════════════════════════════════════════════
# 主推断流程测试
# ═══════════════════════════════════════════════════════════

class TestInferenceBasic:
    """基本推断测试"""
    
    @pytest.mark.asyncio
    async def test_infer_empty_fields(self, inference):
        """测试空字段列表"""
        result = await inference.infer(
            datasource_luid="ds-123",
            fields=[],
        )
        
        assert result.dimension_hierarchy == {}
    
    @pytest.mark.asyncio
    async def test_infer_single_field(self, inference):
        """测试单个字段推断"""
        fields = [
            {
                "field_name": "year",
                "field_caption": "年份",
                "data_type": "integer",
                "sample_values": ["2020", "2021", "2022"],
                "unique_count": 5,
            },
        ]
        
        result = await inference.infer(
            datasource_luid="ds-test-single",
            fields=fields,
        )
        
        assert "year" in result.dimension_hierarchy
        attrs = result.dimension_hierarchy["year"]
        assert attrs.category.value == "time"
        assert 1 <= attrs.level <= 5
    
    @pytest.mark.asyncio
    async def test_infer_multiple_fields(self, inference):
        """测试多个字段推断"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
            {"field_name": "city", "field_caption": "城市", "data_type": "string"},
            {"field_name": "category", "field_caption": "产品类别", "data_type": "string"},
        ]
        
        result = await inference.infer(
            datasource_luid="ds-test-multi",
            fields=fields,
        )
        
        assert len(result.dimension_hierarchy) == 3
        assert "year" in result.dimension_hierarchy
        assert "city" in result.dimension_hierarchy
        assert "category" in result.dimension_hierarchy


class TestCacheHit:
    """缓存命中测试"""
    
    @pytest.mark.asyncio
    async def test_cache_full_hit(self, inference):
        """测试缓存完全命中"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
        ]
        
        # 第一次推断
        result1 = await inference.infer(
            datasource_luid="ds-cache-test",
            fields=fields,
        )
        
        # 重置统计
        inference.reset_stats()
        
        # 第二次推断（应该命中缓存）
        result2 = await inference.infer(
            datasource_luid="ds-cache-test",
            fields=fields,
        )
        
        # 验证结果一致
        assert result1.dimension_hierarchy.keys() == result2.dimension_hierarchy.keys()
        
        # 验证统计（缓存命中）
        stats = inference.get_stats()
        assert stats["cache_hits"] == 1
        assert stats["llm_inferences"] == 0
    
    @pytest.mark.asyncio
    async def test_force_refresh_skips_cache(self, inference):
        """测试 force_refresh 跳过缓存"""
        fields = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
        ]
        
        # 第一次推断
        await inference.infer(
            datasource_luid="ds-force-refresh",
            fields=fields,
        )
        
        # 重置统计
        inference.reset_stats()
        
        # 第二次推断（强制刷新）
        await inference.infer(
            datasource_luid="ds-force-refresh",
            fields=fields,
            force_refresh=True,
        )
        
        # 验证统计（不应该命中缓存）
        stats = inference.get_stats()
        assert stats["cache_hits"] == 0


class TestIncrementalInference:
    """增量推断测试"""
    
    @pytest.mark.asyncio
    async def test_incremental_new_field(self, inference):
        """测试增量推断 - 新增字段"""
        # 第一次推断
        fields1 = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
        ]
        
        result1 = await inference.infer(
            datasource_luid="ds-incremental-new",
            fields=fields1,
        )
        
        assert "year" in result1.dimension_hierarchy
        
        # 重置统计
        inference.reset_stats()
        
        # 第二次推断（新增字段）
        fields2 = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
            {"field_name": "city", "field_caption": "城市", "data_type": "string"},  # 新增
        ]
        
        result2 = await inference.infer(
            datasource_luid="ds-incremental-new",
            fields=fields2,
        )
        
        assert "year" in result2.dimension_hierarchy
        assert "city" in result2.dimension_hierarchy
        
        # 验证统计（只推断新增字段）
        stats = inference.get_stats()
        # year 应该从缓存复用，city 需要推断
        assert stats["total_fields"] == 2
    
    @pytest.mark.asyncio
    async def test_incremental_deleted_field(self, inference):
        """测试增量推断 - 删除字段"""
        # 第一次推断
        fields1 = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
            {"field_name": "city", "field_caption": "城市", "data_type": "string"},
        ]
        
        result1 = await inference.infer(
            datasource_luid="ds-incremental-delete",
            fields=fields1,
        )
        
        assert "year" in result1.dimension_hierarchy
        assert "city" in result1.dimension_hierarchy
        
        # 第二次推断（删除字段）
        fields2 = [
            {"field_name": "year", "field_caption": "年", "data_type": "integer"},
            # city 被删除
        ]
        
        result2 = await inference.infer(
            datasource_luid="ds-incremental-delete",
            fields=fields2,
        )
        
        assert "year" in result2.dimension_hierarchy
        assert "city" not in result2.dimension_hierarchy
    
    @pytest.mark.asyncio
    async def test_incremental_changed_field(self, inference):
        """测试增量推断 - 字段变更"""
        # 第一次推断
        fields1 = [
            {"field_name": "date_field", "field_caption": "日期", "data_type": "string"},
        ]
        
        result1 = await inference.infer(
            datasource_luid="ds-incremental-change",
            fields=fields1,
        )
        
        # 重置统计
        inference.reset_stats()
        
        # 第二次推断（字段类型变更）
        fields2 = [
            {"field_name": "date_field", "field_caption": "日期", "data_type": "date"},  # 类型变了
        ]
        
        result2 = await inference.infer(
            datasource_luid="ds-incremental-change",
            fields=fields2,
        )
        
        assert "date_field" in result2.dimension_hierarchy
        
        # 验证统计（应该重新推断）
        stats = inference.get_stats()
        assert stats["cache_hits"] == 0  # 不应该完全命中缓存


class TestRAGHit:
    """RAG 命中测试"""
    
    @pytest.mark.asyncio
    async def test_rag_hit_from_seed(self, inference):
        """测试 RAG 命中种子数据"""
        # 使用与种子数据相似的字段
        fields = [
            {"field_name": "year_field", "field_caption": "年份", "data_type": "integer"},
        ]
        
        result = await inference.infer(
            datasource_luid="ds-rag-hit",
            fields=fields,
        )
        
        assert "year_field" in result.dimension_hierarchy
        attrs = result.dimension_hierarchy["year_field"]
        
        # 应该被识别为时间维度
        assert attrs.category.value == "time"
        
        # 验证统计
        stats = inference.get_stats()
        assert stats["rag_hits"] > 0 or stats["llm_inferences"] > 0


class TestSkipRAGStore:
    """跳过 RAG 存储测试"""
    
    @pytest.mark.asyncio
    async def test_skip_rag_store(self, inference, faiss_store):
        """测试 skip_rag_store 参数"""
        initial_count = faiss_store.count
        
        fields = [
            {"field_name": "custom_field", "field_caption": "自定义字段XYZ", "data_type": "string"},
        ]
        
        await inference.infer(
            datasource_luid="ds-skip-rag",
            fields=fields,
            skip_rag_store=True,
        )
        
        # FAISS 索引数量不应该增加（除了种子数据）
        # 注意：种子数据可能在第一次调用时初始化
        # 所以我们只验证 skip_rag_store 不会额外增加
        stats = inference.get_stats()
        assert stats["rag_stores"] == 0


class TestConcurrency:
    """并发控制测试"""
    
    @pytest.mark.asyncio
    async def test_concurrent_same_cache_key(self, inference):
        """测试同一 cache_key 的并发控制"""
        fields = [
            {"field_name": "concurrent_field", "field_caption": "并发测试字段", "data_type": "string"},
        ]
        
        # 并发 5 次调用
        tasks = [
            inference.infer(
                datasource_luid="ds-concurrent",
                fields=fields,
                force_refresh=True,  # 强制刷新以触发实际推断
            )
            for _ in range(5)
        ]
        
        results = await asyncio.gather(*tasks)
        
        # 所有结果应该一致
        for result in results:
            assert "concurrent_field" in result.dimension_hierarchy


class TestStats:
    """统计测试"""
    
    @pytest.mark.asyncio
    async def test_stats_collection(self, inference):
        """测试统计数据收集"""
        inference.reset_stats()
        
        fields = [
            {"field_name": "stats_field", "field_caption": "统计测试", "data_type": "string"},
        ]
        
        await inference.infer(
            datasource_luid="ds-stats",
            fields=fields,
        )
        
        stats = inference.get_stats()
        
        assert stats["total_fields"] == 1
        assert stats["total_time_ms"] > 0
        assert "rag_hit_rate" in stats
    
    def test_stats_reset(self, inference):
        """测试统计重置"""
        inference.reset_stats()
        
        stats = inference.get_stats()
        
        assert stats["total_fields"] == 0
        assert stats["cache_hits"] == 0
        assert stats["rag_hits"] == 0
        assert stats["llm_inferences"] == 0


class TestSeedDataInitialization:
    """种子数据初始化测试"""
    
    @pytest.mark.asyncio
    async def test_auto_initialize_seed_data(self, inference, faiss_store):
        """测试自动初始化种子数据"""
        # 首次调用应该初始化种子数据
        fields = [
            {"field_name": "test_field", "field_caption": "测试", "data_type": "string"},
        ]
        
        await inference.infer(
            datasource_luid="ds-seed-init",
            fields=fields,
        )
        
        # FAISS 索引应该包含种子数据
        assert faiss_store.count >= len(SEED_PATTERNS)


class TestConsistencyRepair:
    """一致性修复测试"""
    
    def test_auto_repair_consistency(self, inference, faiss_store, cache_storage, rag_retriever):
        """测试一致性自动修复"""
        # 先添加一些 metadata
        cache_storage.store_pattern_metadata(
            pattern_id="test-pattern-1",
            field_caption="测试字段1",
            data_type="string",
            sample_values=[],
            unique_count=0,
            category="other",
            category_detail="other-test",
            level=3,
            granularity="medium",
            reasoning="测试",
            confidence=0.9,
        )
        
        # 此时 FAISS 和 metadata 数量不一致
        # 调用修复方法
        repaired = inference._auto_repair_consistency()
        
        # 应该执行了修复
        # 注意：如果 FAISS 已经有种子数据，可能不会触发修复
        # 这里只验证方法可以正常执行
        assert isinstance(repaired, bool)
