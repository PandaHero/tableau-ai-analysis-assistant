# 查询执行器增强设计文档

## 概述

本文档描述了查询执行器（QueryExecutor）增强功能的技术设计。设计目标是在保持向后兼容的前提下，增强查询执行器的功能性、可观测性和易用性。

## 架构设计

### 组件关系图

```
┌─────────────────────────────────────────────────────────────┐
│                      QueryExecutor                          │
├─────────────────────────────────────────────────────────────┤
│  - tableau_api: TableauAPI                                  │
│  - metadata: Optional[Metadata]                             │
│  - query_builder: Optional[QueryBuilder]                    │
│  - logger: Logger                                           │
├─────────────────────────────────────────────────────────────┤
│  + execute_query(VizQLQuery) -> Dict                        │
│  + execute_subtask(QuerySubTask) -> Dict                    │
│  + execute_multiple_subtasks(List[QuerySubTask]) -> List    │
│  + create_with_metadata(TableauAPI, MetadataManager)        │
└─────────────────────────────────────────────────────────────┘
           │                    │                    │
           ▼                    ▼                    ▼
    ┌──────────┐        ┌──────────────┐    ┌──────────┐
    │TableauAPI│        │QueryBuilder  │    │ Metadata │
    └──────────┘        └──────────────┘    └──────────┘
```

### 核心设计原则

1. **单一职责**: QueryExecutor专注于查询执行和结果处理，查询构建委托给QueryBuilder
2. **依赖注入**: 通过构造函数注入依赖，提高可测试性
3. **向后兼容**: 保持现有API不变，新功能通过新方法提供
4. **异步优先**: 所有执行方法都是异步的，支持高并发
5. **可观测性**: 提供详细的日志和性能指标

## 详细设计

### 1. 类结构增强

#### 1.1 构造函数设计

```python
class QueryExecutor:
    def __init__(
        self, 
        tableau_api: TableauAPI,
        metadata: Optional[Metadata] = None
    ):
        """
        初始化查询执行器
        
        Args:
            tableau_api: Tableau API实例（必需）
            metadata: 元数据对象（可选，用于QueryBuilder）
        """
        self.tableau_api = tableau_api
        self.metadata = metadata
        self.query_builder = None
        
        # 如果提供了metadata，自动创建QueryBuilder
        if metadata:
            self.query_builder = QueryBuilder(metadata=metadata)
        
        self.logger = logging.getLogger(__name__)
```

**设计决策**:
- metadata作为可选参数，保持向后兼容
- 自动创建QueryBuilder，减少使用者的配置负担
- 使用标准logging模块，便于集成到现有日志系统

#### 1.2 工厂方法设计

```python
@classmethod
async def create_with_metadata(
    cls, 
    tableau_api: TableauAPI, 
    metadata_manager: Optional[MetadataManager] = None
) -> 'QueryExecutor':
    """
    创建带有元数据的QueryExecutor实例
    
    Args:
        tableau_api: Tableau API实例
        metadata_manager: 元数据管理器（可选）
    
    Returns:
        配置完整的QueryExecutor实例
    """
    metadata = None
    if metadata_manager:
        metadata = await metadata_manager.get_metadata_async()
    
    return cls(tableau_api=tableau_api, metadata=metadata)
```

**设计决策**:
- 使用类方法提供便捷的创建方式
- 异步获取metadata，避免阻塞
- 返回完全配置的实例，开箱即用

### 2. 执行方法设计

#### 2.1 直接执行VizQLQuery

```python
async def execute_query(self, query: VizQLQuery) -> Dict[str, Any]:
    """
    执行VizQL查询
    
    Args:
        query: VizQL查询对象
    
    Returns:
        查询结果字典，包含:
        - data: 查询结果数据
        - metadata: 结果元数据
        - performance: 性能指标
    
    Raises:
        Exception: 查询执行失败时抛出异常
    """
    start_time = time.time()
    
    try:
        # 记录开始日志
        self.logger.info(
            f"开始执行VizQL查询，字段数: {len(query.fields)}"
        )
        
        if query.filters:
            self.logger.info(f"筛选器数: {len(query.filters)}")
        
        # 转换为Tableau API格式
        api_query = self._convert_to_api_format(query)
        
        # 执行查询
        result = await self.tableau_api.execute_vizql_query(api_query)
        
        # 添加性能信息
        execution_time = time.time() - start_time
        row_count = len(result.get('data', []))
        
        result['performance'] = {
            'execution_time': round(execution_time, 3),
            'row_count': row_count,
            'fields_count': len(query.fields),
            'filters_count': len(query.filters) if query.filters else 0
        }
        
        # 记录成功日志
        self.logger.info(
            f"VizQL查询执行成功 (耗时: {execution_time:.3f}秒, "
            f"返回: {row_count} 行数据)"
        )
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        self.logger.error(
            f"VizQL查询执行失败 (耗时: {execution_time:.3f}秒): {e}"
        )
        raise
```

**设计决策**:
- 使用time.time()记录执行时间，精度足够且性能开销小
- 在结果中添加performance字段，不影响现有data和metadata字段
- 使用结构化日志，便于后续分析
- 在异常情况下也记录执行时间，帮助诊断性能问题

#### 2.2 执行QuerySubTask

```python
async def execute_subtask(self, subtask: QuerySubTask) -> Dict[str, Any]:
    """
    执行QuerySubTask（从Intent构建查询并执行）
    
    Args:
        subtask: 查询子任务对象
    
    Returns:
        查询结果字典，包含:
        - data: 查询结果数据
        - metadata: 结果元数据
        - performance: 性能指标（含build_time和total_time）
        - subtask_info: 子任务信息
    
    Raises:
        ValueError: QueryBuilder未初始化
        Exception: 查询构建或执行失败
    """
    if not self.query_builder:
        raise ValueError("QueryBuilder未初始化，需要提供metadata参数")
    
    start_time = time.time()
    
    try:
        self.logger.info(
            f"开始执行子任务: {subtask.question_id} - {subtask.question_text}"
        )
        
        # 使用QueryBuilder构建VizQL查询
        build_start = time.time()
        vizql_query = self.query_builder.build_query(subtask)
        build_time = time.time() - build_start
        
        self.logger.info(f"查询构建完成 (耗时: {build_time:.3f}秒)")
        
        # 执行VizQL查询
        result = await self.execute_query(vizql_query)
        
        # 添加构建时间到性能信息
        if 'performance' in result:
            result['performance']['build_time'] = round(build_time, 3)
            result['performance']['total_time'] = round(
                time.time() - start_time, 3
            )
        
        # 添加子任务信息
        result['subtask_info'] = {
            'question_id': subtask.question_id,
            'question_text': subtask.question_text,
            'task_type': subtask.task_type
        }
        
        return result
        
    except Exception as e:
        execution_time = time.time() - start_time
        self.logger.error(
            f"子任务执行失败: {subtask.question_id} "
            f"(耗时: {execution_time:.3f}秒) - {e}"
        )
        raise
```

**设计决策**:
- 分离构建时间和执行时间，便于性能分析
- 添加subtask_info字段，便于追踪查询来源
- 复用execute_query方法，避免代码重复
- 在QueryBuilder未初始化时提供清晰的错误信息

#### 2.3 批量执行

```python
async def execute_multiple_subtasks(
    self, 
    subtasks: List[QuerySubTask]
) -> List[Dict[str, Any]]:
    """
    批量执行多个QuerySubTask
    
    Args:
        subtasks: 查询子任务列表
    
    Returns:
        查询结果列表，每个元素包含:
        - success: 是否成功
        - result: 查询结果（成功时）
        - error: 错误信息（失败时）
        - subtask_info: 子任务信息（失败时）
    """
    results = []
    total_start = time.time()
    
    self.logger.info(f"开始批量执行 {len(subtasks)} 个子任务")
    
    for i, subtask in enumerate(subtasks, 1):
        try:
            self.logger.info(
                f"执行子任务 {i}/{len(subtasks)}: {subtask.question_id}"
            )
            
            result = await self.execute_subtask(subtask)
            
            results.append({
                'success': True,
                'result': result,
                'error': None
            })
            
        except Exception as e:
            self.logger.error(f"子任务 {subtask.question_id} 执行失败: {e}")
            
            results.append({
                'success': False,
                'result': None,
                'error': str(e),
                'subtask_info': {
                    'question_id': subtask.question_id,
                    'question_text': subtask.question_text,
                    'task_type': subtask.task_type
                }
            })
    
    # 统计和日志
    total_time = time.time() - total_start
    success_count = sum(1 for r in results if r['success'])
    
    self.logger.info(
        f"批量执行完成 (总耗时: {total_time:.3f}秒, "
        f"成功: {success_count}/{len(subtasks)})"
    )
    
    return results
```

**设计决策**:
- 顺序执行而非并发执行，避免对Tableau服务器造成过大压力
- 单个失败不影响其他任务，提高容错性
- 统一的结果格式，便于批量处理
- 详细的进度日志，便于监控长时间运行的批量任务

### 3. 性能监控设计

#### 3.1 性能指标定义

```python
# 基础性能指标（所有查询）
{
    'execution_time': float,  # 查询执行时间（秒）
    'row_count': int,         # 返回行数
    'fields_count': int,      # 字段数量
    'filters_count': int      # 筛选器数量
}

# 扩展性能指标（QuerySubTask）
{
    'execution_time': float,  # 查询执行时间（秒）
    'row_count': int,         # 返回行数
    'fields_count': int,      # 字段数量
    'filters_count': int,     # 筛选器数量
    'build_time': float,      # 查询构建时间（秒）
    'total_time': float       # 总时间（构建+执行）
}
```

#### 3.2 性能数据收集

- 使用`time.time()`在关键点记录时间戳
- 计算时间差得到各阶段耗时
- 从查询对象和结果中提取计数信息
- 将性能数据添加到结果字典的performance字段

#### 3.3 性能日志输出

```python
# 成功日志格式
"VizQL查询执行成功 (耗时: 0.123秒, 返回: 100 行数据)"

# 失败日志格式
"VizQL查询执行失败 (耗时: 0.456秒): 错误信息"

# 批量执行日志格式
"批量执行完成 (总耗时: 1.234秒, 成功: 8/10)"
```

### 4. 错误处理设计

#### 4.1 错误分类

1. **输入验证错误**: QueryBuilder未初始化、参数无效等
2. **查询构建错误**: QueryBuilder抛出的异常
3. **查询执行错误**: TableauAPI抛出的异常
4. **系统错误**: 网络错误、超时等

#### 4.2 错误处理策略

```python
# 输入验证错误 - 立即抛出ValueError
if not self.query_builder:
    raise ValueError("QueryBuilder未初始化，需要提供metadata参数")

# 查询构建/执行错误 - 记录日志后重新抛出
try:
    result = await self.execute_query(vizql_query)
except Exception as e:
    self.logger.error(f"查询执行失败: {e}")
    raise  # 保留原始异常信息

# 批量执行错误 - 捕获并记录，继续执行其他任务
try:
    result = await self.execute_subtask(subtask)
    results.append({'success': True, 'result': result})
except Exception as e:
    self.logger.error(f"子任务执行失败: {e}")
    results.append({'success': False, 'error': str(e)})
```

#### 4.3 日志级别使用

- **INFO**: 正常执行流程（开始、成功、进度）
- **WARNING**: 可恢复的问题（暂未使用）
- **ERROR**: 执行失败、异常情况

### 5. 数据流设计

#### 5.1 直接执行VizQLQuery流程

```
VizQLQuery
    ↓
execute_query()
    ↓
记录开始日志
    ↓
_convert_to_api_format()
    ↓
tableau_api.execute_vizql_query()
    ↓
添加performance字段
    ↓
记录成功日志
    ↓
返回结果
```

#### 5.2 执行QuerySubTask流程

```
QuerySubTask
    ↓
execute_subtask()
    ↓
记录开始日志
    ↓
query_builder.build_query()
    ↓
记录构建完成日志
    ↓
execute_query()
    ↓
添加build_time和total_time
    ↓
添加subtask_info
    ↓
返回结果
```

#### 5.3 批量执行流程

```
List[QuerySubTask]
    ↓
execute_multiple_subtasks()
    ↓
记录批量开始日志
    ↓
for each subtask:
    ↓
    记录进度日志
    ↓
    execute_subtask()
    ↓
    收集结果（成功或失败）
    ↓
统计成功率
    ↓
记录批量完成日志
    ↓
返回结果列表
```

## 接口设计

### 公共接口

```python
class QueryExecutor:
    # 构造函数
    def __init__(
        self, 
        tableau_api: TableauAPI,
        metadata: Optional[Metadata] = None
    ) -> None
    
    # 工厂方法
    @classmethod
    async def create_with_metadata(
        cls, 
        tableau_api: TableauAPI, 
        metadata_manager: Optional[MetadataManager] = None
    ) -> 'QueryExecutor'
    
    # 执行方法
    async def execute_query(
        self, 
        query: VizQLQuery
    ) -> Dict[str, Any]
    
    async def execute_subtask(
        self, 
        subtask: QuerySubTask
    ) -> Dict[str, Any]
    
    async def execute_multiple_subtasks(
        self, 
        subtasks: List[QuerySubTask]
    ) -> List[Dict[str, Any]]
```

### 私有接口

```python
# 保持现有的私有方法不变
def _convert_to_api_format(self, query: VizQLQuery) -> Dict[str, Any]
```

## 测试策略

### 单元测试

1. **测试直接执行VizQLQuery**
   - 验证性能指标正确记录
   - 验证日志正确输出
   - 验证错误处理

2. **测试执行QuerySubTask**
   - 验证QueryBuilder正确调用
   - 验证build_time和total_time正确计算
   - 验证subtask_info正确添加
   - 验证QueryBuilder未初始化时的错误处理

3. **测试批量执行**
   - 验证所有子任务都被执行
   - 验证单个失败不影响其他任务
   - 验证成功率统计正确
   - 验证进度日志正确输出

4. **测试工厂方法**
   - 验证metadata正确获取
   - 验证QueryBuilder正确创建
   - 验证返回实例配置正确

### 集成测试

1. **端到端测试**: 从QuerySubTask到最终结果
2. **性能测试**: 验证性能监控的准确性
3. **错误场景测试**: 验证各种错误情况的处理

## 兼容性考虑

### 向后兼容

1. 保持现有的`execute_query`方法签名不变
2. 新功能通过新方法提供（`execute_subtask`、`execute_multiple_subtasks`）
3. metadata参数为可选，不影响现有使用方式

### 未来扩展

1. 支持并发执行（使用asyncio.gather）
2. 支持查询缓存
3. 支持查询重试机制
4. 支持更详细的性能分析（如网络时间、解析时间等）

## 风险和缓解措施

### 风险1: 性能监控开销

**风险**: 添加性能监控可能影响查询性能

**缓解措施**:
- 使用轻量级的time.time()
- 避免复杂的计算
- 性能开销预计<1%

### 风险2: 批量执行内存占用

**风险**: 批量执行大量查询可能占用大量内存

**缓解措施**:
- 顺序执行而非并发执行
- 建议使用者分批处理大量查询
- 未来可考虑添加流式处理

### 风险3: 日志量过大

**风险**: 详细日志可能产生大量日志数据

**缓解措施**:
- 使用合适的日志级别
- 建议配置日志轮转
- 关键信息使用结构化日志便于过滤

## 实施计划

### Phase 1: 核心功能（已完成）
- ✅ 增强execute_query方法（性能监控）
- ✅ 实现execute_subtask方法
- ✅ 实现execute_multiple_subtasks方法
- ✅ 实现create_with_metadata工厂方法

### Phase 2: 测试和文档
- 编写单元测试
- 编写集成测试
- 更新API文档
- 编写使用示例

### Phase 3: 优化和扩展
- 性能优化
- 添加查询缓存（可选）
- 添加重试机制（可选）
- 支持并发执行（可选）
