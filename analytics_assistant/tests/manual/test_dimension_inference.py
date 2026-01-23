# -*- coding: utf-8 -*-
"""
测试维度层级推断

使用方式：
    python -m analytics_assistant.tests.manual.test_dimension_inference
"""
import asyncio
import sys
from pathlib import Path

project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))


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


async def test_dimension_inference(skip_cache: bool = False):
    """测试维度层级推断"""
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.auth import (
        _jwt_authenticate_async,
        TableauAuthContext,
        clear_auth_cache,
    )
    from analytics_assistant.src.agents.dimension_hierarchy import DimensionHierarchyInference
    
    clear_auth_cache()
    
    config = TABLEAU_CONFIG
    
    print("=" * 60)
    print("测试维度层级推断")
    print("=" * 60)
    print(f"数据源: {config['datasource_name']}")
    print(f"跳过缓存: {skip_cache}")
    print()
    
    # 1. 认证
    print("1. JWT 认证...")
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
    print("   认证成功!")
    
    # 2. 加载数据模型
    print("\n2. 加载数据模型...")
    client = VizQLClient(base_url=config["domain"])
    
    async with TableauDataLoader(client=client) as loader:
        data_model = await loader.load_data_model(
            datasource_name=config["datasource_name"],
            auth=auth,
        )
        print(f"   维度: {len(data_model.dimensions)}, 度量: {len(data_model.measures)}")
    
    # 3. 过滤可见维度
    visible_dims = [f for f in data_model.dimensions if not f.hidden]
    print(f"\n3. 可见维度: {len(visible_dims)} 个")
    
    # 4. 推断
    print("\n4. 执行维度层级推断...")
    print("-" * 60)
    
    inference = DimensionHierarchyInference()
    
    async for token in inference.infer(
        datasource_luid=data_model.datasource_id,
        fields=visible_dims,
        skip_cache=skip_cache,
    ):
        print(token, end="", flush=True)
    
    print("\n" + "-" * 60)
    
    result = inference.get_result()
    if not result:
        print("推断失败")
        return
    
    # 5. 更新 Field 对象
    print("\n5. 更新字段元数据...")
    inference.enrich_fields(visible_dims)
    enriched = sum(1 for f in visible_dims if f.category is not None)
    print(f"   已更新 {enriched} 个字段")
    
    # 6. 打印结果
    print("\n" + "=" * 60)
    print("推断结果")
    print("=" * 60)
    
    # 按类别分组
    by_category = {}
    for name, attrs in result.dimension_hierarchy.items():
        cat = attrs.category.value
        if cat not in by_category:
            by_category[cat] = []
        by_category[cat].append((name, attrs))
    
    for cat, items in sorted(by_category.items()):
        print(f"\n【{cat.upper()}】{len(items)} 个")
        for name, attrs in items[:5]:
            print(f"  {name}: level={attrs.level}, {attrs.granularity}, conf={attrs.level_confidence:.2f}")
        if len(items) > 5:
            print(f"  ... 还有 {len(items) - 5} 个")
    
    # 7. 统计
    print("\n" + "=" * 60)
    print("统计")
    print("=" * 60)
    print(f"总字段数: {len(result.dimension_hierarchy)}")
    
    # 置信度分布
    confidences = [a.level_confidence for a in result.dimension_hierarchy.values()]
    high = sum(1 for c in confidences if c >= 0.85)
    mid = sum(1 for c in confidences if 0.7 <= c < 0.85)
    low = sum(1 for c in confidences if c < 0.7)
    print(f"置信度: 高={high}, 中={mid}, 低={low}")
    
    print("\n✓ 测试完成!")


if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--skip-cache", action="store_true")
    args = parser.parse_args()
    asyncio.run(test_dimension_inference(skip_cache=args.skip_cache))
