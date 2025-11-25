# DeepAgents 架构审查和问题清单

## 📋 审查日期
2024年（基于上下文转移）

## 🎯 审查目的
在更新需求和设计文档之前，全面审查当前架构设计，识别遗漏、冲突和模糊之处。

---

## ❌ 发现的问题

### 1. Question Boost Agent 缺失

**问题描述**：
- 当前系统有 Question Boost Agent（`question_boost_agent.py`）
- 但设计文档中完全没有提及
- 需求文档中也没有相关需求

**影响**：
- 架构不完整
- 可能导致功能遗漏

**建议方案**：

#### 方案 A：作为独立子代理（推荐）✅
```python
subagents = [
    {
        "name": "boost-agent",
        "description": "优化和增强用户问题",
        "prompt": QUESTION_BOOST_PROMPT,
        "tools": [get_metadata],
        "model": model_config.get("model")
    },
    {
        "name": "understanding-agent",
        ...
    },
    ...
]
```

**优势**：
- ✅ 职责清晰，独立可测试
- ✅ 可以并行执行（如果需要）
- ✅ 符合 DeepAgents 的子代理模式

#### 方案 B：作为主 Agent 的工具
```python
@tool
def boost_question(question: str, metadata: Dict) -> Dict:
    """优化用户问题"""
    # 调用 Question Boost 逻辑
    pass

agent = create_deep_agent(
    tools=[boost_question, vizql_query, ...],
    ...
)
```

**优势**：
- ✅ 更轻量
- ✅ 主 Agent 可以决定是否调用

**劣势**：
- ❌ 不符合当前的 Agent 架构
- ❌ 难以复用现有的 QuestionBoostAgent 类

**推荐**：方案 A（作为独立子代理）

---

### 2. 中间件数量不一致

**问题描述**：
- **design.md** 说有 3 个自定义中间件：
  - TableauMetadataMiddleware
  - VizQLQueryMiddleware
  - InsightGenerationMiddleware
  
- **CORRECTIONS.md** 说应该移除 InsightGenerationMiddleware，只保留 2 个

**冲突**：
- 两个文档说法不一致
- 需要明确最终方案

**分析**：

**InsightGenerationMiddleware 的作用**：
- 自动处理大型查询结果的洞察生成
- 但这个功能可以由 Insight SubAgent 完成

**建议**：移除 InsightGenerationMiddleware ✅

**理由**：
1. ✅ 洞察生成是 Insight SubAgent 的职责
2. ✅ 中间件应该是横切关注点（如元数据、查询），不是业务逻辑
3. ✅ 减少中间件数量，简化架构

**最终方案**：2 个自定义中间件
- TableauMetadataMiddleware
- VizQLQueryMiddleware

---

### 3. 子代理数量需要更新

**当前设计**：4 个子代理
- understanding-agent
- planning-agent
- insight-agent
- replanner-agent

**建议更新**：5 个子代理
- **boost-agent** ⭐ (新增)
- understanding-agent
- planning-agent
- insight-agent
- replanner-agent

---

### 4. 执行流程不完整

**当前流程**（design.md）：
```
用户问题
  ↓
主 Agent
  ↓
task(understanding-agent)
  ↓
task(planning-agent)
  ↓
执行查询
  ↓
task(insight-agent)
  ↓
task(replanner-agent)
  ↓
生成报告
```

**问题**：缺少 Question Boost 步骤

**完整流程**（建议）：
```
用户问题
  ↓
主 Agent
  ↓
(可选) task(boost-agent) ⭐ 优化问题
  ↓
task(understanding-agent) - 理解问题
  ↓
task(planning-agent) - 生成查询计划
  ↓
执行查询 (vizql_query)
  ↓
task(insight-agent) - 分析结果
  ↓
task(replanner-agent) - 评估是否需要重规划
  ├─ 如果需要 → 返回 planning-agent
  └─ 如果不需要 → 继续
  ↓
生成最终报告
```

---

## ⚠️ 模糊和需要澄清的地方

### 1. Question Boost 的触发条件

**问题**：什么时候调用 Question Boost？

**当前实现**：
```python
# 从前端传递 boost_question 参数
boost_question = request.boost_question  # True/False
```

**在 DeepAgents 中的方案**：

#### 方案 A：前端控制（保持当前行为）
```python
# 前端传递参数
if request.boost_question:
    # 主 Agent 调用 boost-agent
    boosted = await task("boost-agent", question)
    question = boosted.boosted_question
```

#### 方案 B：主 Agent 智能决定
```python
# 主 Agent 自动判断是否需要优化
# 例如：问题太短、太模糊时自动优化
```

**建议**：方案 A（前端控制）✅
- 保持向后兼容
- 用户可以选择是否优化

---

### 2. Boost Agent 是否需要工具？

**当前实现**：
```python
# QuestionBoostAgent 可以选择使用元数据
use_metadata: bool = False
```

**在 DeepAgents 中**：
```python
boost_agent = {
    "name": "boost-agent",
    "tools": [get_metadata],  # ← 是否需要？
    "prompt": QUESTION_BOOST_PROMPT
}
```

**建议**：提供 get_metadata 工具 ✅
- Boost Agent 可以参考字段信息来优化问题
- 例如：用户说"销售额"，Boost Agent 可以查看元数据确认字段名

---

### 3. 子代理的模型配置

**问题**：每个子代理是否可以使用不同的模型？

**DeepAgents 支持**：
```python
subagents = [
    {
        "name": "boost-agent",
        "model": "gpt-4o-mini",  # 轻量模型
    },
    {
        "name": "planning-agent",
        "model": "claude-sonnet-4",  # 强大模型
    }
]
```

**建议**：
- 默认所有子代理使用相同模型（从前端配置）
- 但保留为特定子代理指定模型的能力
- 例如：Boost Agent 可以用更便宜的模型

---

## ✅ 架构完整性检查

### 核心组件（100% 复用）
- ✅ QueryBuilder
- ✅ QueryExecutor
- ✅ DataProcessor
- ✅ MetadataManager
- ✅ DateParser
- ✅ FieldMapper（升级为语义映射）
- ✅ 所有 Pydantic 模型

### 子代理（5个）
- ⭐ boost-agent（新增）
- ✅ understanding-agent
- ✅ planning-agent
- ✅ insight-agent
- ✅ replanner-agent

### 自定义中间件（2个）
- ✅ TableauMetadataMiddleware
- ✅ VizQLQueryMiddleware
- ❌ InsightGenerationMiddleware（移除）

### 工具（5个）
- ✅ vizql_query（封装 QueryExecutor + DataProcessor）
- ✅ get_metadata（封装 MetadataManager）
- ✅ semantic_map_fields（升级 FieldMapper）
- ✅ parse_date（封装 DateParser）
- ✅ build_vizql_query（封装 QueryBuilder）

### DeepAgents 内置中间件
- ✅ TodoListMiddleware（高层任务规划）
- ✅ FilesystemMiddleware（文件管理）
- ✅ SubAgentMiddleware（子代理委托）
- ✅ SummarizationMiddleware（自动总结）
- ✅ AnthropicPromptCachingMiddleware（缓存）

---

## 🎯 更新建议

### 1. 需求文档更新
- [ ] 添加需求 13：Question Boost 功能
- [ ] 更新需求 2：子代理数量从 4 个改为 5 个
- [ ] 更新需求 4：中间件数量从 3 个改为 2 个

### 2. 设计文档更新
- [ ] 添加 Boost Agent 的详细设计
- [ ] 更新架构图（5 个子代理，2 个中间件）
- [ ] 更新执行流程（包含 Boost 步骤）
- [ ] 明确 Boost Agent 的触发条件
- [ ] 添加 Boost Agent 的工具配置

### 3. 组件复用文档更新
- [ ] 确认 QuestionBoostAgent 类的复用方式
- [ ] 说明如何将现有的 Boost Agent 集成到 DeepAgents

---

## 📊 最终架构总结

```
DeepAgent (主编排器)
├─ 内置中间件（5个）
│   ├─ TodoListMiddleware
│   ├─ FilesystemMiddleware
│   ├─ SubAgentMiddleware
│   ├─ SummarizationMiddleware
│   └─ AnthropicPromptCachingMiddleware
├─ 自定义中间件（2个）✅
│   ├─ TableauMetadataMiddleware
│   └─ VizQLQueryMiddleware
├─ 子代理（5个）✅
│   ├─ boost-agent ⭐ (新增)
│   ├─ understanding-agent
│   ├─ planning-agent
│   ├─ insight-agent
│   └─ replanner-agent
├─ 工具（5个）
│   ├─ vizql_query
│   ├─ get_metadata
│   ├─ semantic_map_fields
│   ├─ parse_date
│   └─ build_vizql_query
└─ 核心组件（100% 复用）
    ├─ QueryBuilder ✅
    ├─ QueryExecutor ✅
    ├─ DataProcessor ✅
    ├─ MetadataManager ✅
    ├─ DateParser ✅
    ├─ QuestionBoostAgent ✅ (新增)
    └─ 所有 Pydantic 模型 ✅
```

---

## 🚦 下一步行动

1. ✅ 确认架构更新方案
2. ⏳ 更新需求文档（requirements.md）
3. ⏳ 更新设计文档（design.md）
4. ⏳ 更新组件复用文档（COMPONENT_REUSE.md）
5. ⏳ 更新总结文档（SUMMARY.md）
6. ⏳ 更新 README.md

---

## ❓ 需要用户确认的问题

1. **Question Boost Agent 的位置**：
   - ✅ 推荐：作为独立子代理
   - ❓ 是否同意？

2. **中间件数量**：
   - ✅ 推荐：2 个（移除 InsightGenerationMiddleware）
   - ❓ 是否同意？

3. **Boost Agent 的触发条件**：
   - ✅ 推荐：前端控制（保持当前行为）
   - ❓ 是否同意？

4. **Boost Agent 的工具**：
   - ✅ 推荐：提供 get_metadata 工具
   - ❓ 是否同意？

---

**请确认以上方案，然后我将更新所有文档。**
