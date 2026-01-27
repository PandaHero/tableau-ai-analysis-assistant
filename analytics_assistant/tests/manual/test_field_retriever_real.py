# -*- coding: utf-8 -*-
"""
FieldRetriever 真实环境测试

使用真实的 Tableau 数据源、Zhipu Embedding 和维度层级推断测试。

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    python tests/manual/test_field_retriever_real.py
    
    # 只测试关键词提取（不需要 Tableau 连接）
    python tests/manual/test_field_retriever_real.py keywords
"""

import asyncio
import logging
import sys
from pathlib import Path
from typing import Dict, List

# 添加项目根目录到 path
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s"
)
logger = logging.getLogger(__name__)


# Tableau 配置（与其他测试保持一致）
TABLEAU_CONFIG = {
    "domain": "https://cpse.cpgroup.cn:11080",
    "site": "ZF",
    "api_version": "3.24",
    "jwt": {
        "client_id": "5d50aad9-f6ea-4ece-b76e-155e9d7b3750",
        "secret_id": "e3095bfe-a831-4641-ab78-59f40073ab75",
        "secret": "1em+PLubDGMtA/yXI1LXHgt2q6u+9PyryC4KQeOa308=",
        "user": "tableauAdmin",
    },
    "datasource_name": "正大益生业绩总览数据 (IMPALA)",
}


async def test_with_real_tableau():
    """使用真实 Tableau 数据源测试 FieldRetriever"""
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.auth import (
        _jwt_authenticate_async,
        TableauAuthContext,
        clear_auth_cache,
    )
    from analytics_assistant.src.agents.dimension_hierarchy import DimensionHierarchyInference
    from analytics_assistant.src.agents.semantic_parser.components.field_retriever import (
        FieldRetriever,
        get_category_keywords,
        extract_categories_by_rules,
    )
    
    clear_auth_cache()
    config = TABLEAU_CONFIG
    
    print("\n" + "=" * 60)
    print("FieldRetriever 真实环境测试")
    print("=" * 60)
    print(f"数据源: {config['datasource_name']}")
    
    # 1. 加载配置
    print("\n[1] 加载配置...")
    from analytics_assistant.src.infra.config import get_config
    app_config = get_config()
    print(f"  - field_retriever 配置: {app_config.config.get('field_retriever', {})}")

    # 2. JWT 认证
    print("\n[2] JWT 认证...")
    response = await _jwt_authenticate_async(
        domain=config["domain"],
        site=config["site"],
        api_version=config["api_version"],
        user=config["jwt"]["user"],
        client_id=config["jwt"]["client_id"],
        secret_id=config["jwt"]["secret_id"],
        secret=config["jwt"]["secret"],
        scopes=["tableau:content:read"],
    )
    api_key = response.get("credentials", {}).get("token")
    auth = TableauAuthContext(api_key=api_key, site=config["site"], domain=config["domain"])
    print("  - 认证成功!")
    
    # 3. 加载数据模型
    print("\n[3] 加载数据模型...")
    client = VizQLClient(base_url=config["domain"])
    
    async with TableauDataLoader(client=client) as loader:
        data_model = await loader.load_data_model(
            datasource_name=config["datasource_name"],
            auth=auth,
        )
    
    fields = data_model.fields
    dimensions = data_model.dimensions
    measures = data_model.measures
    visible_dims = [f for f in dimensions if not f.hidden]
    
    print(f"  - 字段总数: {len(fields)}")
    print(f"  - 维度数: {len(dimensions)} (可见: {len(visible_dims)})")
    print(f"  - 度量数: {len(measures)}")
    
    # 打印部分字段
    print("\n  - 部分字段示例:")
    for i, f in enumerate(fields[:10]):
        role = getattr(f, 'role', 'unknown')
        caption = getattr(f, 'caption', getattr(f, 'name', ''))
        print(f"    {i+1}. {caption} ({role})")

    # 4. 获取维度层级推断结果
    print("\n[4] 获取维度层级推断结果...")
    inference = DimensionHierarchyInference()
    
    # 使用 skip_cache=True 强制重新推断，以获取父子关系
    hierarchy_result = await inference.infer(
        datasource_luid=data_model.datasource_id,
        fields=visible_dims,
        skip_cache=True,  # 强制重新推断以获取父子关系
    )
    
    dimension_hierarchy = None
    if hierarchy_result and hasattr(hierarchy_result, 'dimension_hierarchy'):
        dimension_hierarchy = hierarchy_result.dimension_hierarchy
        print(f"  - 获取到 {len(dimension_hierarchy)} 个维度的层级信息")
        
        # 按类别统计
        by_category = {}
        for name, attrs in dimension_hierarchy.items():
            cat = attrs.category.value if hasattr(attrs.category, 'value') else str(attrs.category)
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append(name)
        
        print("\n  - 按类别统计:")
        for cat, names in sorted(by_category.items()):
            print(f"    {cat}: {len(names)} 个")
    else:
        print("  - 未获取到层级信息")

    # 5. 创建 FieldRetriever（使用真实的 CascadeRetriever）
    print("\n[5] 创建 FieldRetriever...")
    
    # 创建真实的 CascadeRetriever
    from analytics_assistant.src.infra.rag.retriever import RetrieverFactory, RetrievalConfig
    
    retrieval_config = RetrievalConfig(top_k=10)
    cascade_retriever = RetrieverFactory.create_cascade_retriever(
        fields=fields,
        config=retrieval_config,
        collection_name=f"field_retriever_test_{data_model.datasource_id[:8]}",
    )
    print(f"  - 创建 CascadeRetriever 成功，索引 {len(fields)} 个字段")
    
    retriever = FieldRetriever(cascade_retriever=cascade_retriever)
    
    print(f"  - full_schema_threshold: {retriever.full_schema_threshold}")
    print(f"  - min_rule_match_dimensions: {retriever.min_rule_match_dimensions}")
    print(f"  - default_top_k: {retriever.default_top_k}")
    
    # 6. 测试类别关键词提取
    print("\n[6] 测试类别关键词提取...")
    category_keywords = get_category_keywords()
    print(f"  - 类别数: {len(category_keywords)}")
    for cat, kws in category_keywords.items():
        print(f"    {cat}: {len(kws)} 个关键词")
    
    # 7. 测试规则匹配
    print("\n[7] 测试规则匹配...")
    test_questions = [
        "上个月各地区的销售额",
        "今年各产品类别的利润",
        "各客户的订单数量",
        "按部门统计员工人数",
        "北京市的销售情况",
    ]
    
    for q in test_questions:
        matched = extract_categories_by_rules(q)
        print(f"  - '{q}' → 匹配类别: {matched}")
    
    # 8. 测试检索策略
    print("\n[8] 测试检索策略...")
    
    # 判断使用哪种模式
    if len(fields) <= retriever.full_schema_threshold:
        print(f"  - 字段数 {len(fields)} <= {retriever.full_schema_threshold}，使用 L0 全量模式")
    else:
        print(f"  - 字段数 {len(fields)} > {retriever.full_schema_threshold}，使用 L1/L2 模式")
    
    # 9. 测试检索
    print("\n[9] 测试检索...")
    test_cases = [
        ("上个月各地区的销售额", ["time", "geography"]),
        ("今年各产品类别的利润", ["time", "product"]),
        ("各客户的订单数量", ["customer"]),
    ]
    
    for question, expected_categories in test_cases:
        print(f"\n  问题: '{question}'")
        print(f"  期望类别: {expected_categories}")
        
        candidates = await retriever.retrieve(
            question=question,
            data_model=data_model,
            dimension_hierarchy=dimension_hierarchy,
        )
        
        # 统计结果
        dim_candidates = [c for c in candidates if c.field_type == "dimension"]
        measure_candidates = [c for c in candidates if c.field_type == "measure"]
        
        print(f"  返回: {len(candidates)} 个字段 (维度={len(dim_candidates)}, 度量={len(measure_candidates)})")
        
        # 显示维度字段
        if dim_candidates:
            print("  维度字段:")
            for c in dim_candidates[:5]:
                print(f"    - {c.field_caption} ({c.field_name}): source={c.source}, category={c.hierarchy_category}")
            if len(dim_candidates) > 5:
                print(f"    ... 还有 {len(dim_candidates) - 5} 个")
        
        # 显示度量字段数量
        if measure_candidates:
            print(f"  度量字段: {len(measure_candidates)} 个 (规则/embedding 匹配)")
    
    # 10. 测试层级扩展
    print("\n[10] 测试层级扩展...")
    if dimension_hierarchy:
        # 先打印一些维度的详细信息，看看数据结构
        print("  - 检查维度层级数据结构:")
        
        # 按类别分组统计层级分布
        by_category_level: Dict[str, Dict[int, List[str]]] = {}
        for name, attrs in dimension_hierarchy.items():
            cat = attrs.category.value
            level = attrs.level
            if cat not in by_category_level:
                by_category_level[cat] = {}
            if level not in by_category_level[cat]:
                by_category_level[cat][level] = []
            by_category_level[cat][level].append(name)
        
        print("  - 按类别和层级分布:")
        for cat, levels in sorted(by_category_level.items()):
            print(f"    {cat}:")
            for level, names in sorted(levels.items()):
                print(f"      Level {level}: {len(names)} 个 - {names[:3]}{'...' if len(names) > 3 else ''}")
        
        # 找一个有父/子维度的字段
        found = False
        for name, attrs in dimension_hierarchy.items():
            parent = getattr(attrs, 'parent_dimension', None)
            child = getattr(attrs, 'child_dimension', None)
            if parent or child:
                print(f"  - 字段 '{name}' 有层级关系:")
                print(f"    parent: {parent}")
                print(f"    child: {child}")
                
                # 构造一个包含该字段的问题
                caption = None
                for f in fields:
                    if getattr(f, 'name', '') == name:
                        caption = getattr(f, 'caption', name)
                        break
                
                if caption:
                    question = f"按{caption}统计销售额"
                    print(f"  - 测试问题: '{question}'")
                    
                    candidates = await retriever.retrieve(
                        question=question,
                        data_model=data_model,
                        dimension_hierarchy=dimension_hierarchy,
                    )
                    
                    # 检查是否包含父/子维度
                    candidate_names = {c.field_name for c in candidates}
                    dim_names = [c.field_name for c in candidates if c.field_type == "dimension"]
                    print(f"  - 返回维度: {dim_names}")
                    
                    if parent and parent in candidate_names:
                        print(f"  - ✓ 包含父维度 '{parent}'")
                    if child and child in candidate_names:
                        print(f"  - ✓ 包含子维度 '{child}'")
                    
                    found = True
                    break
        
        if not found:
            print("  - 未找到有层级关系的字段")
    else:
        print("  - 无层级信息，跳过层级扩展测试")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


async def test_category_keywords_from_seed():
    """测试从 SEED_PATTERNS 提取类别关键词"""
    
    print("\n" + "=" * 60)
    print("测试从 SEED_PATTERNS 提取类别关键词")
    print("=" * 60)
    
    from analytics_assistant.src.agents.semantic_parser.components.field_retriever import (
        get_category_keywords,
        _build_category_keywords,
    )
    from analytics_assistant.src.agents.dimension_hierarchy.seed_data import SEED_PATTERNS
    
    # 1. 检查 SEED_PATTERNS 结构
    print("\n[1] SEED_PATTERNS 结构...")
    print(f"  - 总数: {len(SEED_PATTERNS)}")
    
    categories = {}
    for p in SEED_PATTERNS:
        cat = p.get("category", "unknown")
        if cat not in categories:
            categories[cat] = []
        categories[cat].append(p.get("field_caption", ""))
    
    print("  - 按类别统计:")
    for cat, captions in categories.items():
        print(f"    {cat}: {len(captions)} 个")
        print(f"      示例: {captions[:3]}")
    
    # 2. 测试关键词构建
    print("\n[2] 构建类别关键词...")
    keywords = _build_category_keywords()
    
    for cat, kws in keywords.items():
        print(f"\n  {cat}:")
        # 分离 seed 来源和扩展来源
        seed_kws = set()
        for p in SEED_PATTERNS:
            if p.get("category") == cat:
                seed_kws.add(p.get("field_caption", "").lower())
        
        extended_kws = kws - seed_kws
        print(f"    - 来自 SEED: {len(seed_kws)} 个")
        print(f"    - 扩展关键词: {len(extended_kws)} 个")
        print(f"    - 总计: {len(kws)} 个")
    
    print("\n" + "=" * 60)
    print("测试完成!")
    print("=" * 60)


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "keywords":
        # 只测试关键词提取
        asyncio.run(test_category_keywords_from_seed())
    else:
        # 完整测试
        asyncio.run(test_with_real_tableau())
