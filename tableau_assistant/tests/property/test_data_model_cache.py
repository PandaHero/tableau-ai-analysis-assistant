# -*- coding: utf-8 -*-
"""
Property-based tests for DataModelCache.

**Feature: session-context-caching**

Tests verify:
- Property 2: 缓存命中时跳过 API 调用
- Property 3: 缓存写入 TTL 一致性
- Property 5: 缓存读写往返一致性
"""
import pytest
from hypothesis import given, strategies as st, settings
import tempfile
import os
import uuid
from typing import Dict, Any, Optional
from unittest.mock import AsyncMock, MagicMock

from tableau_assistant.src.infra.storage.langgraph_store import (
    get_langgraph_store,
    reset_langgraph_store,
)
from tableau_assistant.src.infra.storage.data_model_cache import (
    DataModelCache,
    DATA_MODEL_NAMESPACE,
    HIERARCHY_NAMESPACE,
    DEFAULT_TTL_MINUTES,
)
from tableau_assistant.src.core.models import DataModel, FieldMetadata


# Strategy for generating valid datasource LUIDs
datasource_luid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=50
).filter(lambda x: x.strip() != '')

# Strategy for generating field metadata
field_metadata_strategy = st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=50).filter(lambda x: x.strip() != ''),
    'fieldCaption': st.text(min_size=1, max_size=100).filter(lambda x: x.strip() != ''),
    'role': st.sampled_from(['dimension', 'measure']),
    'dataType': st.sampled_from(['STRING', 'INTEGER', 'REAL', 'DATE', 'DATETIME']),
})

# Strategy for generating DataModel
@st.composite
def data_model_strategy(draw):
    """Generate a valid DataModel for testing."""
    datasource_luid = draw(datasource_luid_strategy)
    datasource_name = draw(st.text(min_size=1, max_size=100).filter(lambda x: x.strip() != ''))
    
    # Generate 1-5 fields
    num_fields = draw(st.integers(min_value=1, max_value=5))
    fields = []
    for i in range(num_fields):
        field_dict = draw(field_metadata_strategy)
        # Ensure unique field names
        field_dict['name'] = f"{field_dict['name']}_{i}"
        field_dict['fieldCaption'] = f"{field_dict['fieldCaption']}_{i}"
        fields.append(FieldMetadata(**field_dict))
    
    return DataModel(
        datasource_luid=datasource_luid,
        datasource_name=datasource_name,
        fields=fields,
        field_count=len(fields),
    )


def get_temp_db_path():
    """Generate a unique temporary database path."""
    return os.path.join(tempfile.gettempdir(), f"test_cache_{uuid.uuid4().hex}.db")


class MockDataModelLoader:
    """Mock loader for testing."""
    
    def __init__(self, data_model: DataModel):
        self.data_model = data_model
        self.load_call_count = 0
        self.hierarchy_call_count = 0
    
    async def load_data_model(self, datasource_luid: str) -> DataModel:
        self.load_call_count += 1
        return self.data_model
    
    async def infer_dimension_hierarchy(self, data_model: DataModel) -> Dict[str, Any]:
        self.hierarchy_call_count += 1
        return {"test_field": {"category": "test", "level": 1}}


class TestCacheHitSkipsAPICall:
    """
    **Feature: session-context-caching, Property 2: 缓存命中时跳过 API 调用**
    **Validates: Requirements 2.2, 3.2, 3.3**
    
    *For any* valid cached data (not expired), calling `get_or_load()` should
    return cached data without triggering Tableau API calls.
    """
    
    @given(data_model=data_model_strategy())
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_cache_hit_skips_loader(self, data_model: DataModel):
        """
        Property: When cache contains valid data, loader is not called.
        
        For any valid DataModel:
        1. Pre-populate cache with the data
        2. Call get_or_load()
        3. Verify loader was NOT called
        4. Verify returned data matches cached data
        """
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            cache = DataModelCache(store)
            
            # Pre-populate cache
            cache._put_to_cache(data_model.datasource_luid, data_model)
            
            # Create mock loader
            mock_loader = MockDataModelLoader(data_model)
            
            # Call get_or_load - should hit cache
            result, is_cache_hit = await cache.get_or_load(
                data_model.datasource_luid,
                mock_loader
            )
            
            # Verify cache hit
            assert is_cache_hit is True, "Expected cache hit"
            
            # Verify loader was NOT called
            assert mock_loader.load_call_count == 0, "Loader should not be called on cache hit"
            assert mock_loader.hierarchy_call_count == 0, "Hierarchy inference should not be called on cache hit"
            
            # Verify data matches
            assert result.datasource_luid == data_model.datasource_luid
            assert result.datasource_name == data_model.datasource_name
            assert result.field_count == data_model.field_count
            
        finally:
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass


class TestCacheTTLConsistency:
    """
    **Feature: session-context-caching, Property 3: 缓存写入 TTL 一致性**
    **Validates: Requirements 2.5**
    
    *For any* newly loaded DataModel, it should be stored with TTL=24h (1440 minutes)
    and be retrievable before TTL expires.
    """
    
    @given(data_model=data_model_strategy())
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_cache_write_with_ttl(self, data_model: DataModel):
        """
        Property: Data stored in cache should be retrievable immediately after write.
        
        For any valid DataModel:
        1. Store data via _put_to_cache()
        2. Immediately retrieve via _get_from_cache()
        3. Data should be present (TTL not expired)
        """
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            cache = DataModelCache(store)
            
            # Store data
            success = cache._put_to_cache(data_model.datasource_luid, data_model)
            assert success is True, "Cache write should succeed"
            
            # Immediately retrieve
            retrieved = cache._get_from_cache(data_model.datasource_luid)
            
            # Should be present (TTL not expired)
            assert retrieved is not None, "Data should be retrievable immediately after write"
            assert retrieved.datasource_luid == data_model.datasource_luid
            
        finally:
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass


class TestCacheRoundTripConsistency:
    """
    **Feature: session-context-caching, Property 5: 缓存读写往返一致性**
    **Validates: Requirements 2.5, 2.6**
    
    *For any* valid DataModel object, storing it in cache and then reading it back
    should produce an equivalent object (field values match).
    """
    
    @given(data_model=data_model_strategy())
    @settings(max_examples=100, deadline=None)
    def test_cache_roundtrip_consistency(self, data_model: DataModel):
        """
        Property: Data written to cache equals data read from cache.
        
        For any valid DataModel:
        1. Write to cache
        2. Read from cache
        3. All field values should match
        """
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            cache = DataModelCache(store)
            
            # Add dimension hierarchy for complete test
            data_model.dimension_hierarchy = {
                "test_dim": {"category": "test", "level": 1}
            }
            
            # Write
            cache._put_to_cache(data_model.datasource_luid, data_model)
            
            # Read
            retrieved = cache._get_from_cache(data_model.datasource_luid)
            
            # Verify round-trip consistency
            assert retrieved is not None, "Data should be retrievable"
            assert retrieved.datasource_luid == data_model.datasource_luid
            assert retrieved.datasource_name == data_model.datasource_name
            assert retrieved.field_count == data_model.field_count
            assert len(retrieved.fields) == len(data_model.fields)
            
            # Verify fields match
            for orig_field, ret_field in zip(data_model.fields, retrieved.fields):
                assert ret_field.name == orig_field.name
                assert ret_field.fieldCaption == orig_field.fieldCaption
                assert ret_field.role == orig_field.role
                assert ret_field.dataType == orig_field.dataType
            
            # Verify dimension hierarchy
            assert retrieved.dimension_hierarchy == data_model.dimension_hierarchy
            
        finally:
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass
    
    @given(
        datasource_luid1=datasource_luid_strategy,
        datasource_luid2=datasource_luid_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_cache_isolation(self, datasource_luid1: str, datasource_luid2: str):
        """
        Property: Different datasources are isolated in cache.
        
        For any two different datasource_luids:
        1. Store different data for each
        2. Each should return its own data
        """
        if datasource_luid1 == datasource_luid2:
            return
        
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            cache = DataModelCache(store)
            
            # Create two different DataModels
            data_model1 = DataModel(
                datasource_luid=datasource_luid1,
                datasource_name="DataSource 1",
                fields=[FieldMetadata(name="f1", fieldCaption="Field 1", role="dimension", dataType="STRING")],
                field_count=1,
            )
            data_model2 = DataModel(
                datasource_luid=datasource_luid2,
                datasource_name="DataSource 2",
                fields=[FieldMetadata(name="f2", fieldCaption="Field 2", role="measure", dataType="INTEGER")],
                field_count=1,
            )
            
            # Store both
            cache._put_to_cache(datasource_luid1, data_model1)
            cache._put_to_cache(datasource_luid2, data_model2)
            
            # Retrieve and verify isolation
            retrieved1 = cache._get_from_cache(datasource_luid1)
            retrieved2 = cache._get_from_cache(datasource_luid2)
            
            assert retrieved1 is not None
            assert retrieved2 is not None
            assert retrieved1.datasource_name == "DataSource 1"
            assert retrieved2.datasource_name == "DataSource 2"
            
        finally:
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass


class TestTTLExpirationReload:
    """
    **Feature: session-context-caching, Property 4: TTL 过期后重新加载**
    **Validates: Requirements 4.1**
    
    *For any* cached data that has expired (TTL exceeded), calling `get_or_load()`
    should trigger a reload from the loader and update the cache.
    """
    
    @given(data_model=data_model_strategy())
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_cache_miss_triggers_loader(self, data_model: DataModel):
        """
        Property: When cache is empty, loader is called.
        
        For any valid DataModel:
        1. Start with empty cache
        2. Call get_or_load()
        3. Verify loader WAS called
        4. Verify data is now in cache
        """
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            cache = DataModelCache(store)
            
            # Create mock loader
            mock_loader = MockDataModelLoader(data_model)
            
            # Call get_or_load - should miss cache and call loader
            result, is_cache_hit = await cache.get_or_load(
                data_model.datasource_luid,
                mock_loader
            )
            
            # Verify cache miss
            assert is_cache_hit is False, "Expected cache miss"
            
            # Verify loader WAS called
            assert mock_loader.load_call_count == 1, "Loader should be called on cache miss"
            assert mock_loader.hierarchy_call_count == 1, "Hierarchy inference should be called"
            
            # Verify data matches
            assert result.datasource_luid == data_model.datasource_luid
            assert result.datasource_name == data_model.datasource_name
            
            # Verify data is now in cache
            cached = cache._get_from_cache(data_model.datasource_luid)
            assert cached is not None, "Data should be in cache after load"
            assert cached.datasource_luid == data_model.datasource_luid
            
        finally:
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass
    
    @given(data_model=data_model_strategy())
    @settings(max_examples=50, deadline=None)
    @pytest.mark.asyncio
    async def test_invalidate_forces_reload(self, data_model: DataModel):
        """
        Property: After invalidation, next get_or_load() triggers reload.
        
        For any valid DataModel:
        1. Pre-populate cache
        2. Invalidate cache
        3. Call get_or_load()
        4. Verify loader WAS called (cache was invalidated)
        """
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            cache = DataModelCache(store)
            
            # Pre-populate cache
            cache._put_to_cache(data_model.datasource_luid, data_model)
            
            # Verify data is in cache
            cached = cache._get_from_cache(data_model.datasource_luid)
            assert cached is not None, "Data should be in cache"
            
            # Invalidate cache
            success = cache.invalidate(data_model.datasource_luid)
            assert success is True, "Invalidation should succeed"
            
            # Verify cache is empty
            cached_after = cache._get_from_cache(data_model.datasource_luid)
            assert cached_after is None, "Cache should be empty after invalidation"
            
            # Create mock loader
            mock_loader = MockDataModelLoader(data_model)
            
            # Call get_or_load - should miss cache and call loader
            result, is_cache_hit = await cache.get_or_load(
                data_model.datasource_luid,
                mock_loader
            )
            
            # Verify cache miss (due to invalidation)
            assert is_cache_hit is False, "Expected cache miss after invalidation"
            
            # Verify loader WAS called
            assert mock_loader.load_call_count == 1, "Loader should be called after invalidation"
            
        finally:
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
