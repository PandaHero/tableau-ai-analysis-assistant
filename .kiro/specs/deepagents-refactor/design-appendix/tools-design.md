# 工具设计详解

本文档详细描述 DeepAgents 重构中的 **8 个 Tableau 工具** 的设计。

## 工具分类

### 核心工具（5个）
1. [get_metadata](#1-get_metadata) - 元数据查询
2. [semantic_map_fields](#2-semantic_map_fields) - 语义字段映射（RAG+LLM）
3. [parse_date](#3-parse_date) - 日期解析
4. [build_vizql_query](#4-build_vizql_query) - 查询构建
5. [execute_vizql_query](#5-execute_vizql_query) - 查询执行

### 辅助工具（3个）
6. [process_query_result](#6-process_query_result) - 数据处理
7. [detect_statistics](#7-detect_statistics) - 统计检测
8. [save_large_result](#8-save_large_result) - 大结果保存

---

## 目录

---

## 1. get_metadata

### 职责

获取 Tableau 数据源元数据，包含字段列表、维度层级、统计信息。

**说明**: 这是最基础的工具，几乎所有 Agent 都需要使用它来了解数据源结构。

### 工具定义

```python
@tool
def get_metadata(
    datasource_luid: str,
    use_cache: bool = True
) -> Dict[str, Any]:
    """
    获取 Tableau 数据源元数据
    
    Args:
        datasource_luid: 数据源 LUID
        use_cache: 是否使用缓存（默认 True）
    
    Returns:
        元数据，包含：
            - fields: 字段列表
            - dimension_hierarchy: 维度层级
            - valid_max_date: 数据最新日期
            - datasource_name: 数据源名称
    
    Example:
        metadata = get_metadata("abc123")
        fields = metadata["fields"]
        hierarchy = metadata["dimension_hierarchy"]
    """
    from tableau_assistant.src.components.metadata_manager import MetadataManager
    
    manager = MetadataManager()
    return manager.get_metadata(
        datasource_luid,
        use_cache=use_cache,
        enhance=True  # 包含维度层级
    )
```

### 元数据结构

```python
{
    "datasource_luid": "abc123",
    "datasource_name": "Superstore",
    "fields": [
        {
            "fieldCaption": "地区",
            "dataType": "string",
            "role": "dimension",
            "unique_count": 4,
            "sample_values": ["华东", "华北", "华南", "华西"]
        },
        {
            "fieldCaption": "销售额",
            "dataType": "real",
            "role": "measure",
            "min": 0.0,
            "max": 1000000.0,
            "avg": 50000.0
        }
    ],
    "dimension_hierarchy": {
        "地区": {
            "category": "地理",
            "level": 1,
            "granularity": "粗粒度",
            "parent_dimension": null,
            "child_dimension": "城市"
        },
        "城市": {
            "category": "地理",
            "level": 2,
            "granularity": "中粒度",
            "parent_dimension": "地区",
            "child_dimension": "门店"
        }
    },
    "valid_max_date": "2024-12-31"
}
```

---

## 2. semantic_map_fields

### 职责

使用 **RAG+LLM混合模型** 实现智能字段映射，将业务术语映射到技术字段名。

### 工具定义

```python
@tool
async def semantic_map_fields(
    user_input: str,
    question_context: str,
    metadata: Dict[str, Any]
) -> Dict[str, Any]:
    """
    使用RAG+LLM混合模型进行语义字段映射
    
    **混合模型架构**：
    1. **RAG阶段**：向量检索快速找到语义相似的候选字段
       - 使用FAISS向量数据库
       - bce-embedding-base-v1或OpenAI embeddings
       - 检索Top-K候选字段（通常K=5-10）
    
    2. **LLM阶段**：语义理解选择最佳匹配
       - 理解业务上下文
       - 考虑问题语义
       - 生成推理过程
    
    **优势**：
    - 理解业务语义（"销售额" vs "销售数量"）
    - 考虑上下文（"去年的销售额" vs "今年的销售额"）
    - 处理同义词（"收入" = "营收" = "销售额"）
    - 处理多语言（"Sales" = "销售额"）
    - 高准确率（RAG召回 + LLM精确判断）
    
    Args:
        user_input: 用户输入的业务术语（如"销售额"）
        question_context: 完整的问题上下文（如"2024年各地区的销售额"）
        metadata: 数据源元数据
    
    Returns:
        映射结果，包含：
            - matched_field: 匹配的技术字段名
            - confidence: 匹配置信度（0-1）
            - reasoning: 匹配理由
            - alternatives: 其他可能的匹配
    
    Example:
        result = await semantic_map_fields(
            "销售额",
            "2024年各地区的销售额",
            metadata
        )
        # {
        #   "matched_field": "Sales",
        #   "confidence": 0.95,
        #   "reasoning": "根据上下文，用户询问的是销售金额",
        #   "alternatives": ["Revenue", "Total Sales"]
        # }
    """
    from tableau_assistant.src.semantic_mapping.semantic_mapper import SemanticMapper
    from tableau_assistant.src.utils.models import select_model
    from langchain_openai import OpenAIEmbeddings
    
    # 初始化 Embeddings 和 LLM
    embeddings = OpenAIEmbeddings(model="text-embedding-3-small")
    llm = select_model(provider="openai", model_name="gpt-4o-mini")
    
    # 创建语义映射器
    mapper = SemanticMapper(
        embeddings=embeddings,
        llm=llm,
        metadata=metadata,
        vector_store_path=f"data/vector_stores/fields_{metadata['datasource_luid']}"
    )
    
    # 执行语义映射
    result = await mapper.map(user_input, question_context)
    
    return result
```

### 工作流程

```
用户输入: "销售额"
  ↓
1. 向量检索 (FAISS)
   ├─ 候选1: [Sales].[Sales Amount] (0.95)
   ├─ 候选2: [Sales].[Revenue] (0.92)
   ├─ 候选3: [Sales].[Quantity] (0.65)
   └─ 候选4: [Sales].[Discount] (0.45)
  ↓
2. 过滤低相似度候选（< 0.6）
   ├─ 保留: Sales Amount, Revenue, Quantity
   └─ 过滤: Discount
  ↓
3. LLM 语义判断
   输入:
     - 问题上下文: "2024年各地区的销售额"
     - 候选字段: [Sales Amount, Revenue, Quantity]
     - 字段描述: {...}
   输出:
     - 最佳匹配: Sales Amount
     - 置信度: 0.95
     - 推理: "用户询问的是销售金额，而非数量"
  ↓
4. 返回结果
   {
     "matched_field": "Sales Amount",
     "confidence": 0.95,
     "reasoning": "...",
     "alternatives": ["Revenue"]
   }
```

---

## 3. parse_date

### 职责

解析相对日期表达式，转换为绝对日期。

### 工具定义

```python
@tool
def parse_date(
    date_expression: str,
    reference_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    解析相对日期表达式
    
    Args:
        date_expression: 日期表达式（如"上个月"、"去年"）
        reference_date: 参考日期（默认为今天）
    
    Returns:
        解析结果，包含：
            - start_date: 开始日期
            - end_date: 结束日期
            - date_type: 日期类型（day/week/month/year）
    
    Example:
        result = parse_date("上个月")
        # {"start_date": "2024-10-01", "end_date": "2024-10-31", "date_type": "month"}
    """
    from tableau_assistant.src.components.date_parser import DateParser
    
    parser = DateParser()
    return parser.parse(date_expression, reference_date)
```

### 支持的日期表达式

**相对日期**：
- 今天、昨天、明天
- 本周、上周、下周
- 本月、上月、下月
- 今年、去年、明年

**时间范围**：
- 最近7天、最近30天
- 最近3个月、最近12个月
- 过去一年、未来一年

**同比/环比**：
- 去年同期
- 上月同期
- 上周同期

---

## 4. build_vizql_query

### 职责

根据语义级别的 Spec 生成技术级别的 VizQL 查询 JSON。

### 工具定义

```python
@tool
def build_vizql_query(
    fields: List[Dict],
    filters: List[Dict],
    sort: Optional[Dict] = None,
    limit: Optional[int] = None
) -> Dict[str, Any]:
    """
    构建 VizQL 查询
    
    Args:
        fields: 字段列表（维度 + 度量）
        filters: 筛选条件
        sort: 排序规则（可选）
        limit: 结果数量限制（可选）
    
    Returns:
        VizQL 查询 JSON
    
    Example:
        query = build_vizql_query(
            fields=[
                {"fieldCaption": "地区", "role": "dimension"},
                {"fieldCaption": "销售额", "role": "measure", "function": "SUM"}
            ],
            filters=[
                {"fieldCaption": "年份", "operator": "=", "value": 2024}
            ]
        )
    """
    from tableau_assistant.src.components.query_builder import QueryBuilder
    
    builder = QueryBuilder()
    return builder.build_vizql_query(fields, filters, sort, limit)
```

### 内部实现（100% 复用）

```python
# tableau_assistant/src/components/query_builder.py
class QueryBuilder:
    """查询构建器（现有组件，100% 复用）"""
    
    def build_vizql_query(
        self,
        fields: List[Dict],
        filters: List[Dict],
        sort: Optional[Dict] = None,
        limit: Optional[int] = None
    ) -> Dict:
        """构建 VizQL 查询"""
        # 1. 构建字段
        vizql_fields = self._build_fields(fields)
        
        # 2. 构建筛选器
        vizql_filters = self._build_filters(filters)
        
        # 3. 构建排序
        if sort:
            self._apply_sort(vizql_fields, sort)
        
        # 4. 构建查询
        query = {
            "fields": vizql_fields,
            "filters": vizql_filters
        }
        
        if limit:
            query["limit"] = limit
        
        return query
```

---

## 5. execute_vizql_query

### 职责

执行 VizQL 查询，调用 Tableau VDS API，处理分页和错误，返回原始查询结果。

**说明**: 这是查询执行的核心工具，封装了 QueryExecutor 组件。

### 工具定义

```python
@tool
async def execute_vizql_query(
    query: Dict[str, Any],
    datasource_luid: str
) -> Dict[str, Any]:
    """
    执行 VizQL 查询
    
    Args:
        query: VizQL 查询对象（由 build_vizql_query 生成）
        datasource_luid: 数据源 LUID
    
    Returns:
        原始查询结果，包含：
            - data: 数据行列表
            - schema: 字段 schema
            - row_count: 行数
            - execution_time: 执行时间
    
    Example:
        query = build_vizql_query(...)
        result = await execute_vizql_query(query, "abc123")
    """
    from tableau_assistant.src.components.query_executor import QueryExecutor
    from tableau_assistant.src.utils.auth import get_jwt_token
    import time
    
    # 获取认证 token
    token = get_jwt_token()
    
    # 执行查询
    start_time = time.time()
    executor = QueryExecutor(token, datasource_luid)
    result = await executor.execute(query)
    execution_time = time.time() - start_time
    
    result["execution_time"] = execution_time
    return result
```

### 内部实现（100% 复用）

```python
# tableau_assistant/src/components/query_executor.py
class QueryExecutor:
    """查询执行器（现有组件，100% 复用）"""
    
    def __init__(self, token: str, datasource_luid: str):
        self.token = token
        self.datasource_luid = datasource_luid
        self.api_url = f"{TABLEAU_SERVER}/api/vizql/v1/query"
    
    async def execute(self, query: Dict) -> Dict:
        """执行查询"""
        # 1. 构建请求
        payload = {
            "datasource": {"luid": self.datasource_luid},
            "query": query
        }
        
        # 2. 调用 VDS API
        response = await self._post_request(self.api_url, payload)
        
        # 3. 处理分页
        all_data = []
        while response.get("hasMore"):
            all_data.extend(response["data"])
            # 获取下一页
            response = await self._get_next_page(response)
        
        return {
            "data": all_data,
            "schema": response["schema"],
            "row_count": len(all_data)
        }
```

---

## 6. process_query_result

### 职责

处理查询结果，进行数据清洗、类型转换、格式化。

**说明**: 封装了 DataProcessor 组件，将原始查询结果转换为易于分析的格式。

### 工具定义

```python
@tool
def process_query_result(
    raw_result: Dict[str, Any],
    options: Optional[Dict[str, Any]] = None
) -> Dict[str, Any]:
    """
    处理查询结果
    
    Args:
        raw_result: 原始查询结果（来自 execute_vizql_query）
        options: 处理选项，包含：
            - convert_types: 是否转换数据类型（默认 True）
            - handle_nulls: 如何处理空值（默认 "keep"）
            - format_dates: 是否格式化日期（默认 True）
    
    Returns:
        处理后的结果，包含：
            - data: 处理后的数据行
            - schema: 字段 schema
            - row_count: 行数
            - statistics: 基础统计信息
    
    Example:
        raw_result = await execute_vizql_query(...)
        processed = process_query_result(raw_result)
    """
    from tableau_assistant.src.components.data_processor import DataProcessor
    
    processor = DataProcessor()
    return processor.process(raw_result, options or {})
```

### 内部实现（100% 复用）

```python
# tableau_assistant/src/components/data_processor.py
class DataProcessor:
    """数据处理器（现有组件，100% 复用）"""
    
    def process(self, raw_result: Dict, options: Dict) -> Dict:
        """处理查询结果"""
        data = raw_result["data"]
        schema = raw_result["schema"]
        
        # 1. 类型转换
        if options.get("convert_types", True):
            data = self._convert_types(data, schema)
        
        # 2. 处理空值
        if options.get("handle_nulls", "keep") != "keep":
            data = self._handle_nulls(data, options["handle_nulls"])
        
        # 3. 格式化日期
        if options.get("format_dates", True):
            data = self._format_dates(data, schema)
        
        # 4. 计算基础统计
        statistics = self._calculate_statistics(data, schema)
        
        return {
            "data": data,
            "schema": schema,
            "row_count": len(data),
            "statistics": statistics
        }
```

---

## 7. detect_statistics

### 职责

对查询结果进行统计检测，识别异常值、趋势、模式。

**说明**: 封装了 StatisticsDetector 组件，为洞察分析提供统计支持。

### 工具定义

```python
@tool
def detect_statistics(
    data: List[Dict[str, Any]],
    schema: Dict[str, Any],
    detection_types: Optional[List[str]] = None
) -> Dict[str, Any]:
    """
    统计检测
    
    Args:
        data: 数据行列表
        schema: 字段 schema
        detection_types: 检测类型列表，可选：
            - "outliers": 异常值检测
            - "trends": 趋势检测
            - "patterns": 模式识别
            - "correlations": 相关性分析
    
    Returns:
        检测结果，包含：
            - outliers: 异常值列表
            - trends: 趋势信息
            - patterns: 识别的模式
            - correlations: 相关性矩阵
    
    Example:
        result = process_query_result(...)
        stats = detect_statistics(
            result["data"],
            result["schema"],
            ["outliers", "trends"]
        )
    """
    from tableau_assistant.src.components.statistics_detector import StatisticsDetector
    
    detector = StatisticsDetector()
    return detector.detect(data, schema, detection_types or ["outliers", "trends"])
```

### 内部实现（100% 复用）

```python
# tableau_assistant/src/components/statistics_detector.py
class StatisticsDetector:
    """统计检测器（现有组件，100% 复用）"""
    
    def detect(
        self,
        data: List[Dict],
        schema: Dict,
        detection_types: List[str]
    ) -> Dict:
        """执行统计检测"""
        results = {}
        
        if "outliers" in detection_types:
            results["outliers"] = self._detect_outliers(data, schema)
        
        if "trends" in detection_types:
            results["trends"] = self._detect_trends(data, schema)
        
        if "patterns" in detection_types:
            results["patterns"] = self._detect_patterns(data, schema)
        
        if "correlations" in detection_types:
            results["correlations"] = self._detect_correlations(data, schema)
        
        return results
```

---

## 8. save_large_result

### 职责

将大型查询结果保存到文件，避免内存溢出。

**说明**: 当查询结果超过阈值（如 100 行）时，自动保存到文件，返回文件路径。

### 工具定义

```python
@tool
def save_large_result(
    result: Dict[str, Any],
    threshold: int = 100
) -> Dict[str, Any]:
    """
    保存大型查询结果
    
    Args:
        result: 查询结果
        threshold: 行数阈值（默认 100）
    
    Returns:
        如果超过阈值，返回：
            - file_path: 文件路径
            - row_count: 行数
            - schema: 字段 schema
        否则返回原结果
    
    Example:
        result = process_query_result(...)
        saved = save_large_result(result, threshold=100)
        if "file_path" in saved:
            # 结果已保存到文件
            file_path = saved["file_path"]
    """
    import json
    import os
    from datetime import datetime
    
    row_count = result.get("row_count", len(result.get("data", [])))
    
    # 如果未超过阈值，直接返回
    if row_count <= threshold:
        return result
    
    # 保存到文件
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    file_path = f"data/query_results/result_{timestamp}.json"
    
    os.makedirs(os.path.dirname(file_path), exist_ok=True)
    with open(file_path, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)
    
    return {
        "file_path": file_path,
        "row_count": row_count,
        "schema": result.get("schema"),
        "message": f"结果已保存到文件（{row_count} 行）"
    }
```

---

## 工具协作流程

### 完整的查询执行流程

```
Planning Agent
  ↓
1. 调用 get_metadata
   → 获取字段列表和维度层级
  ↓
2. 调用 semantic_map_fields (RAG+LLM)
   → 将业务术语映射到技术字段
  ↓
3. 调用 parse_date
   → 解析相对日期表达式
  ↓
4. 调用 build_vizql_query
   → 生成 VizQL 查询 JSON
  ↓
主 Agent（执行查询）
  ↓
5. 调用 execute_vizql_query
   → 执行查询，返回原始结果
  ↓
6. 调用 process_query_result
   → 处理数据（类型转换、格式化）
  ↓
7. 调用 save_large_result
   → 如果结果过大，保存到文件
  ↓
Insight Agent
  ↓
8. 调用 detect_statistics
   → 统计检测（异常值、趋势）
  ↓
9. 分析结果，生成洞察
```

### 工具依赖关系

```
get_metadata
  ├─→ semantic_map_fields (需要元数据)
  └─→ build_vizql_query (需要字段信息)

semantic_map_fields
  └─→ build_vizql_query (提供映射后的字段)

parse_date
  └─→ build_vizql_query (提供解析后的日期)

build_vizql_query
  └─→ execute_vizql_query (提供查询对象)

execute_vizql_query
  └─→ process_query_result (提供原始结果)

process_query_result
  ├─→ save_large_result (提供处理后的结果)
  └─→ detect_statistics (提供处理后的数据)
```

---

## 工具开发指南

### 创建新工具

```python
from langchain_core.tools import tool

@tool
def my_custom_tool(
    param1: str,
    param2: int
) -> Dict[str, Any]:
    """
    工具描述（会被 LLM 看到）
    
    Args:
        param1: 参数1描述
        param2: 参数2描述
    
    Returns:
        返回值描述
    
    Example:
        result = my_custom_tool("value", 123)
    """
    # 实现逻辑
    return {"result": "..."}
```

### 工具最佳实践

1. **清晰的文档** - 详细的 docstring
2. **类型提示** - 使用 Python 类型提示
3. **错误处理** - 优雅的错误处理
4. **示例代码** - 提供使用示例
5. **性能优化** - 避免阻塞操作
6. **100% 复用** - 封装现有组件，不重写业务逻辑

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15
