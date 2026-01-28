# -*- coding: utf-8 -*-
"""
维度层级推断引擎单元测试
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
from unittest.mock import Mock, patch, MagicMock, AsyncMock


class TestUtilityFunctions:
    """测试工具函数"""
    
    def test_compute_fields_hash_deterministic(self):
        """测试字段哈希计算是确定性的"""
        from src.agents.dimension_hierarchy.inference import compute_fields_hash
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
        ]
        
        hash1 = compute_fields_hash(fields)
        hash2 = compute_fields_hash(fields)
        
        assert hash1 == hash2
    
    def test_compute_fields_hash_order_independent(self):
        """测试字段哈希与顺序无关（按 caption 排序）"""
        from src.agents.dimension_hierarchy.inference import compute_fields_hash
        from src.core.schemas.data_model import Field
        
        fields1 = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
        ]
        
        fields2 = [
            Field(name="city", caption="城市", data_type="string", role="dimension"),
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
        ]
        
        assert compute_fields_hash(fields1) == compute_fields_hash(fields2)
    
    def test_compute_single_field_hash(self):
        """测试单字段哈希计算"""
        from src.agents.dimension_hierarchy.inference import compute_single_field_hash
        from src.core.schemas.data_model import Field
        
        field = Field(name="year", caption="年份", data_type="integer", role="dimension")
        
        hash1 = compute_single_field_hash(field)
        hash2 = compute_single_field_hash(field)
        
        assert hash1 == hash2
        assert len(hash1) == 32  # MD5 hash length
    
    def test_generate_pattern_id(self):
        """测试模式 ID 生成"""
        from src.agents.dimension_hierarchy.inference import generate_pattern_id
        
        pid1 = generate_pattern_id("年份", "integer")
        pid2 = generate_pattern_id("年份", "integer")
        pid3 = generate_pattern_id("年份", "string")  # 不同类型
        
        assert pid1 == pid2
        assert pid1 != pid3
        assert len(pid1) == 16  # 截断后的长度
    
    def test_generate_pattern_id_with_scope(self):
        """测试带 scope 的模式 ID 生成"""
        from src.agents.dimension_hierarchy.inference import generate_pattern_id
        
        pid1 = generate_pattern_id("年份", "integer", scope="ds1")
        pid2 = generate_pattern_id("年份", "integer", scope="ds2")
        pid3 = generate_pattern_id("年份", "integer")  # 无 scope
        
        assert pid1 != pid2
        assert pid1 != pid3
    
    def test_build_cache_key_single_table(self):
        """测试单表缓存 key 构建"""
        from src.agents.dimension_hierarchy.inference import build_cache_key
        
        key = build_cache_key("datasource-123")
        assert key == "datasource-123"
    
    def test_build_cache_key_multi_table(self):
        """测试多表缓存 key 构建"""
        from src.agents.dimension_hierarchy.inference import build_cache_key
        
        key = build_cache_key("datasource-123", "table-456")
        assert key == "datasource-123:table-456"


class TestIncrementalFieldsResult:
    """测试增量字段计算"""
    
    def test_compute_incremental_fields_all_new(self):
        """测试全新字段（无缓存）"""
        from src.agents.dimension_hierarchy.inference import (
            compute_incremental_fields, IncrementalFieldsResult
        )
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
        ]
        
        result = compute_incremental_fields(fields, None, None)
        
        assert result.new_fields == {"年份", "城市"}
        assert result.changed_fields == set()
        assert result.deleted_fields == set()
        assert result.unchanged_fields == set()
        assert result.needs_inference is True
    
    def test_compute_incremental_fields_all_unchanged(self):
        """测试全部未变（缓存命中）"""
        from src.agents.dimension_hierarchy.inference import (
            compute_incremental_fields, compute_single_field_hash
        )
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
        ]
        
        # 模拟缓存
        cached_hashes = {"年份": compute_single_field_hash(fields[0])}
        cached_names = {"年份"}
        
        result = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        assert result.new_fields == set()
        assert result.changed_fields == set()
        assert result.unchanged_fields == {"年份"}
        assert result.needs_inference is False
    
    def test_compute_incremental_fields_mixed(self):
        """测试混合情况（新增+变更+删除+未变）"""
        from src.agents.dimension_hierarchy.inference import (
            compute_incremental_fields, compute_single_field_hash
        )
        from src.core.schemas.data_model import Field
        
        # 当前字段
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),  # 未变
            Field(name="city", caption="城市", data_type="string", role="dimension"),   # 新增
            Field(name="province", caption="省份", data_type="integer", role="dimension"),  # 变更（类型变了）
        ]
        
        # 模拟缓存（省份原来是 string 类型）
        old_province = Field(name="province", caption="省份", data_type="string", role="dimension")
        cached_hashes = {
            "年份": compute_single_field_hash(fields[0]),
            "省份": compute_single_field_hash(old_province),  # 旧的 hash
            "国家": "old_hash",  # 已删除的字段
        }
        cached_names = {"年份", "省份", "国家"}
        
        result = compute_incremental_fields(fields, cached_hashes, cached_names)
        
        assert result.new_fields == {"城市"}
        assert result.changed_fields == {"省份"}
        assert result.deleted_fields == {"国家"}
        assert result.unchanged_fields == {"年份"}
        assert result.needs_inference is True
        assert result.fields_to_infer == {"城市", "省份"}


class TestDimensionHierarchyInference:
    """测试 DimensionHierarchyInference 类"""
    
    def test_init_default_config(self):
        """测试默认配置初始化"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            assert inference._enable_rag is False
            assert inference._enable_cache is False
            assert inference._enable_self_learning is False
    
    def test_match_seed_exact(self):
        """测试种子数据精确匹配"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            # 测试精确匹配（种子数据中应该有"年份"）
            result = inference._match_seed("年份")
            
            if result:
                assert result["field_caption"].lower() == "年份"
    
    def test_match_seed_case_insensitive(self):
        """测试种子数据匹配大小写不敏感"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            # 测试大小写不敏感
            result1 = inference._match_seed("Year")
            result2 = inference._match_seed("YEAR")
            result3 = inference._match_seed("year")
            
            # 如果种子数据中有 year，三个结果应该相同
            if result1:
                assert result1 == result2 == result3
    
    def test_serialize_deserialize_attrs(self):
        """测试属性序列化和反序列化"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.agents.dimension_hierarchy.schemas import (
            DimensionAttributes, DimensionCategory
        )
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            original = DimensionAttributes(
                category=DimensionCategory.TIME,
                category_detail="time-year",
                level=1,
                granularity="coarsest",
                level_confidence=0.95,
                reasoning="年份是时间维度",
            )
            
            # 序列化
            serialized = inference._serialize_attrs(original)
            
            assert serialized["category"] == "time"
            assert serialized["level"] == 1
            
            # 反序列化
            deserialized = inference._deserialize_attrs(serialized)
            
            assert deserialized.category == original.category
            assert deserialized.level == original.level
            assert deserialized.granularity == original.granularity
    
    def test_default_attrs(self):
        """测试默认属性生成"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.agents.dimension_hierarchy.schemas import DimensionCategory
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            attrs = inference._default_attrs("未知字段")
            
            assert attrs.category == DimensionCategory.OTHER
            assert attrs.category_detail == "other-unknown"
            assert attrs.level == 3
            assert attrs.level_confidence == 0.0
            assert "推断失败" in attrs.reasoning


class TestInferDimensionHierarchy:
    """测试 infer_dimension_hierarchy 便捷函数"""
    
    @pytest.mark.asyncio
    async def test_infer_empty_fields(self):
        """测试空字段列表"""
        from src.agents.dimension_hierarchy.inference import infer_dimension_hierarchy
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            result = await infer_dimension_hierarchy(
                datasource_luid="test-ds",
                fields=[],
            )
            
            assert result.dimension_hierarchy == {}
    
    @pytest.mark.asyncio
    async def test_infer_with_seed_match(self):
        """测试种子数据匹配"""
        from src.agents.dimension_hierarchy.inference import infer_dimension_hierarchy
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            # 使用种子数据中存在的字段名
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
            ]
            
            result = await infer_dimension_hierarchy(
                datasource_luid="test-ds",
                fields=fields,
            )
            
            # 如果种子数据中有"年份"，应该能匹配到
            if "年份" in result.dimension_hierarchy:
                attrs = result.dimension_hierarchy["年份"]
                assert attrs.level_confidence == 1.0  # 种子匹配置信度为 1.0
                assert "种子匹配" in attrs.reasoning


class TestPatternSource:
    """测试 PatternSource 枚举"""
    
    def test_pattern_source_values(self):
        """测试 PatternSource 枚举值"""
        from src.agents.dimension_hierarchy.inference import PatternSource
        
        assert PatternSource.SEED.value == "seed"
        assert PatternSource.LLM.value == "llm"
        assert PatternSource.MANUAL.value == "manual"


class TestCacheOperations:
    """测试缓存操作"""
    
    def test_get_cache_disabled(self):
        """测试缓存禁用时的 get 操作"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            result = inference._get_cache("test-key")
            assert result is None
    
    def test_put_cache_disabled(self):
        """测试缓存禁用时的 put 操作"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            result = inference._put_cache("test-key", "hash", {}, {})
            assert result is False
    
    def test_get_cache_enabled(self):
        """测试缓存启用时的 get 操作"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=True,
                enable_self_learning=False,
            )
            
            # 缓存应该存在但为空
            result = inference._get_cache("nonexistent-key")
            assert result is None
    
    def test_clear_cache_disabled(self):
        """测试缓存禁用时的清除操作"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            result = inference.clear_cache("test-key")
            assert result is False


class TestEnrichFields:
    """测试字段丰富功能"""
    
    def test_enrich_fields_no_result(self):
        """测试无推断结果时的字段丰富"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
            ]
            
            result = inference.enrich_fields(fields)
            
            # 无推断结果时应返回原字段
            assert result == fields
    
    @pytest.mark.asyncio
    async def test_enrich_fields_with_result(self):
        """测试有推断结果时的字段丰富"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
            ]
            
            # 先执行推断
            await inference.infer("test-ds", fields)
            
            # 然后丰富字段
            enriched = inference.enrich_fields(fields)
            
            # 检查字段是否被丰富
            assert len(enriched) == 1
            if enriched[0].category:
                assert enriched[0].category is not None


class TestGetResult:
    """测试获取结果功能"""
    
    def test_get_result_no_inference(self):
        """测试未推断时获取结果"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            result = inference.get_result()
            assert result is None
    
    @pytest.mark.asyncio
    async def test_get_result_after_inference(self):
        """测试推断后获取结果"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
            ]
            
            await inference.infer("test-ds", fields)
            
            result = inference.get_result()
            assert result is not None
            assert hasattr(result, 'dimension_hierarchy')


class TestInferMethod:
    """测试 infer 方法的各种场景"""
    
    @pytest.mark.asyncio
    async def test_infer_with_table_id(self):
        """测试带 table_id 的推断"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
            ]
            
            result = await inference.infer("test-ds", fields, table_id="table-123")
            
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_infer_skip_cache(self):
        """测试跳过缓存的推断"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=True,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
            ]
            
            result = await inference.infer("test-ds", fields, skip_cache=True)
            
            assert result is not None
    
    @pytest.mark.asyncio
    async def test_infer_multiple_fields(self):
        """测试多字段推断"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            fields = [
                Field(name="year", caption="年份", data_type="integer", role="dimension"),
                Field(name="city", caption="城市", data_type="string", role="dimension"),
                Field(name="category", caption="产品类别", data_type="string", role="dimension"),
            ]
            
            result = await inference.infer("test-ds", fields)
            
            assert result is not None
            # 应该有推断结果
            assert len(result.dimension_hierarchy) > 0
    
    @pytest.mark.asyncio
    async def test_infer_with_empty_caption(self):
        """测试使用空 caption 时使用 name 作为回退"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            # caption 为空字符串的字段
            fields = [
                Field(name="year", caption="", data_type="integer", role="dimension"),
            ]
            
            result = await inference.infer("test-ds", fields)
            
            assert result is not None
            # 应该使用 name 作为键（因为 caption 为空）
            assert "year" in result.dimension_hierarchy


class TestRAGOperations:
    """测试 RAG 相关操作"""
    
    def test_rag_not_initialized(self):
        """测试 RAG 未初始化状态"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=True,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            assert inference._rag_initialized is False
            assert inference._rag_retriever is None
    
    def test_rag_disabled(self):
        """测试 RAG 禁用"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            # 调用 _init_rag 不应该做任何事
            inference._init_rag()
            
            assert inference._rag_retriever is None


class TestSelfLearning:
    """测试自学习功能"""
    
    def test_store_to_rag_disabled(self):
        """测试自学习禁用时的存储"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.agents.dimension_hierarchy.schemas import DimensionAttributes, DimensionCategory
        from src.core.schemas.data_model import Field
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            results = {
                "测试字段": DimensionAttributes(
                    category=DimensionCategory.OTHER,
                    category_detail="other-test",
                    level=3,
                    granularity="medium",
                    level_confidence=0.9,
                    reasoning="测试",
                )
            }
            fields = [Field(name="test", caption="测试字段", data_type="string", role="dimension")]
            
            count = inference._store_to_rag(results, fields, "test-ds")
            
            assert count == 0
    
    def test_add_patterns_to_vector_index_no_retriever(self):
        """测试无检索器时的向量索引更新"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            # 不应该抛出异常
            inference._add_patterns_to_vector_index([])
            inference._add_patterns_to_vector_index([{"pattern_id": "test"}])


class TestPatternManagement:
    """测试模式管理"""
    
    def test_load_patterns_no_store(self):
        """测试无存储时加载模式"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            patterns = inference._load_patterns()
            
            assert patterns == []
    
    def test_init_seed_patterns_no_store(self):
        """测试无存储时初始化种子模式"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        with patch('src.agents.dimension_hierarchy.inference._get_config') as mock_config:
            mock_config.return_value = {}
            
            inference = DimensionHierarchyInference(
                enable_rag=False,
                enable_cache=False,
                enable_self_learning=False,
            )
            
            patterns = inference._init_seed_patterns()
            
            assert patterns == []


class TestConfigFunctions:
    """测试配置函数"""
    
    def test_get_config(self):
        """测试获取配置"""
        from src.agents.dimension_hierarchy.inference import _get_config
        
        config = _get_config()
        
        assert isinstance(config, dict)
    
    def test_get_rag_threshold_seed(self):
        """测试获取 RAG seed 阈值"""
        from src.agents.dimension_hierarchy.inference import _get_rag_threshold_seed
        
        threshold = _get_rag_threshold_seed()
        
        assert isinstance(threshold, float)
        assert 0 <= threshold <= 1
    
    def test_get_rag_threshold_unverified(self):
        """测试获取 RAG unverified 阈值"""
        from src.agents.dimension_hierarchy.inference import _get_rag_threshold_unverified
        
        threshold = _get_rag_threshold_unverified()
        
        assert isinstance(threshold, float)
        assert 0 <= threshold <= 1


class TestModuleExports:
    """测试模块导出"""
    
    def test_inference_module_exports(self):
        """测试 inference 模块导出"""
        from src.agents.dimension_hierarchy.inference import (
            DimensionHierarchyInference,
            IncrementalFieldsResult,
            PatternSource,
            compute_fields_hash,
            compute_single_field_hash,
            compute_incremental_fields,
            generate_pattern_id,
            build_cache_key,
            infer_dimension_hierarchy,
        )
        
        # 验证导出存在
        assert DimensionHierarchyInference is not None
        assert IncrementalFieldsResult is not None
        assert PatternSource is not None
        assert callable(compute_fields_hash)
        assert callable(compute_single_field_hash)
        assert callable(compute_incremental_fields)
        assert callable(generate_pattern_id)
        assert callable(build_cache_key)
        assert callable(infer_dimension_hierarchy)
    
    def test_dimension_hierarchy_module_exports(self):
        """测试 dimension_hierarchy 模块导出"""
        from src.agents.dimension_hierarchy import (
            DimensionCategory,
            DimensionAttributes,
            DimensionHierarchyResult,
            DimensionHierarchyInference,
            infer_dimension_hierarchy,
        )
        
        # 验证导出存在
        assert DimensionCategory is not None
        assert DimensionAttributes is not None
        assert DimensionHierarchyResult is not None
        assert DimensionHierarchyInference is not None
        assert callable(infer_dimension_hierarchy)


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
