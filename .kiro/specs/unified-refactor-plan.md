# Tableau Assistant 统一重构方案

## 文档说明

本文档整合了 `deepagents-refactor` 和 `vizql-api-migration` 两个项目的需求，基于对以下内容的深入分析：

- ✅ DeepAgents 框架源码和文档
- ✅ VizQL Data Service API 规范和 Python SDK
- ✅ 当前系统架构和实现
- ✅ 两个项目的需求、设计和任务文档

**创建时间**: 2025-01-15
**文档版本**: v1.0

---

## 执行摘要

### 核心问题

当前系统面临两个独立但相关的升级需求：

1. **架构升级**：从手动编排的LangGraph迁移到DeepAgents框架
2. **API升级**：从旧版VizQL API升级到Tableau 2025.1+的新版API

### 统一方案

**不采用分阶段迁移，而是一次性完成两个升级**，原因：

1. 两个升级都涉及核心架构变更
2. 分阶段会导致重复工作和技术债务
3. 统一升级可以更好地利用新API的表计算能力简化DeepAgents架构

### 预期收益

- **性能提升**: 30-50%（利用表计算减少多轮查询）
- **代码简化**: 20-30%（移除复杂的问题拆分逻辑）
- **维护成本**: 降低40%（统一框架，减少自定义代码）
- **功能增强**: 支持表计算等高级分析

---

## 1. 现状分析

### 1.1 当前架构

```
┌─────────────────────────────────────────┐
│         FastAPI 入口层                   │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│      LangGraph StateGraph (手动编排)     │
│  - 5个Agent节点                          │
│  - 手动流程控制                          │
│  - 自定义中间件                          │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│         旧版 VizQL API                   │
│  - 不支持表计算                          │
│  - 需要多轮查询                          │
└─────────────────────────────────────────┘
```

### 1.2 核心组件（100%复用）

以下组件已验证可以100%复用：

| 组件 | 路径 | 复用方式 |
|------|------|---------|
| **MetadataManager** | `src/components/metadata_manager.py` | 封装为DeepAgents工具 |
| **QueryExecutor** | `src/components/query_executor.py` | 封装为DeepAgents工具 |
| **QueryBuilder** | `src/components/query_builder/` | 封装为DeepAgents工具 |
| **DataProcessor** | `src/components/data_processor/` | 封装为DeepAgents工具 |
| **所有Pydantic模型** | `src/models/` | 完整保留，作为内部模型 |
| **所有Prompt类** | `prompts/` | 完整保留，4段式结构 |
| **配置管理** | `src/config/settings.py` | 扩展以支持新配置 |

### 1.3 主要问题

1. **API限制**：旧版API不支持表计算，导致复杂的问题拆分
2. **手动编排**：缺少DeepAgents的内置优化（缓存、文件系统、自动总结）
3. **维护复杂**：大量自定义代码，难以维护
4. **性能瓶颈**：多轮查询导致延迟高

---

## 2. 目标架构

### 2.1 整体架构

```
┌─────────────────────────────────────────┐
│         FastAPI 入口层                   │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│      DeepAgents 主Agent                  │
│  - 内置Middleware（7个）                 │
│  - 自定义Middleware（3个）               │
│  - 不使用SubAgentMiddleware             │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│      LangGraph StateGraph (精确控制)     │
│  - 5个Agent节点                          │
│  - 条件路由（可选Boost）                 │
│  - 重规划循环                            │
└─────────────────────────────────────────┘
                  ↓
┌─────────────────────────────────────────┐
│      新版 VizQL Data Service API         │
│  - 支持表计算                            │
│  - 官方Python SDK                        │
│  - 单查询完成复杂分析                    │
└─────────────────────────────────────────┘
```

### 2.2 关键设计决策

#### 决策1：混合架构

**使用DeepAgents基础功能 + StateGraph流程控制**

- ✅ 使用 `create_deep_agent()` 获得内置middleware
- ✅ 使用 StateGraph 保持精确的流程控制
- ❌ **不使用** SubAgentMiddleware（因为需要固定流程）

**理由**：
- 业务需求固定流程：Boost → Understanding → Planning → Execute → Insight → Replanner
- SubAgentMiddleware会让主Agent自主决定调用哪个子代理，失去控制
- StateGraph提供精确的条件路由和循环控制

#### 决策2：一次性升级

**同时完成DeepAgents迁移和VizQL API升级**

**理由**：
- 两个升级都涉及核心架构
- 新API的表计算能力可以简化DeepAgents架构
- 避免重复工作和技术债务

#### 决策3：100%复用现有组件

**所有核心业务组件保持不变，只封装为工具**

**理由**：
- 降低风险，不重写已验证的业务逻辑
- 保护投资，保留所有开发成果
- 快速迁移，只需封装接口

---

## 3. 详细设计

### 3.1 DeepAgents集成

#### 3.1.1 主Agent创建

```python
from deepagents import create_deep_agent
from tableau_assistant.src.tools.vizql_tools import create_vizql_tools

# 创建主Agent
main_agent = create_deep_agent(
    model="claude-sonnet-4",
    tools=create_vizql_tools(),  # 8个VizQL工具
    subagents=[],  # 不使用SubAgentMiddleware
    store=PersistentStore(db_path="data/deepagents_store.db"),
    # 自动获得7个内置middleware：
    # - TodoListMiddleware
    # - FilesystemMiddleware
    # - SummarizationMiddleware
    # - AnthropicPromptCachingMiddleware
    # - PatchToolCallsMiddleware
    # - (不使用SubAgentMiddleware)
    # - (不使用HumanInTheLoopMiddleware)
)
```

#### 3.1.2 工具集设计（8个工具）

基于现有组件封装：

| 工具名 | 封装组件 | 功能 |
|--------|---------|------|
| `get_metadata` | MetadataManager | 获取元数据（使用新SDK） |
| `parse_date` | DateParser | 解析日期 |
| `build_vizql_query` | QueryBuilder | 构建查询（支持表计算） |
| `execute_vizql_query` | QueryExecutor | 执行查询（使用新SDK） |
| `semantic_map_fields` | SemanticMapper | 语义字段映射（RAG+LLM） |
| `process_query_result` | DataProcessor | 处理查询结果 |
| `detect_statistics` | StatisticsDetector | 统计检测 |
| `save_large_result` | FilesystemMiddleware | 保存大结果 |

#### 3.1.3 自定义Middleware（3个）

| Middleware | 功能 | 注入工具 |
|-----------|------|---------|
| `TableauMetadataMiddleware` | 元数据管理 | get_metadata |
| `VizQLQueryMiddleware` | 查询执行 | execute_vizql_query |
| `ApplicationLevelCacheMiddleware` | 应用层缓存 | 无（钩子） |

### 3.2 StateGraph流程设计

```python
from langgraph.graph import StateGraph, START, END

def create_vizql_workflow():
    graph = StateGraph(VizQLState)
    
    # 添加5个Agent节点
    graph.add_node("boost", boost_agent_node)
    graph.add_node("understanding", understanding_agent_node)
    graph.add_node("planning", planning_agent_node)
    graph.add_node("execute", execute_query_node)
    graph.add_node("insight", insight_agent_node)
    graph.add_node("replanner", replanner_agent_node)
    
    # 条件路由：Boost是可选的
    def route_start(state):
        return "boost" if state.get("boost_question") else "understanding"
    
    graph.add_conditional_edges(START, route_start, {
        "boost": "boost",
        "understanding": "understanding"
    })
    
    # 主流程
    graph.add_edge("boost", "understanding")
    graph.add_edge("understanding", "planning")
    graph.add_edge("planning", "execute")
    graph.add_edge("execute", "insight")
    graph.add_edge("insight", "replanner")
    
    # 重规划循环
    def should_replan(state):
        if state.get("replan_decision", {}).get("should_replan"):
            return "understanding"  # 跳过Boost
        return END
    
    graph.add_conditional_edges("replanner", should_replan, {
        "understanding": "understanding",
        END: END
    })
    
    return graph.compile(
        checkpointer=InMemorySaver(),
        store=PersistentStore(db_path="data/langgraph_store.db")
    )
```

### 3.3 VizQL API升级

#### 3.3.1 新版SDK集成

```python
from vizql_data_service_py import (
    VizQLDataServiceClient,
    QueryRequest,
    ReadMetadataRequest,
    Datasource,
    Query,
    query_datasource,
    read_metadata
)
import tableauserverclient as TSC

class VizQLClient:
    """封装官方SDK"""
    
    def __init__(self, server_url, auth, verify_ssl=True):
        self.server = TSC.Server(server_url)
        self.client = VizQLDataServiceClient(
            server_url=server_url,
            server=self.server,
            tableau_auth=auth,
            verify_ssl=verify_ssl
        )
    
    def query_sync(self, datasource_luid, query):
        """同步查询（支持表计算）"""
        request = QueryRequest(
            datasource=Datasource(datasourceLuid=datasource_luid),
            query=query
        )
        with self.server.auth.sign_in(self.auth):
            return query_datasource.sync(client=self.client, body=request)
```

#### 3.3.2 表计算支持

新版API支持10种表计算类型：

1. **CUSTOM** - 自定义表计算
2. **NESTED** - 嵌套表计算
3. **DIFFERENCE_FROM** - 差异计算
4. **PERCENT_DIFFERENCE_FROM** - 百分比差异
5. **PERCENT_FROM** - 百分比
6. **PERCENT_OF_TOTAL** - 占总数百分比
7. **RANK** - 排名
8. **PERCENTILE** - 百分位数
9. **RUNNING_TOTAL** - 累计总计
10. **MOVING_CALCULATION** - 移动计算

**关键优势**：单个查询可以完成复杂分析，不再需要多轮查询和手动计算。

### 3.4 Agent重构

#### 3.4.1 Understanding Agent

**旧版**：拆分技术性子问题
```python
class QuestionUnderstanding:
    sub_questions: List[SubQuestion]  # 技术性拆分
    dependencies: List[Dependency]
```

**新版**：识别表计算类型
```python
class QuestionUnderstanding:
    question_type: str  # comparison, trend, ranking
    dimensions: List[str]
    measures: List[str]
    table_calc_type: Optional[str]  # 需要的表计算类型
    filters: List[Filter]
```

#### 3.4.2 Planning Agent

**旧版**：生成多个子查询
```python
class QueryPlan:
    subtasks: List[QuerySubTask]  # 多个子查询
    execution_strategy: str  # sequential, parallel
```

**新版**：生成单个查询（包含表计算）
```python
class QueryPlan:
    query: Query  # 单个查询
    table_calc_fields: List[TableCalcField]
    field_mappings: Dict[str, str]  # RAG映射结果
```

#### 3.4.3 其他Agent

- **Boost Agent**: 保持不变
- **Insight Agent**: 保持不变
- **Replanner Agent**: 保持不变（仍支持多轮分析）

---

## 4. 实施计划

### 4.1 阶段划分

| 阶段 | 任务 | 预计时间 |
|------|------|---------|
| **阶段1** | 基础设施准备 | 2天 |
| **阶段2** | 工具层实现（8个工具） | 5.5天 |
| **阶段3** | 中间件实现（3个） | 2天 |
| **阶段4** | VizQL SDK集成 | 3天 |
| **阶段5** | 表计算支持 | 4天 |
| **阶段6** | Agent重构（5个） | 7天 |
| **阶段7** | StateGraph集成 | 3天 |
| **阶段8** | 测试和优化 | 5天 |
| **阶段9** | 文档和部署 | 2天 |
| **总计** | | **33.5天（约7周）** |

### 4.2 详细任务（参考现有tasks.md）

详细任务列表请参考：
- `.kiro/specs/deepagents-refactor/tasks.md`
- `.kiro/specs/vizql-api-migration/tasks.md`

**关键整合点**：
1. 阶段2-3：实现DeepAgents工具和中间件
2. 阶段4-5：集成新版VizQL SDK和表计算
3. 阶段6-7：重构Agent并集成到StateGraph

---

## 5. 风险和缓解

### 5.1 技术风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| DeepAgents学习曲线 | 中 | 先完成简单Agent，逐步熟悉 |
| 新API稳定性 | 高 | 与Tableau团队保持沟通 |
| 表计算功能限制 | 中 | 保留部分手动计算作为备选 |
| 性能下降 | 高 | 每阶段进行性能基准测试 |

### 5.2 业务风险

| 风险 | 影响 | 缓解措施 |
|------|------|---------|
| 功能回归 | 高 | 详细测试用例，覆盖所有功能 |
| 用户体验变化 | 中 | 保持API接口不变 |
| 迁移时间过长 | 中 | 严格按照计划执行 |

---

## 6. 成功标准

### 6.1 技术指标

- ✅ 查询响应时间减少 30%
- ✅ 代码行数减少 20%
- ✅ 测试覆盖率 ≥ 80%
- ✅ 系统可用性 ≥ 99.5%

### 6.2 业务指标

- ✅ 用户满意度 ≥ 4.5/5
- ✅ 查询成功率 ≥ 95%
- ✅ 支持表计算类型 ≥ 7种

---

## 7. 参考文档

### 7.1 需求和设计

- [DeepAgents重构需求](.kiro/specs/deepagents-refactor/requirements.md)
- [DeepAgents重构设计](.kiro/specs/deepagents-refactor/design.md)
- [VizQL API迁移需求](.kiro/specs/vizql-api-migration/requirements.md)
- [VizQL API迁移设计](.kiro/specs/vizql-api-migration/design.md)

### 7.2 任务列表

- [DeepAgents重构任务](.kiro/specs/deepagents-refactor/tasks.md)
- [VizQL API迁移任务](.kiro/specs/vizql-api-migration/tasks.md)

### 7.3 外部文档

- [DeepAgents官方文档](https://docs.langchain.com/oss/python/deepagents/overview)
- [VizQL Data Service API文档](https://help.tableau.com/current/api/vizql-data-service/en-us/index.html)
- [vizql-data-service-py SDK](https://github.com/tableau/VizQL-Data-Service/tree/main/python_sdk)

---

## 8. 总结

本方案整合了DeepAgents框架迁移和VizQL API升级两个项目，采用一次性升级策略，预计7周完成。

**核心优势**：
1. 利用DeepAgents内置功能，减少自定义代码
2. 利用新API表计算能力，简化查询逻辑
3. 100%复用现有组件，降低风险
4. 保持固定流程控制，满足业务需求

**下一步**：
1. 审查本方案，确认技术可行性
2. 开始阶段1：基础设施准备
3. 按计划逐步执行各阶段任务

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**状态**: 待审查
