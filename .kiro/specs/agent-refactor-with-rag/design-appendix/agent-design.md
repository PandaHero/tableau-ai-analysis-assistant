# Agent 节点设计

## 概述

本文档描述 Agent 节点（LLM 节点）的详细设计，包括 Understanding（含原 Boost 功能）、Insight、Replanner 的 Prompt 模板和节点逻辑。

**架构变更说明**：Boost Agent 已移除，其功能（元数据获取、问题分类）合并到 Understanding Agent。

**设计规范**：本文档遵循 `prompt-and-schema-design.md` 中定义的设计规范，基于 `PROMPT_AND_MODEL_GUIDE.md` 中的前沿研究。

**核心理念**：
- **Prompt 教 LLM 如何思考**：提供领域知识和推理步骤
- **Schema 告诉 LLM 输出什么**：提供字段填写规则和决策规则
- **`<decision_rule>` 是桥梁**：将 Prompt 中的抽象思考转化为 Schema 中的具体填写动作

**注意**：Insight Agent 的设计在 [insight-design.md](./insight-design.md) 中单独描述。

对应项目结构：`src/agents/`

---

## Agent/Node 工具分配表

| Agent/Node | 类型 | 可用工具/组件 | 工具来源 | 输入 | 输出 |
|------------|------|--------------|---------|------|------|
| Understanding Agent | LLM | get_metadata, get_schema_module, parse_date, detect_date_format | 业务工具 | question | SemanticQuery |
| FieldMapper Node | RAG + LLM 混合 | SemanticMapper | 组件 | SemanticQuery | MappedQuery |
| QueryBuilder Node | 纯代码 | ImplementationResolver + ExpressionGenerator | 组件 | MappedQuery | VizQLQuery |
| Execute Node | 纯代码 | VizQL API 调用 | 代码 | VizQLQuery | QueryResult |
| Insight Agent | LLM | AnalysisCoordinator | 组件 | QueryResult | accumulated_insights |
| Replanner Agent | LLM | write_todos | TodoListMiddleware | insights, QueryResult | ReplanDecision |

**说明**：
- Boost Agent 已移除，功能合并到 Understanding Agent（get_metadata 工具 + 问题分类）
- FieldMapper 从 QueryBuilder 内部组件提升为独立节点（RAG + LLM 混合）
- QueryBuilder 现在是纯代码节点，只包含 ImplementationResolver + ExpressionGenerator

---

## 1. Understanding Agent（含原 Boost 功能）

### 职责

- **问题分类**：判断是否为分析类问题（is_analysis_question）
- **元数据获取**：调用 get_metadata 工具获取字段信息（原 Boost 功能）
- **语义理解**：理解用户问题的语义
- **输出 SemanticQuery**：纯语义，无 VizQL 概念
- 使用动态 Schema 模块选择，减少 token 消耗

### Prompt 模板（4 段式结构）

**核心设计**：Prompt 中的思考步骤与 Schema 中的 `<decision_rule>` 对应。

```python
# tableau_assistant/src/agents/understanding/prompt.py

from tableau_assistant.src.prompts.base import VizQLPrompt
from tableau_assistant.src.models.semantic.query import SemanticQuery
from typing import Type
from pydantic import BaseModel

class UnderstandingPrompt(VizQLPrompt):
    """Understanding Agent 的 Prompt 模板（含原 Boost 功能）
    
    设计原则：
    - Prompt 教 LLM 如何思考（领域知识 + 推理步骤）
    - Schema 告诉 LLM 输出什么（字段填写规则）
    - 思考步骤与 Schema 中的 <decision_rule> 对应
    
    架构变更：
    - Boost Agent 已移除，功能合并到此 Agent
    - 新增：问题分类（is_analysis_question）
    - 新增：元数据获取（get_metadata 工具）
    """
    
    def get_role(self) -> str:
        return """Data analysis expert who classifies questions and extracts structured query intent.

Expertise:
- Question classification (analysis vs non-analysis)
- Semantic understanding of business terminology
- Dimension vs Measure classification
- Time expression parsing
- Analysis type detection (cumulative, ranking, percentage, etc.)"""
    
    def get_task(self) -> str:
        return """Classify question type, get metadata, and output SemanticQuery (pure semantic, no VizQL concepts).

Process: Get metadata → Classify question → Extract entities → Classify roles → Detect analysis type → Output structured JSON"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 0: Get metadata and classify question (原 Boost 功能)
- Use get_metadata tool to get available fields
- Determine if this is an analysis question (is_analysis_question)
- Analysis questions: queries about data, trends, comparisons, aggregations
- Non-analysis questions: greetings, help requests, system questions
- If not analysis question, return early with is_analysis_question=False

Step 1: Understand user intent
- What does the user want to know?
- Is it a simple query or complex analysis?

Step 2: Extract business entities
- Identify all business terms (e.g., "销售额", "省份", "日期")
- Note: Use exact terms from question, not technical field names

Step 3: Classify entity roles
- Dimension: Categorical field for grouping ("各XX", "按XX", "每个XX")
- Measure: Numeric field for aggregation ("销售额", "利润", "数量")
- Time dimension: Date/time field with granularity ("按年", "按月", "按日")

Step 4: Detect time filters
- Absolute: "2024年", "1月", "Q1"
- Relative: "最近3个月", "上周", "去年同期"
- Use parse_date tool to resolve relative dates

Step 5: Detect analysis type (if any)
- Cumulative: "累计", "累积", "running"
- Ranking: "排名", "排序", "TOP", "前N名"
- Percentage: "占比", "百分比", "%"
- Period compare: "同比", "环比", "对比"
- Moving: "移动平均", "滑动"
- Note: If no analysis keywords, skip analyses field

Step 6: Determine computation scope (for multi-dimension analysis)
- Per group: "各XX", "每个XX" → Calculate independently per group
- Across all: "总", "全部", "整体" → Calculate across all data
- Note: ONLY applicable when dimensions.length > 1
- Note: If single dimension, DO NOT fill computation_scope"""
    
    def get_constraints(self) -> str:
        return """MUST:
- Use business terms from question (not technical field names)
- Fill fields in order specified by <fill_order> in Schema
- Follow <decision_rule> for each field
- Use parse_date tool for relative time expressions

MUST NOT:
- Use VizQL concepts (addressing, partitioning, RUNNING_SUM, etc.)
- Invent fields not mentioned in question
- Set computation_scope for single dimension queries
- Use technical field names like "Sales" instead of "销售额" """
    
    def get_user_template(self) -> str:
        return """Analyze this question and output SemanticQuery:

Question: {question}
Available fields: {metadata_summary}
Current date: {current_date}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return SemanticQuery
```

### Prompt 与 Schema 的对应关系

**关键设计**：Prompt 中的每个思考步骤对应 Schema 中的 `<decision_rule>`。

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Prompt 思考步骤 ↔ Schema 决策规则                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Prompt Step 2 (Extract business entities)                                   │
│      ↓ 对应                                                                  │
│  Schema measures.name 的 <decision_rule>:                                    │
│  "Prompt Step 2 (提取业务实体) → 填写 name"                                  │
│                                                                              │
│  Prompt Step 3 (Classify entity roles)                                       │
│      ↓ 对应                                                                  │
│  Schema dimensions.is_time 的 <decision_rule>:                               │
│  "Prompt Step 3 (分类实体角色) → 填写 is_time"                               │
│                                                                              │
│  Prompt Step 5 (Detect analysis type)                                        │
│      ↓ 对应                                                                  │
│  Schema analyses.type 的 <decision_rule>:                                    │
│  "Prompt Step 5 (检测分析类型) → 填写 type"                                  │
│                                                                              │
│  Prompt Step 6 (Determine computation scope)                                 │
│      ↓ 对应                                                                  │
│  Schema analyses.computation_scope 的 <decision_rule>:                       │
│  "Prompt Step 6 (确定计算范围) → 填写 computation_scope"                     │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 节点实现

```python
# tableau_assistant/src/agents/understanding/node.py

async def understanding_node(state: VizQLState, runtime) -> Dict[str, Any]:
    """
    Understanding Agent 节点（含原 Boost 功能）
    
    流程：
    1. 调用 get_metadata 获取元数据（原 Boost 功能）
    2. 判断是否为分析类问题（is_analysis_question）
    3. 如果不是分析类问题，直接返回
    4. 构建 Prompt（包含思考步骤）
    5. LLM 分析问题，调用工具获取需要的信息
    6. LLM 根据 Schema 的 <decision_rule> 生成 SemanticQuery
    """
    llm = get_llm_with_tools([get_metadata, get_schema_module, parse_date, detect_date_format])
    
    current_question = state.get("question", "")
    metadata = state.get("metadata")
    
    prompt = UnderstandingPrompt()
    messages = prompt.format_messages(
        question=current_question,
        metadata_summary=metadata.get_summary() if metadata else "",
        current_date=datetime.now().strftime("%Y-%m-%d")
    )
    
    # 调用 LLM（自动处理 tool calls）
    response = await process_tool_calls(llm, messages, tool_map)
    
    # 解析输出
    # LLM 输出包含两部分：is_analysis_question（路由决策）和 semantic_query（语义查询）
    output = json.loads(response.content)
    is_analysis_question = output.get("is_analysis_question", True)
    
    # 如果不是分析类问题，直接返回（semantic_query 为 None）
    if not is_analysis_question:
        return {
            "semantic_query": None,
            "is_analysis_question": False,
            "understanding_complete": True,
            "current_question": current_question,
        }
    
    # 解析 SemanticQuery（Pydantic 验证）
    semantic_query = SemanticQuery.model_validate(output.get("semantic_query", {}))
    
    return {
        "semantic_query": semantic_query,
        "is_analysis_question": True,
        "understanding_complete": True,
        "current_question": current_question,
    }
```

### 动态 Schema 模块选择

Understanding Agent 使用动态 Schema 模块选择工具，LLM 按需获取 Intent 模型的填写规则：

```python
# 可用模块
SCHEMA_MODULES = {
    "measures": "度量字段（销售额、利润等数值概念）",
    "dimensions": "维度字段（分组、分类概念）",
    "date_fields": "日期分组字段（按年、按月）",
    "date_filters": "日期筛选条件（2024年、最近3个月）",
    "filters": "非日期筛选条件（华东地区、销售额>1000）",
    "topn": "TopN 筛选（前10名、TOP5）",
    "table_calcs": "表计算（累计、排名、占比）",
}
```

**Token 节省效果**：平均节省 40-60%

---

## 2. Replanner Agent

### 职责

- **智能评估**分析完整性（completeness_score）
- **识别缺失方面**（missing_aspects）
- **生成新问题**（new_questions）
- **智能路由**决定下一步（current_stage）

### 完成度评估标准

| 评分 | 标准 | 决策 |
|------|------|------|
| 0.9-1.0 | 完全回答问题，洞察深入 | 无需重规划 |
| 0.7-0.9 | 基本回答问题，可以更深入 | 考虑重规划 |
| 0.5-0.7 | 部分回答问题，缺少关键信息 | 建议重规划 |
| <0.5 | 未能回答问题 | 必须重规划 |

### Prompt 模板（4 段式结构）

```python
# tableau_assistant/src/agents/replanner/prompt.py

from tableau_assistant.src.prompts.base import VizQLPrompt
from tableau_assistant.src.models.replanner import ReplanDecision
from typing import Type
from pydantic import BaseModel

class ReplannerPrompt(VizQLPrompt):
    """Replanner Agent 的 Prompt 模板
    
    设计原则：
    - Prompt 教 LLM 如何评估分析完整性
    - Schema 告诉 LLM 输出什么（ReplanDecision 结构）
    - 思考步骤与 Schema 中的 <decision_rule> 对应
    """
    
    def get_role(self) -> str:
        return """Analysis planning expert who evaluates analysis completeness and decides on replanning.

Expertise:
- Evaluating question coverage and data completeness
- Identifying missing aspects and anomalies
- Generating targeted follow-up questions
- Making intelligent routing decisions"""
    
    def get_task(self) -> str:
        return """Evaluate current analysis completeness and decide whether to replan.

Process: Evaluate completeness → Identify missing aspects → Generate new questions → Make routing decision"""
    
    def get_specific_domain_knowledge(self) -> str:
        return """**Think step by step:**

Step 1: Evaluate completeness
- Question coverage: Does the analysis answer the original question?
- Data completeness: Is all relevant data included?
- Insight depth: Are the insights meaningful and actionable?
- Anomaly handling: Are anomalies explained?

Step 2: Score completeness (0-1)
- 0.9-1.0: Fully answered, deep insights → No replan needed
- 0.7-0.9: Mostly answered, could go deeper → Consider replan
- 0.5-0.7: Partially answered, missing key info → Suggest replan
- <0.5: Not answered → Must replan

Step 3: Identify missing aspects (if score < 0.9)
- What information is missing?
- What anomalies need explanation?
- What follow-up analysis would be valuable?

Step 4: Generate new questions (if should_replan)
- Targeted: Address specific missing aspects
- Specific: Clear and unambiguous
- Executable: Can be answered by a query
- Incremental: Build on existing results

Step 5: Make routing decision
- should_replan=true → Return to Understanding with new question
- should_replan=false → End analysis"""
    
    def get_constraints(self) -> str:
        return """MUST:
- Evaluate all four dimensions (coverage, completeness, depth, anomalies)
- Provide specific reasons for the decision
- Generate actionable new questions if replanning

MUST NOT:
- Replan if completeness_score >= 0.9
- Replan if max_replan_rounds reached
- Generate vague or non-executable questions"""
    
    def get_user_template(self) -> str:
        return """Evaluate this analysis and decide on replanning:

Original Question: {original_question}
Current Insights: {insights}
Query Result Summary: {result_summary}
Replan Count: {replan_count} / {max_replan_rounds}"""
    
    def get_output_model(self) -> Type[BaseModel]:
        return ReplanDecision
```

### Prompt 与 Schema 的对应关系

```
┌─────────────────────────────────────────────────────────────────────────────┐
│                    Prompt 思考步骤 ↔ Schema 决策规则                         │
├─────────────────────────────────────────────────────────────────────────────┤
│                                                                              │
│  Prompt Step 2 (Score completeness)                                          │
│      ↓ 对应                                                                  │
│  Schema completeness_score 的 <decision_rule>:                               │
│  "Prompt Step 2 (评分完成度) → 填写 completeness_score"                      │
│                                                                              │
│  Prompt Step 3 (Identify missing aspects)                                    │
│      ↓ 对应                                                                  │
│  Schema missing_aspects 的 <decision_rule>:                                  │
│  "Prompt Step 3 (识别缺失方面) → 填写 missing_aspects"                       │
│                                                                              │
│  Prompt Step 4 (Generate new questions)                                      │
│      ↓ 对应                                                                  │
│  Schema new_questions 的 <decision_rule>:                                    │
│  "Prompt Step 4 (生成新问题) → 填写 new_questions"                           │
│                                                                              │
│  Prompt Step 5 (Make routing decision)                                       │
│      ↓ 对应                                                                  │
│  Schema should_replan 的 <decision_rule>:                                    │
│  "Prompt Step 5 (路由决策) → 填写 should_replan"                             │
│                                                                              │
└─────────────────────────────────────────────────────────────────────────────┘
```

### 节点实现

```python
# tableau_assistant/src/agents/replanner/node.py

async def replanner_node(state: VizQLState, runtime) -> Dict[str, Any]:
    """
    Replanner Agent 节点（智能重规划）
    
    流程：
    1. 评估当前分析完整性（completeness_score）
    2. 识别缺失方面（missing_aspects）
    3. 生成新问题（new_questions）
    4. 决定下一步（current_stage）
    """
    # 获取洞察结果
    insights = state.get("insights", [])
    if not insights:
        return {
            "replan_decision": ReplanDecision(
                should_replan=False,
                reason="没有洞察结果，无法评估完成度",
                completeness_score=0.0
            ).model_dump(),
            "current_stage": "summarize"
        }
    
    # 检查是否达到最大重规划次数
    replan_count = state.get("replan_count", 0)
    max_replan_rounds = runtime.context.max_replan_rounds
    
    if replan_count >= max_replan_rounds:
        return {
            "replan_decision": ReplanDecision(
                should_replan=False,
                reason=f"已达到最大重规划次数（{max_replan_rounds}）",
                completeness_score=1.0
            ).model_dump(),
            "current_stage": "summarize"
        }
    
    # LLM 评估
    llm = get_llm_with_tools([write_todos])
    
    prompt = ReplannerPrompt()
    messages = prompt.format_messages(
        original_question=state.get("question", ""),
        insights=_format_insights(insights),
        result_summary=_format_result_summary(state.get("query_result")),
        replan_count=replan_count,
        max_replan_rounds=max_replan_rounds
    )
    
    response = await process_tool_calls(llm, messages, tool_map)
    
    # 解析输出（Pydantic 验证）
    decision = ReplanDecision.model_validate_json(response.content)
    
    # 路由决策
    if decision.should_replan:
        new_questions = decision.new_questions or []
        return {
            "replan_decision": decision.model_dump(),
            # 使用新问题作为当前问题，回到 Understanding 重新理解
            "question": new_questions[0] if new_questions else state.get("question"),
            "replan_count": replan_count + 1,
            "replan_history": [{
                "round": replan_count + 1,
                "reason": decision.reason,
                "new_questions": new_questions,
                "completeness_score": decision.completeness_score
            }],
        }
    else:
        return {
            "replan_decision": decision.model_dump(),
        }
```

### 智能路由决策

```
Replanner Agent (LLM)
    │
    ├─ 评估完成度 (completeness_score)
    │   ├─ 0.9-1.0: 完全回答 → END
    │   ├─ 0.7-0.9: 基本回答 → 考虑重规划
    │   ├─ 0.5-0.7: 部分回答 → 建议重规划
    │   └─ <0.5: 未能回答 → 必须重规划
    │
    ├─ 识别缺失方面 (missing_aspects)
    │   └─ 例: ["利润率分析", "华东地区异常原因"]
    │
    ├─ 生成新问题 (new_questions)
    │   └─ 例: ["各地区的利润率是多少？"]
    │
    └─ 路由决策
        ├─ should_replan=True → Understanding（重新理解新问题）
        └─ should_replan=False → END（结束分析）

注意：Planning 节点已移除，重规划时直接回到 Understanding 节点重新理解新问题。
```

### HumanInTheLoopMiddleware 协作

```
Replanner Agent
    │
    ▼ 生成 ReplanDecision（包含新问题）
    │
    ▼ 调用 write_todos 工具（由 TodoListMiddleware 提供）
    │
    ▼ HumanInTheLoopMiddleware 自动暂停（如果配置了 interrupt_on）
    │
    ▼ 用户审查问题（选择/修改/拒绝）
    │
    ▼ 继续执行或结束
```

---

## 附录：设计规范检查清单

### Prompt 模板检查

- [ ] 是否使用 4 段式结构（Role、Task、Domain Knowledge、Constraints）？
- [ ] 是否提供了清晰的思考步骤（Step 1, 2, 3...）？
- [ ] 是否避免了具体字段名（字段名应在 Schema 中）？
- [ ] 思考步骤是否与 Schema 中的 `<decision_rule>` 对应？

### Prompt 与 Schema 协同检查

- [ ] Prompt 中的每个思考步骤是否有对应的 Schema `<decision_rule>`？
- [ ] Schema 中的 `<decision_rule>` 是否引用了 Prompt 中的步骤？
- [ ] 是否遵循了"Prompt 教思考，Schema 教填写"的原则？

---

**文档版本**: v2.0
**最后更新**: 2025-12-05
**参考文档**: 
- `prompt-and-schema-design.md`
- `tableau_assistant/docs/PROMPT_AND_MODEL_GUIDE.md`
