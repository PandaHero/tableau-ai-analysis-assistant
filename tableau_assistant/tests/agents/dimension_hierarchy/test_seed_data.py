# -*- coding: utf-8 -*-
"""
种子数据单元测试

测试种子数据模块的功能：
- 种子数据定义验证（44 个模式，6 个类别）
- few-shot 示例获取
- 种子数据初始化（批量添加到 FAISS + LangGraph Store）

使用真实 Embedding API，不使用 mock。

Requirements: 3.1, 3.2, 3.3
"""
import pytest
import tempfile
import shutil

from tableau_assistant.src.agents.dimension_hierarchy.seed_data import (
    SEED_PATTERNS,
    get_seed_few_shot_examples,
    initialize_seed_patterns,
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
# 种子数据定义测试
# ═══════════════════════════════════════════════════════════

class TestSeedPatternsDefinition:
    """种子数据定义测试"""
    
    def test_seed_patterns_count(self):
        """测试种子数据数量为 44"""
        assert len(SEED_PATTERNS) == 44
    
    def test_seed_patterns_categories(self):
        """测试种子数据覆盖 6 个类别"""
        categories = set(p["category"] for p in SEED_PATTERNS)
        expected = {"time", "geography", "product", "customer", "organization", "financial"}
        
        assert categories == expected
    
    def test_seed_patterns_category_distribution(self):
        """测试各类别的模式数量"""
        category_counts = {}
        for p in SEED_PATTERNS:
            cat = p["category"]
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        # 验证各类别数量
        assert category_counts["time"] == 10
        assert category_counts["geography"] == 8
        assert category_counts["product"] == 8
        assert category_counts["customer"] == 6
        assert category_counts["organization"] == 6
        assert category_counts["financial"] == 6
    
    def test_seed_patterns_required_fields(self):
        """测试每个模式包含必需字段"""
        required_fields = [
            "field_caption", "data_type", "category", "category_detail",
            "level", "granularity", "reasoning", "confidence", "source", "verified"
        ]
        
        for i, pattern in enumerate(SEED_PATTERNS):
            for field in required_fields:
                assert field in pattern, f"Pattern {i} missing field: {field}"
    
    def test_seed_patterns_source_is_seed(self):
        """测试所有种子数据的 source 为 seed"""
        for pattern in SEED_PATTERNS:
            assert pattern["source"] == "seed"
    
    def test_seed_patterns_verified_is_true(self):
        """测试所有种子数据的 verified 为 True"""
        for pattern in SEED_PATTERNS:
            assert pattern["verified"] is True
    
    def test_seed_patterns_confidence_is_one(self):
        """测试所有种子数据的 confidence 为 1.0"""
        for pattern in SEED_PATTERNS:
            assert pattern["confidence"] == 1.0
    
    def test_seed_patterns_chinese_and_english(self):
        """测试种子数据包含中英文字段名"""
        chinese_count = 0
        english_count = 0
        
        for pattern in SEED_PATTERNS:
            caption = pattern["field_caption"]
            # 简单判断：包含中文字符
            if any('\u4e00' <= c <= '\u9fff' for c in caption):
                chinese_count += 1
            else:
                english_count += 1
        
        # 应该有中英文混合
        assert chinese_count > 0, "应该包含中文字段名"
        assert english_count > 0, "应该包含英文字段名"
    
    def test_seed_patterns_level_range(self):
        """测试 level 在 1-5 范围内"""
        for pattern in SEED_PATTERNS:
            assert 1 <= pattern["level"] <= 5


# ═══════════════════════════════════════════════════════════
# Few-shot 示例获取测试
# ═══════════════════════════════════════════════════════════

class TestGetSeedFewShotExamples:
    """Few-shot 示例获取测试"""
    
    def test_get_all_categories(self):
        """测试获取所有类别的示例"""
        examples = get_seed_few_shot_examples()
        
        # 默认每类别 2 个，6 个类别 = 12 个
        assert len(examples) == 12
    
    def test_get_specific_categories(self):
        """测试获取指定类别的示例"""
        examples = get_seed_few_shot_examples(categories=["time", "geography"])
        
        # 2 个类别，每类别 2 个 = 4 个
        assert len(examples) == 4
        
        # 验证只包含指定类别
        categories = set(e["category"] for e in examples)
        assert categories == {"time", "geography"}
    
    def test_get_max_per_category(self):
        """测试限制每类别数量"""
        examples = get_seed_few_shot_examples(max_per_category=1)
        
        # 6 个类别，每类别 1 个 = 6 个
        assert len(examples) == 6
    
    def test_example_fields(self):
        """测试示例包含必需字段"""
        examples = get_seed_few_shot_examples(max_per_category=1)
        
        required_fields = [
            "field_caption", "data_type", "category",
            "category_detail", "level", "granularity"
        ]
        
        for example in examples:
            for field in required_fields:
                assert field in example
    
    def test_example_excludes_internal_fields(self):
        """测试示例不包含内部字段"""
        examples = get_seed_few_shot_examples(max_per_category=1)
        
        internal_fields = ["reasoning", "confidence", "source", "verified"]
        
        for example in examples:
            for field in internal_fields:
                assert field not in example


# ═══════════════════════════════════════════════════════════
# 种子数据初始化测试
# ═══════════════════════════════════════════════════════════

class TestInitializeSeedPatterns:
    """种子数据初始化测试"""
    
    def test_initialize_all_patterns(self, rag_retriever, faiss_store, cache_storage):
        """测试初始化所有种子数据"""
        count = initialize_seed_patterns(rag_retriever)
        
        # 应该成功添加 44 个模式
        assert count == 44
        
        # 验证 FAISS 索引包含 44 个向量
        assert faiss_store.count == 44
    
    def test_initialize_idempotent(self, rag_retriever, faiss_store):
        """测试初始化幂等性（重复调用不会重复添加）"""
        # 第一次初始化
        count1 = initialize_seed_patterns(rag_retriever)
        assert count1 == 44
        
        # 第二次初始化（应该跳过已存在的）
        count2 = initialize_seed_patterns(rag_retriever)
        assert count2 == 44  # 返回成功数（包括跳过的）
        
        # FAISS 索引仍然只有 44 个向量
        assert faiss_store.count == 44
    
    def test_initialized_patterns_searchable(self, rag_retriever):
        """测试初始化后的模式可被检索"""
        initialize_seed_patterns(rag_retriever)
        
        # 检索相似字段
        fields = [
            {"field_name": "year", "field_caption": "年份", "data_type": "integer"},
            {"field_name": "city", "field_caption": "城市名", "data_type": "string"},
            {"field_name": "product", "field_caption": "商品类别", "data_type": "string"},
        ]
        
        results = rag_retriever.batch_search_metadata_only(fields)
        
        # 应该能命中相似的种子模式
        assert len(results) == 3
        
        # 验证 year 命中时间维度
        year_pattern, year_sim = results["year"]
        assert year_pattern is not None
        assert year_pattern["category"] == "time"
        assert year_sim > 0.9
        
        # 验证 city 命中地理维度
        city_pattern, city_sim = results["city"]
        assert city_pattern is not None
        assert city_pattern["category"] == "geography"
        assert city_sim > 0.9
        
        # 验证 product 命中产品维度
        product_pattern, product_sim = results["product"]
        assert product_pattern is not None
        assert product_pattern["category"] == "product"
        assert product_sim > 0.9
    
    def test_initialized_patterns_metadata(self, rag_retriever, cache_storage):
        """测试初始化后的模式元数据正确"""
        initialize_seed_patterns(rag_retriever)
        
        # 获取一个已知模式的元数据
        pattern_id = DimensionRAGRetriever.generate_pattern_id("年", "integer")
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        
        assert metadata is not None
        assert metadata["field_caption"] == "年"
        assert metadata["data_type"] == "integer"
        assert metadata["category"] == "time"
        assert metadata["category_detail"] == "time-year"
        assert metadata["level"] == 1
        assert metadata["granularity"] == "coarsest"
        assert metadata["source"] == "seed"
        assert metadata["verified"] is True
        assert metadata["confidence"] == 1.0
