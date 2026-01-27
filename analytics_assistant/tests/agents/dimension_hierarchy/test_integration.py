# -*- coding: utf-8 -*-
"""
维度层级推断集成测试（使用真实 LLM 和 Embedding）

运行方式：
    python -m pytest tests/agents/dimension_hierarchy/test_integration.py -v -s

测试覆盖：
1. 种子数据匹配
2. LLM 推断（真实调用 DeepSeek）
3. RAG 初始化和检索（真实调用智谱 Embedding）
4. 自学习功能
5. 缓存功能
6. 增量推断
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

import pytest
import asyncio
import shutil


class TestDimensionHierarchyIntegration:
    """维度层级推断集成测试"""
    
    @pytest.mark.asyncio
    async def test_infer_time_dimensions(self):
        """测试时间维度推断（使用真实 LLM）"""
        from src.agents.dimension_hierarchy.inference import infer_dimension_hierarchy
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="quarter", caption="季度", data_type="string", role="dimension"),
            Field(name="month", caption="月份", data_type="integer", role="dimension"),
        ]
        
        print("\n=== 测试时间维度推断 ===")
        result = await infer_dimension_hierarchy(
            datasource_luid="test-integration",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, level={attrs.level}, confidence={attrs.level_confidence:.2f}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 3
        
        # 年份应该是时间维度，level 1
        if "年份" in result.dimension_hierarchy:
            year_attrs = result.dimension_hierarchy["年份"]
            assert year_attrs.category.value == "time"
            assert year_attrs.level == 1
    
    @pytest.mark.asyncio
    async def test_infer_geography_dimensions(self):
        """测试地理维度推断（使用真实 LLM）"""
        from src.agents.dimension_hierarchy.inference import infer_dimension_hierarchy
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="country", caption="国家", data_type="string", role="dimension"),
            Field(name="province", caption="省份", data_type="string", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
        ]
        
        print("\n=== 测试地理维度推断 ===")
        result = await infer_dimension_hierarchy(
            datasource_luid="test-integration",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, level={attrs.level}, confidence={attrs.level_confidence:.2f}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 3
        
        # 国家应该是地理维度，level 1
        if "国家" in result.dimension_hierarchy:
            country_attrs = result.dimension_hierarchy["国家"]
            assert country_attrs.category.value == "geography"
            assert country_attrs.level == 1
    
    @pytest.mark.asyncio
    async def test_infer_product_dimensions(self):
        """测试产品维度推断（使用真实 LLM）"""
        from src.agents.dimension_hierarchy.inference import infer_dimension_hierarchy
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="category", caption="产品类别", data_type="string", role="dimension"),
            Field(name="subcategory", caption="产品子类", data_type="string", role="dimension"),
            Field(name="product_name", caption="产品名称", data_type="string", role="dimension"),
        ]
        
        print("\n=== 测试产品维度推断 ===")
        result = await infer_dimension_hierarchy(
            datasource_luid="test-integration",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, level={attrs.level}, confidence={attrs.level_confidence:.2f}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 3
        
        # 产品类别应该是产品维度，level 1
        if "产品类别" in result.dimension_hierarchy:
            category_attrs = result.dimension_hierarchy["产品类别"]
            assert category_attrs.category.value == "product"
            assert category_attrs.level == 1
    
    @pytest.mark.asyncio
    async def test_infer_mixed_dimensions(self):
        """测试混合维度推断（使用真实 LLM）"""
        from src.agents.dimension_hierarchy.inference import infer_dimension_hierarchy
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="province", caption="省份", data_type="string", role="dimension"),
            Field(name="category", caption="产品类别", data_type="string", role="dimension"),
            Field(name="customer_type", caption="客户类型", data_type="string", role="dimension"),
        ]
        
        print("\n=== 测试混合维度推断 ===")
        result = await infer_dimension_hierarchy(
            datasource_luid="test-integration",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, level={attrs.level}, confidence={attrs.level_confidence:.2f}, reasoning={attrs.reasoning[:50]}...")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 4
    
    @pytest.mark.asyncio
    async def test_infer_with_llm_fallback(self):
        """测试 LLM 回退推断（非种子数据字段）"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        # 使用不在种子数据中的字段名
        fields = [
            Field(name="fiscal_period", caption="财务期间", data_type="string", role="dimension"),
            Field(name="sales_region", caption="销售大区", data_type="string", role="dimension"),
            Field(name="product_line", caption="产品线", data_type="string", role="dimension"),
        ]
        
        print("\n=== 测试 LLM 回退推断 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,  # 禁用 RAG，强制使用 LLM
            enable_cache=False,
            enable_self_learning=False,
        )
        
        result = await inference.infer(
            datasource_luid="test-llm-fallback",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, level={attrs.level}, confidence={attrs.level_confidence:.2f}")
            print(f"    reasoning: {attrs.reasoning}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 3
        
        # 财务期间应该是时间或财务维度
        if "财务期间" in result.dimension_hierarchy:
            attrs = result.dimension_hierarchy["财务期间"]
            assert attrs.category.value in ["time", "financial"]
    
    @pytest.mark.asyncio
    async def test_infer_with_streaming(self):
        """测试流式输出"""
        from src.agents.dimension_hierarchy.inference import infer_dimension_hierarchy
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
        ]
        
        print("\n=== 测试流式输出 ===")
        
        tokens = []
        async def on_token(token: str):
            tokens.append(token)
            print(token, end="", flush=True)
        
        result = await infer_dimension_hierarchy(
            datasource_luid="test-streaming",
            fields=fields,
            on_token=on_token,
        )
        
        print(f"\n\n收到 {len(tokens)} 个 token")
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 2


class TestDimensionHierarchyWithCache:
    """测试缓存功能"""
    
    @pytest.mark.asyncio
    async def test_cache_hit(self):
        """测试缓存命中"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
        ]
        
        print("\n=== 测试缓存命中 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=True,
            enable_self_learning=False,
        )
        
        # 第一次推断
        print("第一次推断...")
        result1 = await inference.infer(
            datasource_luid="test-cache",
            fields=fields,
        )
        print(f"结果: {result1.dimension_hierarchy}")
        
        # 第二次推断（应该命中缓存）
        print("第二次推断（应该命中缓存）...")
        result2 = await inference.infer(
            datasource_luid="test-cache",
            fields=fields,
        )
        print(f"结果: {result2.dimension_hierarchy}")
        
        # 验证结果一致
        assert result1.dimension_hierarchy.keys() == result2.dimension_hierarchy.keys()
    
    @pytest.mark.asyncio
    async def test_incremental_inference(self):
        """测试增量推断"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试增量推断 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=True,
            enable_self_learning=False,
        )
        
        # 第一次推断：2 个字段
        fields1 = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
        ]
        
        print("第一次推断: 2 个字段")
        result1 = await inference.infer(
            datasource_luid="test-incremental",
            fields=fields1,
        )
        print(f"结果: {len(result1.dimension_hierarchy)} 个字段")
        
        # 第二次推断：3 个字段（新增 1 个）
        fields2 = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
            Field(name="category", caption="产品类别", data_type="string", role="dimension"),
        ]
        
        print("第二次推断: 3 个字段（新增 1 个）")
        result2 = await inference.infer(
            datasource_luid="test-incremental",
            fields=fields2,
        )
        print(f"结果: {len(result2.dimension_hierarchy)} 个字段")
        
        # 验证结果
        assert len(result2.dimension_hierarchy) == 3
        assert "产品类别" in result2.dimension_hierarchy


if __name__ == "__main__":
    # 直接运行测试
    asyncio.run(TestDimensionHierarchyIntegration().test_infer_mixed_dimensions())


class TestRAGIntegration:
    """RAG 集成测试（使用真实 Embedding）"""
    
    @pytest.fixture(autouse=True)
    def setup_and_teardown(self):
        """测试前后清理"""
        # 清理测试用的索引目录
        test_index_dir = Path("analytics_assistant/data/indexes/dimension_patterns_test")
        if test_index_dir.exists():
            shutil.rmtree(test_index_dir)
        
        yield
        
        # 测试后清理
        if test_index_dir.exists():
            shutil.rmtree(test_index_dir)
    
    @pytest.mark.asyncio
    async def test_rag_initialization_with_real_embedding(self):
        """测试 RAG 初始化（使用真实 Embedding）"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试 RAG 初始化 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=False,
            enable_self_learning=True,
        )
        
        # 触发 RAG 初始化
        inference._init_rag()
        
        print(f"RAG 初始化状态: {inference._rag_initialized}")
        print(f"RAG 检索器: {inference._rag_retriever}")
        
        assert inference._rag_initialized is True
    
    @pytest.mark.asyncio
    async def test_rag_search_with_real_embedding(self):
        """测试 RAG 搜索（使用真实 Embedding）"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试 RAG 搜索 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=False,
            enable_self_learning=True,
        )
        
        # 初始化 RAG
        inference._init_rag()
        
        if inference._rag_retriever is None:
            print("RAG 检索器未初始化，跳过测试")
            pytest.skip("RAG retriever not initialized")
        
        # 测试搜索
        fields = [
            Field(name="year", caption="年度", data_type="integer", role="dimension"),
            Field(name="region", caption="区域", data_type="string", role="dimension"),
        ]
        
        results, misses = await inference._rag_search(fields)
        
        print(f"RAG 命中: {len(results)} 个")
        print(f"RAG 未命中: {len(misses)} 个")
        
        for name, attrs in results.items():
            print(f"  - {name}: category={attrs.category.value}, confidence={attrs.level_confidence:.2f}")
        
        # 验证结果
        assert isinstance(results, dict)
        assert isinstance(misses, list)
    
    @pytest.mark.asyncio
    async def test_full_inference_with_rag(self):
        """测试完整推断流程（种子 + RAG + LLM）"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试完整推断流程（种子 + RAG + LLM）===")
        
        inference = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        # 混合字段：种子数据 + 需要 RAG/LLM 的字段
        fields = [
            # 种子数据中存在的字段
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
            # 需要 RAG 或 LLM 推断的字段
            Field(name="fiscal_quarter", caption="财务季度", data_type="string", role="dimension"),
            Field(name="sales_territory", caption="销售区域", data_type="string", role="dimension"),
        ]
        
        result = await inference.infer(
            datasource_luid="test-full-inference",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, level={attrs.level}, confidence={attrs.level_confidence:.2f}")
            print(f"    reasoning: {attrs.reasoning}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 4
        
        # 年份应该是种子匹配
        assert "年份" in result.dimension_hierarchy
        assert result.dimension_hierarchy["年份"].level_confidence == 1.0
        assert "种子匹配" in result.dimension_hierarchy["年份"].reasoning


class TestSelfLearningIntegration:
    """自学习集成测试"""
    
    @pytest.mark.asyncio
    async def test_self_learning_stores_high_confidence_results(self):
        """测试自学习存储高置信度结果"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试自学习功能 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=True,
        )
        
        # 使用需要 LLM 推断的字段
        fields = [
            Field(name="business_unit", caption="业务单元", data_type="string", role="dimension"),
            Field(name="cost_center", caption="成本中心", data_type="string", role="dimension"),
        ]
        
        result = await inference.infer(
            datasource_luid="test-self-learning",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, confidence={attrs.level_confidence:.2f}")
            print(f"    reasoning: {attrs.reasoning}")
        
        # 检查是否有高置信度结果被存储
        if inference._pattern_store:
            pattern_index = inference._pattern_store.get("_pattern_index") or []
            print(f"存储的模式数量: {len(pattern_index)}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 2


class TestLLMInferenceIntegration:
    """LLM 推断集成测试"""
    
    @pytest.mark.asyncio
    async def test_llm_inference_with_complex_fields(self):
        """测试 LLM 推断复杂字段"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试 LLM 推断复杂字段 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        # 复杂字段名，需要 LLM 理解语义
        fields = [
            Field(name="order_create_time", caption="订单创建时间", data_type="datetime", role="dimension"),
            Field(name="ship_to_country", caption="收货国家", data_type="string", role="dimension"),
            Field(name="product_hierarchy_l1", caption="产品层级L1", data_type="string", role="dimension"),
            Field(name="customer_segment", caption="客户细分", data_type="string", role="dimension"),
            Field(name="sales_channel", caption="销售渠道", data_type="string", role="dimension"),
        ]
        
        result = await inference.infer(
            datasource_luid="test-llm-complex",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}:")
            print(f"      category: {attrs.category.value}")
            print(f"      category_detail: {attrs.category_detail}")
            print(f"      level: {attrs.level}")
            print(f"      granularity: {attrs.granularity}")
            print(f"      confidence: {attrs.level_confidence:.2f}")
            print(f"      reasoning: {attrs.reasoning}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 5
        
        # 验证推断的合理性
        if "订单创建时间" in result.dimension_hierarchy:
            attrs = result.dimension_hierarchy["订单创建时间"]
            assert attrs.category.value == "time"
        
        if "收货国家" in result.dimension_hierarchy:
            attrs = result.dimension_hierarchy["收货国家"]
            assert attrs.category.value == "geography"
        
        if "销售渠道" in result.dimension_hierarchy:
            attrs = result.dimension_hierarchy["销售渠道"]
            assert attrs.category.value == "channel"
    
    @pytest.mark.asyncio
    async def test_llm_inference_with_english_fields(self):
        """测试 LLM 推断英文字段"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试 LLM 推断英文字段 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        # 英文字段名
        fields = [
            Field(name="fiscal_year", caption="Fiscal Year", data_type="integer", role="dimension"),
            Field(name="geo_region", caption="Geographic Region", data_type="string", role="dimension"),
            Field(name="product_family", caption="Product Family", data_type="string", role="dimension"),
        ]
        
        result = await inference.infer(
            datasource_luid="test-llm-english",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: category={attrs.category.value}, level={attrs.level}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 3
    
    @pytest.mark.asyncio
    async def test_llm_inference_with_streaming_callback(self):
        """测试 LLM 推断流式回调"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试 LLM 推断流式回调 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        fields = [
            Field(name="region_code", caption="区域代码", data_type="string", role="dimension"),
        ]
        
        tokens_received = []
        
        async def on_token(token: str):
            tokens_received.append(token)
            print(token, end="", flush=True)
        
        result = await inference.infer(
            datasource_luid="test-streaming",
            fields=fields,
            on_token=on_token,
        )
        
        print(f"\n\n收到 {len(tokens_received)} 个 token")
        print(f"推断结果: {result.dimension_hierarchy}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 1


class TestEnrichFieldsIntegration:
    """字段丰富集成测试"""
    
    @pytest.mark.asyncio
    async def test_enrich_fields_updates_field_attributes(self):
        """测试字段丰富更新字段属性"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试字段丰富功能 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
        ]
        
        # 先推断
        await inference.infer(
            datasource_luid="test-enrich",
            fields=fields,
        )
        
        # 然后丰富字段
        enriched_fields = inference.enrich_fields(fields)
        
        print("丰富后的字段:")
        for f in enriched_fields:
            print(f"  - {f.caption}:")
            print(f"      category: {f.category}")
            print(f"      category_detail: {f.category_detail}")
            print(f"      hierarchy_level: {f.hierarchy_level}")
            print(f"      granularity: {f.granularity}")
            print(f"      level_confidence: {f.level_confidence}")
        
        # 验证字段被丰富
        year_field = next(f for f in enriched_fields if f.caption == "年份")
        assert year_field.category == "time"
        assert year_field.hierarchy_level == 1


class TestCacheIntegration:
    """缓存集成测试"""
    
    @pytest.mark.asyncio
    async def test_cache_stores_and_retrieves_results(self):
        """测试缓存存储和检索结果"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        import time
        
        print("\n=== 测试缓存存储和检索 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=True,
            enable_self_learning=False,
        )
        
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="month", caption="月份", data_type="integer", role="dimension"),
        ]
        
        # 第一次推断（应该执行完整推断）
        print("第一次推断...")
        start1 = time.time()
        result1 = await inference.infer(
            datasource_luid="test-cache-perf",
            fields=fields,
        )
        time1 = time.time() - start1
        print(f"耗时: {time1:.3f}s")
        
        # 第二次推断（应该命中缓存，更快）
        print("第二次推断（应该命中缓存）...")
        start2 = time.time()
        result2 = await inference.infer(
            datasource_luid="test-cache-perf",
            fields=fields,
        )
        time2 = time.time() - start2
        print(f"耗时: {time2:.3f}s")
        
        # 验证结果一致
        assert result1.dimension_hierarchy.keys() == result2.dimension_hierarchy.keys()
        
        # 缓存命中应该更快
        print(f"缓存加速比: {time1/time2:.1f}x")
    
    @pytest.mark.asyncio
    async def test_cache_invalidation_on_field_change(self):
        """测试字段变化时缓存失效"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试缓存失效 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=True,
            enable_self_learning=False,
        )
        
        # 第一次推断
        fields1 = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
        ]
        
        result1 = await inference.infer(
            datasource_luid="test-cache-invalidation",
            fields=fields1,
        )
        print(f"第一次推断: {len(result1.dimension_hierarchy)} 个字段")
        
        # 修改字段类型（应该触发重新推断）
        fields2 = [
            Field(name="year", caption="年份", data_type="string", role="dimension"),  # 类型变了
        ]
        
        result2 = await inference.infer(
            datasource_luid="test-cache-invalidation",
            fields=fields2,
        )
        print(f"第二次推断（字段类型变化）: {len(result2.dimension_hierarchy)} 个字段")
        
        # 验证结果
        assert len(result2.dimension_hierarchy) == 1


class TestEdgeCases:
    """边界情况测试"""
    
    @pytest.mark.asyncio
    async def test_empty_caption_uses_name(self):
        """测试空 caption 使用 name"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试空 caption 使用 name ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        fields = [
            Field(name="year", caption="", data_type="integer", role="dimension"),
        ]
        
        result = await inference.infer(
            datasource_luid="test-empty-caption",
            fields=fields,
        )
        
        print(f"推断结果: {result.dimension_hierarchy}")
        
        # 应该使用 name 作为键
        assert "year" in result.dimension_hierarchy
    
    @pytest.mark.asyncio
    async def test_special_characters_in_field_name(self):
        """测试字段名包含特殊字符"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试特殊字符字段名 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        fields = [
            Field(name="year_2024", caption="年份(2024)", data_type="integer", role="dimension"),
            Field(name="city_name", caption="城市/地区", data_type="string", role="dimension"),
        ]
        
        result = await inference.infer(
            datasource_luid="test-special-chars",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name}: {attrs.category.value}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 2
    
    @pytest.mark.asyncio
    async def test_large_batch_inference(self):
        """测试大批量字段推断"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试大批量字段推断 ===")
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        # 创建 20 个字段
        fields = [
            Field(name="year", caption="年份", data_type="integer", role="dimension"),
            Field(name="quarter", caption="季度", data_type="string", role="dimension"),
            Field(name="month", caption="月份", data_type="integer", role="dimension"),
            Field(name="week", caption="周", data_type="integer", role="dimension"),
            Field(name="date", caption="日期", data_type="date", role="dimension"),
            Field(name="country", caption="国家", data_type="string", role="dimension"),
            Field(name="province", caption="省份", data_type="string", role="dimension"),
            Field(name="city", caption="城市", data_type="string", role="dimension"),
            Field(name="district", caption="区县", data_type="string", role="dimension"),
            Field(name="category", caption="产品类别", data_type="string", role="dimension"),
            Field(name="subcategory", caption="产品子类", data_type="string", role="dimension"),
            Field(name="brand", caption="品牌", data_type="string", role="dimension"),
            Field(name="product_name", caption="产品名称", data_type="string", role="dimension"),
            Field(name="customer_type", caption="客户类型", data_type="string", role="dimension"),
            Field(name="customer_name", caption="客户名称", data_type="string", role="dimension"),
            Field(name="department", caption="部门", data_type="string", role="dimension"),
            Field(name="employee", caption="员工", data_type="string", role="dimension"),
            Field(name="channel", caption="渠道", data_type="string", role="dimension"),
            Field(name="store", caption="门店", data_type="string", role="dimension"),
            Field(name="order_id", caption="订单ID", data_type="string", role="dimension"),
        ]
        
        import time
        start = time.time()
        
        result = await inference.infer(
            datasource_luid="test-large-batch",
            fields=fields,
        )
        
        elapsed = time.time() - start
        
        print(f"推断 {len(fields)} 个字段耗时: {elapsed:.2f}s")
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        
        # 统计各类别数量
        category_counts = {}
        for name, attrs in result.dimension_hierarchy.items():
            cat = attrs.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        print("类别分布:")
        for cat, count in sorted(category_counts.items()):
            print(f"  - {cat}: {count}")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == 20


class TestTableauEndToEnd:
    """
    使用真实 Tableau 环境的端到端测试
    
    测试完整流程：Tableau 字段 → 种子匹配 → RAG 搜索 → LLM 推断 → 自学习
    
    运行方式：
        python -m pytest analytics_assistant/tests/agents/dimension_hierarchy/test_integration.py::TestTableauEndToEnd -v -s
    """
    
    # 测试用数据源名称（与 Tableau 集成测试一致）
    TEST_DATASOURCE_NAME = "正大益生业绩总览数据 (IMPALA)"
    
    @pytest.fixture(scope="class")
    def reset_config(self):
        """重置配置单例以确保加载最新配置"""
        from src.infra.config.config_loader import AppConfig
        AppConfig._instance = None
        yield
        AppConfig._instance = None
    
    @pytest.fixture(scope="class")
    def datasource_luid(self, reset_config):
        """获取测试用的数据源 LUID（通过名称查找）"""
        from src.platform.tableau.auth import get_tableau_auth
        from src.platform.tableau.client import VizQLClient
        
        # 使用同步方式获取认证
        auth = get_tableau_auth()
        
        # 使用 asyncio.run 运行异步代码
        async def get_luid():
            async with VizQLClient() as client:
                luid = await client.get_datasource_luid_by_name(
                    datasource_name=self.TEST_DATASOURCE_NAME,
                    api_key=auth.api_key,
                )
                return luid
        
        luid = asyncio.run(get_luid())
        if not luid:
            pytest.skip(f"未找到数据源: {self.TEST_DATASOURCE_NAME}")
        
        print(f"\n测试数据源: {self.TEST_DATASOURCE_NAME} -> {luid}")
        return luid
    
    @pytest.mark.asyncio
    async def test_load_tableau_fields(self, reset_config, datasource_luid):
        """测试从 Tableau 加载字段"""
        from src.platform.tableau.data_loader import TableauDataLoader
        
        print("\n=== 测试从 Tableau 加载字段 ===")
        
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
            
            assert data_model is not None
            assert len(data_model.fields) > 0
            
            # 统计维度和度量
            dimensions = data_model.dimensions
            measures = data_model.measures
            
            print(f"数据源: {data_model.datasource_name}")
            print(f"总字段数: {len(data_model.fields)}")
            print(f"维度: {len(dimensions)}")
            print(f"度量: {len(measures)}")
            
            # 打印前 10 个维度字段
            print("\n前 10 个维度字段:")
            for f in dimensions[:10]:
                print(f"  - {f.caption} ({f.data_type})")
            
            return data_model
    
    @pytest.mark.asyncio
    async def test_infer_tableau_dimensions(self, reset_config, datasource_luid):
        """测试推断 Tableau 数据源的维度层级（带流式输出）"""
        from src.platform.tableau.data_loader import TableauDataLoader
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        print("\n=== 测试推断 Tableau 维度层级 ===")
        
        # 1. 加载 Tableau 字段
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
        
        # 只取维度字段
        dimension_fields = data_model.dimensions
        print(f"加载了 {len(dimension_fields)} 个维度字段")
        
        # 2. 推断维度层级（带流式输出）
        inference = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=True,
            enable_self_learning=True,
        )
        
        tokens_received = []
        
        async def on_token(token: str):
            tokens_received.append(token)
            print(token, end="", flush=True)
        
        print("\nLLM 流式输出:")
        result = await inference.infer(
            datasource_luid=datasource_luid,
            fields=dimension_fields,
            on_token=on_token,
        )
        
        print(f"\n\n收到 {len(tokens_received)} 个 token")
        
        print(f"\n推断结果: {len(result.dimension_hierarchy)} 个字段")
        
        # 统计各类别数量
        category_counts = {}
        for name, attrs in result.dimension_hierarchy.items():
            cat = attrs.category.value
            category_counts[cat] = category_counts.get(cat, 0) + 1
        
        print("\n类别分布:")
        for cat, count in sorted(category_counts.items()):
            print(f"  - {cat}: {count}")
        
        # 打印部分推断结果
        print("\n部分推断结果:")
        for i, (name, attrs) in enumerate(result.dimension_hierarchy.items()):
            if i >= 15:
                print(f"  ... 还有 {len(result.dimension_hierarchy) - 15} 个字段")
                break
            print(f"  - {name}:")
            print(f"      category: {attrs.category.value}")
            print(f"      level: {attrs.level}")
            print(f"      confidence: {attrs.level_confidence:.2f}")
            print(f"      reasoning: {attrs.reasoning[:60]}...")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == len(dimension_fields)
    
    @pytest.mark.asyncio
    async def test_full_pipeline_with_rag_and_self_learning(self, reset_config, datasource_luid):
        """测试完整流程：种子匹配 → RAG → LLM → 自学习"""
        from src.platform.tableau.data_loader import TableauDataLoader
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        print("\n=== 测试完整流程（种子 + RAG + LLM + 自学习）===")
        
        # 1. 加载 Tableau 字段
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
        
        # 只取前 20 个维度字段进行测试
        dimension_fields = data_model.dimensions[:20]
        print(f"测试 {len(dimension_fields)} 个维度字段")
        
        # 2. 第一次推断（会触发 LLM 和自学习）
        inference = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=False,  # 禁用缓存，强制推断
            enable_self_learning=True,
        )
        
        print("\n第一次推断（触发 LLM 和自学习）...")
        import time
        start1 = time.time()
        result1 = await inference.infer(
            datasource_luid=f"{datasource_luid}-test-pipeline",
            fields=dimension_fields,
        )
        time1 = time.time() - start1
        print(f"耗时: {time1:.2f}s")
        
        # 统计推断来源
        seed_count = sum(1 for attrs in result1.dimension_hierarchy.values() if "种子匹配" in attrs.reasoning)
        rag_count = sum(1 for attrs in result1.dimension_hierarchy.values() if "RAG 匹配" in attrs.reasoning)
        llm_count = len(result1.dimension_hierarchy) - seed_count - rag_count
        
        print(f"\n推断来源统计:")
        print(f"  - 种子匹配: {seed_count}")
        print(f"  - RAG 匹配: {rag_count}")
        print(f"  - LLM 推断: {llm_count}")
        
        # 3. 第二次推断（应该有更多 RAG 命中，因为自学习存储了结果）
        inference2 = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=False,  # 禁用缓存
            enable_self_learning=False,  # 禁用自学习，只读取
        )
        
        print("\n第二次推断（验证自学习效果）...")
        start2 = time.time()
        result2 = await inference2.infer(
            datasource_luid=f"{datasource_luid}-test-pipeline-2",
            fields=dimension_fields,
        )
        time2 = time.time() - start2
        print(f"耗时: {time2:.2f}s")
        
        # 统计第二次推断来源
        seed_count2 = sum(1 for attrs in result2.dimension_hierarchy.values() if "种子匹配" in attrs.reasoning)
        rag_count2 = sum(1 for attrs in result2.dimension_hierarchy.values() if "RAG 匹配" in attrs.reasoning)
        llm_count2 = len(result2.dimension_hierarchy) - seed_count2 - rag_count2
        
        print(f"\n第二次推断来源统计:")
        print(f"  - 种子匹配: {seed_count2}")
        print(f"  - RAG 匹配: {rag_count2}")
        print(f"  - LLM 推断: {llm_count2}")
        
        # 验证结果
        assert len(result1.dimension_hierarchy) == len(dimension_fields)
        assert len(result2.dimension_hierarchy) == len(dimension_fields)
        
        # 自学习应该增加 RAG 命中率
        print(f"\n自学习效果: RAG 命中从 {rag_count} 增加到 {rag_count2}")
    
    @pytest.mark.asyncio
    async def test_incremental_inference_with_tableau(self, reset_config, datasource_luid):
        """测试增量推断（Tableau 字段变化）"""
        from src.platform.tableau.data_loader import TableauDataLoader
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        print("\n=== 测试增量推断 ===")
        
        # 1. 加载 Tableau 字段
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
        
        dimension_fields = data_model.dimensions
        
        # 2. 第一次推断：前 10 个字段
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=True,
            enable_self_learning=False,
        )
        
        fields_batch1 = dimension_fields[:10]
        print(f"\n第一次推断: {len(fields_batch1)} 个字段")
        
        import time
        start1 = time.time()
        result1 = await inference.infer(
            datasource_luid=f"{datasource_luid}-incremental",
            fields=fields_batch1,
        )
        time1 = time.time() - start1
        print(f"耗时: {time1:.2f}s, 结果: {len(result1.dimension_hierarchy)} 个字段")
        
        # 3. 第二次推断：前 15 个字段（新增 5 个）
        fields_batch2 = dimension_fields[:15]
        print(f"\n第二次推断: {len(fields_batch2)} 个字段（新增 5 个）")
        
        start2 = time.time()
        result2 = await inference.infer(
            datasource_luid=f"{datasource_luid}-incremental",
            fields=fields_batch2,
        )
        time2 = time.time() - start2
        print(f"耗时: {time2:.2f}s, 结果: {len(result2.dimension_hierarchy)} 个字段")
        
        # 增量推断应该更快（只推断新增的 5 个字段）
        print(f"\n增量推断加速: 第二次应该更快（只推断新增字段）")
        
        # 验证结果
        assert len(result1.dimension_hierarchy) == 10
        assert len(result2.dimension_hierarchy) == 15
    
    @pytest.mark.asyncio
    async def test_enrich_tableau_fields(self, reset_config, datasource_luid):
        """测试丰富 Tableau 字段属性"""
        from src.platform.tableau.data_loader import TableauDataLoader
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        print("\n=== 测试丰富 Tableau 字段属性 ===")
        
        # 1. 加载 Tableau 字段
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
        
        # 取前 10 个维度字段
        dimension_fields = data_model.dimensions[:10]
        
        # 2. 推断
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        await inference.infer(
            datasource_luid=f"{datasource_luid}-enrich",
            fields=dimension_fields,
        )
        
        # 3. 丰富字段
        enriched_fields = inference.enrich_fields(dimension_fields)
        
        print("\n丰富后的字段:")
        for f in enriched_fields:
            print(f"  - {f.caption}:")
            print(f"      原始: data_type={f.data_type}, role={f.role}")
            print(f"      丰富: category={f.category}, level={f.hierarchy_level}, confidence={f.level_confidence:.2f}")
        
        # 验证字段被丰富
        for f in enriched_fields:
            assert f.category is not None
            assert f.hierarchy_level is not None
    
    @pytest.mark.asyncio
    async def test_streaming_with_tableau_fields(self, reset_config, datasource_luid):
        """测试流式输出（使用 Tableau 字段）"""
        from src.platform.tableau.data_loader import TableauDataLoader
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        print("\n=== 测试流式输出 ===")
        
        # 1. 加载 Tableau 字段
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
        
        # 取 3 个不在种子数据中的字段（强制 LLM 推断）
        dimension_fields = [f for f in data_model.dimensions if f.caption not in ["年份", "月份", "季度", "国家", "省份", "城市"]][:3]
        
        if not dimension_fields:
            pytest.skip("没有找到需要 LLM 推断的字段")
        
        print(f"测试字段: {[f.caption for f in dimension_fields]}")
        
        # 2. 推断（带流式输出）
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        tokens_received = []
        
        async def on_token(token: str):
            tokens_received.append(token)
            print(token, end="", flush=True)
        
        print("\nLLM 输出:")
        result = await inference.infer(
            datasource_luid=f"{datasource_luid}-streaming",
            fields=dimension_fields,
            on_token=on_token,
        )
        
        print(f"\n\n收到 {len(tokens_received)} 个 token")
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == len(dimension_fields)
        assert len(tokens_received) > 0  # 应该收到流式 token
    
    @pytest.mark.asyncio
    async def test_rag_initialization_with_existing_index(self, reset_config, datasource_luid):
        """测试 RAG 初始化（加载已有索引）"""
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from pathlib import Path
        
        print("\n=== 测试 RAG 初始化（加载已有索引）===")
        
        # 检查索引是否存在
        index_path = Path("analytics_assistant/data/indexes/dimension_patterns")
        print(f"索引路径: {index_path}")
        print(f"索引存在: {index_path.exists()}")
        
        # 初始化推断器（会触发 RAG 初始化）
        inference = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=False,
            enable_self_learning=True,
        )
        
        # 手动触发 RAG 初始化
        inference._init_rag()
        
        print(f"RAG 初始化状态: {inference._rag_initialized}")
        print(f"RAG 检索器: {inference._rag_retriever is not None}")
        
        # 验证
        assert inference._rag_initialized is True
    
    @pytest.mark.asyncio
    async def test_pattern_store_operations(self, reset_config, datasource_luid):
        """测试模式存储操作"""
        from src.platform.tableau.data_loader import TableauDataLoader
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        
        print("\n=== 测试模式存储操作 ===")
        
        # 1. 加载 Tableau 字段
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
        
        # 取 5 个不在种子数据中的字段
        dimension_fields = [f for f in data_model.dimensions if f.caption not in ["年份", "月份", "季度", "国家", "省份", "城市"]][:5]
        
        if not dimension_fields:
            pytest.skip("没有找到需要 LLM 推断的字段")
        
        print(f"测试字段: {[f.caption for f in dimension_fields]}")
        
        # 2. 推断（启用自学习）
        inference = DimensionHierarchyInference(
            enable_rag=True,
            enable_cache=False,
            enable_self_learning=True,
        )
        
        result = await inference.infer(
            datasource_luid=f"{datasource_luid}-pattern-store",
            fields=dimension_fields,
        )
        
        # 3. 检查模式存储
        if inference._pattern_store:
            pattern_index = inference._pattern_store.get("_pattern_index") or []
            print(f"\n模式存储中的模式数量: {len(pattern_index)}")
            
            # 打印最近添加的模式
            print("\n最近添加的模式:")
            for pid in pattern_index[-5:]:
                pattern = inference._pattern_store.get(pid)
                if pattern:
                    print(f"  - {pattern['field_caption']}: {pattern['category']} (source={pattern.get('source')})")
        
        # 验证结果
        assert len(result.dimension_hierarchy) == len(dimension_fields)
    
    @pytest.mark.asyncio
    async def test_llm_retry_logic(self, reset_config, datasource_luid):
        """测试 LLM 重试逻辑"""
        from src.platform.tableau.data_loader import TableauDataLoader
        from src.agents.dimension_hierarchy.inference import DimensionHierarchyInference
        from src.core.schemas.data_model import Field
        
        print("\n=== 测试 LLM 重试逻辑 ===")
        
        # 使用一些复杂的字段名，可能导致 LLM 解析困难
        fields = [
            Field(name="complex_field_1", caption="复杂字段名称_包含特殊字符!@#", data_type="string", role="dimension"),
            Field(name="complex_field_2", caption="超长字段名称" * 10, data_type="string", role="dimension"),
        ]
        
        inference = DimensionHierarchyInference(
            enable_rag=False,
            enable_cache=False,
            enable_self_learning=False,
        )
        
        result = await inference.infer(
            datasource_luid=f"{datasource_luid}-retry",
            fields=fields,
        )
        
        print(f"推断结果: {len(result.dimension_hierarchy)} 个字段")
        for name, attrs in result.dimension_hierarchy.items():
            print(f"  - {name[:30]}...: {attrs.category.value}, confidence={attrs.level_confidence:.2f}")
        
        # 即使字段名复杂，也应该返回结果（可能是默认值）
        assert len(result.dimension_hierarchy) == len(fields)


if __name__ == "__main__":
    # 直接运行所有测试
    pytest.main([__file__, "-v", "-s"])
