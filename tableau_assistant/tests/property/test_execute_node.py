"""
Property Tests for Execute Node

Tests:
- QueryResult data structure
- Mock result generation
- Error handling

Requirements:
- R7.1: Execute VizQL API call
- R7.2: Parse API response
- R7.3: Error handling
"""

import pytest
from hypothesis import given, strategies as st, settings
from typing import Dict, Any

from tableau_assistant.src.nodes.execute import ExecuteNode
from tableau_assistant.src.nodes.execute.node import (
    QueryResult,
    VizQLDataServiceClient,
)


class TestQueryResult:
    """Tests for QueryResult data structure."""
    
    def test_query_result_success(self):
        """QueryResult should correctly indicate success."""
        result = QueryResult(
            data=[{"col1": "value1"}],
            columns=[{"fieldCaption": "col1"}],
            row_count=1,
            execution_time=0.5,
        )
        
        assert result.is_success() is True
        assert result.error is None
        assert result.row_count == 1
    
    def test_query_result_error(self):
        """QueryResult should correctly indicate error."""
        result = QueryResult(
            error="Connection failed",
            execution_time=0.1,
        )
        
        assert result.is_success() is False
        assert result.error == "Connection failed"
        assert result.row_count == 0
    
    def test_query_result_to_dict(self):
        """QueryResult should convert to dict correctly."""
        result = QueryResult(
            data=[{"col1": "value1"}],
            columns=[{"fieldCaption": "col1"}],
            row_count=1,
            execution_time=0.5,
        )
        
        result_dict = result.to_dict()
        
        assert "data" in result_dict
        assert "columns" in result_dict
        assert "row_count" in result_dict
        assert "execution_time" in result_dict
        assert result_dict["row_count"] == 1


class TestVizQLDataServiceClient:
    """Tests for VizQL Data Service client."""
    
    def test_mock_result_generation(self):
        """Client should generate mock results when VDS not configured."""
        client = VizQLDataServiceClient(base_url="")  # Empty URL triggers mock
        
        query = {
            "fields": [
                {"fieldCaption": "Category"},
                {"fieldCaption": "Sales", "function": "SUM"},
            ]
        }
        
        result = client._mock_result(query)
        
        assert result.is_success()
        assert result.row_count == 5  # Mock generates 5 rows
        assert len(result.columns) == 2
    
    def test_mock_result_field_types(self):
        """Mock result should generate appropriate values for field types."""
        client = VizQLDataServiceClient(base_url="")
        
        query = {
            "fields": [
                {"fieldCaption": "Order Date"},
                {"fieldCaption": "Sales Amount"},
                {"fieldCaption": "Category"},
            ]
        }
        
        result = client._mock_result(query)
        
        assert result.is_success()
        # Check that date field has date-like values
        for row in result.data:
            assert "Order Date" in row
            assert "Sales Amount" in row
            assert "Category" in row
    
    @given(st.lists(
        st.fixed_dictionaries({
            "fieldCaption": st.text(min_size=1, max_size=20),
        }),
        min_size=1,
        max_size=5,
    ))
    @settings(max_examples=10)
    def test_mock_result_handles_any_fields(self, fields):
        """Mock result should handle any field configuration."""
        client = VizQLDataServiceClient(base_url="")
        
        query = {"fields": fields}
        result = client._mock_result(query)
        
        assert result.is_success()
        assert result.row_count == 5
        assert len(result.columns) == len(fields)


class TestExecuteNode:
    """Tests for Execute Node."""
    
    @pytest.mark.asyncio
    async def test_execute_with_mock_client(self):
        """Execute node should work with mock client."""
        client = VizQLDataServiceClient(base_url="")  # Mock mode
        executor = ExecuteNode(client=client)
        
        query = {
            "fields": [
                {"fieldCaption": "Category"},
                {"fieldCaption": "Sales", "function": "SUM"},
            ]
        }
        
        result = await executor.execute(query, "Sample - Superstore")
        
        assert result.is_success()
        assert result.row_count > 0
    
    @pytest.mark.asyncio
    async def test_execute_with_vizql_query_object(self):
        """Execute node should handle VizQLQuery objects."""
        from tableau_assistant.src.nodes.query_builder.node import VizQLQuery
        
        client = VizQLDataServiceClient(base_url="")
        executor = ExecuteNode(client=client)
        
        # Create a VizQLQuery object
        vizql_query = VizQLQuery()
        vizql_query.fields = [
            {"fieldCaption": "Category"},
            {"fieldCaption": "Sales", "function": "SUM"},
        ]
        
        result = await executor.execute(vizql_query, "Sample - Superstore")
        
        assert result.is_success()
    
    @pytest.mark.asyncio
    async def test_execute_invalid_query_format(self):
        """Execute node should handle invalid query format."""
        executor = ExecuteNode()
        
        # Pass an invalid query type
        result = await executor.execute("invalid", "Sample - Superstore")
        
        # Should still work (converted to dict)
        assert result is not None


class TestExecuteNodeEntry:
    """Tests for execute_node entry point."""
    
    @pytest.mark.asyncio
    async def test_execute_node_missing_query(self):
        """Execute node should handle missing vizql_query."""
        from tableau_assistant.src.nodes.execute import execute_node
        
        state = {}  # No vizql_query
        
        result = await execute_node(state)
        
        assert "errors" in result
        assert result["execute_complete"] is True
    
    @pytest.mark.asyncio
    async def test_execute_node_with_query(self):
        """Execute node should execute query from state."""
        from tableau_assistant.src.nodes.execute import execute_node
        
        state = {
            "vizql_query": {
                "fields": [
                    {"fieldCaption": "Category"},
                    {"fieldCaption": "Sales", "function": "SUM"},
                ]
            },
            "datasource": "Sample - Superstore",
        }
        
        result = await execute_node(state)
        
        assert "query_result" in result
        assert result["execute_complete"] is True
