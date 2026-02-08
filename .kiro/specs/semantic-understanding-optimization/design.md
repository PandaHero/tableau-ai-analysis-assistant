# Design Document: Semantic Understanding Optimization (Phase 14)

## Overview

本设计文档描述了语义理解优化（Phase 14）的技术架构和实现方案。采用"规则先行 + 双 LLM 验证"的架构，在保证准确性的同时大幅减少 Token 消耗。

### 设计目标

1. **Token 优化**：SemanticUnderstanding 输入减少约 60%
2. **准确性提升**：规则 + LLM 双重验证
3. **延迟可控**：+200-300ms（FeatureExtractor），但主 LLM 推理更快
4. **可降级**：异常情况下能够降级运行，保证服务可用性

### 核心设计原则

| 原则 | 说明 |
|------|------|
| 规则先行 | RulePrefilter 必须执行，提取信息以减轻 LLM 负担 |
| 统一流程 | 所有查询都经过双 LLM（无分流），确保准确性 |
| 第一步轻量 | FeatureExtractor 使用快速模型验证+修正规则结果 |
| 第二步精简 | 基于第一步输出，裁剪 Prompt 和 Schema 以减少 Token |
| 种子充分利用 | 计算公式种子直接插入 Prompt |

### 关键架构约束

**FieldRetriever 必须在 FeatureExtractor 之后执行**：
- FeatureExtractor 输出 `required_measures` 和 `required_dimensions`
- FieldRetriever 使用这些输出进行 Top-K 检索并返回置信度分数
- **禁止并行执行**

### 术语与命名约定

| 术语 | 说明 |
|------|------|
| Phase 14 | 语义理解优化阶段的代号 |
| PrefilterResult | 规则预处理结果 |
| FeatureExtractionOutput | 特征提取输出 |
| FieldRAGResult | 字段检索结果（Top-K 候选 + 置信度） |


## Architecture

### 11 阶段优化架构

```
用户问题
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 1: IntentRouter (意图路由)                               │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题                                                │
│ 输出: 意图类型 (DATA_QUERY / CLARIFICATION / GENERAL / IRRELEVANT) │
│ LLM调用: 0-1 次                                               │
│ 数据源: keywords_data.py, rules_data.py                       │
│                                                              │
│ 如果意图是 IRRELEVANT → 直接返回礼貌拒绝                       │
│ 如果意图是 GENERAL → 直接返回元数据相关信息                    │
│ 如果意图是 DATA_QUERY → 继续下一阶段                           │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 2: QueryCache (查询缓存)                                 │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题, 数据源ID                                       │
│ 输出: 缓存的查询结果 或 继续下一阶段                            │
│ LLM调用: 0 次                                                 │
│                                                              │
│ 如果缓存命中 → 直接返回缓存结果                                │
│ 如果缓存未命中 → 继续下一阶段                                  │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 3: RulePrefilter (规则预处理) ⭐ 新增                     │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题                                                │
│ 输出: PrefilterResult                                         │
│ LLM调用: 0 次                                                 │
│ 数据源: keywords_data.py, computation_seeds.py, TimeHintGenerator │
│                                                              │
│ 处理内容:                                                     │
│ 1. 使用 keywords_data.py 检测复杂度类型                        │
│ 2. 使用 computation_seeds.py 匹配计算公式                      │
│ 3. 使用 TimeHintGenerator 生成时间提示                         │
│ 4. 计算 match_confidence                                      │
│                                                              │
│ 输出 PrefilterResult:                                         │
│ - time_hints: 时间表达式解析提示                               │
│ - matched_computations: 匹配的计算种子                         │
│ - detected_complexity: 检测到的复杂度类型                      │
│ - match_confidence: 规则匹配置信度                             │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 4: FeatureCache (特征缓存) ⭐ 新增                        │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 用户问题, 数据源ID                                       │
│ 输出: 缓存的特征 或 继续下一阶段                               │
│ LLM调用: 0 次                                                 │
│                                                              │
│ 缓存键: hash(question) + datasource_luid                      │
│ 语义匹配: embedding 相似度 > 0.95 时命中                       │
│                                                              │
│ 如果缓存命中 → 跳过 FeatureExtractor，直接到 FieldRetriever    │
│ 如果缓存未命中 → 继续下一阶段                                  │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 5: FeatureExtractor (特征提取) ⭐ 新增 - 第一次 LLM 调用   │
│ ─────────────────────────────────────────────────────────────│
│ 输入:                                                        │
│ - 用户问题                                                    │
│ - PrefilterResult（规则预处理结果）                            │
│                                                              │
│ 输出: FeatureExtractionOutput                                 │
│ LLM调用: 1 次（快速模型，~200 tokens 输入）                    │
│ 模型: DeepSeek-V3 或同等快速模型                               │
│                                                              │
│ 处理内容:                                                     │
│ 1. 验证规则提取的时间提示                                      │
│ 2. 验证规则匹配的计算类型                                      │
│ 3. 提取 required_measures 和 required_dimensions              │
│ 4. 计算 confirmation_confidence                               │
│                                                              │
│ 输出 FeatureExtractionOutput:                                 │
│ - required_measures: ["利润", "销售额"]                        │
│ - required_dimensions: ["城市", "地区"]                        │
│ - confirmed_time_hints: 确认后的时间提示                       │
│ - confirmed_computations: 确认后的计算种子                     │
│ - confirmation_confidence: LLM 确认置信度                      │
│                                                              │
│ 超时降级: 500ms 超时后使用 PrefilterResult 降级                │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 6: FieldRetriever (字段检索) ⭐ 依赖 FeatureExtractor     │
│ ─────────────────────────────────────────────────────────────│
│ 输入:                                                        │
│ - FeatureExtractionOutput.required_measures                   │
│ - FeatureExtractionOutput.required_dimensions                 │
│ - DataModel                                                   │
│                                                              │
│ 输出: FieldRAGResult                                          │
│ LLM调用: 0 次（向量检索）                                      │
│                                                              │
│ 处理内容:                                                     │
│ 1. 对 required_measures 进行 Top-K 检索                        │
│ 2. 对 required_dimensions 进行 Top-K 检索                      │
│ 3. 检索时间相关字段                                            │
│ 4. 计算每个候选字段的置信度分数                                │
│                                                              │
│ 输出 FieldRAGResult:                                          │
│ - measures: [{field_name, confidence, description}, ...]      │
│ - dimensions: [{field_name, confidence, description}, ...]    │
│ - time_fields: [{field_name, confidence, description}, ...]   │
│                                                              │
│ 关键: 输出 Top-K 候选 + 置信度，由主 LLM 最终选择              │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 7: DynamicSchemaBuilder + ModularPromptBuilder ⭐ 新增    │
│ ─────────────────────────────────────────────────────────────│
│ 输入:                                                        │
│ - FeatureExtractionOutput                                     │
│ - FieldRAGResult                                              │
│ - PrefilterResult                                             │
│                                                              │
│ 输出: 优化后的 Schema 和 Prompt                                │
│ LLM调用: 0 次                                                 │
│                                                              │
│ DynamicSchemaBuilder:                                         │
│ - 根据特征选择 Schema 模块（base/time/computation/filter）     │
│ - 只包含 FieldRAGResult 中的候选字段                           │
│ - 限制字段数量 <= MAX_FIELDS (20)                              │
│                                                              │
│ ModularPromptBuilder:                                         │
│ - 根据特征选择 Prompt 模块                                     │
│ - 插入匹配的计算种子（高置信度时）                             │
│ - 插入时间提示                                                 │
│ - 目标: Token 减少约 60%                                       │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 8: SemanticUnderstanding (语义理解) - 第二次 LLM 调用     │
│ ─────────────────────────────────────────────────────────────│
│ 输入:                                                        │
│ - 优化后的 Prompt（含计算种子、时间提示）                      │
│ - 优化后的 Schema（只含候选字段）                              │
│ - 对话历史                                                    │
│                                                              │
│ 输出: SemanticOutput                                          │
│ LLM调用: 1 次（主模型）                                        │
│                                                              │
│ 处理内容:                                                     │
│ 1. 调用主 LLM 生成 SemanticOutput                              │
│ 2. 保留现有的自校验机制（LLM 内部验证）                        │
│ 3. 保留现有的 ErrorCorrector 机制（错误修正）                  │
│                                                              │
│ 输出 SemanticOutput:                                          │
│ - restated_question: 完整独立的问题描述                        │
│ - what: 度量列表（从候选中选择）                               │
│ - where: 维度、过滤条件                                        │
│ - computations: 派生度量计算逻辑                               │
│ - needs_clarification: 是否需要澄清                            │
│ - overall_confidence: 综合置信度                               │
│                                                              │
│ 注意: OutputValidator（阶段9）是在自校验之上的额外验证层       │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 9: OutputValidator (输出验证) ⭐ 新增                     │
│ ─────────────────────────────────────────────────────────────│
│ 输入: SemanticOutput, FieldRAGResult                          │
│ 输出: 验证后的 SemanticOutput 或 错误信息                      │
│ LLM调用: 0 次                                                 │
│                                                              │
│ 验证内容:                                                     │
│ 1. 字段引用有效性（是否在 FieldRAGResult 中）                  │
│ 2. 计算表达式语法正确性                                        │
│ 3. 时间范围合理性                                              │
│                                                              │
│ 自动修正:                                                     │
│ - 字段名大小写修正                                             │
│ - 简单语法错误修正                                             │
│                                                              │
│ 如果验证通过 → 继续下一阶段                                    │
│ 如果不可修正 → 返回澄清请求                                    │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 10: FilterValueValidator (筛选值验证)                    │
│ ─────────────────────────────────────────────────────────────│
│ 输入: SemanticOutput 中的 filters                             │
│ 输出: 验证结果 (通过/需要澄清)                                 │
│ LLM调用: 0 次                                                 │
│                                                              │
│ 验证逻辑:                                                     │
│ 1. 检查筛选值是否存在于字段中                                  │
│ 2. 跳过时间字段和高基数字段                                    │
│ 3. 提供相似值建议                                              │
│                                                              │
│ 如果验证通过 → 继续下一阶段                                    │
│ 如果需要澄清 → 返回澄清问题                                    │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
┌──────────────────────────────────────────────────────────────┐
│ 阶段 11: QueryAdapter + 执行 + 缓存                           │
│ ─────────────────────────────────────────────────────────────│
│ 输入: 验证后的 SemanticOutput                                  │
│ 输出: 查询结果                                                 │
│ LLM调用: 0 次                                                 │
│                                                              │
│ 处理内容:                                                     │
│ 1. QueryAdapter 转换为目标查询语言                             │
│ 2. 执行查询                                                    │
│ 3. 缓存成功的查询（QueryCache）                                │
│ 4. 缓存特征（FeatureCache）                                    │
└──────────────────────────────────────────────────────────────┘
    │
    ▼
  返回结果
```


### LLM 调用次数分析

| 场景 | LLM 调用次数 | 说明 |
|------|-------------|------|
| 缓存命中（QueryCache） | 0-1 次 | IntentRouter 可能调用 |
| 特征缓存命中（FeatureCache） | 1 次 | 只调用 SemanticUnderstanding |
| 正常流程 | 2 次 | FeatureExtractor + SemanticUnderstanding |
| FeatureExtractor 超时降级 | 1 次 | 只调用 SemanticUnderstanding |
| 需要澄清 | 2 次/轮 | 每轮对话 |

### 数据流图

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           数据流向                                       │
├─────────────────────────────────────────────────────────────────────────┤
│                                                                          │
│  keywords_data.py ──┐                                                    │
│                     ├──► RulePrefilter ──► PrefilterResult               │
│  computation_seeds.py ─┤                        │                        │
│                     │                           │                        │
│  TimeHintGenerator ─┘                           ▼                        │
│                                          FeatureExtractor                │
│                                                 │                        │
│                                                 ▼                        │
│                                    FeatureExtractionOutput               │
│                                                 │                        │
│                                                 ▼                        │
│                                          FieldRetriever                  │
│                                                 │                        │
│                                                 ▼                        │
│                                          FieldRAGResult                  │
│                                                 │                        │
│                    ┌────────────────────────────┼────────────────────┐   │
│                    │                            │                    │   │
│                    ▼                            ▼                    │   │
│           DynamicSchemaBuilder          ModularPromptBuilder         │   │
│                    │                            │                    │   │
│                    └────────────────────────────┼────────────────────┘   │
│                                                 │                        │
│                                                 ▼                        │
│                                    SemanticUnderstanding                 │
│                                                 │                        │
│                                                 ▼                        │
│                                         SemanticOutput                   │
│                                                 │                        │
│                                                 ▼                        │
│                                        OutputValidator                   │
│                                                 │                        │
│                                                 ▼                        │
│                                    FilterValueValidator                  │
│                                                 │                        │
│                                                 ▼                        │
│                                          QueryAdapter                    │
└─────────────────────────────────────────────────────────────────────────┘

注意：DynamicSchemaBuilder 和 ModularPromptBuilder 都需要 FieldRAGResult 作为输入，
因此它们在 FieldRetriever 之后执行，可以并行处理。
```

### 种子文件使用映射

| 种子文件 | 使用位置 | 用途 |
|----------|----------|------|
| `keywords_data.py` | IntentRouter + RulePrefilter | 意图分类 + 复杂度检测 |
| `computation_seeds.py` | RulePrefilter + ModularPromptBuilder | 公式匹配 + Prompt 插入 |
| `rules_data.py` | IntentRouter | 无关问题过滤 |
| `seed_data.py` | DimensionHierarchyInference | 维度分类（现有功能） |


## SemanticParserState 扩展

Phase 14 需要在 `SemanticParserState` 中添加以下字段：

**文件位置**：`analytics_assistant/src/agents/semantic_parser/state.py`

```python
from typing import Optional
from .schemas.phase14 import (
    PrefilterResult,
    FeatureExtractionOutput,
    FieldRAGResult,
    ValidationResult,
)


class SemanticParserState(TypedDict):
    """SemanticParser 状态（Phase 14 扩展）"""
    
    # ... 现有字段 ...
    
    # Phase 14 新增字段
    prefilter_result: Optional[PrefilterResult]
    """规则预处理结果"""
    
    feature_extraction_output: Optional[FeatureExtractionOutput]
    """特征提取输出"""
    
    field_rag_result: Optional[FieldRAGResult]
    """字段检索结果（Top-K 候选 + 置信度）"""
    
    dynamic_schema: Optional[dict]
    """动态构建的 Schema"""
    
    modular_prompt: Optional[str]
    """模块化构建的 Prompt"""
    
    validation_result: Optional[ValidationResult]
    """输出验证结果"""
    
    is_degraded: bool
    """是否处于降级模式"""
    
    phase14_metrics: Optional[dict]
    """Phase 14 性能指标（各阶段耗时、Token 数等）"""
```


## Components and Interfaces

### 1. RulePrefilter

**职责**：规则预处理，无 LLM 调用，提取时间提示、匹配计算种子、检测复杂度

**文件位置**：`analytics_assistant/src/agents/semantic_parser/components/rule_prefilter.py`

```python
from typing import List, Optional
from pydantic import BaseModel, Field
from enum import Enum


class ComplexityType(str, Enum):
    """复杂度类型"""
    SIMPLE = "simple"           # 简单聚合
    RATIO = "ratio"             # 比率计算
    TIME_COMPARE = "time_compare"  # 同比/环比
    RANK = "rank"               # 排名
    SHARE = "share"             # 占比
    CUMULATIVE = "cumulative"   # 累计
    SUBQUERY = "subquery"       # 子查询


class MatchedComputation(BaseModel):
    """匹配的计算种子"""
    seed_name: str              # 种子名称（如 profit_rate）
    display_name: str           # 显示名称（如 利润率）
    calc_type: str              # 计算类型
    formula: Optional[str] = None  # 公式模板
    keywords_matched: List[str] = Field(default_factory=list)  # 匹配的关键词


class TimeHint(BaseModel):
    """时间提示"""
    original_expression: str    # 原始表达式（如 "上个月"）
    hint_type: str              # 提示类型（relative/absolute/range）
    parsed_hint: str            # 解析提示（如 "2024-01 到 2024-01"）
    confidence: float = 1.0     # 解析置信度


class PrefilterResult(BaseModel):
    """规则预处理结果"""
    time_hints: List[TimeHint] = Field(default_factory=list)
    matched_computations: List[MatchedComputation] = Field(default_factory=list)
    detected_complexity: List[ComplexityType] = Field(default_factory=list)
    detected_language: str = "zh"  # 检测到的语言
    match_confidence: float = 0.0  # 规则匹配置信度 (0-1)
    low_confidence: bool = False   # 是否低置信度


class RulePrefilter:
    """规则预处理器
    
    在 LLM 调用前进行规则预处理，提取：
    - 时间提示（使用 TimeHintGenerator）
    - 计算种子匹配（使用 computation_seeds.py）
    - 复杂度类型检测（使用 keywords_data.py）
    
    不调用 LLM，目标 50ms 内完成。
    """
    
    # 低置信度阈值
    LOW_CONFIDENCE_THRESHOLD = 0.7
    
    def __init__(self):
        self._load_config()
    
    def _load_config(self) -> None:
        """从 app.yaml 加载配置"""
        from analytics_assistant.src.infra.config import get_config
        config = get_config()
        phase14_config = config.get("semantic_parser", {}).get("phase14", {})
        self.LOW_CONFIDENCE_THRESHOLD = phase14_config.get(
            "low_confidence_threshold", 0.7
        )
    
    def prefilter(self, question: str) -> PrefilterResult:
        """执行规则预处理
        
        Args:
            question: 用户问题
            
        Returns:
            PrefilterResult 包含时间提示、计算种子、复杂度类型
        """
        # 1. 检测语言
        detected_language = self._detect_language(question)
        
        # 2. 生成时间提示
        time_hints = self._generate_time_hints(question)
        
        # 3. 匹配计算种子
        matched_computations = self._match_computations(question)
        
        # 4. 检测复杂度类型
        detected_complexity = self._detect_complexity(question)
        
        # 5. 计算匹配置信度
        match_confidence = self._calculate_confidence(
            time_hints, matched_computations, detected_complexity
        )
        
        return PrefilterResult(
            time_hints=time_hints,
            matched_computations=matched_computations,
            detected_complexity=detected_complexity,
            detected_language=detected_language,
            match_confidence=match_confidence,
            low_confidence=match_confidence < self.LOW_CONFIDENCE_THRESHOLD,
        )
    
    def _detect_language(self, question: str) -> str:
        """检测问题语言"""
        # 简单的语言检测逻辑
        import re
        if re.search(r'[\u4e00-\u9fff]', question):
            return "zh"
        elif re.search(r'[\u3040-\u309f\u30a0-\u30ff]', question):
            return "ja"
        return "en"
    
    def _generate_time_hints(self, question: str) -> List[TimeHint]:
        """生成时间提示"""
        from ..prompts.time_hint_generator import TimeHintGenerator
        generator = TimeHintGenerator()
        return generator.generate_hints(question)
    
    def _match_computations(self, question: str) -> List[MatchedComputation]:
        """匹配计算种子"""
        from ..computation_seeds import find_computations_in_text
        seeds = find_computations_in_text(question)
        return [
            MatchedComputation(
                seed_name=seed.name,
                display_name=seed.display_name,
                calc_type=seed.calc_type,
                formula=seed.formula,
                keywords_matched=seed.keywords,
            )
            for seed in seeds
        ]
    
    def _detect_complexity(self, question: str) -> List[ComplexityType]:
        """检测复杂度类型"""
        from ..keywords_data import COMPLEXITY_KEYWORDS
        
        detected = []
        question_lower = question.lower()
        
        # 检测派生度量
        if any(kw in question_lower for kw in COMPLEXITY_KEYWORDS.get("derived_metric", [])):
            detected.append(ComplexityType.RATIO)
        
        # 检测时间计算
        if any(kw in question_lower for kw in COMPLEXITY_KEYWORDS.get("time_calc", [])):
            detected.append(ComplexityType.TIME_COMPARE)
        
        # 检测子查询
        if any(kw in question_lower for kw in COMPLEXITY_KEYWORDS.get("subquery", [])):
            detected.append(ComplexityType.SUBQUERY)
        
        # 检测表计算
        if any(kw in question_lower for kw in COMPLEXITY_KEYWORDS.get("table_calc", [])):
            # 根据具体关键词细分
            if any(kw in question_lower for kw in ["排名", "排序"]):
                detected.append(ComplexityType.RANK)
            elif any(kw in question_lower for kw in ["累计", "累加"]):
                detected.append(ComplexityType.CUMULATIVE)
            elif any(kw in question_lower for kw in ["占比", "份额"]):
                detected.append(ComplexityType.SHARE)
        
        # 如果没有检测到复杂类型，标记为简单
        if not detected:
            detected.append(ComplexityType.SIMPLE)
        
        return detected
    
    def _calculate_confidence(
        self,
        time_hints: List[TimeHint],
        matched_computations: List[MatchedComputation],
        detected_complexity: List[ComplexityType],
    ) -> float:
        """计算匹配置信度
        
        置信度计算逻辑：
        - 时间提示匹配：+0.3
        - 计算种子匹配：+0.4
        - 复杂度检测（非 SIMPLE）：+0.3
        """
        confidence = 0.0
        
        if time_hints:
            confidence += 0.3 * min(1.0, sum(h.confidence for h in time_hints) / len(time_hints))
        
        if matched_computations:
            confidence += 0.4
        
        if detected_complexity and ComplexityType.SIMPLE not in detected_complexity:
            confidence += 0.3
        
        return min(1.0, confidence)
```


### 2. FeatureExtractor

**职责**：使用快速 LLM 验证规则结果，提取字段需求

**文件位置**：`analytics_assistant/src/agents/semantic_parser/components/feature_extractor.py`

```python
from typing import List, Optional
from pydantic import BaseModel, Field


class FeatureExtractionOutput(BaseModel):
    """特征提取输出"""
    required_measures: List[str] = Field(
        default_factory=list,
        description="需要的度量字段（业务术语，如 '利润', '销售额'）"
    )
    required_dimensions: List[str] = Field(
        default_factory=list,
        description="需要的维度字段（业务术语，如 '城市', '地区'）"
    )
    confirmed_time_hints: List[str] = Field(
        default_factory=list,
        description="确认后的时间提示"
    )
    confirmed_computations: List[str] = Field(
        default_factory=list,
        description="确认后的计算种子名称"
    )
    confirmation_confidence: float = Field(
        default=0.0,
        description="LLM 确认置信度 (0-1)"
    )
    is_degraded: bool = Field(
        default=False,
        description="是否为降级模式（超时后使用规则结果）"
    )


class FeatureExtractor:
    """特征提取器
    
    使用快速 LLM 验证规则预处理结果，提取：
    - required_measures: 需要的度量字段
    - required_dimensions: 需要的维度字段
    - 确认/修正时间提示和计算种子
    
    目标：~200 tokens 输入，300ms 内完成
    超时降级：500ms 超时后使用 PrefilterResult 降级
    """
    
    # 默认配置
    DEFAULT_TIMEOUT_MS = 500
    DEFAULT_MODEL = "deepseek-v3"
    
    def __init__(self):
        self._load_config()
    
    def _load_config(self) -> None:
        """从 app.yaml 加载配置"""
        from analytics_assistant.src.infra.config import get_config
        config = get_config()
        phase14_config = config.get("semantic_parser", {}).get("phase14", {})
        
        self.timeout_ms = phase14_config.get("feature_extractor_timeout_ms", self.DEFAULT_TIMEOUT_MS)
        self.model_name = phase14_config.get("feature_extractor_model", self.DEFAULT_MODEL)
    
    async def extract(
        self,
        question: str,
        prefilter_result: "PrefilterResult",
    ) -> FeatureExtractionOutput:
        """提取特征
        
        Args:
            question: 用户问题
            prefilter_result: 规则预处理结果
            
        Returns:
            FeatureExtractionOutput 包含字段需求和确认结果
            
        Raises:
            FeatureExtractorTimeoutError: 超时时抛出（调用方应降级处理）
        """
        import asyncio
        
        try:
            # 设置超时
            result = await asyncio.wait_for(
                self._do_extract(question, prefilter_result),
                timeout=self.timeout_ms / 1000.0,
            )
            return result
        except asyncio.TimeoutError:
            # 超时降级
            return self._create_degraded_output(prefilter_result)
    
    async def _do_extract(
        self,
        question: str,
        prefilter_result: "PrefilterResult",
    ) -> FeatureExtractionOutput:
        """执行特征提取（内部方法）"""
        from analytics_assistant.src.agents.base.node import get_llm
        from langchain_core.messages import SystemMessage, HumanMessage
        
        # 构建精简 Prompt（目标 ~200 tokens）
        system_prompt = self._build_system_prompt()
        user_prompt = self._build_user_prompt(question, prefilter_result)
        
        # 调用快速模型
        llm = get_llm(model_name=self.model_name)
        llm_with_output = llm.with_structured_output(FeatureExtractionOutput)
        
        result = await llm_with_output.ainvoke([
            SystemMessage(content=system_prompt),
            HumanMessage(content=user_prompt),
        ])
        
        return result
    
    def _build_system_prompt(self) -> str:
        """构建系统提示（精简版）"""
        return """你是一个特征提取助手。从用户问题中提取：
1. required_measures: 需要查询的度量（如"利润"、"销售额"）
2. required_dimensions: 需要的维度（如"城市"、"地区"）
3. 验证时间提示和计算类型是否正确

输出 JSON 格式。简洁回答。"""
    
    def _build_user_prompt(
        self,
        question: str,
        prefilter_result: "PrefilterResult",
    ) -> str:
        """构建用户提示"""
        parts = [f"问题: {question}"]
        
        if prefilter_result.time_hints:
            hints = [h.original_expression for h in prefilter_result.time_hints]
            parts.append(f"检测到的时间: {hints}")
        
        if prefilter_result.matched_computations:
            comps = [c.display_name for c in prefilter_result.matched_computations]
            parts.append(f"检测到的计算: {comps}")
        
        return "\n".join(parts)
    
    def _create_degraded_output(
        self,
        prefilter_result: "PrefilterResult",
    ) -> FeatureExtractionOutput:
        """创建降级输出（超时时使用）"""
        return FeatureExtractionOutput(
            required_measures=[],  # 降级时无法提取，由 FieldRetriever 使用全量检索
            required_dimensions=[],
            confirmed_time_hints=[h.original_expression for h in prefilter_result.time_hints],
            confirmed_computations=[c.seed_name for c in prefilter_result.matched_computations],
            confirmation_confidence=prefilter_result.match_confidence * 0.8,  # 降级置信度打折
            is_degraded=True,
        )
```


### 3. FeatureCache

**职责**：缓存特征提取结果，支持语义相似匹配

**文件位置**：`analytics_assistant/src/agents/semantic_parser/components/feature_cache.py`

```python
from typing import Optional, List
from datetime import datetime, timedelta
from pydantic import BaseModel, Field
import hashlib


class CachedFeature(BaseModel):
    """缓存的特征"""
    question: str
    question_hash: str
    question_embedding: List[float] = Field(default_factory=list)
    datasource_luid: str
    feature_output: dict  # FeatureExtractionOutput.model_dump()
    created_at: datetime
    expires_at: datetime
    hit_count: int = 0


class FeatureCache:
    """特征缓存
    
    缓存 FeatureExtractor 的输出，支持：
    - 精确匹配：hash(question + datasource_luid)
    - 语义匹配：embedding 相似度 > 0.95
    
    与 QueryCache 独立管理。
    """
    
    # 默认配置
    DEFAULT_TTL_SECONDS = 3600  # 1 小时
    SIMILARITY_THRESHOLD = 0.95
    
    # 缓存命名空间
    CACHE_NAMESPACE = ("semantic_parser", "feature_cache")
    
    def __init__(self, store, embedding_model):
        """
        Args:
            store: LangGraph SqliteStore 实例
            embedding_model: Embedding 模型
        """
        self._store = store
        self._embedding = embedding_model
        self._load_config()
    
    def _load_config(self) -> None:
        """从 app.yaml 加载配置"""
        from analytics_assistant.src.infra.config import get_config
        config = get_config()
        phase14_config = config.get("semantic_parser", {}).get("phase14", {})
        
        self.ttl_seconds = phase14_config.get("feature_cache_ttl_seconds", self.DEFAULT_TTL_SECONDS)
        self.similarity_threshold = phase14_config.get(
            "feature_cache_similarity_threshold", self.SIMILARITY_THRESHOLD
        )
    
    def _make_key(self, question: str, datasource_luid: str) -> str:
        """生成缓存键"""
        content = f"{question}:{datasource_luid}"
        return hashlib.md5(content.encode()).hexdigest()
    
    async def get(
        self,
        question: str,
        datasource_luid: str,
    ) -> Optional[CachedFeature]:
        """精确匹配获取缓存
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 ID
            
        Returns:
            CachedFeature 或 None
        """
        key = self._make_key(question, datasource_luid)
        namespace = (*self.CACHE_NAMESPACE, datasource_luid)
        
        try:
            items = await self._store.aget(namespace, key)
            if not items:
                return None
            
            cached = CachedFeature.model_validate(items[0].value)
            
            # TTL 检查
            if datetime.now() > cached.expires_at:
                return None
            
            # 更新命中计数
            cached.hit_count += 1
            await self._store.aput(namespace, key, cached.model_dump())
            
            return cached
        except Exception:
            return None
    
    async def get_similar(
        self,
        question: str,
        datasource_luid: str,
    ) -> Optional[CachedFeature]:
        """语义相似匹配获取缓存
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 ID
            
        Returns:
            相似度 > threshold 的 CachedFeature 或 None
        """
        # 计算问题 embedding
        question_embedding = await self._embedding.aembed_query(question)
        
        # 搜索该数据源的所有缓存
        namespace = (*self.CACHE_NAMESPACE, datasource_luid)
        
        try:
            # 使用 alist 获取该命名空间下所有缓存项
            # 注意：LangGraph SqliteStore 使用 alist 而非 asearch
            items = await self._store.alist(namespace)
            
            best_match = None
            best_similarity = 0.0
            
            for item in items:
                cached = CachedFeature.model_validate(item.value)
                
                # TTL 检查
                if datetime.now() > cached.expires_at:
                    continue
                
                # 计算相似度
                similarity = self._cosine_similarity(
                    question_embedding, cached.question_embedding
                )
                
                if similarity > self.similarity_threshold and similarity > best_similarity:
                    best_match = cached
                    best_similarity = similarity
            
            return best_match
        except Exception:
            return None
    
    async def set(
        self,
        question: str,
        datasource_luid: str,
        feature_output: "FeatureExtractionOutput",
    ) -> None:
        """设置缓存
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 ID
            feature_output: 特征提取输出
        """
        key = self._make_key(question, datasource_luid)
        namespace = (*self.CACHE_NAMESPACE, datasource_luid)
        
        # 计算 embedding
        question_embedding = await self._embedding.aembed_query(question)
        
        cached = CachedFeature(
            question=question,
            question_hash=key,
            question_embedding=question_embedding,
            datasource_luid=datasource_luid,
            feature_output=feature_output.model_dump(),
            created_at=datetime.now(),
            expires_at=datetime.now() + timedelta(seconds=self.ttl_seconds),
            hit_count=0,
        )
        
        await self._store.aput(namespace, key, cached.model_dump())
    
    def _cosine_similarity(self, vec1: List[float], vec2: List[float]) -> float:
        """计算余弦相似度"""
        import math
        
        if not vec1 or not vec2 or len(vec1) != len(vec2):
            return 0.0
        
        dot_product = sum(a * b for a, b in zip(vec1, vec2))
        norm1 = math.sqrt(sum(a * a for a in vec1))
        norm2 = math.sqrt(sum(b * b for b in vec2))
        
        if norm1 == 0 or norm2 == 0:
            return 0.0
        
        return dot_product / (norm1 * norm2)
```


### 4. FieldRetriever

**职责**：基于 FeatureExtractor 输出进行批量 Top-K 检索，返回候选字段及置信度

**文件位置**：`analytics_assistant/src/agents/semantic_parser/components/field_retriever.py`

**检索策略**：
1. **数据类型优先**：先按 role（measure/dimension）过滤
2. **维度类别增强**：对于维度字段，可结合维度推断的 category 和 category_detail 优化检索
3. **批量检索**：使用批量检索而非逐个检索，提高效率
4. **级联检索**：精确匹配 → 向量检索（复用 CascadeRetriever）

```python
from typing import List, Optional, Dict
from pydantic import BaseModel, Field


class FieldCandidate(BaseModel):
    """字段候选"""
    field_name: str
    confidence: float = Field(ge=0.0, le=1.0, description="置信度分数")
    description: Optional[str] = None
    sample_values: List[str] = Field(default_factory=list)
    data_type: Optional[str] = None
    field_type: Optional[str] = None  # dimension / measure
    category: Optional[str] = None  # 维度类别（来自维度推断）
    category_detail: Optional[str] = None  # 维度细分类别


class FieldRAGResult(BaseModel):
    """字段检索结果
    
    包含 Top-K 候选字段及置信度分数，
    由主 LLM 从候选中选择正确字段。
    """
    measures: List[FieldCandidate] = Field(
        default_factory=list,
        description="度量字段候选列表，按置信度降序"
    )
    dimensions: List[FieldCandidate] = Field(
        default_factory=list,
        description="维度字段候选列表，按置信度降序"
    )
    time_fields: List[FieldCandidate] = Field(
        default_factory=list,
        description="时间字段候选列表，按置信度降序"
    )


class FieldRetriever:
    """字段检索器
    
    基于 FeatureExtractor 输出进行批量 Top-K 检索：
    - 使用 required_measures 批量检索度量字段
    - 使用 required_dimensions 批量检索维度字段
    - 返回 Top-K 候选 + 置信度分数
    
    检索优化：
    - 数据类型优先：先按 role 过滤，缩小检索范围
    - 维度类别增强：利用维度推断的 category/category_detail 优化维度检索
    - 批量检索：一次性检索多个术语，避免多次网络往返
    
    关键：必须在 FeatureExtractor 之后执行
    """
    
    # 默认配置
    DEFAULT_TOP_K = 5
    
    def __init__(self, retrieval_pipeline, field_indexer):
        """
        Args:
            retrieval_pipeline: RetrievalPipeline 实例
            field_indexer: FieldIndexer 实例（用于批量检索）
        """
        self._pipeline = retrieval_pipeline
        self._indexer = field_indexer
        self._load_config()
    
    def _load_config(self) -> None:
        """从 app.yaml 加载配置"""
        from analytics_assistant.src.infra.config import get_config
        config = get_config()
        phase14_config = config.get("semantic_parser", {}).get("phase14", {})
        
        self.top_k = phase14_config.get("field_retriever_top_k", self.DEFAULT_TOP_K)
    
    async def retrieve(
        self,
        feature_output: "FeatureExtractionOutput",
        data_model: "DataModel",
    ) -> FieldRAGResult:
        """批量检索字段
        
        Args:
            feature_output: FeatureExtractor 输出
            data_model: 数据模型
            
        Returns:
            FieldRAGResult 包含 Top-K 候选字段及置信度
        """
        # 1. 批量检索度量字段（按 role=measure 过滤）
        measures = await self._batch_retrieve(
            terms=feature_output.required_measures,
            role_filter="measure",
        )
        
        # 2. 批量检索维度字段（按 role=dimension 过滤，可结合 category 优化）
        dimensions = await self._batch_retrieve(
            terms=feature_output.required_dimensions,
            role_filter="dimension",
        )
        
        # 3. 批量检索时间字段（按 data_type 过滤）
        time_fields = await self._batch_retrieve_time_fields()
        
        return FieldRAGResult(
            measures=measures,
            dimensions=dimensions,
            time_fields=time_fields,
        )
    
    async def _batch_retrieve(
        self,
        terms: List[str],
        role_filter: str,
        category_filter: Optional[str] = None,
    ) -> List[FieldCandidate]:
        """批量检索字段
        
        Args:
            terms: 检索术语列表
            role_filter: 角色过滤（measure/dimension）
            category_filter: 类别过滤（可选，用于维度优化）
        """
        if not terms:
            # 降级模式：返回该角色的所有字段
            return self._get_all_by_role(role_filter)
        
        # 批量检索：一次性处理所有术语
        from analytics_assistant.src.infra.rag.retriever import MetadataFilter
        
        filters = MetadataFilter(role=role_filter, category=category_filter)
        
        # 使用 batch_search 批量检索
        batch_results = self._pipeline.batch_search(
            queries=terms,
            top_k=self.top_k,
            filters=filters,
        )
        
        # 合并结果
        candidates = []
        for term, results in batch_results.items():
            for result in results:
                candidates.append(FieldCandidate(
                    field_name=result.field_chunk.field_name,
                    confidence=result.score,
                    description=result.field_chunk.field_caption,
                    sample_values=result.field_chunk.sample_values or [],
                    data_type=result.field_chunk.data_type,
                    field_type=role_filter,
                    category=result.field_chunk.category,
                ))
        
        # 去重并按置信度排序
        return self._dedupe_and_sort(candidates)
    
    async def _batch_retrieve_time_fields(self) -> List[FieldCandidate]:
        """批量检索时间字段
        
        使用数据类型过滤 + 批量向量检索的组合策略
        """
        from analytics_assistant.src.infra.rag.retriever import MetadataFilter
        import asyncio
        
        # 按数据类型过滤时间字段
        time_data_types = ["date", "datetime", "timestamp"]
        
        # 并发检索所有时间数据类型
        async def search_by_type(data_type: str) -> List[FieldCandidate]:
            filters = MetadataFilter(data_type=data_type)
            results = await self._pipeline.asearch(
                query="时间 日期",  # 通用时间查询
                top_k=self.top_k,
                filters=filters,
            )
            return [
                FieldCandidate(
                    field_name=result.field_chunk.field_name,
                    confidence=result.score,
                    description=result.field_chunk.field_caption,
                    data_type=result.field_chunk.data_type,
                    field_type="dimension",
                )
                for result in results
            ]
        
        # 并发执行所有检索
        all_results = await asyncio.gather(
            *[search_by_type(dt) for dt in time_data_types]
        )
        
        # 合并结果
        candidates = []
        for result_list in all_results:
            candidates.extend(result_list)
        
        return self._dedupe_and_sort(candidates)
    
    async def _retrieve_dimensions_with_category(
        self,
        required_dimensions: List[str],
        confirmed_computations: List[dict],
    ) -> List[FieldCandidate]:
        """利用维度类别优化检索
        
        根据计算类型推断需要的维度类别，优化检索精度：
        - TIME_COMPARE → 优先检索 category=TIME 的维度
        - RANK/SHARE → 优先检索 category=GEOGRAPHY 或 PRODUCT 的维度
        """
        # 根据计算类型推断维度类别
        category_hints = self._infer_category_from_computations(confirmed_computations)
        
        candidates = []
        for term in required_dimensions:
            # 优先使用类别过滤检索
            for category in category_hints:
                results = await self._batch_retrieve(
                    terms=[term],
                    role_filter="dimension",
                    category_filter=category,
                )
                candidates.extend(results)
            
            # 如果类别检索结果不足，回退到无类别过滤
            if len(candidates) < self.top_k:
                fallback_results = await self._batch_retrieve(
                    terms=[term],
                    role_filter="dimension",
                )
                candidates.extend(fallback_results)
        
        return self._dedupe_and_sort(candidates)
    
    def _infer_category_from_computations(
        self,
        confirmed_computations: List[dict],
    ) -> List[str]:
        """根据计算类型推断维度类别"""
        categories = []
        for comp in confirmed_computations:
            calc_type = comp.get("calc_type", "")
            if calc_type == "TIME_COMPARE":
                categories.append("TIME")
            elif calc_type in ["RANK", "SHARE"]:
                categories.extend(["GEOGRAPHY", "PRODUCT", "ORGANIZATION"])
        return list(set(categories))
    
    def _dedupe_and_sort(
        self,
        candidates: List[FieldCandidate],
    ) -> List[FieldCandidate]:
        """去重并按置信度降序排序"""
        seen = {}
        for c in candidates:
            if c.field_name not in seen or c.confidence > seen[c.field_name].confidence:
                seen[c.field_name] = c
        
        return sorted(seen.values(), key=lambda x: x.confidence, reverse=True)[:self.top_k]
    
    def _get_all_by_role(self, role: str) -> List[FieldCandidate]:
        """获取指定角色的所有字段（降级模式）"""
        all_chunks = self._indexer.get_all_chunks()
        candidates = [
            FieldCandidate(
                field_name=chunk.field_name,
                confidence=0.5,  # 降级模式置信度较低
                description=chunk.field_caption,
                data_type=chunk.data_type,
                field_type=role,
                category=chunk.category,
            )
            for chunk in all_chunks
            if chunk.role == role
        ]
        return candidates[:self.top_k * 2]  # 降级时返回更多候选
```


### 5. DynamicSchemaBuilder

**职责**：根据特征动态构建 Schema，减少 Token 消耗

**文件位置**：`analytics_assistant/src/agents/semantic_parser/components/dynamic_schema_builder.py`

```python
from typing import List, Set
from enum import Enum


class SchemaModule(str, Enum):
    """Schema 模块类型"""
    BASE = "base"               # 基础模块（始终包含）
    TIME = "time"               # 时间模块
    COMPUTATION = "computation" # 计算模块
    FILTER = "filter"           # 筛选模块
    CLARIFICATION = "clarification"  # 澄清模块


class DynamicSchemaBuilder:
    """动态 Schema 构建器
    
    根据 FeatureExtractionOutput 选择 Schema 模块，
    只包含 FieldRAGResult 中的候选字段，
    限制字段数量 <= MAX_FIELDS。
    """
    
    # 默认配置
    MAX_FIELDS = 20
    
    def __init__(self):
        self._load_config()
    
    def _load_config(self) -> None:
        """从 app.yaml 加载配置"""
        from analytics_assistant.src.infra.config import get_config
        config = get_config()
        phase14_config = config.get("semantic_parser", {}).get("phase14", {})
        
        self.max_fields = phase14_config.get("max_schema_fields", self.MAX_FIELDS)
    
    def build(
        self,
        feature_output: "FeatureExtractionOutput",
        field_rag_result: "FieldRAGResult",
        prefilter_result: "PrefilterResult",
    ) -> dict:
        """构建动态 Schema
        
        Args:
            feature_output: 特征提取输出
            field_rag_result: 字段检索结果
            prefilter_result: 规则预处理结果
            
        Returns:
            动态 Schema 字典
        """
        # 1. 选择需要的模块
        modules = self._select_modules(feature_output, prefilter_result)
        
        # 2. 收集字段
        fields = self._collect_fields(field_rag_result, modules)
        
        # 3. 构建 Schema（传入 feature_output 和 prefilter_result 用于细分计算类型选择）
        schema = self._build_schema(fields, modules, feature_output, prefilter_result)
        
        return schema
    
    def _select_modules(
        self,
        feature_output: "FeatureExtractionOutput",
        prefilter_result: "PrefilterResult",
    ) -> Set[SchemaModule]:
        """选择需要的 Schema 模块"""
        modules = {SchemaModule.BASE}  # 始终包含基础模块
        
        # 检测到时间表达式
        if feature_output.confirmed_time_hints or prefilter_result.time_hints:
            modules.add(SchemaModule.TIME)
        
        # 检测到计算需求
        if feature_output.confirmed_computations or prefilter_result.matched_computations:
            modules.add(SchemaModule.COMPUTATION)
        
        # 检测到复杂度类型（非 SIMPLE）
        from .rule_prefilter import ComplexityType
        if prefilter_result.detected_complexity:
            if ComplexityType.SIMPLE not in prefilter_result.detected_complexity:
                modules.add(SchemaModule.COMPUTATION)
        
        return modules
    
    def _collect_fields(
        self,
        field_rag_result: "FieldRAGResult",
        modules: Set[SchemaModule],
    ) -> List[dict]:
        """收集字段"""
        fields = []
        
        # 添加度量字段
        for candidate in field_rag_result.measures:
            fields.append({
                "name": candidate.field_name,
                "type": "measure",
                "confidence": candidate.confidence,
                "description": candidate.description,
            })
        
        # 添加维度字段
        for candidate in field_rag_result.dimensions:
            fields.append({
                "name": candidate.field_name,
                "type": "dimension",
                "confidence": candidate.confidence,
                "description": candidate.description,
            })
        
        # 添加时间字段（如果需要时间模块）
        if SchemaModule.TIME in modules:
            for candidate in field_rag_result.time_fields:
                fields.append({
                    "name": candidate.field_name,
                    "type": "time",
                    "confidence": candidate.confidence,
                    "description": candidate.description,
                })
        
        # 按置信度排序并限制数量
        fields.sort(key=lambda x: x["confidence"], reverse=True)
        return fields[:self.max_fields]
    
    def _build_schema(
        self,
        fields: List[dict],
        modules: Set[SchemaModule],
        feature_output: "FeatureExtractionOutput" = None,
        prefilter_result: "PrefilterResult" = None,
    ) -> dict:
        """构建 Schema 字典
        
        根据细分计算类型只选择相关的 computation_types，
        而不是包含所有计算类型。
        """
        schema = {
            "modules": [m.value for m in modules],
            "fields": fields,
            "field_count": len(fields),
        }
        
        # 添加模块特定的 Schema 扩展
        if SchemaModule.COMPUTATION in modules:
            # 根据细分计算类型选择相关的 computation_types
            schema["computation_types"] = self._select_computation_types(
                feature_output, prefilter_result
            )
        
        if SchemaModule.TIME in modules:
            schema["time_expressions"] = [
                "relative", "absolute", "range", "period",
            ]
        
        return schema
    
    def _select_computation_types(
        self,
        feature_output: "FeatureExtractionOutput",
        prefilter_result: "PrefilterResult",
    ) -> List[str]:
        """根据细分计算类型选择相关的 computation_types
        
        不同的 calc_type 对应不同的计算类型子集：
        - RATIO/SHARE → 比率相关
        - TIME_COMPARE → 时间计算相关
        - RANK → 排名相关
        - CUMULATIVE → 累计相关
        - SIMPLE → 基础聚合
        """
        from .rule_prefilter import ComplexityType
        
        # 收集所有确认的计算类型
        calc_types = set()
        
        # 从 FeatureExtractor 确认的计算
        if feature_output and feature_output.confirmed_computations:
            for comp in feature_output.confirmed_computations:
                if isinstance(comp, dict):
                    calc_types.add(comp.get("calc_type", ""))
                elif hasattr(comp, "calc_type"):
                    calc_types.add(comp.calc_type)
        
        # 从 RulePrefilter 检测的复杂度
        if prefilter_result and prefilter_result.detected_complexity:
            for complexity in prefilter_result.detected_complexity:
                calc_types.add(complexity.value if hasattr(complexity, 'value') else str(complexity))
        
        # 根据 calc_type 映射到具体的 computation_types
        computation_types = set()
        
        for calc_type in calc_types:
            if calc_type in ["ratio", "RATIO"]:
                computation_types.update(["RATIO", "DIFFERENCE", "PRODUCT"])
            elif calc_type in ["share", "SHARE"]:
                computation_types.update(["RATIO", "TABLE_CALC_PERCENT_OF_TOTAL"])
            elif calc_type in ["time_compare", "TIME_COMPARE"]:
                computation_types.update(["TABLE_CALC_PERCENT_DIFF", "TABLE_CALC_DIFF", "DIFFERENCE"])
            elif calc_type in ["rank", "RANK"]:
                computation_types.update(["TABLE_CALC_RANK"])
            elif calc_type in ["cumulative", "CUMULATIVE"]:
                computation_types.update(["TABLE_CALC_RUNNING_SUM", "TABLE_CALC_RUNNING_AVG"])
            elif calc_type in ["subquery", "SUBQUERY"]:
                computation_types.update(["SUBQUERY", "NESTED"])
            elif calc_type in ["simple", "SIMPLE"]:
                computation_types.update(["SUM", "AVG", "COUNT", "MIN", "MAX"])
        
        # 如果没有检测到任何类型，返回基础聚合
        if not computation_types:
            computation_types = {"SUM", "AVG", "COUNT", "MIN", "MAX"}
        
        return sorted(list(computation_types))
```


### 6. ModularPromptBuilder

**职责**：根据特征模块化组装 Prompt，插入计算种子和时间提示

**文件位置**：`analytics_assistant/src/agents/semantic_parser/prompts/modular_prompt_builder.py`

```python
from typing import List, Optional, Set


class ModularPromptBuilder:
    """模块化 Prompt 构建器
    
    根据 FeatureExtractionOutput 选择 Prompt 模块：
    - 插入匹配的计算种子（高置信度时）
    - 插入时间提示
    - 根据语言调整内容
    
    目标：Token 减少约 60%
    """
    
    # 低置信度阈值（低于此值不插入计算种子）
    LOW_CONFIDENCE_THRESHOLD = 0.7
    
    def __init__(self):
        self._load_config()
    
    def _load_config(self) -> None:
        """从 app.yaml 加载配置"""
        from analytics_assistant.src.infra.config import get_config
        config = get_config()
        phase14_config = config.get("semantic_parser", {}).get("phase14", {})
        
        self.low_confidence_threshold = phase14_config.get(
            "low_confidence_threshold", self.LOW_CONFIDENCE_THRESHOLD
        )
    
    def build(
        self,
        feature_output: "FeatureExtractionOutput",
        prefilter_result: "PrefilterResult",
        dynamic_schema: dict,
        conversation_history: Optional[List[dict]] = None,
    ) -> str:
        """构建模块化 Prompt
        
        Args:
            feature_output: 特征提取输出
            prefilter_result: 规则预处理结果
            dynamic_schema: 动态 Schema
            conversation_history: 对话历史
            
        Returns:
            组装后的 Prompt 字符串
        """
        parts = []
        
        # 1. 基础指令模块（始终包含）
        parts.append(self._build_base_module(prefilter_result.detected_language))
        
        # 2. 字段列表模块
        parts.append(self._build_fields_module(dynamic_schema))
        
        # 3. 时间提示模块（如果有）
        if feature_output.confirmed_time_hints or prefilter_result.time_hints:
            parts.append(self._build_time_module(
                feature_output.confirmed_time_hints,
                prefilter_result.time_hints,
            ))
        
        # 4. 计算种子模块（高置信度时）
        if self._should_insert_computation_seeds(feature_output, prefilter_result):
            parts.append(self._build_computation_module(
                feature_output.confirmed_computations,
                prefilter_result.matched_computations,
            ))
        
        # 5. 对话历史模块（如果有）
        if conversation_history:
            parts.append(self._build_history_module(conversation_history))
        
        return "\n\n".join(parts)
    
    def _should_insert_computation_seeds(
        self,
        feature_output: "FeatureExtractionOutput",
        prefilter_result: "PrefilterResult",
    ) -> bool:
        """判断是否应该插入计算种子
        
        低置信度时不插入，避免误导 LLM
        """
        # 检查 LLM 确认置信度
        if feature_output.confirmation_confidence < self.low_confidence_threshold:
            return False
        
        # 检查规则匹配置信度
        if prefilter_result.low_confidence:
            return False
        
        # 检查是否有匹配的计算
        return bool(
            feature_output.confirmed_computations or
            prefilter_result.matched_computations
        )
    
    def _build_base_module(self, language: str) -> str:
        """构建基础指令模块"""
        if language == "zh":
            return """<instructions>
你是一个数据分析助手。根据用户问题，从候选字段中选择正确的字段，生成结构化查询。

输出要求：
1. restated_question: 用完整的句子重述用户问题
2. what.measures: 从候选度量中选择需要的字段
3. where.dimensions: 从候选维度中选择需要的字段
4. where.filters: 筛选条件
5. computations: 派生度量计算（如果需要）
</instructions>"""
        else:
            return """<instructions>
You are a data analysis assistant. Based on the user's question, select the correct fields from candidates and generate a structured query.

Output requirements:
1. restated_question: Restate the user's question in a complete sentence
2. what.measures: Select required fields from measure candidates
3. where.dimensions: Select required fields from dimension candidates
4. where.filters: Filter conditions
5. computations: Derived measure calculations (if needed)
</instructions>"""
    
    def _build_fields_module(self, dynamic_schema: dict) -> str:
        """构建字段列表模块"""
        lines = ["<candidate_fields>"]
        
        # 按类型分组
        measures = [f for f in dynamic_schema["fields"] if f["type"] == "measure"]
        dimensions = [f for f in dynamic_schema["fields"] if f["type"] == "dimension"]
        time_fields = [f for f in dynamic_schema["fields"] if f["type"] == "time"]
        
        if measures:
            lines.append("度量字段:")
            for f in measures:
                desc = f.get("description", "")
                conf = f.get("confidence", 0)
                lines.append(f"  - {f['name']} (置信度:{conf:.2f}) {desc}")
        
        if dimensions:
            lines.append("维度字段:")
            for f in dimensions:
                desc = f.get("description", "")
                conf = f.get("confidence", 0)
                lines.append(f"  - {f['name']} (置信度:{conf:.2f}) {desc}")
        
        if time_fields:
            lines.append("时间字段:")
            for f in time_fields:
                lines.append(f"  - {f['name']}")
        
        lines.append("</candidate_fields>")
        return "\n".join(lines)
    
    def _build_time_module(
        self,
        confirmed_hints: List[str],
        prefilter_hints: List["TimeHint"],
    ) -> str:
        """构建时间提示模块"""
        lines = ["<time_hints>"]
        lines.append("检测到的时间表达式:")
        
        # 优先使用 LLM 确认的提示
        if confirmed_hints:
            for hint in confirmed_hints:
                lines.append(f"  - {hint}")
        elif prefilter_hints:
            for hint in prefilter_hints:
                lines.append(f"  - {hint.original_expression} → {hint.parsed_hint}")
        
        lines.append("</time_hints>")
        return "\n".join(lines)
    
    def _build_computation_module(
        self,
        confirmed_computations: List[str],
        prefilter_computations: List["MatchedComputation"],
    ) -> str:
        """构建计算种子模块"""
        from ..computation_seeds import get_computation_by_keyword, COMPUTATION_SEEDS
        
        lines = ["<computation_hints>"]
        lines.append("检测到的计算类型（请参考以下公式）:")
        
        # 收集需要展示的计算种子
        seeds_to_show = set()
        
        if confirmed_computations:
            seeds_to_show.update(confirmed_computations)
        
        if prefilter_computations:
            for comp in prefilter_computations:
                seeds_to_show.add(comp.seed_name)
        
        # 展示计算种子详情
        for seed_name in seeds_to_show:
            for seed in COMPUTATION_SEEDS:
                if seed.name == seed_name:
                    lines.append(f"  - {seed.display_name}:")
                    lines.append(f"    类型: {seed.calc_type}")
                    if seed.formula:
                        lines.append(f"    公式: {seed.formula}")
                    if seed.description:
                        lines.append(f"    说明: {seed.description}")
                    break
        
        lines.append("</computation_hints>")
        return "\n".join(lines)
    
    def _build_history_module(self, conversation_history: List[dict]) -> str:
        """构建对话历史模块"""
        lines = ["<conversation_history>"]
        
        # 只保留最近 3 轮对话
        recent_history = conversation_history[-6:]  # 3 轮 = 6 条消息
        
        for msg in recent_history:
            role = msg.get("role", "user")
            content = msg.get("content", "")
            # 截断过长的内容
            if len(content) > 200:
                content = content[:200] + "..."
            lines.append(f"{role}: {content}")
        
        lines.append("</conversation_history>")
        return "\n".join(lines)
```


### 7. OutputValidator

**职责**：预验证 LLM 输出，自动修正简单错误

**文件位置**：`analytics_assistant/src/agents/semantic_parser/components/output_validator.py`

```python
from typing import List, Optional, Tuple
from pydantic import BaseModel, Field
from enum import Enum


class ValidationErrorType(str, Enum):
    """验证错误类型"""
    INVALID_FIELD = "invalid_field"           # 无效字段引用
    SYNTAX_ERROR = "syntax_error"             # 语法错误
    MISSING_REQUIRED = "missing_required"     # 缺少必需字段
    TYPE_MISMATCH = "type_mismatch"           # 类型不匹配


class ValidationError(BaseModel):
    """验证错误"""
    error_type: ValidationErrorType
    field_name: Optional[str] = None
    message: str
    auto_correctable: bool = False
    suggested_correction: Optional[str] = None


class ValidationResult(BaseModel):
    """验证结果"""
    is_valid: bool
    errors: List[ValidationError] = Field(default_factory=list)
    corrected_output: Optional[dict] = None  # 自动修正后的输出
    needs_clarification: bool = False
    clarification_message: Optional[str] = None


class OutputValidator:
    """输出验证器
    
    在 SemanticUnderstanding 输出后立即执行：
    - 验证字段引用有效性
    - 验证计算表达式语法
    - 自动修正简单错误
    
    减少对 ErrorCorrector 的依赖。
    """
    
    def validate(
        self,
        semantic_output: "SemanticOutput",
        field_rag_result: "FieldRAGResult",
    ) -> ValidationResult:
        """验证 LLM 输出
        
        Args:
            semantic_output: SemanticUnderstanding 输出
            field_rag_result: 字段检索结果
            
        Returns:
            ValidationResult 包含验证结果和可能的修正
        """
        errors = []
        corrected_output = semantic_output.model_dump()
        
        # 1. 验证度量字段
        measure_errors, corrected_measures = self._validate_measures(
            semantic_output.what.measures if semantic_output.what else [],
            field_rag_result,
        )
        errors.extend(measure_errors)
        if corrected_measures:
            corrected_output["what"]["measures"] = corrected_measures
        
        # 2. 验证维度字段
        dimension_errors, corrected_dimensions = self._validate_dimensions(
            semantic_output.where.dimensions if semantic_output.where else [],
            field_rag_result,
        )
        errors.extend(dimension_errors)
        if corrected_dimensions:
            corrected_output["where"]["dimensions"] = corrected_dimensions
        
        # 3. 验证计算表达式
        if semantic_output.computations:
            comp_errors = self._validate_computations(
                semantic_output.computations,
                field_rag_result,
            )
            errors.extend(comp_errors)
        
        # 判断是否需要澄清
        uncorrectable_errors = [e for e in errors if not e.auto_correctable]
        
        if uncorrectable_errors:
            return ValidationResult(
                is_valid=False,
                errors=errors,
                needs_clarification=True,
                clarification_message=self._build_clarification_message(uncorrectable_errors),
            )
        
        # 所有错误都可自动修正
        if errors:
            return ValidationResult(
                is_valid=True,
                errors=errors,
                corrected_output=corrected_output,
            )
        
        return ValidationResult(is_valid=True)
    
    def _validate_measures(
        self,
        measures: List[str],
        field_rag_result: "FieldRAGResult",
    ) -> Tuple[List[ValidationError], Optional[List[str]]]:
        """验证度量字段"""
        errors = []
        corrected = []
        valid_names = {c.field_name.lower(): c.field_name for c in field_rag_result.measures}
        
        for measure in measures:
            if measure.lower() in valid_names:
                # 修正大小写
                corrected.append(valid_names[measure.lower()])
            else:
                # 尝试模糊匹配
                best_match = self._fuzzy_match(measure, list(valid_names.values()))
                if best_match:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.INVALID_FIELD,
                        field_name=measure,
                        message=f"字段 '{measure}' 不在候选列表中，已修正为 '{best_match}'",
                        auto_correctable=True,
                        suggested_correction=best_match,
                    ))
                    corrected.append(best_match)
                else:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.INVALID_FIELD,
                        field_name=measure,
                        message=f"字段 '{measure}' 不在候选列表中，无法自动修正",
                        auto_correctable=False,
                    ))
        
        return errors, corrected if corrected else None
    
    def _validate_dimensions(
        self,
        dimensions: List[str],
        field_rag_result: "FieldRAGResult",
    ) -> Tuple[List[ValidationError], Optional[List[str]]]:
        """验证维度字段"""
        errors = []
        corrected = []
        valid_names = {c.field_name.lower(): c.field_name for c in field_rag_result.dimensions}
        # 也包含时间字段
        for c in field_rag_result.time_fields:
            valid_names[c.field_name.lower()] = c.field_name
        
        for dimension in dimensions:
            if dimension.lower() in valid_names:
                corrected.append(valid_names[dimension.lower()])
            else:
                best_match = self._fuzzy_match(dimension, list(valid_names.values()))
                if best_match:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.INVALID_FIELD,
                        field_name=dimension,
                        message=f"字段 '{dimension}' 不在候选列表中，已修正为 '{best_match}'",
                        auto_correctable=True,
                        suggested_correction=best_match,
                    ))
                    corrected.append(best_match)
                else:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.INVALID_FIELD,
                        field_name=dimension,
                        message=f"字段 '{dimension}' 不在候选列表中，无法自动修正",
                        auto_correctable=False,
                    ))
        
        return errors, corrected if corrected else None
    
    def _validate_computations(
        self,
        computations: List[dict],
        field_rag_result: "FieldRAGResult",
    ) -> List[ValidationError]:
        """验证计算表达式"""
        errors = []
        valid_measures = {c.field_name for c in field_rag_result.measures}
        
        for comp in computations:
            # 检查 base_measures 是否有效
            base_measures = comp.get("base_measures", [])
            for measure in base_measures:
                if measure not in valid_measures:
                    errors.append(ValidationError(
                        error_type=ValidationErrorType.INVALID_FIELD,
                        field_name=measure,
                        message=f"计算表达式中的字段 '{measure}' 不在候选列表中",
                        auto_correctable=False,
                    ))
            
            # 检查公式语法（简单检查括号匹配）
            formula = comp.get("formula", "")
            if formula and not self._check_brackets(formula):
                errors.append(ValidationError(
                    error_type=ValidationErrorType.SYNTAX_ERROR,
                    message=f"公式 '{formula}' 括号不匹配",
                    auto_correctable=False,
                ))
        
        return errors
    
    def _fuzzy_match(self, target: str, candidates: List[str], threshold: float = 0.8) -> Optional[str]:
        """模糊匹配"""
        from difflib import SequenceMatcher
        
        best_match = None
        best_ratio = 0.0
        
        for candidate in candidates:
            ratio = SequenceMatcher(None, target.lower(), candidate.lower()).ratio()
            if ratio > threshold and ratio > best_ratio:
                best_match = candidate
                best_ratio = ratio
        
        return best_match
    
    def _check_brackets(self, formula: str) -> bool:
        """检查括号是否匹配"""
        stack = []
        brackets = {'(': ')', '[': ']', '{': '}'}
        
        for char in formula:
            if char in brackets:
                stack.append(char)
            elif char in brackets.values():
                if not stack:
                    return False
                if brackets[stack.pop()] != char:
                    return False
        
        return len(stack) == 0
    
    def _build_clarification_message(self, errors: List[ValidationError]) -> str:
        """构建澄清消息"""
        messages = []
        for error in errors:
            if error.error_type == ValidationErrorType.INVALID_FIELD:
                messages.append(f"无法识别字段 '{error.field_name}'")
            else:
                messages.append(error.message)
        
        return "请确认以下问题：\n" + "\n".join(f"- {m}" for m in messages)
```


### 8. Phase14 异常定义

**职责**：统一的异常层次结构

**文件位置**：`analytics_assistant/src/core/exceptions.py`（扩展）

```python
from typing import Optional, Dict, Any


class Phase14Error(Exception):
    """Phase 14 优化架构异常基类"""
    
    def __init__(
        self,
        message: str,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message)
        self.message = message
        self.context = context or {}
    
    def __str__(self) -> str:
        if self.context:
            return f"{self.message} | context: {self.context}"
        return self.message


class RulePrefilterError(Phase14Error):
    """规则预处理异常"""
    pass


class FeatureExtractionError(Phase14Error):
    """特征提取异常"""
    pass


class FeatureExtractorTimeoutError(FeatureExtractionError):
    """特征提取超时异常
    
    当 FeatureExtractor 超时时抛出，
    调用方应降级使用 PrefilterResult。
    """
    
    def __init__(
        self,
        timeout_ms: int,
        context: Optional[Dict[str, Any]] = None,
    ):
        message = f"FeatureExtractor 超时 ({timeout_ms}ms)"
        super().__init__(message, context)
        self.timeout_ms = timeout_ms


class FieldRetrievalError(Phase14Error):
    """字段检索异常"""
    pass


class OutputValidationError(Phase14Error):
    """输出验证异常"""
    
    def __init__(
        self,
        message: str,
        validation_errors: list,
        context: Optional[Dict[str, Any]] = None,
    ):
        super().__init__(message, context)
        self.validation_errors = validation_errors


class DynamicSchemaError(Phase14Error):
    """动态 Schema 构建异常"""
    pass


class ModularPromptError(Phase14Error):
    """模块化 Prompt 构建异常"""
    pass
```

## Data Models

### 核心数据模型汇总

| 模型 | 位置 | 用途 |
|------|------|------|
| PrefilterResult | schemas/phase14.py | 规则预处理结果 |
| FeatureExtractionOutput | schemas/phase14.py | 特征提取输出 |
| FieldRAGResult | schemas/phase14.py | 字段检索结果 |
| FieldCandidate | schemas/phase14.py | 字段候选（含 category/category_detail） |
| TimeHint | schemas/phase14.py | 时间提示 |
| MatchedComputation | schemas/phase14.py | 匹配的计算种子 |
| ValidationResult | schemas/phase14.py | 验证结果 |
| CachedFeature | components/feature_cache.py | 缓存的特征（与 FeatureCache 同文件） |

### 配置参数

**文件位置**：`analytics_assistant/config/app.yaml`

```yaml
semantic_parser:
  phase14:
    # === 全局配置 ===
    enabled: true
    global_confidence_threshold: 0.7
    
    # === RulePrefilter 配置 ===
    low_confidence_threshold: 0.7
    rule_prefilter_max_time_ms: 50
    
    # === FeatureExtractor 配置 ===
    feature_extractor_timeout_ms: 500
    feature_extractor_model: "deepseek-v3"
    feature_extractor_max_input_tokens: 200
    
    # === FeatureCache 配置 ===
    feature_cache_ttl_seconds: 3600
    feature_cache_similarity_threshold: 0.95
    feature_cache_max_size: 1000
    
    # === FieldRetriever 配置 ===
    field_retriever_top_k: 5
    field_retriever_fallback_multiplier: 2  # 降级时返回 top_k * multiplier 个候选
    enable_category_filter: true
    
    # === DynamicSchemaBuilder 配置 ===
    max_schema_fields: 20
    
    # === OutputValidator 配置 ===
    fuzzy_match_threshold: 0.8
    auto_correct_case: true
    
    # === 降级配置 ===
    enable_degradation: true
    degradation_log_level: "warning"
```

### 性能约束说明

| 阶段 | 约束 | 计算依据 |
|------|------|----------|
| RulePrefilter | 50ms | 关键词匹配 O(n) + 正则匹配 O(n) + 时间解析 O(1)，n 为问题长度 |
| FeatureExtractor | 300ms | DeepSeek-V3 平均推理延迟 150-200ms + 网络开销 50-100ms |
| FieldRetriever | 100ms | 向量检索平均延迟 30-50ms × 并发检索（度量+维度+时间） |
| DynamicSchemaBuilder | 10ms | 纯内存操作，字段过滤和排序 |
| ModularPromptBuilder | 10ms | 字符串拼接和模板渲染 |
| OutputValidator | 20ms | 字段验证和模糊匹配 |
| **总延迟增加** | 200-300ms | 主 LLM 推理因 Token 减少 60% 而加速 300-400ms，总体持平或略快 |


## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system—essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

### Property 1: 阶段执行顺序不变性

*For any* 用户问题和数据源，11 个阶段的执行顺序应始终为：IntentRouter → QueryCache → RulePrefilter → FeatureCache → FeatureExtractor → FieldRetriever → DynamicSchemaBuilder → ModularPromptBuilder → SemanticUnderstanding → OutputValidator → FilterValueValidator → QueryAdapter。

**Validates: Requirements 1.1, 1.2, 1.3**

### Property 2: FieldRetriever 依赖 FeatureExtractor

*For any* 非缓存命中的查询，FieldRetriever 的执行开始时间应严格晚于 FeatureExtractor 的执行结束时间，且两者不存在时间重叠。

**Validates: Requirements 1.2, 1.3, 5.1**

### Property 3: 双 LLM 调用保证

*For any* 非缓存命中且非降级的查询，LLM 调用次数应恰好为 2 次（FeatureExtractor + SemanticUnderstanding）。

**Validates: Requirements 1.4**

### Property 4: RulePrefilter 无 LLM 调用

*For any* 用户问题，RulePrefilter 执行期间 LLM 调用次数应为 0。

**Validates: Requirements 2.1**

### Property 5: RulePrefilter 输入处理完整性

*For any* 包含时间表达式或计算关键词的用户问题，RulePrefilter 输出的 PrefilterResult 应包含对应的 time_hints 或 matched_computations。

**Validates: Requirements 2.2, 2.3, 2.4, 2.5**

### Property 6: 低置信度标记正确性

*For any* 规则匹配置信度低于阈值（0.7）的 PrefilterResult，low_confidence 字段应为 true。

**Validates: Requirements 2.6**

### Property 7: RulePrefilter 性能约束

*For any* 用户问题，RulePrefilter 执行时间应不超过 50ms。

**Validates: Requirements 2.7**

### Property 8: FeatureExtractor 超时降级

*For any* FeatureExtractor 执行超过 500ms 的情况，系统应返回 is_degraded=true 的 FeatureExtractionOutput，且使用 PrefilterResult 的数据。

**Validates: Requirements 3.6, 10.1**

### Property 9: FeatureExtractor Token 约束

*For any* FeatureExtractor 调用，输入 Token 数应不超过 200。

**Validates: Requirements 3.5**

### Property 10: FeatureCache 语义匹配

*For any* 两个语义相似度 > 0.95 的问题（相同数据源），第二个问题应命中 FeatureCache 并返回第一个问题的缓存特征。

**Validates: Requirements 4.2, 4.3**

### Property 11: FeatureCache 数据源隔离

*For any* 两个相同问题但不同数据源的查询，FeatureCache 应分别缓存，互不影响。

**Validates: Requirements 4.6**

### Property 12: FeatureCache TTL 过期

*For any* 缓存的特征，在 TTL 过期后应不再被返回。

**Validates: Requirements 4.4**

### Property 13: FieldRetriever 基于特征检索

*For any* FeatureExtractionOutput 包含 required_measures 的情况，FieldRetriever 返回的 measures 候选应与 required_measures 语义相关。

**Validates: Requirements 5.2**

### Property 14: FieldRAGResult 结构完整性

*For any* FieldRetriever 返回的 FieldRAGResult，每个 FieldCandidate 应包含 field_name、confidence、description 字段。

**Validates: Requirements 5.3, 5.4**

### Property 15: FieldRetriever Top-K 约束

*For any* FieldRetriever 返回的 FieldRAGResult，measures、dimensions、time_fields 列表长度应不超过配置的 top_k 值。

**Validates: Requirements 5.5**

### Property 16: FieldRetriever 置信度排序

*For any* FieldRetriever 返回的候选列表，应按 confidence 降序排列。

**Validates: Requirements 5.6**

### Property 17: DynamicSchemaBuilder 模块选择

*For any* 包含时间表达式的 FeatureExtractionOutput，DynamicSchemaBuilder 输出应包含 TIME 模块；包含计算需求时应包含 COMPUTATION 模块。

**Validates: Requirements 6.1, 6.4, 6.5, 6.6**

### Property 18: DynamicSchemaBuilder BASE 模块不变性

*For any* 输入，DynamicSchemaBuilder 输出应始终包含 BASE 模块。

**Validates: Requirements 6.3**

### Property 19: DynamicSchemaBuilder 字段数量约束

*For any* DynamicSchemaBuilder 输出，字段数量应不超过 MAX_FIELDS（默认 20）。

**Validates: Requirements 6.7**

### Property 20: ModularPromptBuilder 内容插入

*For any* 高置信度（>= 0.7）的 FeatureExtractionOutput，ModularPromptBuilder 输出的 Prompt 应包含 confirmed_computations 对应的计算种子和 confirmed_time_hints。

**Validates: Requirements 7.2, 7.3**

### Property 21: ModularPromptBuilder 低置信度回退

*For any* 置信度 < 0.7 的 FeatureExtractionOutput 或 PrefilterResult，ModularPromptBuilder 输出的 Prompt 应不包含计算种子。

**Validates: Requirements 7.5, 13.1**

### Property 22: ModularPromptBuilder 语言适配

*For any* 检测到的语言（zh/en/ja），ModularPromptBuilder 输出的 Prompt 应使用对应语言的指令。

**Validates: Requirements 7.4**

### Property 23: ModularPromptBuilder Token 优化

*For any* 相同查询，使用 ModularPromptBuilder 生成的 Prompt Token 数应比原始完整 Prompt 减少约 60%（允许 ±10% 误差）。

**Validates: Requirements 7.6**

### Property 24: OutputValidator 字段验证

*For any* SemanticOutput 中引用的字段，如果不在 FieldRAGResult 候选列表中，OutputValidator 应标记为 INVALID_FIELD 错误。

**Validates: Requirements 8.2**

### Property 25: OutputValidator 语法验证

*For any* SemanticOutput 中的计算表达式，如果括号不匹配，OutputValidator 应标记为 SYNTAX_ERROR 错误。

**Validates: Requirements 8.3**

### Property 26: OutputValidator 自动修正

*For any* 可自动修正的错误（如字段名大小写），OutputValidator 应返回 corrected_output 且 is_valid=true。

**Validates: Requirements 8.4**

### Property 27: OutputValidator 澄清请求

*For any* 不可自动修正的错误，OutputValidator 应返回 needs_clarification=true 和 clarification_message。

**Validates: Requirements 8.5**

### Property 28: 置信度范围有效性

*For any* PrefilterResult.match_confidence、FeatureExtractionOutput.confirmation_confidence、FieldCandidate.confidence，值应在 [0, 1] 范围内。

**Validates: Requirements 9.1, 9.2, 9.3**

### Property 29: 降级标记一致性

*For any* 降级场景（超时、缓存不可用、检索失败），系统应设置 is_degraded=true 或 degraded=true 标记。

**Validates: Requirements 10.1, 10.2, 10.3, 10.4**


## Error Handling

### 降级策略规范

**降级原则**：
1. **数据降级**：返回更保守的结果（如更多候选、更低置信度）
2. **逻辑降级**：跳过可选步骤，使用上一阶段的输出
3. **标记降级**：所有降级必须设置 `is_degraded=true`
4. **日志记录**：降级必须记录 WARNING 级别日志

**降级行为统一规范**：

| 阶段 | 触发条件 | 降级行为 | 输出变化 |
|------|----------|----------|----------|
| FeatureExtractor | 超时/异常 | 使用 PrefilterResult | `required_measures=[]`, `is_degraded=true` |
| FeatureCache | 不可用 | 跳过缓存 | 无输出变化，记录日志 |
| FieldRetriever | 检索失败 | 返回全量字段 | `top_k * fallback_multiplier` 个候选，置信度=0.5 |
| DynamicSchemaBuilder | 构建失败 | 使用完整 Schema | 包含所有字段，Token 优化失效 |
| ModularPromptBuilder | 构建失败 | 使用完整 Prompt | 不插入种子，Token 优化失效 |
| OutputValidator | 不可修正错误 | 返回澄清请求 | `needs_clarification=true` |

### 异常处理策略

| 异常类型 | 处理策略 | 降级行为 |
|----------|----------|----------|
| RulePrefilterError | 记录日志，使用空 PrefilterResult | 继续执行，不影响后续阶段 |
| FeatureExtractorTimeoutError | 记录日志，使用 PrefilterResult 降级 | is_degraded=true |
| FeatureExtractionError | 记录日志，使用 PrefilterResult 降级 | is_degraded=true |
| FieldRetrievalError | 记录日志，使用全量字段列表 | 返回更多候选字段 |
| OutputValidationError | 返回澄清请求 | needs_clarification=true |
| DynamicSchemaError | 记录日志，使用完整 Schema | Token 优化失效 |
| ModularPromptError | 记录日志，使用完整 Prompt | Token 优化失效 |

### 错误恢复流程

```
异常发生
    │
    ▼
┌─────────────────────────────────────────────────────────────────┐
│                    错误恢复决策                                   │
├─────────────────────────────────────────────────────────────────┤
│                                                                  │
│  1. FeatureExtractor 超时/异常:                                  │
│     └─ 降级使用 PrefilterResult                                  │
│        └─ 设置 is_degraded=true                                  │
│        └─ 继续执行 FieldRetriever（使用全量检索）                 │
│                                                                  │
│  2. FeatureCache 不可用:                                         │
│     └─ 跳过缓存，直接调用 FeatureExtractor                       │
│        └─ 记录警告日志                                           │
│                                                                  │
│  3. FieldRetriever 失败:                                         │
│     └─ 降级使用全量字段列表                                      │
│        └─ 增加候选数量（top_k * fallback_multiplier）            │
│        └─ 设置所有候选置信度为 0.5                               │
│                                                                  │
│  4. OutputValidator 发现不可修正错误:                            │
│     └─ 返回澄清请求                                              │
│        └─ 用户回复后重新开始流程                                 │
│                                                                  │
│  5. 连续降级超过阈值:                                            │
│     └─ 记录错误日志                                              │
│        └─ 触发告警                                               │
└─────────────────────────────────────────────────────────────────┘
```

### 日志记录规范

```python
# 降级日志格式
logger.warning(
    "Phase14 降级: %s",
    {
        "stage": "FeatureExtractor",
        "reason": "timeout",
        "timeout_ms": 500,
        "fallback": "PrefilterResult",
        "question_hash": "abc123",
    }
)

# 异常日志格式
logger.error(
    "Phase14 异常: %s",
    {
        "stage": "FieldRetriever",
        "error_type": "FieldRetrievalError",
        "message": "向量检索失败",
        "context": {"datasource_luid": "xxx"},
    }
)
```

## Testing Strategy

### 测试类型

| 测试类型 | 覆盖范围 | 工具 |
|----------|----------|------|
| 单元测试 | 各组件独立功能 | pytest |
| 属性测试 | 正确性属性验证 | hypothesis |
| 集成测试 | 组件间交互 | pytest + 真实 LLM |
| 性能测试 | 延迟和 Token 消耗 | pytest-benchmark |

### 单元测试重点

1. **RulePrefilter**
   - 关键词匹配逻辑
   - 时间提示生成
   - 计算种子匹配
   - 置信度计算

2. **FeatureExtractor**
   - 超时降级行为
   - 输出结构验证
   - Token 数量控制

3. **FeatureCache**
   - 精确匹配
   - 语义相似匹配
   - TTL 过期
   - 数据源隔离

4. **FieldRetriever**
   - Top-K 检索
   - 置信度排序
   - 降级模式

5. **DynamicSchemaBuilder**
   - 模块选择逻辑
   - 字段数量限制

6. **ModularPromptBuilder**
   - 计算种子插入
   - 低置信度回退
   - 语言适配

7. **OutputValidator**
   - 字段验证
   - 语法验证
   - 自动修正

### 属性测试配置

```python
from hypothesis import given, strategies as st, settings

# 最小 100 次迭代
@settings(max_examples=100)
@given(question=st.text(min_size=1, max_size=200))
def test_rule_prefilter_no_llm_call(question: str):
    """
    Feature: semantic-understanding-optimization
    Property 4: RulePrefilter 无 LLM 调用
    Validates: Requirements 2.1
    """
    # 测试实现
    pass
```

### 性能基准测试

```python
def test_token_reduction_benchmark():
    """
    验证 Token 减少约 60% 的目标
    
    Feature: semantic-understanding-optimization
    Property 23: ModularPromptBuilder Token 优化
    Validates: Requirements 7.6
    """
    # 比较优化前后的 Token 数
    original_tokens = count_tokens(original_prompt)
    optimized_tokens = count_tokens(optimized_prompt)
    
    reduction = (original_tokens - optimized_tokens) / original_tokens
    assert 0.5 <= reduction <= 0.7  # 50%-70% 减少
```

### 集成测试场景

1. **正常流程**：完整 11 阶段执行
2. **缓存命中**：QueryCache 和 FeatureCache 命中
3. **超时降级**：FeatureExtractor 超时
4. **低置信度**：规则匹配置信度低
5. **字段验证失败**：OutputValidator 发现错误
6. **多轮对话**：澄清后重新执行
