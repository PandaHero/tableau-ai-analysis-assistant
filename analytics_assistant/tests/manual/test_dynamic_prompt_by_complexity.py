# -*- coding: utf-8 -*-
"""
测试不同 ComplexityType 下生成的动态 Prompt - 使用真实 Tableau 环境

运行方式：
    $env:PYTHONPATH = "."
    python analytics_assistant/tests/manual/test_dynamic_prompt_by_complexity.py

功能：
1. 连接真实 Tableau 环境
2. 针对不同 ComplexityType 生成动态 Prompt
3. 记录每个节点的输入输出
4. 调用 LLM 获取输出
5. 将完整流程保存到文档
"""

import asyncio
import json
import logging
import os
import sys
from datetime import date
from typing import Any, Dict, List, Optional

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))))

from dotenv import load_dotenv
load_dotenv()

logging.basicConfig(level=logging.INFO, format='%(asctime)s - %(name)s - %(levelname)s - %(message)s')
logger = logging.getLogger(__name__)

TEST_QUESTIONS = [
    {"name": "SIMPLE - 简单聚合", "question": "各省份的销售额是多少？", "expected": "simple"},
    {"name": "RATIO - 比率计算", "question": "各省份的毛利率是多少？", "expected": "ratio"},
    {"name": "TIME_COMPARE - 同比", "question": "各省份销售额的同比增长率是多少？", "expected": "time_compare"},
    {"name": "RANK - 排名", "question": "销售额排名前10的省份有哪些？", "expected": "rank"},
    {"name": "SHARE - 占比", "question": "各省份销售额占总销售额的比例是多少？", "expected": "share"},
    {"name": "CUMULATIVE - 累计", "question": "按月份计算累计销售额", "expected": "cumulative"},
    {"name": "SUBQUERY - 子查询", "question": "销售额超过平均值的省份有哪些？", "expected": "subquery"},
]


def get_tableau_config() -> Dict[str, str]:
    return {
        "domain": os.getenv("TABLEAU_DOMAIN", ""),
        "site": os.getenv("TABLEAU_SITE", ""),
        "datasource_luid": os.getenv("DATASOURCE_LUID", ""),
    }


async def get_tableau_auth_context():
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    auth_ctx = await get_tableau_auth_async()
    logger.info(f"获取 Tableau 认证成功 (方式: {auth_ctx.auth_method})")
    return auth_ctx


async def get_data_model(auth_ctx, datasource_luid: str):
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    
    async with VizQLClient() as client:
        loader = TableauDataLoader(client=client)
        data_model = await loader.load_data_model(
            datasource_id=datasource_luid,
            auth=auth_ctx,
        )
    
    logger.info(f"加载数据模型: {data_model.field_count} 个字段")
    return data_model


async def call_llm(prompt: str) -> Any:
    """调用 LLM 获取输出"""
    from langchain_core.messages import HumanMessage
    from analytics_assistant.src.agents.base.node import get_llm, stream_llm_structured
    from analytics_assistant.src.agents.semantic_parser.schemas.output import SemanticOutput
    
    llm = get_llm(agent_name="semantic_parser", enable_json_mode=True)
    messages = [HumanMessage(content=prompt)]
    
    result = await stream_llm_structured(
        llm=llm,
        messages=messages,
        output_model=SemanticOutput,
        return_thinking=False,
    )
    
    return result


async def test_single_question(
    question: str, 
    name: str, 
    expected: str, 
    data_model, 
    datasource_luid: str,
    call_llm_flag: bool = True,
) -> Dict[str, Any]:
    """测试单个问题，记录每个节点的输入输出"""
    from analytics_assistant.src.agents.semantic_parser.components.rule_prefilter import RulePrefilter
    from analytics_assistant.src.agents.semantic_parser.components.feature_extractor import FeatureExtractor
    from analytics_assistant.src.agents.semantic_parser.components.field_retriever import FieldRetriever
    from analytics_assistant.src.agents.semantic_parser.components.dynamic_schema_builder import DynamicSchemaBuilder
    from analytics_assistant.src.agents.semantic_parser.prompts.prompt_builder import DynamicPromptBuilder
    from analytics_assistant.src.agents.semantic_parser.schemas.config import SemanticConfig
    from analytics_assistant.src.agents.semantic_parser.schemas.prefilter import FeatureExtractionOutput
    
    print(f"\n{'═' * 100}")
    print(f"【{name}】")
    print(f"问题: {question}")
    print(f"预期 ComplexityType: {expected}")
    print(f"{'═' * 100}")
    
    current_date = date.today()
    result_data = {
        "name": name,
        "question": question,
        "expected": expected,
        "current_date": str(current_date),
    }
    
    # ═══════════════════════════════════════════════════════════════════════
    # 阶段 1: RulePrefilter
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n[Stage 1] RulePrefilter")
    prefilter = RulePrefilter(current_date=current_date)
    prefilter_result = prefilter.prefilter(question)
    
    # 记录 RulePrefilter 输入输出
    result_data["stage1_rule_prefilter"] = {
        "input": {
            "question": question,
            "current_date": str(current_date),
        },
        "output": {
            "detected_complexity": [c.value for c in prefilter_result.detected_complexity],
            "matched_computations": [
                {
                    "seed_name": comp.seed_name,
                    "display_name": comp.display_name,
                    "calc_type": comp.calc_type,
                    "formula": comp.formula,
                    "keywords_matched": comp.keywords_matched,
                }
                for comp in prefilter_result.matched_computations
            ],
            "time_hints": [
                {
                    "original_expression": hint.original_expression,
                    "hint_type": hint.hint_type.value if hint.hint_type else None,
                    "resolved_range": str(hint.resolved_range) if hint.resolved_range else None,
                }
                for hint in prefilter_result.time_hints
            ],
            "match_confidence": prefilter_result.match_confidence,
        },
    }
    
    print(f"  输入:")
    print(f"    - question: {question}")
    print(f"    - current_date: {current_date}")
    print(f"  输出:")
    print(f"    - detected_complexity: {[c.value for c in prefilter_result.detected_complexity]}")
    print(f"    - matched_computations: {len(prefilter_result.matched_computations)} 个")
    print(f"    - time_hints: {len(prefilter_result.time_hints)} 个")
    print(f"    - match_confidence: {prefilter_result.match_confidence:.2f}")
    if prefilter_result.matched_computations:
        for comp in prefilter_result.matched_computations:
            print(f"      - {comp.display_name} ({comp.calc_type}): {comp.formula}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 阶段 2: FeatureExtractor
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n[Stage 2] FeatureExtractor")
    print(f"  说明: 使用快速 LLM 验证 RulePrefilter 结果，提取字段需求")
    print(f"  超时设置: 500ms（超时后降级到规则结果）")
    
    extractor = FeatureExtractor()
    
    # 记录输入
    feature_extractor_input = {
        "question": question,
        "prefilter_result": {
            "detected_complexity": [c.value for c in prefilter_result.detected_complexity],
            "matched_computations_count": len(prefilter_result.matched_computations),
            "time_hints_count": len(prefilter_result.time_hints),
        },
    }
    
    try:
        feature_output = await extractor.extract(question=question, prefilter_result=prefilter_result)
        feature_extractor_success = True
    except Exception as e:
        logger.warning(f"FeatureExtractor 失败: {e}")
        feature_output = FeatureExtractionOutput(is_degraded=True)
        feature_extractor_success = False
    
    result_data["stage2_feature_extractor"] = {
        "input": feature_extractor_input,
        "output": {
            "required_measures": feature_output.required_measures,
            "required_dimensions": feature_output.required_dimensions,
            "confirmed_time_hints": feature_output.confirmed_time_hints,
            "confirmed_computations": feature_output.confirmed_computations,
            "confirmation_confidence": feature_output.confirmation_confidence,
            "is_degraded": feature_output.is_degraded,
        },
        "success": feature_extractor_success,
    }
    
    print(f"  输入:")
    print(f"    - question: {question}")
    print(f"    - prefilter_result.detected_complexity: {[c.value for c in prefilter_result.detected_complexity]}")
    print(f"  输出:")
    print(f"    - required_measures: {feature_output.required_measures}")
    print(f"    - required_dimensions: {feature_output.required_dimensions}")
    print(f"    - confirmed_time_hints: {feature_output.confirmed_time_hints}")
    print(f"    - confirmed_computations: {feature_output.confirmed_computations}")
    print(f"    - is_degraded: {feature_output.is_degraded}")
    if feature_output.is_degraded:
        print(f"    [WARN] 降级模式: LLM 调用超时或失败，使用 RulePrefilter 结果作为降级方案")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 阶段 3: FieldRetriever
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n[Stage 3] FieldRetriever")
    print(f"  说明: 根据 FeatureExtractor 输出检索相关字段")
    
    retriever = FieldRetriever()
    
    # 记录输入
    field_retriever_input = {
        "feature_output": {
            "required_measures": feature_output.required_measures,
            "required_dimensions": feature_output.required_dimensions,
            "is_degraded": feature_output.is_degraded,
        },
        "data_model_field_count": data_model.field_count,
        "datasource_luid": datasource_luid,
    }
    
    field_rag_result = await retriever.retrieve(
        feature_output=feature_output, 
        data_model=data_model, 
        datasource_luid=datasource_luid
    )
    
    result_data["stage3_field_retriever"] = {
        "input": field_retriever_input,
        "output": {
            "measures": [
                {"field_name": f.field_name, "data_type": f.data_type}
                for f in field_rag_result.measures
            ],
            "dimensions": [
                {"field_name": f.field_name, "data_type": f.data_type}
                for f in field_rag_result.dimensions
            ],
            "time_fields": [
                {"field_name": f.field_name, "data_type": f.data_type}
                for f in field_rag_result.time_fields
            ],
            "measures_count": len(field_rag_result.measures),
            "dimensions_count": len(field_rag_result.dimensions),
            "time_fields_count": len(field_rag_result.time_fields),
        },
    }
    
    print(f"  输入:")
    print(f"    - feature_output.required_measures: {feature_output.required_measures}")
    print(f"    - feature_output.required_dimensions: {feature_output.required_dimensions}")
    print(f"    - feature_output.is_degraded: {feature_output.is_degraded}")
    print(f"    - data_model.field_count: {data_model.field_count}")
    print(f"  输出:")
    print(f"    - measures: {len(field_rag_result.measures)} 个")
    print(f"    - dimensions: {len(field_rag_result.dimensions)} 个")
    print(f"    - time_fields: {len(field_rag_result.time_fields)} 个")
    if feature_output.is_degraded:
        print(f"    [WARN] 由于 FeatureExtractor 降级，使用 fallback 字段（前 N 个字段）")

    
    # ═══════════════════════════════════════════════════════════════════════
    # 阶段 4: DynamicSchemaBuilder
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n[Stage 4] DynamicSchemaBuilder")
    print(f"  说明: 根据 ComplexityType 裁剪 JSON Schema，只保留需要的字段")
    
    schema_builder = DynamicSchemaBuilder()
    
    # 记录输入
    schema_builder_input = {
        "feature_output": {
            "required_measures": feature_output.required_measures,
            "required_dimensions": feature_output.required_dimensions,
            "is_degraded": feature_output.is_degraded,
        },
        "field_rag_result": {
            "measures_count": len(field_rag_result.measures),
            "dimensions_count": len(field_rag_result.dimensions),
            "time_fields_count": len(field_rag_result.time_fields),
        },
        "prefilter_result": {
            "detected_complexity": [c.value for c in prefilter_result.detected_complexity],
            "matched_computations_count": len(prefilter_result.matched_computations),
        },
    }
    
    schema_result = schema_builder.build(
        feature_output=feature_output, 
        field_rag_result=field_rag_result, 
        prefilter_result=prefilter_result
    )
    
    result_data["stage4_dynamic_schema_builder"] = {
        "input": schema_builder_input,
        "output": {
            "detected_complexity": [c.value for c in schema_result.detected_complexity],
            "modules": [m.value for m in schema_result.modules],
            "allowed_calc_types": schema_result.allowed_calc_types,
            "schema_json_length": len(schema_result.schema_json),
            "schema_json": schema_result.schema_json if schema_result.schema_json else "(空 - SIMPLE 类型不需要 Schema)",
            "field_candidates_count": len(schema_result.field_candidates),
        },
    }
    
    print(f"  输入:")
    print(f"    - prefilter_result.detected_complexity: {[c.value for c in prefilter_result.detected_complexity]}")
    print(f"    - prefilter_result.matched_computations: {len(prefilter_result.matched_computations)} 个")
    print(f"    - field_rag_result: {len(field_rag_result.measures)} measures, {len(field_rag_result.dimensions)} dimensions")
    print(f"  输出:")
    print(f"    - detected_complexity: {[c.value for c in schema_result.detected_complexity]}")
    print(f"    - modules: {[m.value for m in schema_result.modules]}")
    print(f"    - allowed_calc_types: {schema_result.allowed_calc_types}")
    print(f"    - schema_json 长度: {len(schema_result.schema_json)} 字符")
    print(f"    - field_candidates: {len(schema_result.field_candidates)} 个")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 阶段 5: DynamicPromptBuilder
    # ═══════════════════════════════════════════════════════════════════════
    print(f"\n[Stage 5] DynamicPromptBuilder")
    print(f"  说明: 根据所有前置节点的输出构建最终 Prompt")
    
    prompt_builder = DynamicPromptBuilder()
    config = SemanticConfig(
        current_date=current_date, 
        timezone="Asia/Shanghai", 
        max_schema_tokens=2000, 
        max_few_shot_examples=3
    )
    
    # 记录输入
    prompt_builder_input = {
        "question": question,
        "config": {
            "current_date": str(config.current_date),
            "timezone": config.timezone,
            "max_schema_tokens": config.max_schema_tokens,
            "max_few_shot_examples": config.max_few_shot_examples,
        },
        "field_candidates_count": len(schema_result.field_candidates),
        "schema_json_length": len(schema_result.schema_json),
        "detected_complexity": [c.value for c in schema_result.detected_complexity],
        "allowed_calc_types": schema_result.allowed_calc_types,
        "prefilter_matched_computations": [
            comp.display_name for comp in prefilter_result.matched_computations
        ],
    }
    
    prompt = prompt_builder.build(
        question=question, 
        config=config, 
        field_candidates=schema_result.field_candidates,
        schema_json=schema_result.schema_json, 
        detected_complexity=schema_result.detected_complexity,
        allowed_calc_types=schema_result.allowed_calc_types, 
        prefilter_result=prefilter_result, 
        feature_output=feature_output,
    )
    
    result_data["stage5_dynamic_prompt_builder"] = {
        "input": prompt_builder_input,
        "output": {
            "prompt_length": len(prompt),
            "prompt_tokens_estimate": len(prompt) // 2,
            "prompt": prompt,
        },
    }
    
    print(f"  输入:")
    print(f"    - question: {question}")
    print(f"    - config.current_date: {config.current_date}")
    print(f"    - field_candidates: {len(schema_result.field_candidates)} 个")
    print(f"    - schema_json: {len(schema_result.schema_json)} 字符")
    print(f"    - detected_complexity: {[c.value for c in schema_result.detected_complexity]}")
    print(f"    - allowed_calc_types: {schema_result.allowed_calc_types}")
    print(f"    - prefilter_matched_computations: {[comp.display_name for comp in prefilter_result.matched_computations]}")
    print(f"  输出:")
    print(f"    - prompt_length: {len(prompt)} 字符 (~{len(prompt) // 2} tokens)")
    
    print(f"\n{'─' * 100}")
    print(f"[Note] 生成的完整 Prompt")
    print(f"{'─' * 100}")
    print(prompt)
    print(f"{'─' * 100}")
    
    # ═══════════════════════════════════════════════════════════════════════
    # 阶段 6: 调用 LLM
    # ═══════════════════════════════════════════════════════════════════════
    llm_output_json: str = ""
    
    if call_llm_flag:
        print(f"\n[Stage 6] 调用 LLM (SemanticUnderstanding)")
        print(f"  说明: 将 Prompt 发送给 LLM，获取结构化输出")
        
        try:
            llm_result = await call_llm(prompt)
            # 转换为 JSON 字符串（排除系统字段）
            llm_output = llm_result.model_dump(
                exclude={"query_id", "parent_query_id", "clarification_source", "parsing_warnings"},
                exclude_none=True,
            )
            llm_output_json = json.dumps(llm_output, ensure_ascii=False, indent=2)
            
            result_data["stage6_llm_output"] = {
                "success": True,
                "output": llm_output,
            }
            
            print(f"  [OK] LLM 调用成功")
            print(f"\n[Output] LLM 输出:")
            print(llm_output_json)
        except Exception as e:
            logger.error(f"LLM 调用失败: {e}", exc_info=True)
            llm_output_json = f"错误: {str(e)}"
            result_data["stage6_llm_output"] = {
                "success": False,
                "error": str(e),
            }
            print(f"  [FAIL] LLM 调用失败: {e}")
    else:
        result_data["stage6_llm_output"] = {"skipped": True}
    
    # 汇总结果
    result_data["actual"] = [c.value for c in schema_result.detected_complexity]
    result_data["prompt_length"] = len(prompt)
    result_data["schema_length"] = len(schema_result.schema_json)
    result_data["prompt"] = prompt
    result_data["llm_output"] = llm_output_json
    
    return result_data



def format_stage_for_markdown(stage_name: str, stage_data: Dict[str, Any]) -> List[str]:
    """将阶段数据格式化为 Markdown"""
    lines = []
    lines.append(f"#### {stage_name}\n\n")
    
    if "input" in stage_data:
        lines.append("**输入:**\n")
        lines.append("```json\n")
        lines.append(json.dumps(stage_data["input"], ensure_ascii=False, indent=2))
        lines.append("\n```\n\n")
    
    if "output" in stage_data:
        lines.append("**输出:**\n")
        lines.append("```json\n")
        # 对于 prompt，单独处理
        output_data = stage_data["output"].copy() if isinstance(stage_data["output"], dict) else stage_data["output"]
        if isinstance(output_data, dict) and "prompt" in output_data:
            prompt = output_data.pop("prompt")
            lines.append(json.dumps(output_data, ensure_ascii=False, indent=2))
            lines.append("\n```\n\n")
            lines.append("**生成的 Prompt:**\n")
            lines.append("```\n")
            lines.append(prompt)
            lines.append("\n```\n\n")
        else:
            lines.append(json.dumps(output_data, ensure_ascii=False, indent=2))
            lines.append("\n```\n\n")
    
    if "success" in stage_data:
        status = "[OK]" if stage_data["success"] else "[FAIL]"
        lines.append(f"**状态:** {status}\n\n")
    
    if "error" in stage_data:
        lines.append(f"**错误:** {stage_data['error']}\n\n")
    
    return lines


async def run_all_tests():
    from datetime import datetime
    from pathlib import Path
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    
    # 输出文件 - 使用相对于当前脚本的路径
    script_dir = Path(__file__).parent
    output_dir = script_dir.parent / "test_outputs"
    output_dir.mkdir(exist_ok=True)
    output_file = output_dir / f"dynamic_prompt_test_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    
    lines = []
    lines.append("# 动态 Prompt 完整流程测试 - 使用真实 Tableau 环境\n\n")
    lines.append(f"测试时间: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n\n")
    
    # 添加流程说明
    lines.append("## 流程概述\n\n")
    lines.append("```\n")
    lines.append("用户问题\n")
    lines.append("    │\n")
    lines.append("    ▼\n")
    lines.append("┌─────────────────────────────────────────────────────────────┐\n")
    lines.append("│ 阶段 1: RulePrefilter                                       │\n")
    lines.append("│ - 规则匹配检测 ComplexityType                               │\n")
    lines.append("│ - 提取时间提示和计算种子                                    │\n")
    lines.append("└─────────────────────────────────────────────────────────────┘\n")
    lines.append("    │\n")
    lines.append("    ▼\n")
    lines.append("┌─────────────────────────────────────────────────────────────┐\n")
    lines.append("│ 阶段 2: FeatureExtractor                                    │\n")
    lines.append("│ - 快速 LLM 验证（500ms 超时）                               │\n")
    lines.append("│ - 提取 required_measures/dimensions                         │\n")
    lines.append("│ - 超时则降级到规则结果                                      │\n")
    lines.append("└─────────────────────────────────────────────────────────────┘\n")
    lines.append("    │\n")
    lines.append("    ▼\n")
    lines.append("┌─────────────────────────────────────────────────────────────┐\n")
    lines.append("│ 阶段 3: FieldRetriever                                      │\n")
    lines.append("│ - 根据 required_measures/dimensions 检索字段                │\n")
    lines.append("│ - 降级模式下使用 fallback 字段                              │\n")
    lines.append("└─────────────────────────────────────────────────────────────┘\n")
    lines.append("    │\n")
    lines.append("    ▼\n")
    lines.append("┌─────────────────────────────────────────────────────────────┐\n")
    lines.append("│ 阶段 4: DynamicSchemaBuilder                                │\n")
    lines.append("│ - 根据 ComplexityType 裁剪 JSON Schema                      │\n")
    lines.append("│ - 限制 calc_type 枚举值                                     │\n")
    lines.append("└─────────────────────────────────────────────────────────────┘\n")
    lines.append("    │\n")
    lines.append("    ▼\n")
    lines.append("┌─────────────────────────────────────────────────────────────┐\n")
    lines.append("│ 阶段 5: DynamicPromptBuilder                                │\n")
    lines.append("│ - 组装最终 Prompt                                           │\n")
    lines.append("│ - 包含字段、Schema、计算提示等                              │\n")
    lines.append("└─────────────────────────────────────────────────────────────┘\n")
    lines.append("    │\n")
    lines.append("    ▼\n")
    lines.append("┌─────────────────────────────────────────────────────────────┐\n")
    lines.append("│ 阶段 6: LLM 调用                                            │\n")
    lines.append("│ - 发送 Prompt 给 LLM                                        │\n")
    lines.append("│ - 获取结构化 SemanticOutput                                 │\n")
    lines.append("└─────────────────────────────────────────────────────────────┘\n")
    lines.append("```\n\n")
    lines.append("---\n\n")
    
    print("=" * 100)
    print("动态 Prompt 完整流程测试 - 使用真实 Tableau 环境")
    print("=" * 100)
    
    config = get_tableau_config()
    if not config["domain"]:
        logger.error("请配置 TABLEAU_DOMAIN 环境变量")
        return
    
    datasource_luid = config["datasource_luid"]
    logger.info(f"Tableau Domain: {config['domain']}, Site: {config['site']}")
    
    auth_ctx = await get_tableau_auth_context()
    
    # 如果没有配置 datasource_luid，通过名称获取
    if not datasource_luid:
        datasource_name = "正大益生"
        logger.info(f"通过名称查找数据源: {datasource_name}")
        
        async with VizQLClient() as client:
            datasource_luid = await client.get_datasource_luid_by_name(
                datasource_name=datasource_name,
                api_key=auth_ctx.api_key,
            )
        
        if not datasource_luid:
            logger.error(f"找不到数据源: {datasource_name}")
            return
    
    logger.info(f"Datasource LUID: {datasource_luid}")
    data_model = await get_data_model(auth_ctx, datasource_luid)
    
    results = []
    for tc in TEST_QUESTIONS:
        try:
            result = await test_single_question(
                tc["question"], 
                tc["name"], 
                tc["expected"], 
                data_model, 
                datasource_luid,
                call_llm_flag=True,
            )
            results.append(result)
            
            # 写入详细结果
            lines.append(f"## {result['name']}\n\n")
            lines.append(f"**问题**: {result['question']}\n\n")
            lines.append(f"**预期 ComplexityType**: {result['expected']}\n\n")
            lines.append(f"**实际 ComplexityType**: {', '.join(result['actual'])}\n\n")
            
            # 阶段 1
            lines.extend(format_stage_for_markdown(
                "阶段 1: RulePrefilter", 
                result.get("stage1_rule_prefilter", {})
            ))
            
            # 阶段 2
            stage2 = result.get("stage2_feature_extractor", {})
            lines.extend(format_stage_for_markdown(
                "阶段 2: FeatureExtractor", 
                stage2
            ))
            if stage2.get("output", {}).get("is_degraded"):
                lines.append("> [WARN] **降级模式**: FeatureExtractor 超时（500ms），使用 RulePrefilter 结果作为降级方案\n\n")
            
            # 阶段 3
            lines.extend(format_stage_for_markdown(
                "阶段 3: FieldRetriever", 
                result.get("stage3_field_retriever", {})
            ))
            
            # 阶段 4
            lines.extend(format_stage_for_markdown(
                "阶段 4: DynamicSchemaBuilder", 
                result.get("stage4_dynamic_schema_builder", {})
            ))
            
            # 阶段 5
            lines.extend(format_stage_for_markdown(
                "阶段 5: DynamicPromptBuilder", 
                result.get("stage5_dynamic_prompt_builder", {})
            ))
            
            # 阶段 6
            stage6 = result.get("stage6_llm_output", {})
            if not stage6.get("skipped"):
                lines.append("#### 阶段 6: LLM 输出\n\n")
                if stage6.get("success"):
                    lines.append("**LLM 输出:**\n")
                    lines.append("```json\n")
                    lines.append(json.dumps(stage6.get("output", {}), ensure_ascii=False, indent=2))
                    lines.append("\n```\n\n")
                else:
                    lines.append(f"**错误:** {stage6.get('error', '未知错误')}\n\n")
            
            lines.append("---\n\n")
            
        except Exception as e:
            logger.error(f"测试失败 [{tc['name']}]: {e}", exc_info=True)
            results.append({"name": tc["name"], "error": str(e)})
            lines.append(f"## {tc['name']}\n\n")
            lines.append(f"**错误**: {str(e)}\n\n---\n\n")
    
    # 写入汇总
    lines.append("## 测试汇总\n\n")
    lines.append("| 名称 | 预期 | 实际 | Prompt长度 | Schema长度 | 降级 |\n")
    lines.append("|------|------|------|------------|------------|------|\n")
    for r in results:
        if "error" in r:
            lines.append(f"| {r['name']} | ERROR | {r['error'][:30]} | - | - | - |\n")
        else:
            actual = ", ".join(r.get("actual", []))
            is_degraded = r.get("stage2_feature_extractor", {}).get("output", {}).get("is_degraded", False)
            degraded_str = "是" if is_degraded else "否"
            lines.append(f"| {r['name']} | {r['expected']} | {actual} | {r.get('prompt_length', '-')} | {r.get('schema_length', '-')} | {degraded_str} |\n")
    
    # 保存文件
    with open(output_file, 'w', encoding='utf-8') as f:
        f.writelines(lines)
    
    print(f"\n结果已保存到: {output_file}")
    print("=" * 100)


if __name__ == "__main__":
    asyncio.run(run_all_tests())

