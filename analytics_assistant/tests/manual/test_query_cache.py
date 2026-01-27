# -*- coding: utf-8 -*-
"""
QueryCache 手动测试

测试查询缓存功能：
- 精确匹配缓存
- Schema Hash 失效机制
- TTL 过期
- 数据源级别失效

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    python -m pytest tests/manual/test_query_cache.py -v
"""

import pytest
from datetime import datetime, timedelta
from unittest.mock import MagicMock, patch

from analytics_assistant.src.agents.semantic_parser.components.query_cache import (
    CachedQuery,
    QueryCache,
    compute_schema_hash,
    compute_question_hash,
)


class TestComputeSchemaHash:
    """测试 compute_schema_hash 函数"""
    
    def test_empty_data_model(self):
        """测试空数据模型"""
        # 没有 fields 属性
        data_model = MagicMock(spec=[])
        hash1 = compute_schema_hash(data_model)
        assert hash1 is not None
        assert len(hash1) == 32  # MD5 hash 长度
        
        # fields 为空列表
        data_model = MagicMock()
        data_model.fields = []
        hash2 = compute_schema_hash(data_model)
        assert hash2 == hash1  # 都是 "empty" 的 hash
    
    def test_same_fields_same_hash(self):
        """测试相同字段产生相同 hash"""
        field1 = MagicMock()
        field1.name = "sales"
        field1.data_type = "float"
        field1.role = "MEASURE"
        
        field2 = MagicMock()
        field2.name = "region"
        field2.data_type = "string"
        field2.role = "DIMENSION"
        
        data_model1 = MagicMock()
        data_model1.fields = [field1, field2]
        
        data_model2 = MagicMock()
        data_model2.fields = [field2, field1]  # 顺序不同
        
        hash1 = compute_schema_hash(data_model1)
        hash2 = compute_schema_hash(data_model2)
        
        # 排序后应该相同
        assert hash1 == hash2
    
    def test_different_fields_different_hash(self):
        """测试不同字段产生不同 hash"""
        field1 = MagicMock()
        field1.name = "sales"
        field1.data_type = "float"
        field1.role = "MEASURE"
        
        field2 = MagicMock()
        field2.name = "profit"  # 不同字段名
        field2.data_type = "float"
        field2.role = "MEASURE"
        
        data_model1 = MagicMock()
        data_model1.fields = [field1]
        
        data_model2 = MagicMock()
        data_model2.fields = [field2]
        
        hash1 = compute_schema_hash(data_model1)
        hash2 = compute_schema_hash(data_model2)
        
        assert hash1 != hash2
    
    def test_type_change_changes_hash(self):
        """测试类型变更导致 hash 变化"""
        field1 = MagicMock()
        field1.name = "sales"
        field1.data_type = "float"
        field1.role = "MEASURE"
        
        field2 = MagicMock()
        field2.name = "sales"
        field2.data_type = "integer"  # 类型变更
        field2.role = "MEASURE"
        
        data_model1 = MagicMock()
        data_model1.fields = [field1]
        
        data_model2 = MagicMock()
        data_model2.fields = [field2]
        
        hash1 = compute_schema_hash(data_model1)
        hash2 = compute_schema_hash(data_model2)
        
        assert hash1 != hash2
    
    def test_role_change_changes_hash(self):
        """测试角色变更导致 hash 变化"""
        field1 = MagicMock()
        field1.name = "count"
        field1.data_type = "integer"
        field1.role = "MEASURE"
        
        field2 = MagicMock()
        field2.name = "count"
        field2.data_type = "integer"
        field2.role = "DIMENSION"  # 角色变更
        
        data_model1 = MagicMock()
        data_model1.fields = [field1]
        
        data_model2 = MagicMock()
        data_model2.fields = [field2]
        
        hash1 = compute_schema_hash(data_model1)
        hash2 = compute_schema_hash(data_model2)
        
        assert hash1 != hash2


class TestComputeQuestionHash:
    """测试 compute_question_hash 函数"""
    
    def test_same_question_same_hash(self):
        """测试相同问题产生相同 hash"""
        hash1 = compute_question_hash("上个月的销售额", "ds_123")
        hash2 = compute_question_hash("上个月的销售额", "ds_123")
        assert hash1 == hash2
    
    def test_case_insensitive(self):
        """测试大小写不敏感"""
        hash1 = compute_question_hash("Sales Report", "ds_123")
        hash2 = compute_question_hash("sales report", "ds_123")
        assert hash1 == hash2
    
    def test_whitespace_normalized(self):
        """测试空白字符标准化"""
        hash1 = compute_question_hash("  上个月的销售额  ", "ds_123")
        hash2 = compute_question_hash("上个月的销售额", "ds_123")
        assert hash1 == hash2
    
    def test_different_datasource_different_hash(self):
        """测试不同数据源产生不同 hash"""
        hash1 = compute_question_hash("销售额", "ds_123")
        hash2 = compute_question_hash("销售额", "ds_456")
        assert hash1 != hash2


class TestCachedQuery:
    """测试 CachedQuery 模型"""
    
    def test_create_cached_query(self):
        """测试创建 CachedQuery"""
        cached = CachedQuery(
            question="上个月的销售额",
            question_hash="abc123",
            datasource_luid="ds_123",
            schema_hash="schema_abc",
            semantic_output={"what": {"measures": ["销售额"]}},
            query="SELECT SUM(sales) FROM ...",
            expires_at=datetime.now() + timedelta(hours=24),
        )
        
        assert cached.question == "上个月的销售额"
        assert cached.hit_count == 0
        assert cached.question_embedding is None
    
    def test_serialization(self):
        """测试序列化"""
        cached = CachedQuery(
            question="测试问题",
            question_hash="hash123",
            datasource_luid="ds_123",
            schema_hash="schema_abc",
            semantic_output={"test": "data"},
            query="SELECT 1",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        
        data = cached.model_dump()
        assert "question" in data
        assert "expires_at" in data
        
        # 反序列化
        restored = CachedQuery.model_validate(data)
        assert restored.question == cached.question


class TestQueryCache:
    """测试 QueryCache 类"""
    
    @pytest.fixture
    def mock_store(self):
        """创建 mock store"""
        store = MagicMock()
        store.get.return_value = None
        store.search.return_value = []
        return store
    
    @pytest.fixture
    def cache(self, mock_store):
        """创建 QueryCache 实例"""
        return QueryCache(store=mock_store, default_ttl=3600)
    
    def test_get_cache_miss(self, cache, mock_store):
        """测试缓存未命中"""
        mock_store.get.return_value = None
        
        result = cache.get(
            question="测试问题",
            datasource_luid="ds_123",
            current_schema_hash="schema_abc",
        )
        
        assert result is None
    
    def test_get_cache_hit(self, cache, mock_store):
        """测试缓存命中"""
        cached_data = CachedQuery(
            question="测试问题",
            question_hash="hash123",
            datasource_luid="ds_123",
            schema_hash="schema_abc",
            semantic_output={"test": "data"},
            query="SELECT 1",
            expires_at=datetime.now() + timedelta(hours=1),
            hit_count=5,
        )
        
        mock_item = MagicMock()
        mock_item.value = cached_data.model_dump()
        mock_store.get.return_value = mock_item
        
        result = cache.get(
            question="测试问题",
            datasource_luid="ds_123",
            current_schema_hash="schema_abc",
        )
        
        assert result is not None
        assert result.question == "测试问题"
        assert result.hit_count == 6  # 命中计数 +1
    
    def test_get_cache_expired(self, cache, mock_store):
        """测试缓存过期"""
        cached_data = CachedQuery(
            question="测试问题",
            question_hash="hash123",
            datasource_luid="ds_123",
            schema_hash="schema_abc",
            semantic_output={"test": "data"},
            query="SELECT 1",
            expires_at=datetime.now() - timedelta(hours=1),  # 已过期
            hit_count=5,
        )
        
        mock_item = MagicMock()
        mock_item.value = cached_data.model_dump()
        mock_store.get.return_value = mock_item
        
        result = cache.get(
            question="测试问题",
            datasource_luid="ds_123",
            current_schema_hash="schema_abc",
        )
        
        assert result is None  # 过期返回 None
    
    def test_get_schema_hash_mismatch(self, cache, mock_store):
        """测试 schema hash 不匹配"""
        cached_data = CachedQuery(
            question="测试问题",
            question_hash="hash123",
            datasource_luid="ds_123",
            schema_hash="old_schema",  # 旧的 schema hash
            semantic_output={"test": "data"},
            query="SELECT 1",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        
        mock_item = MagicMock()
        mock_item.value = cached_data.model_dump()
        mock_store.get.return_value = mock_item
        
        result = cache.get(
            question="测试问题",
            datasource_luid="ds_123",
            current_schema_hash="new_schema",  # 新的 schema hash
        )
        
        assert result is None  # schema 不匹配返回 None
    
    def test_set_cache(self, cache, mock_store):
        """测试设置缓存"""
        result = cache.set(
            question="测试问题",
            datasource_luid="ds_123",
            schema_hash="schema_abc",
            semantic_output={"test": "data"},
            query="SELECT 1",
            ttl=7200,
        )
        
        assert result is True
        mock_store.put.assert_called_once()
    
    def test_invalidate_by_datasource(self, cache, mock_store):
        """测试按数据源失效"""
        mock_item1 = MagicMock()
        mock_item1.key = "key1"
        mock_item2 = MagicMock()
        mock_item2.key = "key2"
        mock_store.search.return_value = [mock_item1, mock_item2]
        
        count = cache.invalidate_by_datasource("ds_123")
        
        assert count == 2
        assert mock_store.delete.call_count == 2
    
    def test_invalidate_by_schema_change(self, cache, mock_store):
        """测试按 schema 变更失效"""
        # 一个旧 schema，一个新 schema
        old_cached = CachedQuery(
            question="问题1",
            question_hash="hash1",
            datasource_luid="ds_123",
            schema_hash="old_schema",
            semantic_output={},
            query="SELECT 1",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        new_cached = CachedQuery(
            question="问题2",
            question_hash="hash2",
            datasource_luid="ds_123",
            schema_hash="new_schema",
            semantic_output={},
            query="SELECT 2",
            expires_at=datetime.now() + timedelta(hours=1),
        )
        
        mock_item1 = MagicMock()
        mock_item1.key = "key1"
        mock_item1.value = old_cached.model_dump()
        
        mock_item2 = MagicMock()
        mock_item2.key = "key2"
        mock_item2.value = new_cached.model_dump()
        
        mock_store.search.return_value = [mock_item1, mock_item2]
        
        count = cache.invalidate_by_schema_change("ds_123", "new_schema")
        
        # 只有旧 schema 的被删除
        assert count == 1
        mock_store.delete.assert_called_once()


class TestQueryCacheCosineSimilarity:
    """测试余弦相似度计算"""
    
    def test_identical_vectors(self):
        """测试相同向量"""
        vec = [1.0, 2.0, 3.0]
        similarity = QueryCache._cosine_similarity(vec, vec)
        assert abs(similarity - 1.0) < 0.0001
    
    def test_orthogonal_vectors(self):
        """测试正交向量"""
        vec1 = [1.0, 0.0]
        vec2 = [0.0, 1.0]
        similarity = QueryCache._cosine_similarity(vec1, vec2)
        assert abs(similarity) < 0.0001
    
    def test_opposite_vectors(self):
        """测试相反向量"""
        vec1 = [1.0, 2.0, 3.0]
        vec2 = [-1.0, -2.0, -3.0]
        similarity = QueryCache._cosine_similarity(vec1, vec2)
        assert abs(similarity + 1.0) < 0.0001
    
    def test_empty_vectors(self):
        """测试空向量"""
        assert QueryCache._cosine_similarity([], []) == 0.0
        assert QueryCache._cosine_similarity([1.0], []) == 0.0
    
    def test_different_length_vectors(self):
        """测试不同长度向量"""
        vec1 = [1.0, 2.0]
        vec2 = [1.0, 2.0, 3.0]
        similarity = QueryCache._cosine_similarity(vec1, vec2)
        assert similarity == 0.0


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v"])
