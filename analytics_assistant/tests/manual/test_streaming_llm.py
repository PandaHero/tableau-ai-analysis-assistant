# -*- coding: utf-8 -*-
"""
手动测试：使用真实 Tableau 环境 + 公司内部 DeepSeek R1 流式输出

连接真实 Tableau Server，使用 '销售分析' 数据源，
走完整的语义解析流程并实时展示 thinking + token 输出。

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    python tests/manual/test_streaming_llm.py
"""

import asyncio
import logging
import os
import sys
import time
from datetime import datetime
from typing import Any, Dict, List, Optional

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
    print(f"\n{'═' * 60}")
    print(f"{Colors.BOLD}{Colors.CYAN}  {title}{Colors.RESET}")
    print(f"{'═' * 60}\n")


def print_section(title: str) -> None:
    print(f"\n{Colors.BOLD}{Colors.YELLOW}> {title}{Colors.RESET}")
    print(f"{'─' * 40}")


def print_kv(key: str, value: Any) -> None:
    print(f"  {key:20s} {value}")


# ═══════════════════════════════════════════════════════════════════════════
# 调试输出：中间状态详情
# ═══════════════════════════════════════════════════════════════════════════

def _print_debug_intermediate_state(final_state: Dict[str, Any]) -> None:
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

            # 颜色区分维度/度量
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
        # 打印完整 prompt，加缩进便于阅读
        for line in prompt.split("\n"):
            print(f"  {Colors.DIM}{line}{Colors.RESET}")


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
    print(f"\n\n{Colors.DIM}── {token_count} tokens, {elapsed:.1f}s, "
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

    thinking_parts: List[str] = []
    token_parts: List[str] = []

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

    print(f"\n\n{Colors.DIM}── {elapsed:.1f}s, thinking {len(thinking)} 字符{Colors.RESET}")

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
# 测试 3: 真实 Tableau 环境完整流程
# ═══════════════════════════════════════════════════════════════════════════

async def test_real_tableau_full_pipeline() -> None:
    """使用真实 Tableau 环境 + '销售分析' 数据源，走完整语义解析流程。

    流程：
    1. Tableau 认证
    2. 通过数据源名称查找 LUID
    3. 加载 DataModel（GraphQL）
    4. 构建 WorkflowContext
    5. 编译图并执行完整流程（带流式输出）
    """
    print_header("测试 3: 真实 Tableau 环境完整流程")

    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    from analytics_assistant.src.orchestration.workflow.context import (
        WorkflowContext,
        create_workflow_config,
    )
    from analytics_assistant.src.agents.semantic_parser.graph import (
        compile_semantic_parser_graph,
    )
    from langgraph.checkpoint.memory import MemorySaver

    datasource_name = "销售"
    question = "2025年各地区的销售额环比是多少"  # 去掉"环比",先测试基本功能

    print(f"{Colors.GREEN}数据源: {datasource_name}{Colors.RESET}")
    print(f"{Colors.GREEN}问题:   {question}{Colors.RESET}")

    # ── 阶段 1: Tableau 认证 ──
    print_section("阶段 1: Tableau 认证")
    start = time.time()
    auth = await get_tableau_auth_async()
    elapsed = time.time() - start
    print_kv("认证方式:", auth.auth_method)
    print_kv("站点:", auth.site)
    print_kv("域名:", auth.domain)
    print(f"{Colors.DIM}  耗时: {elapsed:.1f}s{Colors.RESET}")

    # ── 阶段 2: 加载数据模型 ──
    print_section("阶段 2: 加载数据模型")
    start = time.time()

    async with TableauDataLoader() as loader:
        data_model = await loader.load_data_model(
            datasource_name=datasource_name,
            auth=auth,
        )

    elapsed = time.time() - start
    print_kv("数据源 LUID:", data_model.datasource_id)
    print_kv("数据源名称:", data_model.datasource_name or "N/A")

    # 统计字段
    dimensions = [f for f in data_model.fields if f.role == "DIMENSION"]
    measures = [f for f in data_model.fields if f.role == "MEASURE"]
    print_kv("维度字段:", len(dimensions))
    print_kv("度量字段:", len(measures))
    print_kv("逻辑表:", len(data_model.tables) if data_model.tables else 0)
    print(f"{Colors.DIM}  耗时: {elapsed:.1f}s{Colors.RESET}")

    # 显示部分字段
    print(f"\n  {Colors.DIM}维度字段 (前 10):{Colors.RESET}")
    for f in dimensions[:10]:
        print(f"    - {f.name} [{f.data_type}] caption={f.caption or 'N/A'} {f.description or ''}")
    print(f"  {Colors.DIM}度量字段 (前 10):{Colors.RESET}")
    for f in measures[:10]:
        print(f"    - {f.name} [{f.data_type}] caption={f.caption or 'N/A'} {f.description or ''}")
    
    # 显示所有日期相关字段
    print(f"\n  {Colors.DIM}日期相关字段:{Colors.RESET}")
    time_keywords = {"date", "time", "year", "month", "day", "日期", "时间", "年", "月", "日", "dt", "yyyymm"}
    time_data_types = {"date", "datetime", "timestamp"}
    for f in dimensions:
        is_time = False
        if f.data_type and f.data_type.lower() in time_data_types:
            is_time = True
        elif any(kw in f.name.lower() for kw in time_keywords):
            is_time = True
        elif f.caption and any(kw in f.caption.lower() for kw in time_keywords):
            is_time = True
        
        if is_time:
            print(f"    - {f.name} [{f.data_type}] caption={f.caption or 'N/A'}")

    # ── 阶段 3: 构建 WorkflowContext ──
    print_section("阶段 3: 构建 WorkflowContext")
    
    # 创建 VizQL 客户端和平台适配器
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
    
    vizql_client = VizQLClient()
    platform_adapter = TableauAdapter(vizql_client=vizql_client)
    
    ctx = WorkflowContext(
        datasource_luid=data_model.datasource_id,
        data_model=data_model,
        auth=auth,
        current_time=datetime.now().isoformat(),
        platform_adapter=platform_adapter,
    )
    print_kv("datasource_luid:", ctx.datasource_luid)
    print_kv("schema_hash:", ctx.schema_hash[:16] + "...")
    print_kv("has_data_model:", ctx.data_model is not None)
    print_kv("has_auth:", ctx.auth is not None)
    print_kv("has_platform_adapter:", ctx.platform_adapter is not None)

    # ── 阶段 4: 编译并执行完整图 ──
    print_section("阶段 4: 执行完整语义解析图 (带流式输出)")

    # 流式回调
    thinking_parts: List[str] = []
    token_parts: List[str] = []
    first_thinking = True
    first_token = True

    async def on_thinking(text: str) -> None:
        nonlocal first_thinking
        if first_thinking:
            print(f"\n  {Colors.BOLD}[Thinking]{Colors.RESET}")
            first_thinking = False
        thinking_parts.append(text)
        print(f"{Colors.MAGENTA}{text}{Colors.RESET}", end="", flush=True)

    async def on_token(text: str) -> None:
        nonlocal first_token
        if first_token:
            print(f"\n\n  {Colors.BOLD}[Output]{Colors.RESET}")
            first_token = False
        token_parts.append(text)
        print(f"{Colors.GREEN}{text}{Colors.RESET}", end="", flush=True)

    # 编译图
    checkpointer = MemorySaver()
    compiled = compile_semantic_parser_graph(checkpointer=checkpointer)

    # 构建 config（包含 WorkflowContext 和流式回调）
    config = create_workflow_config(
        thread_id=f"test-real-{int(time.time())}",
        context=ctx,
    )
    # 注入流式回调
    config["configurable"]["on_token"] = on_token
    config["configurable"]["on_thinking"] = on_thinking

    # 构建初始 state
    initial_state: Dict[str, Any] = {
        "question": question,
        "datasource_luid": data_model.datasource_id,
        "current_time": datetime.now().isoformat(),
    }

    start = time.time()
    print(f"\n  执行中...")

    final_state = await compiled.ainvoke(initial_state, config)

    elapsed = time.time() - start
    print(f"\n\n{Colors.DIM}── 总耗时 {elapsed:.1f}s{Colors.RESET}")

    # ── 调试：中间状态 ──
    _print_debug_intermediate_state(final_state)

    # ── 打印结果 ──
    print_section("最终结果")

    # 意图路由
    intent = final_state.get("intent_router_output", {})
    print_kv("意图类型:", intent.get("intent_type", "N/A"))
    print_kv("意图置信度:", f"{intent.get('confidence', 0):.2f}")

    # 规则预处理
    pf = final_state.get("prefilter_result", {})
    if pf:
        print_kv("时间提示:", pf.get("time_hints", []))
        print_kv("匹配置信度:", f"{pf.get('match_confidence', 0):.2f}")

    # 语义输出
    semantic = final_state.get("semantic_output", {})
    if semantic:
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

    # 缓存命中
    if final_state.get("cache_hit"):
        print(f"\n  {Colors.YELLOW}⚡ 缓存命中{Colors.RESET}")

    # 优化指标
    metrics = final_state.get("optimization_metrics", {})
    if metrics:
        print(f"\n  {Colors.DIM}优化指标:{Colors.RESET}")
        for k, v in metrics.items():
            print(f"    {k}: {v:.1f}ms" if isinstance(v, float) else f"    {k}: {v}")

    # Thinking 统计
    if thinking_parts:
        full_thinking = "".join(thinking_parts)
        print(f"\n  {Colors.DIM}Thinking: {len(full_thinking)} 字符{Colors.RESET}")

    # ── 阶段 5: 执行 VizQL 查询 ──
    semantic_output_raw = final_state.get("semantic_output")
    semantic_query = final_state.get("semantic_query")
    
    # 如果 semantic_query 不在顶层，尝试从 parse_result 中获取
    if not semantic_query:
        parse_result = final_state.get("parse_result", {})
        semantic_query = parse_result.get("query")
    
    execute_result = None

    if semantic_output_raw and semantic_query:
        print_section("阶段 5: 执行 VizQL 查询")

        # 调试：打印实际发送的 VizQL 查询
        import json as _json
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
                data_model=data_model,  # 传递 data_model 用于构建 field_metadata
                api_key=auth.api_key,
                site=auth.site,
            )
            elapsed = time.time() - start

            print_kv("行数:", execute_result.row_count)
            print_kv("列数:", len(execute_result.columns))
            print_kv("执行耗时:", f"{execute_result.execution_time_ms}ms")
            print(f"{Colors.DIM}  总耗时: {elapsed:.1f}s{Colors.RESET}")

            # 打印列信息
            print(f"\n  {Colors.DIM}列信息:{Colors.RESET}")
            for col in execute_result.columns:
                role = "维度" if col.is_dimension else "度量" if col.is_measure else "计算" if col.is_computation else "未知"
                print(f"    - {col.name} [{col.data_type}] ({role})")

            # 打印前 5 行数据
            if execute_result.data:
                print(f"\n  {Colors.DIM}前 5 行数据:{Colors.RESET}")
                for i, row in enumerate(execute_result.data[:5]):
                    print(f"    [{i}] {row}")
                if execute_result.row_count > 5:
                    print(f"    ... 共 {execute_result.row_count} 行")

        except Exception as e:
            elapsed = time.time() - start
            print(f"  {Colors.RED}查询执行失败: {e}{Colors.RESET}")
            print(f"{Colors.DIM}  耗时: {elapsed:.1f}s{Colors.RESET}")
            logger.exception("VizQL 查询执行失败")
    else:
        print_section("阶段 5: 跳过 (无 semantic_query)")
        if not semantic_output_raw:
            print(f"  {Colors.YELLOW}原因: 缺少 semantic_output{Colors.RESET}")
        if not semantic_query:
            print(f"  {Colors.YELLOW}原因: 缺少 semantic_query{Colors.RESET}")

    # ── 阶段 6: 数据画像 ──
    data_profile = None

    if execute_result and execute_result.row_count > 0:
        print_section("阶段 6: 数据画像 (DataProfiler)")
        start = time.time()

        from analytics_assistant.src.agents.insight.components.data_profiler import DataProfiler

        profiler = DataProfiler()
        data_profile = profiler.generate(execute_result)
        elapsed = time.time() - start

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
    else:
        print_section("阶段 6: 跳过 (无查询结果)")

    # ── 阶段 7: 洞察分析 (Insight Agent) ──
    insight_output = None

    if execute_result and data_profile and execute_result.row_count > 0:
        print_section("阶段 7: 洞察分析 (Insight Agent)")
        start = time.time()

        from analytics_assistant.src.agents.insight.components.data_store import DataStore
        from analytics_assistant.src.agents.insight.graph import run_insight_agent

        # 创建 DataStore 并保存数据
        store = DataStore(store_id=f"test-{int(time.time())}")
        store.save(execute_result)
        store.set_profile(data_profile)

        # 流式回调
        insight_thinking: List[str] = []
        insight_tokens: List[str] = []
        first_insight_thinking = True
        first_insight_token = True

        async def on_insight_thinking(text: str) -> None:
            nonlocal first_insight_thinking
            if first_insight_thinking:
                print(f"\n  {Colors.BOLD}[Insight Thinking]{Colors.RESET}")
                first_insight_thinking = False
            insight_thinking.append(text)
            print(f"{Colors.MAGENTA}{text}{Colors.RESET}", end="", flush=True)

        async def on_insight_token(text: str) -> None:
            nonlocal first_insight_token
            if first_insight_token:
                print(f"\n\n  {Colors.BOLD}[Insight Output]{Colors.RESET}")
                first_insight_token = False
            insight_tokens.append(text)
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

            print(f"\n\n{Colors.DIM}── 洞察耗时 {elapsed:.1f}s{Colors.RESET}")
            print_kv("发现数量:", len(insight_output.findings))
            print_kv("整体置信度:", f"{insight_output.overall_confidence:.2f}")
            print_kv("摘要:", insight_output.summary[:100] + "..." if len(insight_output.summary) > 100 else insight_output.summary)

            for i, finding in enumerate(insight_output.findings, 1):
                print(f"\n  {Colors.BOLD}发现 {i}:{Colors.RESET} [{finding.finding_type.value}/{finding.analysis_level.value}] "
                      f"置信度={finding.confidence:.2f}")
                print(f"    {finding.description[:150]}{'...' if len(finding.description) > 150 else ''}")

        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  {Colors.RED}洞察分析失败: {e}{Colors.RESET}")
            print(f"{Colors.DIM}  耗时: {elapsed:.1f}s{Colors.RESET}")
            logger.exception("Insight Agent 执行失败")
        finally:
            store.cleanup()
    else:
        print_section("阶段 7: 跳过 (无查询结果或数据画像)")

    # ── 阶段 8: 重规划 (Replanner Agent) ──
    if insight_output and semantic_output_raw and data_profile:
        print_section("阶段 8: 重规划 (Replanner Agent)")
        start = time.time()

        from analytics_assistant.src.agents.replanner.graph import run_replanner_agent

        # 流式回调
        replan_thinking: List[str] = []
        replan_tokens: List[str] = []
        first_replan_thinking = True
        first_replan_token = True

        async def on_replan_thinking(text: str) -> None:
            nonlocal first_replan_thinking
            if first_replan_thinking:
                print(f"\n  {Colors.BOLD}[Replanner Thinking]{Colors.RESET}")
                first_replan_thinking = False
            replan_thinking.append(text)
            print(f"{Colors.MAGENTA}{text}{Colors.RESET}", end="", flush=True)

        async def on_replan_token(text: str) -> None:
            nonlocal first_replan_token
            if first_replan_token:
                print(f"\n\n  {Colors.BOLD}[Replanner Output]{Colors.RESET}")
                first_replan_token = False
            replan_tokens.append(text)
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

            print(f"\n\n{Colors.DIM}── 重规划耗时 {elapsed:.1f}s{Colors.RESET}")
            print_kv("是否重规划:", replan_decision.should_replan)
            print_kv("原因:", replan_decision.reason[:100] + "..." if len(replan_decision.reason) > 100 else replan_decision.reason)

            if replan_decision.should_replan and replan_decision.new_question:
                print(f"\n  {Colors.BOLD}新问题:{Colors.RESET} {replan_decision.new_question}")

            if replan_decision.suggested_questions:
                print(f"\n  {Colors.BOLD}建议问题:{Colors.RESET}")
                for i, q in enumerate(replan_decision.suggested_questions, 1):
                    print(f"    {i}. {q}")

        except Exception as e:
            elapsed = time.time() - start
            print(f"\n  {Colors.RED}重规划失败: {e}{Colors.RESET}")
            print(f"{Colors.DIM}  耗时: {elapsed:.1f}s{Colors.RESET}")
            logger.exception("Replanner Agent 执行失败")
    else:
        print_section("阶段 8: 跳过 (缺少前置结果)")
        if not insight_output:
            print(f"  {Colors.YELLOW}原因: 缺少洞察结果{Colors.RESET}")


# ═══════════════════════════════════════════════════════════════════════════
# 主入口
# ═══════════════════════════════════════════════════════════════════════════

async def main() -> None:
    """运行所有测试。"""
    print(f"\n{Colors.BOLD}{'=' * 60}")
    print(f"  公司内部 DeepSeek R1 + 真实 Tableau 流式输出测试")
    print(f"{'=' * 60}{Colors.RESET}")

    # # 测试 1: 简单流式输出
    # try:
    #     await test_simple_stream()
    # except Exception as e:
    #     print(f"\n{Colors.RED}测试 1 失败: {e}{Colors.RESET}")
    #     logger.exception("test_simple_stream failed")

    # # 测试 2: 带 Thinking 的结构化流式输出
    # try:
    #     await test_stream_with_thinking()
    # except Exception as e:
    #     print(f"\n{Colors.RED}测试 2 失败: {e}{Colors.RESET}")
    #     logger.exception("test_stream_with_thinking failed")

    # 测试 3: 完整流程（真实 Tableau + Rerank）
    try:
        await test_real_tableau_full_pipeline()
    except Exception as e:
        print(f"\n{Colors.RED}测试 3 失败: {e}{Colors.RESET}")
        logger.exception("test_real_tableau_full_pipeline failed")

    print(f"\n{Colors.BOLD}{'=' * 60}")
    print(f"  测试完成")
    print(f"{'=' * 60}{Colors.RESET}\n")


if __name__ == "__main__":
    asyncio.run(main())
