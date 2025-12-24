"""
Semantic Parser 集成测试

使用真实的 Tableau 环境、真实的 LLM 和真实数据进行测试。
包含维度层级推断。

运行方式:
    python -m tableau_assistant.tests.integration.test_semantic_parser_integration

或者使用 pytest:
    pytest tableau_assistant/tests/integration/test_semantic_parser_integration.py -v -s
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv

# 加载环境变量
load_dotenv()

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 测试配置
# ═══════════════════════════════════════════════════════════════════════════

# 测试问题列表
TEST_QUESTIONS = [
    # 简单查询
    "各省份的销售额是多少？",
    "按月份统计订单数量",
    
    # 带筛选的查询
    "北京市的销售额",
    "2024年的销售趋势",
    
    # 复杂计算
    "各省份销售额占比",
    "按月份计算销售额同比增长",
    "各产品类别的销售额排名",
    
    # 需要澄清的问题
    "销售情况怎么样？",
    
    # 一般性问题
    "你好",
    "这个数据源有哪些字段？",
]


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_tableau_config() -> Dict[str, str]:
    """从环境变量获取 Tableau 配置"""
    return {
        "domain": os.getenv("TABLEAU_DOMAIN", ""),
        "site": os.getenv("TABLEAU_SITE", ""),
        "datasource_luid": os.getenv("DATASOURCE_LUID", ""),
        "pat_name": os.getenv("TABLEAU_PAT_NAME", ""),
        "pat_secret": os.getenv("TABLEAU_PAT_SECRET", ""),
    }


async def get_tableau_auth_context():
    """获取 Tableau 认证上下文"""
    from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async, TableauAuthContext
    
    auth_ctx = await get_tableau_auth_async()
    logger.info(f"获取 Tableau 认证成功 (方式: {auth_ctx.auth_method})")
    return auth_ctx


async def get_metadata(
    datasource_luid: str,
    token: str,
    site: str,
    domain: str
) -> "DataModel":
    """获取数据源元数据"""
    from tableau_assistant.src.platforms.tableau.metadata import get_datasource_metadata
    from tableau_assistant.src.core.models import DataModel, FieldMetadata, LogicalTable, LogicalTableRelationship
    
    logger.info(f"获取数据源元数据: {datasource_luid}")
    
    # 获取原始元数据
    raw_metadata = await get_datasource_metadata(
        datasource_luid=datasource_luid,
        tableau_token=token,
        tableau_site=site,
        tableau_domain=domain,
    )
    
    # 转换为 DataModel 对象
    fields = []
    for f in raw_metadata.get("fields", []):
        role = f.get("role", "dimension").lower()
        if role not in ("dimension", "measure"):
            role = "dimension"
        
        field = FieldMetadata(
            name=f.get("name", ""),
            fieldCaption=f.get("fieldCaption", f.get("name", "")),
            role=role,
            dataType=f.get("dataType", "STRING"),
            dataCategory=f.get("dataCategory"),
            aggregation=f.get("aggregation"),
            formula=f.get("formula"),
            sample_values=f.get("sample_values"),
            unique_count=f.get("unique_count"),
        )
        fields.append(field)
    
    # 解析逻辑表结构
    logical_tables = []
    logical_table_relationships = []
    raw_data_model = raw_metadata.get("data_model")
    if raw_data_model:
        if hasattr(raw_data_model, 'logicalTables'):
            logical_tables = raw_data_model.logicalTables
            logical_table_relationships = raw_data_model.logicalTableRelationships
        elif isinstance(raw_data_model, dict):
            for t in raw_data_model.get("logicalTables", []):
                logical_tables.append(LogicalTable(
                    logicalTableId=t.get("logicalTableId", ""),
                    caption=t.get("caption", "")
                ))
            for r in raw_data_model.get("logicalTableRelationships", []):
                logical_table_relationships.append(LogicalTableRelationship(
                    fromLogicalTableId=r.get("fromLogicalTableId", ""),
                    toLogicalTableId=r.get("toLogicalTableId", "")
                ))
    
    data_model = DataModel(
        datasource_luid=datasource_luid,
        datasource_name=raw_metadata.get("datasource_name", "Unknown"),
        datasource_description=raw_metadata.get("datasource_description"),
        datasource_owner=raw_metadata.get("datasource_owner"),
        logical_tables=logical_tables,
        logical_table_relationships=logical_table_relationships,
        fields=fields,
        field_count=len(fields),
    )
    
    logger.info(f"元数据获取成功: {data_model.field_count} 个字段")
    logger.info(f"  - 维度: {len(data_model.get_dimensions())} 个")
    logger.info(f"  - 度量: {len(data_model.get_measures())} 个")
    
    return data_model


async def run_dimension_hierarchy(
    data_model: "DataModel",
    datasource_luid: str
) -> "DimensionHierarchyResult":
    """运行维度层级推断"""
    from tableau_assistant.src.agents.dimension_hierarchy import dimension_hierarchy_node
    
    logger.info("开始维度层级推断...")
    
    result = await dimension_hierarchy_node(
        data_model=data_model,
        datasource_luid=datasource_luid,
        stream=True,  # 测试时关闭流式输出
        use_cache=True,
        incremental=True,
        parallel=True,
    )
    
    logger.info(f"维度层级推断完成: {len(result.dimension_hierarchy)} 个维度")
    
    # 打印部分结果
    for field_name, attrs in list(result.dimension_hierarchy.items())[:5]:
        logger.info(f"  - {field_name}: {attrs.category_detail} L{attrs.level}")
    
    return result


def format_data_model_for_prompt(data_model: "DataModel") -> Dict[str, Any]:
    """将 DataModel 格式化为 prompt 需要的格式"""
    fields = []
    for f in data_model.fields:
        field_info = {
            "name": f.name,
            "fieldCaption": f.fieldCaption,
            "role": f.role,
            "dataType": f.dataType,
        }
        if f.sample_values:
            field_info["sample_values"] = f.sample_values[:3]
        if f.category:
            field_info["category"] = f.category
        if f.level:
            field_info["level"] = f.level
        fields.append(field_info)
    
    return {"fields": fields}


# ═══════════════════════════════════════════════════════════════════════════
# 测试函数
# ═══════════════════════════════════════════════════════════════════════════

async def test_single_question(
    question: str,
    data_model: "DataModel",
    history: Optional[List[Dict[str, str]]] = None
) -> Dict[str, Any]:
    """测试单个问题"""
    from tableau_assistant.src.agents.semantic_parser import SemanticParserAgent
    from tableau_assistant.src.core.models import IntentType
    import traceback
    
    logger.info(f"\n{'='*60}")
    logger.info(f"测试问题: {question}")
    logger.info(f"{'='*60}")
    
    # 准备 data_model
    metadata_dict = format_data_model_for_prompt(data_model)
    
    # 创建 agent 并解析
    agent = SemanticParserAgent()
    
    start_time = datetime.now()
    try:
        result = await agent.parse(
            question=question,
            history=history,
            metadata=metadata_dict,
        )
    except Exception as e:
        logger.error(f"解析失败: {e}")
        logger.error(traceback.format_exc())
        raise
    elapsed = (datetime.now() - start_time).total_seconds()
    
    # 输出结果
    logger.info(f"\n--- 解析结果 (耗时: {elapsed:.2f}s) ---")
    logger.info(f"重述问题: {result.restated_question}")
    logger.info(f"意图类型: {result.intent.type.value}")
    logger.info(f"意图推理: {result.intent.reasoning}")
    
    if result.intent.type == IntentType.DATA_QUERY and result.semantic_query:
        sq = result.semantic_query
        logger.info(f"\n语义查询:")
        if sq.dimensions:
            dims = [f"{d.field_name}({d.date_granularity})" if d.date_granularity else d.field_name 
                    for d in sq.dimensions]
            logger.info(f"  维度: {dims}")
        if sq.measures:
            measures = [f"{m.field_name}({m.aggregation})" for m in sq.measures]
            logger.info(f"  度量: {measures}")
        if sq.filters:
            logger.info(f"  筛选: {len(sq.filters)} 个 - {sq.filters}")
        if sq.computations:
            logger.info(f"  计算: {len(sq.computations)} 个")
            for comp in sq.computations:
                logger.info(f"    - {comp.calc_type.value}: target={comp.target}, partition_by={comp.partition_by}")
    
    elif result.intent.type == IntentType.CLARIFICATION and result.clarification:
        logger.info(f"\n澄清问题: {result.clarification.question}")
    
    elif result.intent.type == IntentType.GENERAL and result.general_response:
        logger.info(f"\n一般回复: {result.general_response}")
    
    return {
        "question": question,
        "restated_question": result.restated_question,
        "intent_type": result.intent.type.value,
        "elapsed_seconds": elapsed,
        "success": True,
    }


async def test_conversation_flow(data_model: "DataModel") -> List[Dict[str, Any]]:
    """测试多轮对话"""
    from tableau_assistant.src.agents.semantic_parser import SemanticParserAgent
    
    logger.info(f"\n{'#'*60}")
    logger.info("测试多轮对话")
    logger.info(f"{'#'*60}")
    
    conversation = [
        "各省份的销售额",
        "按月份细分呢？",
        "只看北京的",
        "计算同比增长",
    ]
    
    metadata_dict = format_data_model_for_prompt(data_model)
    agent = SemanticParserAgent()
    
    history = []
    results = []
    
    for question in conversation:
        logger.info(f"\n用户: {question}")
        
        result = await agent.parse(
            question=question,
            history=history,
            metadata=metadata_dict,
        )
        
        logger.info(f"重述: {result.restated_question}")
        logger.info(f"意图: {result.intent.type.value}")
        
        # 更新历史
        history.append({"role": "user", "content": question})
        history.append({"role": "assistant", "content": result.restated_question})
        
        results.append({
            "question": question,
            "restated_question": result.restated_question,
            "intent_type": result.intent.type.value,
        })
    
    return results


async def run_all_tests():
    """运行所有测试"""
    logger.info("="*60)
    logger.info("Semantic Parser 集成测试")
    logger.info("="*60)
    
    # 1. 获取 Tableau 配置
    config = get_tableau_config()
    if not config["domain"] or not config["datasource_luid"]:
        logger.error("请配置 TABLEAU_DOMAIN 和 DATASOURCE_LUID 环境变量")
        return
    
    logger.info(f"Tableau Domain: {config['domain']}")
    logger.info(f"Datasource LUID: {config['datasource_luid']}")
    
    # 2. 获取 Tableau 认证
    try:
        auth_ctx = await get_tableau_auth_context()
    except Exception as e:
        logger.error(f"获取 Tableau 认证失败: {e}")
        return
    
    # 3. 获取数据模型
    try:
        data_model = await get_metadata(
            datasource_luid=config["datasource_luid"],
            token=auth_ctx.api_key,
            site=auth_ctx.site,
            domain=auth_ctx.domain,
        )
    except Exception as e:
        logger.error(f"获取数据模型失败: {e}")
        return
    
    # 4. 运行维度层级推断
    try:
        hierarchy_result = await run_dimension_hierarchy(
            data_model=data_model,
            datasource_luid=config["datasource_luid"],
        )
        # 将层级信息注入到 data_model
        for field_name, attrs in hierarchy_result.dimension_hierarchy.items():
            field = data_model.get_field(field_name)
            if field:
                field.category = attrs.category
                field.category_detail = attrs.category_detail
                field.level = attrs.level
                field.granularity = attrs.granularity
    except Exception as e:
        logger.warning(f"维度层级推断失败（继续测试）: {e}")
    
    # 5. 测试单个问题
    logger.info("\n" + "="*60)
    logger.info("测试单个问题")
    logger.info("="*60)
    
    results = []
    for question in TEST_QUESTIONS:
        try:
            result = await test_single_question(question, data_model)
            results.append(result)
        except Exception as e:
            logger.error(f"测试失败: {question}")
            logger.error(f"错误: {e}")
            results.append({
                "question": question,
                "success": False,
                "error": str(e),
            })
    
    # 6. 测试多轮对话
    try:
        conversation_results = await test_conversation_flow(data_model)
    except Exception as e:
        logger.error(f"多轮对话测试失败: {e}")
        conversation_results = []
    
    # 7. 输出测试摘要
    logger.info("\n" + "="*60)
    logger.info("测试摘要")
    logger.info("="*60)
    
    success_count = sum(1 for r in results if r.get("success", False))
    logger.info(f"单问题测试: {success_count}/{len(results)} 成功")
    
    if conversation_results:
        logger.info(f"多轮对话测试: {len(conversation_results)} 轮完成")
    
    # 统计意图分布
    intent_counts = {}
    for r in results:
        if r.get("success"):
            intent = r.get("intent_type", "unknown")
            intent_counts[intent] = intent_counts.get(intent, 0) + 1
    
    logger.info(f"意图分布: {intent_counts}")
    
    # 平均耗时
    times = [r.get("elapsed_seconds", 0) for r in results if r.get("success")]
    if times:
        avg_time = sum(times) / len(times)
        logger.info(f"平均耗时: {avg_time:.2f}s")


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(run_all_tests())
