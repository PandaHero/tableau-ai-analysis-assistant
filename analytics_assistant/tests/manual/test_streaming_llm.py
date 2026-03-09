# -*- coding: utf-8 -*-
"""
手动测试：使用真实 Tableau 环境 + 公司内部 DeepSeek R1 流式输出

连接真实 Tableau Server，使用 '销售分析' 数据源，
走完整的语义解析流程并实时展示 thinking + token 输出。

支持多问题批量测试，覆盖以下场景：
- 简单聚合查询
- 时间筛选 + 维度分组
- 多维度交叉分析
- 排序 / Top-N
- 计算字段（环比、同比、占比）
- 复杂筛选条件
- 边界情况（模糊表述、无筛选、全量查询）

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    python tests/manual/test_streaming_llm.py

    # 只跑指定问题编号（从 0 开始）
    python tests/manual/test_streaming_llm.py --questions 0 3 5

    # 跳过洞察和重规划阶段（只测语义解析 + 查询执行）
    python tests/manual/test_streaming_llm.py --skip-insight

    # 只跑简单流式测试
    python tests/manual/test_streaming_llm.py --simple-only
"""

import argparse
import asyncio
import json as _json
import logging
import os
import sys
import time
import traceback
from datetime import datetime
from typing import Any, Optional

# 确保项目根目录在 sys.path 中
project_root = os.path.dirname(
    os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
)
if project_root not in sys.path:
    sys.path.insert(0, project_root)

from langchain_core.messages import HumanMessage

from analytics_assistant.src.agents.base.node import (
    get_llm,
    stream_llm,
    stream_llm_structured,
)
from analytics_assistant.src.agents.semantic_parser.schemas.output import SemanticOutput

logging.basicConfig(level=logging.INFO, format="%(name)s - %(levelname)s - %(message)s")
logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 测试问题集
# ═══════════════════════════════════════════════════════════════════════════

# 每个问题包含：question（问题文本）、category（分类）、description（测试目的）
#
# 数据源字段说明（销售数据源，字段名为拼音缩写）：
#   维度: pro_name(省份), shop_nm(门店), dept_nm(部门), class_nm(品类),
#         group_nm(组), subc_nm(子类), div_nm(事业部), matnr_name(商品名),
#         dt(日期,STRING), yyyymm(年月,STRING), shop_id, pro_id, ...
#   度量: netamt(销售额), groplamt(毛利), sale_cost(销售成本),
#         sh_qty(销售数量), sale_weight(销售重量), bf_amt, ef_amt, ...
#
TEST_QUESTIONS: list[dict[str, str]] = [
    # ── 基础聚合 ──
    {
        "question": "各省份的销售额是多少",
        "category": "基础聚合",
        "description": "最简单的维度+度量查询，验证基本链路",
    },
    {
        "question": "总销售额和总毛利分别是多少",
        "category": "基础聚合",
        "description": "无维度的纯聚合查询，多个度量",
    },
    {
        "question": "各部门的销售数量汇总",
        "category": "基础聚合",
        "description": "单维度+单度量，验证 dept_nm + sh_qty 映射",
    },
    # ── 时间筛选 ──
    {
        "question": "2024年每个月的销售额趋势",
        "category": "时间筛选",
        "description": "年份筛选 + 月份维度，验证时间解析和 DATETRUNC",
    },
    {
        "question": "2025年第一季度各部门的毛利",
        "category": "时间筛选",
        "description": "季度时间范围 + 部门维度，验证季度解析",
    },
    # ── 多维度交叉 ──
    {
        "question": "各省份各部门的销售额和毛利",
        "category": "多维度交叉",
        "description": "两个维度 + 两个度量的交叉分析",
    },
    {
        "question": "各事业部在各省份的销售数量",
        "category": "多维度交叉",
        "description": "事业部 × 省份 × 销售数量，验证多维度组合",
    },
    # ── 排序 / Top-N ──
    {
        "question": "销售额最高的前10个商品",
        "category": "排序/Top-N",
        "description": "Top-N 查询，验证排序和限制",
    },
    {
        "question": "哪个省份的毛利最低",
        "category": "排序/Top-N",
        "description": "极值查询，验证排序 + 限制",
    },
    # ── 计算字段 ──
    {
        "question": "各省份的毛利率是多少",
        "category": "计算字段",
        "description": "毛利率 = 毛利/销售额，验证比率计算公式",
    },
    {
        "question": "2024年各月销售额的环比变化",
        "category": "计算字段",
        "description": "环比计算，验证表计算生成",
    },
    # ── 复杂筛选 ──
    {
        "question": "广东省2024年下半年的月度销售额",
        "category": "复杂筛选",
        "description": "省份筛选 + 时间范围筛选 + 月度维度",
    },
    {
        "question": "销售额超过100万的省份有哪些",
        "category": "复杂筛选",
        "description": "度量条件筛选（HAVING 语义）",
    },
    # ── 模糊/自然语言 ──
    {
        "question": "最近半年卖得最好的商品是什么",
        "category": "模糊表述",
        "description": "模糊时间（最近半年）+ 模糊度量（卖得最好）",
    },
    {
        "question": "哪些门店在亏损",
        "category": "模糊表述",
        "description": "隐含筛选条件（毛利<0），验证语义理解",
    },
    # ── 对比分析 ──
    {
        "question": "2024年和2025年各省份销售额对比",
        "category": "对比分析",
        "description": "跨年对比，验证多时间段处理",
    },
]


# ═══════════════════════════════════════════════════════════════════════════
# 颜色输出工具
# ═══════════════════════════════════════════════════════════════════════════

class Colors:
    """终端颜色"""
    CYAN = "\033[96m"
    GREEN = "\033[92m"
    YELLOW = "\033[93m"
    RED = "\033[91m"
    MAGENTA = "\033[95m"
    BOLD = "\033[1m"
    DIM = "\033[2m"
    RESET = "\033[0m"


def print_header(title: str) -> None:
    print(f"\n{'=' * 60}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.RESET}")
    print(f"{'=' * 60}\n")


def print_section(title: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.YELLOW}> {title}{Colors.RESET}")
    print(f"{'-' * 40}")


def print_kv(key: str, value: Any) -> None:
    print(f"  {key:20s} {value}")


def print_result_row(label: str, status: str, elapsed: float, detail: str = "") -> None:
    """打印结果汇总行。"""
    color = Colors.GREEN if status == "PASS" else Colors.RED if status == "FAIL" else Colors.YELLOW
    print(f"  {color}{status:6s}{Colors.RESET} {label:40s} {elapsed:6.1f}s  {detail}")


# ═══════════════════════════════════════════════════════════════════════════
# 调试输出：中间状态详情
# ═══════════════════════════════════════════════════════════════════════════

def _print_debug_intermediate_state(final_state: dict[str, Any]) -> None:
    """打印完整流程的中间状态，用于调试字段匹配和 Prompt 构建。"""

    # ── 1. 规则预处理 (RulePrefilter) ──
    pf = final_state.get("prefilter_result")
    if pf:
        print_section("调试 [1/5] RulePrefilter 规则预处理")
        hints = pf.get("time_hints", [])
        if hints:
            for h in hints:
                print(f"  时间提示: {h.get('original_expression', '')} → "
                      f"{h.get('hint_type', '')} ({h.get('parsed_hint', '')})")
        comps = pf.get("matched_computations", [])
        if comps:
            for c in comps:
                print(f"  计算匹配: {c.get('seed_name', '')} ({c.get('calc_type', '')})")
        print_kv("检测复杂度:", pf.get("detected_complexity", []))
        print_kv("检测语言:", pf.get("detected_language", "N/A"))
        print_kv("匹配置信度:", f"{pf.get('match_confidence', 0):.2f}")

    # ── 2. 特征提取 (FeatureExtractor) ──
    fe = final_state.get("feature_extraction_output")
    if fe:
        print_section("调试 [2/5] FeatureExtractor 特征提取")
        print_kv("required_measures:", fe.get("required_measures", []))
        print_kv("required_dimensions:", fe.get("required_dimensions", []))
        print_kv("time_hints:", fe.get("confirmed_time_hints", []))
        print_kv("computations:", fe.get("confirmed_computations", []))
        print_kv("confidence:", f"{fe.get('confirmation_confidence', 0):.2f}")
        print_kv("is_degraded:", fe.get("is_degraded", False))

    # ── 3. 字段检索 (FieldRetriever) ──
    candidates = final_state.get("field_candidates")
    if candidates:
        print_section("调试 [3/5] FieldRetriever 字段匹配结果")
        print(f"  共 {len(candidates)} 个候选字段:\n")
        for i, c in enumerate(candidates, 1):
            name = c.get("field_name", "?")
            caption = c.get("field_caption", "")
            ftype = c.get("role", "") or c.get("field_type", "?")
            dtype = c.get("data_type", "")
            conf = c.get("confidence", 0)
            source = c.get("source", "?")
            desc = c.get("business_description", "") or c.get("description", "")
            aliases = c.get("aliases", [])

            color = Colors.CYAN if ftype == "dimension" else Colors.GREEN
            print(f"  {color}[{i}] {name}{Colors.RESET}"
                  f"  caption={caption}  role={ftype}  type={dtype}  conf={conf:.2f}  source={source}")
            if desc:
                print(f"      description: {desc}")
            if aliases:
                print(f"      aliases: {aliases}")
            samples = c.get("sample_values", [])
            if samples:
                print(f"      sample_values: {samples}")
            print()

    # ── 4. 动态 Schema (DynamicSchemaBuilder) ──
    ds = final_state.get("dynamic_schema_result")
    if ds:
        print_section("调试 [4/5] DynamicSchemaBuilder 动态 Schema")
        print_kv("modules:", ds.get("modules", []))
        print_kv("computation_types:", ds.get("computation_types", []))
        print_kv("time_expressions:", ds.get("time_expressions", []))

    # ── 5. 最终 Prompt (ModularPromptBuilder) ──
    prompt = final_state.get("modular_prompt")
    if prompt:
        print_section("调试 [5/5] ModularPromptBuilder 最终 Prompt")
        print(f"  Prompt 长度: {len(prompt)} 字符\n")
        for line in prompt.split("\n"):
            print(f"  {Colors.DIM}{line}{Colors.RESET}")


def _print_semantic_output(semantic: dict[str, Any]) -> None:
    """打印语义解析结果。"""
    print(f"\n  {Colors.BOLD}语义理解结果:{Colors.RESET}")
    print_kv("  query_id:", semantic.get("query_id", "N/A"))
    print_kv("  restated:", semantic.get("restated_question", "N/A"))
    print_kv("  clarification:", semantic.get("needs_clarification", "N/A"))

    what = semantic.get("what", {})
    if what:
        ms = what.get("measures", [])
        print_kv("  measures:", [
            m.get("field_name") if isinstance(m, dict) else m for m in ms
        ])

    where = semantic.get("where", {})
    if where:
        ds = where.get("dimensions", [])
        fs = where.get("filters", [])
        print_kv("  dimensions:", [
            d.get("field_name") if isinstance(d, dict) else d for d in ds
        ])
        if fs:
            for f in fs:
                if isinstance(f, dict):
                    print_kv("  filter:", f"{f.get('field_name')} {f.get('operator', '=')} {f.get('values', [])}")
                else:
                    print_kv("  filter:", str(f))

    sc = semantic.get("self_check", {})
    if sc:
        print_kv("  overall:", f"{sc.get('overall_confidence', 'N/A')}")
        print_kv("  field_mapping:", f"{sc.get('field_mapping_confidence', 'N/A')}")
        print_kv("  time_range:", f"{sc.get('time_range_confidence', 'N/A')}")

    comps = semantic.get("computations", [])
    if comps:
        print(f"\n  {Colors.BOLD}计算:{Colors.RESET}")
        for c in comps:
            if isinstance(c, dict):
                print_kv("  ", f"{c.get('name')} ({c.get('calc_type')}): {c.get('formula', '')}")
            else:
                print_kv("  ", str(c))


def _print_execute_result(execute_result: Any) -> None:
    """打印查询执行结果。"""
    print_kv("行数:", execute_result.row_count)
    print_kv("列数:", len(execute_result.columns))
    print_kv("执行耗时:", f"{execute_result.execution_time_ms}ms")

    print(f"\n  {Colors.DIM}列信息:{Colors.RESET}")
    for col in execute_result.columns:
        role = "维度" if col.is_dimension else "度量" if col.is_measure else "计算" if col.is_computation else "未知"
        print(f"    - {col.name} [{col.data_type}] ({role})")

    if execute_result.data:
        print(f"\n  {Colors.DIM}前 5 行数据:{Colors.RESET}")
        for i, row in enumerate(execute_result.data[:5]):
            print(f"    [{i}] {row}")
        if execute_result.row_count > 5:
            print(f"    ... 共 {execute_result.row_count} 行")


# ═══════════════════════════════════════════════════════════════════════════
# 测试 1: 简单流式输出
# ═══════════════════════════════════════════════════════════════════════════

async def test_simple_stream() -> None:
    """简单流式输出，逐 token 打印。"""
    print_header("测试 1: 简单流式输出 (stream_llm)")

    llm = get_llm(agent_name="semantic_parser", model_id="custom-deepseek-r1")
    print(f"{Colors.DIM}模型: {llm.model_name}, API: {llm.api_base}{Colors.RESET}")

    question = "用一句话解释什么是数据仓库"
    messages = [HumanMessage(content=question)]
    print(f"{Colors.GREEN}问题: {question}{Colors.RESET}\n")

    print_section("LLM 输出")
    start = time.time()
    token_count = 0

    async for token in stream_llm(llm, messages):
        print(token, end="", flush=True)
        token_count += 1

    elapsed = time.time() - start
    print(f"\n\n{Colors.DIM}-- {token_count} tokens, {elapsed:.1f}s, "
          f"{token_count / elapsed:.1f} tokens/s{Colors.RESET}")


# ═══════════════════════════════════════════════════════════════════════════
# 测试 2: 带 Thinking 的结构化流式输出
# ═══════════════════════════════════════════════════════════════════════════

async def test_stream_with_thinking() -> None:
    """带 thinking 的结构化流式输出（R1 推理模型）。"""
    print_header("测试 2: 带 Thinking 的结构化流式输出")

    llm = get_llm(
        agent_name="semantic_parser",
        model_id="custom-deepseek-r1",
        enable_json_mode=True,
    )
    print(f"{Colors.DIM}模型: {llm.model_name}, 推理模型: {llm.is_reasoning_model}{Colors.RESET}")

    question = "各地区的销售额"
    messages = [HumanMessage(content=f"""你是一个数据分析助手，负责理解用户的数据查询需求。

可用字段:
- Region (地区) [dimension, string]: 销售地区
- Sales (销售额) [measure, real]: 销售金额

分析用户问题，提取查询信息并以 JSON 格式输出。

用户问题: {question}""")]

    print(f"{Colors.GREEN}问题: {question}{Colors.RESET}")

    thinking_parts: list[str] = []
    token_parts: list[str] = []

    async def on_thinking(text: str) -> None:
        thinking_parts.append(text)
        print(f"{Colors.MAGENTA}{text}{Colors.RESET}", end="", flush=True)

    async def on_token(text: str) -> None:
        token_parts.append(text)
        print(f"{Colors.GREEN}{text}{Colors.RESET}", end="", flush=True)

    start = time.time()
    print_section("Thinking + Output")

    result, thinking = await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=SemanticOutput,
        on_thinking=on_thinking,
        on_token=on_token,
        return_thinking=True,
    )
    elapsed = time.time() - start

    print(f"\n\n{Colors.DIM}-- {elapsed:.1f}s, thinking {len(thinking)} chars{Colors.RESET}")

    print_section("结构化输出")
    print_kv("query_id:", result.query_id)
    print_kv("restated_question:", result.restated_question)
    print_kv("needs_clarification:", result.needs_clarification)
    if result.what:
        print_kv("measures:", [m.field_name for m in result.what.measures])
    if result.where:
        print_kv("dimensions:", [d.field_name for d in result.where.dimensions])
    if result.self_check:
        print_kv("overall_confidence:", f"{result.self_check.overall_confidence:.2f}")


# ═══════════════════════════════════════════════════════════════════════════
# 测试 3: 真实 Tableau 环境完整流程（多问题批量测试）
# ═══════════════════════════════════════════════════════════════════════════

async def _setup_tableau_env() -> tuple:
    """初始化 Tableau 环境：认证 + 数据模型加载 + WorkflowContext。

    Returns:
        (auth, data_model, ctx, platform_adapter, compiled_graph) 元组
    """
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    from analytics_assistant.src.orchestration.workflow.context import (
        WorkflowContext,
        create_workflow_config,
    )
    from analytics_assistant.src.agents.semantic_parser.graph import (
        compile_semantic_parser_graph,
    )
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
    from langgraph.checkpoint.memory import MemorySaver

    datasource_name = "销售"

    # 认证
    print_section("环境准备: Tableau 认证")
    start = time.time()
    auth = await get_tableau_auth_async()
    print_kv("认证方式:", auth.auth_method)
    print(f"{Colors.DIM}  耗时: {time.time() - start:.1f}s{Colors.RESET}")

    # 数据模型加载
    print_section("环境准备: 加载数据模型")
    start = time.time()
    async with TableauDataLoader() as loader:
        data_model = await loader.load_data_model(
            datasource_name=datasource_name,
            auth=auth,
        )
    elapsed = time.time() - start

    dimensions = [f for f in data_model.fields if f.role == "DIMENSION"]
    measures = [f for f in data_model.fields if f.role == "MEASURE"]
    print_kv("数据源 LUID:", data_model.datasource_id)
    print_kv("维度字段:", len(dimensions))
    print_kv("度量字段:", len(measures))
    print(f"{Colors.DIM}  耗时: {elapsed:.1f}s{Colors.RESET}")

    # 显示字段概览
    print(f"\n  {Colors.DIM}维度字段:{Colors.RESET}")
    for f in dimensions:
        print(f"    - {f.name} [{f.data_type}] caption={f.caption or 'N/A'}")
    print(f"  {Colors.DIM}度量字段:{Colors.RESET}")
    for f in measures:
        print(f"    - {f.name} [{f.data_type}] caption={f.caption or 'N/A'}")

    # WorkflowContext
    vizql_client = VizQLClient()
    platform_adapter = TableauAdapter(vizql_client=vizql_client)
    ctx = WorkflowContext(
        datasource_luid=data_model.datasource_id,
        data_model=data_model,
        auth=auth,
        field_samples=getattr(data_model, "_field_samples_cache", None),
        current_time=datetime.now().isoformat(),
        platform_adapter=platform_adapter,
    )
    ctx = await ctx.load_field_semantic(allow_online_inference=False)

    # 编译图
    checkpointer = MemorySaver()
    compiled = compile_semantic_parser_graph(checkpointer=checkpointer)

    return auth, data_model, ctx, platform_adapter, compiled


async def _run_single_question(
    question_info: dict[str, str],
    question_index: int,
    auth: Any,
    data_model: Any,
    ctx: Any,
    platform_adapter: Any,
    compiled: Any,
    skip_insight: bool = False,
    verbose: bool = True,
) -> dict[str, Any]:
    """执行单个问题的完整流程。

    Returns:
        结果字典，包含各阶段的状态和耗时
    """
    from analytics_assistant.src.orchestration.workflow.context import create_workflow_config

    question = question_info["question"]
    category = question_info["category"]
    description = question_info["description"]

    result = {
        "question": question,
        "category": category,
        "description": description,
        "index": question_index,
        "semantic_parse": {"status": "skip", "elapsed": 0.0},
        "query_execute": {"status": "skip", "elapsed": 0.0},
        "data_profile": {"status": "skip", "elapsed": 0.0},
        "insight": {"status": "skip", "elapsed": 0.0},
        "replanner": {"status": "skip", "elapsed": 0.0},
        "errors": [],
    }

    print_header(f"问题 [{question_index}] ({category}): {question}")
    print(f"  {Colors.DIM}测试目的: {description}{Colors.RESET}")

    # ── 阶段 A: 语义解析 ──
    print_section("阶段 A: 语义解析")

    thinking_parts: list[str] = []
    token_parts: list[str] = []
    first_thinking = True
    first_token = True

    async def on_thinking(text: str) -> None:
        nonlocal first_thinking
        if first_thinking:
            print(f"\n  {Colors.BOLD}[Thinking]{Colors.RESET}")
            first_thinking = False
        thinking_parts.append(text)
        if verbose:
            print(f"{Colors.MAGENTA}{text}{Colors.RESET}", end="", flush=True)

    async def on_token(text: str) -> None:
        nonlocal first_token
        if first_token:
            print(f"\n\n  {Colors.BOLD}[Output]{Colors.RESET}")
            first_token = False
        token_parts.append(text)
        if verbose:
            print(f"{Colors.GREEN}{text}{Colors.RESET}", end="", flush=True)

    config = create_workflow_config(
        thread_id=f"test-q{question_index}-{int(time.time())}",
        context=ctx,
    )
    config["configurable"]["on_token"] = on_token
    config["configurable"]["on_thinking"] = on_thinking

    initial_state: dict[str, Any] = {
        "question": question,
        "datasource_luid": data_model.datasource_id,
        "current_time": datetime.now().isoformat(),
    }

    start = time.time()
    try:
        final_state = await compiled.ainvoke(initial_state, config)
        elapsed = time.time() - start
        result["semantic_parse"] = {"status": "pass", "elapsed": elapsed}
        print(f"\n\n{Colors.DIM}-- parse {elapsed:.1f}s{Colors.RESET}")
    except Exception as e:
        elapsed = time.time() - start
        result["semantic_parse"] = {"status": "fail", "elapsed": elapsed}
        result["errors"].append(f"语义解析失败: {e}")
        print(f"\n  {Colors.RED}语义解析失败: {e}{Colors.RESET}")
        logger.exception(f"问题 [{question_index}] 语义解析失败")
        return result

    # 打印中间状态（简略模式）
    if verbose:
        _print_debug_intermediate_state(final_state)

    # 打印语义输出
    semantic = final_state.get("semantic_output", {})
    if semantic:
        _print_semantic_output(semantic)

    # ── 阶段 B: VizQL 查询执行 ──
    semantic_output_raw = final_state.get("semantic_output")
    semantic_query = final_state.get("semantic_query")
    if not semantic_query:
        parse_result = final_state.get("parse_result", {})
        semantic_query = parse_result.get("query")

    execute_result = None

    if semantic_output_raw and semantic_query:
        print_section("阶段 B: VizQL 查询执行")

        if verbose:
            print(f"\n  {Colors.DIM}VizQL 查询:{Colors.RESET}")
            if isinstance(semantic_query, dict):
                print(f"  {_json.dumps(semantic_query, indent=2, ensure_ascii=False)}")
            else:
                print(f"  {semantic_query}")

        start = time.time()
        try:
            semantic_output_obj = SemanticOutput.model_validate(semantic_output_raw)
            execute_result = await platform_adapter.execute_query(
                semantic_output=semantic_output_obj,
                datasource_id=data_model.datasource_id,
                data_model=data_model,
                api_key=auth.api_key,
                site=auth.site,
            )
            elapsed = time.time() - start
            result["query_execute"] = {
                "status": "pass",
                "elapsed": elapsed,
                "row_count": execute_result.row_count,
                "col_count": len(execute_result.columns),
            }
            _print_execute_result(execute_result)
            print(f"{Colors.DIM}  总耗时: {elapsed:.1f}s{Colors.RESET}")

        except Exception as e:
            elapsed = time.time() - start
            result["query_execute"] = {"status": "fail", "elapsed": elapsed}
            result["errors"].append(f"查询执行失败: {e}")
            print(f"  {Colors.RED}查询执行失败: {e}{Colors.RESET}")
            logger.exception(f"问题 [{question_index}] VizQL 查询失败")
    else:
        print_section("阶段 B: 跳过 (无 semantic_query)")
        if not semantic_output_raw:
            print(f"  {Colors.YELLOW}原因: 缺少 semantic_output{Colors.RESET}")
        if not semantic_query:
            needs_clar = semantic.get("needs_clarification", False) if semantic else False
            if needs_clar:
                clar_q = semantic.get("clarification_question", "")
                print(f"  {Colors.YELLOW}原因: LLM 请求澄清 — {clar_q}{Colors.RESET}")
                result["query_execute"] = {"status": "fail", "elapsed": 0.0}
                result["errors"].append(f"LLM 请求澄清: {clar_q}")
            else:
                print(f"  {Colors.YELLOW}原因: 缺少 semantic_query{Colors.RESET}")
                result["query_execute"] = {"status": "fail", "elapsed": 0.0}
                result["errors"].append("语义解析未生成查询")

    if skip_insight:
        return result

    # ── 阶段 C: 数据画像 ──
    data_profile = None

    if execute_result and execute_result.row_count > 0:
        print_section("阶段 C: 数据画像")
        start = time.time()

        from analytics_assistant.src.agents.insight.components.data_profiler import DataProfiler

        profiler = DataProfiler()
        data_profile = profiler.generate(execute_result)
        elapsed = time.time() - start
        result["data_profile"] = {"status": "pass", "elapsed": elapsed}

        print_kv("行数:", data_profile.row_count)
        print_kv("列数:", data_profile.column_count)
        print(f"{Colors.DIM}  耗时: {elapsed:.3f}s{Colors.RESET}")

        for cp in data_profile.columns_profile:
            if cp.is_numeric and cp.numeric_stats:
                stats = cp.numeric_stats
                print(f"    {Colors.GREEN}{cp.column_name}{Colors.RESET} [数值] "
                      f"min={stats.min:.2f} max={stats.max:.2f} avg={stats.avg:.2f}")
            elif cp.categorical_stats:
                stats = cp.categorical_stats
                top_vals = [tv["value"] for tv in stats.top_values[:3]]
                print(f"    {Colors.CYAN}{cp.column_name}{Colors.RESET} [分类] "
                      f"unique={stats.unique_count} top={top_vals}")
            elif cp.error:
                print(f"    {Colors.RED}{cp.column_name}{Colors.RESET} [错误] {cp.error}")

    # ── 阶段 D: 洞察分析 ──
    insight_output = None

    if execute_result and data_profile and execute_result.row_count > 0:
        print_section("阶段 D: 洞察分析 (Insight Agent)")
        start = time.time()

        from analytics_assistant.src.agents.insight.components.data_store import DataStore
        from analytics_assistant.src.agents.insight.graph import run_insight_agent

        store = DataStore(store_id=f"test-q{question_index}-{int(time.time())}")
        store.save(execute_result)
        store.set_profile(data_profile)

        insight_thinking: list[str] = []
        first_insight_thinking = True
        first_insight_token = True

        async def on_insight_thinking(text: str) -> None:
            nonlocal first_insight_thinking
            if first_insight_thinking:
                print(f"\n  {Colors.BOLD}[Insight Thinking]{Colors.RESET}")
                first_insight_thinking = False
            insight_thinking.append(text)
            if verbose:
                print(f"{Colors.MAGENTA}{text}{Colors.RESET}", end="", flush=True)

        async def on_insight_token(text: str) -> None:
            nonlocal first_insight_token
            if first_insight_token:
                print(f"\n\n  {Colors.BOLD}[Insight Output]{Colors.RESET}")
                first_insight_token = False
            if verbose:
                print(f"{Colors.GREEN}{text}{Colors.RESET}", end="", flush=True)

        try:
            insight_output = await run_insight_agent(
                data_store=store,
                data_profile=data_profile,
                semantic_output_dict=semantic_output_raw,
                analysis_depth="detailed",
                on_token=on_insight_token,
                on_thinking=on_insight_thinking,
            )
            elapsed = time.time() - start
            result["insight"] = {
                "status": "pass",
                "elapsed": elapsed,
                "findings_count": len(insight_output.findings),
                "confidence": insight_output.overall_confidence,
            }

            print(f"\n\n{Colors.DIM}-- insight {elapsed:.1f}s{Colors.RESET}")
            print_kv("发现数量:", len(insight_output.findings))
            print_kv("整体置信度:", f"{insight_output.overall_confidence:.2f}")
            summary = insight_output.summary
            print_kv("摘要:", summary[:100] + "..." if len(summary) > 100 else summary)

            for i, finding in enumerate(insight_output.findings, 1):
                print(f"\n  {Colors.BOLD}发现 {i}:{Colors.RESET} "
                      f"[{finding.finding_type.value}/{finding.analysis_level.value}] "
                      f"置信度={finding.confidence:.2f}")
                desc = finding.description
                print(f"    {desc[:150]}{'...' if len(desc) > 150 else ''}")

        except Exception as e:
            elapsed = time.time() - start
            result["insight"] = {"status": "fail", "elapsed": elapsed}
            result["errors"].append(f"洞察分析失败: {e}")
            print(f"\n  {Colors.RED}洞察分析失败: {e}{Colors.RESET}")
            logger.exception(f"问题 [{question_index}] Insight Agent 失败")
        finally:
            store.cleanup()

    # ── 阶段 E: 重规划 ──
    if insight_output and semantic_output_raw and data_profile:
        print_section("阶段 E: 重规划 (Replanner Agent)")
        start = time.time()

        from analytics_assistant.src.agents.replanner.graph import run_replanner_agent

        first_replan_thinking = True
        first_replan_token = True

        async def on_replan_thinking(text: str) -> None:
            nonlocal first_replan_thinking
            if first_replan_thinking:
                print(f"\n  {Colors.BOLD}[Replanner Thinking]{Colors.RESET}")
                first_replan_thinking = False
            if verbose:
                print(f"{Colors.MAGENTA}{text}{Colors.RESET}", end="", flush=True)

        async def on_replan_token(text: str) -> None:
            nonlocal first_replan_token
            if first_replan_token:
                print(f"\n\n  {Colors.BOLD}[Replanner Output]{Colors.RESET}")
                first_replan_token = False
            if verbose:
                print(f"{Colors.GREEN}{text}{Colors.RESET}", end="", flush=True)

        try:
            replan_decision = await run_replanner_agent(
                insight_output_dict=insight_output.model_dump(),
                semantic_output_dict=semantic_output_raw,
                data_profile_dict=data_profile.model_dump(),
                analysis_depth="detailed",
                on_token=on_replan_token,
                on_thinking=on_replan_thinking,
            )
            elapsed = time.time() - start
            result["replanner"] = {
                "status": "pass",
                "elapsed": elapsed,
                "should_replan": replan_decision.should_replan,
            }

            print(f"\n\n{Colors.DIM}-- replan {elapsed:.1f}s{Colors.RESET}")
            print_kv("是否重规划:", replan_decision.should_replan)
            reason = replan_decision.reason
            print_kv("原因:", reason[:100] + "..." if len(reason) > 100 else reason)

            if replan_decision.should_replan and replan_decision.new_question:
                print(f"\n  {Colors.BOLD}新问题:{Colors.RESET} {replan_decision.new_question}")

            if replan_decision.suggested_questions:
                print(f"\n  {Colors.BOLD}建议问题:{Colors.RESET}")
                for i, q in enumerate(replan_decision.suggested_questions, 1):
                    print(f"    {i}. {q}")

        except Exception as e:
            elapsed = time.time() - start
            result["replanner"] = {"status": "fail", "elapsed": elapsed}
            result["errors"].append(f"重规划失败: {e}")
            print(f"\n  {Colors.RED}重规划失败: {e}{Colors.RESET}")
            logger.exception(f"问题 [{question_index}] Replanner Agent 失败")

    return result


# ═══════════════════════════════════════════════════════════════════════════
# 测试 3 主入口
# ═══════════════════════════════════════════════════════════════════════════

async def test_real_tableau_full_pipeline(
    question_indices: Optional[list[int]] = None,
    skip_insight: bool = False,
    verbose: bool = True,
) -> None:
    """使用真实 Tableau 环境批量测试多个问题。

    Args:
        question_indices: 要测试的问题编号列表（None 表示全部）
        skip_insight: 是否跳过洞察和重规划阶段
        verbose: 是否打印详细的 thinking/token 输出
    """
    print_header("测试 3: 真实 Tableau 环境完整流程（多问题批量测试）")

    # 选择要测试的问题
    if question_indices is not None:
        questions = []
        for idx in question_indices:
            if 0 <= idx < len(TEST_QUESTIONS):
                questions.append((idx, TEST_QUESTIONS[idx]))
            else:
                print(f"  {Colors.YELLOW}警告: 问题编号 {idx} 超出范围 (0-{len(TEST_QUESTIONS)-1}){Colors.RESET}")
    else:
        questions = list(enumerate(TEST_QUESTIONS))

    if not questions:
        print(f"  {Colors.RED}没有有效的问题可测试{Colors.RESET}")
        return

    print(f"  共 {len(questions)} 个问题待测试:")
    for idx, q in questions:
        print(f"    [{idx}] ({q['category']}) {q['question']}")
    if skip_insight:
        print(f"  {Colors.YELLOW}跳过洞察和重规划阶段{Colors.RESET}")

    # 初始化环境（只做一次）
    auth, data_model, ctx, platform_adapter, compiled = await _setup_tableau_env()

    # 逐个执行
    all_results: list[dict[str, Any]] = []
    total_start = time.time()

    for idx, question_info in questions:
        try:
            result = await _run_single_question(
                question_info=question_info,
                question_index=idx,
                auth=auth,
                data_model=data_model,
                ctx=ctx,
                platform_adapter=platform_adapter,
                compiled=compiled,
                skip_insight=skip_insight,
                verbose=verbose,
            )
            all_results.append(result)
        except Exception as e:
            print(f"\n  {Colors.RED}问题 [{idx}] 执行异常: {e}{Colors.RESET}")
            logger.exception(f"问题 [{idx}] 执行异常")
            all_results.append({
                "question": question_info["question"],
                "category": question_info["category"],
                "index": idx,
                "errors": [f"执行异常: {e}"],
                "semantic_parse": {"status": "fail", "elapsed": 0.0},
                "query_execute": {"status": "skip", "elapsed": 0.0},
                "data_profile": {"status": "skip", "elapsed": 0.0},
                "insight": {"status": "skip", "elapsed": 0.0},
                "replanner": {"status": "skip", "elapsed": 0.0},
            })

    total_elapsed = time.time() - total_start

    # ── 汇总报告 ──
    _print_summary_report(all_results, total_elapsed, skip_insight)


def _print_summary_report(
    results: list[dict[str, Any]],
    total_elapsed: float,
    skip_insight: bool,
) -> None:
    """打印测试汇总报告。"""
    print_header("测试汇总报告")

    # 表头
    stages = ["语义解析", "查询执行"]
    if not skip_insight:
        stages.extend(["数据画像", "洞察分析", "重规划"])

    header = f"  {'#':>3s}  {'状态':6s}  {'问题':40s}  "
    header += "  ".join(f"{s:8s}" for s in stages)
    header += f"  {'错误':s}"
    print(header)
    print(f"  {'-' * (len(header) + 20)}")

    pass_count = 0
    fail_count = 0
    skip_count = 0

    for r in results:
        idx = r.get("index", "?")
        q = r.get("question", "?")
        if len(q) > 38:
            q = q[:35] + "..."
        errors = r.get("errors", [])

        # 判断整体状态
        stage_keys = ["semantic_parse", "query_execute"]
        if not skip_insight:
            stage_keys.extend(["data_profile", "insight", "replanner"])

        has_fail = any(r.get(k, {}).get("status") == "fail" for k in stage_keys)
        has_pass = any(r.get(k, {}).get("status") == "pass" for k in stage_keys)

        if has_fail:
            overall = "FAIL"
            fail_count += 1
            color = Colors.RED
        elif has_pass:
            overall = "PASS"
            pass_count += 1
            color = Colors.GREEN
        else:
            overall = "SKIP"
            skip_count += 1
            color = Colors.YELLOW

        # 各阶段状态
        stage_strs = []
        for k in stage_keys:
            s = r.get(k, {})
            status = s.get("status", "skip")
            elapsed = s.get("elapsed", 0.0)
            if status == "pass":
                stage_strs.append(f"{Colors.GREEN}OK{elapsed:5.1f}s{Colors.RESET}")
            elif status == "fail":
                stage_strs.append(f"{Colors.RED}NG{elapsed:5.1f}s{Colors.RESET}")
            else:
                stage_strs.append(f"{Colors.DIM}  -    {Colors.RESET}")

        error_str = ""
        if errors:
            # 只显示第一个错误的前 50 字符
            error_str = f"{Colors.RED}{errors[0][:50]}{Colors.RESET}"

        print(f"  {idx:>3}  {color}{overall:6s}{Colors.RESET}  {q:40s}  "
              + "  ".join(stage_strs)
              + f"  {error_str}")

    # 统计
    print(f"\n  {'-' * 60}")
    total = len(results)
    print(f"  总计: {total} 个问题  "
          f"{Colors.GREEN}通过: {pass_count}{Colors.RESET}  "
          f"{Colors.RED}失败: {fail_count}{Colors.RESET}  "
          f"{Colors.YELLOW}跳过: {skip_count}{Colors.RESET}  "
          f"总耗时: {total_elapsed:.1f}s")

    # 失败详情
    failed = [r for r in results if r.get("errors")]
    if failed:
        print(f"\n  {Colors.RED}{Colors.BOLD}失败详情:{Colors.RESET}")
        for r in failed:
            idx = r.get("index", "?")
            q = r.get("question", "?")
            print(f"\n  [{idx}] {q}")
            for err in r.get("errors", []):
                print(f"    {Colors.RED}→ {err}{Colors.RESET}")

    # 查询结果统计
    executed = [r for r in results if r.get("query_execute", {}).get("status") == "pass"]
    if executed:
        print(f"\n  {Colors.BOLD}查询结果统计:{Colors.RESET}")
        for r in executed:
            idx = r.get("index", "?")
            q = r.get("question", "?")
            qe = r.get("query_execute", {})
            rows = qe.get("row_count", 0)
            cols = qe.get("col_count", 0)
            elapsed = qe.get("elapsed", 0.0)
            print(f"    [{idx}] {rows:>5d} 行 × {cols} 列  {elapsed:5.1f}s  {q[:40]}")


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

def parse_args() -> argparse.Namespace:
    """解析命令行参数。"""
    parser = argparse.ArgumentParser(
        description="Analytics Assistant 流式输出 + 完整流程测试"
    )
    parser.add_argument(
        "--questions", "-q",
        nargs="*",
        type=int,
        default=None,
        help="要测试的问题编号（从 0 开始），不指定则测试全部",
    )
    parser.add_argument(
        "--skip-insight",
        action="store_true",
        help="跳过洞察和重规划阶段（只测语义解析 + 查询执行）",
    )
    parser.add_argument(
        "--simple-only",
        action="store_true",
        help="只运行简单流式测试（测试 1 和 2）",
    )
    parser.add_argument(
        "--quiet", "-Q",
        action="store_true",
        help="安静模式：不打印 thinking/token 流式输出",
    )
    parser.add_argument(
        "--list",
        action="store_true",
        help="列出所有可用的测试问题",
    )
    return parser.parse_args()


async def main() -> None:
    """运行所有测试。"""
    args = parse_args()

    # 列出问题
    if args.list:
        print(f"\n{Colors.BOLD}可用测试问题:{Colors.RESET}\n")
        for i, q in enumerate(TEST_QUESTIONS):
            print(f"  [{i:>2d}] ({q['category']:8s}) {q['question']}")
            print(f"       {Colors.DIM}{q['description']}{Colors.RESET}")
        print(f"\n  共 {len(TEST_QUESTIONS)} 个问题\n")
        return

    print(f"\n{Colors.BOLD}{'=' * 60}")
    print(f"  公司内部 DeepSeek R1 + 真实 Tableau 流式输出测试")
    print(f"{'=' * 60}{Colors.RESET}")

    if args.simple_only:
        # 只跑简单测试
        try:
            await test_simple_stream()
        except Exception as e:
            print(f"\n{Colors.RED}测试 1 失败: {e}{Colors.RESET}")
            logger.exception("test_simple_stream failed")

        try:
            await test_stream_with_thinking()
        except Exception as e:
            print(f"\n{Colors.RED}测试 2 失败: {e}{Colors.RESET}")
            logger.exception("test_stream_with_thinking failed")
    else:
        # 完整流程测试
        try:
            await test_real_tableau_full_pipeline(
                question_indices=args.questions,
                skip_insight=args.skip_insight,
                verbose=not args.quiet,
            )
        except Exception as e:
            print(f"\n{Colors.RED}测试 3 失败: {e}{Colors.RESET}")
            logger.exception("test_real_tableau_full_pipeline failed")

    print(f"\n{Colors.BOLD}{'=' * 60}")
    print(f"  测试完成")
    print(f"{'=' * 60}{Colors.RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
