# -*- coding: utf-8 -*-
"""
RAG 检索器单元测试

测试 DimensionRAGRetriever 类的功能：
- 批量检索（返回 pattern + similarity）
- pattern_id 生成（验证包含 data_type，同名不同类型不碰撞）
- 模式存储（含重复检查，已存在时跳过）
- 阈值分层（seed/verified=0.92, llm/unverified=0.95）

使用真实 Embedding API，不使用 mock。

Requirements: 1.1, 2.1, 2.2
"""
import pytest
import tempfile
import shutil

from tableau_assistant.src.agents.dimension_hierarchy.rag_retriever import (
    DimensionRAGRetriever,
)
from tableau_assistant.src.agents.dimension_hierarchy.faiss_store import (
    DimensionPatternFAISS,
    DEFAULT_DIMENSION,
)
from tableau_assistant.src.agents.dimension_hierarchy.cache_storage import (
    DimensionHierarchyCacheStorage,
    RAG_SIMILARITY_THRESHOLD,
    RAG_SIMILARITY_THRESHOLD_UNVERIFIED,
    PatternSource,
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


# ═══════════════════════════════════════════════════════════
# Pattern ID 生成测试
# ═══════════════════════════════════════════════════════════

class TestPatternIdGeneration:
    """Pattern ID 生成测试"""
    
    def test_generate_pattern_id_basic(self):
        """测试基本 pattern_id 生成"""
        pattern_id = DimensionRAGRetriever.generate_pattern_id(
            field_caption="年",
            data_type="integer",
        )
        
        assert len(pattern_id) == 16
        assert pattern_id.isalnum()
    
    def test_generate_pattern_id_with_datasource(self):
        """测试带数据源的 pattern_id 生成"""
        pattern_id = DimensionRAGRetriever.generate_pattern_id(
            field_caption="年",
            data_type="integer",
            datasource_luid="ds-123",
        )
        
        assert len(pattern_id) == 16
    
    def test_same_caption_different_type_different_id(self):
        """测试同名不同类型生成不同 ID（关键测试）"""
        id1 = DimensionRAGRetriever.generate_pattern_id(
            field_caption="日期",
            data_type="date",
        )
        id2 = DimensionRAGRetriever.generate_pattern_id(
            field_caption="日期",
            data_type="string",
        )
        
        # 同名不同类型应该生成不同的 pattern_id
        assert id1 != id2
    
    def test_same_caption_same_type_same_id(self):
        """测试同名同类型生成相同 ID"""
        id1 = DimensionRAGRetriever.generate_pattern_id(
            field_caption="城市",
            data_type="string",
        )
        id2 = DimensionRAGRetriever.generate_pattern_id(
            field_caption="城市",
            data_type="string",
        )
        
        assert id1 == id2
    
    def test_different_datasource_different_id(self):
        """测试不同数据源生成不同 ID"""
        id1 = DimensionRAGRetriever.generate_pattern_id(
            field_caption="年",
            data_type="integer",
            datasource_luid="ds-123",
        )
        id2 = DimensionRAGRetriever.generate_pattern_id(
            field_caption="年",
            data_type="integer",
            datasource_luid="ds-456",
        )
        
        assert id1 != id2
    
    def test_global_vs_datasource_different_id(self):
        """测试全局和数据源特定生成不同 ID"""
        id_global = DimensionRAGRetriever.generate_pattern_id(
            field_caption="年",
            data_type="integer",
            datasource_luid=None,  # 全局
        )
        id_ds = DimensionRAGRetriever.generate_pattern_id(
            field_caption="年",
            data_type="integer",
            datasource_luid="ds-123",
        )
        
        assert id_global != id_ds


# ═══════════════════════════════════════════════════════════
# 查询文本构建测试
# ═══════════════════════════════════════════════════════════

class TestQueryTextBuilding:
    """查询文本构建测试"""
    
    def test_build_query_text_metadata_only(self):
        """测试查询文本构建"""
        query_text = DimensionRAGRetriever._build_query_text_metadata_only(
            field_caption="年份",
            data_type="integer",
        )
        
        assert "年份" in query_text
        assert "integer" in query_text
        assert query_text == "字段名: 年份 | 数据类型: integer"
    
    def test_build_query_text_chinese(self):
        """测试中文字段名"""
        query_text = DimensionRAGRetriever._build_query_text_metadata_only(
            field_caption="产品类别",
            data_type="string",
        )
        
        assert "产品类别" in query_text
        assert "string" in query_text
    
    def test_build_query_text_english(self):
        """测试英文字段名"""
        query_text = DimensionRAGRetriever._build_query_text_metadata_only(
            field_caption="Category",
            data_type="string",
        )
        
        assert "Category" in query_text


# ═══════════════════════════════════════════════════════════
# 模式存储测试
# ═══════════════════════════════════════════════════════════

class TestStorePattern:
    """模式存储测试"""
    
    def test_store_pattern_basic(self, rag_retriever, cache_storage):
        """测试基本模式存储"""
        result = rag_retriever.store_pattern(
            field_caption="年",
            data_type="integer",
            category="time",
            category_detail="年份",
            level=1,
            granularity="year",
            reasoning="时间维度-年",
            confidence=0.95,
            source="seed",
            verified=True,
        )
        
        assert result is True
        
        # 验证元数据已存储
        pattern_id = DimensionRAGRetriever.generate_pattern_id("年", "integer")
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        
        assert metadata is not None
        assert metadata["field_caption"] == "年"
        assert metadata["category"] == "time"
        assert metadata["source"] == "seed"
        assert metadata["verified"] is True
    
    def test_store_pattern_skip_existing(self, rag_retriever, cache_storage):
        """测试已存在模式跳过"""
        # 第一次存储
        rag_retriever.store_pattern(
            field_caption="月",
            data_type="integer",
            category="time",
            category_detail="月份",
            level=2,
            granularity="month",
            reasoning="时间维度-月",
            confidence=0.95,
            source="seed",
        )
        
        # 第二次存储（应该跳过）
        result = rag_retriever.store_pattern(
            field_caption="月",
            data_type="integer",
            category="time",
            category_detail="月份-修改",  # 尝试修改
            level=2,
            granularity="month",
            reasoning="时间维度-月-修改",
            confidence=0.99,
            source="llm",
        )
        
        assert result is True  # 返回成功（跳过）
        
        # 验证元数据未被修改
        pattern_id = DimensionRAGRetriever.generate_pattern_id("月", "integer")
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        
        assert metadata["category_detail"] == "月份"  # 保持原值
        assert metadata["source"] == "seed"  # 保持原值
    
    def test_store_pattern_with_sample_values(self, rag_retriever, cache_storage):
        """测试带样例值的模式存储"""
        result = rag_retriever.store_pattern(
            field_caption="城市",
            data_type="string",
            category="geography",
            category_detail="城市",
            level=3,
            granularity="city",
            reasoning="地理维度-城市",
            confidence=0.90,
            sample_values=["北京", "上海", "广州", "深圳"],
            unique_count=100,
            source="llm",
            verified=False,
        )
        
        assert result is True
        
        pattern_id = DimensionRAGRetriever.generate_pattern_id("城市", "string")
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        
        assert metadata["sample_values"] == ["北京", "上海", "广州", "深圳"]
        assert metadata["unique_count"] == 100
    
    def test_batch_store_patterns(self, rag_retriever, cache_storage):
        """测试批量存储模式"""
        patterns = [
            {
                "field_caption": "省份",
                "data_type": "string",
                "category": "geography",
                "category_detail": "省份",
                "level": 1,
                "granularity": "province",
                "reasoning": "地理维度-省份",
                "confidence": 0.95,
                "source": "seed",
                "verified": True,
            },
            {
                "field_caption": "区县",
                "data_type": "string",
                "category": "geography",
                "category_detail": "区县",
                "level": 4,
                "granularity": "district",
                "reasoning": "地理维度-区县",
                "confidence": 0.90,
                "source": "seed",
                "verified": True,
            },
        ]

        store_result = rag_retriever.batch_store_patterns(patterns)

        assert store_result["total"] == 2
        assert store_result["metadata_written"] == 2
        assert store_result["faiss_written"] == 2
        assert store_result["skipped_existing"] == 0

        # 验证都已存储
        for p in patterns:
            pattern_id = DimensionRAGRetriever.generate_pattern_id(
                p["field_caption"],
                p["data_type"],
            )
            metadata = cache_storage.get_pattern_metadata(pattern_id)
            assert metadata is not None


# ═══════════════════════════════════════════════════════════
# 批量检索测试
# ═══════════════════════════════════════════════════════════

class TestBatchSearch:
    """批量检索测试"""
    
    @pytest.fixture
    def populated_retriever(self, rag_retriever):
        """预填充数据的 RAG 检索器"""
        # 添加种子数据
        seed_patterns = [
            {
                "field_caption": "年",
                "data_type": "integer",
                "category": "time",
                "category_detail": "年份",
                "level": 1,
                "granularity": "year",
                "reasoning": "时间维度-年",
                "confidence": 1.0,
                "source": "seed",
                "verified": True,
            },
            {
                "field_caption": "省份",
                "data_type": "string",
                "category": "geography",
                "category_detail": "省份",
                "level": 1,
                "granularity": "province",
                "reasoning": "地理维度-省份",
                "confidence": 1.0,
                "source": "seed",
                "verified": True,
            },
            {
                "field_caption": "产品类别",
                "data_type": "string",
                "category": "product",
                "category_detail": "产品类别",
                "level": 1,
                "granularity": "category",
                "reasoning": "产品维度-类别",
                "confidence": 1.0,
                "source": "seed",
                "verified": True,
            },
        ]
        
        rag_retriever.batch_store_patterns(seed_patterns)
        return rag_retriever
    
    def test_batch_search_hit(self, populated_retriever):
        """测试批量检索命中"""
        fields = [
            {"field_name": "year", "field_caption": "年份", "data_type": "integer"},
        ]
        
        results = populated_retriever.batch_search_metadata_only(fields)
        
        assert "year" in results
        pattern, similarity = results["year"]
        
        # 应该命中 "年"
        assert pattern is not None
        assert pattern["field_caption"] == "年"
        assert similarity > 0.9
    
    def test_batch_search_miss(self, populated_retriever):
        """测试批量检索未命中"""
        fields = [
            {"field_name": "amount", "field_caption": "销售金额", "data_type": "real"},
        ]
        
        results = populated_retriever.batch_search_metadata_only(fields)
        
        assert "amount" in results
        pattern, similarity = results["amount"]
        
        # 应该未命中（没有相似的模式）
        assert pattern is None
        # 但仍然返回相似度分数
        assert isinstance(similarity, float)
    
    def test_batch_search_multiple_fields(self, populated_retriever):
        """测试批量检索多个字段"""
        fields = [
            {"field_name": "year", "field_caption": "年份", "data_type": "integer"},
            {"field_name": "province", "field_caption": "省", "data_type": "string"},
            {"field_name": "category", "field_caption": "商品分类", "data_type": "string"},
            {"field_name": "amount", "field_caption": "金额", "data_type": "real"},
        ]
        
        results = populated_retriever.batch_search_metadata_only(fields)
        
        assert len(results) == 4
        
        # 验证每个字段都有结果
        for field_name in ["year", "province", "category", "amount"]:
            assert field_name in results
            pattern, similarity = results[field_name]
            assert isinstance(similarity, float)
    
    def test_batch_search_empty_fields(self, populated_retriever):
        """测试空字段列表"""
        results = populated_retriever.batch_search_metadata_only([])
        
        assert results == {}


# ═══════════════════════════════════════════════════════════
# 阈值分层测试
# ═══════════════════════════════════════════════════════════

class TestThresholdTiering:
    """阈值分层测试"""
    
    def test_get_effective_threshold_seed(self, rag_retriever):
        """测试种子数据使用标准阈值"""
        pattern = {"source": "seed", "verified": True}
        threshold = rag_retriever._get_effective_threshold(pattern)
        
        assert threshold == RAG_SIMILARITY_THRESHOLD  # 0.92
    
    def test_get_effective_threshold_verified(self, rag_retriever):
        """测试已验证数据使用标准阈值"""
        pattern = {"source": "llm", "verified": True}
        threshold = rag_retriever._get_effective_threshold(pattern)
        
        assert threshold == RAG_SIMILARITY_THRESHOLD  # 0.92
    
    def test_get_effective_threshold_unverified(self, rag_retriever):
        """测试未验证 LLM 数据使用更高阈值"""
        pattern = {"source": "llm", "verified": False}
        threshold = rag_retriever._get_effective_threshold(pattern)
        
        assert threshold == RAG_SIMILARITY_THRESHOLD_UNVERIFIED  # 0.95
    
    def test_get_effective_threshold_none_pattern(self, rag_retriever):
        """测试空 pattern 使用标准阈值"""
        threshold = rag_retriever._get_effective_threshold(None)
        
        assert threshold == RAG_SIMILARITY_THRESHOLD  # 0.92
    
    def test_get_effective_threshold_manual(self, rag_retriever):
        """测试手动添加数据使用标准阈值"""
        pattern = {"source": "manual", "verified": True}
        threshold = rag_retriever._get_effective_threshold(pattern)
        
        assert threshold == RAG_SIMILARITY_THRESHOLD  # 0.92
    
    def test_threshold_tiering_in_search(self, rag_retriever, cache_storage, faiss_store):
        """测试检索时阈值分层生效"""
        # 添加一个未验证的 LLM 模式
        rag_retriever.store_pattern(
            field_caption="客户名称",
            data_type="string",
            category="customer",
            category_detail="客户名称",
            level=1,
            granularity="name",
            reasoning="客户维度",
            confidence=0.90,
            source="llm",
            verified=False,  # 未验证
        )
        
        # 检索相似字段
        fields = [
            {"field_name": "customer", "field_caption": "客户", "data_type": "string"},
        ]
        
        results = rag_retriever.batch_search_metadata_only(fields)
        
        # 由于是未验证的 LLM 模式，需要更高的相似度才能命中
        # 具体是否命中取决于实际相似度
        assert "customer" in results
        pattern, similarity = results["customer"]
        
        # 如果相似度 < 0.95，应该未命中
        if similarity < RAG_SIMILARITY_THRESHOLD_UNVERIFIED:
            assert pattern is None
