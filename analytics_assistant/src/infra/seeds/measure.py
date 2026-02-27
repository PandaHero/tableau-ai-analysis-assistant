# -*- coding: utf-8 -*-
"""
度量模式种子数据

预置常见度量模式，覆盖主要类别：
- revenue: 收入类（销售额、营业收入、GMV）
- cost: 成本类（成本、费用、支出）
- profit: 利润类（利润、毛利、净利）
- quantity: 数量类（数量、件数、订单数）
- ratio: 比率类（占比、增长率、转化率）
- count: 计数类（人数、次数、频次）
- average: 平均类（均价、平均值）

用于 RAG 检索和 LLM few-shot 示例。

用法：
    from analytics_assistant.src.infra.seeds import (
        MEASURE_SEEDS,
        get_measure_few_shot_examples,
    )
"""
from typing import Any

# ══════════════════════════════════════════════════════════════
# 度量模式种子数据
# ══════════════════════════════════════════════════════════════

MEASURE_SEEDS: list[dict[str, Any]] = [
    # ─────────────────────────────────────────────────────────
    # REVENUE 收入类 - 中文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "销售额",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "表示产品或服务销售的总金额",
        "aliases": ["销售金额", "营收", "Sales", "Revenue"],
        "reasoning": "收入类度量，表示销售收入",
    },
    {
        "field_caption": "营业收入",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "企业主营业务产生的收入总额",
        "aliases": ["营收", "主营收入", "Operating Revenue"],
        "reasoning": "收入类度量，表示营业收入",
    },
    {
        "field_caption": "GMV",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "商品交易总额，包含所有订单金额",
        "aliases": ["交易额", "成交额", "Gross Merchandise Value"],
        "reasoning": "收入类度量，表示商品交易总额",
    },
    {
        "field_caption": "收入",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "企业获得的经济利益流入",
        "aliases": ["总收入", "Income", "Revenue"],
        "reasoning": "收入类度量，表示总收入",
    },
    {
        "field_caption": "金额",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "交易或业务的货币金额",
        "aliases": ["总金额", "Amount", "Value"],
        "reasoning": "收入类度量，表示金额",
    },
    # ─────────────────────────────────────────────────────────
    # REVENUE 收入类 - 英文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "Sales",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "Total sales amount for products or services",
        "aliases": ["Sales Amount", "Revenue", "销售额"],
        "reasoning": "Revenue measure representing sales income",
    },
    {
        "field_caption": "Revenue",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "Total revenue from business operations",
        "aliases": ["Total Revenue", "Income", "营收"],
        "reasoning": "Revenue measure representing total income",
    },
    {
        "field_caption": "Amount",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "Monetary amount of transactions",
        "aliases": ["Total Amount", "Value", "金额"],
        "reasoning": "Revenue measure representing transaction amount",
    },
    {
        "field_caption": "order_amount",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "Total amount of orders",
        "aliases": ["Order Value", "订单金额"],
        "reasoning": "Revenue measure representing order amount",
    },
    {
        "field_caption": "net_sales",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "Net sales after deductions",
        "aliases": ["Net Revenue", "净销售额"],
        "reasoning": "Revenue measure representing net sales",
    },

    # ─────────────────────────────────────────────────────────
    # COST 成本类 - 中文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "成本",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "生产或获取产品/服务所需的支出",
        "aliases": ["总成本", "Cost", "费用"],
        "reasoning": "成本类度量，表示成本支出",
    },
    {
        "field_caption": "费用",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "企业运营过程中产生的各项支出",
        "aliases": ["支出", "Expense", "开支"],
        "reasoning": "成本类度量，表示费用支出",
    },
    {
        "field_caption": "销售成本",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "销售产品或服务直接产生的成本",
        "aliases": ["COGS", "Cost of Sales", "销货成本"],
        "reasoning": "成本类度量，表示销售成本",
    },
    {
        "field_caption": "运营成本",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "企业日常运营产生的成本",
        "aliases": ["运营费用", "Operating Cost", "经营成本"],
        "reasoning": "成本类度量，表示运营成本",
    },
    # ─────────────────────────────────────────────────────────
    # COST 成本类 - 英文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "Cost",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Total cost of products or services",
        "aliases": ["Total Cost", "Expense", "成本"],
        "reasoning": "Cost measure representing total cost",
    },
    {
        "field_caption": "Expense",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Business operating expenses",
        "aliases": ["Expenses", "费用", "支出"],
        "reasoning": "Cost measure representing expenses",
    },
    {
        "field_caption": "COGS",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Cost of goods sold",
        "aliases": ["Cost of Sales", "销售成本", "销货成本"],
        "reasoning": "Cost measure representing cost of goods sold",
    },
    {
        "field_caption": "shipping_cost",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Cost of shipping and delivery",
        "aliases": ["Shipping Fee", "运费", "物流成本"],
        "reasoning": "Cost measure representing shipping cost",
    },

    # ─────────────────────────────────────────────────────────
    # PROFIT 利润类 - 中文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "利润",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "收入减去成本后的盈余",
        "aliases": ["盈利", "Profit", "净利"],
        "reasoning": "利润类度量，表示利润",
    },
    {
        "field_caption": "毛利",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "销售收入减去销售成本的差额",
        "aliases": ["毛利润", "Gross Profit", "销售毛利"],
        "reasoning": "利润类度量，表示毛利",
    },
    {
        "field_caption": "净利润",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "扣除所有成本和费用后的最终利润",
        "aliases": ["净利", "Net Profit", "纯利"],
        "reasoning": "利润类度量，表示净利润",
    },
    {
        "field_caption": "营业利润",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "主营业务产生的利润",
        "aliases": ["经营利润", "Operating Profit", "营业盈利"],
        "reasoning": "利润类度量，表示营业利润",
    },
    # ─────────────────────────────────────────────────────────
    # PROFIT 利润类 - 英文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "Profit",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "Revenue minus costs and expenses",
        "aliases": ["Net Profit", "利润", "盈利"],
        "reasoning": "Profit measure representing profit",
    },
    {
        "field_caption": "Gross Profit",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "Revenue minus cost of goods sold",
        "aliases": ["Gross Margin", "毛利", "毛利润"],
        "reasoning": "Profit measure representing gross profit",
    },
    {
        "field_caption": "margin",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "Profit margin or difference",
        "aliases": ["Profit Margin", "利润率", "边际"],
        "reasoning": "Profit measure representing margin",
    },

    # ─────────────────────────────────────────────────────────
    # QUANTITY 数量类 - 中文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "数量",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "产品或物品的数量",
        "aliases": ["件数", "Quantity", "个数"],
        "reasoning": "数量类度量，表示数量",
    },
    {
        "field_caption": "订单数",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "订单的总数量",
        "aliases": ["订单量", "Order Count", "订单数量"],
        "reasoning": "数量类度量，表示订单数",
    },
    {
        "field_caption": "销量",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "销售的产品数量",
        "aliases": ["销售量", "Sales Volume", "出货量"],
        "reasoning": "数量类度量，表示销量",
    },
    {
        "field_caption": "库存",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "当前库存的产品数量",
        "aliases": ["库存量", "Inventory", "存货"],
        "reasoning": "数量类度量，表示库存",
    },
    # ─────────────────────────────────────────────────────────
    # QUANTITY 数量类 - 英文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "Quantity",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "Number of items or units",
        "aliases": ["Qty", "数量", "件数"],
        "reasoning": "Quantity measure representing count of items",
    },
    {
        "field_caption": "order_count",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "Total number of orders",
        "aliases": ["Orders", "订单数", "订单量"],
        "reasoning": "Quantity measure representing order count",
    },
    {
        "field_caption": "units_sold",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "Number of units sold",
        "aliases": ["Sales Units", "销量", "销售数量"],
        "reasoning": "Quantity measure representing units sold",
    },
    {
        "field_caption": "inventory",
        "data_type": "integer",
        "measure_category": "quantity",
        "business_description": "Current inventory level",
        "aliases": ["Stock", "库存", "存货"],
        "reasoning": "Quantity measure representing inventory",
    },

    # ─────────────────────────────────────────────────────────
    # RATIO 比率类 - 中文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "占比",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "某部分占总体的百分比",
        "aliases": ["比例", "Ratio", "百分比"],
        "reasoning": "比率类度量，表示占比",
    },
    {
        "field_caption": "增长率",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "相比基期的增长百分比",
        "aliases": ["增速", "Growth Rate", "同比增长"],
        "reasoning": "比率类度量，表示增长率",
    },
    {
        "field_caption": "转化率",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "从一个状态转化到另一个状态的比率",
        "aliases": ["转换率", "Conversion Rate", "CVR"],
        "reasoning": "比率类度量，表示转化率",
    },
    {
        "field_caption": "利润率",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "利润占收入的百分比",
        "aliases": ["毛利率", "Profit Margin", "净利率"],
        "reasoning": "比率类度量，表示利润率",
    },
    # ─────────────────────────────────────────────────────────
    # RATIO 比率类 - 英文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "Ratio",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "Proportion or percentage",
        "aliases": ["Percentage", "占比", "比例"],
        "reasoning": "Ratio measure representing proportion",
    },
    {
        "field_caption": "growth_rate",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "Rate of growth compared to baseline",
        "aliases": ["Growth", "增长率", "增速"],
        "reasoning": "Ratio measure representing growth rate",
    },
    {
        "field_caption": "conversion_rate",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "Rate of conversion from one state to another",
        "aliases": ["CVR", "转化率", "转换率"],
        "reasoning": "Ratio measure representing conversion rate",
    },
    {
        "field_caption": "profit_margin",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "Profit as percentage of revenue",
        "aliases": ["Margin", "利润率", "毛利率"],
        "reasoning": "Ratio measure representing profit margin",
    },

    # ─────────────────────────────────────────────────────────
    # COUNT 计数类 - 中文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "人数",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "人员的数量统计",
        "aliases": ["人员数", "Headcount", "员工数"],
        "reasoning": "计数类度量，表示人数",
    },
    {
        "field_caption": "次数",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "事件发生的次数",
        "aliases": ["频次", "Times", "频率"],
        "reasoning": "计数类度量，表示次数",
    },
    {
        "field_caption": "客户数",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "客户的数量统计",
        "aliases": ["客户量", "Customer Count", "用户数"],
        "reasoning": "计数类度量，表示客户数",
    },
    {
        "field_caption": "访问量",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "访问或浏览的次数",
        "aliases": ["PV", "Page Views", "浏览量"],
        "reasoning": "计数类度量，表示访问量",
    },
    # ─────────────────────────────────────────────────────────
    # COUNT 计数类 - 英文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "Count",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "Total count of items or events",
        "aliases": ["Total Count", "计数", "数量"],
        "reasoning": "Count measure representing total count",
    },
    {
        "field_caption": "headcount",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "Number of employees or people",
        "aliases": ["Employee Count", "人数", "员工数"],
        "reasoning": "Count measure representing headcount",
    },
    {
        "field_caption": "customer_count",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "Number of customers",
        "aliases": ["Customers", "客户数", "用户数"],
        "reasoning": "Count measure representing customer count",
    },
    {
        "field_caption": "page_views",
        "data_type": "integer",
        "measure_category": "count",
        "business_description": "Number of page views",
        "aliases": ["PV", "访问量", "浏览量"],
        "reasoning": "Count measure representing page views",
    },

    # ─────────────────────────────────────────────────────────
    # AVERAGE 平均类 - 中文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "均价",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "产品或服务的平均价格",
        "aliases": ["平均价格", "Average Price", "单价"],
        "reasoning": "平均类度量，表示均价",
    },
    {
        "field_caption": "平均值",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "数值的算术平均",
        "aliases": ["均值", "Average", "Mean"],
        "reasoning": "平均类度量，表示平均值",
    },
    {
        "field_caption": "客单价",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "每位客户的平均消费金额",
        "aliases": ["平均订单金额", "AOV", "Average Order Value"],
        "reasoning": "平均类度量，表示客单价",
    },
    # ─────────────────────────────────────────────────────────
    # AVERAGE 平均类 - 英文
    # ─────────────────────────────────────────────────────────
    {
        "field_caption": "Average",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "Arithmetic mean of values",
        "aliases": ["Mean", "Avg", "平均值"],
        "reasoning": "Average measure representing mean value",
    },
    {
        "field_caption": "avg_price",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "Average price of products",
        "aliases": ["Average Price", "均价", "单价"],
        "reasoning": "Average measure representing average price",
    },
    {
        "field_caption": "AOV",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "Average order value per customer",
        "aliases": ["Average Order Value", "客单价", "平均订单金额"],
        "reasoning": "Average measure representing average order value",
    },
    {
        "field_caption": "avg_revenue",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "Average revenue per unit or period",
        "aliases": ["Average Revenue", "平均收入", "ARPU"],
        "reasoning": "Average measure representing average revenue",
    },
    
    # ─────────────────────────────────────────────────────────
    # 扩展种子数据 - 常见业务度量（中英文）
    # ─────────────────────────────────────────────────────────
    
    # 运费/物流成本
    {
        "field_caption": "运费",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "货物运输产生的费用",
        "aliases": ["物流费", "freight_cost", "Freight Cost", "运输费"],
        "reasoning": "成本类度量，表示运费",
    },
    {
        "field_caption": "freight_cost",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Cost of freight and shipping",
        "aliases": ["运费", "Freight", "Shipping Cost"],
        "reasoning": "Cost measure representing freight cost",
    },
    {
        "field_caption": "freight_costs",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Total freight and shipping costs",
        "aliases": ["运费", "Freight Costs", "物流成本"],
        "reasoning": "Cost measure representing freight costs",
    },
    
    # 税前利润
    {
        "field_caption": "税前利润",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "扣除税费前的利润",
        "aliases": ["pre_tax_profit", "Pre-tax Profit", "EBT"],
        "reasoning": "利润类度量，表示税前利润",
    },
    {
        "field_caption": "pre_tax_profit",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "Profit before tax deduction",
        "aliases": ["税前利润", "Pre-tax Profit", "EBT"],
        "reasoning": "Profit measure representing pre-tax profit",
    },
    
    # 毛利相关
    {
        "field_caption": "gross_profit",
        "data_type": "real",
        "measure_category": "profit",
        "business_description": "Revenue minus cost of goods sold",
        "aliases": ["毛利", "Gross Profit", "毛利润"],
        "reasoning": "Profit measure representing gross profit",
    },
    {
        "field_caption": "gross_profit_rate",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "Gross profit as percentage of revenue",
        "aliases": ["毛利率", "Gross Margin", "GPM"],
        "reasoning": "Ratio measure representing gross profit rate",
    },
    {
        "field_caption": "毛利率",
        "data_type": "real",
        "measure_category": "ratio",
        "business_description": "毛利占收入的百分比",
        "aliases": ["gross_profit_rate", "Gross Margin", "GPM"],
        "reasoning": "比率类度量，表示毛利率",
    },
    
    # 净销售额
    {
        "field_caption": "净销售额",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "扣除退货和折扣后的销售额",
        "aliases": ["net_sales", "Net Sales", "净收入"],
        "reasoning": "收入类度量，表示净销售额",
    },
    
    # 折扣
    {
        "field_caption": "折扣",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "给予客户的价格减免",
        "aliases": ["Discount", "discount", "折扣金额"],
        "reasoning": "成本类度量，表示折扣",
    },
    {
        "field_caption": "Discount",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Price reduction given to customers",
        "aliases": ["折扣", "discount", "Discount Amount"],
        "reasoning": "Cost measure representing discount",
    },
    
    # 订单相关
    {
        "field_caption": "订单金额",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "单个订单的总金额",
        "aliases": ["order_amount", "Order Amount", "订单额"],
        "reasoning": "收入类度量，表示订单金额",
    },
    
    # 单价
    {
        "field_caption": "单价",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "单个产品的价格",
        "aliases": ["unit_price", "Unit Price", "价格"],
        "reasoning": "平均类度量，表示单价",
    },
    {
        "field_caption": "unit_price",
        "data_type": "real",
        "measure_category": "average",
        "business_description": "Price per unit of product",
        "aliases": ["单价", "Unit Price", "Price"],
        "reasoning": "Average measure representing unit price",
    },
    
    # 税额
    {
        "field_caption": "税额",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "应缴纳的税款金额",
        "aliases": ["tax_amount", "Tax Amount", "税金"],
        "reasoning": "成本类度量，表示税额",
    },
    {
        "field_caption": "tax_amount",
        "data_type": "real",
        "measure_category": "cost",
        "business_description": "Amount of tax payable",
        "aliases": ["税额", "Tax", "税金"],
        "reasoning": "Cost measure representing tax amount",
    },
    
    # 含税/不含税金额
    {
        "field_caption": "含税金额",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "包含税费的总金额",
        "aliases": ["amount_with_tax", "Amount with Tax", "含税价"],
        "reasoning": "收入类度量，表示含税金额",
    },
    {
        "field_caption": "不含税金额",
        "data_type": "real",
        "measure_category": "revenue",
        "business_description": "不包含税费的金额",
        "aliases": ["amount_without_tax", "Amount without Tax", "不含税价"],
        "reasoning": "收入类度量，表示不含税金额",
    },
]

# ══════════════════════════════════════════════════════════════
# 辅助函数
# ══════════════════════════════════════════════════════════════

def get_measure_few_shot_examples(
    categories: list[str] = None,
    max_per_category: int = 1,
) -> list[dict[str, Any]]:
    """
    获取度量种子数据作为 few-shot 示例
    
    Args:
        categories: 要获取的类别列表，None 表示所有类别
        max_per_category: 每个类别最多返回的示例数
    
    Returns:
        few-shot 示例列表
    """
    if categories is None:
        categories = [
            "revenue", "cost", "profit", "quantity",
            "ratio", "count", "average",
        ]
    
    examples = []
    category_counts = {cat: 0 for cat in categories}
    
    for pattern in MEASURE_SEEDS:
        cat = pattern["measure_category"]
        if cat in categories and category_counts[cat] < max_per_category:
            examples.append({
                "field_caption": pattern["field_caption"],
                "data_type": pattern["data_type"],
                "measure_category": pattern["measure_category"],
                "business_description": pattern["business_description"],
                "aliases": pattern["aliases"],
            })
            category_counts[cat] += 1
    
    return examples

__all__ = [
    "MEASURE_SEEDS",
    "get_measure_few_shot_examples",
]
