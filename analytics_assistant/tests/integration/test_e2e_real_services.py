# -*- coding: utf-8 -*-
"""
End-to-End Integration Test with Real Services

完整集成测试：维度层级 → 字段映射 → 语义理解
使用真实 Tableau 服务和 DeepSeek LLM

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    pytest tests/integration/test_e2e_real_services.py -v --tb=short -s

测试流程：
1. 连接真实 Tableau 数据源（正大益生）
2. 加载真实 DataModel
3. 运行 DimensionHierarchyInference（真实 LLM）
4. 运行 FieldMapperNode（真实 RAG + LLM）
5. 运行 SemanticUnderstanding（真实 LLM + 流式输出）
"""

import asyncio
import logging
import sys
from datetime import date
from typing import Any, Dict, List, Optional

import pytest

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
    handlers=[logging.StreamHandler(sys.stdout)],
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 真实服务辅助函数
# ═══════════════════════════════════════════════════════════════════════════

async def get_real_tableau_components():
    """获取真实的 Tableau 组件
    
    Returns:
        tuple: (client, adapter, auth, datasource_luid, data_model)
    """
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    
    try:
        # 获取真实认证
        auth = await get_tableau_auth_async()
        
        # 创建真实组件
        client = VizQLClient()
        adapter = TableauAdapter(vizql_client=client)
        
        # 获取数据源 LUID
        datasource_name = "正大益生"
        datasource_luid = await client.get_datasource_luid_by_name(
            datasource_name=datasource_name,
            api_key=auth.api_key,
        )
        
        if not datasource_luid:
            logger.warning(f"未找到数据源: {datasource_name}")
            return None, None, None, None, None
        
        logger.info(f"数据源 LUID: {datasource_luid}")
        
        # 加载真实数据模型
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth,
        )
        
        logger.info(f"数据模型加载完成: {len(data_model.fields)} 个字段")
        logger.info(f"  - 维度: {len(data_model.dimensions)} 个")
        logger.info(f"  - 度量: {len(data_model.measures)} 个")
        
        return client, adapter, auth, datasource_luid, data_model
    except Exception as e:
        logger.error(f"获取 Tableau 组件失败: {e}")
        return None, None, None, None, None


# ═══════════════════════════════════════════════════════════════════════════
# 流式输出回调
# ═══════════════════════════════════════════════════════════════════════════

class StreamingCallbacks:
    """流式输出回调处理器"""
    
    def __init__(self, prefix: str = ""):
        self.prefix = prefix
        self.tokens: List[str] = []
        self.thinking_content: str = ""
        self.partial_results: List[Dict[str, Any]] = []
    
    async def on_token(self, token: str) -> None:
        """Token 回调"""
        self.tokens.append(token)
        print(token, end="", flush=True)
    
    async def on_thinking(self, thinking: str) -> None:
        """Thinking 回调（R1 模型）"""
        self.thinking_content = thinking
        if thinking:
            print(f"\n{self.prefix}[Thinking] {thinking[:100]}...", flush=True)
    
    async def on_partial(self, partial: Dict[str, Any]) -> None:
        """部分结果回调"""
        self.partial_results.append(partial)
    
    def get_full_output(self) -> str:
        """获取完整输出"""
        return "".join(self.tokens)


# ═══════════════════════════════════════════════════════════════════════════
# 测试类
# ═══════════════════════════════════════════════════════════════════════════

class TestEndToEndRealServices:
    """端到端集成测试：使用真实服务"""
    
    @pytest.mark.asyncio
    async def test_dimension_hierarchy_inference(self):
        """测试维度层级推断（真实 LLM）"""
        from analytics_assistant.src.agents.dimension_hierarchy.inference import (
            DimensionHierarchyInference,
        )
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("维度层级推断测试")
            print("=" * 60)
            
            # 创建推断器
            inference = DimensionHierarchyInference(
                enable_rag=True,
                enable_cache=True,
                enable_self_learning=True,
            )
            
            # 获取维度字段
            dimension_fields = data_model.dimensions[:10]  # 限制数量避免过长
            
            print(f"\n待推断字段 ({len(dimension_fields)} 个):")
            for f in dimension_fields:
                print(f"  - {f.name} ({f.data_type})")
            
            # 流式输出回调
            callbacks = StreamingCallbacks(prefix="[DimHierarchy] ")
            
            print("\n开始推断...")
            print("-" * 40)
            
            # 执行推断
            result = await inference.infer(
                datasource_luid=datasource_luid,
                fields=dimension_fields,
                on_token=callbacks.on_token,
            )
            
            print("\n" + "-" * 40)
            print(f"\n推断结果 ({len(result.dimension_hierarchy)} 个字段):")
            
            for name, attrs in result.dimension_hierarchy.items():
                print(f"\n  {name}:")
                print(f"    - 类别: {attrs.category.value}")
                print(f"    - 详细类别: {attrs.category_detail}")
                print(f"    - 层级: {attrs.level}")
                print(f"    - 粒度: {attrs.granularity}")
                print(f"    - 置信度: {attrs.level_confidence:.2f}")
                if attrs.parent_dimension:
                    print(f"    - 父维度: {attrs.parent_dimension}")
                if attrs.child_dimension:
                    print(f"    - 子维度: {attrs.child_dimension}")
            
            # 验证结果
            assert len(result.dimension_hierarchy) > 0
            
            # 验证每个结果都有必要字段
            for name, attrs in result.dimension_hierarchy.items():
                assert attrs.category is not None
                assert attrs.level >= 1
                assert 0 <= attrs.level_confidence <= 1
            
            print("\n✅ 维度层级推断测试通过")
            
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_field_mapper_node(self):
        """测试字段映射（真实 RAG + LLM）"""
        from analytics_assistant.src.agents.field_mapper.node import FieldMapperNode
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("字段映射测试")
            print("=" * 60)
            
            # 创建 FieldMapperNode
            mapper = FieldMapperNode()
            
            # 加载元数据
            field_count = mapper.load_metadata(
                fields=data_model.fields,
                datasource_luid=datasource_luid,
            )
            
            print(f"\n已加载 {field_count} 个字段到索引")
            
            # 测试业务术语
            test_terms = [
                "销售额",
                "地区",
                "客户",
                "产品",
                "日期",
            ]
            
            print(f"\n测试术语: {test_terms}")
            print("-" * 40)
            
            # 批量映射
            results = await mapper.map_fields_batch(
                terms=test_terms,
                datasource_luid=datasource_luid,
                context="查询各地区的销售数据",
            )
            
            print("\n映射结果:")
            for term, mapping in results.items():
                print(f"\n  {term}:")
                print(f"    - 技术字段: {mapping.technical_field}")
                print(f"    - 置信度: {mapping.confidence:.2f}")
                print(f"    - 来源: {mapping.mapping_source}")
                if mapping.reasoning:
                    print(f"    - 推理: {mapping.reasoning[:50]}...")
            
            # 获取统计信息
            stats = mapper.get_stats()
            print(f"\n统计信息:")
            print(f"  - 总映射数: {stats['total_mappings']}")
            print(f"  - 缓存命中: {stats['cache_hits']}")
            print(f"  - 快速路径: {stats['fast_path_hits']}")
            print(f"  - LLM 回退: {stats['llm_fallback_count']}")
            
            # 验证结果
            assert len(results) == len(test_terms)
            
            print("\n✅ 字段映射测试通过")
            
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_semantic_understanding(self):
        """测试语义理解（真实 LLM + 流式输出）"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("语义理解测试")
            print("=" * 60)
            
            # 创建 SemanticUnderstanding
            understanding = SemanticUnderstanding()
            
            # 构建字段候选
            field_candidates = []
            for f in data_model.fields[:20]:  # 限制数量
                field_candidates.append(FieldCandidate(
                    field_name=f.name,
                    field_caption=f.caption or f.name,
                    role=f.role,
                    data_type=f.data_type,
                    score=0.8,
                ))
            
            print(f"\n字段候选 ({len(field_candidates)} 个):")
            for fc in field_candidates[:5]:
                print(f"  - {fc.field_caption} ({fc.role})")
            print("  ...")
            
            # 测试问题
            test_question = "上个月各地区的销售额"
            
            print(f"\n测试问题: {test_question}")
            print("-" * 40)
            
            # 流式输出回调
            callbacks = StreamingCallbacks(prefix="[Semantic] ")
            
            print("\n开始语义理解...")
            print("-" * 40)
            
            # 执行语义理解
            result = await understanding.understand(
                question=test_question,
                field_candidates=field_candidates,
                current_date=date.today(),
                timezone="Asia/Shanghai",
                fiscal_year_start_month=1,
                on_token=callbacks.on_token,
                on_thinking=callbacks.on_thinking,
            )
            
            print("\n" + "-" * 40)
            print("\n语义理解结果:")
            print(f"  - 重述问题: {result.restated_question}")
            print(f"  - 需要澄清: {result.needs_clarification}")
            print(f"  - Query ID: {result.query_id}")
            
            if result.what:
                print(f"\n  What (度量):")
                for m in result.what.measures:
                    print(f"    - {m.field_name} ({m.aggregation})")
            
            if result.where:
                print(f"\n  Where (维度):")
                for d in result.where.dimensions:
                    print(f"    - {d.field_name}")
                
                if result.where.filters:
                    print(f"\n  Filters:")
                    for f in result.where.filters:
                        print(f"    - {f.field_name}: {getattr(f, 'values', getattr(f, 'range', 'N/A'))}")
            
            if result.self_check:
                print(f"\n  自检结果:")
                print(f"    - 字段映射置信度: {result.self_check.field_mapping_confidence:.2f}")
                print(f"    - 时间范围置信度: {result.self_check.time_range_confidence:.2f}")
                print(f"    - 计算逻辑置信度: {result.self_check.computation_confidence:.2f}")
                print(f"    - 整体置信度: {result.self_check.overall_confidence:.2f}")
            
            # 验证结果
            assert result.restated_question is not None
            assert result.self_check is not None
            
            print("\n✅ 语义理解测试通过")
            
        finally:
            if client:
                await client.close()


    @pytest.mark.asyncio
    async def test_full_e2e_flow(self):
        """完整端到端流程测试：维度层级 → 字段映射 → 语义理解"""
        from analytics_assistant.src.agents.dimension_hierarchy.inference import (
            DimensionHierarchyInference,
        )
        from analytics_assistant.src.agents.field_mapper.node import FieldMapperNode
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("完整端到端流程测试")
            print("=" * 60)
            
            # ─────────────────────────────────────────────────────────
            # 阶段 1: 维度层级推断
            # ─────────────────────────────────────────────────────────
            print("\n" + "─" * 40)
            print("阶段 1: 维度层级推断")
            print("─" * 40)
            
            dim_inference = DimensionHierarchyInference(
                enable_rag=True,
                enable_cache=True,
                enable_self_learning=True,
            )
            
            # 只推断维度字段
            dimension_fields = data_model.dimensions[:15]
            
            dim_callbacks = StreamingCallbacks(prefix="[DimHierarchy] ")
            
            print(f"\n推断 {len(dimension_fields)} 个维度字段...")
            
            dim_result = await dim_inference.infer(
                datasource_luid=datasource_luid,
                fields=dimension_fields,
                on_token=dim_callbacks.on_token,
            )
            
            # 使用推断结果丰富字段
            enriched_fields = dim_inference.enrich_fields(dimension_fields)
            
            print(f"\n维度层级推断完成: {len(dim_result.dimension_hierarchy)} 个字段")
            
            # 打印部分结果
            for name, attrs in list(dim_result.dimension_hierarchy.items())[:3]:
                print(f"  - {name}: {attrs.category.value} (L{attrs.level}, {attrs.level_confidence:.2f})")
            
            # ─────────────────────────────────────────────────────────
            # 阶段 2: 字段映射
            # ─────────────────────────────────────────────────────────
            print("\n" + "─" * 40)
            print("阶段 2: 字段映射")
            print("─" * 40)
            
            mapper = FieldMapperNode()
            
            # 加载所有字段（包含丰富后的维度字段）
            all_fields = list(enriched_fields) + list(data_model.measures)
            mapper.load_metadata(
                fields=all_fields,
                datasource_luid=datasource_luid,
            )
            
            # 测试业务术语映射
            business_terms = ["销售额", "地区", "客户", "日期", "产品"]
            
            print(f"\n映射业务术语: {business_terms}")
            
            mapping_results = await mapper.map_fields_batch(
                terms=business_terms,
                datasource_luid=datasource_luid,
                context="查询各地区的销售数据",
            )
            
            print("\n映射结果:")
            for term, mapping in mapping_results.items():
                print(f"  - {term} → {mapping.technical_field} ({mapping.confidence:.2f})")
            
            # ─────────────────────────────────────────────────────────
            # 阶段 3: 语义理解
            # ─────────────────────────────────────────────────────────
            print("\n" + "─" * 40)
            print("阶段 3: 语义理解")
            print("─" * 40)
            
            understanding = SemanticUnderstanding()
            
            # 构建字段候选（使用映射结果和丰富后的字段）
            field_candidates = []
            for f in all_fields[:25]:
                # 获取维度层级信息
                dim_attrs = dim_result.dimension_hierarchy.get(f.caption or f.name)
                
                field_candidates.append(FieldCandidate(
                    field_name=f.name,
                    field_caption=f.caption or f.name,
                    role=f.role,
                    data_type=f.data_type,
                    score=0.8,
                    category=dim_attrs.category.value if dim_attrs else None,
                    level=dim_attrs.level if dim_attrs else None,
                    granularity=dim_attrs.granularity if dim_attrs else None,
                ))
            
            # 测试问题
            test_questions = [
                "上个月各地区的销售额",
                "本季度销售额同比增长",
                "各产品类别的销售占比",
            ]
            
            for question in test_questions:
                print(f"\n问题: {question}")
                print("-" * 30)
                
                sem_callbacks = StreamingCallbacks(prefix="[Semantic] ")
                
                result = await understanding.understand(
                    question=question,
                    field_candidates=field_candidates,
                    current_date=date.today(),
                    timezone="Asia/Shanghai",
                    fiscal_year_start_month=1,
                    on_token=sem_callbacks.on_token,
                    on_thinking=sem_callbacks.on_thinking,
                )
                
                print(f"\n重述: {result.restated_question}")
                print(f"置信度: {result.self_check.overall_confidence:.2f}")
                
                if result.what and result.what.measures:
                    measures = [m.field_name for m in result.what.measures]
                    print(f"度量: {measures}")
                
                if result.where and result.where.dimensions:
                    dimensions = [d.field_name for d in result.where.dimensions]
                    print(f"维度: {dimensions}")
                
                if result.how_type:
                    print(f"计算类型: {result.how_type.value}")
                    if result.computations:
                        for comp in result.computations:
                            print(f"计算公式: {comp.formula}")
            
            # ─────────────────────────────────────────────────────────
            # 验证
            # ─────────────────────────────────────────────────────────
            print("\n" + "─" * 40)
            print("验证结果")
            print("─" * 40)
            
            # 验证维度层级
            assert len(dim_result.dimension_hierarchy) > 0
            print("✅ 维度层级推断成功")
            
            # 验证字段映射
            assert len(mapping_results) == len(business_terms)
            print("✅ 字段映射成功")
            
            # 验证语义理解
            assert result.restated_question is not None
            print("✅ 语义理解成功")
            
            print("\n" + "=" * 60)
            print("✅ 完整端到端流程测试通过")
            print("=" * 60)
            
        finally:
            if client:
                await client.close()
    
    @pytest.mark.asyncio
    async def test_streaming_output_display(self):
        """测试流式输出展示效果"""
        from analytics_assistant.src.agents.semantic_parser.components.semantic_understanding import (
            SemanticUnderstanding,
        )
        from analytics_assistant.src.agents.semantic_parser.schemas.intermediate import (
            FieldCandidate,
        )
        
        client, adapter, auth, datasource_luid, data_model = await get_real_tableau_components()
        
        if data_model is None:
            pytest.skip("无法连接 Tableau 服务或未找到数据源")
        
        try:
            print("\n" + "=" * 60)
            print("流式输出展示测试")
            print("=" * 60)
            
            understanding = SemanticUnderstanding()
            
            # 构建字段候选
            field_candidates = []
            for f in data_model.fields[:20]:
                field_candidates.append(FieldCandidate(
                    field_name=f.name,
                    field_caption=f.caption or f.name,
                    role=f.role,
                    data_type=f.data_type,
                    score=0.8,
                ))
            
            question = "计算各地区上个月的销售额环比增长率"
            
            print(f"\n问题: {question}")
            print("\n" + "-" * 40)
            print("流式输出:")
            print("-" * 40 + "\n")
            
            # 统计信息
            token_count = 0
            
            async def count_tokens(token: str) -> None:
                nonlocal token_count
                token_count += 1
                print(token, end="", flush=True)
            
            result = await understanding.understand(
                question=question,
                field_candidates=field_candidates,
                current_date=date.today(),
                on_token=count_tokens,
            )
            
            print("\n\n" + "-" * 40)
            print(f"Token 数量: {token_count}")
            print(f"重述问题: {result.restated_question}")
            print(f"整体置信度: {result.self_check.overall_confidence:.2f}")
            
            if result.how_type:
                print(f"计算类型: {result.how_type.value}")
                if result.computations:
                    for comp in result.computations:
                        print(f"计算公式: {comp.formula}")
            
            print("\n✅ 流式输出展示测试通过")
            
        finally:
            if client:
                await client.close()


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    pytest.main([__file__, "-v", "--tb=short", "-s"])
