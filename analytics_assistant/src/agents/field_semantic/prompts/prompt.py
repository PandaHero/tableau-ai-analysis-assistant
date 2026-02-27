# -*- coding: utf-8 -*-
"""
字段语义推断 Prompt

分为系统提示和用户提示：
- SYSTEM_PROMPT: 定义任务、规则、输出格式
- build_user_prompt(): 构建用户输入（字段列表 + few-shot 示例）

支持维度和度量字段的统一语义分析。
"""
import json
from typing import Any, Optional

from analytics_assistant.src.infra.seeds import (
    get_dimension_few_shot_examples,
    get_measure_few_shot_examples,
)

# ══════════════════════════════════════════════════════════════
# 系统提示
# ══════════════════════════════════════════════════════════════

SYSTEM_PROMPT = """你是一个字段语义分析专家，负责推断数据字段的语义属性。

## 任务
分析每个字段，根据其角色（维度/度量）推断相应属性：

### 维度字段（role="dimension"）
1. category: 维度类别（time/geography/product/customer/organization/channel/financial/other）
2. category_detail: 详细类别，格式 'category-subcategory'
3. level: 层级 1-5（1 最粗，5 最细）
4. granularity: 粒度描述（coarsest/coarse/medium/fine/finest，与 level 对应）

### 度量字段（role="measure"）
1. measure_category: 度量类别
   - revenue: 收入类（销售额、营业收入、GMV）
   - cost: 成本类（成本、费用、支出）
   - profit: 利润类（利润、毛利、净利）
   - quantity: 数量类（数量、件数、订单数）
   - ratio: 比率类（占比、增长率、转化率）
   - count: 计数类（人数、次数、频次）
   - average: 平均类（均价、平均值）
   - other: 其他

### 所有字段
1. business_description: 业务描述（一句话说明字段的业务含义）
2. aliases: 别名列表（用户可能使用的其他名称）
3. confidence: 置信度 0-1

## 层级说明（维度字段）
- Level 1 (coarsest): 最粗粒度，如国家、年份、产品大类、一级渠道
- Level 2 (coarse): 粗粒度，如省份、季度、产品类别、二级渠道
- Level 3 (medium): 中等粒度，如城市、月份、子类别、品牌
- Level 4 (fine): 细粒度，如区县、周、产品名称
- Level 5 (finest): 最细粒度，如地址、日期、SKU、客户ID

## 业务描述规则
- 使用自然语言描述字段的业务含义
- 描述应简洁明了，不超过 50 字
- 包含字段的用途和典型使用场景
- ⚠️ 如果提供了 sample_values（样例值），必须优先根据样例值判断字段的真实业务含义
  - 例如：字段名为 "dept_nm"，但样例值为 ["水果", "蔬菜", "猪肉"]，则应推断为产品类别而非部门
  - 字段名可能具有误导性，样例值是判断字段真实含义的最可靠依据

## 别名生成规则（必须）
⚠️ 每个字段必须生成 2-5 个别名，不能为空！
- 包含常见的同义词和缩写
- 包含中英文对照（如适用）
- 包含业务术语的变体
- 如果有 sample_values，别名应反映样例值暗示的真实业务含义
- 示例：
  - "销售额" → ["销售金额", "营收", "Sales", "Revenue"]
  - "省份" → ["省", "省区", "Province"]
  - "日期" → ["时间", "Date", "日"]

## 推断优先级（重要）
当字段名与样例值暗示的含义不一致时，以样例值为准：
- 样例值包含食品名称（水果、蔬菜等）→ 产品类别维度
- 样例值包含地名（北京、上海等）→ 地理维度
- 样例值包含人名 → 客户/员工维度
- 样例值包含日期/时间 → 时间维度"""

# ══════════════════════════════════════════════════════════════
# 用户提示构建
# ══════════════════════════════════════════════════════════════

def build_user_prompt(
    fields: list[dict[str, Any]],
    include_few_shot: bool = True,
    max_dimension_examples: int = 2,
    max_measure_examples: int = 2,
) -> str:
    """
    构建用户提示
    
    Args:
        fields: 要推断的字段列表，每个字段包含：
            - field_caption: 字段显示名称
            - data_type: 数据类型
            - role: 字段角色（dimension/measure）
            - sample_values: 样例值（可选）
            - unique_count: 唯一值数量（可选）
        include_few_shot: 是否包含 few-shot 示例
        max_dimension_examples: 最大维度示例数
        max_measure_examples: 最大度量示例数
    
    Returns:
        用户提示字符串
    """
    parts = []
    
    # Few-shot 示例
    if include_few_shot:
        examples = _build_few_shot_examples(max_dimension_examples, max_measure_examples)
        if examples:
            parts.append("## 参考示例")
            parts.append("```json")
            parts.append(json.dumps(examples, ensure_ascii=False, indent=2))
            parts.append("```")
    
    # 待分析字段
    fields_info = _build_fields_info(fields)
    
    parts.append("\n## 待分析字段")
    parts.append("```json")
    parts.append(json.dumps(fields_info, ensure_ascii=False, indent=2))
    parts.append("```")
    parts.append("\n请分析以上字段，返回 field_semantic JSON。")
    
    return "\n".join(parts)

def _build_few_shot_examples(
    max_dimension: int = 2,
    max_measure: int = 2,
) -> dict[str, Any]:
    """构建 few-shot 示例（确保 aliases 不为空）"""
    examples = {"field_semantic": {}}
    
    # 维度示例（只选择有 aliases 的）
    dimension_examples = get_dimension_few_shot_examples(max_per_category=1)
    count = 0
    for ex in dimension_examples:
        if count >= max_dimension:
            break
        aliases = ex.get("aliases", [])
        if not aliases:
            continue  # 跳过没有 aliases 的示例
        field_name = ex.get("field_caption", f"维度{count+1}")
        examples["field_semantic"][field_name] = {
            "role": "dimension",
            "category": ex.get("category", "other"),
            "category_detail": ex.get("category_detail", "other-unknown"),
            "level": ex.get("level", 3),
            "granularity": ex.get("granularity", "medium"),
            "business_description": ex.get("business_description", field_name),
            "aliases": aliases,
            "confidence": 0.95,
        }
        count += 1
    
    # 度量示例（只选择有 aliases 的）
    measure_examples = get_measure_few_shot_examples(max_per_category=1)
    count = 0
    for ex in measure_examples:
        if count >= max_measure:
            break
        aliases = ex.get("aliases", [])
        if not aliases:
            continue  # 跳过没有 aliases 的示例
        field_name = ex.get("field_caption", f"度量{count+1}")
        examples["field_semantic"][field_name] = {
            "role": "measure",
            "measure_category": ex.get("measure_category", "other"),
            "business_description": ex.get("business_description", field_name),
            "aliases": aliases,
            "confidence": 0.95,
        }
        count += 1
    
    return examples

def _build_fields_info(fields: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """构建字段信息列表"""
    fields_info = []
    
    for f in fields:
        info = {
            "field_caption": f.get("field_caption", f.get("caption", "")),
            "data_type": f.get("data_type", "string"),
            "role": f.get("role", "dimension"),
        }
        
        # 可选字段
        if f.get("sample_values"):
            info["sample_values"] = f["sample_values"][:5]
        if f.get("unique_count") is not None:
            info["unique_count"] = f["unique_count"]
        
        fields_info.append(info)
    
    return fields_info

def get_system_prompt() -> str:
    """获取系统提示"""
    return SYSTEM_PROMPT

__all__ = [
    "SYSTEM_PROMPT",
    "build_user_prompt",
    "get_system_prompt",
]
