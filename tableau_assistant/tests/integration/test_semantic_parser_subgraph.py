"""
SemanticParser Subgraph 集成测试

使用真实的 Tableau 环境、真实的 LLM 和真实数据进行测试。
测试新的 LangGraph Subgraph 架构。

运行方式:
    python -m tableau_assistant.tests.integration.test_semantic_parser_subgraph

或者使用 pytest:
    pytest tableau_assistant/tests/integration/test_semantic_parser_subgraph.py -v -s
"""
import asyncio
import json
import logging
import os
import sys
from datetime import datetime
from typing import Any, Dict, List, Optional
from pathlib import Path

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

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
LOG_FILE = OUTPUT_DIR / f"semantic_parser_test_{TIMESTAMP}.log"
LLM_RESPONSES_FILE = OUTPUT_DIR / f"llm_responses_{TIMESTAMP}.md"

# 配置日志 - 同时输出到控制台和文件
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    handlers=[
        logging.StreamHandler(),  # 控制台输出
        logging.FileHandler(LOG_FILE, encoding='utf-8'),  # 文件输出
    ]
)
logger = logging.getLogger(__name__)

# LLM 响应收集器
class LLMResponseCollector:
    """收集和保存 LLM 响应"""
    
    def __init__(self, output_file: Path):
        self.output_file = output_file
        self.responses: List[Dict[str, Any]] = []
        self._init_file()
    
    def _init_file(self):
        """初始化输出文件"""
        with open(self.output_file, 'w', encoding='utf-8') as f:
            f.write(f"# LLM 响应记录\n\n")
            f.write(f"生成时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
            f.write("---\n\n")
    
    def add_response(
        self,
        question: str,
        node_name: str,
        llm_output: str,
        parsed_result: Any = None,
        elapsed_ms: float = 0,
        metadata: Dict[str, Any] = None,
    ):
        """添加一条 LLM 响应记录"""
        record = {
            "timestamp": datetime.now().isoformat(),
            "question": question,
            "node_name": node_name,
            "llm_output": llm_output,
            "parsed_result": parsed_result,
            "elapsed_ms": elapsed_ms,
            "metadata": metadata or {},
        }
        self.responses.append(record)
        
        # 实时写入文件
        self._append_to_file(record)
    
    def _append_to_file(self, record: Dict[str, Any]):
        """追加记录到文件"""
        with open(self.output_file, 'a', encoding='utf-8') as f:
            f.write(f"## 问题: {record['question']}\n\n")
            f.write(f"**节点**: `{record['node_name']}`\n")
            f.write(f"**时间**: {record['timestamp']}\n")
            f.write(f"**耗时**: {record['elapsed_ms']:.0f}ms\n\n")
            
            f.write("### LLM 原始输出\n\n")
            f.write("```\n")
            f.write(record['llm_output'])
            f.write("\n```\n\n")
            
            if record['parsed_result']:
                f.write("### 解析结果\n\n")
                f.write("```json\n")
                try:
                    if hasattr(record['parsed_result'], 'model_dump'):
                        f.write(json.dumps(record['parsed_result'].model_dump(), ensure_ascii=False, indent=2))
                    elif hasattr(record['parsed_result'], '__dict__'):
                        f.write(json.dumps(record['parsed_result'].__dict__, ensure_ascii=False, indent=2, default=str))
                    else:
                        f.write(json.dumps(record['parsed_result'], ensure_ascii=False, indent=2, default=str))
                except Exception as e:
                    f.write(f"序列化失败: {e}\n{str(record['parsed_result'])}")
                f.write("\n```\n\n")
            
            if record['metadata']:
                f.write("### 元数据\n\n")
                f.write("```json\n")
                f.write(json.dumps(record['metadata'], ensure_ascii=False, indent=2, default=str))
                f.write("\n```\n\n")
            
            f.write("---\n\n")
    
    def save_summary(self):
        """保存汇总信息"""
        with open(self.output_file, 'a', encoding='utf-8') as f:
            f.write("# 测试汇总\n\n")
            f.write(f"总记录数: {len(self.responses)}\n\n")
            
            # 按节点统计
            node_stats = {}
            for r in self.responses:
                node = r['node_name']
                if node not in node_stats:
                    node_stats[node] = {'count': 0, 'total_ms': 0}
                node_stats[node]['count'] += 1
                node_stats[node]['total_ms'] += r['elapsed_ms']
            
            f.write("## 按节点统计\n\n")
            f.write("| 节点 | 调用次数 | 平均耗时(ms) |\n")
            f.write("|------|----------|-------------|\n")
            for node, stats in node_stats.items():
                avg_ms = stats['total_ms'] / stats['count'] if stats['count'] > 0 else 0
                f.write(f"| {node} | {stats['count']} | {avg_ms:.0f} |\n")

# 全局 LLM 响应收集器
llm_collector = LLMResponseCollector(LLM_RESPONSES_FILE)

logger.info(f"日志文件: {LOG_FILE}")
logger.info(f"LLM响应文件: {LLM_RESPONSES_FILE}")


# ═══════════════════════════════════════════════════════════════════════════
# 测试配置
# ═══════════════════════════════════════════════════════════════════════════

# 测试问题列表 - 按复杂度分类
TEST_QUESTIONS = {
    "simple": [
        # 简单查询 - 应该走 step1 → pipeline 路径
        # "去年各省份的销售额是多少？",
        # "按月份统计订单数量",
        # "北京市的销售额",
    ],
    "complex": [
        # 复杂计算 - 应该走 step1 → step2 → pipeline 路径
        # "2025年各省份销售额占比",
        # "今年按月份计算销售额同比增长",
        "各产品类别的销售额排名",
    ],
    "clarification": [
        # 需要澄清的问题 - 应该返回澄清问题
        "销售情况怎么样？",
    ],
    "general": [
        # 一般性问题 - 应该直接返回
        "你好",
        "这个数据源有哪些字段？",
    ],
}


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def get_tableau_config() -> Dict[str, str]:
    """从环境变量获取 Tableau 配置"""
    # 支持多环境配置，优先使用 TABLEAU_CLOUD_* 变量
    domain = os.getenv("TABLEAU_CLOUD_DOMAIN", os.getenv("TABLEAU_DOMAIN", ""))
    site = os.getenv("TABLEAU_CLOUD_SITE", os.getenv("TABLEAU_SITE", ""))
    
    return {
        "domain": domain,
        "site": site,
        "datasource_luid": os.getenv("DATASOURCE_LUID", ""),
        "pat_name": os.getenv("TABLEAU_CLOUD_PAT_NAME", os.getenv("TABLEAU_PAT_NAME", "")),
        "pat_secret": os.getenv("TABLEAU_CLOUD_PAT_SECRET", os.getenv("TABLEAU_PAT_SECRET", "")),
    }


async def get_tableau_auth_context():
    """获取 Tableau 认证上下文"""
    from tableau_assistant.src.platforms.tableau.auth import get_tableau_auth_async
    
    auth_ctx = await get_tableau_auth_async()
    logger.info(f"获取 Tableau 认证成功 (方式: {auth_ctx.auth_method})")
    return auth_ctx


async def get_data_model(
    datasource_luid: str,
    token: str,
    site: str,
    domain: str,
    auth_ctx: "TableauAuthContext" = None,
    use_cache: bool = True,
) -> "DataModel":
    """获取数据源元数据，使用 LangGraph SqliteStore 缓存"""
    from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
    from tableau_assistant.src.infra.storage.data_model_cache import DataModelCache
    from tableau_assistant.src.infra.storage.data_model_loader import TableauDataModelLoader
    
    logger.info(f"获取数据源元数据: {datasource_luid}")
    
    # 使用缓存机制
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


async def run_dimension_hierarchy(
    data_model: "DataModel",
    datasource_luid: str
) -> Optional["DimensionHierarchyResult"]:
    """运行维度层级推断"""
    try:
        from tableau_assistant.src.agents.dimension_hierarchy import dimension_hierarchy_node
        
        logger.info("开始维度层级推断...")
        
        result = await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid=datasource_luid,
            stream=False,
            use_cache=True,
            incremental=True,
            parallel=True,
        )
        
        logger.info(f"维度层级推断完成: {len(result.dimension_hierarchy)} 个维度")
        
        # 打印部分结果
        for field_name, attrs in list(result.dimension_hierarchy.items())[:5]:
            logger.info(f"  - {field_name}: {attrs.category_detail} L{attrs.level}")
        
        return result
    except Exception as e:
        logger.warning(f"维度层级推断失败（继续测试）: {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# Subgraph 测试函数 (内部辅助函数，不是 pytest 测试)
# ═══════════════════════════════════════════════════════════════════════════

async def _run_subgraph_single_question(
    question: str,
    data_model: "DataModel",
    datasource_luid: str,
    auth_ctx: "TableauAuthContext",
    history: Optional[List[Dict[str, str]]] = None,
    expected_path: Optional[str] = None,
) -> Dict[str, Any]:
    """测试单个问题 - 使用 Subgraph 架构"""
    from tableau_assistant.src.agents.semantic_parser.subgraph import create_semantic_parser_subgraph
    from tableau_assistant.src.agents.semantic_parser.state import SemanticParserState
    from tableau_assistant.src.core.models import IntentType, HowType
    from tableau_assistant.src.orchestration.workflow.context import WorkflowContext, create_workflow_config
    from langchain_core.messages import HumanMessage, AIMessage
    
    logger.info(f"\n{'='*60}")
    logger.info(f"测试问题: {question}")
    logger.info(f"预期路径: {expected_path or '未指定'}")
    logger.info(f"{'='*60}")
    
    # 创建 Subgraph
    graph = create_semantic_parser_subgraph()
    compiled_graph = graph.compile()
    
    # 创建 WorkflowContext 和 config
    workflow_ctx = WorkflowContext(
        auth=auth_ctx,
        datasource_luid=datasource_luid,
        data_model=data_model,
    )
    config = create_workflow_config(
        thread_id=f"test-{question[:20]}",
        context=workflow_ctx,
    )
    
    # 准备消息历史
    messages = []
    if history:
        for msg in history:
            if msg["role"] == "user":
                messages.append(HumanMessage(content=msg["content"]))
            else:
                messages.append(AIMessage(content=msg["content"]))
    messages.append(HumanMessage(content=question))
    
    # 准备初始状态
    initial_state: SemanticParserState = {
        # 必需字段
        "question": question,
        "messages": messages,
        "data_model": data_model,
        "datasource_luid": datasource_luid,
        
        # 可选字段初始化
        "step1_output": None,
        "step2_output": None,
        "pipeline_success": None,
        "needs_clarification": None,
        "pipeline_aborted": None,
        "retry_from": None,
        "error_feedback": None,
        "react_action": None,
        "pipeline_error": None,
        "retry_count": None,
        "retry_history": None,
        "clarification_question": None,
        "user_message": None,
        "columns": None,
        "row_count": None,
        "file_path": None,
        "is_large_result": None,
        "mapped_query": None,
        "vizql_query": None,
        "execution_time_ms": None,
        "thinking": None,
        "semantic_query": None,
        "restated_question": None,
        "current_stage": "semantic_parser",
        
        # VizQLState 必需字段
        "answered_questions": [],
        "is_analysis_question": True,
        "intent_type": None,
        "intent_reasoning": None,
        "general_response": None,
        "non_analysis_response": None,
        "clarification_options": None,
        "clarification_field": None,
        "query_result": None,
        "insights": [],
        "all_insights": [],
        "replan_decision": None,
        "replan_count": 0,
        "max_replan_rounds": 3,
        "replan_history": [],
        "final_report": None,
        "execution_path": [],
        "semantic_parser_complete": False,
        "field_mapper_complete": False,
        "query_builder_complete": False,
        "execute_complete": False,
        "insight_complete": False,
        "replanner_complete": False,
        "datasource": datasource_luid,
        "dimension_hierarchy": None,
        "data_insight_profile": None,
        "current_dimensions": [],
        "pending_questions": [],
        "errors": [],
        "warnings": [],
        "performance": None,
        "visualizations": [],
    }
    
    start_time = datetime.now()
    result = None
    
    # LLM 响应收集
    llm_responses_buffer: Dict[str, str] = {}  # node_name -> accumulated_output
    node_start_times: Dict[str, datetime] = {}  # node_name -> start_time
    
    try:
        # 使用 astream_events 执行 Subgraph，捕获流式输出
        token_count = 0
        current_node = ""
        current_llm_output = ""
        
        async for event in compiled_graph.astream_events(initial_state, config=config, version="v2"):
            event_type = event.get("event")
            event_name = event.get("name", "")
            
            # 捕获节点开始事件
            if event_type == "on_chain_start":
                if event_name and event_name not in ["RunnableSequence", "ChannelWrite", "LangGraph"]:
                    # 保存上一个节点的 LLM 输出
                    if current_node and current_llm_output:
                        llm_responses_buffer[current_node] = current_llm_output
                        node_elapsed = (datetime.now() - node_start_times.get(current_node, start_time)).total_seconds() * 1000
                        logger.info(f"\n[{current_node}] LLM输出长度: {len(current_llm_output)} 字符, 耗时: {node_elapsed:.0f}ms")
                    
                    current_node = event_name
                    current_llm_output = ""
                    node_start_times[current_node] = datetime.now()
                    print(f"\n  [*] [{current_node}] ", end="", flush=True)
            
            # 捕获 LLM 流式 token
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content") and chunk.content:
                    token = chunk.content
                    print(token, end="", flush=True)
                    token_count += len(token)
                    current_llm_output += token
            
            # 捕获 LLM 完成事件 (非流式)
            if event_type == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                if output and hasattr(output, "content") and output.content:
                    if not current_llm_output:  # 如果没有流式输出，使用完整输出
                        current_llm_output = output.content
                        logger.info(f"\n[{current_node}] LLM完整输出: {len(current_llm_output)} 字符")
            
            # 捕获最终状态
            if event_type == "on_chain_end" and event_name == "LangGraph":
                output = event.get("data", {}).get("output")
                if output and isinstance(output, dict):
                    result = output
        
        # 保存最后一个节点的输出
        if current_node and current_llm_output:
            llm_responses_buffer[current_node] = current_llm_output
            node_elapsed = (datetime.now() - node_start_times.get(current_node, start_time)).total_seconds() * 1000
            logger.info(f"\n[{current_node}] LLM输出长度: {len(current_llm_output)} 字符, 耗时: {node_elapsed:.0f}ms")
        
        print(f"\n  [OK] (total {token_count} chars)")
        
        # 如果没有从事件中获取到结果，使用 ainvoke 作为后备
        if result is None:
            logger.warning("未从 astream_events 获取到结果，使用 ainvoke 后备")
            result = await compiled_graph.ainvoke(initial_state, config=config)
        
        elapsed = (datetime.now() - start_time).total_seconds()
        
        # 分析结果
        step1_output = result.get("step1_output")
        step2_output = result.get("step2_output")
        pipeline_success = result.get("pipeline_success")
        needs_clarification = result.get("needs_clarification")
        pipeline_aborted = result.get("pipeline_aborted")
        semantic_query = result.get("semantic_query")
        restated_question = result.get("restated_question")
        query_result = result.get("query_result")
        row_count = result.get("row_count")
        clarification_question = result.get("clarification_question")
        user_message = result.get("user_message")
        retry_count = result.get("retry_count") or 0
        
        # 记录 LLM 响应到文档
        for node_name, llm_output in llm_responses_buffer.items():
            node_elapsed = (node_start_times.get(node_name, start_time) - start_time).total_seconds() * 1000
            
            # 确定解析结果
            parsed_result = None
            if node_name == "step1" and step1_output:
                parsed_result = step1_output
            elif node_name == "step2" and step2_output:
                parsed_result = step2_output
            
            # 元数据
            metadata = {
                "expected_path": expected_path,
                "retry_count": retry_count,
                "pipeline_success": pipeline_success,
                "needs_clarification": needs_clarification,
            }
            
            llm_collector.add_response(
                question=question,
                node_name=node_name,
                llm_output=llm_output,
                parsed_result=parsed_result,
                elapsed_ms=node_elapsed,
                metadata=metadata,
            )
        
        # 确定执行路径
        actual_path = "step1"
        if step2_output:
            actual_path = "step1 → step2"
        if pipeline_success is not None:
            actual_path += " → pipeline"
            if pipeline_success:
                actual_path += " (成功)"
            else:
                actual_path += " (失败)"
        if needs_clarification:
            actual_path = "step1 → CLARIFY"
        if pipeline_aborted:
            actual_path += " → ABORT"
        
        # 输出结果
        logger.info(f"\n--- 执行结果 (耗时: {elapsed:.2f}s) ---")
        logger.info(f"执行路径: {actual_path}")
        logger.info(f"重试次数: {retry_count}")
        
        if step1_output:
            logger.info(f"\nStep1 输出:")
            logger.info(f"  重述问题: {restated_question}")
            logger.info(f"  意图类型: {step1_output.intent.type.value}")
            logger.info(f"  How类型: {step1_output.how_type.value}")
            
            if step1_output.intent.type == IntentType.DATA_QUERY:
                if step1_output.where.dimensions:
                    dims = [d.field_name for d in step1_output.where.dimensions]
                    logger.info(f"  维度: {dims}")
                if step1_output.what.measures:
                    measures = [m.field_name for m in step1_output.what.measures]
                    logger.info(f"  度量: {measures}")
        
        if step2_output:
            logger.info(f"\nStep2 输出:")
            logger.info(f"  计算数量: {len(step2_output.computations)}")
            for comp in step2_output.computations:
                # calc_type 可能是字符串或枚举
                calc_type_str = comp.calc_type.value if hasattr(comp.calc_type, 'value') else comp.calc_type
                logger.info(f"    - {calc_type_str}: target={comp.target}")
        
        if pipeline_success:
            logger.info(f"\nPipeline 成功:")
            logger.info(f"  行数: {row_count}")
            if query_result:
                logger.info(f"  数据预览: {query_result[:3] if isinstance(query_result, list) else '...'}")
        
        if needs_clarification:
            logger.info(f"\n需要澄清:")
            logger.info(f"  问题: {clarification_question}")
        
        if pipeline_aborted:
            logger.info(f"\nPipeline 中止:")
            logger.info(f"  消息: {user_message}")
        
        return {
            "question": question,
            "expected_path": expected_path,
            "actual_path": actual_path,
            "elapsed_seconds": elapsed,
            "success": pipeline_success or needs_clarification or (step1_output and step1_output.intent.type != IntentType.DATA_QUERY),
            "step1_output": step1_output,
            "step2_output": step2_output,
            "pipeline_success": pipeline_success,
            "needs_clarification": needs_clarification,
            "pipeline_aborted": pipeline_aborted,
            "row_count": row_count,
            "retry_count": retry_count,
        }
        
    except Exception as e:
        elapsed = (datetime.now() - start_time).total_seconds()
        logger.error(f"测试失败: {e}", exc_info=True)
        return {
            "question": question,
            "expected_path": expected_path,
            "actual_path": "ERROR",
            "elapsed_seconds": elapsed,
            "success": False,
            "error": str(e),
        }


async def _run_subgraph_conversation_flow(
    data_model: "DataModel",
    datasource_luid: str,
    auth_ctx: "TableauAuthContext",
) -> List[Dict[str, Any]]:
    """测试多轮对话 - 使用 Subgraph 架构"""
    logger.info(f"\n{'#'*60}")
    logger.info("测试多轮对话 (Subgraph)")
    logger.info(f"{'#'*60}")
    
    conversation = [
        "各省份的销售额",
        "按月份细分呢？",
        "只看北京的",
    ]
    
    history = []
    results = []
    
    for question in conversation:
        logger.info(f"\n用户: {question}")
        
        result = await _run_subgraph_single_question(
            question=question,
            data_model=data_model,
            datasource_luid=datasource_luid,
            auth_ctx=auth_ctx,
            history=history,
        )
        
        # 更新历史
        history.append({"role": "user", "content": question})
        if result.get("restated_question"):
            history.append({"role": "assistant", "content": result["restated_question"]})
        
        results.append(result)
    
    return results


# ═══════════════════════════════════════════════════════════════════════════
# 主测试函数
# ═══════════════════════════════════════════════════════════════════════════

async def run_all_tests():
    """运行所有 Subgraph 测试"""
    logger.info("="*60)
    logger.info("SemanticParser Subgraph 集成测试")
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
    
    # 3. 获取数据模型（使用缓存）
    try:
        data_model = await get_data_model(
            datasource_luid=config["datasource_luid"],
            token=auth_ctx.api_key,
            site=auth_ctx.site,
            domain=auth_ctx.domain,
            auth_ctx=auth_ctx,
        )
    except Exception as e:
        logger.error(f"获取数据模型失败: {e}")
        return
    
    # 4. 维度层级已在缓存中处理，不需要单独运行
    # 如果缓存命中，dimension_hierarchy 已经包含在 data_model 中
    if data_model.dimension_hierarchy:
        logger.info(f"维度层级已加载: {len(data_model.dimension_hierarchy)} 个维度")
        for field_name, attrs in list(data_model.dimension_hierarchy.items())[:5]:
            if isinstance(attrs, dict):
                logger.info(f"  - {field_name}: {attrs.get('category_detail', 'unknown')} L{attrs.get('level', 0)}")
            else:
                logger.info(f"  - {field_name}: {attrs.category_detail} L{attrs.level}")
    else:
        # 如果没有维度层级，运行推断
        hierarchy_result = await run_dimension_hierarchy(
            data_model=data_model,
            datasource_luid=config["datasource_luid"],
        )
        if hierarchy_result:
            # 将层级信息注入到 data_model
            for field_name, attrs in hierarchy_result.dimension_hierarchy.items():
                field = data_model.get_field(field_name)
                if field:
                    field.category = attrs.category
                    field.category_detail = attrs.category_detail
                    field.level = attrs.level
                    field.granularity = attrs.granularity
    
    # 5. 测试简单查询
    logger.info("\n" + "="*60)
    logger.info("测试简单查询 (step1 → pipeline)")
    logger.info("="*60)
    
    simple_results = []
    for question in TEST_QUESTIONS["simple"]:
        result = await _run_subgraph_single_question(
            question=question,
            data_model=data_model,
            datasource_luid=config["datasource_luid"],
            auth_ctx=auth_ctx,
            expected_path="step1 → pipeline",
        )
        simple_results.append(result)
    
    # 6. 测试复杂查询
    logger.info("\n" + "="*60)
    logger.info("测试复杂查询 (step1 → step2 → pipeline)")
    logger.info("="*60)
    
    complex_results = []
    for question in TEST_QUESTIONS["complex"]:
        result = await _run_subgraph_single_question(
            question=question,
            data_model=data_model,
            datasource_luid=config["datasource_luid"],
            auth_ctx=auth_ctx,
            expected_path="step1 → step2 → pipeline",
        )
        complex_results.append(result)
    
    # 7. 测试澄清问题
    logger.info("\n" + "="*60)
    logger.info("测试澄清问题 (step1 → CLARIFY)")
    logger.info("="*60)
    
    clarification_results = []
    for question in TEST_QUESTIONS["clarification"]:
        result = await _run_subgraph_single_question(
            question=question,
            data_model=data_model,
            datasource_luid=config["datasource_luid"],
            auth_ctx=auth_ctx,
            expected_path="step1 → CLARIFY",
        )
        clarification_results.append(result)
    
    # 8. 测试一般性问题
    logger.info("\n" + "="*60)
    logger.info("测试一般性问题 (step1 → END)")
    logger.info("="*60)
    
    general_results = []
    for question in TEST_QUESTIONS["general"]:
        result = await _run_subgraph_single_question(
            question=question,
            data_model=data_model,
            datasource_luid=config["datasource_luid"],
            auth_ctx=auth_ctx,
            expected_path="step1 → END",
        )
        general_results.append(result)
    
    # 9. 测试多轮对话
    try:
        conversation_results = await _run_subgraph_conversation_flow(
            data_model=data_model,
            datasource_luid=config["datasource_luid"],
            auth_ctx=auth_ctx,
        )
    except Exception as e:
        logger.error(f"多轮对话测试失败: {e}")
        conversation_results = []
    
    # 10. 输出测试摘要
    all_results = simple_results + complex_results + clarification_results + general_results
    
    logger.info("\n" + "="*60)
    logger.info("测试摘要")
    logger.info("="*60)
    
    success_count = sum(1 for r in all_results if r.get("success", False))
    logger.info(f"总测试数: {len(all_results)}")
    logger.info(f"成功: {success_count}")
    logger.info(f"失败: {len(all_results) - success_count}")
    
    # 按类别统计
    logger.info(f"\n按类别统计:")
    logger.info(f"  简单查询: {sum(1 for r in simple_results if r.get('success'))} / {len(simple_results)}")
    logger.info(f"  复杂查询: {sum(1 for r in complex_results if r.get('success'))} / {len(complex_results)}")
    logger.info(f"  澄清问题: {sum(1 for r in clarification_results if r.get('success'))} / {len(clarification_results)}")
    logger.info(f"  一般问题: {sum(1 for r in general_results if r.get('success'))} / {len(general_results)}")
    
    if conversation_results:
        logger.info(f"  多轮对话: {sum(1 for r in conversation_results if r.get('success'))} / {len(conversation_results)}")
    
    # 平均耗时
    times = [r.get("elapsed_seconds", 0) for r in all_results if r.get("success")]
    if times:
        avg_time = sum(times) / len(times)
        logger.info(f"\n平均耗时: {avg_time:.2f}s")
    
    # 失败的测试
    failed = [r for r in all_results if not r.get("success")]
    if failed:
        logger.info(f"\n失败的测试:")
        for r in failed:
            logger.info(f"  - {r['question']}: {r.get('error', r.get('actual_path', 'unknown'))}")
    
    # 保存 LLM 响应汇总
    llm_collector.save_summary()
    logger.info(f"\n输出文件:")
    logger.info(f"  日志文件: {LOG_FILE}")
    logger.info(f"  LLM响应文件: {LLM_RESPONSES_FILE}")


# ═══════════════════════════════════════════════════════════════════════════
# 入口
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    asyncio.run(run_all_tests())
