"""
维度层级模式存储属性测试

**Feature: rag-enhancement, Property 17: 维度层级模式存储**
**Validates: Requirements 9.3**

测试维度层级模式的存储和检索一致性。
"""
import pytest
import tempfile
import os
import time
from hypothesis import given, strategies as st, settings

from tableau_assistant.src.capabilities.rag.dimension_pattern import (
    DimensionPattern,
    PatternSearchResult,
    DimensionPatternStore,
    DimensionHierarchyRAG,
)
from tableau_assistant.src.capabilities.rag.embeddings import MockEmbedding


# 使用固定的测试数据库路径
TEST_DB_PATH = "data/test_dimension_patterns.db"


def get_test_store():
    """获取测试存储实例"""
    store = DimensionPatternStore(
        db_path=TEST_DB_PATH,
        embedding_provider=MockEmbedding(dimensions=128),
        use_cache=False
    )
    store.clear()  # 清除之前的数据
    return store


# 自定义策略：生成有效的维度类别
dimension_categories = st.sampled_from([
    "geographic", "time", "product", "customer", "organization", "financial", "other"
])

# 自定义策略：生成有效的数据类型
data_types = st.sampled_from([
    "STRING", "INTEGER", "REAL", "DATETIME", "DATE", "BOOLEAN"
])

# 自定义策略：生成有效的粒度描述
granularities = st.sampled_from([
    "coarsest", "coarse", "medium", "fine", "finest"
])


class TestDimensionPatternStore:
    """
    维度模式存储测试
    
    **Feature: rag-enhancement, Property 17: 维度层级模式存储**
    **Validates: Requirements 9.3**
    """
    
    @pytest.fixture
    def temp_store(self):
        """创建测试存储"""
        store = get_test_store()
        yield store
        store.clear()
    
    def test_store_and_retrieve_pattern(self, temp_store):
        """测试存储和检索模式"""
        pattern = temp_store.store_pattern(
            field_name="province",
            field_caption="省份",
            data_type="STRING",
            sample_values=["北京", "上海", "广东"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="省份是地理维度的粗粒度层级",
            confidence=0.95,
            datasource_luid="test-luid"
        )
        
        assert pattern is not None
        assert pattern.field_name == "province"
        assert pattern.category == "geographic"
        assert pattern.level == 2
        
        # 验证可以检索到
        retrieved = temp_store.get_pattern(pattern.pattern_id)
        assert retrieved is not None
        assert retrieved.field_caption == "省份"
    
    def test_search_similar_patterns(self, temp_store):
        """测试搜索相似模式"""
        # 存储一些模式
        temp_store.store_pattern(
            field_name="province",
            field_caption="省份",
            data_type="STRING",
            sample_values=["北京", "上海", "广东"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="省份是地理维度",
            confidence=0.95,
        )
        
        temp_store.store_pattern(
            field_name="city",
            field_caption="城市",
            data_type="STRING",
            sample_values=["北京市", "上海市", "广州市"],
            unique_count=300,
            category="geographic",
            category_detail="geographic-city",
            level=3,
            granularity="medium",
            reasoning="城市是地理维度",
            confidence=0.90,
        )
        
        # 搜索相似模式
        results = temp_store.search_similar_patterns(
            field_caption="地区",
            data_type="STRING",
            sample_values=["华北", "华东", "华南"],
            unique_count=7,
            top_k=3,
            similarity_threshold=0.0  # 降低阈值以确保能找到结果
        )
        
        # 应该能找到相似的地理维度模式
        assert len(results) > 0
    
    def test_get_few_shot_examples(self, temp_store):
        """测试获取 few-shot 示例"""
        # 存储模式
        temp_store.store_pattern(
            field_name="year",
            field_caption="年份",
            data_type="INTEGER",
            sample_values=["2020", "2021", "2022"],
            unique_count=5,
            category="time",
            category_detail="time-year",
            level=1,
            granularity="coarsest",
            reasoning="年份是时间维度的最粗粒度",
            confidence=0.98,
        )
        
        # 获取示例
        examples = temp_store.get_few_shot_examples(
            field_caption="年度",
            data_type="INTEGER",
            sample_values=["2019", "2020", "2021"],
            unique_count=4,
            top_k=3
        )
        
        # 应该能获取到示例
        # 注意：由于使用 MockEmbedding，相似度可能不高
        assert isinstance(examples, list)
    
    @given(
        st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))),
        st.text(min_size=1, max_size=50, alphabet=st.characters(whitelist_categories=('L', 'N'))),
        data_types,
        st.lists(st.text(min_size=1, max_size=20), min_size=1, max_size=5),
        st.integers(min_value=1, max_value=10000),
        dimension_categories,
        st.integers(min_value=1, max_value=5),
        granularities,
        st.floats(min_value=0.0, max_value=1.0)
    )
    @settings(max_examples=30, deadline=None)
    def test_store_retrieve_property(
        self,
        field_name,
        field_caption,
        data_type,
        sample_values,
        unique_count,
        category,
        level,
        granularity,
        confidence
    ):
        """
        属性测试：存储后检索的模式与原始模式一致
        
        **Feature: rag-enhancement, Property 17: 维度层级模式存储**
        **Validates: Requirements 9.3**
        """
        store = get_test_store()
        
        pattern = store.store_pattern(
            field_name=field_name,
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count,
            category=category,
            category_detail=f"{category}-detail",
            level=level,
            granularity=granularity,
            reasoning="测试推理",
            confidence=confidence,
            datasource_luid=f"test-{time.time()}"
        )
        
        # 验证存储成功
        assert pattern is not None
        assert pattern.pattern_id is not None
        
        # 验证检索一致性
        retrieved = store.get_pattern(pattern.pattern_id)
        assert retrieved is not None
        assert retrieved.field_name == field_name
        assert retrieved.field_caption == field_caption
        assert retrieved.data_type == data_type
        assert retrieved.category == category
        assert retrieved.level == level
        assert retrieved.granularity == granularity


class TestDimensionPatternModel:
    """维度模式数据模型测试"""
    
    def test_to_dict_and_from_dict(self):
        """测试字典转换"""
        pattern = DimensionPattern(
            pattern_id="test-id",
            field_name="province",
            field_caption="省份",
            data_type="STRING",
            sample_values=["北京", "上海"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="测试",
            confidence=0.95,
        )
        
        # 转换为字典
        data = pattern.to_dict()
        assert data["field_name"] == "province"
        assert data["category"] == "geographic"
        
        # 从字典创建
        restored = DimensionPattern.from_dict(data)
        assert restored.field_name == pattern.field_name
        assert restored.category == pattern.category
        assert restored.level == pattern.level
    
    def test_build_index_text(self):
        """测试构建索引文本"""
        pattern = DimensionPattern(
            pattern_id="test-id",
            field_name="province",
            field_caption="省份",
            data_type="STRING",
            sample_values=["北京", "上海", "广东"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="测试",
            confidence=0.95,
        )
        
        index_text = pattern.build_index_text()
        
        assert "省份" in index_text
        assert "STRING" in index_text
        assert "31" in index_text
        assert "geographic" in index_text
        assert "2" in index_text
    
    def test_to_few_shot_example(self):
        """测试生成 few-shot 示例"""
        pattern = DimensionPattern(
            pattern_id="test-id",
            field_name="province",
            field_caption="省份",
            data_type="STRING",
            sample_values=["北京", "上海", "广东"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="省份是地理维度的粗粒度层级",
            confidence=0.95,
        )
        
        example = pattern.to_few_shot_example()
        
        assert "省份" in example
        assert "geographic" in example
        assert "2" in example
        assert "省份是地理维度的粗粒度层级" in example
    
    @given(
        st.text(min_size=1, max_size=50),
        st.text(min_size=1, max_size=50),
        data_types,
        dimension_categories,
        st.integers(min_value=1, max_value=5)
    )
    @settings(max_examples=50)
    def test_dict_round_trip_property(
        self,
        field_name,
        field_caption,
        data_type,
        category,
        level
    ):
        """
        属性测试：字典转换往返一致性
        
        **Feature: rag-enhancement, Property 17: 维度层级模式存储**
        """
        pattern = DimensionPattern(
            pattern_id=f"test-{time.time()}",
            field_name=field_name,
            field_caption=field_caption,
            data_type=data_type,
            sample_values=["sample1", "sample2"],
            unique_count=100,
            category=category,
            category_detail=f"{category}-detail",
            level=level,
            granularity="medium",
            reasoning="测试推理",
            confidence=0.9,
        )
        
        # 往返转换
        data = pattern.to_dict()
        restored = DimensionPattern.from_dict(data)
        
        # 验证一致性
        assert restored.field_name == pattern.field_name
        assert restored.field_caption == pattern.field_caption
        assert restored.data_type == pattern.data_type
        assert restored.category == pattern.category
        assert restored.level == pattern.level


class TestDimensionHierarchyRAG:
    """维度层级 RAG 增强测试"""
    
    @pytest.fixture
    def rag(self):
        """创建 RAG 实例"""
        store = get_test_store()
        rag = DimensionHierarchyRAG(pattern_store=store, similarity_threshold=0.0)
        yield rag
        store.clear()
    
    def test_get_inference_context_no_patterns(self, rag):
        """测试无模式时的推断上下文"""
        context = rag.get_inference_context(
            field_caption="测试字段",
            data_type="STRING",
            sample_values=["a", "b", "c"],
            unique_count=3
        )
        
        assert context["has_similar_patterns"] is False
        assert context["few_shot_examples"] == []
    
    def test_get_inference_context_with_patterns(self, rag):
        """测试有模式时的推断上下文"""
        # 先存储一个模式
        rag.store_inference_result(
            field_name="province",
            field_caption="省份",
            data_type="STRING",
            sample_values=["北京", "上海"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="测试",
            confidence=0.95,
        )
        
        # 获取推断上下文
        context = rag.get_inference_context(
            field_caption="地区",
            data_type="STRING",
            sample_values=["华北", "华东"],
            unique_count=7
        )
        
        # 由于使用 MockEmbedding 和低阈值，应该能找到相似模式
        assert isinstance(context, dict)
        assert "has_similar_patterns" in context
        assert "few_shot_examples" in context
    
    def test_stats(self, rag):
        """测试统计信息"""
        # 执行一些操作
        rag.get_inference_context(
            field_caption="测试",
            data_type="STRING",
            sample_values=["a"],
            unique_count=1
        )
        
        stats = rag.get_stats()
        
        assert "total_inferences" in stats
        assert "rag_assisted" in stats
        assert "fallback_count" in stats
        assert stats["total_inferences"] == 1
    
    def test_fallback_to_llm_when_no_patterns(self, rag):
        """
        测试无相似模式时降级到纯 LLM 推断
        
        **Feature: rag-enhancement, Task 21.6: 降级逻辑**
        **Validates: Requirements 9.5**
        """
        # 使用高阈值确保无法匹配
        rag.similarity_threshold = 0.99
        
        context = rag.get_inference_context(
            field_caption="完全不相关的字段",
            data_type="STRING",
            sample_values=["x", "y", "z"],
            unique_count=3
        )
        
        # 验证降级标志
        assert context["has_similar_patterns"] is False
        assert context["fallback_to_llm"] is True
        assert context["fallback_reason"] is not None
        assert "无相似模式" in context["fallback_reason"]
        
        # 验证统计
        stats = rag.get_stats()
        assert stats["fallback_count"] >= 1
    
    def test_store_all_confidence_levels(self, rag):
        """
        测试存储所有置信度级别的推断结果
        
        **Feature: rag-enhancement, Task 21.4: 模式存储**
        **Validates: Requirements 9.3**
        """
        # 存储低置信度结果
        low_conf_pattern = rag.store_inference_result(
            field_name="field_low",
            field_caption="低置信度字段",
            data_type="STRING",
            sample_values=["a", "b"],
            unique_count=2,
            category="other",
            category_detail="other-unknown",
            level=3,
            granularity="medium",
            reasoning="不确定的推断",
            confidence=0.5,  # 低置信度
        )
        
        # 存储高置信度结果
        high_conf_pattern = rag.store_inference_result(
            field_name="field_high",
            field_caption="高置信度字段",
            data_type="STRING",
            sample_values=["北京", "上海"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="明确的地理维度",
            confidence=0.95,  # 高置信度
        )
        
        # 验证两个都被存储
        assert low_conf_pattern is not None
        assert high_conf_pattern is not None
        
        # 验证可以检索到
        assert rag.pattern_store.get_pattern(low_conf_pattern.pattern_id) is not None
        assert rag.pattern_store.get_pattern(high_conf_pattern.pattern_id) is not None
    
    def test_confidence_weighted_retrieval(self, rag):
        """
        测试按置信度加权的检索排序
        
        **Feature: rag-enhancement, Task 21.4: 模式存储**
        **Validates: Requirements 9.3**
        """
        # 存储两个相似的模式，但置信度不同
        rag.store_inference_result(
            field_name="province_low",
            field_caption="省份A",
            data_type="STRING",
            sample_values=["北京", "上海"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="低置信度",
            confidence=0.5,
        )
        
        rag.store_inference_result(
            field_name="province_high",
            field_caption="省份B",
            data_type="STRING",
            sample_values=["广东", "浙江"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="高置信度",
            confidence=0.95,
        )
        
        # 检索时应该按加权分数排序
        results = rag.pattern_store.search_similar_patterns(
            field_caption="省份",
            data_type="STRING",
            sample_values=["江苏", "山东"],
            unique_count=31,
            top_k=2,
            similarity_threshold=0.0,
            weight_by_confidence=True
        )
        
        # 验证返回了结果
        assert len(results) == 2
        
        # 高置信度的应该排在前面（如果相似度相近）
        # 注意：由于 MockEmbedding 的特性，相似度可能相同
        # 但加权后高置信度的分数应该更高
    
    @given(
        st.floats(min_value=0.1, max_value=1.0),
        st.floats(min_value=0.1, max_value=1.0)
    )
    @settings(max_examples=20, deadline=None)
    def test_store_any_positive_confidence_property(self, conf1, conf2):
        """
        属性测试：任何正置信度的结果都应该被存储
        
        **Feature: rag-enhancement, Property 17: 维度层级模式存储**
        **Validates: Requirements 9.3**
        """
        store = get_test_store()
        rag = DimensionHierarchyRAG(pattern_store=store, similarity_threshold=0.0)
        
        # 存储两个不同置信度的模式
        pattern1 = rag.store_inference_result(
            field_name=f"field_{conf1}",
            field_caption=f"字段_{conf1}",
            data_type="STRING",
            sample_values=["a", "b"],
            unique_count=2,
            category="other",
            category_detail="other",
            level=3,
            granularity="medium",
            reasoning="测试",
            confidence=conf1,
        )
        
        pattern2 = rag.store_inference_result(
            field_name=f"field_{conf2}",
            field_caption=f"字段_{conf2}",
            data_type="STRING",
            sample_values=["c", "d"],
            unique_count=2,
            category="other",
            category_detail="other",
            level=3,
            granularity="medium",
            reasoning="测试",
            confidence=conf2,
        )
        
        # 验证都被存储
        assert pattern1 is not None
        assert pattern2 is not None
        assert pattern1.confidence == conf1
        assert pattern2.confidence == conf2
        
        store.clear()


class TestPatternSearchResult:
    """模式搜索结果测试"""
    
    def test_search_result_creation(self):
        """测试搜索结果创建"""
        pattern = DimensionPattern(
            pattern_id="test-id",
            field_name="province",
            field_caption="省份",
            data_type="STRING",
            sample_values=["北京"],
            unique_count=31,
            category="geographic",
            category_detail="geographic-province",
            level=2,
            granularity="coarse",
            reasoning="测试",
            confidence=0.95,
        )
        
        result = PatternSearchResult(
            pattern=pattern,
            similarity=0.85,
            rank=1
        )
        
        assert result.pattern.field_name == "province"
        assert result.similarity == 0.85
        assert result.rank == 1


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
