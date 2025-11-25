# 任务调度器深度设计文档

## 文档说明

本文档深入分析任务调度器的设计，这是 Tableau Assistant 系统化改进的核心组件。

**创建时间**: 2025-11-20  
**状态**: 设计中

---

## 1. 现状分析

### 1.1 当前实现

**已有组件**：
- ✅ `QueryExecutor`: 可以执行单个 QuerySubTask
- ✅ `QueryExecutor.execute_multiple_subtasks()`: 可以串行执行多个 QuerySubTask
- ✅ `QueryBuilder`: 将 QuerySubTask 转换为 VizQLQuery
- ✅ `DataProcessor`: 处理 ProcessingSubTask（数据后处理）

**当前流程**：
```
TaskPlannerAgent 生成 QueryPlanningResult
    ↓
包含多个 SubTask (QuerySubTask + ProcessingSubTask)
    ↓
❌ 没有自动调度执行
    ↓
需要手动调用 QueryExecutor.execute_multiple_subtasks()
```

### 1.2 核心问题

1. **缺少自动调度**：
   - QueryPlanningResult 生成后，没有自动执行
   - 需要手动调用 QueryExecutor
   - 没有依赖关系处理

2. **缺少并行执行**：
   - `execute_multiple_subtasks()` 是串行执行
   - 独立的子任务应该并行执行
   - 浪费时间

3. **缺少依赖管理**：
   - ProcessingSubTask 依赖 QuerySubTask 的结果
   - 当前没有自动处理依赖关系
   - 需要手动排序

4. **缺少错误处理**：
   - 单个任务失败后如何处理？
   - 是否继续执行其他任务？
   - 如何收集和报告错误？

5. **缺少进度跟踪**：
   - 用户无法看到任务执行进度
   - 无法知道哪些任务完成、哪些失败
   - 缺少实时反馈

---

## 2. 任务调度器设计

### 2.1 核心职责

**TaskScheduler** 负责：
1. **依赖分析**：分析任务之间的依赖关系
2. **任务排序**：按依赖关系对任务进行拓扑排序
3. **并行执行**：并行执行独立的任务
4. **串行执行**：串行执行有依赖的任务
5. **错误处理**：处理任务失败，决定是否继续
6. **进度跟踪**：实时跟踪任务执行进度
7. **结果收集**：收集所有任务的结果

### 2.2 任务类型

```python
# 1. QuerySubTask - 查询任务
{
    "question_id": "q1",
    "task_type": "query",
    "question_text": "2016年各地区的销售额",
    "intents": [...],  # 查询意图
    "depends_on": []   # 无依赖
}

# 2. ProcessingSubTask - 后处理任务
{
    "question_id": "p1",
    "task_type": "post_processing",
    "question_text": "计算同比增长率",
    "processing_type": "yoy",
    "source_tasks": ["q1", "q2"],  # 依赖 q1 和 q2
    "depends_on": [0, 1]  # 依赖索引
}
```

### 2.3 依赖关系

**依赖类型**：
1. **无依赖**：可以立即执行（并行）
2. **单依赖**：依赖一个任务的结果
3. **多依赖**：依赖多个任务的结果

**依赖图示例**：
```
q1 (无依赖) ──┐
              ├──> p1 (依赖 q1, q2)
q2 (无依赖) ──┘

q3 (无依赖)

执行顺序：
- 第 1 轮（并行）：q1, q2, q3
- 第 2 轮（串行）：p1（等待 q1, q2 完成）
```

### 2.4 执行策略

**策略 1：最大并行度**
- 优点：最快
- 缺点：资源消耗大
- 适用：任务少（< 10 个）

**策略 2：限制并行度**
- 优点：资源可控
- 缺点：可能不是最快
- 适用：任务多（> 10 个）

**策略 3：智能调度**
- 根据任务类型和资源情况动态调整
- 优先执行关键路径上的任务
- 适用：复杂场景

---

## 3. 详细设计

### 3.1 TaskScheduler 类

```python
class TaskScheduler:
    """
    任务调度器
    
    负责自动调度和执行 QueryPlanningResult 中的所有任务
    
    特性：
    - 依赖分析和拓扑排序
    - 并行执行独立任务
    - 串行执行有依赖任务
    - 错误处理和重试
    - 进度跟踪和实时反馈
    - 结果收集和聚合
    """
    
    def __init__(
        self,
        query_executor: QueryExecutor,
        data_processor: DataProcessor,
        max_parallel: int = 5,
        fail_fast: bool = False,
        enable_retry: bool = True,
        max_retries: int = 3
    ):
        """
        初始化任务调度器
        
        Args:
            query_executor: 查询执行器
            data_processor: 数据处理器
            max_parallel: 最大并行任务数（默认 5）
            fail_fast: 是否在第一个失败时停止（默认 False）
            enable_retry: 是否启用重试（默认 True）
            max_retries: 最大重试次数（默认 3）
        """
        self.query_executor = query_executor
        self.data_processor = data_processor
        self.max_parallel = max_parallel
        self.fail_fast = fail_fast
        self.enable_retry = enable_retry
        self.max_retries = max_retries
    
    async def execute_plan(
        self,
        query_plan: QueryPlanningResult,
        datasource_luid: str,
        tableau_config: Dict[str, str],
        progress_callback: Optional[Callable] = None
    ) -> SchedulerResult:
        """
        执行查询计划（核心方法）
        
        Args:
            query_plan: 查询计划
            datasource_luid: 数据源 LUID
            tableau_config: Tableau 配置
            progress_callback: 进度回调函数（可选）
        
        Returns:
            SchedulerResult 包含所有任务的结果
        """
        # 1. 依赖分析
        dependency_graph = self._build_dependency_graph(query_plan.subtasks)
        
        # 2. 拓扑排序
        execution_order = self._topological_sort(dependency_graph)
        
        # 3. 分批执行
        results = {}
        for batch in execution_order:
            # 并行执行当前批次
            batch_results = await self._execute_batch(
                batch,
                query_plan.subtasks,
                results,  # 已完成任务的结果
                datasource_luid,
                tableau_config,
                progress_callback
            )
            
            # 更新结果
            results.update(batch_results)
            
            # 检查是否需要停止
            if self.fail_fast and any(r.get('success') == False for r in batch_results.values()):
                break
        
        # 4. 返回结果
        return SchedulerResult(
            total_tasks=len(query_plan.subtasks),
            completed_tasks=len(results),
            successful_tasks=sum(1 for r in results.values() if r.get('success')),
            failed_tasks=sum(1 for r in results.values() if not r.get('success')),
            results=results
        )
```

### 3.2 依赖分析

```python
def _build_dependency_graph(
    self,
    subtasks: List[SubTask]
) -> Dict[str, List[str]]:
    """
    构建依赖图
    
    Args:
        subtasks: 所有子任务
    
    Returns:
        依赖图 {task_id: [依赖的 task_id 列表]}
    """
    graph = {}
    
    for subtask in subtasks:
        task_id = subtask.question_id
        
        if subtask.task_type == "query":
            # QuerySubTask 通常无依赖
            graph[task_id] = []
        
        elif subtask.task_type == "post_processing":
            # ProcessingSubTask 依赖 source_tasks
            dependencies = subtask.source_tasks or []
            graph[task_id] = dependencies
    
    return graph
```

### 3.3 拓扑排序

```python
def _topological_sort(
    self,
    dependency_graph: Dict[str, List[str]]
) -> List[List[str]]:
    """
    拓扑排序（分批）
    
    Args:
        dependency_graph: 依赖图
    
    Returns:
        执行顺序（分批）[[batch1], [batch2], ...]
    """
    # 计算入度
    in_degree = {task_id: 0 for task_id in dependency_graph}
    for dependencies in dependency_graph.values():
        for dep in dependencies:
            in_degree[dep] = in_degree.get(dep, 0) + 1
    
    # 分批执行
    batches = []
    remaining = set(dependency_graph.keys())
    
    while remaining:
        # 找到所有入度为 0 的任务（可以并行执行）
        batch = [
            task_id for task_id in remaining
            if all(dep not in remaining for dep in dependency_graph[task_id])
        ]
        
        if not batch:
            # 检测到循环依赖
            raise ValueError(f"Circular dependency detected: {remaining}")
        
        batches.append(batch)
        remaining -= set(batch)
    
    return batches
```

### 3.4 批量执行

```python
async def _execute_batch(
    self,
    batch: List[str],
    all_subtasks: List[SubTask],
    completed_results: Dict[str, Any],
    datasource_luid: str,
    tableau_config: Dict[str, str],
    progress_callback: Optional[Callable]
) -> Dict[str, Any]:
    """
    并行执行一批任务
    
    Args:
        batch: 当前批次的任务 ID 列表
        all_subtasks: 所有子任务
        completed_results: 已完成任务的结果
        datasource_luid: 数据源 LUID
        tableau_config: Tableau 配置
        progress_callback: 进度回调
    
    Returns:
        当前批次的结果 {task_id: result}
    """
    # 创建任务
    tasks = []
    task_id_map = {}
    
    for task_id in batch:
        subtask = next(t for t in all_subtasks if t.question_id == task_id)
        
        if subtask.task_type == "query":
            # 查询任务
            task = self._execute_query_task(
                subtask,
                datasource_luid,
                tableau_config,
                progress_callback
            )
        else:
            # 后处理任务
            task = self._execute_processing_task(
                subtask,
                completed_results,
                progress_callback
            )
        
        tasks.append(task)
        task_id_map[task] = task_id
    
    # 并行执行（限制并行度）
    results = {}
    
    # 使用 asyncio.Semaphore 限制并行度
    semaphore = asyncio.Semaphore(self.max_parallel)
    
    async def execute_with_semaphore(task, task_id):
        async with semaphore:
            try:
                result = await task
                return task_id, result
            except Exception as e:
                logger.error(f"Task {task_id} failed: {e}")
                return task_id, {
                    'success': False,
                    'error': str(e),
                    'task_id': task_id
                }
    
    # 执行所有任务
    task_results = await asyncio.gather(*[
        execute_with_semaphore(task, task_id_map[task])
        for task in tasks
    ])
    
    # 收集结果
    for task_id, result in task_results:
        results[task_id] = result
    
    return results
```

### 3.5 进度跟踪

```python
class ProgressTracker:
    """
    进度跟踪器
    
    实时跟踪任务执行进度，支持回调通知
    """
    
    def __init__(self, total_tasks: int):
        self.total_tasks = total_tasks
        self.completed_tasks = 0
        self.successful_tasks = 0
        self.failed_tasks = 0
        self.current_task = None
        self.start_time = time.time()
    
    def start_task(self, task_id: str, task_type: str):
        """开始执行任务"""
        self.current_task = {
            'task_id': task_id,
            'task_type': task_type,
            'start_time': time.time()
        }
    
    def complete_task(self, task_id: str, success: bool):
        """完成任务"""
        self.completed_tasks += 1
        if success:
            self.successful_tasks += 1
        else:
            self.failed_tasks += 1
        
        self.current_task = None
    
    def get_progress(self) -> Dict[str, Any]:
        """获取进度信息"""
        elapsed_time = time.time() - self.start_time
        progress_percent = (self.completed_tasks / self.total_tasks) * 100
        
        return {
            'total_tasks': self.total_tasks,
            'completed_tasks': self.completed_tasks,
            'successful_tasks': self.successful_tasks,
            'failed_tasks': self.failed_tasks,
            'progress_percent': progress_percent,
            'elapsed_time': elapsed_time,
            'current_task': self.current_task
        }
```

---

## 4. 集成到工作流

### 4.1 在 VizQLWorkflow 中集成

```python
# 在 vizql_workflow.py 中添加任务调度节点

def task_scheduler_node(state: VizQLState, config=None) -> Dict[str, Any]:
    """任务调度节点"""
    from langgraph.runtime import Runtime
    from tableau_assistant.src.components.task_scheduler import TaskScheduler
    
    # 获取查询计划
    query_plan = state.get("query_plan")
    if not query_plan:
        return {"errors": ["查询计划不存在"]}
    
    # 创建任务调度器
    scheduler = TaskScheduler(
        query_executor=...,  # 从 runtime 获取
        data_processor=...,  # 从 runtime 获取
        max_parallel=5
    )
    
    # 执行计划
    result = await scheduler.execute_plan(
        query_plan=query_plan,
        datasource_luid=config["configurable"]["datasource_luid"],
        tableau_config=...,
        progress_callback=lambda progress: print(f"进度: {progress['progress_percent']:.1f}%")
    )
    
    # 更新状态
    return {
        "subtask_results": result.results,
        "current_stage": "insight"
    }

# 添加到工作流
graph.add_node("task_scheduler", task_scheduler_node)
graph.add_edge("planning", "task_scheduler")
graph.add_edge("task_scheduler", "insight")
```

---

## 5. 缓存策略优化

### 5.1 查询结果缓存

**当前问题**：
- 查询结果没有缓存
- 重规划时需要重新执行所有查询
- 浪费时间和资源

**改进方案**：
```python
class QueryResultCache:
    """查询结果缓存"""
    
    def __init__(self, store: PersistentStore, ttl: int = 3600):
        """
        初始化查询结果缓存
        
        Args:
            store: 持久化存储
            ttl: 缓存过期时间（秒），默认 1 小时
                 建议：3600-7200 秒（1-2 小时）
                 原因：支持累积洞察和重规划
        """
        self.store = store
        self.ttl = ttl
    
    def _generate_cache_key(self, subtask: QuerySubTask) -> str:
        """生成缓存键"""
        # 基于查询内容生成哈希
        cache_input = {
            "intents": [intent.model_dump() for intent in subtask.intents],
            "question_text": subtask.question_text
        }
        cache_str = json.dumps(cache_input, sort_keys=True)
        return hashlib.md5(cache_str.encode()).hexdigest()
    
    def get(self, subtask: QuerySubTask) -> Optional[Dict]:
        """获取缓存的查询结果"""
        cache_key = self._generate_cache_key(subtask)
        item = self.store.get(
            namespace=("query_results",),
            key=cache_key
        )
        return item.value if item else None
    
    def set(self, subtask: QuerySubTask, result: Dict):
        """保存查询结果到缓存"""
        cache_key = self._generate_cache_key(subtask)
        self.store.put(
            namespace=("query_results",),
            key=cache_key,
            value=result,
            ttl=self.ttl
        )
```

### 5.2 缓存时间建议

| 缓存类型 | 当前 TTL | 建议 TTL | 原因 |
|---------|---------|---------|------|
| 元数据 | 1 小时 | 1 小时 | ✅ 合理 |
| 维度层级 | 24 小时 | 24 小时 | ✅ 合理 |
| LLM 响应 | 1 小时 | 1 小时 | ✅ 合理 |
| **查询结果** | ❌ 无 | **1-2 小时** | 🔴 需要添加 |

**查询结果缓存的重要性**：
1. **重规划场景**：用户不满意结果，要求重新分析
   - 无需重新执行所有查询
   - 只执行新增的查询
   - 大幅提升响应速度

2. **累积洞察场景**：多轮对话，逐步深入
   - 保留之前的查询结果
   - 新问题可以复用旧结果
   - 提供更连贯的分析体验

3. **成本优化**：
   - 减少 VDS API 调用
   - 减少数据传输
   - 降低服务器负载

---

## 6. 实施计划

### 6.1 第一阶段：核心功能（2 周）

**Week 1: 基础调度器**
- [ ] 实现 TaskScheduler 类
- [ ] 实现依赖分析和拓扑排序
- [ ] 实现串行执行
- [ ] 单元测试

**Week 2: 并行执行和集成**
- [ ] 实现并行执行（asyncio）
- [ ] 实现进度跟踪
- [ ] 集成到 VizQLWorkflow
- [ ] 集成测试

### 6.2 第二阶段：优化和缓存（1 周）

**Week 3: 缓存和优化**
- [ ] 实现查询结果缓存
- [ ] 优化并行度控制
- [ ] 错误处理和重试
- [ ] 性能测试

---

## 7. 预期效果

### 7.1 性能提升

| 场景 | 当前 | 优化后 | 提升 |
|------|------|--------|------|
| 3 个独立查询 | 串行 15s | 并行 5s | **3x** |
| 5 个独立查询 | 串行 25s | 并行 5s | **5x** |
| 重规划（3 个查询） | 15s | 缓存 0.1s | **150x** |

### 7.2 用户体验提升

- ✅ 自动执行，无需手动调用
- ✅ 实时进度反馈
- ✅ 并行执行，速度更快
- ✅ 智能缓存，重规划更快
- ✅ 错误处理，更加健壮

---

**文档版本**: v1.0  
**作者**: Kiro AI Assistant  
**状态**: 待审核
