# 系统需求详细规格

本文档包含LangGraph工作流编排、提示词模板管理、前端UI重构的详细规格。

---

## 需求13：LangGraph工作流编排

### 详细功能说明

#### 1. 工作流定义

**节点定义**：
- **metadata_node** - 元数据管理器（获取元数据 + 维度层级推断）
- **understanding_node** - 问题理解Agent
- **field_selector_node** - 字段选择Agent
- **task_decomposer_node** - 任务拆分Agent
- **execution_node** - 任务调度器（并行执行子任务）
- **merge_node** - 数据合并器
- **replanner_node** - 重规划Agent
- **summarizer_node** - 总结Agent

**边定义**：
```python
from langgraph.graph import StateGraph, END

# 创建状态图
workflow = StateGraph(State)

# 添加节点
workflow.add_node("metadata", metadata_node)
workflow.add_node("understanding", understanding_node)
workflow.add_node("field_selector", field_selector_node)
workflow.add_node("task_decomposer", task_decomposer_node)
workflow.add_node("execution", execution_node)
workflow.add_node("merge", merge_node)
workflow.add_node("replanner", replanner_node)
workflow.add_node("summarizer", summarizer_node)

# 添加边
workflow.set_entry_point("metadata")
workflow.add_edge("metadata", "understanding")
workflow.add_edge("understanding", "field_selector")
workflow.add_edge("field_selector", "task_decomposer")
workflow.add_edge("task_decomposer", "execution")
workflow.add_edge("execution", "merge")
workflow.add_edge("merge", "replanner")

# 条件路由
workflow.add_conditional_edges(
    "replanner",
    should_replan,  # 决策函数
    {
        "replan": "understanding",  # 重规划 → 回到问题理解
        "compose": "summarizer"     # 不重规划 → 总结
    }
)

workflow.add_edge("summarizer", END)

# 编译工作流
app = workflow.compile()
```

#### 2. 状态管理

**状态定义**：
```python
from typing import TypedDict, List, Dict, Any

class State(TypedDict):
    """工作流状态"""

    # 用户输入
    user_question: str
    datasource_luid: str
    options: Dict[str, Any]

    # 元数据
    metadata: Dict[str, Any]
    dimension_hierarchy: Dict[str, Any]

    # 问题理解
    question_understanding: Dict[str, Any]

    # 字段选择
    selected_fields: Dict[str, Any]

    # 任务拆分
    subtasks: List[Dict[str, Any]]

    # 执行结果
    execution_results: List[Dict[str, Any]]

    # 合并结果
    merged_data: List[Dict[str, Any]]

    # 洞察
    insights: List[Dict[str, Any]]

    # 重规划
    replan_decision: Dict[str, Any]
    replan_history: List[Dict[str, Any]]

    # 最终报告
    final_report: Dict[str, Any]

    # 元信息
    current_round: int
    max_replan_rounds: int
    execution_time: float
```

**状态更新**：
```python
def understanding_node(state: State) -> State:
    """问题理解节点"""
    # 调用问题理解Agent
    understanding_result = understanding_agent.invoke(
        question=state["user_question"],
        options=state["options"]
    )

    # 更新状态
    state["question_understanding"] = understanding_result

    return state
```

#### 3. 对话历史管理

**使用LangGraph的MemorySaver**：
```python
from langgraph.checkpoint.memory import MemorySaver

# 创建内存存储
memory = MemorySaver()

# 编译工作流（带检查点）
app = workflow.compile(checkpointer=memory)

# 执行工作流（带会话ID）
config = {"configurable": {"thread_id": "session_123"}}
result = app.invoke(initial_state, config=config)

# 获取对话历史
history = memory.get_history(thread_id="session_123")
```

**对话历史结构**：
```python
{
  "thread_id": "session_123",
  "messages": [
    {
      "round": 1,
      "user_question": "2016年各地区的销售额",
      "final_report": {...}
    },
    {
      "round": 2,
      "user_question": "华东地区各门店的销售额",
      "final_report": {...}
    }
  ]
}
```

#### 4. 条件路由

**重规划决策函数**：
```python
def should_replan(state: State) -> str:
    """决定是否需要重规划"""
    replan_decision = state["replan_decision"]
    current_round = state["current_round"]
    max_rounds = state["max_replan_rounds"]

    # 检查是否达到最大轮数
    if current_round >= max_rounds:
        return "compose"

    # 检查是否需要重规划
    if replan_decision.get("should_replan", False):
        return "replan"
    else:
        return "compose"
```

#### 5. 检查点机制

**支持中断和恢复**：
```python
# 执行工作流（可中断）
config = {"configurable": {"thread_id": "session_123"}}

try:
    result = app.invoke(initial_state, config=config)
except KeyboardInterrupt:
    print("工作流被中断")

    # 恢复工作流
    checkpoint = memory.get_checkpoint(thread_id="session_123")
    result = app.invoke(checkpoint, config=config)
```

### 详细验收标准

#### 1. 工作流执行正确性 100%

**测试方法**：
- 准备10个不同复杂度的问题
- 验证工作流是否按照预期顺序执行
- 验证状态是否正确传递

**验收指标**：
- 节点执行顺序正确率 100%
- 状态传递正确率 100%
- 条件路由正确率 100%

#### 2. 状态管理一致性 100%

**测试方法**：
- 在每个节点后检查状态
- 验证状态是否包含所有必要字段
- 验证状态是否正确更新

**验收指标**：
- 状态完整性 100%
- 状态一致性 100%

#### 3. 错误恢复成功率 >= 90%

**测试方法**：
- 模拟不同节点的错误
- 验证是否能正确恢复
- 验证错误信息是否正确记录

**验收指标**：
- 错误恢复成功率 >= 90%
- 错误信息记录完整性 100%

#### 4. 流式输出延迟 <= 1秒

**测试方法**：
- 记录每个节点的输出时间
- 计算延迟时间

**验收指标**：
- 平均延迟 <= 0.5秒
- P95延迟 <= 1秒

---

## 需求14：提示词模板管理

### 详细功能说明

#### 1. 模板存储

**文件结构**：
```
experimental/tools/prompts.py
```

**模板命名规范**：
```python
# ========================================
# 1. Agent提示词模板（给LLM使用）
# ========================================
# 这些模板会作为system prompt或user prompt发送给LLM
# 命名规范：<AGENT_NAME>_AGENT_TEMPLATE

DIMENSION_HIERARCHY_AGENT_TEMPLATE = """..."""  # 维度层级推断Agent
UNDERSTANDING_AGENT_TEMPLATE = """..."""        # 问题理解Agent
QUERY_PLANNER_AGENT_TEMPLATE = """..."""        # 查询规划Agent（合并了字段选择和任务拆分）
INSIGHT_AGENT_TEMPLATE = """..."""              # 洞察Agent
REPLANNER_AGENT_TEMPLATE = """..."""            # 重规划Agent
SUMMARIZER_AGENT_TEMPLATE = """..."""           # 总结Agent

# ========================================
# 2. 规则模板（给LLM参考，嵌入到查询规划Agent提示词中）
# ========================================
# 这些规则会被插入到**查询规划Agent**的提示词中
# 帮助LLM生成语义级别的StructuredQuestionSpec
# 命名规范：COMMON_<RULE_NAME>_RULES

COMMON_FIELD_NAME_RULES = """..."""             # 字段命名规则（字段名必须精确匹配）
VIZQL_CAPABILITIES_SUMMARY = """..."""          # VizQL查询能力摘要（语义级别，不包含技术细节）

# 重要说明：
# - 规则模板只帮助LLM生成语义级别的Spec，不包含VizQL技术细节
# - 查询规划Agent输出的是语义Spec（如：{"dims": ["地区"], "metrics": [{"field": "销售额", "aggregation": "sum"}]}）
# - 查询构建器根据语义Spec用代码规则生成技术级别的VizQL查询JSON
# - 查询构建器参考tableau_sdk的类型定义，确保生成的查询100%符合VDS规范

# ========================================
# 3. 非LLM模板（纯代码使用，不给LLM）
# ========================================
# 这些模板是代码逻辑使用的，不会发送给LLM
# 命名规范：<COMPONENT_NAME>_<PURPOSE>

# 注意：以下模板不在prompts.py中，而是在各自的代码文件中
# - VIZQL_QUERY_TEMPLATE：VizQL查询JSON模板（查询构建器使用，纯代码规则）
# - MERGE_STRATEGY_RULES：数据合并策略规则（数据合并器使用，纯代码规则）
# - ERROR_MESSAGE_TEMPLATE：错误消息模板（错误处理使用）
# - PROGRESS_MESSAGE_TEMPLATE：进度消息模板（SSE推送使用）
```

#### 2. 模板分类说明

**给LLM使用的模板**（存储在prompts.py中）：

| 类型 | 数量 | 命名规范 | 用途 | 使用者 | 示例 |
|------|------|----------|------|--------|------|
| **Agent提示词** | 6个 | `<AGENT_NAME>_AGENT_TEMPLATE` | 作为system prompt发送给LLM | 各Agent | `UNDERSTANDING_AGENT_TEMPLATE` |
| **规则模板** | 2个 | `COMMON_<RULE_NAME>_RULES` | 嵌入到**查询规划Agent**提示词中，帮助LLM生成正确的Spec | 查询规划Agent | `COMMON_FIELD_NAME_RULES` |

**不给LLM使用的模板**（存储在各自的代码文件中）：

| 类型 | 用途 | 存储位置 | 使用者 | 示例 |
|------|------|----------|--------|------|
| **代码模板** | 生成VizQL查询JSON | 查询构建器代码中 | 查询构建器 | VizQL查询JSON模板 |
| **合并规则** | 决定数据合并策略 | 数据合并器代码中 | 数据合并器 | 合并策略规则 |
| **消息模板** | 错误消息、进度消息等 | 各组件的代码文件中 | 各组件 | 错误消息模板 |

**关键区别**：
- ✅ **给LLM用的模板** → 存储在`prompts.py`中，内容是自然语言描述，会发送给LLM
  - Agent提示词：直接作为prompt
  - 规则模板：嵌入到**任务拆分Agent**的提示词中，帮助LLM生成符合VizQL规范的Spec
- ❌ **不给LLM用的模板** → 存储在各自的代码文件中，内容是代码或配置，不会发送给LLM
  - 查询构建器：根据Spec用代码规则生成VizQL查询
  - 数据合并器：用代码规则决定合并策略

#### 3. 模板结构

**标准Agent提示词结构**：
```python
UNDERSTANDING_AGENT_TEMPLATE = """
# 角色定义
你是一位资深的业务数据分析师。

# 任务说明
你的任务是理解用户的问题意图，提取关键信息，评估问题复杂度。

# 输入说明
- 用户问题：{question}
- 数据源信息：{datasource_info}

# 输出格式
请输出JSON格式：
{{
  "question_type": ["类型1", "类型2"],
  "time_range": {{...}},
  "filters": {{...}},
  "complexity": "Simple/Medium/Complex"
}}

# 示例
输入：2016年各地区的销售额
输出：
{{
  "question_type": ["对比"],
  "time_range": {{"type": "absolute", "start": "2016-01-01", "end": "2016-12-31"}},
  "complexity": "Simple"
}}

# 注意事项
1. 时间范围只负责理解和提取，具体日期计算由查询构建器完成
2. 识别隐含需求（如同比需要两个时间段）
3. 评估问题复杂度（Simple/Medium/Complex）
"""
```

#### 3. 模板版本控制

**使用Git管理**：
```bash
# 提交提示词变更
git add experimental/tools/prompts.py
git commit -m "feat: 优化问题理解Agent的提示词"

# 查看提示词变更历史
git log --oneline experimental/tools/prompts.py

# 回滚提示词
git checkout <commit_hash> experimental/tools/prompts.py
```

**变更日志**：
```python
# prompts.py 文件头部
"""
提示词模板管理

变更日志：
- 2025-10-30: 优化问题理解Agent的提示词，增加隐含需求识别
- 2025-01-14: 优化字段选择Agent的提示词，增加维度层级利用
- 2025-01-13: 初始版本
"""
```

#### 4. 模板测试

**测试用例**：
```python
# tests/test_prompts.py

def test_understanding_agent_template():
    """测试问题理解Agent的提示词"""
    # 准备测试数据
    test_cases = [
        {
            "question": "2016年各地区的销售额",
            "expected_output": {
                "question_type": ["对比"],
                "complexity": "Simple"
            }
        },
        {
            "question": "2016年vs 2015年的销售额增长率",
            "expected_output": {
                "question_type": ["对比", "同比"],
                "complexity": "Medium"
            }
        }
    ]

    # 执行测试
    for case in test_cases:
        result = understanding_agent.invoke(case["question"])
        assert result["question_type"] == case["expected_output"]["question_type"]
        assert result["complexity"] == case["expected_output"]["complexity"]
```

### 详细验收标准

#### 1. 所有提示词集中管理 100%

**测试方法**：
- 检查所有Agent的提示词是否在prompts.py中
- 检查是否有硬编码的提示词

**验收指标**：
- 所有提示词在prompts.py中
- 无硬编码提示词

#### 2. 命名规范遵守率 100%

**测试方法**：
- 检查所有提示词的命名是否符合规范
- 规范：`<AGENT_NAME>_AGENT_TEMPLATE` 或 `<RULE_NAME>_RULES`

**验收指标**：
- 命名规范遵守率 100%

#### 3. 版本控制覆盖率 100%

**测试方法**：
- 检查prompts.py是否在Git版本控制中
- 检查是否有变更日志

**验收指标**：
- prompts.py在Git版本控制中
- 有变更日志

#### 4. 模板测试覆盖率 >= 80%

**测试方法**：
- 检查是否有测试用例
- 计算测试覆盖率

**验收指标**：
- 每个Agent至少有3个测试用例
- 测试覆盖率 >= 80%

---



---

## 需求14：前端UI重构（Vue 3 + TypeScript）

### 详细功能说明

#### 1. 对话界面

**设计目标**：像ChatGPT一样流畅的对话体验

**核心功能**：
- Token级流式输出（SSE）
- Markdown渲染（支持表格、代码块、列表）
- 代码高亮（使用highlight.js）
- LaTeX公式渲染（使用KaTeX）
- 图片预览
- 消息编辑和重新生成

**技术实现**：
```vue
<template>
  <div class="chat-container">
    <!-- 消息列表 -->
    <div class="message-list" ref="messageList">
      <div
        v-for="message in messages"
        :key="message.id"
        :class="['message', message.role]"
      >
        <!-- 用户消息 -->
        <div v-if="message.role === 'user'" class="user-message">
          {{ message.content }}
        </div>

        <!-- AI消息（支持流式输出） -->
        <div v-else class="ai-message">
          <MarkdownRenderer :content="message.content" :streaming="message.streaming" />
        </div>
      </div>
    </div>

    <!-- 输入框 -->
    <div class="input-container">
      <textarea
        v-model="userInput"
        @keydown.enter.exact="sendMessage"
        placeholder="输入问题..."
      />
      <div class="input-actions">
        <button @click="boostQuestion" class="boost-btn" :disabled="!userInput.trim()">
          ✨ Boost
        </button>
        <button @click="sendMessage" class="send-btn" :disabled="!userInput.trim()">
          发送
        </button>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import MarkdownRenderer from './MarkdownRenderer.vue'

const messages = ref<Message[]>([])
const userInput = ref('')
const messageList = ref<HTMLElement>()

// 问题Boost功能（使用LLM增强问题）
const boostQuestion = async () => {
  if (!userInput.value.trim()) return

  const originalQuestion = userInput.value

  // 显示加载状态
  const loadingMessage: Message = {
    id: Date.now(),
    role: 'system',
    content: '正在优化您的问题...',
    streaming: true
  }
  messages.value.push(loadingMessage)

  try {
    // 调用后端API增强问题
    const response = await fetch('/api/boost-question', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({
        question: originalQuestion,
        datasource_luid: currentDatasource.value
      })
    })

    const { boosted_question, suggestions } = await response.json()

    // 移除加载消息
    messages.value = messages.value.filter(m => m.id !== loadingMessage.id)

    // 显示增强后的问题和建议
    const boostMessage: Message = {
      id: Date.now(),
      role: 'system',
      content: `
### 优化后的问题
${boosted_question}

### 其他建议
${suggestions.map((s: string, i: number) => `${i + 1}. ${s}`).join('\n')}

您可以选择使用优化后的问题，或继续使用原问题。
      `
    }
    messages.value.push(boostMessage)

    // 更新输入框为增强后的问题
    userInput.value = boosted_question

  } catch (error) {
    // 移除加载消息
    messages.value = messages.value.filter(m => m.id !== loadingMessage.id)

    // 显示错误
    messages.value.push({
      id: Date.now(),
      role: 'system',
      content: '问题优化失败，请直接发送原问题。'
    })
  }
}

// 发送消息
const sendMessage = async () => {
  if (!userInput.value.trim()) return

  // 添加用户消息
  messages.value.push({
    id: Date.now(),
    role: 'user',
    content: userInput.value
  })

  // 清空输入框
  const question = userInput.value
  userInput.value = ''

  // 创建AI消息（流式输出）
  const aiMessage: Message = {
    id: Date.now() + 1,
    role: 'assistant',
    content: '',
    streaming: true
  }
  messages.value.push(aiMessage)

  // 建立SSE连接
  const eventSource = new EventSource(`/api/chat?question=${encodeURIComponent(question)}`)

  eventSource.onmessage = (event) => {
    const data = JSON.parse(event.data)

    if (data.type === 'token') {
      // Token级流式输出
      aiMessage.content += data.content
    } else if (data.type === 'done') {
      // 流式输出完成
      aiMessage.streaming = false
      eventSource.close()
    }
  }

  eventSource.onerror = () => {
    aiMessage.streaming = false
    eventSource.close()
  }
}

// 自动滚动到底部
watch(messages, () => {
  setTimeout(() => {
    messageList.value?.scrollTo({
      top: messageList.value.scrollHeight,
      behavior: 'smooth'
    })
  }, 100)
}, { deep: true })
</script>
```

#### 2. 分析过程展示

**设计目标**：像Perplexity一样清晰的分析过程

**核心功能**：
- 展示6个Agent的执行过程
- 展示每个Agent的输入输出
- 展示执行时间和token消耗
- 支持折叠/展开
- 支持复制结果

**技术实现**：
```vue
<template>
  <div class="analysis-process">
    <div class="process-header">
      <h3>分析过程</h3>
      <button @click="toggleAll">{{ allExpanded ? '全部折叠' : '全部展开' }}</button>
    </div>

    <!-- Agent执行步骤 -->
    <div
      v-for="step in analysisSteps"
      :key="step.id"
      :class="['process-step', step.status]"
    >
      <!-- 步骤头部 -->
      <div class="step-header" @click="toggleStep(step.id)">
        <div class="step-info">
          <span class="step-icon">{{ getStepIcon(step.status) }}</span>
          <span class="step-name">{{ step.name }}</span>
          <span class="step-time">{{ step.duration }}ms</span>
          <span class="step-tokens">{{ step.tokens }} tokens</span>
        </div>
        <span class="expand-icon">{{ step.expanded ? '▼' : '▶' }}</span>
      </div>

      <!-- 步骤详情 -->
      <div v-if="step.expanded" class="step-details">
        <!-- 输入 -->
        <div class="step-section">
          <h4>输入</h4>
          <CodeBlock :code="JSON.stringify(step.input, null, 2)" language="json" />
        </div>

        <!-- 输出 -->
        <div class="step-section">
          <h4>输出</h4>
          <CodeBlock :code="JSON.stringify(step.output, null, 2)" language="json" />
        </div>

        <!-- 错误信息 -->
        <div v-if="step.error" class="step-section error">
          <h4>错误</h4>
          <pre>{{ step.error }}</pre>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import CodeBlock from './CodeBlock.vue'

interface AnalysisStep {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
  duration: number
  tokens: number
  input: any
  output: any
  error?: string
  expanded: boolean
}

const analysisSteps = ref<AnalysisStep[]>([])
const allExpanded = computed(() => analysisSteps.value.every(s => s.expanded))

const toggleStep = (id: string) => {
  const step = analysisSteps.value.find(s => s.id === id)
  if (step) {
    step.expanded = !step.expanded
  }
}

const toggleAll = () => {
  const expand = !allExpanded.value
  analysisSteps.value.forEach(s => s.expanded = expand)
}

const getStepIcon = (status: string) => {
  switch (status) {
    case 'pending': return '⏳'
    case 'running': return '🔄'
    case 'completed': return '✅'
    case 'error': return '❌'
    default: return '❓'
  }
}
</script>
```

#### 3. 数据可视化

**设计目标**：使用Tableau原生可视化能力，提供专业的数据展示

**核心功能**：
- 表格展示（支持排序、筛选、分页）
- **Tableau临时viz可视化**（使用Tableau Embedding API v3）
- 下钻交互（点击维度值下钻）
- 数据导出（CSV、Excel）

**技术实现**：

**方案1：使用Tableau Embedding API v3创建临时viz**

```vue
<template>
  <div class="data-visualization">
    <!-- 视图切换 -->
    <div class="view-switcher">
      <button
        v-for="view in ['table', 'viz']"
        :key="view"
        :class="{ active: currentView === view }"
        @click="currentView = view"
      >
        {{ view === 'table' ? '表格' : 'Tableau可视化' }}
      </button>
    </div>

    <!-- 表格视图 -->
    <div v-if="currentView === 'table'" class="table-view">
      <DataTable
        :data="tableData"
        :columns="tableColumns"
        :sortable="true"
        :filterable="true"
        :pageable="true"
        @row-click="handleRowClick"
      />
    </div>

    <!-- Tableau可视化视图 -->
    <div v-else class="viz-view">
      <div ref="vizContainer" class="viz-container"></div>
    </div>

    <!-- 导出按钮 -->
    <div class="export-buttons">
      <button @click="exportCSV">导出CSV</button>
      <button @click="exportExcel">导出Excel</button>
      <button v-if="currentView === 'viz'" @click="exportVizImage">导出图片</button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, watch } from 'vue'
import DataTable from './DataTable.vue'

const currentView = ref<'table' | 'viz'>('table')
const tableData = ref([])
const tableColumns = ref([])
const vizContainer = ref<HTMLElement>()
let viz: any = null

// 创建Tableau临时viz
const createTempViz = async (queryResult: any) => {
  if (!vizContainer.value) return

  // 1. 调用后端API创建临时viz
  const response = await fetch('/api/create-temp-viz', {
    method: 'POST',
    headers: { 'Content-Type': 'application/json' },
    body: JSON.stringify({
      datasource_luid: queryResult.datasource_luid,
      vizql_query: queryResult.vizql_query,
      viz_type: 'bar' // 或根据数据自动推荐
    })
  })

  const { temp_viz_url } = await response.json()

  // 2. 使用Tableau Embedding API v3嵌入viz
  const { TableauViz } = await import('@tableau/embedding-api')

  viz = new TableauViz()
  viz.src = temp_viz_url
  viz.width = '100%'
  viz.height = '600px'
  viz.toolbar = 'bottom'

  vizContainer.value.appendChild(viz)
}

// 处理行点击（下钻）
const handleRowClick = (row: any) => {
  emit('drill-down', row)
}

// 导出功能
const exportCSV = () => {
  const csv = convertToCSV(tableData.value)
  downloadFile(csv, 'data.csv', 'text/csv')
}

const exportExcel = () => {
  const excel = convertToExcel(tableData.value)
  downloadFile(excel, 'data.xlsx', 'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet')
}

const exportVizImage = async () => {
  if (viz) {
    const image = await viz.exportImageAsync()
    downloadFile(image, 'viz.png', 'image/png')
  }
}

// 监听查询结果变化
watch(() => props.queryResult, (newResult) => {
  if (newResult && currentView.value === 'viz') {
    createTempViz(newResult)
  }
})
</script>

<style scoped>
.viz-container {
  width: 100%;
  min-height: 600px;
  border: 1px solid var(--gray-200);
  border-radius: 8px;
  overflow: hidden;
}
</style>
```

**后端API实现（Python）**：

```python
from tableau_api_lib import TableauServerConnection
from tableau_api_lib.utils import querying

@app.post("/api/create-temp-viz")
async def create_temp_viz(request: TempVizRequest):
    """
    创建Tableau临时viz

    流程：
    1. 使用VizQL查询获取数据
    2. 创建临时工作簿（使用Tableau REST API）
    3. 返回临时viz的嵌入URL
    """
    # 1. 执行VizQL查询获取数据
    query_result = execute_vizql_query(
        datasource_luid=request.datasource_luid,
        query=request.vizql_query
    )

    # 2. 创建临时工作簿
    # 使用Tableau Hyper API创建临时数据源
    temp_hyper_file = create_temp_hyper(query_result.data)

    # 3. 发布临时工作簿到Tableau Server
    workbook_id = publish_temp_workbook(
        hyper_file=temp_hyper_file,
        viz_type=request.viz_type,
        project_id=TEMP_PROJECT_ID  # 专门用于临时viz的项目
    )

    # 4. 生成嵌入URL（带JWT token）
    embed_url = generate_embed_url(
        workbook_id=workbook_id,
        view_name="Sheet1",
        expiry_minutes=60  # 1小时后过期
    )

    # 5. 设置自动清理任务（1小时后删除）
    schedule_cleanup(workbook_id, delay_minutes=60)

    return {"temp_viz_url": embed_url}
```

#### 4. 进度反馈

**设计目标**：实时显示执行进度

**核心功能**：
- 实时进度条
- 当前执行的Agent
- 已完成/总任务数
- 预计剩余时间

**技术实现**：
```vue
<template>
  <div class="progress-feedback">
    <!-- 进度条 -->
    <div class="progress-bar">
      <div class="progress-fill" :style="{ width: `${progress}%` }"></div>
    </div>

    <!-- 进度信息 -->
    <div class="progress-info">
      <span class="current-agent">{{ currentAgent }}</span>
      <span class="task-count">{{ completedTasks }} / {{ totalTasks }}</span>
      <span class="estimated-time">预计剩余 {{ estimatedTime }}秒</span>
    </div>

    <!-- 任务列表 -->
    <div class="task-list">
      <div
        v-for="task in tasks"
        :key="task.id"
        :class="['task-item', task.status]"
      >
        <span class="task-icon">{{ getTaskIcon(task.status) }}</span>
        <span class="task-name">{{ task.name }}</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted } from 'vue'

interface Task {
  id: string
  name: string
  status: 'pending' | 'running' | 'completed' | 'error'
}

const tasks = ref<Task[]>([])
const currentAgent = ref('')
const completedTasks = computed(() => tasks.value.filter(t => t.status === 'completed').length)
const totalTasks = computed(() => tasks.value.length)
const progress = computed(() => (completedTasks.value / totalTasks.value) * 100)
const estimatedTime = ref(0)

// 建立SSE连接接收进度更新
onMounted(() => {
  const eventSource = new EventSource('/api/progress')

  eventSource.addEventListener('task_start', (event) => {
    const data = JSON.parse(event.data)
    const task = tasks.value.find(t => t.id === data.task_id)
    if (task) {
      task.status = 'running'
      currentAgent.value = data.agent_name
    }
  })

  eventSource.addEventListener('task_complete', (event) => {
    const data = JSON.parse(event.data)
    const task = tasks.value.find(t => t.id === data.task_id)
    if (task) {
      task.status = 'completed'
    }
  })

  eventSource.addEventListener('task_error', (event) => {
    const data = JSON.parse(event.data)
    const task = tasks.value.find(t => t.id === data.task_id)
    if (task) {
      task.status = 'error'
    }
  })
})

const getTaskIcon = (status: string) => {
  switch (status) {
    case 'pending': return '⏳'
    case 'running': return '🔄'
    case 'completed': return '✅'
    case 'error': return '❌'
    default: return '❓'
  }
}
</script>
```

#### 5. 重规划交互

**设计目标**：展示推荐问题，支持一键执行

**核心功能**：
- 展示推荐问题列表
- 显示推荐理由
- 一键执行推荐问题
- 编辑推荐问题

**技术实现**：
```vue
<template>
  <div class="replan-interaction">
    <div class="replan-header">
      <h3>发现以下值得深入的问题</h3>
    </div>

    <!-- 推荐问题列表 -->
    <div class="suggested-questions">
      <div
        v-for="question in suggestedQuestions"
        :key="question.id"
        class="question-card"
      >
        <!-- 问题内容 -->
        <div class="question-content">
          <h4>{{ question.text }}</h4>
          <p class="question-reason">{{ question.reason }}</p>
        </div>

        <!-- 操作按钮 -->
        <div class="question-actions">
          <button @click="executeQuestion(question)" class="primary">
            执行
          </button>
          <button @click="editQuestion(question)" class="secondary">
            编辑
          </button>
          <button @click="dismissQuestion(question)" class="tertiary">
            忽略
          </button>
        </div>
      </div>
    </div>

    <!-- 或者继续原问题 -->
    <div class="continue-option">
      <button @click="continueOriginal">
        不深入，直接生成报告
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'

interface SuggestedQuestion {
  id: string
  text: string
  reason: string
  type: 'drill_down' | 'comparison' | 'root_cause'
}

const suggestedQuestions = ref<SuggestedQuestion[]>([])

const executeQuestion = (question: SuggestedQuestion) => {
  // 执行推荐问题
  emit('execute-question', question.text)
}

const editQuestion = (question: SuggestedQuestion) => {
  // 打开编辑对话框
  const edited = prompt('编辑问题', question.text)
  if (edited) {
    emit('execute-question', edited)
  }
}

const dismissQuestion = (question: SuggestedQuestion) => {
  // 忽略推荐问题
  suggestedQuestions.value = suggestedQuestions.value.filter(q => q.id !== question.id)
}

const continueOriginal = () => {
  // 不重规划，直接生成报告
  emit('skip-replan')
}
</script>
```

### 详细验收标准

#### 1. 流式输出流畅度 >= 90%

**测试方法**：
- 测试100次流式输出
- 记录卡顿次数（延迟 > 500ms）
- 计算流畅度 = (100 - 卡顿次数) / 100

**验收指标**：
- 流畅度 >= 90%
- 平均延迟 <= 100ms
- P95延迟 <= 300ms

#### 2. 分析过程可视化完整性 100%

**测试方法**：
- 检查是否展示了所有Agent的执行过程
- 检查是否展示了输入输出
- 检查是否展示了执行时间和token消耗

**验收指标**：
- 所有Agent都有展示
- 输入输出完整
- 时间和token准确

#### 3. 数据可视化准确性 100%

**测试方法**：
- 对比表格数据和原始数据
- 对比图表数据和原始数据
- 验证排序、筛选、分页功能

**验收指标**：
- 表格数据准确率 100%
- 图表数据准确率 100%
- 排序、筛选、分页功能正常

#### 4. 进度反馈实时性 <= 1秒延迟

**测试方法**：
- 记录后端发送进度更新的时间
- 记录前端接收进度更新的时间
- 计算延迟时间

**验收指标**：
- 平均延迟 <= 0.5秒
- P95延迟 <= 1秒

---

**文档版本**: v1.0
**最后更新**: 2025-10-30


---

## 需求15：问题Boost功能

### 详细功能说明

**设计目标**：借助LLM能力，帮助用户优化和增强问题表达，提高分析准确性

#### 核心功能

1. **问题优化** - 将模糊的问题转换为更精确的表达
2. **问题补全** - 自动补充缺失的关键信息（时间范围、维度、度量）
3. **多个建议** - 提供3-5个相关的问题建议
4. **上下文感知** - 基于数据源元数据和对话历史优化问题

#### 后端API实现

```python
from langchain.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI

@app.post("/api/boost-question")
async def boost_question(request: BoostQuestionRequest):
    """
    使用LLM增强用户问题

    输入：
    - question: 用户原始问题
    - datasource_luid: 数据源ID
    - conversation_history: 对话历史（可选）

    输出：
    - boosted_question: 优化后的问题
    - suggestions: 相关问题建议列表
    - reasoning: 优化理由
    """

    # 1. 获取数据源元数据
    metadata = get_metadata(request.datasource_luid)
    dimension_hierarchy = get_dimension_hierarchy(request.datasource_luid)

    # 2. 构建提示词
    prompt = ChatPromptTemplate.from_messages([
        ("system", QUESTION_BOOST_TEMPLATE),
        ("user", """
原始问题：{question}

数据源信息：
- 可用维度：{dimensions}
- 可用度量：{measures}
- 维度层级：{hierarchy}

对话历史：
{conversation_history}

请优化这个问题，使其更加精确和可执行。
        """)
    ])

    # 3. 调用LLM
    llm = ChatOpenAI(model="gpt-4", temperature=0.3)
    chain = prompt | llm

    result = chain.invoke({
        "question": request.question,
        "dimensions": [d["fieldCaption"] for d in metadata["dimensions"]],
        "measures": [m["fieldCaption"] for m in metadata["measures"]],
        "hierarchy": json.dumps(dimension_hierarchy, ensure_ascii=False),
        "conversation_history": format_conversation_history(request.conversation_history)
    })

    # 4. 解析结果
    response = json.loads(result.content)

    return {
        "boosted_question": response["boosted_question"],
        "suggestions": response["suggestions"],
        "reasoning": response["reasoning"]
    }
```

#### 提示词模板

```python
QUESTION_BOOST_TEMPLATE = """
你是一位资深的数据分析师，擅长将模糊的业务问题转换为精确的数据查询问题。

你的任务是优化用户的问题，使其：
1. **更精确** - 明确时间范围、维度、度量
2. **更完整** - 补充缺失的关键信息
3. **更可执行** - 符合数据源的字段和能力

优化规则：
1. 如果问题缺少时间范围，根据上下文推断或使用"最近一个月"
2. 如果维度名称模糊，映射到数据源中的实际字段名
3. 如果度量名称模糊，映射到数据源中的实际字段名
4. 如果问题过于宽泛，建议具体的分析角度

输出格式（JSON）：
{
  "boosted_question": "优化后的问题",
  "suggestions": [
    "相关问题建议1",
    "相关问题建议2",
    "相关问题建议3"
  ],
  "reasoning": "优化理由"
}

示例：

输入：
原始问题：销售情况怎么样
数据源：零售销售数据
可用维度：地区、产品类别、门店、日期
可用度量：销售额、订单量、客户数

输出：
{
  "boosted_question": "最近一个月各地区的销售额、订单量和客户数分别是多少？",
  "suggestions": [
    "最近一个月销售额TOP10的门店是哪些？",
    "最近一个月各产品类别的销售额占比",
    "最近一个月的销售额趋势（按日统计）"
  ],
  "reasoning": "原问题过于宽泛，补充了时间范围（最近一个月）、维度（地区）和度量（销售额、订单量、客户数），使问题更加具体和可执行。"
}
"""
```

#### 验收标准

1. **优化准确率 >= 85%** - 优化后的问题能够被系统正确理解和执行
2. **建议相关性 >= 80%** - 提供的问题建议与原问题相关
3. **响应时间 <= 2秒** - 问题优化不应影响用户体验
4. **用户采纳率 >= 60%** - 用户选择使用优化后的问题的比例

---

**文档版本**: v1.0
**最后更新**: 2025-10-30


---

## 需求17：环境配置管理

### 详细功能说明

#### 1. .env文件配置

**配置项定义**：

```bash
# ========== 日期处理配置 ==========

# 周开始日：0=周一（ISO标准，中国习惯），6=周日（美国标准）
# 注意：如果问题中明确提到周开始日，以问题为准
WEEK_START_DAY=0

# SetFilter阈值（uniqueCount小于此值时使用SetFilter）
SET_FILTER_THRESHOLD=50



# ========== 日志配置 ==========

# 日志级别：DEBUG, INFO, WARNING, ERROR, CRITICAL
LOG_LEVEL=INFO

# 日志文件路径
LOG_FILE=logs/tableau_assistant.log

# ========== API配置 ==========

# API服务
API_HOST=0.0.0.0
API_PORT=8000

# CORS配置
CORS_ORIGINS=http://localhost:3000,http://localhost:5173
```

```

#### 4. 配置优先级

**日期处理配置的优先级**：

1. **问题理解结果**（最高优先级）
   - 用户在问题中明确提到的配置（如"周日开始的本周"）
   - 由问题理解Agent提取

2. **.env环境配置**
   - 从.env文件加载的配置
   - 适用于整个系统的默认行为

3. **代码默认值**（最低优先级）
   - 当.env未配置时使用的fallback值
   - 确保系统能正常运行

**实现示例**：

```python
def get_week_start_day(
    date_features: Dict,
    config: Config
) -> int:
    """
    获取周开始日（优先级：问题指定 > 环境配置 > 默认值）
    
    Args:
        date_features: 问题理解Agent提取的日期特征
        config: 全局配置
    
    Returns:
        0: 周一开始
        6: 周日开始
    """
    # 优先级1：问题中明确提到
    if date_features.get("week_start_day_mentioned"):
        return date_features["week_start_day"]
    
    # 优先级2：环境配置
    return config.WEEK_START_DAY
```

### 详细验收标准

#### 1. 配置加载正确性

**测试方法**：
- 创建测试.env文件
- 加载配置
- 验证所有配置项的值

**验收指标**：
- 所有配置项都能正确加载
- 配置默认值正确
- 配置类型转换正确（int、float、bool、list）

#### 2. 配置验证完整性

**测试方法**：
- 测试缺少必需配置的情况
- 测试配置值超出范围的情况
- 验证错误消息清晰

**验收指标**：
- 缺少必需配置时抛出清晰错误
- 配置值超出范围时抛出清晰错误
- 错误消息包含配置项名称和要求

#### 3. 配置优先级正确

**测试方法**：
- 测试问题指定 > 环境配置 > 默认值的优先级
- 验证不同场景下的配置选择

**验收指标**：
- 问题指定的配置优先级最高
- 环境配置优先于默认值
- 配置选择逻辑清晰可追踪

#### 4. .env.example文件完整

**验收指标**：
- 包含所有配置项
- 每个配置项都有注释说明
- 提供合理的示例值
- 标注必需配置和可选配置

#### 5. 配置文档完整

**验收指标**：
- README中包含配置说明
- 每个配置项都有详细说明
- 提供配置示例
- 说明配置优先级规则

---
