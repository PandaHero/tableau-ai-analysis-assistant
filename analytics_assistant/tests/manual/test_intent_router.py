# -*- coding: utf-8 -*-
"""
IntentRouter 手动测试（简化版）

测试三层意图识别策略：
- L0 规则层：关键词匹配（元数据/数据分析/无关）
- L1 小模型分类（可选，默认禁用）
- L2 兜底：DATA_QUERY

运行方式：
    cd analytics_assistant
    $env:PYTHONPATH = ".."
    python -m pytest tests/manual/test_intent_router.py -v
"""

import asyncio
import pytest

from analytics_assistant.src.agents.semantic_parser.components.intent_router import (
    IntentType,
    IntentRouterOutput,
    IntentRouter,
    METADATA_KEYWORDS,
    DATA_ANALYSIS_KEYWORDS,
    IRRELEVANT_PATTERNS,
)


class TestIntentType:
    """测试 IntentType 枚举"""
    
    def test_intent_type_values(self):
        """测试枚举值（简化为 3 种）"""
        assert IntentType.DATA_QUERY.value == "DATA_QUERY"
        assert IntentType.GENERAL.value == "GENERAL"
        assert IntentType.IRRELEVANT.value == "IRRELEVANT"
        
        # 确认只有 3 种类型
        assert len(IntentType) == 3
    
    def test_intent_type_is_string_enum(self):
        """测试枚举是字符串类型"""
        assert isinstance(IntentType.DATA_QUERY, str)
        assert IntentType.DATA_QUERY == "DATA_QUERY"


class TestIntentRouterOutput:
    """测试 IntentRouterOutput 模型"""
    
    def test_create_output(self):
        """测试创建输出"""
        output = IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=0.95,
            reason="测试原因",
            source="L0_RULES",
        )
        
        assert output.intent_type == IntentType.DATA_QUERY
        assert output.confidence == 0.95
        assert output.reason == "测试原因"
        assert output.source == "L0_RULES"
    
    def test_confidence_validation(self):
        """测试置信度范围验证"""
        # 有效范围
        output = IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=0.0,
            reason="test",
            source="L0_RULES",
        )
        assert output.confidence == 0.0
        
        output = IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=1.0,
            reason="test",
            source="L0_RULES",
        )
        assert output.confidence == 1.0
        
        # 无效范围
        with pytest.raises(ValueError):
            IntentRouterOutput(
                intent_type=IntentType.DATA_QUERY,
                confidence=-0.1,
                reason="test",
                source="L0_RULES",
            )
    
    def test_serialization(self):
        """测试序列化"""
        output = IntentRouterOutput(
            intent_type=IntentType.DATA_QUERY,
            confidence=0.95,
            reason="测试",
            source="L0_RULES",
        )
        
        data = output.model_dump()
        assert data["intent_type"] == "DATA_QUERY"
        
        # 反序列化
        restored = IntentRouterOutput.model_validate(data)
        assert restored.intent_type == IntentType.DATA_QUERY


class TestIntentRouterL0Rules:
    """测试 IntentRouter L0 规则层"""
    
    @pytest.fixture
    def router(self):
        """创建 IntentRouter 实例"""
        return IntentRouter(enable_l1=False)
    
    # ─────────────────────────────────────────────────────────────────
    # 元数据问答测试 → GENERAL
    # ─────────────────────────────────────────────────────────────────
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("question", [
        "有哪些字段",
        "有什么维度",
        "度量列表",
        "指标有哪些",
        "数据源是什么",
        "数据集叫什么名字",
        "表名称是什么",
        "可以查询什么",
        "能查哪些数据",
        "schema是什么",
        "元数据",
    ])
    async def test_metadata_questions(self, router, question):
        """测试元数据问答 → GENERAL"""
        result = await router.route(question)
        
        assert result.intent_type == IntentType.GENERAL
        assert result.source == "L0_RULES"
        assert result.confidence >= 0.9
    
    # ─────────────────────────────────────────────────────────────────
    # 数据分析问题测试 → DATA_QUERY
    # ─────────────────────────────────────────────────────────────────
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("question", [
        # 基础查询
        "上个月各地区的销售额",
        "查询本季度的利润",
        "统计今年的订单数量",
        # 趋势分析
        "销售额趋势",
        "利润增长情况",
        "订单数量变化",
        # 对比分析
        "各地区销售额对比",
        "同比增长率",
        "环比变化",
        # 排名
        "销售额最高的产品",
        "top10客户",
        "排名前5的地区",
        # 占比
        "各产品销售额占比",
        "地区利润比例",
        # 聚合
        "按地区统计销售额",
        "各省份的订单数",
        "每月的收入",
        # 筛选
        "华东地区的销售额",
        "只看上海的数据",
    ])
    async def test_data_analysis_questions(self, router, question):
        """测试数据分析问题 → DATA_QUERY"""
        result = await router.route(question)
        
        assert result.intent_type == IntentType.DATA_QUERY
        assert result.source == "L0_RULES"
        assert result.confidence >= 0.7
    
    # ─────────────────────────────────────────────────────────────────
    # 无关问题测试 → IRRELEVANT
    # ─────────────────────────────────────────────────────────────────
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("question", [
        # 纯打招呼
        "你好",
        "hi",
        "hello",
        "谢谢",
        "再见",
        "好的",
        "ok",
        # 明确无关话题
        "今天天气怎么样",
        "讲个笑话",
        "你是谁",
        "帮我写一篇文章",
        "翻译这段话",
        "最近有什么新闻",
        "股票怎么样",
        "推荐个电影",
    ])
    async def test_irrelevant_questions(self, router, question):
        """测试无关问题 → IRRELEVANT"""
        result = await router.route(question)
        
        assert result.intent_type == IntentType.IRRELEVANT
        assert result.source == "L0_RULES"
        assert result.confidence >= 0.9
    
    # ─────────────────────────────────────────────────────────────────
    # L2 兜底测试 → DATA_QUERY
    # ─────────────────────────────────────────────────────────────────
    
    @pytest.mark.asyncio
    @pytest.mark.parametrize("question", [
        # 模糊问题（没有明确关键词）
        "帮我看看数据",
        "分析一下",
        "查一下情况",
        # 不常见的表达
        "给我出个报告",
        "看看业绩",
    ])
    async def test_fallback_to_data_query(self, router, question):
        """测试 L2 兜底 → DATA_QUERY"""
        result = await router.route(question)
        
        # 模糊问题走 L2 兜底，默认当作数据查询
        assert result.intent_type == IntentType.DATA_QUERY
        assert result.source == "L2_FALLBACK"
        assert result.confidence == 0.5


class TestIntentRouterConfiguration:
    """测试 IntentRouter 配置"""
    
    def test_default_configuration(self):
        """测试默认配置"""
        router = IntentRouter()
        
        assert router.l1_confidence_threshold == 0.8
        assert router.enable_l1 is False
    
    def test_custom_configuration(self):
        """测试自定义配置"""
        router = IntentRouter(
            l1_confidence_threshold=0.9,
            enable_l1=True,
        )
        
        assert router.l1_confidence_threshold == 0.9
        assert router.enable_l1 is True
    
    def test_keywords_loaded(self):
        """测试关键词已加载"""
        router = IntentRouter()
        
        assert len(router._metadata_keywords) > 0
        assert len(router._data_analysis_keywords) > 0
        assert len(router._irrelevant_patterns) > 0


class TestIntentRouterEdgeCases:
    """测试边界情况"""
    
    @pytest.fixture
    def router(self):
        return IntentRouter()
    
    @pytest.mark.asyncio
    async def test_mixed_question_metadata_priority(self, router):
        """测试混合问题 - 元数据优先"""
        # 同时包含元数据和数据分析关键词时，元数据优先
        result = await router.route("有哪些字段可以查询销售额")
        assert result.intent_type == IntentType.GENERAL
    
    @pytest.mark.asyncio
    async def test_multiple_data_keywords_higher_confidence(self, router):
        """测试多个数据分析关键词 - 更高置信度"""
        # 单个关键词
        result1 = await router.route("销售额")
        
        # 多个关键词
        result2 = await router.route("上个月各地区的销售额趋势")
        
        # 多关键词应该有更高置信度
        assert result2.confidence >= result1.confidence
    
    @pytest.mark.asyncio
    async def test_case_insensitive(self, router):
        """测试大小写不敏感"""
        result1 = await router.route("销售额")
        result2 = await router.route("SCHEMA")
        
        assert result1.intent_type == IntentType.DATA_QUERY
        assert result2.intent_type == IntentType.GENERAL
    
    @pytest.mark.asyncio
    async def test_empty_question(self, router):
        """测试空问题"""
        result = await router.route("")
        # 空问题走 L2 兜底
        assert result.intent_type == IntentType.DATA_QUERY
        assert result.source == "L2_FALLBACK"
    
    @pytest.mark.asyncio
    async def test_whitespace_question(self, router):
        """测试纯空白问题"""
        result = await router.route("   ")
        assert result.intent_type == IntentType.DATA_QUERY
        assert result.source == "L2_FALLBACK"


# ═══════════════════════════════════════════════════════════════════════════
# 运行测试
# ═══════════════════════════════════════════════════════════════════════════

if __name__ == "__main__":
    async def main():
        router = IntentRouter()
        
        test_cases = [
            # 元数据 → GENERAL
            ("有哪些字段", IntentType.GENERAL),
            ("数据源是什么", IntentType.GENERAL),
            
            # 数据分析 → DATA_QUERY
            ("上个月各地区的销售额", IntentType.DATA_QUERY),
            ("利润趋势", IntentType.DATA_QUERY),
            ("按产品统计订单数", IntentType.DATA_QUERY),
            
            # 无关 → IRRELEVANT
            ("你好", IntentType.IRRELEVANT),
            ("今天天气怎么样", IntentType.IRRELEVANT),
            
            # 模糊（L2 兜底）→ DATA_QUERY
            ("帮我看看", IntentType.DATA_QUERY),
        ]
        
        print("=" * 60)
        print("IntentRouter 测试（简化版）")
        print("=" * 60)
        
        for question, expected_intent in test_cases:
            result = await router.route(question)
            status = "✓" if result.intent_type == expected_intent else "✗"
            print(f"{status} '{question}'")
            print(f"   → {result.intent_type.value} (expected: {expected_intent.value})")
            print(f"   → source: {result.source}, confidence: {result.confidence:.2f}")
            print(f"   → reason: {result.reason}")
            print()
    
    asyncio.run(main())
