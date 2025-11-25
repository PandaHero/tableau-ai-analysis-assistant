# VizQL多智能体查询与分析重构 - 设计文档

## 文档导航

本设计文档采用**精简主文档 + 详细附录**的结构，便于快速理解和深入研究。

### 📋 主文档（本文件）
- 技术架构概述
- 核心设计决策
- 数据流设计
- 关键技术选型

### 📚 详细附录（./design-appendix/）
- [Agent设计详解](./design-appendix/agent-design.md) - 7个Agent的详细设计
- [代码组件设计详解](./design-appendix/component-design.md) - 6个代码组件的详细设计
- [数据模型设计](./design-appendix/data-models.md) - 完整的数据模型定义
- [API设计](./design-appendix/api-design.md) - REST API和内部接口设计
- [前端架构设计](./design-appendix/frontend-design.md) - Vue 3前端架构

---

## 技术架构

### 整体架构图

```
┌─────────────────────────────────────────────────────────────┐
│                    前端层 (Vue 3 + TypeScript)               │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  对话界面 │ 进度展示 │ 数据可视化 │ Tableau Viz      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │ HTTP/SSE
┌─────────────────────────────────────────────────────────────┐
│                    API层 (FastAPI)                           │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  /api/chat  │  /api/boost  │  /api/temp-viz         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│              LangGraph编排层 (StateGraph)                    │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  状态管理 │ 工作流编排 │ 对话历史 │ 检查点机制      │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                   Agent层 (7个Agent)                         │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  维度层级 │ 问题Boost │ 问题理解 │ 任务规划         │  │
│  │  洞察     │ 重规划    │ 总结                         │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                代码组件层 (6个组件)                          │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  元数据管理 │ 查询构建 │ 查询执行 │ 统计检测        │  │
│  │  数据合并   │ 任务调度                               │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
                            │
┌─────────────────────────────────────────────────────────────┐
│                      数据层                                  │
│  ┌──────────────────────────────────────────────────────┐  │
│  │  Redis缓存 │ Tableau VDS │ Tableau REST API │ LLM   │  │
│  └──────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────┘
```

---

## 核心设计决策

### 1. 为什么选择LangGraph？

**决策**：使用LangGraph作为工作流编排框架

**理由**：
- ✅ **状态管理** - 内置StateGraph，自动管理状态传递
- ✅ **对话历史** - MemorySaver提供开箱即用的对话历史管理
- ✅ **条件路由** - 支持复杂的条件分支（如重规划决策）
- ✅ **检查点机制** - 支持中断和恢复
- ✅ **流式输出** - 原生支持SSE流式输出
- ✅ **可视化** - 可以生成工作流图，便于调试

**替代方案**：
- ❌ 纯LangChain - 缺少状态管理和对话历史
- ❌ 自定义编排 - 开发成本高，功能不完善

### 2. 为什么合并字段选择和任务拆分？

**决策**：将字段选择Agent和任务拆分Agent合并为任务规划Agent

**理由**：
- ✅ **减少LLM调用** - 从2次减少到1次，节省~2秒和~5,700 tokens
- ✅ **避免信息丢失** - 字段选择和任务拆分高度相关，合并后避免信息传递损失
- ✅ **简化流程** - 减少状态传递的复杂度

**权衡**：
- ⚠️ 单次token消耗增加（从~4,000增加到~8,250）
- ✅ 但仍在20%上下文限制内（40,960 × 20% = 8,192）

### 3. 双路径设计：Simple/Medium vs Complex问题

**核心决策**：根据问题复杂度采用不同的处理路径

**Simple/Medium问题（直接执行路径）**：
- ✅ 用户知道要什么 → 直接生成完整查询
- ✅ needs_replan=False → 跳过洞察和重规划
- ✅ 可能有拆分和依赖 → 任务调度器按stage执行
- ✅ 必须走数据合并器 → 计算占比、排名等
- ✅ 直接生成总结 → 高效完成

**Complex问题（探索式分析路径）**：
- ✅ 用户不知道答案在哪 → 探索式分析
- ✅ needs_replan=True → 必须走洞察和重规划
- ✅ 第0轮生成现象确认查询 → 全局视图（不局部查询）
- ✅ 洞察Agent分析异常 → 生成探索建议
- ✅ 重规划Agent决策 → 生成下一轮问题
- ✅ 多轮迭代 → 类似Tableau Pulse

**职责划分优化**：

**问题理解Agent**（语义级别）：
- ✅ 基于VizQL能力拆分子问题
- ✅ 评估问题复杂度（决定后续路径）
- ✅ 记录用户说的词（如"区域"、"收入"）
- ❌ 不验证字段是否存在

**任务规划Agent**（技术级别）：
- ✅ 根据complexity选择路径
- ✅ Complex问题生成全局查询（为统计检测提供对比数据）
- ✅ Simple/Medium问题识别依赖关系
- ✅ 完整字段映射和QuerySpec生成

**洞察Agent**（数据分析+探索建议）：
- ✅ 基于指标类型选择分析方式（异常分析 vs 贡献度分析）
- ✅ 查找dimension_hierarchy，生成exploration_suggestions
- ✅ 包含child_dimension和优先级

**重规划Agent**（决策+问题生成+多轮控制）：
- ✅ 评估exploration_suggestions优先级
- ✅ 生成自然语言问题
- ✅ 控制重规划轮次（支持多轮迭代）
- ✅ 评估分析完整性，决定是否继续
- ❌ 不查找维度层级（洞察Agent已完成）

**理由**：
- ✅ **职责清晰** - 理解、规划、分析、决策各司其职
- ✅ **便于调试** - 可以单独验证每个环节
- ✅ **减少token** - 问题理解不需要元数据（节省~6,700 tokens）
- ✅ **智能规划** - 根据问题复杂度采用不同的规划策略
- ✅ **灵活迭代** - 支持多轮重规划，直到分析完整

### 4. 重规划轮次控制设计

**决策**：支持多轮重规划，通过环境变量控制最大轮数

**关键概念**：

1. **needs_replan**（任务规划Agent设置）：
   - 初始标志，由问题复杂度决定
   - Complex问题第0轮：needs_replan=true
   - 第1轮及以后：needs_replan=false（处理具体问题）

2. **should_replan**（重规划Agent决策）：
   - 每轮的决策，由重规划Agent根据分析结果决定
   - 可以多轮重规划，直到分析完整或达到最大轮数

**控制流程**：

```python
# 伪代码
round_num = 0
max_rounds = int(os.getenv("MAX_REPLAN_ROUNDS", "3"))

while round_num <= max_rounds:
    if round_num == 0:
        # 第0轮：初始查询
        planning_result = task_planner_agent(
            question=original_question,
            complexity="Complex"
        )
        # planning_result.needs_replan = True
    else:
        # 第1轮及以后：处理重规划问题清单
        planning_result = task_planner_agent(
            questions=replan_questions,
            complexity="Simple"
        )
        # planning_result.needs_replan = False
    
    # 执行查询 → 统计检测 → 洞察分析
    results = execute_queries(planning_result.queries)
    stats = statistics_detector(results)
    insights = insight_agent(results, stats)
    
    # 重规划决策
    replan_decision = replanner_agent(
        insights=insights,
        round_num=round_num,
        max_rounds=max_rounds
    )
    
    if not replan_decision.should_replan:
        break  # 分析完整，结束
    
    if round_num >= max_rounds:
        break  # 达到最大轮数，强制结束
    
    # 继续下一轮
    replan_questions = replan_decision.new_questions
    round_num += 1

# 生成总结
final_report = summarizer_agent(all_insights)
```

**决策逻辑**：

```python
def replanner_agent(insights, round_num, max_rounds):
    # 1. 检查是否达到最大轮数
    if round_num >= max_rounds:
        return {
            "should_replan": False,
            "reasoning": "已达到最大重规划轮数限制",
            "max_rounds_reached": True
        }
    
    # 2. 评估分析完整性
    completeness = evaluate_completeness(insights)
    
    # 3. 检查是否有新的异常或未解答的问题
    has_new_anomalies = check_new_anomalies(insights)
    has_unanswered_questions = check_unanswered_questions(insights)
    
    # 4. 决策
    if completeness >= 0.8 and not has_new_anomalies:
        return {
            "should_replan": False,
            "reasoning": "分析已完整，无需继续"
        }
    
    if has_new_anomalies or has_unanswered_questions:
        return {
            "should_replan": True,
            "reasoning": "发现新异常或未解答问题，需要继续分析",
            "new_questions": generate_questions(insights)
        }
    
    return {
        "should_replan": False,
        "reasoning": "无明显需要继续分析的方向"
    }
```

**环境变量配置**：
- `MAX_REPLAN_ROUNDS`: 最大重规划轮数（默认3）
- `MIN_COMPLETENESS_SCORE`: 最小完整性分数阈值（默认0.8）
- `ENABLE_FORCED_STOP`: 是否启用强制停止（默认true）

**理由**：
- ✅ **灵活控制** - 可以根据需求调整最大轮数
- ✅ **避免无限循环** - 强制停止机制防止无限重规划
- ✅ **完整性保证** - 基于完整性评分决定是否继续
- ✅ **用户体验** - 多轮迭代提供更深入的分析

### 6. 为什么使用Pydantic模型而不是直接生成VizQL？

**决策**：使用Pydantic模型定义数据结构，参考tableau_sdk的类型定义

**理由**：
- ✅ **类型安全** - 编译时类型检查，减少运行时错误
- ✅ **自动验证** - Pydantic自动验证数据格式
- ✅ **IDE支持** - 完整的代码补全和类型提示
- ✅ **可维护性** - 类型定义集中管理，易于修改

**实现方式**：
```python
# 参考 tableau_sdk/apis/vizqlDataServiceApi.ts
# 创建对应的 Python Pydantic 模型

from pydantic import BaseModel
from typing import Literal, Optional, Union

class FieldBase(BaseModel):
    fieldCaption: str
    sortDirection: Optional[Literal["ASC", "DESC"]] = None
    sortPriority: Optional[int] = None

class FunctionField(FieldBase):
    function: Literal["SUM", "AVG", "COUNT", "MIN", "MAX"]

Field = Union[FieldBase, FunctionField]
```

### 7. 为什么使用临时viz而不是前端图表库？

**决策**：使用Tableau临时viz而不是Chart.js/ECharts等前端图表库

**理由**：
- ✅ **专业性** - Tableau的可视化能力远超前端图表库
- ✅ **一致性** - 与Tableau平台保持一致的视觉风格
- ✅ **交互性** - Tableau的交互能力（下钻、筛选、高亮）更强大
- ✅ **计算能力** - Tableau可以在viz中进行复杂计算

**权衡**：
- ⚠️ 需要创建临时工作簿（增加复杂度）
- ⚠️ 需要管理临时资源（自动清理）
- ✅ 但用户体验提升显著

---

## 数据流设计

### 主流程数据流

```
1. 用户输入问题
   ↓
2. (可选) 问题Boost Agent优化问题
   输入: 原始问题 + 元数据
   输出: 优化后的问题 + 建议
   ↓
3. 问题理解Agent
   输入: 问题
   输出: QuestionUnderstanding（包含sub_questions、complexity等）
   ↓
4. 任务规划Agent
   输入: QuestionUnderstanding + 元数据 + 维度层级
   输出: QueryPlanningResult（包含queries、needs_replan等）
   ↓
5. 查询构建器 + 查询执行器
   对每个Query:
     5.1 查询构建器: QuerySpec → VizQL JSON
     5.2 查询执行器: VizQL JSON → DataFrame
   ↓
6. 统计检测器
   输入: DataFrame
   输出: StatisticsReport（异常检测、趋势分析）
   ↓
7. 数据合并器（按需）
   输入: List[DataFrame]
   输出: MergedData（第0轮不合并，第1轮及以后按需合并）
   ↓
8. 洞察Agent
   输入: DataFrame + StatisticsReport
   输出: Insights（包含contribution_analysis、new_questions等）
   ↓
9. 重规划Agent
   输入: 原始问题 + Insights + 元数据
   输出: ReplanDecision（包含drill_down_target、new_questions等）
   ↓
10. 如果需要重规划 → 任务调度器 → 回到步骤4（处理重规划问题清单）
    否则 → 继续
    ↓
11. 总结Agent
    输入: 原始问题 + 所有Insights + 重规划历史
    输出: FinalReport
```

### 状态传递（LangGraph 1.0 更新）

**使用Runtime和Context简化状态**：

```python
from dataclasses import dataclass
from typing import TypedDict, Annotated, List, Dict, Any
from langgraph.runtime import Runtime
import operator

# 1. 定义Context（不可变的运行时上下文）
@dataclass
class VizQLContext:
    """运行时上下文 - 使用context_schema定义"""
    datasource_luid: str
    user_id: str
    session_id: str
    tableau_token: str
    max_replan: int = 2

# 2. 定义State（只包含核心数据）
class VizQLState(TypedDict):
    """LangGraph状态定义 - 精简版"""
    
    # 用户输入
    question: str
    
    # Agent输出
    understanding: Dict[str, Any]
    query_plan: Dict[str, Any]
    subtask_results: Annotated[List[Dict], operator.add]  # 自动累积
    insights: Annotated[List[Dict], operator.add]  # 自动累积
    replan_decision: Dict[str, Any]
    final_report: Dict[str, Any]
    
    # 控制流程
    replan_count: int
    current_stage: str

# 3. 节点函数签名（使用Runtime）
def query_planner_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext]  # ← 新增Runtime参数
) -> VizQLState:
    """查询规划Agent节点"""
    # 从context获取数据源信息（不需要在state中传递）
    datasource_luid = runtime.context.datasource_luid
    tableau_token = runtime.context.tableau_token
    
    # 从store获取缓存的元数据
    if runtime.store:
        metadata = runtime.store.get(("metadata",), datasource_luid)
    
    # 规划查询
    plan = plan_query(state["question"], metadata)
    
    return {"query_plan": plan}
```

**关键变更**：
- ✅ **Context替代State传递** - datasource_luid、user_id等移到Context
- ✅ **Store替代Redis** - 使用runtime.store访问缓存
- ✅ **Runtime统一接口** - 统一访问context、store、config
- ✅ **State精简** - 只保留核心数据，减少传递开销

---

## 关键技术选型

### 后端技术栈

| 技术 | 版本 | 用途 | 选择理由 |
|------|------|------|----------|
| **Python** | 3.11+ | 主要开发语言 | LangChain生态、类型提示、异步支持 |
| **FastAPI** | 0.104+ | Web框架 | 高性能、自动文档、类型安全 |
| **LangChain** | 1.0.3+ | LLM框架 | 丰富的工具链、社区活跃 |
| **LangGraph** | 1.0.2+ | 工作流编排 | Runtime、Store、astream_events |
| **Pydantic** | 2.5+ | 数据验证 | 类型安全、自动验证、JSON序列化 |
| **Redis** | 7.0+ | 缓存（部分） | 高性能、支持过期时间 |
| **Pandas** | 2.1+ | 数据处理 | 强大的数据分析能力 |
| **NumPy** | 1.26+ | 数值计算 | 统计分析、异常检测 |

**版本更新说明**：
- ✅ **LangChain 1.0.3** - 新增astream_events、bind_tools增强
- ✅ **LangGraph 1.0.2** - 新增Runtime、Store、context_schema
- ⚠️ **Redis** - 部分功能由Store替代（元数据缓存、用户偏好）

### 前端技术栈

| 技术 | 版本 | 用途 | 选择理由 |
|------|------|------|----------|
| **Vue 3** | 3.3+ | 前端框架 | Composition API、TypeScript支持 |
| **TypeScript** | 5.0+ | 类型系统 | 类型安全、IDE支持 |
| **Vite** | 5.0+ | 构建工具 | 快速开发、HMR |
| **Pinia** | 2.1+ | 状态管理 | 简洁、TypeScript友好 |
| **Tableau Embedding API** | v3 | Tableau嵌入 | 官方API、功能完整 |
| **Markdown-it** | 13.0+ | Markdown渲染 | 可扩展、插件丰富 |
| **Highlight.js** | 11.9+ | 代码高亮 | 支持多语言、主题丰富 |

### LLM选择

| 模型 | 上下文 | 用途 | 选择理由 |
|------|--------|------|----------|
| **Qwen3-32B-AWQ-Int4** | 40,960 | 主要模型 | 高性能、大上下文、本地部署 |
| **备选：GPT-4** | 128,000 | 备用模型 | 更强的推理能力 |

---

## 目录结构

```
experimental/
├── agents/                      # Agent实现
│   ├── dimension_hierarchy.py   # 维度层级推断Agent
│   ├── question_boost.py        # 问题Boost Agent
│   ├── understanding.py         # 问题理解Agent（拆分子问题）
│   ├── task_planner.py          # 任务规划Agent（智能规划查询策略）
│   ├── insight.py               # 洞察Agent（贡献度分析）
│   ├── replanner.py             # 重规划Agent（下钻维度查找）
│   └── summarizer.py            # 总结Agent
│
├── components/                  # 代码组件
│   ├── metadata_manager.py      # 元数据管理器
│   ├── query_builder.py         # 查询构建器
│   ├── query_executor.py        # 查询执行器
│   ├── statistics_detector.py   # 统计检测器
│   ├── data_merger.py           # 数据合并器
│   └── task_scheduler.py        # 任务调度器
│
├── models/                      # 数据模型
│   ├── state.py                 # LangGraph状态定义
│   ├── question.py              # 问题相关模型
│   ├── task.py                  # 任务相关模型
│   ├── vizql.py                 # VizQL查询模型（参考tableau_sdk）
│   └── result.py                # 结果相关模型
│
├── workflows/                   # LangGraph工作流
│   ├── main_workflow.py         # 主工作流
│   └── nodes.py                 # 节点定义
│
├── tools/                       # 工具和提示词
│   ├── prompts.py               # 所有提示词模板
│   └── utils.py                 # 工具函数
│
├── api/                         # FastAPI路由
│   ├── chat.py                  # 对话API
│   ├── boost.py                 # 问题Boost API
│   └── viz.py                   # 临时viz API
│
└── tests/                       # 测试
    ├── test_agents/
    ├── test_components/
    └── test_workflows/
```

---

## 接口设计概览

### REST API

| 端点 | 方法 | 功能 | 输入 | 输出 |
|------|------|------|------|------|
| `/api/chat` | POST | 对话查询 | 问题 + 数据源 | SSE流式输出 |
| `/api/boost-question` | POST | 问题优化 | 原始问题 | 优化后的问题 + 建议 |
| `/api/create-temp-viz` | POST | 创建临时viz | 查询结果 + viz类型 | viz URL |
| `/api/metadata/{luid}` | GET | 获取元数据 | 数据源ID | 元数据 + 维度层级 |

### 内部接口

详见 [API设计文档](./design-appendix/api-design.md)

---

## 性能设计

### 缓存策略（使用Store + Redis混合）

| 缓存类型 | 存储方式 | 有效期 | 缓存key | 用途 |
|---------|---------|--------|---------|------|
| 元数据 | **Store** | 1小时 | `("metadata",) + luid` | 减少Metadata API调用 |
| 维度层级 | **Store** | 24小时 | `("dimension_hierarchy",) + luid` | 减少LLM调用 |
| 用户偏好 | **Store** | 永久 | `("user_preferences",) + user_id` | 用户偏好学习 |
| 问题历史 | **Store** | 永久 | `("question_history", user_id) + timestamp` | 问题模式识别 |
| 异常知识库 | **Store** | 永久 | `("anomaly_knowledge",) + key` | 异常解释复用 |
| 查询结果 | Redis | 5分钟 | `query_result:{fingerprint}` | 减少VDS API调用 |

**存储选择说明**：
- ✅ **Store** - 适合需要语义搜索、跨会话持久化的数据
- ✅ **Redis** - 适合短期缓存、高频访问的数据

### 并发控制

- **同Stage并行** - 使用ThreadPoolExecutor，最多3个并发
- **洞察Agent并行** - 每个子任务的洞察Agent可并行调用
- **资源监控** - 监控CPU、内存、数据库连接数

### Token优化

- **元数据精简** - 只传递必要字段
- **数据采样** - 智能采样，最多30行
- **摘要传递** - 重规划Agent只接收摘要

详见 [技术规格 - 性能优化](./appendix/technical-specs.md#性能优化策略)

---

## 错误处理设计

### 错误分类

- **可重试错误** - 网络错误、超时、临时错误 → 指数退避重试
- **不可重试错误** - 认证错误、参数错误、业务错误 → 直接返回

### 降级策略

1. **查询降级** - 减少维度、使用采样数据
2. **缓存降级** - 使用过期缓存
3. **部分失败** - 部分任务失败不影响整体

详见 [技术规格 - 错误处理](./appendix/technical-specs.md#错误处理策略)

---

## 安全设计

### 认证授权

- **Tableau认证** - 使用JWT token访问Tableau API
- **API认证** - FastAPI的OAuth2认证
- **权限控制** - 基于Tableau的权限体系

### 数据安全

- **敏感信息** - 不在日志中记录敏感信息
- **临时viz** - 1小时后自动删除
- **缓存清理** - 定期清理过期缓存

---

## 监控设计

### 监控指标

- **系统指标** - CPU、内存、磁盘、网络
- **应用指标** - QPS、响应时间、错误率、缓存命中率
- **业务指标** - LLM调用次数、Token消耗、查询成功率、重规划率

### 告警规则

- **错误率 > 5%** - 警告
- **P95响应时间 > 30秒** - 警告
- **查询成功率 < 95%** - 警告

详见 [技术规格 - 监控和告警](./appendix/technical-specs.md#监控和告警)

---

---

## LangGraph 1.0 新特性应用

### 1. Runtime 类

**作用**：统一访问运行时上下文（context）、持久化存储（store）、配置（config）

**应用场景**：
- 传递数据源信息（datasource_luid, tableau_token）
- 访问用户信息（user_id, session_id）
- 控制重规划次数（max_replan）
- 访问Store存储

**示例**：
```python
def query_planner_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext]
) -> VizQLState:
    # 从context获取（类型安全）
    datasource_luid = runtime.context.datasource_luid
    
    # 从store获取缓存
    metadata = runtime.store.get(("metadata",), datasource_luid)
    
    return {"query_plan": ...}
```

### 2. Store 功能

**作用**：跨会话的持久化存储，支持向量搜索

**应用场景**：
- **维度层级缓存**（24小时）
- **用户偏好学习**（常用维度、度量、时间范围）
- **异常知识库**（已知异常及解释）
- **问题历史**（用户提问模式）

**示例**：
```python
# 保存用户偏好
runtime.store.put(
    namespace=("user_preferences",),
    key=user_id,
    value={"detail_level": "high", "preferred_viz": "bar"}
)

# 语义搜索历史问题
history = runtime.store.search(
    namespace=("question_history", user_id),
    query=question,
    limit=5
)
```

### 3. context_schema

**作用**：定义运行时上下文的schema，替代旧的config_schema

**应用场景**：
- 定义VizQLContext（datasource_luid, user_id, tableau_token等）
- 类型安全、不可变

**示例**：
```python
@dataclass
class VizQLContext:
    datasource_luid: str
    user_id: str
    tableau_token: str
    max_replan: int = 2

graph = StateGraph(
    state_schema=VizQLState,
    context_schema=VizQLContext  # ← 新参数
)
```

### 4. astream_events

**作用**：更强大的流式输出API，提供详细的事件信息

**应用场景**：
- **前端实时进度展示**（哪个Agent正在执行）
- **Token级流式渲染**（像ChatGPT一样）
- **调试和监控**（详细的执行日志）

**示例**：
```python
async for event in app.astream_events(input_data, version="v2"):
    if event["event"] == "on_chat_model_stream":
        # Token级流式输出
        token = event["data"]["chunk"].content
        yield token
    elif event["event"] == "on_chain_start":
        # Agent开始执行
        print(f"Agent: {event['name']}")
```

### 5. input/output_schema

**作用**：定义图的输入输出类型，自动验证

**应用场景**：
- API接口定义
- 自动验证输入输出

**示例**：
```python
class VizQLInput(TypedDict):
    question: str
    datasource_luid: str

class VizQLOutput(TypedDict):
    final_report: Dict[str, Any]

graph = StateGraph(
    state_schema=VizQLState,
    input_schema=VizQLInput,
    output_schema=VizQLOutput
)
```

### 迁移优先级

**P0（必须完成）**：
1. 引入Runtime和context_schema（1-2天）
2. 使用Store替代部分Redis缓存（2-3天）

**P1（强烈推荐）**：
3. 使用astream_events实现详细进度（2天）
4. 使用input/output_schema（1天）

**详细说明**：参见 [LangChain/LangGraph 1.0 新特性文档](../../../docs/LANGCHAIN_LANGGRAPH_1.0_NEW_FEATURES.md)

---

## 附录索引

- [Agent设计详解](./design-appendix/agent-design.md) - 7个Agent的详细设计
- [代码组件设计详解](./design-appendix/component-design.md) - 6个代码组件的详细设计
- [数据模型设计](./design-appendix/data-models.md) - 完整的数据模型定义
- [API设计](./design-appendix/api-design.md) - REST API和内部接口设计
- [前端架构设计](./design-appendix/frontend-design.md) - Vue 3前端架构
- [LangChain/LangGraph 1.0 新特性](../../../docs/LANGCHAIN_LANGGRAPH_1.0_NEW_FEATURES.md) - 新特性详解

---

**设计文档版本**: v1.1
**最后更新**: 2025-10-31
**文档状态**: 已更新（整合LangGraph 1.0新特性）
