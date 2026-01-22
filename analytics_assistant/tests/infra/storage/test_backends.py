"""
测试存储模块

测试 langgraph_store 提供的存储能力：
- KV 存储（LangGraph SqliteStore）
- 向量存储（LangChain FAISS）
- 缓存管理器
"""
import pytest
import tempfile
from pathlib import Path


class TestKVStore:
    """测试 KV 存储（LangGraph SqliteStore）"""
    
    def test_singleton(self):
        """测试单例模式"""
        from analytics_assistant.src.infra.storage import (
            get_kv_store, 
            reset_kv_store
        )
        
        reset_kv_store()
        
        store1 = get_kv_store()
        store2 = get_kv_store()
        assert store1 is store2
        
        reset_kv_store()
    
    def test_basic_operations(self):
        """测试基本操作"""
        from analytics_assistant.src.infra.storage import (
            get_kv_store, 
            reset_kv_store
        )
        
        reset_kv_store()
        store = get_kv_store()
        namespace = ("test", "basic")
        
        # Put
        store.put(namespace, "key1", {"data": "value1"})
        
        # Get
        item = store.get(namespace, "key1")
        assert item is not None
        assert item.value == {"data": "value1"}
        
        # Delete
        store.delete(namespace, "key1")
        item = store.get(namespace, "key1")
        assert item is None
        
        reset_kv_store()
    
    def test_namespace_isolation(self):
        """测试命名空间隔离"""
        from analytics_assistant.src.infra.storage import (
            get_kv_store, 
            reset_kv_store
        )
        
        reset_kv_store()
        store = get_kv_store()
        
        ns1 = ("ns1",)
        ns2 = ("ns2",)
        
        store.put(ns1, "key1", "value_ns1")
        store.put(ns2, "key1", "value_ns2")
        
        assert store.get(ns1, "key1").value == "value_ns1"
        assert store.get(ns2, "key1").value == "value_ns2"
        
        reset_kv_store()


class TestCacheManager:
    """测试缓存管理器"""
    
    def test_basic_operations(self):
        """测试基本操作"""
        from analytics_assistant.src.infra.storage import CacheManager, reset_kv_store
        
        reset_kv_store()
        cache = CacheManager("test_cache")
        
        # Set
        assert cache.set("key1", {"data": "value1"})
        
        # Get
        value = cache.get("key1")
        assert value == {"data": "value1"}
        
        # Exists
        assert cache.exists("key1")
        assert not cache.exists("key2")
        
        # Delete
        assert cache.delete("key1")
        assert cache.get("key1") is None
        
        reset_kv_store()
    
    def test_get_or_compute(self):
        """测试 get_or_compute"""
        from analytics_assistant.src.infra.storage import CacheManager, reset_kv_store
        
        reset_kv_store()
        cache = CacheManager("test_compute")
        
        # 先清理可能存在的缓存
        cache.delete("key1")
        
        compute_count = [0]
        
        def expensive_fn():
            compute_count[0] += 1
            return {"result": "computed"}
        
        # 第一次调用，应该计算
        result1 = cache.get_or_compute("key1", expensive_fn)
        assert result1 == {"result": "computed"}
        assert compute_count[0] == 1
        
        # 第二次调用，应该从缓存获取
        result2 = cache.get_or_compute("key1", expensive_fn)
        assert result2 == {"result": "computed"}
        assert compute_count[0] == 1  # 没有再次计算
        
        reset_kv_store()
    
    def test_stats(self):
        """测试统计信息"""
        from analytics_assistant.src.infra.storage import CacheManager, reset_kv_store
        
        reset_kv_store()
        cache = CacheManager("test_stats")
        
        cache.set("key1", "value1")
        cache.get("key1")  # hit
        cache.get("key2")  # miss
        
        stats = cache.get_stats()
        assert stats["hits"] == 1
        assert stats["misses"] == 1
        assert stats["sets"] == 1
        
        reset_kv_store()


class TestVectorStore:
    """测试向量存储"""
    
    def test_faiss_creation(self):
        """测试 FAISS 创建"""
        from analytics_assistant.src.infra.storage import get_vector_store
        from langchain_core.embeddings import Embeddings
        
        # Mock embeddings
        class MockEmbeddings(Embeddings):
            def embed_documents(self, texts):
                return [[0.1] * 384 for _ in texts]
            def embed_query(self, text):
                return [0.1] * 384
        
        embeddings = MockEmbeddings()
        
        # FAISS 需要先有数据才能创建，get_vector_store 返回 None
        store = get_vector_store("faiss", embeddings, "test_collection")
        # 返回 None 是预期行为，需要用 FAISS.from_texts() 创建
        assert store is None
    
    def test_invalid_backend(self):
        """测试无效后端"""
        from analytics_assistant.src.infra.storage import get_vector_store
        
        with pytest.raises(ValueError, match="不支持的向量存储后端"):
            get_vector_store("invalid", None, "test")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
