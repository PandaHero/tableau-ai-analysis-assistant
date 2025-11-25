# 子代理设计详解

本文档详细描述 DeepAgents 重构中的 5 个子代理的设计。

## 目录

1. [Boost Agent](#1-boost-agent) - 问题优化
2. [Understanding Agent](#2-understanding-agent) - 问题理解
3. [Planning Agent](#3-planning-agent) - 查询规划
4. [Insight Agent](#4-insight-agent) - 洞察分析
5. [Replanner Agent](#5-replanner-agent) - 重规划决策

---

## 1. Boost Agent

### 职责

优化用户问题，补充缺失信息，使问题更加精确和可执行。

### 配置

```python
boost_agent = {
    "name": "boost-agent",
    "description": "优化用户问题，补充时间范围、维度、度量等缺失信息",
    "model": "gpt-4o-mini",  # 轻量级模型
    "tools": ["get_metadata"],
    "max_tokens": 1000,
    "temperature": 0.1,
    "timeout": 30
}
```

### 输入输出

**输入**（~2,000 tokens）：
```python
{
    "original_question": "销售情况",
    "metadata": {...},  # 数据源元数据
    "conversation_history": [...]  # 可选
}
```

**输出**：
```python
{
    "boosted_question": "2024年各地区的销售额和订单量分别是多少？",
    "improvements": [
        "补充了时间范围：2024年",
        "明确了维度：地区",
        "明确了度量：销售额、订单量"
    ],
    "suggestions": [
        "2024年销售额TOP10的门店是哪些？",
        "2024年各产品类别的销售额占比",
        "2024年的销售额趋势（按月统计）"
    ],
    "confidence": 0.85,
    "reasoning": "原问题过于宽泛，补充了时间、维度和度量"
}
```

### Prompt 设计

详见 [prompts.py](../../../src/deepagents/prompts.py#boost-agent)

### 使用场景

- 用户问题模糊："销售情况"
- 缺少时间范围："各地区销售额"
- 缺少对比维度："利润分析"

---

## 2. Understanding Agent

### 职责

理解用户问题意图，**拆分复杂问题为子问题**，识别问题类型，提取关键实体，评估复杂度。

### 核心功能

1. **问题拆分** - 将复杂问题拆分为多个可执行的子问题
2. **问题分类** - 识别问题类型（对比、趋势、排名等）
3. **实体提取** - 提取维度、度量、时间范围等关键实体
4. **复杂度评估** - 评估问题复杂度（简单/中等/复杂）
5. **隐含需求识别** - 识别用户未明确表达的需求

### 配置

```python
understanding_agent = {
    "name": "understanding-agent",
    "description": "理解用户问题意图，识别查询类型和复杂度",
    "model": "claude-3-5-sonnet-20241022",
    "tools": [],  # 不需要工具
    "max_tokens": 2000,
    "temperature": 0.0,
    "timeout": 60
}
```

### 输入输出

**输入**（~1,550 tokens）：
```python
{
    "question": "2024年各地区的销售额和利润率，按销售额降序"
}
```

**输出**：
```python
{
    "question_type": ["comparison", "ranking"],
    "complexity": "simple",
    "mentioned_dimensions": ["地区"],
    "mentioned_measures": ["销售额", "利润率"],
    "time_range": {
        "type": "absolute",
        "year": 2024
    },
    "sort_requirement": "按销售额降序",
    "topn_requirement": null,
    "aggregation_intent": "sum",
    "implicit_requirements": [
        "需要排序",
        "降序排列"
    ],
    "confidence": 0.92,
    "reasoning": "用户明确提到了地区维度和两个度量，问题类型是对比和排名"
}
```

### 问题类型

- **comparison** - 对比分析
- **trend** - 趋势分析
- **ranking** - 排名分析
- **distribution** - 分布分析
- **correlation** - 相关性分析
- **root_cause** - 根因分析

### 复杂度评估

- **simple** - 单一维度+单一度量，无复杂过滤
- **medium** - 多维度或多度量，有时间范围
- **complex** - 多轮分析、根因挖掘、复杂计算

---

## 3. Planning Agent

### 职责

根据问题理解生成查询计划，**执行语义字段映射（RAG+LLM混合模型）**，生成完整的查询规格。

### 核心功能

1. **语义字段映射** - 使用RAG+LLM将业务术语映射到技术字段
   - RAG阶段：向量检索快速找到候选字段
   - LLM阶段：语义理解选择最佳匹配
2. **查询规划** - 生成可执行的VizQL查询计划
3. **依赖分析** - 分析查询间的依赖关系
4. **执行策略选择** - 选择最优的执行策略（并行/顺序/流水线）

### 配置

```python
planning_agent = {
    "name": "planning-agent",
    "description": "生成查询计划，执行语义字段映射（RAG+LLM）",
    "model": "claude-3-5-sonnet-20241022",
    "tools": [
        "get_metadata",           # 获取元数据
        "semantic_map_fields",    # 语义字段映射（RAG+LLM）
        "parse_date",             # 日期解析
        "build_vizql_query"       # 查询构建
    ],
    "max_tokens": 3000,
    "temperature": 0.0,
    "timeout": 90
}
```

### 输入输出

**输入**（~8,250 tokens）：
```python
{
    "understanding": {...},  # 问题理解结果
    "metadata": {...},  # 完整元数据
    "previous_results": [...]  # 可选，重规划时使用
}
```

**输出**：
```python
{
    "queries": [
        {
            "query_id": "q1",
            "question_text": "2024年各地区的销售额和利润率",
            "fields": [
                {
                    "fieldCaption": "地区",
                    "dataType": "string",
                    "role": "dimension"
                },
                {
                    "fieldCaption": "销售额",
                    "dataType": "real",
                    "role": "measure",
                    "function": "SUM",
                    "sortDirection": "DESC",
                    "sortPriority": 1
                },
                {
                    "fieldCaption": "利润率",
                    "dataType": "real",
                    "role": "measure",
                    "function": "AVG"
                }
            ],
            "filters": [
                {
                    "fieldCaption": "订单日期",
                    "filterType": "QUANTITATIVE_DATE",
                    "year": 2024
                }
            ],
            "dependencies": [],
            "cache_key": "region_sales_2024"
        }
    ],
    "execution_strategy": "sequential",
    "needs_replan": false,
    "reasoning": "简单问题，单个查询即可完成"
}
```

### 执行策略

- **sequential** - 顺序执行（有依赖）
- **parallel** - 并行执行（无依赖）
- **pipeline** - 流水线执行（部分依赖）
- **adaptive** - 自适应执行（运行时决定）

---

## 4. Insight Agent

### 职责

分析查询结果，使用渐进式分析处理大数据集，生成业务洞察。

### 配置

```python
insight_agent = {
    "name": "insight-agent",
    "description": "分析查询结果，生成洞察",
    "model": "claude-3-5-sonnet-20241022",
    "tools": [
        "read_file",           # 读取大文件
        "detect_statistics"    # 统计检测
    ],
    "max_tokens": 4000,
    "temperature": 0.2,
    "timeout": 120
}
```

### 渐进式分析流程

```
IF 数据量 > 100行:
  1. Coordinator 决定使用渐进式分析
  2. DataProfiler 生成数据画像
  3. SemanticChunker 智能分块
  4. ChunkAnalyzer 逐块分析
  5. InsightAccumulator 累积洞察
  6. AI 判断是否早停
ELSE:
  直接分析全部数据
```

### 输入输出

**输入**（~4,050 tokens）：
```python
{
    "query_result": {...},  # 查询结果或文件路径
    "question": "2024年各地区的销售额",
    "statistics": {...}  # 统计检测结果
}
```

**输出**：
```python
{
    "key_findings": [
        "华东地区销售额最高，占总销售额的35%",
        "相比2023年，2024年销售额增长了12%"
    ],
    "insights": [
        {
            "type": "comparison",
            "description": "华东地区销售额显著高于其他地区",
            "evidence": ["华东: 3500万", "华北: 2000万"],
            "confidence": 0.95,
            "importance": "high"
        }
    ],
    "contribution_analysis": [
        {
            "dimension": "地区",
            "dimension_value": "华东",
            "contribution_percentage": 35.0,
            "rank": 1
        }
    ],
    "recommendations": [
        "建议重点关注华东地区的市场策略",
        "可以进一步分析华东地区的产品类别分布"
    ],
    "confidence": 0.90,
    "reasoning": "基于完整的数据分析和统计检测结果"
}
```

---

## 5. Replanner Agent

### 职责

评估分析完整性，决定是否需要重规划，生成新的分析问题。

### 配置

```python
replanner_agent = {
    "name": "replanner-agent",
    "description": "评估分析完整性，决定是否需要深入分析",
    "model": "claude-3-5-sonnet-20241022",
    "tools": ["get_metadata"],
    "max_tokens": 2000,
    "temperature": 0.1,
    "timeout": 60
}
```

### 输入输出

**输入**（~5,250 tokens）：
```python
{
    "original_question": "为什么华东地区利润率低？",
    "accumulated_insights": [...],  # 所有轮次的洞察
    "current_round": 1,
    "max_rounds": 3
}
```

**输出**：
```python
{
    "should_replan": true,
    "reason": "找到了华东利润率低的现象，但未找到根本原因",
    "new_questions": [
        "华东地区各产品类别的利润率分别是多少？",
        "华东地区各城市的利润率分别是多少？"
    ],
    "focus_areas": ["产品类别", "城市"],
    "expected_insights": [
        "识别利润率最低的产品类别或城市",
        "找到利润率低的根本原因"
    ],
    "confidence": 0.88,
    "completeness_score": 0.4,
    "max_rounds_reached": false
}
```

### 重规划决策逻辑

```python
def should_replan(insights, round_num, max_rounds):
    # 1. 检查轮次限制
    if round_num >= max_rounds:
        return False, "达到最大轮次"
    
    # 2. 评估完整性
    completeness = evaluate_completeness(insights)
    if completeness >= 0.8:
        return False, "分析已完整"
    
    # 3. 检查是否有新发现
    has_new_anomalies = check_anomalies(insights)
    if has_new_anomalies:
        return True, "发现新异常，需要深入分析"
    
    return False, "无明显需要继续分析的方向"
```

---

## 子代理协作流程

```
用户问题
  ↓
Boost Agent (可选)
  ↓
Understanding Agent
  ↓
Planning Agent
  ├─ 调用 semantic_map_fields 工具
  └─ 生成查询计划
  ↓
执行查询（主 Agent）
  ↓
Insight Agent
  ├─ 如果数据量大 → 渐进式分析
  └─ 生成洞察
  ↓
Replanner Agent
  ├─ 评估完整性
  └─ 决定是否重规划
  ↓
IF 需要重规划:
  回到 Understanding Agent（新问题）
ELSE:
  生成最终报告
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15
