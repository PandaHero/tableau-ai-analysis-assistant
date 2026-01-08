# -*- coding: utf-8 -*-
"""
Dimension Hierarchy Cache Storage 单元测试

测试内容：
- 缓存 CRUD 操作（get/put/delete）
- 模式元数据 CRUD 操作（get/store/delete/clear/get_all）
- update_pattern_verified() 验证状态更新
- field_hash 计算（仅用元数据，不含样例数据）
- single_field_hash 计算

Requirements: 1.1, 1.3
"""
import pytest
import tempfile
import os
from pathlib import Path
from dataclasses import dataclass
from typing import Optional, List

from tableau_assistant.src.agents.dimension_hierarchy.cache_storage import (
    DimensionHierarchyCacheStorage,
    PatternSource,
    compute_field_hash_metadata_only,
    compute_single_field_hash,
    NS_HIERARCHY_CACHE,
    NS_DIMENSION_PATTERNS_METADATA,
    RAG_SIMILARITY_THRESHOLD,
    RAG_SIMILARITY_THRESHOLD_UNVERIFIED,
    RAG_STORE_CONFIDENCE_THRESHOLD,
    MAX_LOCKS,
    LOCK_EXPIRE_SECONDS,
)


# ═══════════════════════════════════════════════════════════
# 测试用的 Mock 字段类
# ═══════════════════════════════════════════════════════════

@dataclass
class MockField:
    """模拟 FieldMetadata 对象"""
    name: str
    fieldCaption: str
    dataType: str
    sample_values: Optional[List[str]] = None
    unique_count: Optional[int] = None


# ═══════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════

@pytest.fixture
def temp_db_path():
    """创建临时数据库路径"""
    with tempfile.TemporaryDirectory() as tmpdir:
        db_path = os.path.join(tmpdir, "test_store.db")
        yield db_path


@pytest.fixture
def test_store(temp_db_path):
    """创建测试用的 SqliteStore"""
    from langgraph.store.sqlite import SqliteStore
    from langgraph.store.base import TTLConfig
    import sqlite3
    
    # 确保目录存在
    Path(temp_db_path).parent.mkdir(parents=True, exist_ok=True)
    
    # 创建连接
    conn = sqlite3.connect(temp_db_path, check_same_thread=False, isolation_level=None)
    
    # TTL 配置
    ttl_config: TTLConfig = {
        "default_ttl": 1440,
        "refresh_on_read": True,
        "sweep_interval_minutes": 60,
    }
    
    # 创建 SqliteStore
    store = SqliteStore(conn, ttl=ttl_config)
    store.setup()
    
    yield store
    
    # 清理
    conn.close()


@pytest.fixture
def cache_storage(test_store):
    """创建测试用的 DimensionHierarchyCacheStorage"""
    return DimensionHierarchyCacheStorage(store=test_store)


@pytest.fixture
def sample_fields():
    """创建测试用的字段列表"""
    return [
        MockField(name="year", fieldCaption="年", dataType="integer", sample_values=["2020", "2021", "2022"], unique_count=3),
        MockField(name="city", fieldCaption="城市", dataType="string", sample_values=["北京", "上海", "广州"], unique_count=100),
        MockField(name="amount", fieldCaption="金额", dataType="real", sample_values=["100.5", "200.3"], unique_count=1000),
    ]


# ═══════════════════════════════════════════════════════════
# 常量测试
# ═══════════════════════════════════════════════════════════

class TestConstants:
    """测试常量定义"""
    
    def test_namespace_constants(self):
        """测试 namespace 常量"""
        assert NS_HIERARCHY_CACHE == "dimension_hierarchy_cache"
        assert NS_DIMENSION_PATTERNS_METADATA == "dimension_patterns_metadata"
    
    def test_threshold_constants(self):
        """测试阈值常量"""
        assert RAG_SIMILARITY_THRESHOLD == 0.92
        assert RAG_SIMILARITY_THRESHOLD_UNVERIFIED == 0.95
        assert RAG_STORE_CONFIDENCE_THRESHOLD == 0.85
    
    def test_concurrency_constants(self):
        """测试并发控制常量"""
        assert MAX_LOCKS == 1000
        assert LOCK_EXPIRE_SECONDS == 3600


# ═══════════════════════════════════════════════════════════
# PatternSource 枚举测试
# ═══════════════════════════════════════════════════════════

class TestPatternSource:
    """测试 PatternSource 枚举"""
    
    def test_pattern_source_values(self):
        """测试枚举值"""
        assert PatternSource.SEED.value == "seed"
        assert PatternSource.LLM.value == "llm"
        assert PatternSource.MANUAL.value == "manual"
    
    def test_pattern_source_is_string(self):
        """测试枚举是字符串类型"""
        assert isinstance(PatternSource.SEED, str)
        assert PatternSource.SEED == "seed"


# ═══════════════════════════════════════════════════════════
# field_hash 计算测试
# ═══════════════════════════════════════════════════════════

class TestFieldHashComputation:
    """测试 field_hash 计算"""
    
    def test_compute_field_hash_metadata_only(self, sample_fields):
        """测试整体字段列表 hash 计算"""
        hash_val = compute_field_hash_metadata_only(sample_fields)
        
        # 验证返回 32 字符的 MD5 hash
        assert len(hash_val) == 32
        assert hash_val.isalnum()
    
    def test_field_hash_excludes_sample_values(self, sample_fields):
        """测试 hash 不包含 sample_values"""
        # 原始 hash
        hash1 = compute_field_hash_metadata_only(sample_fields)
        
        # 修改 sample_values
        modified_fields = [
            MockField(name="year", fieldCaption="年", dataType="integer", sample_values=["2023", "2024"], unique_count=2),
            MockField(name="city", fieldCaption="城市", dataType="string", sample_values=["深圳", "杭州"], unique_count=50),
            MockField(name="amount", fieldCaption="金额", dataType="real", sample_values=["300.0"], unique_count=500),
        ]
        hash2 = compute_field_hash_metadata_only(modified_fields)
        
        # hash 应该相同（因为 name, caption, dataType 没变）
        assert hash1 == hash2
    
    def test_field_hash_changes_with_metadata(self, sample_fields):
        """测试元数据变化时 hash 改变"""
        hash1 = compute_field_hash_metadata_only(sample_fields)
        
        # 修改 caption
        modified_fields = [
            MockField(name="year", fieldCaption="年份", dataType="integer"),  # caption 变了
            MockField(name="city", fieldCaption="城市", dataType="string"),
            MockField(name="amount", fieldCaption="金额", dataType="real"),
        ]
        hash2 = compute_field_hash_metadata_only(modified_fields)
        
        # hash 应该不同
        assert hash1 != hash2
    
    def test_field_hash_order_independent(self):
        """测试字段顺序不影响 hash"""
        fields1 = [
            MockField(name="a", fieldCaption="A", dataType="string"),
            MockField(name="b", fieldCaption="B", dataType="integer"),
        ]
        fields2 = [
            MockField(name="b", fieldCaption="B", dataType="integer"),
            MockField(name="a", fieldCaption="A", dataType="string"),
        ]
        
        hash1 = compute_field_hash_metadata_only(fields1)
        hash2 = compute_field_hash_metadata_only(fields2)
        
        # hash 应该相同（按 name 排序）
        assert hash1 == hash2
    
    def test_compute_single_field_hash(self):
        """测试单字段 hash 计算"""
        hash_val = compute_single_field_hash("year", "年", "integer")
        
        # 验证返回 32 字符的 MD5 hash
        assert len(hash_val) == 32
        assert hash_val.isalnum()
    
    def test_single_field_hash_changes_with_caption(self):
        """测试 caption 变化时单字段 hash 改变"""
        hash1 = compute_single_field_hash("year", "年", "integer")
        hash2 = compute_single_field_hash("year", "年份", "integer")
        
        assert hash1 != hash2
    
    def test_single_field_hash_changes_with_datatype(self):
        """测试 dataType 变化时单字段 hash 改变"""
        hash1 = compute_single_field_hash("year", "年", "integer")
        hash2 = compute_single_field_hash("year", "年", "string")
        
        assert hash1 != hash2


# ═══════════════════════════════════════════════════════════
# 缓存 CRUD 测试
# ═══════════════════════════════════════════════════════════

class TestHierarchyCache:
    """测试维度层级缓存 CRUD 操作"""
    
    def test_put_and_get_cache(self, cache_storage):
        """测试存入和获取缓存"""
        cache_key = "ds-123"
        field_hash = "abc123"
        field_meta_hashes = {"year": "hash1", "city": "hash2"}
        hierarchy_data = {
            "year": {"category": "time", "level": 1},
            "city": {"category": "geography", "level": 3},
        }
        
        # 存入
        result = cache_storage.put_hierarchy_cache(
            cache_key=cache_key,
            field_hash=field_hash,
            field_meta_hashes=field_meta_hashes,
            hierarchy_data=hierarchy_data,
        )
        assert result is True
        
        # 获取
        cache = cache_storage.get_hierarchy_cache(cache_key)
        assert cache is not None
        assert cache["cache_key"] == cache_key
        assert cache["field_hash"] == field_hash
        assert cache["field_meta_hashes"] == field_meta_hashes
        assert cache["hierarchy_data"] == hierarchy_data
        assert "created_at" in cache
    
    def test_get_nonexistent_cache(self, cache_storage):
        """测试获取不存在的缓存"""
        cache = cache_storage.get_hierarchy_cache("nonexistent-key")
        assert cache is None
    
    def test_delete_cache(self, cache_storage):
        """测试删除缓存"""
        cache_key = "ds-to-delete"
        
        # 先存入
        cache_storage.put_hierarchy_cache(
            cache_key=cache_key,
            field_hash="hash",
            field_meta_hashes={},
            hierarchy_data={},
        )
        
        # 验证存在
        assert cache_storage.get_hierarchy_cache(cache_key) is not None
        
        # 删除
        result = cache_storage.delete_hierarchy_cache(cache_key)
        assert result is True
        
        # 验证已删除
        assert cache_storage.get_hierarchy_cache(cache_key) is None
    
    def test_update_cache(self, cache_storage):
        """测试更新缓存"""
        cache_key = "ds-update"
        
        # 第一次存入
        cache_storage.put_hierarchy_cache(
            cache_key=cache_key,
            field_hash="hash1",
            field_meta_hashes={"a": "1"},
            hierarchy_data={"a": {"level": 1}},
        )
        
        # 更新
        cache_storage.put_hierarchy_cache(
            cache_key=cache_key,
            field_hash="hash2",
            field_meta_hashes={"a": "2", "b": "3"},
            hierarchy_data={"a": {"level": 2}, "b": {"level": 3}},
        )
        
        # 验证更新
        cache = cache_storage.get_hierarchy_cache(cache_key)
        assert cache["field_hash"] == "hash2"
        assert cache["field_meta_hashes"] == {"a": "2", "b": "3"}
    
    def test_cache_with_empty_key(self, cache_storage):
        """测试空 key 的处理"""
        result = cache_storage.put_hierarchy_cache(
            cache_key="",
            field_hash="hash",
            field_meta_hashes={},
            hierarchy_data={},
        )
        assert result is False
        
        cache = cache_storage.get_hierarchy_cache("")
        assert cache is None
    
    def test_multi_table_cache_key(self, cache_storage):
        """测试多表数据源的缓存 key（luid:tableId 格式）"""
        cache_key = "ds-123:table-456"
        
        cache_storage.put_hierarchy_cache(
            cache_key=cache_key,
            field_hash="hash",
            field_meta_hashes={"field1": "h1"},
            hierarchy_data={"field1": {"level": 1}},
        )
        
        cache = cache_storage.get_hierarchy_cache(cache_key)
        assert cache is not None
        assert cache["cache_key"] == cache_key


# ═══════════════════════════════════════════════════════════
# 模式元数据 CRUD 测试
# ═══════════════════════════════════════════════════════════

class TestPatternMetadata:
    """测试 RAG 模式元数据 CRUD 操作"""
    
    def test_store_and_get_pattern_metadata(self, cache_storage):
        """测试存入和获取模式元数据"""
        pattern_id = "pattern-001"
        
        result = cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption="年",
            data_type="integer",
            sample_values=["2020", "2021", "2022"],
            unique_count=10,
            category="time",
            category_detail="time-year",
            level=1,
            granularity="coarsest",
            reasoning="年份字段，时间维度最粗粒度",
            confidence=0.95,
            datasource_luid="ds-123",
            source=PatternSource.SEED,
            verified=True,
        )
        assert result is True
        
        # 获取
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        assert metadata is not None
        assert metadata["pattern_id"] == pattern_id
        assert metadata["field_caption"] == "年"
        assert metadata["data_type"] == "integer"
        assert metadata["sample_values"] == ["2020", "2021", "2022"]
        assert metadata["unique_count"] == 10
        assert metadata["category"] == "time"
        assert metadata["category_detail"] == "time-year"
        assert metadata["level"] == 1
        assert metadata["granularity"] == "coarsest"
        assert metadata["confidence"] == 0.95
        assert metadata["source"] == "seed"
        assert metadata["verified"] is True
        assert "created_at" in metadata
    
    def test_get_nonexistent_pattern(self, cache_storage):
        """测试获取不存在的模式"""
        metadata = cache_storage.get_pattern_metadata("nonexistent")
        assert metadata is None
    
    def test_delete_pattern_metadata(self, cache_storage):
        """测试删除模式元数据"""
        pattern_id = "pattern-to-delete"
        
        # 先存入
        cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption="测试",
            data_type="string",
            sample_values=[],
            unique_count=0,
            category="other",
            category_detail="other",
            level=1,
            granularity="medium",
            reasoning="测试",
            confidence=0.5,
        )
        
        # 验证存在
        assert cache_storage.get_pattern_metadata(pattern_id) is not None
        
        # 删除
        result = cache_storage.delete_pattern_metadata(pattern_id)
        assert result is True
        
        # 验证已删除
        assert cache_storage.get_pattern_metadata(pattern_id) is None
    
    def test_sample_values_truncation(self, cache_storage):
        """测试 sample_values 截断到 10 个"""
        pattern_id = "pattern-truncate"
        long_samples = [f"value_{i}" for i in range(20)]
        
        cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption="测试",
            data_type="string",
            sample_values=long_samples,
            unique_count=20,
            category="other",
            category_detail="other",
            level=1,
            granularity="medium",
            reasoning="测试",
            confidence=0.5,
        )
        
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        assert len(metadata["sample_values"]) == 10
    
    def test_pattern_source_as_string(self, cache_storage):
        """测试 source 参数可以是字符串"""
        pattern_id = "pattern-string-source"
        
        cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption="测试",
            data_type="string",
            sample_values=[],
            unique_count=0,
            category="other",
            category_detail="other",
            level=1,
            granularity="medium",
            reasoning="测试",
            confidence=0.5,
            source="llm",  # 字符串而非枚举
        )
        
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        assert metadata["source"] == "llm"


# ═══════════════════════════════════════════════════════════
# 验证状态更新测试
# ═══════════════════════════════════════════════════════════

class TestUpdatePatternVerified:
    """测试 update_pattern_verified() 验证状态更新"""
    
    def test_update_verified_to_true(self, cache_storage):
        """测试将 verified 更新为 True"""
        pattern_id = "pattern-verify"
        
        # 存入未验证的模式
        cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption="测试",
            data_type="string",
            sample_values=[],
            unique_count=0,
            category="other",
            category_detail="other",
            level=1,
            granularity="medium",
            reasoning="测试",
            confidence=0.5,
            source=PatternSource.LLM,
            verified=False,
        )
        
        # 验证初始状态
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        assert metadata["verified"] is False
        
        # 更新验证状态
        result = cache_storage.update_pattern_verified(pattern_id, True)
        assert result is True
        
        # 验证更新后状态
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        assert metadata["verified"] is True
        assert "verified_at" in metadata
        assert metadata["verified_at"] is not None
    
    def test_update_verified_to_false(self, cache_storage):
        """测试将 verified 更新为 False"""
        pattern_id = "pattern-unverify"
        
        # 存入已验证的模式
        cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption="测试",
            data_type="string",
            sample_values=[],
            unique_count=0,
            category="other",
            category_detail="other",
            level=1,
            granularity="medium",
            reasoning="测试",
            confidence=0.5,
            verified=True,
        )
        
        # 更新为未验证
        result = cache_storage.update_pattern_verified(pattern_id, False)
        assert result is True
        
        # 验证更新后状态
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        assert metadata["verified"] is False
        assert metadata["verified_at"] is None
    
    def test_update_nonexistent_pattern(self, cache_storage):
        """测试更新不存在的模式"""
        result = cache_storage.update_pattern_verified("nonexistent", True)
        assert result is False


# ═══════════════════════════════════════════════════════════
# get_all 和 clear 测试
# ═══════════════════════════════════════════════════════════

class TestGetAllAndClear:
    """测试 get_all_pattern_metadata() 和 clear_pattern_metadata()"""
    
    def test_get_all_pattern_metadata(self, cache_storage):
        """测试获取所有模式元数据"""
        # 存入多个模式
        for i in range(3):
            cache_storage.store_pattern_metadata(
                pattern_id=f"pattern-{i}",
                field_caption=f"字段{i}",
                data_type="string",
                sample_values=[],
                unique_count=i,
                category="other",
                category_detail="other",
                level=i + 1,
                granularity="medium",
                reasoning=f"测试{i}",
                confidence=0.5 + i * 0.1,
            )
        
        # 获取所有
        all_patterns = cache_storage.get_all_pattern_metadata()
        assert len(all_patterns) == 3
        
        # 验证内容
        pattern_ids = {p["pattern_id"] for p in all_patterns}
        assert pattern_ids == {"pattern-0", "pattern-1", "pattern-2"}
    
    def test_get_all_empty(self, cache_storage):
        """测试空存储时获取所有"""
        all_patterns = cache_storage.get_all_pattern_metadata()
        assert all_patterns == []
    
    def test_clear_pattern_metadata(self, cache_storage):
        """测试清空所有模式元数据"""
        # 存入多个模式
        for i in range(5):
            cache_storage.store_pattern_metadata(
                pattern_id=f"pattern-clear-{i}",
                field_caption=f"字段{i}",
                data_type="string",
                sample_values=[],
                unique_count=0,
                category="other",
                category_detail="other",
                level=1,
                granularity="medium",
                reasoning="测试",
                confidence=0.5,
            )
        
        # 验证存入
        assert len(cache_storage.get_all_pattern_metadata()) == 5
        
        # 清空
        count = cache_storage.clear_pattern_metadata()
        assert count == 5
        
        # 验证已清空
        assert len(cache_storage.get_all_pattern_metadata()) == 0
    
    def test_clear_empty_storage(self, cache_storage):
        """测试清空空存储"""
        count = cache_storage.clear_pattern_metadata()
        assert count == 0


# ═══════════════════════════════════════════════════════════
# 边界情况测试
# ═══════════════════════════════════════════════════════════

class TestEdgeCases:
    """测试边界情况"""
    
    def test_store_explicitly_set_to_none(self):
        """测试显式设置 _store 为 None 时的处理"""
        # 创建 storage 后手动设置 _store 为 None（模拟 store 不可用的情况）
        storage = DimensionHierarchyCacheStorage.__new__(DimensionHierarchyCacheStorage)
        storage._store = None
        
        # 所有操作应该安全返回
        assert storage.get_hierarchy_cache("key") is None
        assert storage.put_hierarchy_cache("key", "hash", {}, {}) is False
        assert storage.delete_hierarchy_cache("key") is False
        assert storage.get_pattern_metadata("id") is None
        assert storage.store_pattern_metadata(
            pattern_id="id",
            field_caption="test",
            data_type="string",
            sample_values=[],
            unique_count=0,
            category="other",
            category_detail="other",
            level=1,
            granularity="medium",
            reasoning="test",
            confidence=0.5,
        ) is False
        assert storage.delete_pattern_metadata("id") is False
        assert storage.get_all_pattern_metadata() == []
        assert storage.clear_pattern_metadata() == 0
    
    def test_unicode_field_caption(self, cache_storage):
        """测试 Unicode 字段名"""
        pattern_id = "pattern-unicode"
        
        cache_storage.store_pattern_metadata(
            pattern_id=pattern_id,
            field_caption="日期時間🕐",  # 包含中文、日文、emoji
            data_type="datetime",
            sample_values=["2024-01-01"],
            unique_count=100,
            category="time",
            category_detail="time-datetime",
            level=5,
            granularity="finest",
            reasoning="日期时间字段",
            confidence=0.9,
        )
        
        metadata = cache_storage.get_pattern_metadata(pattern_id)
        assert metadata["field_caption"] == "日期時間🕐"
    
    def test_large_hierarchy_data(self, cache_storage):
        """测试大量字段的缓存"""
        cache_key = "ds-large"
        
        # 创建 100 个字段的数据
        hierarchy_data = {
            f"field_{i}": {"category": "other", "level": i % 5 + 1}
            for i in range(100)
        }
        field_meta_hashes = {
            f"field_{i}": f"hash_{i}"
            for i in range(100)
        }
        
        cache_storage.put_hierarchy_cache(
            cache_key=cache_key,
            field_hash="large_hash",
            field_meta_hashes=field_meta_hashes,
            hierarchy_data=hierarchy_data,
        )
        
        cache = cache_storage.get_hierarchy_cache(cache_key)
        assert len(cache["hierarchy_data"]) == 100
        assert len(cache["field_meta_hashes"]) == 100
