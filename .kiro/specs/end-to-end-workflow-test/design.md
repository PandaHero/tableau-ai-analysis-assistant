# Design Document

## Overview

本设计文档描述了端到端集成测试脚本的架构和实现方案。该测试脚本将验证Tableau Assistant从用户问题输入到最终结果输出的完整工作流程，包括所有核心组件的集成测试。

测试脚本将使用真实的Tableau数据源和元数据，模拟实际的用户场景，确保各个组件能够正确协同工作。

## Architecture

### 整体架构

```
┌─────────────────────────────────────────────────────────────┐
│                    Test Orchestrator                         │
│                  (主测试协调器)                               │
└─────────────────────────────────────────────────────────────┘
                            │
                            ├─── Test Environment Setup
                            │    (环境初始化)
                            │
                            ├─── Test Case Executor
                            │    (测试用例执行器)
                            │
                            └─── Test Reporter
                                 (测试报告生成器)

┌─────────────────────────────────────────────────────────────┐
│                    Workflow Under Test                       │
│                  (被测试的工作流)                             │
└─────────────────────────────────────────────────────────────┘
                            │
        ┌───────────────────┼───────────────────┐
        │                   │                   │
   ┌────▼────┐        ┌────▼────┐        ┌────▼────┐
   │ Question│        │Question │        │Metadata │
   │  Boost  │───────▶│Under-   │───────▶│ Manager │
   │  Agent  │        │standing │        │         │
   └─────────┘        │  Agent  │        └─────────┘
                      └────┬────┘              │
                           │                   │
                      ┌────▼────┐              │
                      │  Task   │◀─────────────┘
                      │ Planner │
                      │  Agent  │
                      └────┬────┘
                           │
                      ┌────▼────┐
                      │  Query  │
                      │ Builder │
                      └────┬────┘
                           │
                      ┌────▼────┐
                      │  Query  │
                      │Executor │
                      └─────────┘
```

### 测试流程

测试脚本将按照以下顺序执行：

1. **环境初始化阶段**
   - 创建Runtime环境
   - 初始化Store Manager和Metadata Manager
   - 加载Tableau配置
   - 验证环境配置

2. **元数据准备阶段**
   - 获取真实数据源元数据
   - 测试元数据缓存功能
   - 获取增强元数据（维度层级、最大日期）

3. **问题处理阶段**（针对每个测试用例）
   - 问题Boost测试
   - 问题理解测试
   - 任务规划测试
   - 查询构建测试
   - 查询执行测试

4. **存储管理测试阶段**
   - 缓存读写测试
   - 缓存清除测试
   - 缓存过期测试

5. **报告生成阶段**
   - 汇总测试结果
   - 生成性能统计
   - 输出测试报告

## Components and Interfaces

### 1. TestOrchestrator（主测试协调器）

**职责：**
- 协调整个测试流程
- 管理测试用例的执行
- 收集和汇总测试结果

**接口：**
```python
class TestOrchestrator:
    def __init__(self):
        """初始化测试协调器"""
        
    async def run_all_tests(self) -> TestReport:
        """运行所有测试"""
        
    async def run_single_test(self, test_case: TestCase) -> TestResult:
        """运行单个测试用例"""
```

### 2. TestEnvironment（测试环境）

**职责：**
- 创建和配置Runtime环境
- 初始化所有必要的管理器
- 提供环境清理功能

**接口：**
```python
class TestEnvironment:
    def __init__(self):
        """初始化测试环境"""
        self.runtime: Optional[Runtime] = None
        self.store_manager: Optional[StoreManager] = None
        self.metadata_manager: Optional[MetadataManager] = None
        
    async def setup(self) -> bool:
        """设置测试环境"""
        
    async def teardown(self):
        """清理测试环境"""
        
    def get_runtime(self) -> Runtime:
        """获取Runtime实例"""
        
    def get_store_manager(self) -> StoreManager:
        """获取Store Manager实例"""
        
    def get_metadata_manager(self) -> MetadataManager:
        """获取Metadata Manager实例"""
```

### 3. TestCase（测试用例）

**职责：**
- 定义单个测试用例的数据
- 包含测试问题和期望结果

**数据结构：**
```python
@dataclass
class TestCase:
    name: str  # 测试用例名称
    description: str  # 测试用例描述
    question: str  # 测试问题
    expected_question_type: Optional[str]  # 期望的问题类型
    expected_dimensions: Optional[List[str]]  # 期望的维度
    expected_measures: Optional[List[str]]  # 期望的度量
    expected_time_range: Optional[Dict[str, Any]]  # 期望的时间范围
    complexity: str  # 复杂度（simple, medium, complex）
```

### 4. WorkflowTester（工作流测试器）

**职责：**
- 执行完整的工作流测试
- 调用各个Agent和组件
- 验证每个阶段的输出

**接口：**
```python
class WorkflowTester:
    def __init__(self, environment: TestEnvironment):
        """初始化工作流测试器"""
        
    async def test_question_boost(
        self, 
        question: str
    ) -> Tuple[QuestionBoost, TestStageResult]:
        """测试问题Boost Agent"""
        
    async def test_understanding(
        self, 
        question: str
    ) -> Tuple[QuestionUnderstanding, TestStageResult]:
        """测试问题理解Agent"""
        
    async def test_task_planning(
        self,
        understanding: QuestionUnderstanding,
        metadata: Metadata
    ) -> Tuple[QueryPlanningResult, TestStageResult]:
        """测试任务规划Agent"""
        
    async def test_query_building(
        self,
        query_plan: QueryPlanningResult,
        metadata: Metadata
    ) -> Tuple[List[VizQLQuery], TestStageResult]:
        """测试查询构建器"""
        
    async def test_query_execution(
        self,
        queries: List[VizQLQuery],
        datasource_luid: str
    ) -> Tuple[List[Dict[str, Any]], TestStageResult]:
        """测试查询执行器"""
```

### 5. MetadataTester（元数据测试器）

**职责：**
- 测试元数据管理功能
- 验证缓存机制
- 测试增强元数据功能

**接口：**
```python
class MetadataTester:
    def __init__(self, environment: TestEnvironment):
        """初始化元数据测试器"""
        
    async def test_metadata_fetch(self) -> TestStageResult:
        """测试元数据获取"""
        
    async def test_metadata_cache(self) -> TestStageResult:
        """测试元数据缓存"""
        
    async def test_enhanced_metadata(self) -> TestStageResult:
        """测试增强元数据"""
        
    async def test_dimension_hierarchy(self) -> TestStageResult:
        """测试维度层级"""
```

### 6. StoreTester（存储测试器）

**职责：**
- 测试Store Manager功能
- 验证缓存操作
- 测试数据持久化

**接口：**
```python
class StoreTester:
    def __init__(self, environment: TestEnvironment):
        """初始化存储测试器"""
        
    async def test_cache_write(self) -> TestStageResult:
        """测试缓存写入"""
        
    async def test_cache_read(self) -> TestStageResult:
        """测试缓存读取"""
        
    async def test_cache_clear(self) -> TestStageResult:
        """测试缓存清除"""
        
    async def test_cache_expiration(self) -> TestStageResult:
        """测试缓存过期"""
```

### 7. TestReporter（测试报告器）

**职责：**
- 格式化测试输出
- 生成测试报告
- 提供统计信息

**接口：**
```python
class TestReporter:
    def __init__(self):
        """初始化测试报告器"""
        
    def print_section(self, title: str):
        """打印分隔线和标题"""
        
    def print_stage_result(self, stage_name: str, result: TestStageResult):
        """打印阶段测试结果"""
        
    def print_test_summary(self, report: TestReport):
        """打印测试总结"""
        
    def format_duration(self, seconds: float) -> str:
        """格式化时间"""
        
    def format_data_sample(self, data: List[Dict], max_rows: int = 5) -> str:
        """格式化数据样本"""
```

## Data Models

### TestStageResult（阶段测试结果）

```python
@dataclass
class TestStageResult:
    stage_name: str  # 阶段名称
    success: bool  # 是否成功
    duration: float  # 执行时间（秒）
    output_data: Optional[Any]  # 输出数据
    error_message: Optional[str]  # 错误信息
    warnings: List[str]  # 警告信息
    metadata: Dict[str, Any]  # 额外的元数据（如token使用量）
```

### TestResult（测试用例结果）

```python
@dataclass
class TestResult:
    test_case: TestCase  # 测试用例
    success: bool  # 是否成功
    total_duration: float  # 总执行时间
    stage_results: List[TestStageResult]  # 各阶段结果
    error_message: Optional[str]  # 错误信息
    summary: Dict[str, Any]  # 测试摘要
```

### TestReport（测试报告）

```python
@dataclass
class TestReport:
    total_tests: int  # 总测试数
    passed_tests: int  # 通过的测试数
    failed_tests: int  # 失败的测试数
    total_duration: float  # 总执行时间
    test_results: List[TestResult]  # 所有测试结果
    environment_info: Dict[str, Any]  # 环境信息
    statistics: Dict[str, Any]  # 统计信息
```

## Error Handling

### 错误分类

1. **环境错误**
   - 缺少必要的环境变量
   - Tableau连接失败
   - 数据源不存在

2. **组件错误**
   - Agent执行失败
   - 查询构建失败
   - 查询执行失败

3. **验证错误**
   - 输出格式不正确
   - 缺少必要字段
   - 数据类型不匹配

### 错误处理策略

1. **环境错误**：立即终止测试，输出详细的诊断信息
2. **组件错误**：记录错误，继续执行其他测试用例
3. **验证错误**：标记测试失败，但继续执行

### 错误输出格式

```python
{
    "error_type": "component_error",
    "component": "question_boost_agent",
    "error_message": "Failed to parse JSON response",
    "original_error": "JSONDecodeError: ...",
    "timestamp": "2025-11-07T10:30:00",
    "context": {
        "question": "...",
        "response": "..."
    }
}
```

## Testing Strategy

### 测试用例设计

测试脚本将包含以下类型的测试用例：

1. **简单查询测试**
   - 单维度、单度量
   - 无筛选条件
   - 示例："显示各地区的销售额"

2. **时间序列测试**
   - 包含时间维度
   - 日期筛选
   - 示例："显示最近3个月的销售趋势"

3. **复杂聚合测试**
   - 多维度、多度量
   - 复杂筛选条件
   - 示例："显示各地区各产品类别的销售额和利润，筛选销售额大于10000的记录"

4. **排名分析测试**
   - 包含排序
   - Top N查询
   - 示例："显示销售额前10的产品"

5. **对比分析测试**
   - 同比、环比
   - 多时间段对比
   - 示例："对比今年和去年同期的销售额"

### 验证策略

每个测试阶段都将进行以下验证：

1. **输出存在性验证**：确保组件返回了输出
2. **输出格式验证**：确保输出符合预期的数据结构
3. **输出内容验证**：确保输出包含必要的字段和数据
4. **性能验证**：记录执行时间，识别性能瓶颈

### 性能监控

测试脚本将收集以下性能指标：

- 每个Agent的执行时间
- Token使用量（如果可用）
- 查询执行时间
- 总端到端执行时间
- 内存使用情况（可选）

## Implementation Details

### 文件结构

```
tableau_assistant/tests/
├── test_end_to_end_workflow.py  # 主测试脚本
├── test_helpers/
│   ├── __init__.py
│   ├── test_environment.py      # 测试环境管理
│   ├── test_cases.py            # 测试用例定义
│   ├── workflow_tester.py       # 工作流测试器
│   ├── metadata_tester.py       # 元数据测试器
│   ├── store_tester.py          # 存储测试器
│   └── test_reporter.py         # 测试报告器
```

### 主测试脚本结构

```python
#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
端到端工作流集成测试

测试完整的工作流程：
1. 问题Boost
2. 问题理解
3. 元数据管理
4. 任务规划
5. 查询构建
6. 查询执行
7. 存储管理
"""

# 1. 导入和环境设置
# 2. 定义测试用例
# 3. 创建测试环境
# 4. 执行元数据测试
# 5. 执行工作流测试
# 6. 执行存储测试
# 7. 生成测试报告

async def main():
    """主测试函数"""
    # 初始化
    reporter = TestReporter()
    environment = TestEnvironment()
    
    # 设置环境
    await environment.setup()
    
    # 执行测试
    orchestrator = TestOrchestrator(environment, reporter)
    report = await orchestrator.run_all_tests()
    
    # 输出报告
    reporter.print_test_summary(report)
    
    # 清理
    await environment.teardown()

if __name__ == "__main__":
    asyncio.run(main())
```

### 输出格式设计

测试输出将使用清晰的分隔线和符号：

```
================================================================================
  测试用例 1: 简单查询测试
================================================================================

问题: 显示各地区的销售额

--------------------------------------------------------------------------------
  阶段 1: 问题Boost
--------------------------------------------------------------------------------
✓ 成功
  - 执行时间: 1.23秒
  - Token使用: 150 tokens
  - 优化后问题: 显示所有地区的总销售额，按地区分组

--------------------------------------------------------------------------------
  阶段 2: 问题理解
--------------------------------------------------------------------------------
✓ 成功
  - 执行时间: 0.98秒
  - 问题类型: aggregation
  - 维度: [地区]
  - 度量: [销售额]
  - 时间范围: 无

[... 更多阶段 ...]

================================================================================
  测试总结
================================================================================
✓ 总测试数: 5
✓ 通过: 5
✗ 失败: 0
⏱ 总执行时间: 45.67秒
```

### 配置管理

测试脚本将从以下来源读取配置：

1. **环境变量**（.env文件）
   - DATASOURCE_LUID
   - TABLEAU_TOKEN
   - TABLEAU_SITE
   - TABLEAU_DOMAIN

2. **测试配置**（可选的配置文件）
   - 测试用例列表
   - 性能阈值
   - 输出详细级别

### 依赖关系

测试脚本依赖以下组件：

- LangGraph Runtime和Store
- 所有Agent（question_boost, understanding, task_planner）
- 所有组件（metadata_manager, store_manager, query_builder, query_executor）
- Tableau VDS API工具
- 现有的模型定义（state, context, metadata等）

## Extensibility

### 添加新测试用例

只需在测试用例列表中添加新的TestCase对象：

```python
TEST_CASES.append(TestCase(
    name="新测试用例",
    description="测试描述",
    question="测试问题",
    expected_question_type="aggregation",
    complexity="medium"
))
```

### 添加新的测试阶段

可以在WorkflowTester中添加新的测试方法：

```python
async def test_new_component(self, input_data) -> Tuple[Output, TestStageResult]:
    """测试新组件"""
    start_time = time.time()
    try:
        # 执行测试
        output = await new_component.process(input_data)
        
        # 验证输出
        assert output is not None
        
        return output, TestStageResult(
            stage_name="new_component",
            success=True,
            duration=time.time() - start_time,
            output_data=output
        )
    except Exception as e:
        return None, TestStageResult(
            stage_name="new_component",
            success=False,
            duration=time.time() - start_time,
            error_message=str(e)
        )
```

### 自定义报告格式

可以扩展TestReporter类以支持不同的输出格式：

```python
class JSONTestReporter(TestReporter):
    """JSON格式的测试报告器"""
    
    def print_test_summary(self, report: TestReport):
        """输出JSON格式的测试报告"""
        import json
        print(json.dumps(report, indent=2, ensure_ascii=False))
```

## Performance Considerations

### 优化策略

1. **并行执行**：不同测试用例可以并行执行（如果需要）
2. **缓存复用**：多个测试用例可以共享元数据缓存
3. **资源清理**：每个测试用例执行后清理临时数据
4. **超时控制**：为每个阶段设置合理的超时时间

### 性能基准

预期的性能指标：

- 问题Boost：< 2秒
- 问题理解：< 2秒
- 元数据获取（首次）：< 5秒
- 元数据获取（缓存）：< 0.1秒
- 任务规划：< 3秒
- 查询构建：< 0.5秒
- 查询执行：< 5秒（取决于数据量）
- 总端到端时间：< 20秒（单个测试用例）

## Security Considerations

### 敏感信息保护

1. **不在输出中显示完整的Token**
2. **不在日志中记录敏感的查询参数**
3. **使用环境变量管理凭证**
4. **测试数据不包含真实的业务敏感信息**

### 访问控制

1. **测试脚本只能访问测试环境的数据源**
2. **使用只读权限的Tableau Token**
3. **限制测试脚本的网络访问范围**

## Future Enhancements

### 可能的改进方向

1. **持续集成**：集成到CI/CD流程中
2. **性能回归测试**：跟踪性能变化趋势
3. **覆盖率报告**：生成代码覆盖率报告
4. **压力测试**：测试系统在高负载下的表现
5. **可视化报告**：生成HTML格式的测试报告
6. **自动化问题诊断**：当测试失败时自动分析原因
