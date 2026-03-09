# -*- coding: utf-8 -*-
"""
计算公式种子数据

预置常见的派生度量计算公式，用于：
- 语义理解后处理：通过规则匹配识别用户意图中的计算需求
- 自动构建计算逻辑：匹配到种子后，直接使用种子信息构建 DerivedComputation
- 减少 LLM 推理负担：常见计算公式由规则处理，LLM 只需处理复杂/非标准情况

这些是业务领域中通用的计算表达式，如：
- 利润率 = 利润 / 销售额
- 同比增长率 = (本期 - 去年同期) / 去年同期

种子数据是领域知识，不应放入 app.yaml 配置文件。
种子数据通过规则匹配使用，不直接丢给 LLM。

用法：
    from analytics_assistant.src.infra.seeds import (
        COMPUTATION_SEEDS,
        ComputationSeed,
    )
"""
from dataclasses import dataclass, field
from typing import Any, Optional

@dataclass
class ComputationSeed:
    """计算表达式种子
    
    Attributes:
        name: 计算名称（英文标识符）
        display_name: 显示名称（中文）
        keywords: 触发关键词列表
        calc_type: 计算类型（对应 CalcType 枚举）
        formula: 计算公式模板，使用 {measure1}, {measure2} 等占位符
        base_measures: 基础度量占位符列表
        description: 计算说明
        examples: 使用示例
        partition_by: 表计算分区维度（可选）
        relative_to: 差异计算参考点（可选）
    """
    name: str
    display_name: str
    keywords: list[str]
    calc_type: str
    formula: Optional[str] = None
    base_measures: list[str] = field(default_factory=list)
    description: str = ""
    examples: list[str] = field(default_factory=list)
    partition_by: Optional[list[str]] = None
    relative_to: Optional[str] = None
    
    def to_computation_dict(
        self,
        measure_mapping: Optional[dict[str, str]] = None,
    ) -> dict[str, Any]:
        """转换为 DerivedComputation 格式的字典
        
        Args:
            measure_mapping: 度量映射，如 {"measure1": "利润", "measure2": "销售额"}
        
        Returns:
            可用于构建 DerivedComputation 的字典
        """
        result = {
            "name": self.name,
            "display_name": self.display_name,
            "calc_type": self.calc_type,
            "base_measures": [],
        }
        
        # 替换公式中的占位符
        if self.formula and measure_mapping:
            formula = self.formula
            for placeholder, actual in measure_mapping.items():
                formula = formula.replace(f"{{{placeholder}}}", f"[{actual}]")
            result["formula"] = formula
            result["base_measures"] = list(measure_mapping.values())
        elif self.formula:
            result["formula"] = self.formula
            result["base_measures"] = self.base_measures
        
        # 添加可选字段
        if self.partition_by:
            result["partition_by"] = self.partition_by
        if self.relative_to:
            result["relative_to"] = self.relative_to
        
        return result

# ══════════════════════════════════════════════════════════════
# 通用计算表达式种子数据
# ══════════════════════════════════════════════════════════════

COMPUTATION_SEEDS: list[ComputationSeed] = [
    # ─────────────────────────────────────────────────────────
    # 比率类计算（RATIO）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="profit_rate",
        display_name="利润率",
        keywords=["利润率", "毛利率", "净利率", "利润比"],
        calc_type="RATIO",
        formula="{profit}/{revenue}",
        base_measures=["profit", "revenue"],
        description="利润与销售额的比率",
        examples=["各地区的利润率", "产品利润率排名"],
    ),
    ComputationSeed(
        name="gross_margin",
        display_name="毛利率",
        keywords=["毛利率", "毛利润率"],
        calc_type="RATIO",
        formula="({revenue}-{cost})/{revenue}",
        base_measures=["revenue", "cost"],
        description="(销售额-成本)/销售额",
        examples=["各产品的毛利率"],
    ),
    ComputationSeed(
        name="conversion_rate",
        display_name="转化率",
        keywords=["转化率", "转换率", "成交率"],
        calc_type="RATIO",
        formula="{conversions}/{visitors}",
        base_measures=["conversions", "visitors"],
        description="转化数/访问数",
        examples=["各渠道的转化率", "页面转化率"],
    ),
    ComputationSeed(
        name="return_rate",
        display_name="退货率",
        keywords=["退货率", "退单率", "退款率"],
        calc_type="RATIO",
        formula="{returns}/{orders}",
        base_measures=["returns", "orders"],
        description="退货数/订单数",
        examples=["各品类的退货率"],
    ),
    ComputationSeed(
        name="completion_rate",
        display_name="完成率",
        keywords=["完成率", "达成率", "完成度"],
        calc_type="RATIO",
        formula="{actual}/{target}",
        base_measures=["actual", "target"],
        description="实际值/目标值",
        examples=["销售目标完成率", "KPI达成率"],
    ),
    ComputationSeed(
        name="average_order_value",
        display_name="客单价",
        keywords=["客单价", "平均订单金额", "单均价", "笔单价"],
        calc_type="RATIO",
        formula="{revenue}/{orders}",
        base_measures=["revenue", "orders"],
        description="销售额/订单数",
        examples=["各地区客单价", "客单价趋势"],
    ),
    ComputationSeed(
        name="average_unit_price",
        display_name="平均单价",
        keywords=["平均单价", "均价", "单价"],
        calc_type="RATIO",
        formula="{revenue}/{quantity}",
        base_measures=["revenue", "quantity"],
        description="销售额/销售数量",
        examples=["各产品平均单价"],
    ),

    # ─────────────────────────────────────────────────────────
    # 占比类计算（TABLE_CALC_PERCENT_OF_TOTAL）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="market_share",
        display_name="市场份额",
        keywords=["市场份额", "份额", "占比", "比重", "占总"],
        calc_type="TABLE_CALC_PERCENT_OF_TOTAL",
        base_measures=["measure"],
        description="某部分占总体的百分比",
        examples=["各地区销售额占比", "产品市场份额"],
    ),
    ComputationSeed(
        name="contribution_rate",
        display_name="贡献率",
        keywords=["贡献率", "贡献度", "贡献占比"],
        calc_type="TABLE_CALC_PERCENT_OF_TOTAL",
        base_measures=["measure"],
        description="某部分对总体的贡献百分比",
        examples=["各产品利润贡献率"],
    ),
    
    # ─────────────────────────────────────────────────────────
    # 同比/环比类计算（TABLE_CALC_PERCENT_DIFF）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="yoy_growth",
        display_name="同比增长率",
        keywords=["同比增长", "同比增长率", "同比", "年同比", "去年同期"],
        calc_type="TABLE_CALC_PERCENT_DIFF",
        base_measures=["measure"],
        relative_to="PREVIOUS",
        description="(本期-去年同期)/去年同期",
        examples=["销售额同比增长率", "利润同比变化"],
    ),
    ComputationSeed(
        name="mom_growth",
        display_name="环比增长率",
        keywords=["环比增长", "环比增长率", "环比", "月环比", "上月"],
        calc_type="TABLE_CALC_PERCENT_DIFF",
        base_measures=["measure"],
        relative_to="PREVIOUS",
        description="(本期-上期)/上期",
        examples=["销售额环比增长率", "月度环比变化"],
    ),
    ComputationSeed(
        name="growth_rate",
        display_name="增长率",
        keywords=["增长率", "增速", "增幅"],
        calc_type="TABLE_CALC_PERCENT_DIFF",
        base_measures=["measure"],
        relative_to="PREVIOUS",
        description="(本期-上期)/上期",
        examples=["销售增长率", "用户增长率"],
    ),
    
    # ─────────────────────────────────────────────────────────
    # 差异类计算（TABLE_CALC_DIFFERENCE）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="yoy_diff",
        display_name="同比差异",
        keywords=["同比差异", "同比差额", "同比变化量"],
        calc_type="TABLE_CALC_DIFFERENCE",
        base_measures=["measure"],
        relative_to="PREVIOUS",
        description="本期-去年同期（绝对值）",
        examples=["销售额同比差异"],
    ),
    ComputationSeed(
        name="mom_diff",
        display_name="环比差异",
        keywords=["环比差异", "环比差额", "环比变化量"],
        calc_type="TABLE_CALC_DIFFERENCE",
        base_measures=["measure"],
        relative_to="PREVIOUS",
        description="本期-上期（绝对值）",
        examples=["销售额环比差异"],
    ),
    
    # ─────────────────────────────────────────────────────────
    # 排名类计算（TABLE_CALC_RANK）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="rank",
        display_name="排名",
        keywords=["排名", "名次", "排序", "第几名"],
        calc_type="TABLE_CALC_RANK",
        base_measures=["measure"],
        description="按度量值排名",
        examples=["销售额排名", "利润排名"],
    ),
    
    # ─────────────────────────────────────────────────────────
    # 累计类计算（TABLE_CALC_RUNNING）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="ytd",
        display_name="年初至今累计",
        keywords=["年初至今", "YTD", "年累计", "本年累计"],
        calc_type="TABLE_CALC_RUNNING",
        base_measures=["measure"],
        description="从年初到当前的累计值",
        examples=["年初至今销售额", "YTD利润"],
    ),
    ComputationSeed(
        name="running_total",
        display_name="累计",
        keywords=["累计", "累加", "累积"],
        calc_type="TABLE_CALC_RUNNING",
        base_measures=["measure"],
        description="从起始到当前的累计值",
        examples=["累计销售额", "累计订单数"],
    ),
    
    # ─────────────────────────────────────────────────────────
    # 移动计算（TABLE_CALC_MOVING）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="moving_average",
        display_name="移动平均",
        keywords=["移动平均", "滑动平均", "MA", "均线"],
        calc_type="TABLE_CALC_MOVING",
        base_measures=["measure"],
        description="最近N期的平均值",
        examples=["3个月移动平均销售额", "7日移动平均"],
    ),
    
    # ─────────────────────────────────────────────────────────
    # 简单计算（SUM/DIFFERENCE/PRODUCT）
    # ─────────────────────────────────────────────────────────
    ComputationSeed(
        name="profit",
        display_name="利润",
        keywords=["利润", "净利润"],
        calc_type="DIFFERENCE",
        formula="{revenue}-{cost}",
        base_measures=["revenue", "cost"],
        description="销售额-成本",
        examples=["各地区利润", "产品利润"],
    ),
    ComputationSeed(
        name="total_cost",
        display_name="总成本",
        keywords=["总成本", "成本合计"],
        calc_type="SUM",
        formula="{fixed_cost}+{variable_cost}",
        base_measures=["fixed_cost", "variable_cost"],
        description="固定成本+可变成本",
        examples=["各部门总成本"],
    ),
    ComputationSeed(
        name="total_amount",
        display_name="总金额",
        keywords=["总金额", "总价", "金额合计"],
        calc_type="PRODUCT",
        formula="{unit_price}*{quantity}",
        base_measures=["unit_price", "quantity"],
        description="单价*数量",
        examples=["订单总金额"],
    ),
]

__all__ = [
    "ComputationSeed",
    "COMPUTATION_SEEDS",
]
