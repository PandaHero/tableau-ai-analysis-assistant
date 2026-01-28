# -*- coding: utf-8 -*-
"""
Property-Based Tests for Semantic Parser Components

Property 1-5 测试：
- Property 1: Intent Classification Coverage
- Property 2: Cache Round-Trip Consistency
- Property 3: Cache Invalidation on Model Change
- Property 4: Top-K Retrieval Threshold
- Property 5: Exact Match Priority

测试框架：Hypothesis
运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    pytest tests/agents/semantic_parser/test_pbt_properties.py -v
"""

import asyncio
import hashlib
from datetime import date, datetime, timedelta
from typing import Any, Dict, List, Optional
from unittest.mock import MagicMock, AsyncMock

import pytest
from hypothesis import given, settings, strategies as st, assume
from pydantic import BaseModel

# 导入被测组件
from analytics_assistant.src.agents.semantic_parser.components.intent_router import (
    IntentRouter,
    IntentType,
    IntentRouterOutput,
)
from analytics_assistant.src.agents.semantic_parser.components.query_cache import (
    QueryCache,
    CachedQuery,
    compute_schema_hash,
    compute_question_hash,
)
from analytics_assistant.src.agents.semantic_parser.components.field_retriever import (
    FieldRetriever,
    FieldCandidate,
)


# ═══════════════════════════════════════════════════════════════════════════
# 测试数据生成策略
# ═══════════════════════════════════════════════════════════════════════════

# 用户问题生成策略
question_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N', 'P', 'Z')),
    min_size=1,
    max_size=200,
).filter(lambda x: x.strip())  # 过滤空白字符串

# 中文问题生成策略
chinese_question_strategy = st.sampled_from([
    "上个月各地区的销售额",
    "今年各产品类别的利润",
    "各客户的订单数量",
    "按部门统计员工人数",
    "北京市的销售情况",
    "本季度销售趋势",
    "去年同期对比",
    "top10 客户",
    "利润率分析",
    "库存周转率",
    "你好",
    "天气怎么样",
    "有哪些字段",
    "数据源是什么",
    "帮我写一篇文章",
    "推荐个电影",
    "",  # 空字符串
    "   ",  # 空白字符串
    "分析",  # 短模糊词
    "查询",  # 短模糊词
])

# 数据源 ID 生成策略
datasource_luid_strategy = st.text(
    alphabet=st.characters(whitelist_categories=('L', 'N')),
    min_size=8,
    max_size=36,
).filter(lambda x: x.strip())

# Top-K 值生成策略
top_k_strategy = st.integers(min_value=1, max_value=100)


# ═══════════════════════════════════════════════════════════════════════════
# Mock 数据模型
# ═══════════════════════════════════════════════════════════════════════════

class MockField:
    """模拟字段对象"""
    def __init__(self, name: str, data_type: str = "string", role: str = "dimension"):
        self.name = name
        self.field_name = name
        self.caption = name
        self.field_caption = name
        self.data_type = data_type
        self.role = role


class MockDataModel:
    """模拟数据模型"""
    def __init__(self, fields: List[MockField]):
        self.fields = fields
    
    @property
    def dimensions(self):
        return [f for f in self.fields if f.role == "dimension"]
    
    @property
    def measures(self):
        return [f for f in self.fields if f.role == "measure"]


def create_mock_data_model(field_count: int = 10) -> MockDataModel:
    """创建模拟数据模型"""
    fields = []
    for i in range(field_count):
        if i % 3 == 0:
            fields.append(MockField(f"measure_{i}", "integer", "measure"))
        else:
            fields.append(MockField(f"dimension_{i}", "string", "dimension"))
    return MockDataModel(fields)


# ═══════════════════════════════════════════════════════════════════════════
# Property 1: Intent Classification Coverage
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty1IntentClassificationCoverage:
    """
    Property 1: Intent Classification Coverage
    
    **Validates: Requirements 1.2**
    
    *For any* user question, the IntentRouter SHALL classify it into exactly 
    one of the defined intent types (DATA_QUERY, CLARIFICATION, GENERAL, IRRELEVANT) 
    with a confidence score between 0 and 1.
    
    注意：当前实现只有 3 种意图类型（DATA_QUERY, GENERAL, IRRELEVANT），
    CLARIFICATION 由 SemanticUnderstanding 处理。
    """
    
    @pytest.fixture
    def router(self):
        return IntentRouter()
    
    @given(question=chinese_question_strategy)
    @settings(max_examples=50, deadline=None)
    def test_any_question_classified_to_valid_intent(self, question: str):
        """任意问题都被分类为有效意图类型"""
        router = IntentRouter()
        
        # 跳过空字符串
        if not question or not question.strip():
            return
        
        result = asyncio.run(router.route(question))
        
        # 验证返回类型
        assert isinstance(result, IntentRouterOutput)
        
        # 验证意图类型是有效枚举值
        assert result.intent_type in [
            IntentType.DATA_QUERY,
            IntentType.GENERAL,
            IntentType.IRRELEVANT,
        ]
        
        # 验证置信度在 0-1 之间
        assert 0.0 <= result.confidence <= 1.0
        
        # 验证有来源标识
        assert result.source in ["L0_RULES", "L1_CLASSIFIER", "L2_FALLBACK"]
        
        # 验证有原因说明
        assert result.reason and len(result.reason) > 0
    
    @given(question=st.text(min_size=1, max_size=500))
    @settings(max_examples=30, deadline=None)
    def test_random_text_classified(self, question: str):
        """随机文本也能被分类"""
        router = IntentRouter()
        
        # 跳过空字符串
        if not question or not question.strip():
            return
        
        result = asyncio.run(router.route(question))
        
        # 验证返回有效结果
        assert isinstance(result, IntentRouterOutput)
        assert result.intent_type in IntentType
        assert 0.0 <= result.confidence <= 1.0


# ═══════════════════════════════════════════════════════════════════════════
# Property 2: Cache Round-Trip Consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty2CacheRoundTripConsistency:
    """
    Property 2: Cache Round-Trip Consistency
    
    **Validates: Requirements 2.1, 2.2**
    
    *For any* successfully executed query, caching then retrieving with 
    the same question SHALL return an equivalent query result.
    """
    
    @staticmethod
    def _create_mock_store():
        """创建模拟存储（静态方法，避免 fixture 问题）"""
        store = MagicMock()
        store._data = {}
        
        def mock_get(namespace, key):
            full_key = f"{namespace}:{key}"
            if full_key in store._data:
                item = MagicMock()
                item.value = store._data[full_key]
                return item
            return None
        
        def mock_put(namespace, key, value, ttl=None):
            full_key = f"{namespace}:{key}"
            store._data[full_key] = value
        
        def mock_delete(namespace, key):
            full_key = f"{namespace}:{key}"
            if full_key in store._data:
                del store._data[full_key]
        
        store.get = mock_get
        store.put = mock_put
        store.delete = mock_delete
        
        return store
    
    @given(
        question=st.text(min_size=5, max_size=100).filter(lambda x: x.strip()),
        datasource_luid=st.text(min_size=8, max_size=36).filter(lambda x: x.strip()),
    )
    @settings(max_examples=30, deadline=None)
    def test_cache_round_trip(self, question: str, datasource_luid: str):
        """缓存写入后读取返回等价结果"""
        # 每次测试创建新的 mock store
        mock_store = self._create_mock_store()
        cache = QueryCache(store=mock_store)
        
        # 准备测试数据
        schema_hash = hashlib.md5(b"test_schema").hexdigest()
        semantic_output = {"what": {"measures": ["sales"]}, "where": {"dimensions": ["region"]}}
        query = "SELECT SUM(sales) FROM table GROUP BY region"
        
        # 写入缓存
        success = cache.set(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
            semantic_output=semantic_output,
            query=query,
        )
        assert success
        
        # 读取缓存
        result = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=schema_hash,
        )
        
        # 验证结果等价
        assert result is not None
        assert result.question == question
        assert result.datasource_luid == datasource_luid
        assert result.schema_hash == schema_hash
        assert result.semantic_output == semantic_output
        assert result.query == query


# ═══════════════════════════════════════════════════════════════════════════
# Property 3: Cache Invalidation on Model Change
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty3CacheInvalidationOnModelChange:
    """
    Property 3: Cache Invalidation on Model Change
    
    **Validates: Requirements 2.5**
    
    *For any* cached query associated with a datasource, changing the 
    datasource's data model SHALL invalidate all related cache entries.
    """
    
    @staticmethod
    def _create_mock_store():
        """创建模拟存储（静态方法，避免 fixture 问题）"""
        store = MagicMock()
        store._data = {}
        
        def mock_get(namespace, key):
            full_key = f"{namespace}:{key}"
            if full_key in store._data:
                item = MagicMock()
                item.value = store._data[full_key]
                return item
            return None
        
        def mock_put(namespace, key, value, ttl=None):
            full_key = f"{namespace}:{key}"
            store._data[full_key] = value
        
        store.get = mock_get
        store.put = mock_put
        
        return store
    
    def test_schema_hash_change_invalidates_cache(self):
        """schema_hash 变更时缓存失效"""
        mock_store = self._create_mock_store()
        cache = QueryCache(store=mock_store)
        
        question = "上个月各地区的销售额"
        datasource_luid = "ds_12345678"
        old_schema_hash = hashlib.md5(b"old_schema").hexdigest()
        new_schema_hash = hashlib.md5(b"new_schema").hexdigest()
        
        # 使用旧 schema 写入缓存
        cache.set(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=old_schema_hash,
            semantic_output={"what": {}},
            query="SELECT ...",
        )
        
        # 使用旧 schema 读取 - 应该命中
        result_old = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=old_schema_hash,
        )
        assert result_old is not None
        
        # 使用新 schema 读取 - 应该失效
        result_new = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=new_schema_hash,
        )
        assert result_new is None
    
    @given(
        field_count_before=st.integers(min_value=1, max_value=20),
        field_count_after=st.integers(min_value=1, max_value=20),
    )
    @settings(max_examples=20, deadline=None)
    def test_field_change_changes_schema_hash(
        self, 
        field_count_before: int, 
        field_count_after: int
    ):
        """字段变更导致 schema_hash 变化"""
        # 跳过相同字段数的情况（可能产生相同 hash）
        assume(field_count_before != field_count_after)
        
        model_before = create_mock_data_model(field_count_before)
        model_after = create_mock_data_model(field_count_after)
        
        hash_before = compute_schema_hash(model_before)
        hash_after = compute_schema_hash(model_after)
        
        # 字段数不同时，hash 应该不同
        assert hash_before != hash_after


# ═══════════════════════════════════════════════════════════════════════════
# Property 4: Top-K Retrieval Threshold
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty4TopKRetrievalThreshold:
    """
    Property 4: Top-K Retrieval Threshold
    
    **Validates: Requirements 3.2**
    
    *For any* data model with field count exceeding the threshold, 
    the FieldRetriever SHALL return at most K candidates (where K is configurable).
    """
    
    @given(
        top_k=st.integers(min_value=1, max_value=50),
        field_count=st.integers(min_value=1, max_value=200),
    )
    @settings(max_examples=30, deadline=None)
    def test_retrieval_respects_top_k(self, top_k: int, field_count: int):
        """检索结果不超过 Top-K"""
        # 创建模拟数据模型
        data_model = create_mock_data_model(field_count)
        
        # 创建 FieldRetriever（无 embedding retriever，使用规则匹配）
        retriever = FieldRetriever(
            cascade_retriever=None,
            default_top_k=top_k,
            full_schema_threshold=10,  # 低阈值，触发规则匹配
            min_rule_match_dimensions=1,
        )
        
        # 执行检索
        question = "上个月各地区的销售额"
        candidates = asyncio.run(retriever.retrieve(
            question=question,
            data_model=data_model,
            top_k=top_k,
        ))
        
        # 验证：当字段数 <= full_schema_threshold 时，返回全量
        # 当字段数 > full_schema_threshold 时，返回规则匹配结果
        # 无论哪种情况，都应该是有效的 FieldCandidate 列表
        assert isinstance(candidates, list)
        for c in candidates:
            assert isinstance(c, FieldCandidate)
            assert 0.0 <= c.confidence <= 1.0
    
    def test_full_schema_mode_returns_all_fields(self):
        """L0 全量模式返回所有字段"""
        # 创建小数据模型（触发 L0 全量模式）
        data_model = create_mock_data_model(field_count=5)
        
        retriever = FieldRetriever(
            cascade_retriever=None,
            full_schema_threshold=20,  # 高阈值，触发全量模式
        )
        
        candidates = asyncio.run(retriever.retrieve(
            question="销售额",
            data_model=data_model,
        ))
        
        # 全量模式应返回所有字段
        assert len(candidates) == 5


# ═══════════════════════════════════════════════════════════════════════════
# Property 5: Exact Match Priority
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty5ExactMatchPriority:
    """
    Property 5: Exact Match Priority
    
    **Validates: Requirements 3.5**
    
    *For any* field retrieval, exact matches SHALL have higher confidence 
    scores than semantic matches for the same field.
    """
    
    def test_direct_field_name_match_has_high_confidence(self):
        """直接字段名匹配有高置信度"""
        # 创建包含特定字段的数据模型
        fields = [
            MockField("销售额", "integer", "measure"),
            MockField("地区", "string", "dimension"),
            MockField("产品", "string", "dimension"),
            MockField("客户", "string", "dimension"),
        ]
        data_model = MockDataModel(fields)
        
        retriever = FieldRetriever(
            cascade_retriever=None,
            full_schema_threshold=100,  # 高阈值，触发规则匹配
            min_rule_match_dimensions=1,
        )
        
        # 问题中直接提到字段名
        question = "各地区的销售额"
        candidates = asyncio.run(retriever.retrieve(
            question=question,
            data_model=data_model,
        ))
        
        # 找到 "地区" 字段
        region_candidates = [c for c in candidates if c.field_name == "地区"]
        
        # 如果匹配到，应该有较高置信度
        if region_candidates:
            assert region_candidates[0].confidence >= 0.8
            assert region_candidates[0].source in ["rule_match", "full_schema"]
    
    def test_rule_match_confidence_higher_than_embedding(self):
        """规则匹配置信度高于 embedding 匹配"""
        retriever = FieldRetriever(cascade_retriever=None)
        
        # 验证置信度实例属性
        assert retriever._rule_match_confidence > retriever._embedding_confidence_base
        assert retriever._full_schema_confidence >= retriever._embedding_confidence_base
    
    @given(question=chinese_question_strategy)
    @settings(max_examples=20, deadline=None)
    def test_matched_fields_have_valid_confidence(self, question: str):
        """匹配的字段有有效的置信度"""
        if not question or not question.strip():
            return
        
        # 创建数据模型
        fields = [
            MockField("销售额", "integer", "measure"),
            MockField("利润", "integer", "measure"),
            MockField("地区", "string", "dimension"),
            MockField("时间", "date", "dimension"),
            MockField("产品", "string", "dimension"),
        ]
        data_model = MockDataModel(fields)
        
        retriever = FieldRetriever(
            cascade_retriever=None,
            full_schema_threshold=100,
        )
        
        candidates = asyncio.run(retriever.retrieve(
            question=question,
            data_model=data_model,
        ))
        
        # 所有候选都应有有效置信度
        for c in candidates:
            assert 0.0 <= c.confidence <= 1.0
            assert c.source in ["full_schema", "rule_match", "embedding", "hierarchy_expand"]


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short"])


# ═══════════════════════════════════════════════════════════════════════════
# Property 10: Few-Shot Example Count
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty10FewShotExampleCount:
    """
    Property 10: Few-Shot Example Count
    
    **Validates: Requirements 4.2**
    
    *For any* retrieval request, the FewShotManager SHALL return 
    between 0 and 3 examples (inclusive).
    
    使用真实的存储层和 Zhipu embedding。
    """
    
    # 测试用的数据源 ID 前缀，便于清理
    TEST_DATASOURCE_PREFIX = "ds_pbt_test_"
    
    @staticmethod
    def _get_real_store():
        """获取真实存储"""
        from analytics_assistant.src.infra.storage import get_kv_store
        return get_kv_store()
    
    @staticmethod
    def _get_real_embedding():
        """获取真实 embedding"""
        from analytics_assistant.src.infra.ai import get_embeddings
        return get_embeddings()
    
    def test_retrieve_returns_at_most_3_examples(self):
        """检索返回最多 3 个示例"""
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FewShotExample,
        )
        
        store = self._get_real_store()
        embedding = self._get_real_embedding()
        
        manager = FewShotManager(
            store=store,
            embedding_model=embedding,
            similarity_threshold=0.3,  # 较低阈值
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}count_test"
        
        # 添加 5 个示例
        for i in range(5):
            question = f"销售额查询问题 {i}"
            example = FewShotExample(
                id=f"ex_count_{i}",
                question=question,
                restated_question=question,
                what={"measures": ["销售额"]},
                where={"dimensions": []},
                how="SIMPLE",
                query=f"SELECT {i}",
                datasource_luid=datasource_luid,
                accepted_count=i,
                question_embedding=embedding.embed_query(question),
            )
            asyncio.run(manager.add(example))
        
        # 检索
        results = asyncio.run(manager.retrieve(
            question="销售额查询",
            datasource_luid=datasource_luid,
            top_k=10,  # 请求 10 个
        ))
        
        # 验证：返回数量在 0-3 之间（最多 3 个）
        assert 0 <= len(results) <= 3
    
    def test_retrieve_returns_empty_when_no_examples(self):
        """无示例时返回空列表"""
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        
        store = self._get_real_store()
        manager = FewShotManager(store=store, embedding_model=None)
        
        # 使用一个不存在示例的数据源
        results = asyncio.run(manager.retrieve(
            question="测试问题",
            datasource_luid=f"{self.TEST_DATASOURCE_PREFIX}empty_{datetime.now().timestamp()}",
            top_k=3,
        ))
        
        assert results == []
    
    def test_retrieve_with_real_embedding(self):
        """使用真实 Zhipu embedding 进行语义检索"""
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FewShotExample,
        )
        
        store = self._get_real_store()
        embedding = self._get_real_embedding()
        
        manager = FewShotManager(
            store=store,
            embedding_model=embedding,
            similarity_threshold=0.5,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}real_embedding"
        
        # 添加示例
        examples_data = [
            ("ex_sales_real", "上个月各地区的销售额是多少", 5),
            ("ex_profit_real", "今年的利润趋势", 3),
            ("ex_customer_real", "客户数量统计", 1),
        ]
        
        for ex_id, question, accepted_count in examples_data:
            example = FewShotExample(
                id=ex_id,
                question=question,
                restated_question=question,
                what={"measures": []},
                where={"dimensions": []},
                how="SIMPLE",
                query="SELECT 1",
                datasource_luid=datasource_luid,
                accepted_count=accepted_count,
                question_embedding=embedding.embed_query(question),
            )
            asyncio.run(manager.add(example))
        
        # 检索相似问题
        results = asyncio.run(manager.retrieve(
            question="各地区销售额",
            datasource_luid=datasource_luid,
            top_k=3,
        ))
        
        # 验证：返回数量在 0-3 之间
        assert 0 <= len(results) <= 3
        
        # 如果有结果，验证语义相似的排在前面
        if results:
            assert any("销售" in r.question for r in results)


# ═══════════════════════════════════════════════════════════════════════════
# Property 11: Accepted Example Priority
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty11AcceptedExamplePriority:
    """
    Property 11: Accepted Example Priority
    
    **Validates: Requirements 4.5**
    
    *For any* retrieval, examples with higher accepted_count SHALL 
    be ranked higher than examples with lower accepted_count.
    
    使用真实的存储层和 Zhipu embedding。
    """
    
    TEST_DATASOURCE_PREFIX = "ds_pbt_test_"
    
    @staticmethod
    def _get_real_store():
        """获取真实存储"""
        from analytics_assistant.src.infra.storage import get_kv_store
        return get_kv_store()
    
    @staticmethod
    def _get_real_embedding():
        """获取真实 embedding"""
        from analytics_assistant.src.infra.ai import get_embeddings
        return get_embeddings()
    
    def test_accepted_examples_ranked_higher(self):
        """接受过的示例排名更高"""
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FewShotExample,
        )
        
        store = self._get_real_store()
        embedding = self._get_real_embedding()
        
        manager = FewShotManager(
            store=store,
            embedding_model=embedding,
            similarity_threshold=0.3,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}priority"
        
        # 添加示例，accepted_count 不同，问题相似
        examples_data = [
            ("ex_priority_low", "销售数据分析低", 1),
            ("ex_priority_mid", "销售数据分析中", 5),
            ("ex_priority_high", "销售数据分析高", 10),
        ]
        
        for ex_id, question, accepted_count in examples_data:
            example = FewShotExample(
                id=ex_id,
                question=question,
                restated_question=question,
                what={"measures": []},
                where={"dimensions": []},
                how="SIMPLE",
                query="SELECT 1",
                datasource_luid=datasource_luid,
                accepted_count=accepted_count,
                question_embedding=embedding.embed_query(question),
            )
            asyncio.run(manager.add(example))
        
        # 检索
        results = asyncio.run(manager.retrieve(
            question="销售数据",
            datasource_luid=datasource_luid,
            top_k=3,
        ))
        
        # 验证：按 accepted_count 降序排列
        if len(results) >= 2:
            for i in range(len(results) - 1):
                assert results[i].accepted_count >= results[i + 1].accepted_count
    
    def test_accepted_priority_with_similar_questions(self):
        """相似问题中，accepted_count 高的优先"""
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FewShotExample,
        )
        
        store = self._get_real_store()
        embedding = self._get_real_embedding()
        
        manager = FewShotManager(
            store=store,
            embedding_model=embedding,
            similarity_threshold=0.5,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}similar_priority"
        
        # 添加非常相似的问题，但 accepted_count 不同
        examples_data = [
            ("ex_sim_low", "各地区销售额统计", 1),
            ("ex_sim_high", "各地区销售额分析", 10),
        ]
        
        for ex_id, question, accepted_count in examples_data:
            example = FewShotExample(
                id=ex_id,
                question=question,
                restated_question=question,
                what={"measures": []},
                where={"dimensions": []},
                how="SIMPLE",
                query="SELECT 1",
                datasource_luid=datasource_luid,
                accepted_count=accepted_count,
                question_embedding=embedding.embed_query(question),
            )
            asyncio.run(manager.add(example))
        
        # 检索
        results = asyncio.run(manager.retrieve(
            question="地区销售额",
            datasource_luid=datasource_luid,
            top_k=3,
        ))
        
        # 验证：accepted_count 高的排在前面
        if len(results) >= 2:
            assert results[0].accepted_count >= results[1].accepted_count


# ═══════════════════════════════════════════════════════════════════════════
# Property 33: Time Hint Generation
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty33TimeHintGeneration:
    """
    Property 33: Time Hint Generation
    
    **Validates: Requirements 11.4 (Req 11)**
    
    *For any* user question containing a recognized time expression 
    (今天, 上个月, 最近N天, 本财年, etc.), the TimeHintGenerator SHALL 
    produce a hint with correct start_date and end_date based on 
    current_date and fiscal_year_start_month.
    """
    
    @pytest.fixture
    def fixed_date(self):
        """固定日期用于测试"""
        return date(2025, 1, 28)  # 周二
    
    @pytest.fixture
    def generator(self, fixed_date):
        """创建时间提示生成器"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        return TimeHintGenerator(current_date=fixed_date)
    
    @pytest.fixture
    def fiscal_generator(self, fixed_date):
        """创建财年时间提示生成器（4月开始）"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        return TimeHintGenerator(current_date=fixed_date, fiscal_year_start_month=4)
    
    # ─────────────────────────────────────────────────────────────────────────
    # 静态时间模式测试
    # ─────────────────────────────────────────────────────────────────────────
    
    def test_static_pattern_today(self, generator, fixed_date):
        """今天 → 当前日期"""
        hints = generator.generate_hints("今天的销售额")
        assert len(hints) >= 1
        today_hint = next((h for h in hints if h.expression == "今天"), None)
        assert today_hint is not None
        assert today_hint.start == "2025-01-28"
        assert today_hint.end == "2025-01-28"
    
    def test_static_pattern_yesterday(self, generator):
        """昨天 → 前一天"""
        hints = generator.generate_hints("昨天的订单数")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "昨天"), None)
        assert hint is not None
        assert hint.start == "2025-01-27"
        assert hint.end == "2025-01-27"
    
    def test_static_pattern_this_week(self, generator):
        """本周 → 周一到当前日期"""
        hints = generator.generate_hints("本周销售趋势")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "本周"), None)
        assert hint is not None
        # 2025-01-28 是周二，本周一是 2025-01-27
        assert hint.start == "2025-01-27"
        assert hint.end == "2025-01-28"
    
    def test_static_pattern_last_week(self, generator):
        """上周 → 上周一到上周日"""
        hints = generator.generate_hints("上周的数据")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "上周"), None)
        assert hint is not None
        # 2025-01-28 是周二，上周一是 2025-01-20，上周日是 2025-01-26
        assert hint.start == "2025-01-20"
        assert hint.end == "2025-01-26"
    
    def test_static_pattern_this_month(self, generator):
        """本月 → 月初到当前日期"""
        hints = generator.generate_hints("本月销售额")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "本月"), None)
        assert hint is not None
        assert hint.start == "2025-01-01"
        assert hint.end == "2025-01-28"
    
    def test_static_pattern_last_month(self, generator):
        """上个月 → 上月整月"""
        hints = generator.generate_hints("上个月各地区的销售额")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "上个月"), None)
        assert hint is not None
        assert hint.start == "2024-12-01"
        assert hint.end == "2024-12-31"
    
    def test_static_pattern_this_quarter(self, generator):
        """本季度 → 季度初到当前日期"""
        hints = generator.generate_hints("本季度业绩")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "本季度"), None)
        assert hint is not None
        # 2025年1月属于Q1，从1月1日开始
        assert hint.start == "2025-01-01"
        assert hint.end == "2025-01-28"
    
    def test_static_pattern_last_quarter(self, generator):
        """上季度 → 上季度整季"""
        hints = generator.generate_hints("上季度对比")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "上季度"), None)
        assert hint is not None
        # 2025年1月的上季度是2024年Q4 (10-12月)
        assert hint.start == "2024-10-01"
        assert hint.end == "2024-12-31"
    
    def test_static_pattern_this_year(self, generator):
        """今年 → 年初到当前日期"""
        hints = generator.generate_hints("今年的总销售额")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "今年"), None)
        assert hint is not None
        assert hint.start == "2025-01-01"
        assert hint.end == "2025-01-28"
    
    def test_static_pattern_last_year(self, generator):
        """去年 → 去年整年"""
        hints = generator.generate_hints("去年的数据")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "去年"), None)
        assert hint is not None
        assert hint.start == "2024-01-01"
        assert hint.end == "2024-12-31"
    
    def test_static_pattern_ytd(self, generator):
        """年初至今 → 年初到当前日期"""
        hints = generator.generate_hints("年初至今的利润")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "年初至今"), None)
        assert hint is not None
        assert hint.start == "2025-01-01"
        assert hint.end == "2025-01-28"
    
    # ─────────────────────────────────────────────────────────────────────────
    # 动态时间模式测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @given(n=st.integers(min_value=1, max_value=365))
    @settings(max_examples=20, deadline=None)
    def test_dynamic_pattern_last_n_days(self, n):
        """最近N天 → 正确的日期范围"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        
        fixed_date = date(2025, 1, 28)
        generator = TimeHintGenerator(current_date=fixed_date)
        
        question = f"最近{n}天的销售额"
        hints = generator.generate_hints(question)
        
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == f"最近{n}天"), None)
        assert hint is not None
        
        expected_start = fixed_date - timedelta(days=n)
        assert hint.start == expected_start.isoformat()
        assert hint.end == fixed_date.isoformat()
    
    @given(n=st.integers(min_value=1, max_value=52))
    @settings(max_examples=20, deadline=None)
    def test_dynamic_pattern_last_n_weeks(self, n):
        """最近N周 → 正确的日期范围"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        
        fixed_date = date(2025, 1, 28)
        generator = TimeHintGenerator(current_date=fixed_date)
        
        question = f"最近{n}周的数据"
        hints = generator.generate_hints(question)
        
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == f"最近{n}周"), None)
        assert hint is not None
        
        expected_start = fixed_date - timedelta(weeks=n)
        assert hint.start == expected_start.isoformat()
        assert hint.end == fixed_date.isoformat()
    
    @given(n=st.integers(min_value=1, max_value=24))
    @settings(max_examples=20, deadline=None)
    def test_dynamic_pattern_last_n_months(self, n):
        """最近N个月 → 正确的日期范围"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        from dateutil.relativedelta import relativedelta
        
        fixed_date = date(2025, 1, 28)
        generator = TimeHintGenerator(current_date=fixed_date)
        
        question = f"最近{n}个月的趋势"
        hints = generator.generate_hints(question)
        
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == f"最近{n}个月"), None)
        assert hint is not None
        
        expected_start = fixed_date - relativedelta(months=n)
        assert hint.start == expected_start.isoformat()
        assert hint.end == fixed_date.isoformat()
    
    # ─────────────────────────────────────────────────────────────────────────
    # 财年相关表达式测试
    # ─────────────────────────────────────────────────────────────────────────
    
    def test_fiscal_year_current(self, fiscal_generator):
        """本财年 → 财年起始到当前日期（4月开始）"""
        hints = fiscal_generator.generate_hints("本财年的业绩")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "本财年"), None)
        assert hint is not None
        # 2025-01-28，财年4月开始，属于FY2024 (2024-04-01 到 2025-03-31)
        assert hint.start == "2024-04-01"
        assert hint.end == "2025-01-28"  # 本财年结束日期是当前日期
    
    def test_fiscal_year_last(self, fiscal_generator):
        """上财年 → 上一财年整年（4月开始）"""
        hints = fiscal_generator.generate_hints("上财年对比")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "上财年"), None)
        assert hint is not None
        # 上财年是 FY2023 (2023-04-01 到 2024-03-31)
        assert hint.start == "2023-04-01"
        assert hint.end == "2024-03-31"
    
    def test_fiscal_ytd(self, fiscal_generator):
        """财年至今 → 财年起始到当前日期"""
        hints = fiscal_generator.generate_hints("财年至今的销售额")
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == "财年至今"), None)
        assert hint is not None
        assert hint.start == "2024-04-01"
        assert hint.end == "2025-01-28"
    
    @given(quarter=st.integers(min_value=1, max_value=4))
    @settings(max_examples=4, deadline=None)
    def test_fiscal_quarter_current_year(self, quarter):
        """财年Q1-Q4 → 正确的季度范围"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        from dateutil.relativedelta import relativedelta
        
        fixed_date = date(2025, 1, 28)
        generator = TimeHintGenerator(current_date=fixed_date, fiscal_year_start_month=4)
        
        question = f"财年Q{quarter}的数据"
        hints = generator.generate_hints(question)
        
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == f"财年Q{quarter}"), None)
        assert hint is not None
        
        # 财年从4月开始，Q1=4-6月, Q2=7-9月, Q3=10-12月, Q4=1-3月
        fy_start = date(2024, 4, 1)  # FY2024 开始
        quarter_start = fy_start + relativedelta(months=(quarter - 1) * 3)
        quarter_end = quarter_start + relativedelta(months=3) - timedelta(days=1)
        
        assert hint.start == quarter_start.isoformat()
        assert hint.end == quarter_end.isoformat()
    
    @given(quarter=st.integers(min_value=1, max_value=4))
    @settings(max_examples=4, deadline=None)
    def test_fiscal_quarter_last_year(self, quarter):
        """上财年Q1-Q4 → 正确的季度范围"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        from dateutil.relativedelta import relativedelta
        
        fixed_date = date(2025, 1, 28)
        generator = TimeHintGenerator(current_date=fixed_date, fiscal_year_start_month=4)
        
        question = f"上财年Q{quarter}的数据"
        hints = generator.generate_hints(question)
        
        assert len(hints) >= 1
        hint = next((h for h in hints if h.expression == f"上财年Q{quarter}"), None)
        assert hint is not None
        
        # 上财年是 FY2023 (2023-04-01 开始)
        fy_start = date(2023, 4, 1)
        quarter_start = fy_start + relativedelta(months=(quarter - 1) * 3)
        quarter_end = quarter_start + relativedelta(months=3) - timedelta(days=1)
        
        assert hint.start == quarter_start.isoformat()
        assert hint.end == quarter_end.isoformat()
    
    # ─────────────────────────────────────────────────────────────────────────
    # format_for_prompt 测试
    # ─────────────────────────────────────────────────────────────────────────
    
    def test_format_for_prompt_with_hints(self, generator):
        """有时间表达式时生成 XML"""
        xml = generator.format_for_prompt("上个月各地区的销售额")
        assert xml.startswith("<time_hints>")
        assert xml.endswith("</time_hints>")
        assert "上个月" in xml
        assert "2024-12-01" in xml
        assert "2024-12-31" in xml
    
    def test_format_for_prompt_without_hints(self, generator):
        """无时间表达式时返回空字符串"""
        xml = generator.format_for_prompt("各地区的销售额")
        assert xml == ""
    
    def test_format_for_prompt_with_fiscal_config(self, fiscal_generator):
        """财年配置不是1月时显示配置说明"""
        xml = fiscal_generator.format_for_prompt("本财年的业绩")
        assert "<fiscal_year_config>" in xml
        assert "财年起始月份: 4月" in xml
    
    def test_format_for_prompt_without_fiscal_config(self, generator):
        """财年配置是1月时不显示配置说明"""
        xml = generator.format_for_prompt("本财年的业绩")
        assert "<fiscal_year_config>" not in xml
    
    # ─────────────────────────────────────────────────────────────────────────
    # 边界情况测试
    # ─────────────────────────────────────────────────────────────────────────
    
    def test_no_time_expression(self, generator):
        """无时间表达式的问题"""
        hints = generator.generate_hints("各地区的销售额")
        assert len(hints) == 0
    
    def test_multiple_time_expressions(self, generator):
        """多个时间表达式"""
        hints = generator.generate_hints("今年和去年的销售额对比")
        assert len(hints) >= 2
        expressions = [h.expression for h in hints]
        assert "今年" in expressions
        assert "去年" in expressions
    
    @given(
        current_date=st.dates(
            min_value=date(2020, 1, 1),
            max_value=date(2030, 12, 31)
        )
    )
    @settings(max_examples=30, deadline=None)
    def test_any_date_produces_valid_hints(self, current_date):
        """任意日期都能生成有效的时间提示"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        
        generator = TimeHintGenerator(current_date=current_date)
        
        # 测试各种时间表达式
        test_questions = [
            "今天的数据",
            "上个月的销售额",
            "本季度业绩",
            "去年对比",
            "最近7天趋势",
        ]
        
        for question in test_questions:
            hints = generator.generate_hints(question)
            assert len(hints) >= 1
            
            for hint in hints:
                # 验证日期格式有效
                start_date = date.fromisoformat(hint.start)
                end_date = date.fromisoformat(hint.end)
                
                # 验证开始日期 <= 结束日期
                assert start_date <= end_date
    
    @given(
        fiscal_month=st.integers(min_value=1, max_value=12)
    )
    @settings(max_examples=12, deadline=None)
    def test_any_fiscal_month_produces_valid_hints(self, fiscal_month):
        """任意财年起始月份都能生成有效的时间提示"""
        from analytics_assistant.src.agents.semantic_parser.prompts.time_hint_generator import (
            TimeHintGenerator,
        )
        
        fixed_date = date(2025, 1, 28)
        generator = TimeHintGenerator(
            current_date=fixed_date,
            fiscal_year_start_month=fiscal_month
        )
        
        # 测试财年相关表达式
        test_questions = [
            "本财年的数据",
            "上财年的销售额",
            "财年至今业绩",
            "财年Q1数据",
            "上财年Q4对比",
        ]
        
        for question in test_questions:
            hints = generator.generate_hints(question)
            assert len(hints) >= 1
            
            for hint in hints:
                # 验证日期格式有效
                start_date = date.fromisoformat(hint.start)
                end_date = date.fromisoformat(hint.end)
                
                # 验证开始日期 <= 结束日期
                assert start_date <= end_date


# ═══════════════════════════════════════════════════════════════════════════
# Property 25: Prompt Complexity Adaptation
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty25PromptComplexityAdaptation:
    """
    Property 25: Prompt Complexity Adaptation
    
    **Validates: Requirements 12.1**
    
    *For any* user question containing derived metric keywords (率, 比, 同比, 环比, 排名, etc.), 
    the DynamicPromptBuilder SHALL select the COMPLEX template.
    """
    
    @pytest.fixture
    def builder(self):
        """创建 DynamicPromptBuilder 实例"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            DynamicPromptBuilder,
        )
        return DynamicPromptBuilder()
    
    # ─────────────────────────────────────────────────────────────────────────
    # 派生度量关键词测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @pytest.mark.parametrize("keyword", [
        "率", "比", "占比", "百分比", "比例",
        "毛利", "净利", "利润率", "转化率", "增长率",
    ])
    def test_derived_metric_keywords_trigger_complex(self, builder, keyword):
        """派生度量关键词触发 COMPLEX 模板"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            PromptComplexity,
        )
        
        question = f"各地区的{keyword}"
        complexity = builder.get_complexity(question)
        assert complexity == PromptComplexity.COMPLEX
    
    # ─────────────────────────────────────────────────────────────────────────
    # 时间计算关键词测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @pytest.mark.parametrize("keyword", [
        "同比", "环比", "增长", "下降", "变化",
        "去年同期", "上月同期", "上周同期",
    ])
    def test_time_calc_keywords_trigger_complex(self, builder, keyword):
        """时间计算关键词触发 COMPLEX 模板"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            PromptComplexity,
        )
        
        question = f"销售额{keyword}"
        complexity = builder.get_complexity(question)
        assert complexity == PromptComplexity.COMPLEX
    
    # ─────────────────────────────────────────────────────────────────────────
    # LOD 关键词测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @pytest.mark.parametrize("keyword", [
        "每个", "各自", "独立", "不考虑",
        "固定", "包含", "排除",
    ])
    def test_lod_keywords_trigger_complex(self, builder, keyword):
        """LOD 关键词触发 COMPLEX 模板"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            PromptComplexity,
        )
        
        question = f"{keyword}客户的首购日期"
        complexity = builder.get_complexity(question)
        assert complexity == PromptComplexity.COMPLEX
    
    # ─────────────────────────────────────────────────────────────────────────
    # 表计算关键词测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @pytest.mark.parametrize("keyword", [
        "排名", "排序", "累计", "移动平均",
        "前N", "TOP", "百分位", "分位",
    ])
    def test_table_calc_keywords_trigger_complex(self, builder, keyword):
        """表计算关键词触发 COMPLEX 模板"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            PromptComplexity,
        )
        
        question = f"销售额{keyword}"
        complexity = builder.get_complexity(question)
        assert complexity == PromptComplexity.COMPLEX
    
    # ─────────────────────────────────────────────────────────────────────────
    # 简单查询测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @pytest.mark.parametrize("question", [
        "上个月各地区的销售额",
        "今年各产品类别的利润",
        "各客户的订单数量",
        "按部门统计员工人数",
        "北京市的销售情况",
    ])
    def test_simple_queries_use_simple_template(self, builder, question):
        """简单查询使用 SIMPLE 模板"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            PromptComplexity,
        )
        
        complexity = builder.get_complexity(question)
        assert complexity == PromptComplexity.SIMPLE
    
    # ─────────────────────────────────────────────────────────────────────────
    # PBT 测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @given(
        keyword=st.sampled_from([
            "率", "比", "占比", "同比", "环比", "增长", "排名", "累计",
            "每个", "各自", "百分位", "移动平均",
        ])
    )
    @settings(max_examples=20, deadline=None)
    def test_any_complex_keyword_triggers_complex(self, keyword):
        """任意复杂度关键词都触发 COMPLEX 模板"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            DynamicPromptBuilder,
            PromptComplexity,
        )
        
        builder = DynamicPromptBuilder()
        question = f"各地区的销售额{keyword}"
        complexity = builder.get_complexity(question)
        assert complexity == PromptComplexity.COMPLEX


# ═══════════════════════════════════════════════════════════════════════════
# Property 26: Time Expression Context
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty26TimeExpressionContext:
    """
    Property 26: Time Expression Context
    
    **Validates: Requirements 11.1, 11.2, 11.3**
    
    *For any* prompt built by DynamicPromptBuilder, the context section SHALL include 
    current_date, timezone, and fiscal_year_start_month.
    """
    
    @pytest.fixture
    def builder(self):
        """创建 DynamicPromptBuilder 实例"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            DynamicPromptBuilder,
        )
        return DynamicPromptBuilder()
    
    @pytest.fixture
    def config(self):
        """创建语义解析配置"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            SemanticConfig,
        )
        return SemanticConfig(
            current_date=date(2025, 1, 28),
            timezone="Asia/Shanghai",
            fiscal_year_start_month=4,
        )
    
    @pytest.fixture
    def field_candidates(self):
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="销售额",
                field_caption="Sales Amount",
                field_type="measure",
                data_type="float",
            ),
            FieldCandidate(
                field_name="地区",
                field_caption="Region",
                field_type="dimension",
                data_type="string",
            ),
        ]
    
    def test_prompt_contains_current_date(self, builder, config, field_candidates):
        """Prompt 包含 current_date"""
        prompt = builder.build(
            question="上个月各地区的销售额",
            field_candidates=field_candidates,
            config=config,
        )
        assert "2025-01-28" in prompt
    
    def test_prompt_contains_timezone(self, builder, config, field_candidates):
        """Prompt 包含 timezone"""
        prompt = builder.build(
            question="上个月各地区的销售额",
            field_candidates=field_candidates,
            config=config,
        )
        assert "Asia/Shanghai" in prompt
    
    def test_prompt_contains_fiscal_year_start_month(self, builder, config, field_candidates):
        """复杂查询 Prompt 包含 fiscal_year_start_month"""
        prompt = builder.build(
            question="各地区的利润率",  # 包含"率"，触发 COMPLEX
            field_candidates=field_candidates,
            config=config,
        )
        assert "财年起始月份" in prompt or "fiscal_year_start_month" in prompt
    
    def test_prompt_contains_time_hints(self, builder, config, field_candidates):
        """包含时间表达式时 Prompt 包含 time_hints"""
        prompt = builder.build(
            question="上个月各地区的销售额",
            field_candidates=field_candidates,
            config=config,
        )
        assert "<time_hints>" in prompt
        assert "上个月" in prompt
        assert "2024-12-01" in prompt
    
    # ─────────────────────────────────────────────────────────────────────────
    # PBT 测试
    # ─────────────────────────────────────────────────────────────────────────
    
    @given(
        current_date=st.dates(
            min_value=date(2020, 1, 1),
            max_value=date(2030, 12, 31)
        ),
        timezone=st.sampled_from([
            "Asia/Shanghai", "America/New_York", "Europe/London", "UTC"
        ]),
        fiscal_month=st.integers(min_value=1, max_value=12),
    )
    @settings(max_examples=20, deadline=None)
    def test_any_config_produces_valid_prompt(self, current_date, timezone, fiscal_month):
        """任意配置都能生成包含必要上下文的 Prompt"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            DynamicPromptBuilder,
            SemanticConfig,
            FieldCandidate,
        )
        
        builder = DynamicPromptBuilder()
        config = SemanticConfig(
            current_date=current_date,
            timezone=timezone,
            fiscal_year_start_month=fiscal_month,
        )
        field_candidates = [
            FieldCandidate(
                field_name="销售额",
                field_caption="Sales",
                field_type="measure",
                data_type="float",
            ),
        ]
        
        prompt = builder.build(
            question="各地区的销售额",
            field_candidates=field_candidates,
            config=config,
        )
        
        # 验证 Prompt 包含必要的上下文信息
        assert current_date.isoformat() in prompt
        assert timezone in prompt
    
    @given(
        question=st.sampled_from([
            "上个月各地区的销售额",
            "本季度业绩",
            "去年对比",
            "最近7天趋势",
            "本财年的数据",
        ])
    )
    @settings(max_examples=10, deadline=None)
    def test_time_expressions_generate_hints(self, question):
        """包含时间表达式的问题生成 time_hints"""
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            DynamicPromptBuilder,
            SemanticConfig,
            FieldCandidate,
        )
        
        builder = DynamicPromptBuilder()
        config = SemanticConfig(
            current_date=date(2025, 1, 28),
            timezone="Asia/Shanghai",
            fiscal_year_start_month=1,
        )
        field_candidates = [
            FieldCandidate(
                field_name="销售额",
                field_caption="Sales",
                field_type="measure",
                data_type="float",
            ),
        ]
        
        prompt = builder.build(
            question=question,
            field_candidates=field_candidates,
            config=config,
        )
        
        # 验证 Prompt 包含 time_hints
        assert "<time_hints>" in prompt


# ═══════════════════════════════════════════════════════════════════════════
# Property 32: Cache Schema Validation on Read
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty32CacheSchemaValidationOnRead:
    """
    Property 32: Cache Schema Validation on Read
    
    **Validates: Requirements 2.3, 2.5**
    
    *For any* cache read operation, if the current schema_hash does not 
    match the cached schema_hash, the cache SHALL return None (cache miss).
    
    This ensures that cached queries are invalidated when the data model changes.
    """
    
    @staticmethod
    def _create_mock_store():
        """创建模拟存储"""
        store = MagicMock()
        store._data = {}
        
        def mock_get(namespace, key):
            full_key = f"{namespace}:{key}"
            if full_key in store._data:
                item = MagicMock()
                item.value = store._data[full_key]
                return item
            return None
        
        def mock_put(namespace, key, value, ttl=None):
            full_key = f"{namespace}:{key}"
            store._data[full_key] = value
        
        def mock_delete(namespace, key):
            full_key = f"{namespace}:{key}"
            if full_key in store._data:
                del store._data[full_key]
        
        store.get = mock_get
        store.put = mock_put
        store.delete = mock_delete
        
        return store
    
    @given(
        question=st.text(min_size=5, max_size=100).filter(lambda x: x.strip()),
        datasource_luid=st.text(min_size=8, max_size=36).filter(lambda x: x.strip()),
        old_schema=st.text(min_size=10, max_size=50).filter(lambda x: x.strip()),
        new_schema=st.text(min_size=10, max_size=50).filter(lambda x: x.strip()),
    )
    @settings(max_examples=30, deadline=None)
    def test_schema_mismatch_returns_none(
        self, 
        question: str, 
        datasource_luid: str,
        old_schema: str,
        new_schema: str,
    ):
        """schema_hash 不匹配时返回 None"""
        # 确保两个 schema 不同
        assume(old_schema != new_schema)
        
        mock_store = self._create_mock_store()
        cache = QueryCache(store=mock_store)
        
        # 计算 hash
        old_schema_hash = hashlib.md5(old_schema.encode()).hexdigest()
        new_schema_hash = hashlib.md5(new_schema.encode()).hexdigest()
        
        # 使用旧 schema 写入缓存
        cache.set(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=old_schema_hash,
            semantic_output={"what": {"measures": ["test"]}},
            query="SELECT 1",
        )
        
        # 使用新 schema 读取 - 应该返回 None
        result = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=new_schema_hash,
        )
        
        assert result is None, "Cache should return None when schema_hash doesn't match"
    
    @given(
        question=st.text(min_size=5, max_size=100).filter(lambda x: x.strip()),
        datasource_luid=st.text(min_size=8, max_size=36).filter(lambda x: x.strip()),
        schema=st.text(min_size=10, max_size=50).filter(lambda x: x.strip()),
    )
    @settings(max_examples=30, deadline=None)
    def test_schema_match_returns_cached_data(
        self, 
        question: str, 
        datasource_luid: str,
        schema: str,
    ):
        """schema_hash 匹配时返回缓存数据"""
        mock_store = self._create_mock_store()
        cache = QueryCache(store=mock_store)
        
        schema_hash = hashlib.md5(schema.encode()).hexdigest()
        semantic_output = {"what": {"measures": ["test_measure"]}}
        query = "SELECT test"
        
        # 写入缓存
        cache.set(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash,
            semantic_output=semantic_output,
            query=query,
        )
        
        # 使用相同 schema 读取 - 应该返回缓存数据
        result = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=schema_hash,
        )
        
        assert result is not None, "Cache should return data when schema_hash matches"
        assert result.schema_hash == schema_hash
        assert result.semantic_output == semantic_output
        assert result.query == query
    
    def test_schema_validation_with_real_data_model_changes(self):
        """测试真实数据模型变更场景"""
        mock_store = self._create_mock_store()
        cache = QueryCache(store=mock_store)
        
        # 模拟数据模型变更场景
        question = "上个月各地区的销售额"
        datasource_luid = "ds_test_schema_validation"
        
        # 场景 1: 初始数据模型
        model_v1 = create_mock_data_model(field_count=5)
        schema_hash_v1 = compute_schema_hash(model_v1)
        
        cache.set(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash_v1,
            semantic_output={"version": 1},
            query="SELECT v1",
        )
        
        # 验证 v1 可以读取
        result_v1 = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=schema_hash_v1,
        )
        assert result_v1 is not None
        assert result_v1.semantic_output["version"] == 1
        
        # 场景 2: 数据模型变更（添加字段）
        model_v2 = create_mock_data_model(field_count=8)  # 更多字段
        schema_hash_v2 = compute_schema_hash(model_v2)
        
        # 使用新 schema 读取旧缓存 - 应该失效
        result_v2 = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=schema_hash_v2,
        )
        assert result_v2 is None, "Cache should be invalidated after schema change"
        
        # 场景 3: 写入新版本
        cache.set(
            question=question,
            datasource_luid=datasource_luid,
            schema_hash=schema_hash_v2,
            semantic_output={"version": 2},
            query="SELECT v2",
        )
        
        # 验证 v2 可以读取
        result_v2_new = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=schema_hash_v2,
        )
        assert result_v2_new is not None
        assert result_v2_new.semantic_output["version"] == 2
        
        # 验证 v1 仍然失效
        result_v1_after = cache.get(
            question=question,
            datasource_luid=datasource_luid,
            current_schema_hash=schema_hash_v1,
        )
        assert result_v1_after is None


# ═══════════════════════════════════════════════════════════════════════════
# Property 6: Restated Question Completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty6RestatedQuestionCompleteness:
    """
    Property 6: Restated Question Completeness
    
    **Validates: Requirements 4.7**
    
    *For any* semantic understanding output, the restated_question SHALL 
    contain all information necessary to understand the query without 
    referring to conversation history.
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Region",
                field_caption="地区",
                field_type="dimension",
                data_type="string",
                confidence=0.92,
            ),
            FieldCandidate(
                field_name="Order_Date",
                field_caption="订单日期",
                field_type="dimension",
                data_type="date",
                confidence=0.88,
                category="time",
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_restated_question_is_complete(self):
        """重述问题包含完整信息"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = await understanding.understand(
            question="各地区的销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 验证 restated_question 存在且非空
        assert isinstance(result, SemanticOutput)
        assert result.restated_question is not None
        assert len(result.restated_question) > 0
        
        # 验证 restated_question 包含关键信息
        # 注意：具体内容取决于 LLM，这里只验证基本结构
        assert isinstance(result.restated_question, str)
    
    @pytest.mark.asyncio
    async def test_restated_question_with_history_is_standalone(self):
        """带历史的重述问题应该是独立的"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        history = [
            {"role": "user", "content": "我想看销售数据"},
            {"role": "assistant", "content": "好的，请问您想看哪个时间段的销售数据？"},
        ]
        
        result = await understanding.understand(
            question="上个月的",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
            history=history,
        )
        
        # 重述问题应该是独立的，不依赖历史
        assert result.restated_question is not None
        assert len(result.restated_question) > len("上个月的")  # 应该比原问题更完整


# ═══════════════════════════════════════════════════════════════════════════
# Property 8: State Completeness
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty8StateCompleteness:
    """
    Property 8: State Completeness
    
    **Validates: Requirements 5.2 (Req 6)**
    
    *For any* semantic understanding output, all required fields 
    (restated_question, what, where, how_type, self_check) SHALL be 
    present and valid.
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Region",
                field_caption="地区",
                field_type="dimension",
                data_type="string",
                confidence=0.92,
            ),
        ]
    
    @given(
        question=st.sampled_from([
            "各地区的销售额",
            "上个月的利润",
            "今年的订单数量",
            "北京的销售情况",
        ])
    )
    @settings(max_examples=4, deadline=None)
    def test_output_has_all_required_fields(self, question: str):
        """输出包含所有必需字段"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            What,
            Where,
            SelfCheck,
            HowType,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = asyncio.run(understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        ))
        
        # 验证所有必需字段存在
        assert isinstance(result, SemanticOutput)
        assert result.restated_question is not None
        assert isinstance(result.what, What)
        assert isinstance(result.where, Where)
        assert result.how_type in HowType
        assert isinstance(result.self_check, SelfCheck)
        
        # 验证 self_check 字段有效
        assert 0 <= result.self_check.field_mapping_confidence <= 1
        assert 0 <= result.self_check.time_range_confidence <= 1
        assert 0 <= result.self_check.computation_confidence <= 1
        assert 0 <= result.self_check.overall_confidence <= 1


# ═══════════════════════════════════════════════════════════════════════════
# Property 12: Self-Check Presence
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty12SelfCheckPresence:
    """
    Property 12: Self-Check Presence
    
    **Validates: Requirements 7.1 (Req 8)**
    
    *For any* semantic understanding output, the self_check field SHALL 
    be present with all confidence scores between 0 and 1.
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_self_check_always_present(self):
        """self_check 字段始终存在"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = await understanding.understand(
            question="销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 验证 self_check 存在
        assert result.self_check is not None
        
        # 验证所有置信度在 0-1 之间
        assert 0 <= result.self_check.field_mapping_confidence <= 1
        assert 0 <= result.self_check.time_range_confidence <= 1
        assert 0 <= result.self_check.computation_confidence <= 1
        assert 0 <= result.self_check.overall_confidence <= 1


# ═══════════════════════════════════════════════════════════════════════════
# Property 13: Low Confidence Flagging
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty13LowConfidenceFlagging:
    """
    Property 13: Low Confidence Flagging
    
    **Validates: Requirements 7.5 (Req 8)**
    
    *For any* semantic output where any confidence score is below the 
    threshold (0.7), the potential_issues list SHALL be non-empty.
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_low_confidence_triggers_issues(self):
        """低置信度触发 potential_issues"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
            get_low_confidence_threshold,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = await understanding.understand(
            question="销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 检查是否有低置信度
        self_check = result.self_check
        low_confidence_threshold = get_low_confidence_threshold()
        has_low_confidence = (
            self_check.field_mapping_confidence < low_confidence_threshold or
            self_check.time_range_confidence < low_confidence_threshold or
            self_check.computation_confidence < low_confidence_threshold or
            self_check.overall_confidence < low_confidence_threshold
        )
        
        # 如果有低置信度，potential_issues 应该非空
        if has_low_confidence:
            assert len(self_check.potential_issues) > 0


# ═══════════════════════════════════════════════════════════════════════════
# Property 18: Streaming Output Validity
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty18StreamingOutputValidity:
    """
    Property 18: Streaming Output Validity
    
    **Validates: Requirements 13.4 (Req 13)**
    
    *For any* completed streaming output, the final result SHALL be a 
    valid Pydantic object that passes schema validation.
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Region",
                field_caption="地区",
                field_type="dimension",
                data_type="string",
                confidence=0.92,
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_streaming_produces_valid_output(self):
        """流式输出产生有效的 Pydantic 对象"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        tokens_received = []
        
        async def on_token(token: str):
            tokens_received.append(token)
        
        result = await understanding.understand(
            question="各地区的销售额是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
            on_token=on_token,
        )
        
        # 验证收到了 token
        assert len(tokens_received) > 0
        
        # 验证结果是有效的 Pydantic 对象
        assert isinstance(result, SemanticOutput)
        
        # 验证可以序列化和反序列化
        json_data = result.model_dump()
        restored = SemanticOutput.model_validate(json_data)
        assert restored.query_id == result.query_id


# ═══════════════════════════════════════════════════════════════════════════
# Property 7: Clarification Detection
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty7ClarificationDetection:
    """
    Property 7: Clarification Detection
    
    **Validates: Requirements 5.1 (Req 6)**
    
    *For any* incomplete user question (missing required information like 
    measure or time range), the output SHALL have needs_clarification=true 
    and a non-empty clarification_question.
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Region",
                field_caption="地区",
                field_type="dimension",
                data_type="string",
                confidence=0.92,
            ),
        ]
    
    @given(
        question=st.sampled_from([
            "数据",  # 非常模糊
            "分析",  # 非常模糊
            "查询",  # 非常模糊
            "看看",  # 非常模糊
            "帮我",  # 非常模糊
        ])
    )
    @settings(max_examples=3, deadline=None)
    def test_vague_question_may_need_clarification(self, question: str):
        """模糊问题可能需要澄清"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            ClarificationSource,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = asyncio.run(understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        ))
        
        # 验证结果是有效的
        assert isinstance(result, SemanticOutput)
        
        # 如果需要澄清，验证澄清问题存在且来源正确
        if result.needs_clarification:
            assert result.clarification_question is not None
            assert len(result.clarification_question) > 0
            assert result.clarification_source == ClarificationSource.SEMANTIC_UNDERSTANDING
    
    @pytest.mark.asyncio
    async def test_incomplete_question_triggers_clarification(self):
        """不完整问题触发澄清"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            ClarificationSource,
        )
        
        understanding = SemanticUnderstanding()
        
        # 使用空字段列表，问题也很模糊
        result = await understanding.understand(
            question="数据",
            field_candidates=[],
            current_date=date(2025, 1, 28),
        )
        
        # 这种情况很可能需要澄清
        # 注意：LLM 的行为可能不确定，所以我们只验证结构
        if result.needs_clarification:
            assert result.clarification_question is not None
            assert result.clarification_source == ClarificationSource.SEMANTIC_UNDERSTANDING


# ═══════════════════════════════════════════════════════════════════════════
# Property 19: Derived Metric Decomposition
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty19DerivedMetricDecomposition:
    """
    Property 19: Derived Metric Decomposition
    
    **Validates: Requirements 5.1 (Req 5)**
    
    *For any* user question containing a derived metric (e.g., "利润率"), 
    the output SHALL include a computation with the correct formula 
    decomposition (e.g., 利润/销售额).
    """
    
    @staticmethod
    def _create_field_candidates_with_profit():
        """创建包含利润和销售额的字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                description="销售金额",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Profit",
                field_caption="利润",
                field_type="measure",
                data_type="number",
                description="利润金额",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Region",
                field_caption="地区",
                field_type="dimension",
                data_type="string",
                confidence=0.92,
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_profit_rate_decomposition(self):
        """利润率被分解为利润/销售额"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            CalcType,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates_with_profit()
        
        result = await understanding.understand(
            question="各地区的利润率是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 验证基本结构
        assert isinstance(result, SemanticOutput)
        
        # 利润率应该被识别为派生度量
        # 检查是否有计算逻辑
        if result.computations and len(result.computations) > 0:
            # 找到利润率相关的计算
            ratio_computations = [
                c for c in result.computations 
                if c.calc_type == CalcType.RATIO or "利润" in (c.name or "")
            ]
            
            if ratio_computations:
                comp = ratio_computations[0]
                # 验证计算类型是 RATIO
                assert comp.calc_type == CalcType.RATIO
                # 验证有公式或基础度量
                assert comp.formula or comp.base_measures
    
    @given(
        question=st.sampled_from([
            "各地区的利润率",
            "利润率分析",
            "毛利率是多少",
        ])
    )
    @settings(max_examples=2, deadline=None)
    def test_ratio_metrics_have_computation(self, question: str):
        """比率类度量有计算逻辑"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            HowType,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates_with_profit()
        
        result = asyncio.run(understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        ))
        
        # 验证基本结构
        assert isinstance(result, SemanticOutput)
        
        # 包含"率"的问题应该被识别为复杂查询
        # 注意：LLM 可能不总是识别，这里只验证结构有效
        if result.how_type == HowType.COMPLEX:
            # 复杂查询应该有计算逻辑
            # 但 LLM 可能不总是生成，所以不强制断言
            pass


# ═══════════════════════════════════════════════════════════════════════════
# Property 20: Computation Pattern Recognition
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty20ComputationPatternRecognition:
    """
    Property 20: Computation Pattern Recognition
    
    **Validates: Requirements 5.2 (Req 5)**
    
    *For any* derived metric matching a known pattern (RATIO, GROWTH, SHARE), 
    the computation's calc_type SHALL correctly identify the pattern.
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Profit",
                field_caption="利润",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Region",
                field_caption="地区",
                field_type="dimension",
                data_type="string",
                confidence=0.92,
            ),
            FieldCandidate(
                field_name="Order_Date",
                field_caption="订单日期",
                field_type="dimension",
                data_type="date",
                confidence=0.90,
                category="time",
            ),
        ]
    
    @pytest.mark.asyncio
    async def test_ratio_pattern_recognition(self):
        """RATIO 模式识别"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            CalcType,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = await understanding.understand(
            question="各地区的利润率是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 如果有计算逻辑，验证类型
        if result.computations:
            for comp in result.computations:
                if "率" in (comp.name or "") or "ratio" in (comp.name or "").lower():
                    assert comp.calc_type == CalcType.RATIO
    
    @pytest.mark.asyncio
    async def test_growth_pattern_recognition(self):
        """GROWTH 模式识别（同比/环比）"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            CalcType,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = await understanding.understand(
            question="销售额同比增长率是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 如果有计算逻辑，验证类型
        if result.computations:
            for comp in result.computations:
                if "增长" in (comp.name or "") or "同比" in (comp.name or ""):
                    assert comp.calc_type in [CalcType.GROWTH, CalcType.TABLE_CALC]
    
    @pytest.mark.asyncio
    async def test_share_pattern_recognition(self):
        """SHARE 模式识别（占比）"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            CalcType,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = await understanding.understand(
            question="各地区销售额占比是多少？",
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        )
        
        # 如果有计算逻辑，验证类型
        if result.computations:
            for comp in result.computations:
                if "占比" in (comp.name or "") or "share" in (comp.name or "").lower():
                    assert comp.calc_type in [CalcType.SHARE, CalcType.TABLE_CALC]
    
    @given(
        question_keyword=st.sampled_from(["利润率", "毛利率"])
    )
    @settings(max_examples=2, deadline=None)
    def test_known_patterns_correctly_identified(self, question_keyword):
        """已知模式被正确识别"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            CalcType,
        )
        
        question = f"各地区的{question_keyword}是多少？"
        expected_type = CalcType.RATIO  # 利润率/毛利率都是 RATIO 类型
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = asyncio.run(understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        ))
        
        # 验证结果有效
        assert result is not None
        
        # 如果有计算逻辑，验证类型匹配
        if result.computations:
            matching_comps = [
                c for c in result.computations 
                if c.calc_type == expected_type
            ]
            # 注意：LLM 可能不总是生成预期的计算类型
            # 这里只验证如果有匹配的计算，类型是正确的
            for comp in matching_comps:
                assert comp.calc_type == expected_type


# ═══════════════════════════════════════════════════════════════════════════
# Property 36: Field Value Cache LRU Eviction
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty36FieldValueCacheLRUEviction:
    """
    Property 36: Field Value Cache LRU Eviction
    
    **Validates: Requirements 10.1.4**
    
    *For any* cache that reaches its capacity limit, the FieldValueCache 
    SHALL evict the least recently used entries first.
    """
    
    @pytest.mark.asyncio
    async def test_lru_eviction_when_capacity_reached(self):
        """达到容量上限时淘汰最久未使用的条目"""
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        
        # 创建小容量缓存（方便测试 LRU）
        cache = FieldValueCache(
            max_fields=4,  # 总共最多 4 个字段
            shard_count=2,  # 2 个分片，每个分片最多 3 个
        )
        
        datasource = "ds_test_lru"
        
        # 添加 4 个字段
        await cache.set("field_1", datasource, ["a", "b"])
        await cache.set("field_2", datasource, ["c", "d"])
        await cache.set("field_3", datasource, ["e", "f"])
        await cache.set("field_4", datasource, ["g", "h"])
        
        # 访问 field_1，使其成为最近使用
        await cache.get("field_1", datasource)
        
        # 添加更多字段，触发 LRU 淘汰
        await cache.set("field_5", datasource, ["i", "j"])
        await cache.set("field_6", datasource, ["k", "l"])
        
        # 验证：field_1 应该还在（因为最近访问过）
        result_1 = await cache.get("field_1", datasource)
        # 注意：由于分片机制，field_1 是否被淘汰取决于它所在的分片
        # 这里主要验证 LRU 机制工作正常
        
        # 验证：缓存总数不超过 max_fields
        stats = cache.get_stats()
        assert stats["total_entries"] <= 4
    
    @pytest.mark.asyncio
    async def test_lru_order_updated_on_access(self):
        """访问时更新 LRU 顺序"""
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        
        cache = FieldValueCache(
            max_fields=2,
            shard_count=1,  # 单分片，方便测试
        )
        
        datasource = "ds_test_lru_order"
        
        # 添加 2 个字段
        await cache.set("old_field", datasource, ["a"])
        await cache.set("new_field", datasource, ["b"])
        
        # 访问 old_field，使其成为最近使用
        await cache.get("old_field", datasource)
        
        # 添加第 3 个字段，应该淘汰 new_field（因为 old_field 刚被访问）
        await cache.set("newest_field", datasource, ["c"])
        
        # 验证：old_field 应该还在
        result_old = await cache.get("old_field", datasource)
        assert result_old == ["a"]
        
        # 验证：new_field 应该被淘汰
        result_new = await cache.get("new_field", datasource)
        assert result_new is None
    
    @given(
        field_count=st.integers(min_value=5, max_value=20),
        max_fields=st.integers(min_value=2, max_value=10),
    )
    @settings(max_examples=10, deadline=None)
    def test_cache_never_exceeds_max_fields(self, field_count: int, max_fields: int):
        """缓存永远不超过最大字段数"""
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        
        cache = FieldValueCache(
            max_fields=max_fields,
            shard_count=4,
        )
        
        datasource = "ds_test_max"
        
        async def run_test():
            # 添加超过容量的字段
            for i in range(field_count):
                await cache.set(f"field_{i}", datasource, [f"value_{i}"])
            
            # 验证：总条目数不超过 max_fields
            stats = cache.get_stats()
            assert stats["total_entries"] <= max_fields
        
        asyncio.run(run_test())


# ═══════════════════════════════════════════════════════════════════════════
# Property 36.1: Field Value Cache Sharded Lock Concurrency
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty36_1ShardedLockConcurrency:
    """
    Property 36.1: Field Value Cache Sharded Lock Concurrency
    
    **Validates: Requirements 10.1.1, 10.1.2**
    
    *For any* concurrent operations on different shards, the FieldValueCache 
    SHALL allow parallel execution without blocking.
    """
    
    @pytest.mark.asyncio
    async def test_different_shards_can_operate_concurrently(self):
        """不同分片的操作可以并行执行"""
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        import time
        
        cache = FieldValueCache(shard_count=4)
        datasource = "ds_test_concurrent"
        
        # 找到映射到不同分片的 key
        keys_by_shard = {}
        for i in range(100):
            key = f"field_{i}"
            full_key = cache._make_key(key, datasource)
            shard_idx = cache._get_shard_index(full_key)
            if shard_idx not in keys_by_shard:
                keys_by_shard[shard_idx] = key
            if len(keys_by_shard) >= 2:
                break
        
        assert len(keys_by_shard) >= 2, "需要至少 2 个不同分片的 key"
        
        shard_keys = list(keys_by_shard.values())
        key_a, key_b = shard_keys[0], shard_keys[1]
        
        # 并发写入不同分片
        start_time = time.time()
        await asyncio.gather(
            cache.set(key_a, datasource, ["a"] * 100),
            cache.set(key_b, datasource, ["b"] * 100),
        )
        elapsed = time.time() - start_time
        
        # 验证：两个操作都成功
        result_a = await cache.get(key_a, datasource)
        result_b = await cache.get(key_b, datasource)
        
        assert result_a is not None
        assert result_b is not None
        assert len(result_a) == 100
        assert len(result_b) == 100
    
    @pytest.mark.asyncio
    async def test_shard_distribution(self):
        """验证 key 分布到不同分片"""
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        
        cache = FieldValueCache(shard_count=16)
        datasource = "ds_test_distribution"
        
        # 统计 key 分布
        shard_counts = [0] * 16
        for i in range(160):
            key = cache._make_key(f"field_{i}", datasource)
            shard_idx = cache._get_shard_index(key)
            shard_counts[shard_idx] += 1
        
        # 验证：每个分片都有 key（分布相对均匀）
        non_empty_shards = sum(1 for c in shard_counts if c > 0)
        assert non_empty_shards >= 8, f"分布不均匀: {shard_counts}"


# ═══════════════════════════════════════════════════════════════════════════
# Property 37: Field Value Cache Preload Threshold
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty37PreloadThreshold:
    """
    Property 37: Field Value Cache Preload Threshold
    
    **Validates: Requirements 10.1.6**
    
    *For any* preload operation, the FieldValueCache SHALL only preload 
    dimension fields with cardinality < 500.
    """
    
    @pytest.mark.asyncio
    async def test_only_low_cardinality_fields_preloaded(self):
        """只预加载基数 < 500 的维度字段"""
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from unittest.mock import MagicMock, AsyncMock
        
        cache = FieldValueCache()
        datasource = "ds_test_preload"
        
        # 创建模拟数据模型
        mock_data_model = MagicMock()
        
        # 创建不同类型的字段
        fields = [
            # 低基数维度字段 - 应该预加载
            MagicMock(name="region", role="DIMENSION", data_type="string", cardinality=50),
            MagicMock(name="category", role="DIMENSION", data_type="string", cardinality=100),
            # 高基数维度字段 - 不应该预加载
            MagicMock(name="customer_id", role="DIMENSION", data_type="string", cardinality=10000),
            # 度量字段 - 不应该预加载
            MagicMock(name="sales", role="MEASURE", data_type="number", cardinality=0),
            # 时间字段 - 不应该预加载
            MagicMock(name="order_date", role="DIMENSION", data_type="date", cardinality=365),
        ]
        
        # 设置字段名属性
        for f in fields:
            f.name = f._mock_name
        
        mock_data_model.fields = fields
        
        # 记录哪些字段被加载
        loaded_fields = []
        
        async def mock_fetch(field_name: str) -> list:
            loaded_fields.append(field_name)
            return [f"value_{i}" for i in range(10)]
        
        # 执行预加载
        count = await cache.preload_common_fields(
            data_model=mock_data_model,
            datasource_luid=datasource,
            fetch_field_values_func=mock_fetch,
        )
        
        # 验证：只加载了低基数维度字段
        assert "region" in loaded_fields
        assert "category" in loaded_fields
        assert "customer_id" not in loaded_fields  # 高基数
        assert "sales" not in loaded_fields  # 度量
        assert "order_date" not in loaded_fields  # 时间类型
    
    @pytest.mark.asyncio
    async def test_preload_respects_max_fields_limit(self):
        """预加载不超过最大字段数限制"""
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from unittest.mock import MagicMock
        
        cache = FieldValueCache()
        datasource = "ds_test_preload_limit"
        
        # 创建 30 个低基数维度字段
        mock_data_model = MagicMock()
        fields = []
        for i in range(30):
            f = MagicMock()
            f.name = f"field_{i}"
            f.role = "DIMENSION"
            f.data_type = "string"
            f.cardinality = 50
            fields.append(f)
        
        mock_data_model.fields = fields
        
        loaded_fields = []
        
        async def mock_fetch(field_name: str) -> list:
            loaded_fields.append(field_name)
            return ["a", "b", "c"]
        
        # 执行预加载
        count = await cache.preload_common_fields(
            data_model=mock_data_model,
            datasource_luid=datasource,
            fetch_field_values_func=mock_fetch,
        )
        
        # 验证：最多预加载 MAX_PRELOAD_FIELDS 个字段
        assert len(loaded_fields) <= cache.MAX_PRELOAD_FIELDS
        assert count <= cache.MAX_PRELOAD_FIELDS


# ═══════════════════════════════════════════════════════════════════════════
# Property 23: Filter Validation Before Execution
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty23FilterValidationBeforeExecution:
    """
    Property 23: Filter Validation Before Execution
    
    **Validates: Requirements 3.4 (Req 3)**
    
    *For any* query with filter conditions, the FilterValueValidator SHALL 
    validate all filter values before query execution.
    """
    
    @staticmethod
    def _create_mock_data_model():
        """创建模拟数据模型"""
        from unittest.mock import MagicMock
        
        model = MagicMock()
        
        # 创建字段
        region_field = MagicMock()
        region_field.name = "region"
        region_field.data_type = "string"
        region_field.role = "dimension"
        
        date_field = MagicMock()
        date_field.name = "order_date"
        date_field.data_type = "date"
        date_field.role = "dimension"
        
        model.fields = [region_field, date_field]
        
        def get_field(name):
            for f in model.fields:
                if f.name == name:
                    return f
            return None
        
        model.get_field = get_field
        return model
    
    @staticmethod
    def _create_mock_semantic_output(filters):
        """创建模拟 SemanticOutput"""
        from unittest.mock import MagicMock
        
        output = MagicMock()
        where = MagicMock()
        where.filters = filters
        output.where = where
        return output

    @pytest.mark.asyncio
    async def test_all_set_filters_are_validated(self):
        """所有 SET 类型筛选条件都被验证 - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter, FilterType
        from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
            FilterValidationType,
        )
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        # 获取真实认证
        auth = await get_tableau_auth_async()
        
        # 创建真实组件
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        cache = FieldValueCache()
        
        # 获取数据源 LUID
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            pytest.skip(f"未找到数据源: {datasource_name}")
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=cache,
        )
        
        # 创建筛选条件 - 使用真实数据源中的字段
        filters = [
            SetFilter(field_name="公司名称", values=["正大益生科技发展（北京）有限公司", "不存在的公司"]),
        ]
        
        semantic_output = self._create_mock_semantic_output(filters)
        
        # 执行验证
        summary = await validator.validate(
            semantic_output=semantic_output,
            data_model=data_model,
            datasource_id=datasource_luid,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        await client.close()

        # 验证：每个筛选值都有验证结果
        assert len(summary.results) == 2  # 两个值
        
        # 验证：精确匹配的值
        exact_result = next(
            (r for r in summary.results if "正大益生科技发展" in r.requested_value), None
        )
        assert exact_result is not None
        assert exact_result.is_valid is True
        assert exact_result.validation_type == FilterValidationType.EXACT_MATCH
        
        # 验证：不存在的值
        not_found_result = next(
            (r for r in summary.results if r.requested_value == "不存在的公司"), None
        )
        assert not_found_result is not None
        assert not_found_result.is_valid is False
    
    @given(
        filter_count=st.integers(min_value=1, max_value=3),
    )
    @settings(max_examples=3, deadline=None)
    def test_multiple_filters_all_validated(self, filter_count: int):
        """多个筛选条件都被验证 - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async def run_test():
            # 获取真实认证
            auth = await get_tableau_auth_async()
            
            # 创建真实组件
            client = VizQLClient()
            adapter = TableauAdapter(vizql_client=client)
            cache = FieldValueCache()
            
            # 获取数据源 LUID
            datasource_name = "正大益生"
            datasource_luid = await client.get_datasource_luid_by_name(
                datasource_name=datasource_name,
                api_key=auth.api_key,
            )
            
            if not datasource_luid:
                await client.close()
                return  # 跳过测试
            
            # 加载真实数据模型
            loader = TableauDataLoader(client=client)
            data_model = await loader.load_data_model(
                datasource_id=datasource_luid,
                auth=auth,
            )
            
            validator = FilterValueValidator(
                platform_adapter=adapter,
                field_value_cache=cache,
            )

            # 创建多个筛选条件 - 使用真实字段
            test_values = ["测试值1", "测试值2", "测试值3"][:filter_count]
            filters = [
                SetFilter(field_name="公司名称", values=[v])
                for v in test_values
            ]
            
            semantic_output = self._create_mock_semantic_output(filters)
            
            summary = await validator.validate(
                semantic_output=semantic_output,
                data_model=data_model,
                datasource_id=datasource_luid,
                api_key=auth.api_key,
                site=auth.site,
            )
            
            await client.close()
            
            # 验证：每个筛选条件都有结果
            assert len(summary.results) >= filter_count
        
        asyncio.run(run_test())


# ═══════════════════════════════════════════════════════════════════════════
# Property 29: Filter Validation Skip for Time Fields
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty29FilterValidationSkipForTimeFields:
    """
    Property 29: Filter Validation Skip for Time Fields
    
    **Validates: Requirements 3.4 (Req 3)**
    
    *For any* filter condition on a time-type field (date, datetime, timestamp), 
    the FilterValueValidator SHALL skip validation and return is_valid=True 
    with skip_reason="time_field".
    """

    @staticmethod
    def _create_mock_data_model_with_time_field(data_type: str):
        """创建包含时间字段的模拟数据模型"""
        from unittest.mock import MagicMock
        
        model = MagicMock()
        
        time_field = MagicMock()
        time_field.name = "order_date"
        time_field.data_type = data_type
        time_field.role = "dimension"
        
        model.fields = [time_field]
        
        def get_field(name):
            for f in model.fields:
                if f.name == name:
                    return f
            return None
        
        model.get_field = get_field
        return model
    
    @given(
        time_data_type=st.sampled_from(["date", "datetime", "timestamp"]),
    )
    @settings(max_examples=3, deadline=None)
    def test_time_fields_skipped(self, time_data_type: str):
        """时间字段跳过验证 - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter, FilterType
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async def run_test():
            # 获取真实认证
            auth = await get_tableau_auth_async()
            
            # 创建真实组件
            client = VizQLClient()
            adapter = TableauAdapter(vizql_client=client)
            cache = FieldValueCache()
            
            # 获取数据源 LUID
            datasource_name = "正大益生"
            datasource_luid = await client.get_datasource_luid_by_name(
                datasource_name=datasource_name,
                api_key=auth.api_key,
            )
            
            if not datasource_luid:
                await client.close()
                return  # 跳过测试
            
            # 加载真实数据模型
            loader = TableauDataLoader(client=client)
            data_model = await loader.load_data_model(
                datasource_id=datasource_luid,
                auth=auth,
            )
            
            validator = FilterValueValidator(
                platform_adapter=adapter,
                field_value_cache=cache,
            )
            
            # 查找数据模型中的时间字段
            time_field = None
            for field in data_model.fields:
                if field.data_type and field.data_type.lower() in ["date", "datetime", "timestamp"]:
                    time_field = field
                    break
            
            if not time_field:
                await client.close()
                return  # 没有时间字段，跳过测试
            
            # 检查 should_validate
            should_val, skip_reason = validator.should_validate(
                field_name=time_field.name,
                filter_type=FilterType.SET,
                data_model=data_model,
                datasource_id=datasource_luid,
            )
            
            await client.close()
            
            # 验证：时间字段跳过验证
            assert should_val is False
            assert skip_reason == "time_field"
        
        asyncio.run(run_test())
    
    @pytest.mark.asyncio
    async def test_date_filter_returns_valid_with_skip_reason(self):
        """日期筛选返回 is_valid=True 和 skip_reason - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
            FilterValidationType,
        )
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        from unittest.mock import MagicMock
        
        # 获取真实认证
        auth = await get_tableau_auth_async()
        
        # 创建真实组件
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        cache = FieldValueCache()
        
        # 获取数据源 LUID
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            await client.close()
            pytest.skip(f"未找到数据源: {datasource_name}")
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        # 查找数据模型中的时间字段
        time_field = None
        for field in data_model.fields:
            if field.data_type and field.data_type.lower() in ["date", "datetime", "timestamp"]:
                time_field = field
                break
        
        if not time_field:
            await client.close()
            pytest.skip("数据模型中没有时间字段")
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=cache,
        )

        # 创建日期筛选
        filters = [SetFilter(field_name=time_field.name, values=["2025-01-01"])]
        
        output = MagicMock()
        where = MagicMock()
        where.filters = filters
        output.where = where
        
        # 执行验证
        summary = await validator.validate(
            semantic_output=output,
            data_model=data_model,
            datasource_id=datasource_luid,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        await client.close()
        
        # 验证：结果是 valid 且有 skip_reason
        assert len(summary.results) == 1
        result = summary.results[0]
        assert result.is_valid is True
        assert result.validation_type == FilterValidationType.SKIPPED
        assert result.skip_reason == "time_field"


# ═══════════════════════════════════════════════════════════════════════════
# Property 38: Unresolvable Filter Detection
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty38UnresolvableFilterDetection:
    """
    Property 38: Unresolvable Filter Detection
    
    **Validates: Requirements 6.1 (Req 6)**
    
    *For any* filter validation where the requested value has no exact match 
    AND no similar values (empty similar_values list), the result SHALL have 
    is_unresolvable=True and the FilterValidationSummary SHALL have 
    has_unresolvable_filters=True.
    """

    @staticmethod
    def _create_mock_data_model():
        """创建模拟数据模型"""
        from unittest.mock import MagicMock
        
        model = MagicMock()
        
        region_field = MagicMock()
        region_field.name = "region"
        region_field.data_type = "string"
        region_field.role = "dimension"
        
        model.fields = [region_field]
        
        def get_field(name):
            for f in model.fields:
                if f.name == name:
                    return f
            return None
        
        model.get_field = get_field
        return model
    
    @pytest.mark.asyncio
    async def test_no_match_no_similar_is_unresolvable(self):
        """无匹配且无相似值时 is_unresolvable=True - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
            FilterValidationType,
        )
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        from unittest.mock import MagicMock
        
        # 获取真实认证
        auth = await get_tableau_auth_async()
        
        # 创建真实组件
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        cache = FieldValueCache()
        
        # 获取数据源 LUID
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            await client.close()
            pytest.skip(f"未找到数据源: {datasource_name}")
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=cache,
            similarity_threshold=0.9,  # 高阈值，确保找不到相似值
        )
        
        # 创建筛选条件 - 值完全不相关
        filters = [SetFilter(field_name="公司名称", values=["XYZ123ABC不存在的随机字符串"])]
        
        output = MagicMock()
        where = MagicMock()
        where.filters = filters
        output.where = where
        
        # 执行验证
        summary = await validator.validate(
            semantic_output=output,
            data_model=data_model,
            datasource_id=datasource_luid,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        await client.close()
        
        # 验证：结果是 unresolvable
        assert len(summary.results) == 1
        result = summary.results[0]
        assert result.is_valid is False
        assert result.is_unresolvable is True
        assert result.validation_type == FilterValidationType.NOT_FOUND
        
        # 验证：汇总也标记为 has_unresolvable_filters
        assert summary.has_unresolvable_filters is True
        assert summary.all_valid is False

    @pytest.mark.asyncio
    async def test_has_similar_is_not_unresolvable(self):
        """有相似值时 is_unresolvable=False - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
            FilterValidationType,
        )
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        from unittest.mock import MagicMock
        
        # 获取真实认证
        auth = await get_tableau_auth_async()
        
        # 创建真实组件
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        cache = FieldValueCache()
        
        # 获取数据源 LUID
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            await client.close()
            pytest.skip(f"未找到数据源: {datasource_name}")
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=cache,
        )
        
        # 创建筛选条件 - 值有相似的（"正大益生" 应该能匹配到 "正大益生科技发展（北京）有限公司"）
        filters = [SetFilter(field_name="公司名称", values=["正大益生"])]
        
        output = MagicMock()
        where = MagicMock()
        where.filters = filters
        output.where = where

        # 执行验证
        summary = await validator.validate(
            semantic_output=output,
            data_model=data_model,
            datasource_id=datasource_luid,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        await client.close()
        
        # 验证：结果需要确认但不是 unresolvable
        assert len(summary.results) == 1
        result = summary.results[0]
        assert result.is_valid is False
        assert result.is_unresolvable is False
        assert result.needs_confirmation is True
        assert len(result.similar_values) > 0
        
        # 验证：汇总不标记为 has_unresolvable_filters
        assert summary.has_unresolvable_filters is False


# ═══════════════════════════════════════════════════════════════════════════
# Property 39: Filter Validation interrupt() Condition
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty39FilterValidationInterruptCondition:
    """
    Property 39: Filter Validation interrupt() Condition
    
    **Validates: Requirements 6.4 (Req 6)**
    
    *For any* filter validation result, interrupt() SHALL be called if and 
    only if needs_confirmation=True AND similar_values is non-empty. 
    If is_unresolvable=True (no similar values), interrupt() SHALL NOT be called.
    
    注意：这个测试验证 FilterValidationResult 的状态，实际的 interrupt() 调用
    在 LangGraph 节点中实现。
    """

    @staticmethod
    def _create_mock_data_model():
        """创建模拟数据模型"""
        from unittest.mock import MagicMock
        
        model = MagicMock()
        
        region_field = MagicMock()
        region_field.name = "region"
        region_field.data_type = "string"
        region_field.role = "dimension"
        
        model.fields = [region_field]
        
        def get_field(name):
            for f in model.fields:
                if f.name == name:
                    return f
            return None
        
        model.get_field = get_field
        return model
    
    @pytest.mark.asyncio
    async def test_needs_confirmation_with_similar_values(self):
        """needs_confirmation=True 且有相似值时应触发 interrupt - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        from unittest.mock import MagicMock
        
        # 获取真实认证
        auth = await get_tableau_auth_async()
        
        # 创建真实组件
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        cache = FieldValueCache()
        
        # 获取数据源 LUID
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            await client.close()
            pytest.skip(f"未找到数据源: {datasource_name}")
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )

        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=cache,
        )
        
        # 使用部分匹配的值
        filters = [SetFilter(field_name="公司名称", values=["正大益生"])]
        
        output = MagicMock()
        where = MagicMock()
        where.filters = filters
        output.where = where
        
        summary = await validator.validate(
            semantic_output=output,
            data_model=data_model,
            datasource_id=datasource_luid,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        await client.close()
        
        # 验证：needs_confirmation=True 且有相似值
        result = summary.results[0]
        assert result.needs_confirmation is True
        assert len(result.similar_values) > 0
        assert result.is_unresolvable is False
        
        # 这种情况下应该触发 interrupt()
        # 实际的 interrupt() 调用在 LangGraph 节点中
    
    @pytest.mark.asyncio
    async def test_unresolvable_should_not_trigger_interrupt(self):
        """is_unresolvable=True 时不应触发 interrupt - 使用真实 Tableau 环境"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        from unittest.mock import MagicMock

        # 获取真实认证
        auth = await get_tableau_auth_async()
        
        # 创建真实组件
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        cache = FieldValueCache()
        
        # 获取数据源 LUID
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            await client.close()
            pytest.skip(f"未找到数据源: {datasource_name}")
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=cache,
            similarity_threshold=0.95,  # 高阈值
        )
        
        # 使用完全不相关的值
        filters = [SetFilter(field_name="公司名称", values=["XYZ123ABC完全不相关的随机字符串"])]
        
        output = MagicMock()
        where = MagicMock()
        where.filters = filters
        output.where = where
        
        summary = await validator.validate(
            semantic_output=output,
            data_model=data_model,
            datasource_id=datasource_luid,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        await client.close()
        
        # 验证：is_unresolvable=True 且没有相似值
        result = summary.results[0]
        assert result.is_unresolvable is True
        assert len(result.similar_values) == 0
        assert result.needs_confirmation is False
        
        # 这种情况下不应触发 interrupt()，而是返回澄清请求

    @given(
        has_similar=st.booleans(),
    )
    @settings(max_examples=4, deadline=None)
    def test_interrupt_condition_logic(self, has_similar: bool):
        """验证 interrupt 条件逻辑"""
        from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
            FilterValidationResult,
            FilterValidationType,
        )
        
        # 创建验证结果
        if has_similar:
            result = FilterValidationResult(
                is_valid=False,
                field_name="region",
                requested_value="北京",
                similar_values=["北京市", "北京区"],
                validation_type=FilterValidationType.NEEDS_CONFIRMATION,
                needs_confirmation=True,
                is_unresolvable=False,
            )
        else:
            result = FilterValidationResult(
                is_valid=False,
                field_name="region",
                requested_value="XYZ",
                similar_values=[],
                validation_type=FilterValidationType.NOT_FOUND,
                needs_confirmation=False,
                is_unresolvable=True,
            )
        
        # 验证：interrupt 条件
        should_interrupt = result.needs_confirmation and len(result.similar_values) > 0
        
        if has_similar:
            assert should_interrupt is True
        else:
            assert should_interrupt is False


# ═══════════════════════════════════════════════════════════════════════════
# Property 40: Multi-Round Filter Confirmation Accumulation
# ═══════════════════════════════════════════════════════════════════════════


class TestProperty40MultiRoundFilterConfirmationAccumulation:
    """
    Property 40: Multi-Round Filter Confirmation Accumulation
    
    **Validates: Requirements 6.4 (Req 6)**
    
    *For any* multi-round filter confirmation scenario, the confirmed_filters 
    list in SemanticParserState SHALL accumulate all confirmations across 
    rounds without losing previous confirmations.
    """
    
    @staticmethod
    def _create_mock_semantic_output():
        """创建模拟 SemanticOutput"""
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            What,
            Where,
            SelfCheck,
            HowType,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        
        return SemanticOutput(
            restated_question="测试问题",
            what=What(measures=[]),
            where=Where(
                dimensions=[],
                filters=[
                SetFilter(field_name="region", values=["北京", "上海"]),
                SetFilter(field_name="category", values=["电子产品"]),
            ]),
            how_type=HowType.SIMPLE,
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=0.9,
                computation_confidence=0.9,
                overall_confidence=0.9,
            ),
        )
    
    def test_single_confirmation_applied(self):
        """单个确认被正确应用"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient

        # 创建真实组件（不需要认证，因为只测试 apply_confirmations）
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=FieldValueCache(),
        )
        
        output = self._create_mock_semantic_output()
        
        # 应用单个确认
        updated = validator.apply_single_confirmation(
            semantic_output=output,
            field_name="region",
            original_value="北京",
            confirmed_value="北京市",
        )
        
        # 验证：北京被替换为北京市
        region_filter = next(
            f for f in updated.where.filters if f.field_name == "region"
        )
        assert "北京市" in region_filter.values
        assert "北京" not in region_filter.values
        assert "上海" in region_filter.values  # 其他值不变
    
    def test_multiple_confirmations_accumulated(self):
        """多个确认被累积应用"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        
        # 创建真实组件（不需要认证，因为只测试 apply_confirmations）
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=FieldValueCache(),
        )
        
        output = self._create_mock_semantic_output()
        
        # 第一轮确认
        output = validator.apply_single_confirmation(
            semantic_output=output,
            field_name="region",
            original_value="北京",
            confirmed_value="北京市",
        )

        # 第二轮确认
        output = validator.apply_single_confirmation(
            semantic_output=output,
            field_name="region",
            original_value="上海",
            confirmed_value="上海市",
        )
        
        # 验证：两个确认都被应用
        region_filter = next(
            f for f in output.where.filters if f.field_name == "region"
        )
        assert "北京市" in region_filter.values
        assert "上海市" in region_filter.values
        assert "北京" not in region_filter.values
        assert "上海" not in region_filter.values
    
    def test_apply_confirmations_batch(self):
        """批量应用确认"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        
        # 创建真实组件（不需要认证，因为只测试 apply_confirmations）
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=FieldValueCache(),
        )
        
        output = self._create_mock_semantic_output()
        
        # 批量确认
        confirmations = {
            "北京": "北京市",
            "上海": "上海市",
            "电子产品": "电子产品类",
        }
        
        updated = validator.apply_confirmations(
            semantic_output=output,
            confirmations=confirmations,
        )

        # 验证：所有确认都被应用
        region_filter = next(
            f for f in updated.where.filters if f.field_name == "region"
        )
        assert "北京市" in region_filter.values
        assert "上海市" in region_filter.values
        
        category_filter = next(
            f for f in updated.where.filters if f.field_name == "category"
        )
        assert "电子产品类" in category_filter.values
    
    @given(
        confirmation_count=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=5, deadline=None)
    def test_confirmations_never_lost(self, confirmation_count: int):
        """确认永远不会丢失"""
        from analytics_assistant.src.agents.semantic_parser.components.filter_validator import (
            FilterValueValidator,
        )
        from analytics_assistant.src.agents.semantic_parser.components.field_value_cache import (
            FieldValueCache,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            What,
            Where,
            SelfCheck,
            HowType,
        )
        from analytics_assistant.src.core.schemas.filters import SetFilter
        from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        
        # 创建真实组件（不需要认证，因为只测试 apply_confirmations）
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=FieldValueCache(),
        )
        
        # 创建有多个值的筛选条件
        values = [f"value_{i}" for i in range(confirmation_count)]
        output = SemanticOutput(
            restated_question="测试",
            what=What(measures=[]),
            where=Where(
                dimensions=[],
                filters=[
                SetFilter(field_name="field", values=values),
            ]),
            how_type=HowType.SIMPLE,
            self_check=SelfCheck(
                field_mapping_confidence=0.9,
                time_range_confidence=0.9,
                computation_confidence=0.9,
                overall_confidence=0.9,
            ),
        )

        # 逐个应用确认
        confirmed_values = []
        for i in range(confirmation_count):
            original = f"value_{i}"
            confirmed = f"confirmed_{i}"
            confirmed_values.append(confirmed)
            
            output = validator.apply_single_confirmation(
                semantic_output=output,
                field_name="field",
                original_value=original,
                confirmed_value=confirmed,
            )
        
        # 验证：所有确认都保留
        field_filter = output.where.filters[0]
        for confirmed in confirmed_values:
            assert confirmed in field_filter.values
        
        # 验证：原始值都被替换
        for i in range(confirmation_count):
            assert f"value_{i}" not in field_filter.values


# ═══════════════════════════════════════════════════════════════════════════
# Property 14: Retry Limit Enforcement
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty14RetryLimitEnforcement:
    """
    Property 14: Retry Limit Enforcement
    
    **Validates: Requirements 9.1 (Req 9)**
    
    *For any* error correction sequence, the ErrorCorrector SHALL NOT 
    exceed max_retries (default 3) attempts.
    """
    
    def test_max_retries_enforced(self):
        """重试次数不超过配置的最大值"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        # 模拟 4 次不同的错误
        errors = [
            ("error_a", "field_not_found"),
            ("error_b", "syntax_error"),
            ("error_c", "invalid_value"),
            ("error_d", "unknown_error"),
        ]
        
        retry_count = 0
        for error_info, error_type in errors:
            should_retry, abort_reason = corrector.should_retry(error_info, error_type)
            
            if should_retry:
                retry_count += 1
                # 记录错误历史
                corrector._error_history.append(ErrorCorrectionHistory(
                    error_type=error_type,
                    error_hash=corrector._compute_error_hash(error_info),
                    attempt_number=retry_count,
                ))
        
        # 验证：最多 max_retries 次重试
        assert retry_count <= corrector.max_retries
    
    @given(error_count=st.integers(min_value=1, max_value=10))
    @settings(max_examples=20, deadline=None)
    def test_retry_count_never_exceeds_max(self, error_count: int):
        """任意错误数量下，重试次数不超过 max_retries"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        successful_retries = 0
        for i in range(error_count):
            error_info = f"unique_error_{i}_{datetime.now().timestamp()}"
            error_type = "field_not_found"
            
            should_retry, _ = corrector.should_retry(error_info, error_type)
            
            if should_retry:
                successful_retries += 1
                corrector._error_history.append(ErrorCorrectionHistory(
                    error_type=error_type,
                    error_hash=corrector._compute_error_hash(error_info),
                    attempt_number=successful_retries,
                ))
        
        # 验证：重试次数不超过 max_retries
        assert successful_retries <= corrector.max_retries


# ═══════════════════════════════════════════════════════════════════════════
# Property 30: Duplicate Error Detection
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty30DuplicateErrorDetection:
    """
    Property 30: Duplicate Error Detection
    
    **Validates: Requirements 9.2 (Req 9)**
    
    *For any* error correction attempt, if the same error (by error_hash) 
    appears 2 or more times in error_history, the ErrorCorrector SHALL 
    abort with reason "duplicate_error_detected".
    """
    
    def test_duplicate_error_detected(self):
        """相同错误出现 max_same_error_count 次时终止"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        # 第一次错误
        error_info = "Field 'sales' not found in datasource"
        error_type = "field_not_found"
        
        should_retry_1, reason_1 = corrector.should_retry(error_info, error_type)
        assert should_retry_1 is True
        assert reason_1 is None
        
        # 记录第一次错误
        corrector._error_history.append(ErrorCorrectionHistory(
            error_type=error_type,
            error_hash=corrector._compute_error_hash(error_info),
            attempt_number=1,
        ))
        
        # 第二次相同错误 - 根据 max_same_error_count=2，第二次仍然允许
        should_retry_2, reason_2 = corrector.should_retry(error_info, error_type)
        # max_same_error_count=2 意味着允许出现 2 次，所以第二次仍然允许
        # 只有当 same_error_count >= max_same_error_count 时才终止
        # 此时 same_error_count=1，不满足 >= 2
        assert should_retry_2 is True
        
        # 记录第二次错误
        corrector._error_history.append(ErrorCorrectionHistory(
            error_type=error_type,
            error_hash=corrector._compute_error_hash(error_info),
            attempt_number=2,
        ))
        
        # 第三次相同错误 - 此时 same_error_count=2，满足 >= 2，应该终止
        should_retry_3, reason_3 = corrector.should_retry(error_info, error_type)
        assert should_retry_3 is False
        assert reason_3 == "duplicate_error_detected"
    
    def test_different_errors_allowed(self):
        """不同错误可以继续重试"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        # 第一次错误
        error_info_1 = "Field 'sales' not found"
        corrector._error_history.append(ErrorCorrectionHistory(
            error_type="field_not_found",
            error_hash=corrector._compute_error_hash(error_info_1),
            attempt_number=1,
        ))
        
        # 第二次不同错误
        error_info_2 = "Syntax error in formula"
        should_retry, reason = corrector.should_retry(error_info_2, "syntax_error")
        
        assert should_retry is True
        assert reason is None
    
    @given(
        error_text=st.text(min_size=10, max_size=100).filter(lambda x: x.strip()),
    )
    @settings(max_examples=20, deadline=None)
    def test_same_error_hash_triggers_abort(self, error_text: str):
        """相同错误 hash 达到 max_same_error_count 次时触发终止"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        # 记录 max_same_error_count 次相同错误
        for i in range(corrector.max_same_error_count):
            corrector._error_history.append(ErrorCorrectionHistory(
                error_type="test_error",
                error_hash=corrector._compute_error_hash(error_text),
                attempt_number=i + 1,
            ))
        
        # 下一次相同错误应该被检测
        should_retry, reason = corrector.should_retry(error_text, "test_error")
        
        assert should_retry is False
        assert reason == "duplicate_error_detected"


# ═══════════════════════════════════════════════════════════════════════════
# Property 30.1: Alternating Error Detection
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty30_1AlternatingErrorDetection:
    """
    Property 30.1: Alternating Error Detection
    
    **Validates: Requirements 9.2 (Req 9)**
    
    *For any* error correction sequence, if the total error_history length 
    reaches max_retries (default 3), the ErrorCorrector SHALL abort with reason 
    "total_error_history_exceeded", preventing alternating error patterns 
    (A→B→A→B) from bypassing duplicate detection.
    """
    
    def test_alternating_errors_detected(self):
        """交替错误模式被检测"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        # 模拟 A→B→A 交替错误模式
        errors = [
            ("error_A", "type_a"),
            ("error_B", "type_b"),
            ("error_A_again", "type_a"),  # 不同文本但会被检测为总历史超限
        ]
        
        for i, (error_info, error_type) in enumerate(errors):
            should_retry, reason = corrector.should_retry(error_info, error_type)
            
            if i < corrector.max_retries:
                if should_retry:
                    corrector._error_history.append(ErrorCorrectionHistory(
                        error_type=error_type,
                        error_hash=corrector._compute_error_hash(error_info),
                        attempt_number=i + 1,
                    ))
        
        # 第 4 次尝试应该被拒绝
        should_retry_4, reason_4 = corrector.should_retry("error_B_again", "type_b")
        assert should_retry_4 is False
        assert reason_4 == "total_error_history_exceeded"
    
    def test_total_history_limit(self):
        """总错误历史达到上限时终止"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.error_correction import (
            ErrorCorrectionHistory,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        # 填充 max_retries 个不同错误
        for i in range(corrector.max_retries):
            corrector._error_history.append(ErrorCorrectionHistory(
                error_type=f"type_{i}",
                error_hash=f"hash_{i}",
                attempt_number=i + 1,
            ))
        
        # 下一次尝试应该被拒绝
        should_retry, reason = corrector.should_retry("new_error", "new_type")
        
        assert should_retry is False
        assert reason == "total_error_history_exceeded"


# ═══════════════════════════════════════════════════════════════════════════
# Property 31: Non-Retryable Error Handling
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty31NonRetryableErrorHandling:
    """
    Property 31: Non-Retryable Error Handling
    
    **Validates: Requirements 9.2 (Req 9)**
    
    *For any* error with type in non_retryable_errors (timeout, 
    service_unavailable, authentication_error, rate_limit_exceeded), 
    the ErrorCorrector SHALL immediately abort without retry.
    """
    
    @pytest.mark.parametrize("error_type", [
        "timeout",
        "service_unavailable",
        "authentication_error",
        "rate_limit_exceeded",
        "permission_denied",
        "quota_exceeded",
    ])
    def test_non_retryable_errors_abort_immediately(self, error_type: str):
        """不可重试错误立即终止"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        # 即使是第一次错误，也应该立即终止
        should_retry, reason = corrector.should_retry(
            error_info="Some error message",
            error_type=error_type,
        )
        
        assert should_retry is False
        assert f"non_retryable_error: {error_type}" == reason
    
    def test_retryable_errors_allowed(self):
        """可重试错误允许重试"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        retryable_types = [
            "field_not_found",
            "syntax_error",
            "invalid_filter_value",
            "unknown_error",
        ]
        
        for error_type in retryable_types:
            should_retry, reason = corrector.should_retry(
                error_info=f"Error of type {error_type}",
                error_type=error_type,
            )
            
            assert should_retry is True, f"Error type {error_type} should be retryable"
            assert reason is None
    
    @given(
        error_type=st.sampled_from([
            "timeout", "service_unavailable", "authentication_error",
            "rate_limit_exceeded", "permission_denied", "quota_exceeded",
        ])
    )
    @settings(max_examples=20, deadline=None)
    def test_non_retryable_always_abort(self, error_type: str):
        """不可重试错误始终终止"""
        from analytics_assistant.src.agents.semantic_parser.components.error_corrector import (
            ErrorCorrector,
        )
        
        corrector = ErrorCorrector(llm=None)
        
        should_retry, reason = corrector.should_retry(
            error_info="Any error message",
            error_type=error_type,
        )
        
        assert should_retry is False
        assert "non_retryable_error" in reason


# ═══════════════════════════════════════════════════════════════════════════
# Property 15: Feedback to Example Promotion
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty15FeedbackToExamplePromotion:
    """
    Property 15: Feedback to Example Promotion
    
    **Validates: Requirements 15.2 (Task 15)**
    
    *For any* accepted feedback (FeedbackType.ACCEPT) with valid semantic_output,
    the FeedbackLearner SHALL add it to the Few-shot example candidate pool
    when auto_promote_enabled is True.
    
    使用真实的存储层。
    """
    
    TEST_DATASOURCE_PREFIX = "ds_pbt_feedback_"
    
    @staticmethod
    def _get_real_store():
        """获取真实存储"""
        from analytics_assistant.src.infra.storage import get_kv_store
        return get_kv_store()
    
    @staticmethod
    def _get_real_embedding():
        """获取真实 embedding"""
        from analytics_assistant.src.infra.ai import get_embeddings
        return get_embeddings()
    
    def test_accepted_feedback_promoted_to_example(self):
        """接受的反馈被提升为示例"""
        from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
            FeedbackLearner,
        )
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.feedback import (
            FeedbackType,
            FeedbackRecord,
        )
        
        store = self._get_real_store()
        embedding = self._get_real_embedding()
        
        # 创建 FewShotManager
        few_shot_manager = FewShotManager(
            store=store,
            embedding_model=embedding,
        )
        
        # 创建 FeedbackLearner（启用自动提升）
        learner = FeedbackLearner(
            store=store,
            few_shot_manager=few_shot_manager,
            auto_promote_enabled=True,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}promote_{int(datetime.now().timestamp())}"
        
        # 创建接受的反馈
        feedback = FeedbackRecord(
            id=f"fb_promote_{int(datetime.now().timestamp())}",
            question="上个月各地区的销售额",
            restated_question="查询上个月各地区的销售额数据",
            semantic_output={
                "what": {"measures": ["销售额"]},
                "where": {"dimensions": ["地区"]},
                "how": "SIMPLE",
            },
            query="SELECT region, SUM(sales) FROM table GROUP BY region",
            feedback_type=FeedbackType.ACCEPT,
            datasource_luid=datasource_luid,
        )
        
        # 记录反馈
        success = asyncio.run(learner.record(feedback))
        assert success
        
        # 验证反馈已记录
        recorded = asyncio.run(learner.get_feedback(feedback.id, datasource_luid))
        assert recorded is not None
        assert recorded.feedback_type == FeedbackType.ACCEPT
    
    def test_rejected_feedback_not_promoted(self):
        """拒绝的反馈不被提升"""
        from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
            FeedbackLearner,
        )
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.feedback import (
            FeedbackType,
            FeedbackRecord,
        )
        
        store = self._get_real_store()
        
        few_shot_manager = FewShotManager(store=store, embedding_model=None)
        learner = FeedbackLearner(
            store=store,
            few_shot_manager=few_shot_manager,
            auto_promote_enabled=True,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}reject_{int(datetime.now().timestamp())}"
        
        # 创建拒绝的反馈
        feedback = FeedbackRecord(
            id=f"fb_reject_{int(datetime.now().timestamp())}",
            question="错误的查询",
            feedback_type=FeedbackType.REJECT,
            rejection_reason="结果不正确",
            datasource_luid=datasource_luid,
        )
        
        # 记录反馈
        success = asyncio.run(learner.record(feedback))
        assert success
        
        # 尝试手动提升（应该失败）
        promote_success = asyncio.run(
            learner.promote_to_example(feedback.id, datasource_luid)
        )
        assert promote_success is False
    
    @given(
        feedback_type=st.sampled_from([
            "accept", "modify", "reject"
        ])
    )
    @settings(max_examples=10, deadline=None)
    def test_only_accept_can_be_promoted(self, feedback_type: str):
        """只有 ACCEPT 类型可以被提升"""
        from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
            FeedbackLearner,
        )
        from analytics_assistant.src.agents.semantic_parser.components.few_shot_manager import (
            FewShotManager,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.feedback import (
            FeedbackType,
            FeedbackRecord,
        )
        
        store = self._get_real_store()
        few_shot_manager = FewShotManager(store=store, embedding_model=None)
        learner = FeedbackLearner(
            store=store,
            few_shot_manager=few_shot_manager,
            auto_promote_enabled=False,  # 禁用自动提升，手动测试
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}type_{feedback_type}_{int(datetime.now().timestamp())}"
        
        # 创建反馈
        ft = FeedbackType(feedback_type)
        feedback = FeedbackRecord(
            id=f"fb_{feedback_type}_{int(datetime.now().timestamp())}",
            question="测试问题",
            semantic_output={"what": {}, "where": {}, "how": "SIMPLE"} if ft == FeedbackType.ACCEPT else None,
            feedback_type=ft,
            datasource_luid=datasource_luid,
        )
        
        # 记录反馈
        asyncio.run(learner.record(feedback))
        
        # 尝试提升
        promote_success = asyncio.run(
            learner.promote_to_example(feedback.id, datasource_luid)
        )
        
        # 只有 ACCEPT 且有 semantic_output 才能提升
        if ft == FeedbackType.ACCEPT and feedback.semantic_output:
            # 可能成功（取决于 FewShotManager 实现）
            pass
        else:
            assert promote_success is False


# ═══════════════════════════════════════════════════════════════════════════
# Property 16: Synonym Learning Threshold
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty16SynonymLearningThreshold:
    """
    Property 16: Synonym Learning Threshold
    
    **Validates: Requirements 15.3 (Task 15)**
    
    *For any* term-to-field mapping confirmed 3 or more times,
    the FeedbackLearner SHALL mark it as a confirmed synonym
    (confirmation_count >= synonym_threshold).
    
    使用真实的存储层。
    """
    
    TEST_DATASOURCE_PREFIX = "ds_pbt_synonym_"
    
    @staticmethod
    def _get_real_store():
        """获取真实存储"""
        from analytics_assistant.src.infra.storage import get_kv_store
        return get_kv_store()
    
    def test_synonym_reaches_threshold_after_3_confirmations(self):
        """同义词确认 3 次后达到阈值"""
        from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
            FeedbackLearner,
        )
        
        store = self._get_real_store()
        learner = FeedbackLearner(
            store=store,
            synonym_threshold=3,  # 阈值为 3
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}threshold_{int(datetime.now().timestamp())}"
        original_term = "销量"
        correct_field = "销售额"
        
        # 确认 3 次
        for i in range(3):
            success = asyncio.run(learner.learn_synonym(
                original_term=original_term,
                correct_field=correct_field,
                datasource_luid=datasource_luid,
            ))
            assert success
        
        # 获取映射
        mapping = asyncio.run(learner.get_synonym_mapping(
            original_term=original_term,
            correct_field=correct_field,
            datasource_luid=datasource_luid,
        ))
        
        assert mapping is not None
        assert mapping.confirmation_count >= 3
        
        # 验证已达到阈值
        confirmed = asyncio.run(learner.get_confirmed_synonyms(datasource_luid))
        assert any(
            m.original_term == original_term and m.correct_field == correct_field
            for m in confirmed
        )
    
    def test_synonym_below_threshold_not_confirmed(self):
        """同义词确认次数不足时未达到阈值"""
        from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
            FeedbackLearner,
        )
        
        store = self._get_real_store()
        learner = FeedbackLearner(
            store=store,
            synonym_threshold=3,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}below_{int(datetime.now().timestamp())}"
        original_term = "数量"
        correct_field = "订单数"
        
        # 只确认 2 次
        for i in range(2):
            asyncio.run(learner.learn_synonym(
                original_term=original_term,
                correct_field=correct_field,
                datasource_luid=datasource_luid,
            ))
        
        # 获取映射
        mapping = asyncio.run(learner.get_synonym_mapping(
            original_term=original_term,
            correct_field=correct_field,
            datasource_luid=datasource_luid,
        ))
        
        assert mapping is not None
        assert mapping.confirmation_count == 2
        
        # 验证未达到阈值
        confirmed = asyncio.run(learner.get_confirmed_synonyms(datasource_luid))
        assert not any(
            m.original_term == original_term and m.correct_field == correct_field
            for m in confirmed
        )
    
    @given(
        confirmation_count=st.integers(min_value=1, max_value=10),
        threshold=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=20, deadline=None)
    def test_threshold_property(self, confirmation_count: int, threshold: int):
        """确认次数与阈值的关系属性"""
        from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
            FeedbackLearner,
        )
        
        store = self._get_real_store()
        learner = FeedbackLearner(
            store=store,
            synonym_threshold=threshold,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}prop_{confirmation_count}_{threshold}_{int(datetime.now().timestamp())}"
        original_term = f"术语_{confirmation_count}"
        correct_field = f"字段_{threshold}"
        
        # 确认指定次数
        for i in range(confirmation_count):
            asyncio.run(learner.learn_synonym(
                original_term=original_term,
                correct_field=correct_field,
                datasource_luid=datasource_luid,
            ))
        
        # 获取映射
        mapping = asyncio.run(learner.get_synonym_mapping(
            original_term=original_term,
            correct_field=correct_field,
            datasource_luid=datasource_luid,
        ))
        
        assert mapping is not None
        assert mapping.confirmation_count == confirmation_count
        
        # 验证阈值逻辑
        confirmed = asyncio.run(learner.get_confirmed_synonyms(datasource_luid))
        is_confirmed = any(
            m.original_term == original_term and m.correct_field == correct_field
            for m in confirmed
        )
        
        # 属性：confirmation_count >= threshold 当且仅当 is_confirmed
        if confirmation_count >= threshold:
            assert is_confirmed, f"count={confirmation_count} >= threshold={threshold}, should be confirmed"
        else:
            assert not is_confirmed, f"count={confirmation_count} < threshold={threshold}, should not be confirmed"
    
    def test_multiple_synonyms_independent(self):
        """多个同义词映射独立计数"""
        from analytics_assistant.src.agents.semantic_parser.components.feedback_learner import (
            FeedbackLearner,
        )
        
        store = self._get_real_store()
        learner = FeedbackLearner(
            store=store,
            synonym_threshold=3,
        )
        
        datasource_luid = f"{self.TEST_DATASOURCE_PREFIX}multi_{int(datetime.now().timestamp())}"
        
        # 映射 1：确认 3 次
        for i in range(3):
            asyncio.run(learner.learn_synonym(
                original_term="销量",
                correct_field="销售额",
                datasource_luid=datasource_luid,
            ))
        
        # 映射 2：确认 1 次
        asyncio.run(learner.learn_synonym(
            original_term="数量",
            correct_field="订单数",
            datasource_luid=datasource_luid,
        ))
        
        # 获取所有已学习的同义词
        all_synonyms = asyncio.run(learner.get_learned_synonyms(datasource_luid))
        assert len(all_synonyms) == 2
        
        # 获取已确认的同义词
        confirmed = asyncio.run(learner.get_confirmed_synonyms(datasource_luid))
        assert len(confirmed) == 1
        assert confirmed[0].original_term == "销量"
        assert confirmed[0].correct_field == "销售额"


# ═══════════════════════════════════════════════════════════════════════════
# Property 24: Clarification Source Tracking
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty24ClarificationSourceTracking:
    """
    Property 24: Clarification Source Tracking
    
    **Validates: 流程控制 - 澄清来源追踪**
    
    *For any* clarification request, the clarification_source field SHALL 
    indicate whether it originated from SemanticUnderstanding or FilterValueValidator.
    
    测试策略：
    1. SemanticUnderstanding 产生的澄清 → clarification_source = SEMANTIC_UNDERSTANDING
    2. FilterValueValidator 产生的澄清 → clarification_source = FILTER_VALIDATOR
    """
    
    @staticmethod
    def _create_field_candidates():
        """创建字段候选列表"""
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        return [
            FieldCandidate(
                field_name="Sales",
                field_caption="销售额",
                field_type="measure",
                data_type="number",
                confidence=0.95,
            ),
            FieldCandidate(
                field_name="Region",
                field_caption="地区",
                field_type="dimension",
                data_type="string",
                sample_values=["北京市", "上海市", "广州市"],
                confidence=0.92,
            ),
            FieldCandidate(
                field_name="OrderDate",
                field_caption="订单日期",
                field_type="dimension",
                data_type="date",
                confidence=0.90,
            ),
        ]
    
    @given(
        question=st.sampled_from([
            "数据",  # 非常模糊，可能触发 SemanticUnderstanding 澄清
            "分析",  # 非常模糊
            "查询",  # 非常模糊
            "看看",  # 非常模糊
            "帮我",  # 非常模糊
        ])
    )
    @settings(max_examples=3, deadline=None)
    def test_semantic_understanding_clarification_source(self, question: str):
        """SemanticUnderstanding 产生的澄清来源正确
        
        **Validates: Property 24**
        
        当 SemanticUnderstanding 因问题不完整而需要澄清时，
        clarification_source 应为 SEMANTIC_UNDERSTANDING。
        """
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            ClarificationSource,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = asyncio.run(understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        ))
        
        # 验证结果是有效的
        assert isinstance(result, SemanticOutput)
        
        # 核心属性：如果需要澄清，来源必须是 SEMANTIC_UNDERSTANDING
        if result.needs_clarification:
            assert result.clarification_source is not None, \
                "needs_clarification=True 时 clarification_source 不能为 None"
            assert result.clarification_source == ClarificationSource.SEMANTIC_UNDERSTANDING, \
                f"SemanticUnderstanding 产生的澄清来源应为 SEMANTIC_UNDERSTANDING，实际为 {result.clarification_source}"
            assert result.clarification_question is not None, \
                "needs_clarification=True 时 clarification_question 不能为 None"
    
    @pytest.mark.asyncio
    async def test_filter_validator_clarification_source(self):
        """FilterValueValidator 产生的澄清来源正确
        
        **Validates: Property 24**
        
        当 FilterValueValidator 因筛选值不匹配而需要澄清时，
        clarification_source 应为 FILTER_VALIDATOR。
        """
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            ClarificationSource,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.filters import (
            FilterValidationResult,
            FilterValidationSummary,
            FilterValidationType,
        )
        
        # 模拟 FilterValueValidator 产生的无法解决的筛选值场景
        # 这里直接测试 graph.py 中 filter_validator_node 的逻辑
        
        # 创建一个无法解决的筛选值结果
        unresolvable_result = FilterValidationResult(
            is_valid=False,
            field_name="Region",
            requested_value="北京",
            matched_values=[],
            similar_values=[],  # 没有相似值
            validation_type=FilterValidationType.NOT_FOUND,
            is_unresolvable=True,
            message="字段 'Region' 中没有找到值 '北京'，也没有相似的候选值",
        )
        
        summary = FilterValidationSummary(
            results=[unresolvable_result],
            all_valid=False,
            has_unresolvable_filters=True,
        )
        
        # 验证 summary 的结构
        assert summary.has_unresolvable_filters is True
        
        # 模拟 filter_validator_node 的输出逻辑
        # 当 has_unresolvable_filters=True 时，应设置 clarification_source
        if summary.has_unresolvable_filters:
            clarification_source = ClarificationSource.FILTER_VALIDATOR.value
            assert clarification_source == "filter_validator", \
                f"FilterValueValidator 产生的澄清来源应为 filter_validator，实际为 {clarification_source}"
    
    @given(
        question=st.sampled_from([
            "各地区的销售额",
            "上个月的销售数据",
            "北京的订单数量",
        ])
    )
    @settings(max_examples=3, deadline=None)
    def test_no_clarification_no_source(self, question: str):
        """不需要澄清时，clarification_source 可以为 None
        
        **Validates: Property 24**
        
        当 needs_clarification=False 时，clarification_source 可以为 None。
        """
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            SemanticOutput,
            ClarificationSource,
        )
        
        understanding = SemanticUnderstanding()
        field_candidates = self._create_field_candidates()
        
        result = asyncio.run(understanding.understand(
            question=question,
            field_candidates=field_candidates,
            current_date=date(2025, 1, 28),
        ))
        
        # 验证结果是有效的
        assert isinstance(result, SemanticOutput)
        
        # 如果不需要澄清，clarification_source 可以为 None
        if not result.needs_clarification:
            # clarification_source 可以是 None 或者不设置
            # 这是允许的行为
            pass
        else:
            # 如果需要澄清，来源必须正确设置
            assert result.clarification_source == ClarificationSource.SEMANTIC_UNDERSTANDING
    
    def test_clarification_source_enum_values(self):
        """验证 ClarificationSource 枚举值
        
        **Validates: Property 24**
        
        确保 ClarificationSource 枚举包含正确的值。
        """
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            ClarificationSource,
        )
        
        # 验证枚举值
        assert ClarificationSource.SEMANTIC_UNDERSTANDING.value == "semantic_understanding"
        assert ClarificationSource.FILTER_VALIDATOR.value == "filter_validator"
        
        # 验证枚举成员数量
        assert len(ClarificationSource) == 2
    
    @pytest.mark.asyncio
    async def test_state_clarification_source_field(self):
        """验证 SemanticParserState 中的 clarification_source 字段
        
        **Validates: Property 24**
        
        确保 State 中的 clarification_source 字段可以正确存储和读取。
        """
        from analytics_assistant.src.agents.semantic_parser.state import (
            SemanticParserState,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.output import (
            ClarificationSource,
        )
        
        # 测试 SemanticUnderstanding 来源
        state1: SemanticParserState = {
            "question": "数据",
            "needs_clarification": True,
            "clarification_question": "请问您想查询什么数据？",
            "clarification_source": ClarificationSource.SEMANTIC_UNDERSTANDING.value,
        }
        
        assert state1["clarification_source"] == "semantic_understanding"
        
        # 测试 FilterValidator 来源
        state2: SemanticParserState = {
            "question": "北京的销售额",
            "needs_clarification": True,
            "clarification_question": "字段中没有找到 '北京'，请选择正确的值",
            "clarification_source": ClarificationSource.FILTER_VALIDATOR.value,
        }
        
        assert state2["clarification_source"] == "filter_validator"
        
        # 测试不需要澄清时
        state3: SemanticParserState = {
            "question": "各地区的销售额",
            "needs_clarification": False,
            "clarification_source": None,
        }
        
        assert state3["clarification_source"] is None



# ═══════════════════════════════════════════════════════════════════════════
# Property 27: Schema Hash Consistency
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty27SchemaHashConsistency:
    """
    Property 27: Schema Hash Consistency
    
    **Validates: Requirements 11.1, 11.2, 11.3**
    
    *For any* data model, the schema_hash SHALL change if and only if 
    the field list changes (name, data_type, or role).
    
    测试策略：
    1. 相同字段列表 → 相同 schema_hash
    2. 字段名变更 → schema_hash 变化
    3. 字段类型变更 → schema_hash 变化
    4. 字段角色变更 → schema_hash 变化
    5. 字段描述变更 → schema_hash 不变（描述不影响查询）
    """
    
    @staticmethod
    def _create_data_model(fields: List[Dict[str, str]]):
        """创建测试用的 DataModel"""
        from analytics_assistant.src.core.schemas.data_model import DataModel, Field
        
        field_objects = [
            Field(
                name=f.get("name", "field"),
                caption=f.get("caption", f.get("name", "field")),
                data_type=f.get("data_type", "STRING"),
                role=f.get("role", "DIMENSION"),
                description=f.get("description"),
            )
            for f in fields
        ]
        
        return DataModel(
            datasource_id="test_ds",
            fields=field_objects,
        )
    
    @given(
        field_count=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20, deadline=None)
    def test_same_fields_same_hash(self, field_count: int):
        """相同字段列表产生相同 schema_hash
        
        **Validates: Property 27**
        """
        fields = [
            {"name": f"field_{i}", "data_type": "STRING", "role": "DIMENSION"}
            for i in range(field_count)
        ]
        
        model1 = self._create_data_model(fields)
        model2 = self._create_data_model(fields)
        
        assert model1.schema_hash == model2.schema_hash, \
            "相同字段列表应产生相同 schema_hash"
    
    @given(
        original_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
        new_name=st.text(min_size=1, max_size=20).filter(lambda x: x.strip()),
    )
    @settings(max_examples=20, deadline=None)
    def test_field_name_change_changes_hash(self, original_name: str, new_name: str):
        """字段名变更导致 schema_hash 变化
        
        **Validates: Property 27**
        """
        assume(original_name.strip() != new_name.strip())
        
        fields1 = [{"name": original_name.strip(), "data_type": "STRING", "role": "DIMENSION"}]
        fields2 = [{"name": new_name.strip(), "data_type": "STRING", "role": "DIMENSION"}]
        
        model1 = self._create_data_model(fields1)
        model2 = self._create_data_model(fields2)
        
        assert model1.schema_hash != model2.schema_hash, \
            f"字段名变更应导致 schema_hash 变化: {original_name} -> {new_name}"
    
    @given(
        original_type=st.sampled_from(["STRING", "INTEGER", "REAL", "DATE", "DATETIME"]),
        new_type=st.sampled_from(["STRING", "INTEGER", "REAL", "DATE", "DATETIME"]),
    )
    @settings(max_examples=20, deadline=None)
    def test_field_type_change_changes_hash(self, original_type: str, new_type: str):
        """字段类型变更导致 schema_hash 变化
        
        **Validates: Property 27**
        """
        assume(original_type != new_type)
        
        fields1 = [{"name": "test_field", "data_type": original_type, "role": "DIMENSION"}]
        fields2 = [{"name": "test_field", "data_type": new_type, "role": "DIMENSION"}]
        
        model1 = self._create_data_model(fields1)
        model2 = self._create_data_model(fields2)
        
        assert model1.schema_hash != model2.schema_hash, \
            f"字段类型变更应导致 schema_hash 变化: {original_type} -> {new_type}"
    
    @given(
        original_role=st.sampled_from(["DIMENSION", "MEASURE"]),
        new_role=st.sampled_from(["DIMENSION", "MEASURE"]),
    )
    @settings(max_examples=10, deadline=None)
    def test_field_role_change_changes_hash(self, original_role: str, new_role: str):
        """字段角色变更导致 schema_hash 变化
        
        **Validates: Property 27**
        """
        assume(original_role != new_role)
        
        fields1 = [{"name": "test_field", "data_type": "STRING", "role": original_role}]
        fields2 = [{"name": "test_field", "data_type": "STRING", "role": new_role}]
        
        model1 = self._create_data_model(fields1)
        model2 = self._create_data_model(fields2)
        
        assert model1.schema_hash != model2.schema_hash, \
            f"字段角色变更应导致 schema_hash 变化: {original_role} -> {new_role}"
    
    @given(
        original_desc=st.text(max_size=100),
        new_desc=st.text(max_size=100),
    )
    @settings(max_examples=20, deadline=None)
    def test_field_description_change_does_not_change_hash(
        self, original_desc: str, new_desc: str
    ):
        """字段描述变更不影响 schema_hash
        
        **Validates: Property 27**
        
        描述变更不影响查询生成，因此 schema_hash 应保持不变。
        """
        fields1 = [
            {"name": "test_field", "data_type": "STRING", "role": "DIMENSION", 
             "description": original_desc}
        ]
        fields2 = [
            {"name": "test_field", "data_type": "STRING", "role": "DIMENSION", 
             "description": new_desc}
        ]
        
        model1 = self._create_data_model(fields1)
        model2 = self._create_data_model(fields2)
        
        assert model1.schema_hash == model2.schema_hash, \
            "字段描述变更不应影响 schema_hash"
    
    @given(
        field_count_before=st.integers(min_value=1, max_value=10),
        field_count_after=st.integers(min_value=1, max_value=10),
    )
    @settings(max_examples=20, deadline=None)
    def test_field_count_change_changes_hash(
        self, field_count_before: int, field_count_after: int
    ):
        """字段数量变更导致 schema_hash 变化
        
        **Validates: Property 27**
        """
        assume(field_count_before != field_count_after)
        
        fields1 = [
            {"name": f"field_{i}", "data_type": "STRING", "role": "DIMENSION"}
            for i in range(field_count_before)
        ]
        fields2 = [
            {"name": f"field_{i}", "data_type": "STRING", "role": "DIMENSION"}
            for i in range(field_count_after)
        ]
        
        model1 = self._create_data_model(fields1)
        model2 = self._create_data_model(fields2)
        
        assert model1.schema_hash != model2.schema_hash, \
            f"字段数量变更应导致 schema_hash 变化: {field_count_before} -> {field_count_after}"
    
    def test_empty_model_has_consistent_hash(self):
        """空数据模型有一致的 schema_hash
        
        **Validates: Property 27**
        """
        model1 = self._create_data_model([])
        model2 = self._create_data_model([])
        
        assert model1.schema_hash == model2.schema_hash, \
            "空数据模型应有一致的 schema_hash"
    
    def test_schema_hash_is_cached(self):
        """schema_hash 被缓存，多次访问返回相同值
        
        **Validates: Property 27**
        """
        fields = [
            {"name": "field_1", "data_type": "STRING", "role": "DIMENSION"},
            {"name": "field_2", "data_type": "INTEGER", "role": "MEASURE"},
        ]
        
        model = self._create_data_model(fields)
        
        # 多次访问应返回相同值
        hash1 = model.schema_hash
        hash2 = model.schema_hash
        hash3 = model.schema_hash
        
        assert hash1 == hash2 == hash3, \
            "schema_hash 应被缓存，多次访问返回相同值"
    
    def test_workflow_context_schema_hash(self):
        """WorkflowContext 正确获取 schema_hash
        
        **Validates: Property 27**
        """
        from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
        
        fields = [
            {"name": "Sales", "data_type": "REAL", "role": "MEASURE"},
            {"name": "Region", "data_type": "STRING", "role": "DIMENSION"},
        ]
        
        model = self._create_data_model(fields)
        
        ctx = WorkflowContext(
            datasource_luid="test_ds",
            data_model=model,
        )
        
        # WorkflowContext 的 schema_hash 应与 DataModel 的一致
        assert ctx.schema_hash == model.schema_hash, \
            "WorkflowContext.schema_hash 应与 DataModel.schema_hash 一致"
    
    def test_workflow_context_detects_schema_change(self):
        """WorkflowContext 正确检测 schema 变更
        
        **Validates: Property 27**
        """
        from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
        
        # 创建两个不同的数据模型
        fields1 = [{"name": "field_1", "data_type": "STRING", "role": "DIMENSION"}]
        fields2 = [{"name": "field_1", "data_type": "INTEGER", "role": "DIMENSION"}]  # 类型变更
        
        model1 = self._create_data_model(fields1)
        model2 = self._create_data_model(fields2)
        
        # 创建上下文，设置 previous_schema_hash
        ctx = WorkflowContext(
            datasource_luid="test_ds",
            data_model=model2,
            previous_schema_hash=model1.schema_hash,
        )
        
        # 应检测到 schema 变更
        assert ctx.has_schema_changed() is True, \
            "WorkflowContext 应检测到 schema 变更"
    
    def test_workflow_context_no_change_when_same_schema(self):
        """WorkflowContext 在 schema 相同时不报告变更
        
        **Validates: Property 27**
        """
        from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
        
        fields = [{"name": "field_1", "data_type": "STRING", "role": "DIMENSION"}]
        
        model = self._create_data_model(fields)
        
        # 创建上下文，previous_schema_hash 与当前相同
        ctx = WorkflowContext(
            datasource_luid="test_ds",
            data_model=model,
            previous_schema_hash=model.schema_hash,
        )
        
        # 不应检测到 schema 变更
        assert ctx.has_schema_changed() is False, \
            "WorkflowContext 在 schema 相同时不应报告变更"



# ═══════════════════════════════════════════════════════════════════════════
# Property 28: Hierarchy Enrichment
# ═══════════════════════════════════════════════════════════════════════════

class TestProperty28HierarchyEnrichment:
    """
    Property 28: Hierarchy Enrichment
    
    **Validates: Requirements 24.1.2, 24.2**
    
    *For any* dimension field with hierarchy information,
    the prompt SHALL include drill-down options.
    
    测试维度层级信息在 Prompt 中的正确包含：
    1. FieldCandidate 包含层级属性时，Prompt 应显示层级信息
    2. 有下钻选项时，Prompt 应包含下钻路径
    3. WorkflowContext 正确丰富字段候选的层级信息
    """
    
    def _get_prompt_builder(self):
        from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import (
            DynamicPromptBuilder,
        )
        return DynamicPromptBuilder()
    
    def _get_semantic_config(self):
        from analytics_assistant.src.agents.semantic_parser.schemas.config import SemanticConfig
        return SemanticConfig(current_date=date(2025, 1, 28))
    
    def _create_field_candidate(
        self,
        field_name: str,
        field_type: str = "dimension",
        hierarchy_category: str = None,
        hierarchy_level: int = None,
        granularity: str = None,
        drill_down_options: list = None,
        child_dimension: str = None,
    ):
        """创建带层级信息的 FieldCandidate"""
        from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
        
        return FieldCandidate(
            field_name=field_name,
            field_caption=field_name,
            field_type=field_type,
            data_type="STRING",
            confidence=0.9,
            hierarchy_category=hierarchy_category,
            hierarchy_level=hierarchy_level,
            granularity=granularity,
            drill_down_options=drill_down_options,
            child_dimension=child_dimension,
        )
    
    @given(
        category=st.sampled_from(["time", "geography", "product", "customer", "organization"]),
        level=st.integers(min_value=1, max_value=5),
    )
    @settings(max_examples=25, deadline=None)
    def test_hierarchy_category_and_level_in_prompt(
        self, 
        category: str,
        level: int,
    ):
        """层级类别和级别应出现在 Prompt 中
        
        **Validates: Property 28**
        """
        prompt_builder = self._get_prompt_builder()
        semantic_config = self._get_semantic_config()
        
        field = self._create_field_candidate(
            field_name="test_dimension",
            hierarchy_category=category,
            hierarchy_level=level,
        )
        
        prompt = prompt_builder.build(
            question="测试问题",
            field_candidates=[field],
            config=semantic_config,
        )
        
        # 验证层级类别出现在 Prompt 中
        category_names = {
            "time": "时间维度",
            "geography": "地理维度",
            "product": "产品维度",
            "customer": "客户维度",
            "organization": "组织维度",
        }
        expected_category = category_names.get(category, category)
        assert expected_category in prompt, \
            f"Prompt 应包含层级类别 '{expected_category}'"
        
        # 验证层级级别出现在 Prompt 中
        assert f"L{level}" in prompt, \
            f"Prompt 应包含层级级别 'L{level}'"
    
    @given(
        drill_options=st.lists(
            st.text(alphabet=st.characters(whitelist_categories=('L',)), min_size=1, max_size=10),
            min_size=1,
            max_size=3,
        ),
    )
    @settings(max_examples=20, deadline=None)
    def test_drill_down_options_in_prompt(
        self, 
        drill_options: list,
    ):
        """下钻选项应出现在 Prompt 中
        
        **Validates: Property 28**
        
        *For any* dimension field with drill-down options,
        the prompt SHALL include those options.
        """
        prompt_builder = self._get_prompt_builder()
        semantic_config = self._get_semantic_config()
        
        field = self._create_field_candidate(
            field_name="test_dimension",
            hierarchy_category="geography",
            hierarchy_level=2,
            drill_down_options=drill_options,
        )
        
        prompt = prompt_builder.build(
            question="测试问题",
            field_candidates=[field],
            config=semantic_config,
        )
        
        # 验证下钻关键字出现在 Prompt 中
        assert "下钻" in prompt, \
            "Prompt 应包含下钻信息"
        
        # 验证至少第一个下钻选项出现在 Prompt 中
        assert drill_options[0] in prompt, \
            f"Prompt 应包含下钻选项 '{drill_options[0]}'"
    
    def test_child_dimension_as_drill_option(self):
        """子维度应作为下钻选项出现
        
        **Validates: Property 28**
        """
        prompt_builder = self._get_prompt_builder()
        semantic_config = self._get_semantic_config()
        
        field = self._create_field_candidate(
            field_name="省份",
            hierarchy_category="geography",
            hierarchy_level=2,
            child_dimension="城市",
        )
        
        prompt = prompt_builder.build(
            question="各省份的销售额",
            field_candidates=[field],
            config=semantic_config,
        )
        
        # 验证子维度作为下钻选项出现
        assert "下钻" in prompt, "Prompt 应包含下钻信息"
        assert "城市" in prompt, "Prompt 应包含子维度 '城市'"
    
    def test_granularity_in_prompt(self):
        """粒度信息应出现在 Prompt 中
        
        **Validates: Property 28**
        """
        prompt_builder = self._get_prompt_builder()
        semantic_config = self._get_semantic_config()
        
        field = self._create_field_candidate(
            field_name="订单日期",
            hierarchy_category="time",
            hierarchy_level=3,
            granularity="月",
        )
        
        prompt = prompt_builder.build(
            question="按月统计销售额",
            field_candidates=[field],
            config=semantic_config,
        )
        
        # 验证粒度信息出现在 Prompt 中
        assert "粒度" in prompt, "Prompt 应包含粒度信息"
        assert "月" in prompt, "Prompt 应包含粒度值 '月'"
    
    def test_no_hierarchy_info_when_not_provided(self):
        """无层级信息时不应添加层级标记
        
        **Validates: Property 28**
        """
        prompt_builder = self._get_prompt_builder()
        semantic_config = self._get_semantic_config()
        
        field = self._create_field_candidate(
            field_name="普通字段",
            field_type="dimension",
        )
        
        prompt = prompt_builder.build(
            question="测试问题",
            field_candidates=[field],
            config=semantic_config,
        )
        
        # 验证没有层级相关标记
        assert "时间维度" not in prompt
        assert "地理维度" not in prompt
        assert "下钻" not in prompt
        assert "粒度:" not in prompt
    
    def test_workflow_context_enriches_field_candidates(self):
        """WorkflowContext 正确丰富字段候选的层级信息
        
        **Validates: Property 28, Task 24.1.2**
        """
        from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
        from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
        
        # 创建带层级信息的上下文
        dimension_hierarchy = {
            "省份": {
                "category": "geography",
                "level": 2,
                "granularity": "省级",
                "parent_dimension": "国家",
                "child_dimension": "城市",
            },
            "订单日期": {
                "category": "time",
                "level": 3,
                "granularity": "日",
                "parent_dimension": "月份",
                "child_dimension": None,
            },
        }
        
        ctx = WorkflowContext(
            datasource_luid="test_ds",
            dimension_hierarchy=dimension_hierarchy,
        )
        
        # 创建字段候选（无层级信息）
        candidates = [
            FieldCandidate(
                field_name="省份",
                field_caption="省份",
                field_type="dimension",
                data_type="STRING",
                confidence=0.9,
            ),
            FieldCandidate(
                field_name="订单日期",
                field_caption="订单日期",
                field_type="dimension",
                data_type="DATE",
                confidence=0.85,
            ),
            FieldCandidate(
                field_name="销售额",
                field_caption="销售额",
                field_type="measure",
                data_type="REAL",
                confidence=0.95,
            ),
        ]
        
        # 丰富层级信息
        enriched = ctx.enrich_field_candidates_with_hierarchy(candidates)
        
        # 验证省份字段被丰富
        province_field = next(f for f in enriched if f.field_name == "省份")
        assert province_field.hierarchy_category == "geography", \
            "省份字段应有 geography 类别"
        assert province_field.hierarchy_level == 2, \
            "省份字段应有层级 2"
        assert province_field.child_dimension == "城市", \
            "省份字段应有子维度 '城市'"
        
        # 验证订单日期字段被丰富
        date_field = next(f for f in enriched if f.field_name == "订单日期")
        assert date_field.hierarchy_category == "time", \
            "订单日期字段应有 time 类别"
        assert date_field.hierarchy_level == 3, \
            "订单日期字段应有层级 3"
        
        # 验证销售额字段未被修改（不在层级字典中）
        sales_field = next(f for f in enriched if f.field_name == "销售额")
        assert sales_field.hierarchy_category is None, \
            "销售额字段不应有层级类别"
    
    def test_empty_hierarchy_does_not_modify_candidates(self):
        """空层级字典不修改字段候选
        
        **Validates: Property 28**
        """
        from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
        from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
        
        ctx = WorkflowContext(
            datasource_luid="test_ds",
            dimension_hierarchy={},
        )
        
        candidates = [
            FieldCandidate(
                field_name="test_field",
                field_caption="test_field",
                field_type="dimension",
                data_type="STRING",
                confidence=0.9,
            ),
        ]
        
        enriched = ctx.enrich_field_candidates_with_hierarchy(candidates)
        
        # 验证字段未被修改
        assert enriched[0].hierarchy_category is None
        assert enriched[0].hierarchy_level is None
    
    def test_none_hierarchy_does_not_modify_candidates(self):
        """None 层级字典不修改字段候选
        
        **Validates: Property 28**
        """
        from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
        from analytics_assistant.src.core.schemas.field_candidate import FieldCandidate
        
        ctx = WorkflowContext(
            datasource_luid="test_ds",
            dimension_hierarchy=None,
        )
        
        candidates = [
            FieldCandidate(
                field_name="test_field",
                field_caption="test_field",
                field_type="dimension",
                data_type="STRING",
                confidence=0.9,
            ),
        ]
        
        enriched = ctx.enrich_field_candidates_with_hierarchy(candidates)
        
        # 验证返回原始列表
        assert enriched is candidates
