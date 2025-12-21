# -*- coding: utf-8 -*-
"""
Property-based tests for LangGraph SqliteStore.

**Feature: session-context-caching, Property 1: 缓存存储命名空间一致性**
**Validates: Requirements 1.4**

Tests verify that:
- Data stored with a namespace can be retrieved with the same namespace
- Namespace structure is preserved correctly
"""
import pytest
from hypothesis import given, strategies as st, settings, HealthCheck
import tempfile
import os
import uuid

from tableau_assistant.src.infra.storage.langgraph_store import (
    get_langgraph_store,
    reset_langgraph_store,
)


# Strategy for generating valid datasource LUIDs
datasource_luid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N'), whitelist_characters='-_'),
    min_size=1,
    max_size=50
).filter(lambda x: x.strip() != '')

# Strategy for generating simple JSON-serializable values
simple_value_strategy = st.fixed_dictionaries({
    'name': st.text(min_size=1, max_size=100),
    'count': st.integers(min_value=0, max_value=1000000),
})


def get_temp_db_path():
    """Generate a unique temporary database path."""
    return os.path.join(tempfile.gettempdir(), f"test_store_{uuid.uuid4().hex}.db")


class TestNamespaceConsistency:
    """
    **Feature: session-context-caching, Property 1: 缓存存储命名空间一致性**
    **Validates: Requirements 1.4**
    
    *For any* datasource_luid, data stored in namespace ("metadata", datasource_luid)
    should be retrievable using the same namespace.
    """
    
    @given(
        datasource_luid=datasource_luid_strategy,
        value=simple_value_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_metadata_namespace_roundtrip(
        self,
        datasource_luid: str,
        value: dict,
    ):
        """
        Property: Data stored in metadata namespace can be retrieved with same namespace.
        
        For any valid datasource_luid and value:
        1. Store value at namespace ("metadata", datasource_luid)
        2. Retrieve from same namespace
        3. Retrieved value should equal stored value
        """
        # Use unique temp path for each test run
        temp_db_path = get_temp_db_path()
        
        try:
            # Reset and get fresh store with temp path
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            
            # Define namespace
            namespace = ("metadata", datasource_luid)
            key = "data"
            
            # Store
            store.put(namespace=namespace, key=key, value=value)
            
            # Retrieve
            item = store.get(namespace=namespace, key=key)
            
            # Verify
            assert item is not None, f"Failed to retrieve item for namespace {namespace}"
            assert item.value == value, f"Value mismatch: expected {value}, got {item.value}"
            assert tuple(item.namespace) == namespace, f"Namespace mismatch: expected {namespace}, got {item.namespace}"
        finally:
            # Cleanup
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass
    
    @given(
        datasource_luid=datasource_luid_strategy,
        value=simple_value_strategy,
    )
    @settings(max_examples=100, deadline=None)
    def test_hierarchy_namespace_roundtrip(
        self,
        datasource_luid: str,
        value: dict,
    ):
        """
        Property: Data stored in dimension_hierarchy namespace can be retrieved.
        
        For any valid datasource_luid and value:
        1. Store value at namespace ("dimension_hierarchy", datasource_luid)
        2. Retrieve from same namespace
        3. Retrieved value should equal stored value
        """
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            
            namespace = ("dimension_hierarchy", datasource_luid)
            key = "data"
            
            store.put(namespace=namespace, key=key, value=value)
            item = store.get(namespace=namespace, key=key)
            
            assert item is not None
            assert item.value == value
            assert tuple(item.namespace) == namespace
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
        value1=simple_value_strategy,
        value2=simple_value_strategy,
    )
    @settings(max_examples=50, deadline=None)
    def test_different_namespaces_isolated(
        self,
        datasource_luid1: str,
        datasource_luid2: str,
        value1: dict,
        value2: dict,
    ):
        """
        Property: Different namespaces are isolated from each other.
        
        For any two different datasource_luids:
        1. Store different values in each namespace
        2. Each namespace should return its own value
        """
        # Skip if same luid (would overwrite)
        if datasource_luid1 == datasource_luid2:
            return
        
        temp_db_path = get_temp_db_path()
        
        try:
            reset_langgraph_store()
            store = get_langgraph_store(db_path=temp_db_path)
            
            namespace1 = ("metadata", datasource_luid1)
            namespace2 = ("metadata", datasource_luid2)
            key = "data"
            
            # Store both
            store.put(namespace=namespace1, key=key, value=value1)
            store.put(namespace=namespace2, key=key, value=value2)
            
            # Retrieve and verify isolation
            item1 = store.get(namespace=namespace1, key=key)
            item2 = store.get(namespace=namespace2, key=key)
            
            assert item1 is not None
            assert item2 is not None
            assert item1.value == value1
            assert item2.value == value2
        finally:
            reset_langgraph_store()
            if os.path.exists(temp_db_path):
                try:
                    os.remove(temp_db_path)
                except Exception:
                    pass


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
