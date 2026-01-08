# -*- coding: utf-8 -*-
"""
维度层级推断真实环境集成测试

使用真实的 Tableau 环境、真实的 Embedding API 和 LLM API 进行测试。
参考 test_semantic_parser_subgraph.py 的测试模式。

运行方式:
    python -m tableau_assistant.tests.agents.dimension_hierarchy.test_real_integration

或者使用 pytest:
    pytest tableau_assistant/tests/agents/dimension_hierarchy/test_real_integration.py -v -s

Requirements: 1.1, 1.2, 1.3, 1.4
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# ═══════════════════════════════════════════════════════════════════════════
# 日志和输出配置
# ═══════════════════════════════════════════════════════════════════════════

# 创建输出目录
OUTPUT_DIR = Path(__file__).parent.parent.parent / "test_outputs"
OUTPUT_DIR.mkdir(exist_ok=True)

# 生成带时间戳的文件名
TIMESTAMP = datetime.now().strftime("%Y%m%d_%H%M%S")
LOG_FILE = OUTPUT_DIR / f"dimension_hierarchy_test_{TIMESTAMP}.log"

# 配置日志 - 同时输出到控制台和文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),
        logging.FileHandler(LOG_FILE, encoding='utf-8'),
    ]
)
logger = logging.getLogger(__name__)

logger.info(f"日志文件: {LOG_FILE}")


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_tableau_config() -> Dict[str, str]:
    """从环境变量获取 Tableau 配置"""
    domain = os.getenv("TABLEAU_CLOUD_DOMAIN", os.getenv("TABLEAU_DOMAIN", ""))
    site = os.getenv("TABLEAU_CLOUD_SITE", os.getenv("TABLEAU_SITE", ""))
    
    return {
        "domain": domain,
        "site": site,
        "datasource_luid": os.getenv("DATASOURCE_LUID", ""),
        "datasource_name": os.getenv("DATASOURCE_NAME", os.getenv("datasource_name", "Superstore Datasource")),
        "pat_name": os.getenv("TABLEAU_CLOUD_PAT_NAME", os.getenv("TABLEAU_PAT_NAME", "")),
        "pat_secret": os.getenv("TABLEAU_CLOUD_PAT_SECRET", os.getenv("TABLEAU_PAT_SECRET", "")),
    }


async def get_tableau_auth_context():
    """获取 Tableau 认证上下文"""
    from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
    
    auth_ctx = await get_tableau_auth_async()
    logger.info(f"获取 Tableau 认证成功 (方式: {auth_ctx.auth_method})")
    return auth_ctx


async def get_datasource_luid(config: Dict[str, str], auth_ctx) -> str:
    """
    获取数据源 LUID
    
    优先使用环境变量中的 DATASOURCE_LUID，如果没有则通过名称查找。
    """
    # 优先使用环境变量中的 LUID
    if config.get("datasource_luid"):
        logger.info(f"使用环境变量中的 DATASOURCE_LUID: {config['datasource_luid']}")
        return config["datasource_luid"]
    
    # 通过名称查找
    datasource_name = config.get("datasource_name", "Superstore Datasource")
    logger.info(f"通过名称查找数据源: {datasource_name}")
    
    from tableau_assistant.src.platforms.tableau import get_datasource_luid_by_name
    
    luid = await asyncio.to_thread(
        get_datasource_luid_by_name,
        auth_ctx.api_key,
        config["domain"],
        datasource_name,
        config.get("site", ""),
    )
    
    if not luid:
        raise ValueError(f"未找到数据源: {datasource_name}")
    
    logger.info(f"解析数据源 LUID: {datasource_name} -> {luid}")
    return luid


async def get_data_model(
    datasource_luid: str,
    auth_ctx: "TableauAuthContext",
) -> "DataModel":
    """获取数据源元数据，使用 LangGraph SqliteStore 缓存"""
    from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
    from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
    from tableau_assistant.src.platforms.tableau import TableauDataModelLoader
    
    logger.info(f"获取数据源元数据: {datasource_luid}")
    
    store = get_langgraph_store()
    cache = DataModelCache(store)
    loader = TableauDataModelLoader(auth_ctx)
    
    data_model, is_cache_hit = await cache.get_or_load(datasource_luid, loader)
    
    if is_cache_hit:
        logger.info(f"从缓存加载元数据: {data_model.field_count} 个字段")
    else:
        logger.info(f"从 API 加载元数据: {data_model.field_count} 个字段")
    
    logger.info(f"  - 维度: {len(data_model.get_dimensions())} 个")
    logger.info(f"  - 度量: {len(data_model.get_measures())} 个")
    
    return data_model


# ═══════════════════════════════════════════════════════════════════════════
# Pytest Fixtures
# ═══════════════════════════════════════════════════════════════════════════

import pytest
import pytest_asyncio

# 使用 session scope 的 event loop
pytestmark = pytest.mark.asyncio(loop_scope="module")


# 缓存 fixtures 数据，避免重复加载
_cached_auth_ctx = None
_cached_datasource_luid = None
_cached_data_model = None


@pytest_asyncio.fixture
async def tableau_auth_ctx():
    """获取 Tableau 认证上下文"""
    global _cached_auth_ctx
    if _cached_auth_ctx is None:
        _cached_auth_ctx = await get_tableau_auth_context()
    return _cached_auth_ctx


@pytest_asyncio.fixture
async def datasource_luid(tableau_auth_ctx) -> str:
    """获取数据源 LUID"""
    global _cached_datasource_luid
    if _cached_datasource_luid is None:
        config = get_tableau_config()
        _cached_datasource_luid = await get_datasource_luid(config, tableau_auth_ctx)
    return _cached_datasource_luid


@pytest_asyncio.fixture
async def data_model(datasource_luid: str, tableau_auth_ctx) -> "DataModel":
    """获取数据模型"""
    global _cached_data_model
    if _cached_data_model is None:
        _cached_data_model = await get_data_model(datasource_luid, tableau_auth_ctx)
    return _cached_data_model


# ═══════════════════════════════════════════════════════════════════════════
# 测试函数
# ═══════════════════════════════════════════════════════════════════════════

async def test_dimension_hierarchy_full_inference(
    data_model: "DataModel",
    datasource_luid: str,
) -> Dict[str, Any]:
    """
    测试完整维度层级推断流程
    
    使用 force_refresh=True 强制执行完整推断流程。
    """
    from tableau_assistant.src.agents.dimension_hierarchy.node import (
        dimension_hierarchy_node,
        get_inference_stats,
        reset_inference_stats,
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("测试: 完整维度层级推断 (force_refresh=True)")
    logger.info("=" * 60)
    
    # 重置统计
    await reset_inference_stats()
    
    start_time = datetime.now()
    
    try:
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid=datasource_luid,
            force_refresh=True,
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        stats = await get_inference_stats()
        
        logger.info(f"\n推断完成，耗时: {elapsed:.2f}s")
        logger.info(f"推断维度数: {len(result.dimension_hierarchy)}")
        
        if "error" not in stats:
            logger.info(f"RAG 命中数: {stats.get('rag_hits', 0)}")
            logger.info(f"LLM 推断数: {stats.get('llm_inferences', 0)}")
            logger.info(f"RAG 命中率: {stats.get('rag_hit_rate', 0):.1%}")
            logger.info(f"RAG 存储数: {stats.get('rag_stores', 0)}")
        
        # 显示部分推断结果
        logger.info("\n推断结果示例:")
        for field_name, attrs in list(result.dimension_hierarchy.items())[:10]:
            logger.info(f"  - {field_name}: {attrs.category_detail} L{attrs.level}({attrs.granularity}) conf={attrs.level_confidence:.2f}")
        
        return {
            "success": True,
            "elapsed_seconds": elapsed,
            "dimension_count": len(result.dimension_hierarchy),
            "stats": stats,
            "result": result,
        }
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"推断失败: {e}", exc_info=True)
        return {
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e),
        }


async def test_dimension_hierarchy_cache_hit(
    data_model: "DataModel",
    datasource_luid: str,
) -> Dict[str, Any]:
    """
    测试缓存命中场景
    
    使用 force_refresh=False，应该命中缓存。
    """
    from tableau_assistant.src.agents.dimension_hierarchy.node import (
        dimension_hierarchy_node,
        get_inference_stats,
        reset_inference_stats,
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("测试: 缓存命中 (force_refresh=False)")
    logger.info("=" * 60)
    
    await reset_inference_stats()
    
    start_time = datetime.now()
    
    try:
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid=datasource_luid,
            force_refresh=False,
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        stats = await get_inference_stats()
        
        logger.info(f"\n推断完成，耗时: {elapsed:.2f}s")
        logger.info(f"推断维度数: {len(result.dimension_hierarchy)}")
        
        if "error" not in stats:
            cache_hits = stats.get('cache_hits', 0)
            llm_inferences = stats.get('llm_inferences', 0)
            logger.info(f"缓存命中数: {cache_hits}")
            logger.info(f"LLM 推断数: {llm_inferences}")
            
            # 验证缓存命中
            if cache_hits > 0 and llm_inferences == 0:
                logger.info("✓ 缓存命中成功!")
            else:
                logger.warning("✗ 缓存未完全命中")
        
        return {
            "success": True,
            "elapsed_seconds": elapsed,
            "dimension_count": len(result.dimension_hierarchy),
            "stats": stats,
        }
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e),
        }


async def test_dimension_hierarchy_rag_retrieval(
    data_model: "DataModel",
    datasource_luid: str,
) -> Dict[str, Any]:
    """
    测试 RAG 检索功能
    
    使用新的 datasource_luid 触发 RAG 检索（而非缓存命中）。
    """
    from tableau_assistant.src.agents.dimension_hierarchy.node import (
        dimension_hierarchy_node,
        get_inference_stats,
        reset_inference_stats,
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("测试: RAG 检索 (新 datasource_luid)")
    logger.info("=" * 60)
    
    await reset_inference_stats()
    
    # 使用新的 datasource_luid 避免缓存命中
    test_datasource_luid = f"{datasource_luid}_rag_test_{TIMESTAMP}"
    
    start_time = datetime.now()
    
    try:
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid=test_datasource_luid,
            force_refresh=False,
            skip_rag_store=True,  # 不存储到 RAG，避免污染
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        stats = await get_inference_stats()
        
        logger.info(f"\n推断完成，耗时: {elapsed:.2f}s")
        logger.info(f"推断维度数: {len(result.dimension_hierarchy)}")
        
        if "error" not in stats:
            rag_hits = stats.get('rag_hits', 0)
            llm_inferences = stats.get('llm_inferences', 0)
            rag_hit_rate = stats.get('rag_hit_rate', 0)
            
            logger.info(f"RAG 命中数: {rag_hits}")
            logger.info(f"LLM 推断数: {llm_inferences}")
            logger.info(f"RAG 命中率: {rag_hit_rate:.1%}")
            
            # 验证 RAG 命中
            if rag_hits > 0:
                logger.info("✓ RAG 检索成功!")
            else:
                logger.warning("✗ RAG 未命中任何模式")
        
        return {
            "success": True,
            "elapsed_seconds": elapsed,
            "dimension_count": len(result.dimension_hierarchy),
            "stats": stats,
        }
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e),
        }


async def test_field_metadata_update(
    data_model: "DataModel",
    datasource_luid: str,
) -> Dict[str, Any]:
    """
    测试字段元数据更新
    
    验证推断后 DataModel 中的字段是否被正确更新。
    """
    from tableau_assistant.src.agents.dimension_hierarchy.node import (
        dimension_hierarchy_node,
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("测试: 字段元数据更新")
    logger.info("=" * 60)
    
    try:
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid=datasource_luid,
            force_refresh=False,
        )
        
        # 验证字段元数据更新
        updated_count = 0
        sample_fields = []
        
        for field in data_model.get_dimensions()[:10]:
            if field.category is not None:
                updated_count += 1
                sample_fields.append({
                    "name": field.fieldCaption,
                    "category": field.category,
                    "category_detail": field.category_detail,
                    "level": field.level,
                    "granularity": field.granularity,
                })
        
        logger.info(f"\n已更新 {updated_count} 个字段的层级信息")
        logger.info("\n字段元数据示例:")
        for f in sample_fields[:5]:
            logger.info(f"  - {f['name']}: {f['category_detail']} L{f['level']}({f['granularity']})")
        
        # 验证 merged_hierarchy
        if hasattr(data_model, "merged_hierarchy") and data_model.merged_hierarchy:
            logger.info(f"\n✓ merged_hierarchy 已设置: {len(data_model.merged_hierarchy)} 个维度")
        else:
            logger.warning("✗ merged_hierarchy 未设置")
        
        return {
            "success": updated_count > 0,
            "updated_count": updated_count,
            "sample_fields": sample_fields,
        }
        
    except Exception as e:
        logger.error(f"测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "error": str(e),
        }


async def test_multi_table_inference(
    data_model: "DataModel",
    datasource_luid: str,
) -> Dict[str, Any]:
    """
    测试多表数据源推断
    
    如果数据源有多个逻辑表，测试并发推断功能。
    """
    from tableau_assistant.src.agents.dimension_hierarchy.node import (
        dimension_hierarchy_node_multi_table,
        get_inference_stats,
        reset_inference_stats,
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("测试: 多表数据源推断")
    logger.info("=" * 60)
    
    logical_tables = getattr(data_model, "logical_tables", None)
    if not logical_tables or len(logical_tables) <= 1:
        logger.info("数据源只有单表，跳过多表测试")
        return {
            "success": True,
            "skipped": True,
            "reason": "单表数据源",
        }
    
    logger.info(f"检测到 {len(logical_tables)} 个逻辑表")
    
    await reset_inference_stats()
    
    start_time = datetime.now()
    
    try:
        result = await dimension_hierarchy_node_multi_table(
            data_model=data_model,
            datasource_luid=f"{datasource_luid}_multi_table_test",
            force_refresh=True,
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        stats = await get_inference_stats()
        
        logger.info(f"\n多表推断完成，耗时: {elapsed:.2f}s")
        logger.info(f"推断维度数: {len(result.dimension_hierarchy)}")
        
        return {
            "success": True,
            "elapsed_seconds": elapsed,
            "dimension_count": len(result.dimension_hierarchy),
            "table_count": len(logical_tables),
            "stats": stats,
        }
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e),
        }


async def test_single_field_inference(
    data_model: "DataModel",
) -> Dict[str, Any]:
    """
    测试单字段推断功能
    
    测试 infer_single_field() 函数。
    """
    from tableau_assistant.src.agents.dimension_hierarchy.node import (
        infer_single_field,
    )
    
    logger.info("\n" + "=" * 60)
    logger.info("测试: 单字段推断")
    logger.info("=" * 60)
    
    # 获取一个维度字段进行测试
    dimensions = data_model.get_dimensions()
    if not dimensions:
        logger.warning("未找到维度字段")
        return {
            "success": False,
            "error": "未找到维度字段",
        }
    
    test_field = dimensions[0]
    logger.info(f"测试字段: {test_field.fieldCaption} ({test_field.dataType})")
    
    start_time = datetime.now()
    
    try:
        result = await infer_single_field(
            field_name=test_field.name,
            field_caption=test_field.fieldCaption,
            data_type=test_field.dataType,
            sample_values=test_field.sample_values[:10] if test_field.sample_values else [],
            unique_count=test_field.unique_count or 0,
            store_result=False,  # 不存储到 RAG
        )
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        if result:
            logger.info(f"\n单字段推断完成，耗时: {elapsed:.2f}s")
            logger.info(f"  - 类别: {result.category}")
            logger.info(f"  - 详细类别: {result.category_detail}")
            logger.info(f"  - 层级: L{result.level}")
            logger.info(f"  - 粒度: {result.granularity}")
            logger.info(f"  - 置信度: {result.level_confidence:.2f}")
            
            return {
                "success": True,
                "elapsed_seconds": elapsed,
                "result": {
                    "category": result.category,
                    "category_detail": result.category_detail,
                    "level": result.level,
                    "granularity": result.granularity,
                    "confidence": result.level_confidence,
                },
            }
        else:
            logger.warning("单字段推断返回 None")
            return {
                "success": False,
                "elapsed_seconds": elapsed,
                "error": "推断返回 None",
            }
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"测试失败: {e}", exc_info=True)
        return {
            "success": False,
            "elapsed_seconds": elapsed,
            "error": str(e),
        }


# ═══════════════════════════════════════════════════════════════════════════
# 主测试函数
# ═══════════════════════════════════════════════════════════════════════════

async def run_all_tests():
    """运行所有维度层级推断测试"""
    logger.info("=" * 60)
    logger.info("维度层级推断真实环境集成测试")
    logger.info("=" * 60)
    
    # 1. 获取 Tableau 配置
    config = get_tableau_config()
    if not config["domain"]:
        logger.error("请配置 TABLEAU_DOMAIN 环境变量")
        return
    
    logger.info(f"Tableau Domain: {config['domain']}")
    logger.info(f"Datasource Name: {config['datasource_name']}")
    
    # 2. 获取 Tableau 认证
    try:
        auth_ctx = await get_tableau_auth_context()
    except Exception as e:
        logger.error(f"获取 Tableau 认证失败: {e}")
        return
    
    # 3. 获取数据源 LUID
    try:
        datasource_luid = await get_datasource_luid(config, auth_ctx)
    except Exception as e:
        logger.error(f"获取数据源 LUID 失败: {e}")
        return
    
    logger.info(f"Datasource LUID: {datasource_luid}")
    
    # 4. 获取数据模型
    try:
        data_model = await get_data_model(
            datasource_luid=datasource_luid,
            auth_ctx=auth_ctx,
        )
    except Exception as e:
        logger.error(f"获取数据模型失败: {e}")
        return
    
    # 5. 显示数据模型信息
    logger.info("\n数据模型信息:")
    logger.info(f"  - 数据源名称: {data_model.datasource_name}")
    logger.info(f"  - 字段总数: {data_model.field_count}")
    logger.info(f"  - 维度字段: {len(data_model.get_dimensions())}")
    logger.info(f"  - 度量字段: {len(data_model.get_measures())}")
    
    logical_tables = getattr(data_model, "logical_tables", None)
    if logical_tables:
        logger.info(f"  - 逻辑表数: {len(logical_tables)}")
    
    # 6. 显示维度字段列表
    logger.info("\n维度字段列表 (前 10 个):")
    for i, field in enumerate(data_model.get_dimensions()[:10], 1):
        sample_str = ""
        if field.sample_values:
            sample_str = f", 样例: {field.sample_values[:3]}"
        logger.info(f"  {i}. {field.fieldCaption} ({field.dataType}){sample_str}")
    
    # 7. 运行测试
    results = {}
    
    # 测试 1: 完整推断
    results["full_inference"] = await test_dimension_hierarchy_full_inference(
        data_model=data_model,
        datasource_luid=datasource_luid,
    )
    
    # 测试 2: 缓存命中
    results["cache_hit"] = await test_dimension_hierarchy_cache_hit(
        data_model=data_model,
        datasource_luid=datasource_luid,
    )
    
    # 测试 3: RAG 检索
    results["rag_retrieval"] = await test_dimension_hierarchy_rag_retrieval(
        data_model=data_model,
        datasource_luid=datasource_luid,
    )
    
    # 测试 4: 字段元数据更新
    results["field_update"] = await test_field_metadata_update(
        data_model=data_model,
        datasource_luid=datasource_luid,
    )
    
    # 测试 5: 多表推断
    results["multi_table"] = await test_multi_table_inference(
        data_model=data_model,
        datasource_luid=datasource_luid,
    )
    
    # 测试 6: 单字段推断
    results["single_field"] = await test_single_field_inference(
        data_model=data_model,
    )
    
    # 8. 输出测试摘要
    logger.info("\n" + "=" * 60)
    logger.info("测试摘要")
    logger.info("=" * 60)
    
    success_count = 0
    for test_name, result in results.items():
        status = "✓" if result.get("success") else "✗"
        if result.get("skipped"):
            status = "○"
        
        elapsed = result.get("elapsed_seconds", 0)
        error = result.get("error", "")
        
        if result.get("skipped"):
            logger.info(f"  {status} {test_name}: 跳过 ({result.get('reason', '')})")
        elif result.get("success"):
            success_count += 1
            logger.info(f"  {status} {test_name}: 成功 ({elapsed:.2f}s)")
        else:
            logger.info(f"  {status} {test_name}: 失败 ({error})")
    
    total_tests = len([r for r in results.values() if not r.get("skipped")])
    logger.info(f"\n总计: {success_count}/{total_tests} 测试通过")
    
    # 9. 输出性能统计
    if results.get("full_inference", {}).get("success"):
        stats = results["full_inference"].get("stats", {})
        if "error" not in stats:
            logger.info("\n性能统计:")
            logger.info(f"  - RAG 命中率: {stats.get('rag_hit_rate', 0):.1%}")
            logger.info(f"  - RAG 命中数: {stats.get('rag_hits', 0)}")
            logger.info(f"  - LLM 推断数: {stats.get('llm_inferences', 0)}")
            logger.info(f"  - RAG 存储数: {stats.get('rag_stores', 0)}")
            logger.info(f"  - 总耗时: {stats.get('total_time_ms', 0):.0f}ms")
    
    logger.info(f"\n输出文件: {LOG_FILE}")


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(run_all_tests())
