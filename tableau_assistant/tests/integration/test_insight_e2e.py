"""
Insight Agent End-to-End Test

完整的端到端测试，使用已完成的功能：
- 维度层级推断 (DimensionHierarchyAgent)
- 问题理解 (SemanticQueryAgent)
- 查询执行 (ExecuteNode)
- 洞察分析 (InsightAgent)

Requirements tested:
- R8.1: Progressive insight analysis
- R8.2: Strategy selection (direct/progressive/hybrid)
- R8.3: Semantic chunking (based on dimension_hierarchy)
- R8.4: Chunk analysis with context
- R8.5: Insight accumulation
- R8.6: Insight synthesis
"""

import asyncio
import sys
import os
from pathlib import Path

import pytest

# Add project root to path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

from dotenv import load_dotenv

# Load environment
env_path = project_root / ".env"
load_dotenv(env_path)


async def get_metadata_with_hierarchy(datasource_luid: str):
    """
    获取元数据和维度层级信息。
    
    使用已完成的 MetadataManager 和 DimensionHierarchyAgent。
    """
    from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient
    from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
    
    # 初始化 VizQL Client
    client = VizQLClient()
    await client.initialize()
    
    # 获取元数据（包含 dimension_hierarchy）
    metadata_manager = MetadataManager(client)
    metadata = await metadata_manager.get_metadata_async(datasource_luid)
    
    return {
        "metadata": metadata,
        "dimension_hierarchy": metadata.dimension_hierarchy,
        "fields": metadata.fields,
        "client": client,
    }


async def execute_query(client, datasource_luid: str, dimensions: list, measures: list):
    """
    执行查询获取数据。
    """
    # 构建查询
    fields = []
    for dim in dimensions:
        fields.append({"fieldCaption": dim})
    for measure in measures:
        fields.append({"fieldCaption": measure, "function": "SUM"})
    
    query = {"fields": fields}
    
    # 执行查询
    result = await client.query_datasource(datasource_luid, query)
    
    return result


@pytest.mark.asyncio
async def test_insight_e2e_with_dimension_hierarchy():
    """
    端到端测试：使用维度层级推断结果进行洞察分析。
    
    流程：
    1. 获取元数据和维度层级
    2. 选择维度和度量
    3. 执行查询
    4. 使用 InsightAgent 分析结果
    """
    print("\n" + "=" * 70)
    print("Insight Agent 端到端测试（使用维度层级）")
    print("=" * 70)
    
    # 获取环境变量
    datasource_luid = os.getenv("DATASOURCE_LUID")
    if not datasource_luid:
        pytest.skip("DATASOURCE_LUID not set in environment")
    
    from tableau_assistant.src.agents.insight import InsightAgent
    from tableau_assistant.src.components.insight import (
        AnalysisCoordinator,
        DataProfiler,
        SemanticChunker,
    )
    
    # Step 1: 获取元数据和维度层级
    print("\n" + "-" * 70)
    print("[Step 1] 获取元数据和维度层级")
    print("-" * 70)
    
    try:
        meta_info = await get_metadata_with_hierarchy(datasource_luid)
        metadata = meta_info["metadata"]
        dimension_hierarchy = meta_info["dimension_hierarchy"]
        fields = meta_info["fields"]
        client = meta_info["client"]
        
        print(f"  ✓ 获取元数据: {len(fields)} 个字段")
        print(f"  ✓ 维度层级: {len(dimension_hierarchy) if dimension_hierarchy else 0} 个维度")
        
        # 显示维度层级信息
        if dimension_hierarchy:
            print("\n  维度层级详情:")
            for name, attrs in list(dimension_hierarchy.items())[:8]:
                cat = attrs.get("category", "unknown") if isinstance(attrs, dict) else getattr(attrs, "category", "unknown")
                level = attrs.get("level", "?") if isinstance(attrs, dict) else getattr(attrs, "level", "?")
                print(f"    - {name}: category={cat}, level={level}")
    except Exception as e:
        pytest.skip(f"无法获取元数据: {e}")
    
    # Step 2: 选择维度和度量
    print("\n" + "-" * 70)
    print("[Step 2] 选择维度和度量")
    print("-" * 70)
    
    # 从字段中选择维度和度量
    dimensions = []
    measures = []
    
    for field in fields:
        if field.role == "dimension" and len(dimensions) < 3:
            dimensions.append(field.name)
        elif field.role == "measure" and len(measures) < 2:
            measures.append(field.name)
    
    if not dimensions or not measures:
        pytest.skip("没有找到合适的维度或度量")
    
    print(f"  ✓ 选择维度: {dimensions}")
    print(f"  ✓ 选择度量: {measures}")
    
    # Step 3: 执行查询
    print("\n" + "-" * 70)
    print("[Step 3] 执行查询")
    print("-" * 70)
    
    try:
        query_result = await execute_query(client, datasource_luid, dimensions, measures)
        data = query_result.get("data", [])
        
        print(f"  ✓ 查询成功: {len(data)} 行数据")
        
        if data:
            print(f"  ✓ 列: {list(data[0].keys())}")
    except Exception as e:
        pytest.skip(f"查询失败: {e}")
    
    if not data:
        pytest.skip("查询结果为空")
    
    # Step 4: 验证 DataProfiler 使用 dimension_hierarchy
    print("\n" + "-" * 70)
    print("[Step 4] DataProfiler 使用 dimension_hierarchy")
    print("-" * 70)
    
    profiler = DataProfiler(dimension_hierarchy=dimension_hierarchy)
    profile = profiler.profile(data)
    
    print(f"  ✓ 数据画像:")
    print(f"    - 行数: {profile.row_count}")
    print(f"    - 列数: {profile.column_count}")
    print(f"    - 密度: {profile.density:.2%}")
    print(f"    - 语义分组: {[(g.type, g.columns) for g in profile.semantic_groups]}")
    
    # Step 5: 验证 SemanticChunker 使用 dimension_hierarchy
    print("\n" + "-" * 70)
    print("[Step 5] SemanticChunker 使用 dimension_hierarchy")
    print("-" * 70)
    
    chunker = SemanticChunker(dimension_hierarchy=dimension_hierarchy)
    chunks = chunker.chunk(data, profile.semantic_groups)
    
    print(f"  ✓ 分块结果: {len(chunks)} 个块")
    for chunk in chunks[:5]:
        print(f"    - {chunk.chunk_name}: {chunk.row_count} 行")
    if len(chunks) > 5:
        print(f"    ... 还有 {len(chunks) - 5} 个块")
    
    # Step 6: 使用 InsightAgent 分析
    print("\n" + "-" * 70)
    print("[Step 6] InsightAgent 分析")
    print("-" * 70)
    
    agent = InsightAgent(dimension_hierarchy=dimension_hierarchy)
    
    context = {
        "question": f"分析 {', '.join(measures)} 在不同 {', '.join(dimensions)} 下的表现",
        "dimensions": [{"name": d} for d in dimensions],
        "measures": [{"name": m} for m in measures],
    }
    
    result = await agent.analyze(data, context)
    
    print(f"  ✓ 分析完成")
    print(f"    - 策略: {result.strategy_used}")
    print(f"    - 分析块数: {result.chunks_analyzed}")
    print(f"    - 总行数: {result.total_rows_analyzed}")
    print(f"    - 执行时间: {result.execution_time:.2f}s")
    print(f"    - 置信度: {result.confidence:.2f}")
    print(f"    - 总结: {result.summary}")
    
    # 显示洞察
    print(f"\n  发现 {len(result.findings)} 个洞察:")
    for i, finding in enumerate(result.findings):
        print(f"    [{i+1}] [{finding.type}] {finding.title}")
        print(f"        重要性: {finding.importance:.2f}")
        if finding.related_columns:
            print(f"        相关列: {finding.related_columns}")
    
    # 验证结果
    assert result.summary is not None, "应该有总结"
    assert result.strategy_used in ["direct", "progressive", "hybrid"], "策略应该是有效值"
    
    print("\n" + "=" * 70)
    print("✓ 端到端测试完成")
    print("=" * 70)


@pytest.mark.asyncio
async def test_insight_strategy_selection():
    """
    测试策略选择逻辑。
    """
    print("\n" + "=" * 70)
    print("策略选择测试")
    print("=" * 70)
    
    from tableau_assistant.src.components.insight import (
        AnalysisCoordinator,
        DataProfile,
        SemanticGroup,
    )
    
    coordinator = AnalysisCoordinator()
    
    # 测试不同数据规模的策略选择
    test_cases = [
        (50, "direct"),
        (99, "direct"),
        (100, "progressive"),
        (500, "progressive"),
        (999, "progressive"),
        (1000, "hybrid"),
        (5000, "hybrid"),
    ]
    
    for row_count, expected_strategy in test_cases:
        profile = DataProfile(
            row_count=row_count,
            column_count=5,
            density=1.0,
            statistics={},
            semantic_groups=[],
        )
        
        strategy = coordinator._select_strategy(profile)
        print(f"  {row_count} 行 → {strategy} (期望: {expected_strategy})")
        assert strategy == expected_strategy, f"策略选择错误: {row_count} 行应该是 {expected_strategy}"
    
    print("\n✓ 策略选择测试通过")


@pytest.mark.asyncio
async def test_insight_with_different_data_sizes():
    """
    测试不同数据规模下的洞察分析。
    """
    print("\n" + "=" * 70)
    print("不同数据规模测试")
    print("=" * 70)
    
    from tableau_assistant.src.components.insight import (
        AnalysisCoordinator,
        InsightResult,
    )
    
    # 生成测试数据
    def generate_test_data(size: int):
        import random
        categories = ["Technology", "Furniture", "Office Supplies"]
        regions = ["East", "West", "North", "South"]
        
        data = []
        for i in range(size):
            data.append({
                "Category": random.choice(categories),
                "Region": random.choice(regions),
                "Sales": random.randint(100, 10000),
                "Profit": random.randint(-500, 2000),
            })
        return data
    
    # 测试不同规模
    test_sizes = [50, 150, 500]  # direct, progressive, progressive
    
    for size in test_sizes:
        print(f"\n  测试 {size} 行数据:")
        
        data = generate_test_data(size)
        
        # 模拟 dimension_hierarchy
        dimension_hierarchy = {
            "Category": {"category": "product", "level": 2},
            "Region": {"category": "geographic", "level": 2},
        }
        
        coordinator = AnalysisCoordinator(dimension_hierarchy=dimension_hierarchy)
        
        context = {
            "question": "分析销售和利润情况",
            "dimensions": [{"name": "Category"}, {"name": "Region"}],
            "measures": [{"name": "Sales"}, {"name": "Profit"}],
        }
        
        result = await coordinator.analyze(data, context)
        
        print(f"    - 策略: {result.strategy_used}")
        print(f"    - 洞察数: {len(result.findings)}")
        print(f"    - 执行时间: {result.execution_time:.2f}s")
        
        assert isinstance(result, InsightResult), "应该返回 InsightResult"
        assert result.strategy_used in ["direct", "progressive", "hybrid"], "策略应该有效"
    
    print("\n✓ 不同数据规模测试完成")


if __name__ == "__main__":
    # 运行测试
    asyncio.run(test_insight_e2e_with_dimension_hierarchy())
    asyncio.run(test_insight_strategy_selection())
    asyncio.run(test_insight_with_different_data_sizes())
