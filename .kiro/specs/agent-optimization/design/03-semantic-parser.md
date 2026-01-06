# SemanticParser 优化设计

## 1. 设计目标

将 SemanticParser 的 Step1 + Step2 合并为单次 LLM 调用，减少调用次数。

## 2. 当前架构分析

### 2.1 当前流程

```
用户问题
    ↓
Step1 (LLM #1)
├── 意图分类
├── 实体提取
└── 输出: Step1Output
    ↓
判断: 是否需要 Step2?
├── SIMPLE → 跳过 Step2
└── LOD/TABLE_CALC → 执行 Step2
    ↓
Step2 (LLM #2, 条件)
├── 计算推理
├── LOD 表达式生成
└── 输出: Step2Output
    ↓
Pipeline (工具)
├── MapFields
├── BuildQuery
└── ExecuteQuery
```

### 2.2 问题分析

1. **两次 LLM 调用**：Step1 + Step2 分离
2. **上下文重复**：Step2 需要重新传递上下文
3. **逻辑分散**：语义理解逻辑分散在两个组件

## 3. 优化方案：UnifiedSemanticParser

### 3.1 合并后流程

```
用户问题
    ↓
UnifiedSemanticParser (LLM #1)
├── 语义理解 (What/Where/How)
├── 意图分类
├── 计算推理 (如需要)
├── 自我验证
└── 输出: UnifiedSemanticOutput
    ↓
Pipeline (工具)
├── MapFields (RAG + Candidate Fields)
├── BuildQuery
└── ExecuteQuery
```

### 3.2 核心思路

使用增强的 System Prompt 指导 LLM 分阶段思考：

```xml
<thinking_steps>
1. 语义理解：提取 What（度量）、Where（维度）、How（筛选）
2. 意图分类：判断 DATA_QUERY / CLARIFICATION / GENERAL
3. 计算检测：检查是否需要复杂计算（排名/占比/累计/差异）
4. 计算推理：如需要，生成计算表达式
5. 自我验证：检查输出完整性和一致性
</thinking_steps>
```

## 4. Schema 设计

### 4.1 UnifiedSemanticOutput

```python
from enum import Enum
from typing import List, Optional
from pydantic import BaseModel, Field


class Intent(str, Enum):
    """意图类型"""
    DATA_QUERY = "DATA_QUERY"
    CLARIFICATION = "CLARIFICATION"
    GENERAL = "GENERAL"


class CalcType(str, Enum):
    """计算类型（精简为 5 种）"""
    RANK = "RANK"           # 排名
    PERCENT = "PERCENT"     # 占比
    RUNNING = "RUNNING"     # 累计
    DIFF = "DIFF"           # 差异（环比/同比）
    NONE = "NONE"           # 无复杂计算


class Dimension(BaseModel):
    """维度字段"""
    field: str = Field(description="字段名")
    granularity: Optional[str] = Field(default=None, description="日期粒度")


class Measure(BaseModel):
    """度量字段"""
    field: str = Field(description="字段名")
    aggregation: str = Field(default="SUM", description="聚合函数")


class Filter(BaseModel):
    """筛选条件"""
    field: str = Field(description="字段名")
    operator: str = Field(description="操作符")
    value: str | list = Field(description="筛选值")


class Computation(BaseModel):
    """复杂计算"""
    calc_type: CalcType = Field(description="计算类型")
    target: str = Field(description="目标度量字段")
    partition_by: List[str] = Field(default_factory=list, description="分区字段")
    expression: Optional[str] = Field(default=None, description="计算表达式")


class UnifiedSemanticOutput(BaseModel):
    """统一语义解析输出
    
    合并 Step1 + Step2 的输出，一次性完成语义理解和计算推理。
    """
    # 意图
    intent: Intent = Field(description="意图类型")
    
    # 语义结构
    dimensions: List[Dimension] = Field(default_factory=list, description="维度列表")
    measures: List[Measure] = Field(default_factory=list, description="度量列表")
    filters: List[Filter] = Field(default_factory=list, description="筛选条件")
    
    # 复杂计算（可选）
    computation: Optional[Computation] = Field(default=None, description="复杂计算")
    
    # 澄清问题（CLARIFICATION 意图时）
    clarification: Optional[str] = Field(default=None, description="澄清问题")
    
    # 推理过程（用于调试和可解释性）
    reasoning: str = Field(description="推理过程")
```

### 4.2 Schema 设计原则

遵循 `docs/appendix-prompt-schema-patterns.md` 的职责分离原则：

```python
# ✅ Schema description 只说"是什么"
class Dimension(BaseModel):
    field: str = Field(description="字段名")
    granularity: Optional[str] = Field(default=None, description="日期粒度")

# ❌ 不要在 Schema 中说"什么时候填"或"怎么判断"
# 这些逻辑应该在 Prompt 中
```

## 5. Prompt 设计

### 5.1 System Prompt 结构

```xml
<identity>
你是 Tableau 数据分析助手的语义解析器。
你的任务是将用户的自然语言问题转换为结构化的查询语义。
</identity>

<capabilities>
你可以：
- 理解用户的数据分析意图
- 提取维度、度量、筛选条件
- 识别复杂计算需求（排名、占比、累计、差异）
- 生成计算表达式

你不能：
- 执行实际的数据查询
- 访问数据源
- 进行数值计算
</capabilities>

<context>
当前时间：{current_time}

候选字段（从数据源检索）：
{candidate_fields}
</context>

<decision_rules>
## 意图分类规则
<intent_rules>
| 条件 | 意图 | 说明 |
|------|------|------|
| 有具体度量 + 有具体维度 | DATA_QUERY | 完整的数据查询 |
| 缺少度量或维度 | CLARIFICATION | 需要澄清 |
| 询问字段/元数据 | GENERAL | 一般性问题 |
</intent_rules>

## 复杂计算检测规则
<calc_rules>
| 关键词 | calc_type | 说明 |
|-------|-----------|------|
| 排名、排行、第几名、Rank | RANK | 添加排名列 |
| 占比、百分比、份额、% of | PERCENT | 计算占总量的比例 |
| 累计、YTD、累积、Running | RUNNING | 累计求和 |
| 环比、同比、增长率、MoM、YoY | DIFF | 与上期比较 |
| 无以上关键词 | NONE | 简单聚合查询 |

**注意：**
- "前10名"、"Top N" 是筛选，不是排名计算
- 一个问题只能有一种复杂计算类型
</calc_rules>

## 日期处理规则
<date_rules>
IF 用户说"今年" THEN 转换为 {current_year}-01-01 到 今天
IF 用户说"去年" THEN 转换为 {last_year}-01-01 到 {last_year}-12-31
IF 用户说"上个月" THEN 转换为 上月第一天 到 上月最后一天
IF 用户说"最近7天" THEN 转换为 7天前 到 今天
</date_rules>
</decision_rules>

<thinking_steps>
在生成输出前，你必须按以下步骤思考：

1. **语义理解**：提取用户问题中的 What（度量）、Where（维度）、How（筛选）
2. **意图分类**：根据规则判断意图类型
3. **计算检测**：检查是否包含复杂计算关键词
4. **计算推理**：如需要复杂计算，确定计算类型和表达式
5. **自我验证**：检查输出的完整性和一致性
</thinking_steps>

<examples>
## 示例 1：简单查询

问题：各省份的销售额

<analysis>
- 语义理解：度量=销售额，维度=省份，筛选=无
- 意图分类：DATA_QUERY（有具体度量和维度）
- 计算检测：无复杂计算关键词
- 计算推理：不需要
- 自我验证：完整
</analysis>

输出：
```json
{
  "intent": "DATA_QUERY",
  "dimensions": [{"field": "省份"}],
  "measures": [{"field": "销售额", "aggregation": "SUM"}],
  "filters": [],
  "computation": null,
  "reasoning": "用户想查看各省份的销售额汇总，这是一个简单的分组聚合查询。"
}
```

## 示例 2：带排名的查询

问题：各省份销售额排名

<analysis>
- 语义理解：度量=销售额，维度=省份，筛选=无
- 意图分类：DATA_QUERY
- 计算检测：包含"排名"关键词
- 计算推理：需要 RANK 计算
- 自我验证：完整
</analysis>

输出：
```json
{
  "intent": "DATA_QUERY",
  "dimensions": [{"field": "省份"}],
  "measures": [{"field": "销售额", "aggregation": "SUM"}],
  "filters": [],
  "computation": {
    "calc_type": "RANK",
    "target": "销售额",
    "partition_by": [],
    "expression": "RANK(SUM([销售额]))"
  },
  "reasoning": "用户想查看各省份销售额的排名，需要添加排名计算。"
}
```

## 反例：Top N 不是排名

问题：销售额前10的省份

<analysis>
- 这是 Top N 筛选，不是排名计算
- 用户想要的是筛选后的子集，不是添加排名列
</analysis>

正确输出：
```json
{
  "filters": [{"field": "销售额", "operator": "top", "value": 10}],
  "computation": null
}
```

错误输出（不要这样做）：
```json
{
  "computation": {"calc_type": "RANK", ...}
}
```

原因："前10名"表示筛选条件，不是要添加排名列
</examples>

<self_correction>
## 自我检查规则

在输出前，检查以下内容：

1. **意图一致性**：intent 与 dimensions/measures 是否匹配
2. **字段存在性**：所有字段是否在候选字段中
3. **计算合理性**：computation 是否与问题中的关键词匹配
4. **筛选完整性**：日期筛选是否正确转换
</self_correction>
```

## 6. 组件实现

### 6.1 UnifiedSemanticComponent

```python
class UnifiedSemanticComponent:
    """统一语义解析组件
    
    合并 Step1 + Step2，一次 LLM 调用完成语义理解和计算推理。
    """
    
    def __init__(self, llm: BaseChatModel):
        self.llm = llm.with_structured_output(UnifiedSemanticOutput)
        self.prompt_template = self._build_prompt_template()
    
    async def parse(
        self,
        question: str,
        candidate_fields: List[CandidateField],
        history: List[BaseMessage] = None,
    ) -> UnifiedSemanticOutput:
        """解析用户问题
        
        Args:
            question: 用户问题
            candidate_fields: RAG 检索的候选字段
            history: 对话历史
            
        Returns:
            UnifiedSemanticOutput
        """
        # 构建 Prompt
        prompt = self.prompt_template.format(
            current_time=datetime.now().isoformat(),
            candidate_fields=self._format_candidates(candidate_fields),
            question=question,
        )
        
        # 构建消息
        messages = [SystemMessage(content=prompt)]
        if history:
            messages.extend(history)
        messages.append(HumanMessage(content=question))
        
        # 调用 LLM
        result = await self.llm.ainvoke(messages)
        
        return result
    
    def _format_candidates(self, candidates: List[CandidateField]) -> str:
        """格式化候选字段"""
        lines = []
        for c in candidates:
            line = f"- {c.name} ({c.role}, {c.data_type})"
            if c.sample_values:
                line += f" 样例: {', '.join(c.sample_values[:3])}"
            lines.append(line)
        return "\n".join(lines)
```

### 6.2 集成到 Subgraph

```python
class SemanticParserSubgraph:
    """SemanticParser Subgraph
    
    节点：
    1. unified_semantic: 统一语义解析
    2. pipeline: 查询执行管道
    3. observer: 错误检查
    """
    
    def build(self) -> StateGraph:
        graph = StateGraph(SemanticParserState)
        
        # 添加节点
        graph.add_node("unified_semantic", self.unified_semantic_node)
        graph.add_node("pipeline", self.pipeline_node)
        graph.add_node("observer", self.observer_node)
        
        # 添加边
        graph.add_edge(START, "unified_semantic")
        graph.add_edge("unified_semantic", "pipeline")
        graph.add_conditional_edges(
            "pipeline",
            self.should_retry,
            {
                "retry": "unified_semantic",
                "continue": END,
            }
        )
        
        return graph.compile()
```

## 7. 性能对比

### 7.1 LLM 调用次数

| 场景 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 简单查询 | 1 (Step1) | 1 | 0% |
| 复杂查询 | 2 (Step1 + Step2) | 1 | 50% |

### 7.2 Token 消耗

| 组件 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 完整数据模型 | 3000+ | 0 | 100% |
| 候选字段 | 0 | 500 | - |
| System Prompt | 1000 | 1500 | -50% |
| **总计** | **4000+** | **2000** | **50%** |

## 8. 迁移策略

### 8.1 Phase 1: Schema 和 Prompt

1. 创建 `UnifiedSemanticOutput` Schema
2. 创建 `UnifiedSemanticPrompt`
3. 单元测试验证

### 8.2 Phase 2: 组件实现

1. 实现 `UnifiedSemanticComponent`
2. 集成 RAG 候选字段
3. 集成测试

### 8.3 Phase 3: Subgraph 更新

1. 更新 `SemanticParserSubgraph`
2. 移除 Step1/Step2 节点
3. 端到端测试

### 8.4 Phase 4: 清理

1. 删除旧的 Step1/Step2 代码
2. 更新文档
