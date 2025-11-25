# MVP闭环实现计划

## 进度跟踪

### ✅ 已完成（3/7）
1. 查询规划Agent（支持动态规划）
2. 查询构建器（MVP版本）
3. 查询执行器（MVP版本）
4. 数据合并器（MVP版本）

### 🔄 下一步
5. 洞察Agent（基础版）- 1小时
6. 重规划Agent - 1.5小时
7. 端到端测试 - 30分钟

**预计剩余时间**：3小时

## 详细实现计划

### 组件3：查询执行器（30分钟）

**文件**：`tableau_assistant/src/components/query_executor.py`

**功能**：
- 调用Tableau VDS API执行查询
- 解析返回结果
- 基础错误处理

**MVP限制**：
- 暂不支持自动重试
- 暂不支持分页
- 暂不支持超时控制

**接口**：
```python
class QueryExecutor:
    def execute_query(
        self,
        query: VizQLQuery,
        datasource_luid: str,
        tableau_config: Dict
    ) -> Dict:
        """执行查询并返回结果"""
        pass
```

### 组件4：数据合并器（30分钟）

**文件**：`tableau_assistant/src/components/data_merger.py`

**功能**：
- 合并多个子任务的结果
- 简单拼接策略

**MVP限制**：
- 暂不支持复杂合并策略
- 暂不支持数据对齐
- 暂不支持去重

**接口**：
```python
class DataMerger:
    def merge_results(
        self,
        subtask_results: List[Dict]
    ) -> Dict:
        """合并多个子任务结果"""
        pass
```

### 组件5：洞察Agent（1小时）

**文件**：`tableau_assistant/src/agents/insight_agent.py`

**功能**：
- 分析查询结果
- 生成基础洞察
- 描述性统计

**MVP限制**：
- 暂不支持贡献度分析
- 暂不支持异常检测
- 暂不支持趋势分析

**接口**：
```python
def insight_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext]
) -> Dict[str, Any]:
    """洞察Agent节点"""
    pass
```

### 组件6：重规划Agent（1.5小时）

**文件**：`tableau_assistant/src/agents/replanner_agent.py`

**功能**：
- 决定是否继续分析
- 基础下钻决策

**MVP限制**：
- 只支持简单的贡献度阈值判断
- 暂不支持交叉分析决策
- 暂不支持异常调查决策

**接口**：
```python
def replanner_agent_node(
    state: VizQLState,
    runtime: Runtime[VizQLContext]
) -> Dict[str, Any]:
    """重规划Agent节点"""
    pass
```

### 测试7：端到端测试（30分钟）

**文件**：`tableau_assistant/tests/manual/test_mvp_loop.py`

**测试用例**：
1. 简单问题（单轮）："2016年各地区的销售额"
2. 诊断问题（两轮）："为什么门店A利润最高？"

## 下一步行动

继续实现：
1. 查询执行器
2. 数据合并器
3. 洞察Agent（基础版）
4. 重规划Agent
5. 端到端测试

预计总时间：4-5小时
