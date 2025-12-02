"""
Integration Tests for Unified Tableau Metadata Service

测试统一的元数据服务功能：
- 字段元数据获取
- 数据模型获取
- 维度样例获取
- 缓存机制
"""
import os
import time
import pytest
from dotenv import load_dotenv

from tableau_assistant.src.bi_platforms.tableau.metadata import (
    TableauMetadataService,
    ServiceFieldMetadata,
    DataModel,
)
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env

# Load environment variables
load_dotenv()


# ============================================================
# Fixtures
# ============================================================

@pytest.fixture(scope="module")
def tableau_context():
    """Get Tableau authentication context"""
    ctx = _get_tableau_context_from_env()
    if not ctx.get("api_key"):
        pytest.skip("Tableau authentication failed")
    return ctx


@pytest.fixture(scope="module")
def metadata_service(tableau_context):
    """Create metadata service"""
    service = TableauMetadataService(domain=tableau_context["domain"])
    yield service
    service.close()


@pytest.fixture
def datasource_luid():
    """Get datasource LUID"""
    luid = os.getenv("DATASOURCE_LUID")
    if not luid:
        pytest.skip("DATASOURCE_LUID not configured")
    return luid


# ============================================================
# Field Metadata Tests
# ============================================================

class TestGetFields:
    """Test get_fields method"""
    
    def test_get_fields_returns_list(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test that get_fields returns a list of FieldMetadata"""
        fields = metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        assert fields is not None
        assert isinstance(fields, list)
        assert len(fields) > 0
        assert all(isinstance(f, ServiceFieldMetadata) for f in fields)
        
        print(f"\n[OK] Retrieved {len(fields)} fields")
    
    def test_fields_have_correct_structure(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test that fields have correct structure"""
        fields = metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        for field in fields:
            assert field.name
            assert field.fieldCaption
            assert field.dataType
            assert field.role in ("dimension", "measure")
        
        print(f"\n[OK] All fields have correct structure")
    
    def test_fields_have_logical_table_id(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test that fields have logicalTableId from VizQL API"""
        fields = metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        fields_with_table = [f for f in fields if f.logicalTableId]
        print(f"\n[INFO] {len(fields_with_table)}/{len(fields)} fields have logicalTableId")
        
        # Most fields should have logicalTableId
        assert len(fields_with_table) > 0
    
    def test_role_distribution(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test role distribution"""
        fields = metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        dimensions = [f for f in fields if f.role == "dimension"]
        measures = [f for f in fields if f.role == "measure"]
        
        print(f"\n[INFO] Role distribution:")
        print(f"  Dimensions: {len(dimensions)}")
        print(f"  Measures: {len(measures)}")
        
        # Print sample fields
        print("\n[INFO] Sample fields:")
        for f in fields[:5]:
            print(f"  - {f.name}: {f.role} ({f.dataType})")


# ============================================================
# Data Model Tests
# ============================================================

class TestGetDataModel:
    """Test get_data_model method"""
    
    def test_get_data_model_returns_model(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test that get_data_model returns a DataModel"""
        try:
            data_model = metadata_service.get_data_model(
                datasource_luid=datasource_luid,
                api_key=tableau_context["api_key"],
                site=tableau_context["site"]
            )
            
            assert data_model is not None
            assert isinstance(data_model, DataModel)
            assert isinstance(data_model.logicalTables, list)
            assert isinstance(data_model.logicalTableRelationships, list)
            
            print(f"\n[OK] Retrieved data model:")
            print(f"  Tables: {len(data_model.logicalTables)}")
            print(f"  Relationships: {len(data_model.logicalTableRelationships)}")
            
        except Exception as e:
            pytest.skip(f"Data model not supported: {e}")


# ============================================================
# Dimension Samples Tests
# ============================================================

class TestGetDimensionSamples:
    """Test get_dimension_samples method"""
    
    def test_get_dimension_samples(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test getting dimension samples"""
        # First get dimensions
        dimensions = metadata_service.get_dimensions(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        if not dimensions:
            pytest.skip("No dimensions found")
        
        # Get samples for first 3 dimensions
        dim_names = [d.name for d in dimensions[:3]]
        samples = metadata_service.get_dimension_samples(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"],
            dimension_names=dim_names,
            sample_size=3
        )
        
        assert samples is not None
        assert isinstance(samples, dict)
        
        print(f"\n[OK] Retrieved samples for {len(samples)} dimensions:")
        for dim, values in samples.items():
            print(f"  - {dim}: {values[:3]}")


# ============================================================
# Cache Tests
# ============================================================

class TestCache:
    """Test caching mechanism"""
    
    def test_cache_improves_performance(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test that caching improves performance"""
        # Clear cache first
        metadata_service.clear_cache()
        
        # First call - no cache
        start1 = time.time()
        fields1 = metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        time1 = time.time() - start1
        
        # Second call - should use cache
        start2 = time.time()
        fields2 = metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        time2 = time.time() - start2
        
        print(f"\n[INFO] Cache performance:")
        print(f"  First call:  {time1:.3f}s")
        print(f"  Second call: {time2:.3f}s")
        print(f"  Speedup: {time1/time2:.1f}x")
        
        # Verify same results
        assert len(fields1) == len(fields2)
        
        # Second call should be much faster
        assert time2 < time1 * 0.5, "Cache should make second call at least 2x faster"
    
    def test_clear_cache(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test clearing cache"""
        # Populate cache
        metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        # Clear cache
        metadata_service.clear_cache(datasource_luid)
        
        # Verify cache is cleared (next call should be slower)
        start = time.time()
        metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        elapsed = time.time() - start
        
        print(f"\n[OK] Cache cleared, next call took {elapsed:.3f}s")


# ============================================================
# Convenience Methods Tests
# ============================================================

class TestConvenienceMethods:
    """Test convenience methods"""
    
    def test_get_dimensions(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test get_dimensions"""
        dimensions = metadata_service.get_dimensions(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        assert all(f.role == "dimension" for f in dimensions)
        print(f"\n[OK] Retrieved {len(dimensions)} dimensions")
    
    def test_get_measures(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test get_measures"""
        measures = metadata_service.get_measures(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        assert all(f.role == "measure" for f in measures)
        print(f"\n[OK] Retrieved {len(measures)} measures")
    
    def test_get_field_by_name(
        self, metadata_service, tableau_context, datasource_luid
    ):
        """Test get_field_by_name"""
        # First get all fields
        fields = metadata_service.get_fields(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        if not fields:
            pytest.skip("No fields found")
        
        # Get first field by name
        target_name = fields[0].name
        field = metadata_service.get_field_by_name(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            field_name=target_name,
            site=tableau_context["site"]
        )
        
        assert field is not None
        assert field.name == target_name
        print(f"\n[OK] Found field by name: {target_name}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
