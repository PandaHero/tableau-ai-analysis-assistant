# -*- coding: utf-8 -*-
"""
FAISS 向量索引单元测试

测试 DimensionPatternFAISS 类的功能：
- 索引创建和加载（持久化）
- 单个/批量添加模式
- 单个/批量检索
- rebuild_index() 重建索引

使用真实 Embedding API，不使用 mock。

Requirements: 2.1, 2.2, 2.3
"""
import pytest
import tempfile
import shutil
from pathlib import Path

from tableau_assistant.src.agents.dimension_hierarchy.faiss_store import (
    DimensionPatternFAISS,
    DEFAULT_DIMENSION,
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
    # 清理
    shutil.rmtree(temp_dir, ignore_errors=True)


@pytest.fixture
def faiss_store(embedding_provider, temp_index_path):
    """创建 FAISS 存储实例"""
    store = DimensionPatternFAISS(
        embedding_provider=embedding_provider,
        index_path=temp_index_path,
        dimension=DEFAULT_DIMENSION,
    )
    return store


# ═══════════════════════════════════════════════════════════
# 索引创建和加载测试
# ═══════════════════════════════════════════════════════════

class TestIndexCreationAndLoading:
    """索引创建和加载测试"""
    
    def test_create_empty_index(self, faiss_store):
        """测试创建空索引"""
        result = faiss_store.load_or_create()
        
        assert result is True
        assert faiss_store.is_loaded is True
        assert faiss_store.count == 0
        assert faiss_store.dimension == DEFAULT_DIMENSION

    def test_load_or_create_idempotent(self, faiss_store):
        """测试 load_or_create 幂等性"""
        faiss_store.load_or_create()
        faiss_store.load_or_create()  # 第二次调用
        
        assert faiss_store.is_loaded is True
        assert faiss_store.count == 0
    
    def test_save_and_load_index(self, embedding_provider, temp_index_path):
        """测试索引持久化和加载"""
        # 1. 创建并添加数据
        store1 = DimensionPatternFAISS(
            embedding_provider=embedding_provider,
            index_path=temp_index_path,
        )
        store1.load_or_create()
        store1.add_pattern("p1", "字段名: 年 | 数据类型: integer")
        store1.add_pattern("p2", "字段名: 城市 | 数据类型: string")
        store1.save()
        
        assert store1.count == 2
        
        # 2. 创建新实例并加载
        store2 = DimensionPatternFAISS(
            embedding_provider=embedding_provider,
            index_path=temp_index_path,
        )
        result = store2.load_or_create()
        
        assert result is True
        assert store2.count == 2
        assert store2.is_loaded is True


# ═══════════════════════════════════════════════════════════
# 添加模式测试
# ═══════════════════════════════════════════════════════════

class TestAddPatterns:
    """添加模式测试"""
    
    def test_add_single_pattern(self, faiss_store):
        """测试添加单个模式"""
        faiss_store.load_or_create()
        
        result = faiss_store.add_pattern(
            pattern_id="test_pattern_1",
            text="字段名: 年份 | 数据类型: integer",
            metadata={"category": "time"},
        )
        
        assert result is True
        assert faiss_store.count == 1
    
    def test_add_multiple_patterns_sequentially(self, faiss_store):
        """测试顺序添加多个模式"""
        faiss_store.load_or_create()
        
        patterns = [
            ("p1", "字段名: 年 | 数据类型: integer"),
            ("p2", "字段名: 月 | 数据类型: integer"),
            ("p3", "字段名: 日 | 数据类型: integer"),
        ]
        
        for pid, text in patterns:
            result = faiss_store.add_pattern(pid, text)
            assert result is True
        
        assert faiss_store.count == 3
    
    def test_batch_add_patterns(self, faiss_store):
        """测试批量添加模式"""
        faiss_store.load_or_create()
        
        patterns = [
            {"pattern_id": "p1", "text": "字段名: 省份 | 数据类型: string"},
            {"pattern_id": "p2", "text": "字段名: 城市 | 数据类型: string"},
            {"pattern_id": "p3", "text": "字段名: 区县 | 数据类型: string"},
            {"pattern_id": "p4", "text": "字段名: 街道 | 数据类型: string"},
        ]
        
        count = faiss_store.batch_add_patterns(patterns)
        
        assert count == 4
        assert faiss_store.count == 4
    
    def test_batch_add_empty_list(self, faiss_store):
        """测试批量添加空列表"""
        faiss_store.load_or_create()
        
        count = faiss_store.batch_add_patterns([])
        
        assert count == 0
        assert faiss_store.count == 0
    
    def test_batch_add_with_metadata(self, faiss_store):
        """测试批量添加带元数据的模式"""
        faiss_store.load_or_create()
        
        patterns = [
            {
                "pattern_id": "p1",
                "text": "字段名: 产品类别 | 数据类型: string",
                "metadata": {"category": "product", "level": 1},
            },
            {
                "pattern_id": "p2",
                "text": "字段名: 产品子类 | 数据类型: string",
                "metadata": {"category": "product", "level": 2},
            },
        ]
        
        count = faiss_store.batch_add_patterns(patterns)
        
        assert count == 2
        assert faiss_store.count == 2


# ═══════════════════════════════════════════════════════════
# 检索测试
# ═══════════════════════════════════════════════════════════

class TestSearch:
    """检索测试"""
    
    @pytest.fixture
    def populated_store(self, faiss_store):
        """预填充数据的 FAISS 存储"""
        faiss_store.load_or_create()
        
        patterns = [
            {"pattern_id": "time_year", "text": "字段名: 年 | 数据类型: integer"},
            {"pattern_id": "time_month", "text": "字段名: 月 | 数据类型: integer"},
            {"pattern_id": "geo_province", "text": "字段名: 省份 | 数据类型: string"},
            {"pattern_id": "geo_city", "text": "字段名: 城市 | 数据类型: string"},
            {"pattern_id": "product_category", "text": "字段名: 产品类别 | 数据类型: string"},
        ]
        faiss_store.batch_add_patterns(patterns)
        
        return faiss_store
    
    def test_search_similar_pattern(self, populated_store):
        """测试检索相似模式"""
        results = populated_store.search("字段名: 年份 | 数据类型: integer", k=3)
        
        assert len(results) > 0
        # 第一个结果应该是 "年"（最相似）
        pattern_id, score = results[0]
        assert pattern_id == "time_year"
        assert score > 0.8  # 相似度应该较高
    
    def test_search_returns_top_k(self, populated_store):
        """测试检索返回 top-k 结果"""
        results = populated_store.search("字段名: 时间 | 数据类型: integer", k=2)
        
        assert len(results) == 2
        # 所有结果都应该有 pattern_id 和 score
        for pattern_id, score in results:
            assert pattern_id != ""
            assert isinstance(score, float)
    
    def test_search_empty_index(self, faiss_store):
        """测试空索引检索"""
        faiss_store.load_or_create()
        
        results = faiss_store.search("字段名: 年 | 数据类型: integer")
        
        assert results == []
    
    def test_search_k_larger_than_count(self, populated_store):
        """测试 k 大于索引数量"""
        results = populated_store.search("字段名: 年 | 数据类型: integer", k=100)
        
        # 应该返回所有可用结果
        assert len(results) == populated_store.count
    
    def test_batch_search(self, populated_store):
        """测试批量检索"""
        query_texts = [
            "字段名: 年份 | 数据类型: integer",
            "字段名: 省 | 数据类型: string",
            "字段名: 商品分类 | 数据类型: string",
        ]
        
        results = populated_store.batch_search(query_texts, k=2)
        
        assert len(results) == 3
        # 每个查询都应该有结果
        for query_results in results:
            assert len(query_results) > 0
            for pattern_id, score in query_results:
                assert pattern_id != ""
                assert isinstance(score, float)
    
    def test_batch_search_empty_queries(self, populated_store):
        """测试批量检索空查询列表"""
        results = populated_store.batch_search([], k=2)
        
        assert results == []
    
    def test_batch_search_empty_index(self, faiss_store):
        """测试空索引批量检索"""
        faiss_store.load_or_create()
        
        results = faiss_store.batch_search(["字段名: 年 | 数据类型: integer"], k=2)
        
        assert len(results) == 1
        assert results[0] == []
    
    def test_batch_search_single_query(self, populated_store):
        """测试批量检索单个查询"""
        results = populated_store.batch_search(
            ["字段名: 城市名称 | 数据类型: string"],
            k=1,
        )
        
        assert len(results) == 1
        assert len(results[0]) == 1
        pattern_id, score = results[0][0]
        assert pattern_id == "geo_city"


# ═══════════════════════════════════════════════════════════
# 重建索引测试
# ═══════════════════════════════════════════════════════════

class TestRebuildIndex:
    """重建索引测试"""
    
    def test_rebuild_index_with_patterns(self, faiss_store):
        """测试用新模式重建索引"""
        faiss_store.load_or_create()
        
        # 先添加一些模式
        faiss_store.add_pattern("old_p1", "字段名: 旧字段1 | 数据类型: string")
        faiss_store.add_pattern("old_p2", "字段名: 旧字段2 | 数据类型: string")
        assert faiss_store.count == 2
        
        # 用新模式重建
        new_patterns = [
            {"pattern_id": "new_p1", "text": "字段名: 新字段1 | 数据类型: integer"},
            {"pattern_id": "new_p2", "text": "字段名: 新字段2 | 数据类型: integer"},
            {"pattern_id": "new_p3", "text": "字段名: 新字段3 | 数据类型: integer"},
        ]
        
        result = faiss_store.rebuild_index(new_patterns)
        
        assert result is True
        assert faiss_store.count == 3
        
        # 验证旧模式已被替换
        results = faiss_store.search("字段名: 旧字段1 | 数据类型: string", k=1)
        if results:
            pattern_id, _ = results[0]
            assert pattern_id != "old_p1"  # 旧模式不应该存在
    
    def test_rebuild_index_empty(self, faiss_store):
        """测试重建为空索引"""
        faiss_store.load_or_create()
        
        # 先添加一些模式
        faiss_store.add_pattern("p1", "字段名: 测试 | 数据类型: string")
        assert faiss_store.count == 1
        
        # 重建为空
        result = faiss_store.rebuild_index([])
        
        assert result is True
        assert faiss_store.count == 0
    
    def test_rebuild_index_persists(self, embedding_provider, temp_index_path):
        """测试重建索引后持久化"""
        # 1. 创建并重建
        store1 = DimensionPatternFAISS(
            embedding_provider=embedding_provider,
            index_path=temp_index_path,
        )
        store1.load_or_create()
        
        patterns = [
            {"pattern_id": "p1", "text": "字段名: 年 | 数据类型: integer"},
            {"pattern_id": "p2", "text": "字段名: 月 | 数据类型: integer"},
        ]
        store1.rebuild_index(patterns)
        
        # 2. 创建新实例并加载
        store2 = DimensionPatternFAISS(
            embedding_provider=embedding_provider,
            index_path=temp_index_path,
        )
        store2.load_or_create()
        
        assert store2.count == 2


# ═══════════════════════════════════════════════════════════
# 向量归一化测试
# ═══════════════════════════════════════════════════════════

class TestVectorNormalization:
    """向量归一化测试"""
    
    def test_normalize_vectors(self):
        """测试向量归一化"""
        import numpy as np
        
        # 创建未归一化的向量
        vectors = np.array([
            [3.0, 4.0, 0.0],
            [1.0, 1.0, 1.0],
        ], dtype=np.float32)
        
        normalized = DimensionPatternFAISS._normalize_vectors(vectors.copy())
        
        # 验证 L2 范数为 1
        for i in range(len(normalized)):
            norm = np.linalg.norm(normalized[i])
            assert abs(norm - 1.0) < 1e-5
    
    def test_normalized_inner_product_equals_cosine(self):
        """测试归一化后内积等于余弦相似度"""
        import numpy as np
        
        v1 = np.array([[3.0, 4.0, 0.0]], dtype=np.float32)
        v2 = np.array([[4.0, 3.0, 0.0]], dtype=np.float32)
        
        # 归一化
        v1_norm = DimensionPatternFAISS._normalize_vectors(v1.copy())
        v2_norm = DimensionPatternFAISS._normalize_vectors(v2.copy())
        
        # 计算内积
        inner_product = np.dot(v1_norm[0], v2_norm[0])
        
        # 计算余弦相似度
        cosine = np.dot(v1[0], v2[0]) / (np.linalg.norm(v1[0]) * np.linalg.norm(v2[0]))
        
        assert abs(inner_product - cosine) < 1e-5


# ═══════════════════════════════════════════════════════════
# 属性测试
# ═══════════════════════════════════════════════════════════

class TestProperties:
    """属性测试"""
    
    def test_count_property(self, faiss_store):
        """测试 count 属性"""
        # 未加载时
        assert faiss_store.count == 0
        
        faiss_store.load_or_create()
        assert faiss_store.count == 0
        
        faiss_store.add_pattern("p1", "字段名: 测试 | 数据类型: string")
        assert faiss_store.count == 1
    
    def test_dimension_property(self, faiss_store):
        """测试 dimension 属性"""
        assert faiss_store.dimension == DEFAULT_DIMENSION
    
    def test_is_loaded_property(self, faiss_store):
        """测试 is_loaded 属性"""
        assert faiss_store.is_loaded is False
        
        faiss_store.load_or_create()
        assert faiss_store.is_loaded is True
