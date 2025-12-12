# Design Document: Workflow E2E Testing

## Overview

本设计文档定义了 Tableau Assistant 工作流端到端测试的架构和实现方案。测试框架使用 pytest + pytest-asyncio 进行异步测试，使用 Hypothesis 进行属性测试，所有测试使用真实的 Tableau 环境和 LLM 服务。

### 设计目标

1. **完整流程覆盖**: 测试从用户问题到最终洞察的完整工作流
2. **真实环境验证**: 使用真实的 Tableau VizQL Data Service 和 LLM API
3. **渐进式分析验证**: 测试维度层级下钻和多轮重规划流程
4. **可维护性**: 测试代码结构清晰，易于扩展和维护

### 测试分类

| 类别 | 描述 | 测试方法 |
|------|------|----------|
| 属性测试 | 验证通用规则在所有输入上成立 | Hypothesis PBT |
| 集成测试 | 验证完整端到端流程 | pytest-asyncio |
| 性能测试 | 验证响应时间在可接受范围 | pytest-benchmark |

## Architecture

### 测试架构概述

测试框架分为三层：

```
┌─────────────────────────────────────────────────────────────────┐
│                        测试层 (Test Layer)                       │
│  ┌─────────────┐  ┌─────────────┐  ┌─────────────────────────┐  │
│  │ Test Cases  │  │  Fixtures   │  │    Test Utilities       │  │
│  │ (测试用例)   │  │ (测试夹具)   │  │ (断言工具、数据生成器)    │  │
│  └─────────────┘  └─────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                    工作流层 (Workflow Layer)                     │
│                                                                 │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                   WorkflowExecutor                        │  │
│  │  (工作流执行器 - 测试的主要入口点)                          │  │
│  └──────────────────────────────────────────────────────────┘  │
│                              │                                  │
│                              ▼                                  │
│  ┌──────────────────────────────────────────────────────────┐  │
│  │                    工作流节点链                            │  │
│  │                                                          │  │
│  │  Understanding → FieldMapper → QueryBuilder → Execute    │  │
│  │       │                                          │       │  │
│  │       │                                          ▼       │  │
│  │       │                                      Insight     │  │
│  │       │                                          │       │  │
│  │       │                                          ▼       │  │
│  │       └──────────── (重规划) ◄─────────────  Replanner   │  │
│  │                                                          │  │
│  └──────────────────────────────────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
                              │
                              ▼
┌─────────────────────────────────────────────────────────────────┐
│                   外部服务层 (External Services)                 │
│  ┌─────────────────────────┐  ┌─────────────────────────────┐  │
│  │   Tableau VizQL API     │  │      LLM Service            │  │
│  │   (真实 Tableau 环境)    │  │   (真实 LLM API)            │  │
│  └─────────────────────────┘  └─────────────────────────────┘  │
└─────────────────────────────────────────────────────────────────┘
```

### 完整工作流执行流程

```
用户问题
    │
    ▼
┌─────────────────┐
│  Understanding  │ ──► 问题分类 + 语义理解
│     Agent       │     输出: SemanticQuery, is_analysis_question
└────────┬────────┘
         │
         ▼ (如果 is_analysis_question=True)
┌─────────────────┐
│   FieldMapper   │ ──► RAG + LLM 字段映射
│      Node       │     输出: MappedQuery
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│  QueryBuilder   │ ──► VizQL 查询生成
│      Node       │     输出: VizQLQuery
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Execute      │ ──► 调用 Tableau VizQL API
│      Node       │     输出: QueryResult
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│    Insight      │ ──► 数据洞察分析
│     Agent       │     输出: insights
└────────┬────────┘
         │
         ▼
┌─────────────────┐
│   Replanner     │ ──► 评估完成度，决定是否重规划
│     Agent       │     输出: ReplanDecision
└────────┬────────┘
         │
         ├──► should_replan=True → 回到 Understanding (新问题)
         │
         └──► should_replan=False → END (返回最终结果)
```

### 测试覆盖范围

| 测试类型 | 覆盖节点 | 验证内容 |
|----------|----------|----------|
| 简单聚合测试 | 全流程 | SUM/AVG/COUNT 聚合正确执行 |
| LOD 测试 | Understanding → QueryBuilder | LOD 识别和表达式生成 |
| 表计算测试 | Understanding → QueryBuilder | 表计算识别和表达式生成 |
| 日期筛选测试 | Understanding | 绝对/相对日期筛选识别 |
| 路由测试 | Understanding → END | 非分析类问题正确路由 |
| 重规划测试 | Insight → Replanner → Understanding | 多轮分析循环 |
| 下钻测试 | 全流程多轮 | 维度层级下钻完整流程 |
| 流式测试 | 全流程 | 事件流正确性 |
| 错误处理测试 | 各节点 | 异常情况优雅降级 |

## Components and Interfaces

### 1. Test Fixtures

```python
@pytest.fixture(scope="module")
def executor() -> WorkflowExecutor:
    """创建工作流执行器实例"""
    return WorkflowExecutor(max_replan_rounds=3)

@pytest.fixture(scope="module")
def printer() -> WorkflowPrinter:
    """创建打印器实例 - 用于显示真实测试输出"""
    return WorkflowPrinter(verbose=True, show_tokens=True)

@pytest.fixture(scope="module")
def settings() -> Settings:
    """加载配置"""
    return Settings()

@pytest.fixture
def check_env(settings: Settings):
    """检查环境配置"""
    required = ["TABLEAU_DOMAIN", "LLM_API_KEY", "DATASOURCE_LUID"]
    missing = [k for k in required if not getattr(settings, k.lower(), None)]
    if missing:
        pytest.skip(f"缺少环境配置: {', '.join(missing)}")
```

### 2. Test Utilities

```python
class TestDataGenerator:
    """测试数据生成器"""
    
    @staticmethod
    def generate_aggregation_question(
        dimension: str,
        measure: str,
        agg_type: str = "SUM"
    ) -> str:
        """生成聚合问题"""
        pass
    
    @staticmethod
    def generate_date_filter_question(
        filter_type: str,  # absolute, relative
        date_range: Dict[str, Any]
    ) -> str:
        """生成日期筛选问题"""
        pass

class WorkflowAssertions:
    """工作流断言工具"""
    
    @staticmethod
    def assert_semantic_query_valid(result: WorkflowResult):
        """验证 SemanticQuery 有效"""
        pass
    
    @staticmethod
    def assert_query_result_valid(result: WorkflowResult):
        """验证 QueryResult 有效"""
        pass
    
    @staticmethod
    def assert_insights_generated(result: WorkflowResult):
        """验证洞察已生成"""
        pass
```

### 3. Test Case Structure

测试用例需要同时支持：
1. **真实输出打印** - 使用 `WorkflowPrinter` 显示详细的执行过程和结果
2. **断言验证** - 使用 pytest assert 验证测试是否通过

```python
class TestSimpleAggregation:
    """简单聚合测试"""
    
    @pytest.mark.asyncio
    async def test_sum_aggregation(self, executor, printer, check_env):
        """SUM 聚合测试"""
        # 执行工作流
        result = await executor.run("各地区销售额是多少")
        
        # 打印真实结果（详细输出）
        printer.print_result(result)
        
        # 断言验证
        assert result.success, f"执行失败: {result.error}"
        assert result.semantic_query is not None
        assert result.query_result is not None
    
    @pytest.mark.asyncio
    async def test_sum_aggregation_streaming(self, executor, printer, check_env):
        """SUM 聚合测试（流式输出）"""
        # 流式执行，实时打印 token 和节点状态
        async for event in executor.stream("各地区销售额是多少"):
            printer.print_event(event)

class TestFullWorkflowCycle:
    """完整工作流循环测试"""
    
    @pytest.mark.asyncio
    async def test_dimension_drilldown_cycle(self, executor, printer, check_env):
        """维度下钻循环测试"""
        # 流式执行，显示完整的多轮分析过程
        async for event in executor.stream("分析各地区销售情况"):
            printer.print_event(event)
        
        # 也可以用 run() 获取最终结果进行断言
        result = await executor.run("分析各地区销售情况")
        printer.print_result(result)
        
        # 断言验证
        assert result.success
        assert result.replan_count >= 0
        assert len(result.insights) > 0
```

### 4. WorkflowPrinter 输出示例

```
▶ [understanding] 开始执行...
  正在分析问题: 各地区销售额是多少
  识别到度量: 销售额
  识别到维度: 地区
✓ [understanding] 完成
  ├─ measures: ['销售额']
  ├─ dimensions: ['地区']
  ├─ filters: 0 个
  └─ analyses: 1 个

▶ [field_mapper] 开始执行...
✓ [field_mapper] 完成
  ├─ field_mappings: 2 个
  │  1. 销售额 → Sales
  │  2. 地区 → Region

▶ [query_builder] 开始执行...
✓ [query_builder] 完成
  ├─ fields: 2 个
  └─ filters: 0 个

▶ [execute] 开始执行...
✓ [execute] 完成
  ├─ rows: 4 行
  │  {'Region': '华东', 'Sales': 1234567.89}
  │  {'Region': '华北', 'Sales': 987654.32}
  │  {'Region': '华南', 'Sales': 876543.21}
  │  ... 还有 1 行

▶ [insight] 开始执行...
✓ [insight] 完成

▶ [replanner] 开始执行...
✓ [replanner] 完成
  ├─ should_replan: False
  ├─ completeness_score: 0.92
  └─ reason: 分析已完成，覆盖了主要地区...

✓ 工作流完成

============================================================
执行结果
============================================================
状态: 成功
耗时: 12.34s
重规划次数: 0
```

## Data Models

### Test Result Model

```python
@dataclass
class E2ETestResult:
    """端到端测试结果"""
    test_name: str
    question: str
    success: bool
    duration: float
    
    # 各阶段输出
    semantic_query: Optional[SemanticQuery]
    mapped_query: Optional[MappedQuery]
    vizql_query: Optional[VizQLQuery]
    query_result: Optional[QueryResult]
    insights: List[InsightResult]
    replan_decision: Optional[ReplanDecision]
    
    # 验证结果
    assertions_passed: List[str]
    assertions_failed: List[str]
    
    # 性能指标
    node_timings: Dict[str, float]
```

### Test Configuration Model

```python
@dataclass
class E2ETestConfig:
    """端到端测试配置"""
    max_replan_rounds: int = 3
    timeout_seconds: int = 120
    enable_streaming: bool = False
    
    # 环境配置
    tableau_domain: str = ""
    datasource_luid: str = ""
    llm_api_key: str = ""
```

## Correctness Properties

*A property is a characteristic or behavior that should hold true across all valid executions of a system-essentially, a formal statement about what the system should do. Properties serve as the bridge between human-readable specifications and machine-verifiable correctness guarantees.*

基于 prework 分析，以下是需要验证的正确性属性：

### Property 1: 简单聚合查询成功执行
*For any* 包含维度和度量的简单聚合问题，WorkflowExecutor.run() 应返回 success=True 且 semantic_query 非空
**Validates: Requirements 1.1, 1.2**

### Property 2: 聚合类型正确识别
*For any* 包含聚合关键词（平均、总计、数量）的问题，Understanding Agent 应正确识别聚合类型（AVG、SUM、COUNT）
**Validates: Requirements 1.4, 1.5**

### Property 3: COUNTD 聚合识别
*For any* 包含"不同"、"去重"关键词的计数问题，Understanding Agent 应识别为 COUNTD 聚合类型
**Validates: Requirements 2.1, 2.2**

### Property 4: LOD 表达式识别
*For any* 需要跨粒度计算的问题，Understanding Agent 应识别 LOD 需求并在 SemanticQuery 中设置正确的 lod_type
**Validates: Requirements 3.1, 19.1, 19.2, 20.1, 21.1**

### Property 5: 表计算识别
*For any* 包含累计、排名、移动平均关键词的问题，Understanding Agent 应识别表计算类型
**Validates: Requirements 4.1, 4.2, 22.1, 23.1, 24.1**

### Property 6: 绝对日期筛选识别
*For any* 包含具体年份、月份或日期范围的问题，Understanding Agent 应生成包含正确日期筛选的 SemanticQuery
**Validates: Requirements 5.1, 5.2, 5.3**

### Property 7: 相对日期筛选识别
*For any* 包含相对日期关键词（本月、上月、最近N月、YTD）的问题，Understanding Agent 应生成包含相对日期筛选的 SemanticQuery
**Validates: Requirements 6.1, 6.2, 6.3, 6.4**

### Property 8: 多维度多度量识别
*For any* 包含多个维度或多个度量的问题，Understanding Agent 应生成包含所有维度和度量的 SemanticQuery
**Validates: Requirements 7.1, 7.2**

### Property 9: 非分析类问题路由
*For any* 非分析类问题（问候语、帮助请求），Understanding Agent 应设置 is_analysis_question=False，工作流应直接路由到 END
**Validates: Requirements 8.1, 8.2, 8.3**

### Property 10: 重规划决策正确性
*For any* Insight Agent 输出，Replanner Agent 应返回包含 completeness_score 的 ReplanDecision
**Validates: Requirements 9.1**

### Property 11: 重规划路由正确性
*For any* ReplanDecision，当 should_replan=True 且 replan_count < max_rounds 时应路由到 Understanding，否则应路由到 END
**Validates: Requirements 9.2, 9.3, 9.4, 9.5**

### Property 12: 流式执行事件完整性
*For any* 流式执行，事件流应包含 NODE_START、NODE_COMPLETE 和 COMPLETE 事件
**Validates: Requirements 10.1, 10.2, 10.4**

### Property 13: 错误处理正确性
*For any* 执行错误，WorkflowResult 应设置 success=False 并包含错误详情
**Validates: Requirements 11.1, 11.2, 11.3**

### Property 14: 洞察生成正确性
*For any* 非空 QueryResult，Insight Agent 应生成至少一条洞察
**Validates: Requirements 1.3, 11.4**

### Property 15: 洞察累积正确性
*For any* 多轮分析，all_insights 应累积所有轮次的洞察且无重复
**Validates: Requirements 15.4, 31.1, 31.2**

### Property 16: SQLite Checkpointer 持久化
*For any* 使用 SQLite checkpointer 的工作流执行，数据库文件应被创建且状态应被保存
**Validates: Requirements 13.1, 13.2**

### Property 17: 性能基准
*For any* 简单聚合查询，执行时间应小于 30 秒
**Validates: Requirements 14.1**

### Property 18: 维度下钻决策正确性
*For any* Replanner 基于维度层级的下钻决策，exploration_questions 应包含基于维度层级的下钻建议
**Validates: Requirements 12.2, 16.2, 17.2, 18.2**

## Error Handling

### 错误分类

| 错误类型 | 处理策略 | 测试验证 |
|----------|----------|----------|
| 环境配置缺失 | pytest.skip() | 检查必要环境变量 |
| LLM API 错误 | 记录错误，标记测试失败 | 验证 errors 列表 |
| VizQL API 错误 | 记录错误，验证错误处理 | 验证 QueryResult.error |
| 超时错误 | pytest.timeout | 验证执行时间 |

### 错误恢复

```python
@pytest.fixture
def error_handler():
    """错误处理 fixture"""
    def handle_error(result: WorkflowResult, expected_error: str = None):
        if not result.success:
            if expected_error and expected_error in str(result.error):
                return True  # 预期错误
            pytest.fail(f"Unexpected error: {result.error}")
        return True
    return handle_error
```

## Testing Strategy

### 双重测试方法

本测试框架采用单元测试和属性测试相结合的方法：

1. **单元测试 (pytest-asyncio)**
   - 验证特定示例的正确行为
   - 测试边界条件和错误情况
   - 验证完整端到端流程

2. **属性测试 (Hypothesis)**
   - 验证通用属性在所有输入上成立
   - 自动生成测试用例
   - 发现边界情况

### 属性测试框架

使用 Hypothesis 库进行属性测试：

```python
from hypothesis import given, strategies as st, settings

# 配置每个属性测试运行 100 次迭代
@settings(max_examples=100)
@given(st.text(min_size=1, max_size=100))
def test_property_example(input_text):
    # 属性测试逻辑
    pass
```

### 测试标注格式

每个属性测试必须包含以下注释：
```python
# **Feature: workflow-e2e-testing, Property {number}: {property_text}**
# **Validates: Requirements X.Y**
```

### 测试组织结构

```
tableau_assistant/tests/integration/
├── test_e2e_simple_aggregation.py      # 简单聚合测试
├── test_e2e_countd.py                  # COUNTD 测试
├── test_e2e_lod.py                     # LOD 表达式测试
├── test_e2e_table_calc.py              # 表计算测试
├── test_e2e_date_filter.py             # 日期筛选测试
├── test_e2e_multi_dimension.py         # 多维度测试
├── test_e2e_routing.py                 # 路由测试
├── test_e2e_replanning.py              # 重规划测试
├── test_e2e_streaming.py               # 流式执行测试
├── test_e2e_error_handling.py          # 错误处理测试
├── test_e2e_full_cycle.py              # 完整循环测试
├── test_e2e_dimension_drilldown.py     # 维度下钻测试
├── test_e2e_persistence.py             # 持久化测试
├── test_e2e_performance.py             # 性能测试
└── conftest.py                         # 共享 fixtures
```

### 测试执行命令

```bash
# 运行所有端到端测试
pytest tableau_assistant/tests/integration/test_e2e_*.py -v

# 运行特定测试类
pytest tableau_assistant/tests/integration/test_e2e_full_cycle.py -v

# 运行属性测试
pytest tableau_assistant/tests/integration/ -v -k "property"

# 运行性能测试
pytest tableau_assistant/tests/integration/test_e2e_performance.py -v --benchmark
```
