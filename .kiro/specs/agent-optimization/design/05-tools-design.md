# 工具设计

## 1. 设计目标

优化工具设计，实现 RAG + Candidate Fields 策略，减少 Token 消耗。

## 2. 工具架构

### 2.1 工具列表

| 工具 | 职责 | LLM 调用 |
|------|------|---------|
| MapFields | 字段映射（RAG + LLM Fallback） | 0-1 |
| BuildQuery | 构建 VizQL 查询 | 0 |
| ExecuteQuery | 执行查询 | 0 |

### 2.2 工具流程

```
UnifiedSemanticParser 输出
    ↓
┌─────────────────────────────────────────┐
│  MapFields                               │
│  ├── RAG 检索候选字段                    │
│  ├── 置信度判断                          │
│  │   ├── >= 0.9 → 直接返回              │
│  │   └── < 0.9 → LLM 从候选中选择       │
│  └── 输出: 字段映射结果                  │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  BuildQuery                              │
│  ├── 转换语义结构为 VizQL 语法          │
│  ├── 生成计算字段表达式                  │
│  └── 输出: VizQL 查询对象               │
└─────────────────────────────────────────┘
    ↓
┌─────────────────────────────────────────┐
│  ExecuteQuery                            │
│  ├── 调用 Tableau VizQL API             │
│  ├── 处理响应                            │
│  └── 输出: 查询结果                      │
└─────────────────────────────────────────┘
```

## 3. MapFields 工具

### 3.1 设计原则

1. **RAG 优先**：先用 RAG 检索，高置信度直接返回
2. **LLM Fallback**：低置信度时让 LLM 从候选中选择
3. **减少 Token**：不传递完整数据模型

### 3.2 实现

```python
from typing import Dict, List, Optional
from pydantic import BaseModel, Field


class CandidateField(BaseModel):
    """候选字段"""
    name: str = Field(description="字段名")
    role: str = Field(description="角色 (dimension/measure)")
    data_type: str = Field(description="数据类型")
    sample_values: List[str] = Field(default_factory=list, description="样例值")
    confidence: float = Field(description="RAG 置信度")


class FieldMappingResult(BaseModel):
    """字段映射结果"""
    entity: str = Field(description="用户提到的实体")
    field_name: str = Field(description="映射到的字段名")
    confidence: float = Field(description="置信度")
    method: str = Field(description="映射方法 (rag/llm)")


class MapFieldsTool:
    """字段映射工具
    
    使用 RAG + LLM Fallback 策略：
    1. RAG 检索候选字段
    2. 高置信度直接返回
    3. 低置信度让 LLM 从候选中选择
    """
    
    def __init__(
        self,
        field_index: "FieldIndex",
        llm: Optional["BaseChatModel"] = None,
        confidence_threshold: float = 0.9,
        top_k: int = 5,
    ):
        self.field_index = field_index
        self.llm = llm
        self.confidence_threshold = confidence_threshold
        self.top_k = top_k
    
    async def execute(
        self,
        entities: List[str],
    ) -> List[FieldMappingResult]:
        """执行字段映射
        
        Args:
            entities: 用户提到的实体列表
            
        Returns:
            字段映射结果列表
        """
        results = []
        
        for entity in entities:
            # Stage 1: RAG 检索
            candidates = await self.field_index.search(entity, top_k=self.top_k)
            
            if not candidates:
                # 无候选字段，跳过
                continue
            
            # Stage 2: 置信度判断
            if candidates[0].confidence >= self.confidence_threshold:
                # 高置信度，直接返回
                results.append(FieldMappingResult(
                    entity=entity,
                    field_name=candidates[0].name,
                    confidence=candidates[0].confidence,
                    method="rag",
                ))
            else:
                # 低置信度，LLM 选择
                if self.llm:
                    selected = await self._llm_select(entity, candidates)
                    results.append(FieldMappingResult(
                        entity=entity,
                        field_name=selected.name,
                        confidence=selected.confidence,
                        method="llm",
                    ))
                else:
                    # 无 LLM，返回最佳候选
                    results.append(FieldMappingResult(
                        entity=entity,
                        field_name=candidates[0].name,
                        confidence=candidates[0].confidence,
                        method="rag",
                    ))
        
        return results
    
    async def _llm_select(
        self,
        entity: str,
        candidates: List[CandidateField],
    ) -> CandidateField:
        """LLM 从候选中选择"""
        prompt = self._build_selection_prompt(entity, candidates)
        
        # 使用结构化输出
        class SelectionOutput(BaseModel):
            selected_index: int = Field(description="选择的候选索引 (0-based)")
            reasoning: str = Field(description="选择理由")
        
        llm_with_schema = self.llm.with_structured_output(SelectionOutput)
        result = await llm_with_schema.ainvoke(prompt)
        
        return candidates[result.selected_index]
    
    def _build_selection_prompt(
        self,
        entity: str,
        candidates: List[CandidateField],
    ) -> str:
        """构建选择 Prompt"""
        candidates_text = "\n".join([
            f"{i}. {c.name} ({c.role}, {c.data_type})"
            + (f" 样例: {', '.join(c.sample_values[:3])}" if c.sample_values else "")
            for i, c in enumerate(candidates)
        ])
        
        return f"""
用户提到的实体: "{entity}"

候选字段:
{candidates_text}

请选择最匹配的字段。
"""
```

### 3.3 FieldIndex 实现

```python
class FieldIndex:
    """字段 RAG 索引
    
    为每个数据源构建字段索引，支持：
    - 字段名语义搜索
    - 样例值匹配
    """
    
    def __init__(self, embeddings: "Embeddings"):
        self.embeddings = embeddings
        self.index = None
        self.fields = []
    
    async def build(self, data_model: "DataModel") -> None:
        """构建索引
        
        Args:
            data_model: 数据模型
        """
        self.fields = data_model.fields
        
        # 构建文档
        documents = []
        for field in self.fields:
            # 组合字段信息
            text = field.name
            if hasattr(field, 'sample_values') and field.sample_values:
                text += f" ({', '.join(field.sample_values[:5])})"
            documents.append(text)
        
        # 向量化
        vectors = await self.embeddings.aembed_documents(documents)
        
        # 构建索引（使用简单的内存索引）
        self.index = {
            "vectors": vectors,
            "documents": documents,
        }
    
    async def search(
        self,
        query: str,
        top_k: int = 5,
    ) -> List[CandidateField]:
        """语义搜索
        
        Args:
            query: 查询文本
            top_k: 返回数量
            
        Returns:
            候选字段列表
        """
        if not self.index:
            return []
        
        # 向量化查询
        query_vector = await self.embeddings.aembed_query(query)
        
        # 计算相似度
        similarities = []
        for i, vec in enumerate(self.index["vectors"]):
            sim = self._cosine_similarity(query_vector, vec)
            similarities.append((i, sim))
        
        # 排序并返回 Top K
        similarities.sort(key=lambda x: x[1], reverse=True)
        
        results = []
        for i, sim in similarities[:top_k]:
            field = self.fields[i]
            results.append(CandidateField(
                name=field.name,
                role=getattr(field, 'role', 'dimension'),
                data_type=getattr(field, 'dataType', 'STRING'),
                sample_values=getattr(field, 'sample_values', []),
                confidence=sim,
            ))
        
        return results
    
    def _cosine_similarity(self, a: List[float], b: List[float]) -> float:
        """计算余弦相似度"""
        import numpy as np
        a, b = np.array(a), np.array(b)
        return float(np.dot(a, b) / (np.linalg.norm(a) * np.linalg.norm(b)))
```

## 4. BuildQuery 工具

### 4.1 设计原则

1. **纯代码实现**：不调用 LLM
2. **语法转换**：将语义结构转换为 VizQL 语法
3. **表达式生成**：生成计算字段表达式

### 4.2 实现

```python
class BuildQueryTool:
    """查询构建工具
    
    将语义结构转换为 VizQL 查询。
    """
    
    def execute(
        self,
        semantic_output: "UnifiedSemanticOutput",
        field_mappings: List[FieldMappingResult],
    ) -> "VizQLQuery":
        """构建查询
        
        Args:
            semantic_output: 语义解析输出
            field_mappings: 字段映射结果
            
        Returns:
            VizQL 查询对象
        """
        # 构建字段映射字典
        mapping_dict = {m.entity: m.field_name for m in field_mappings}
        
        # 构建查询字段
        fields = []
        
        # 添加维度
        for dim in semantic_output.dimensions:
            field_name = mapping_dict.get(dim.field, dim.field)
            fields.append({
                "fieldCaption": field_name,
                "granularity": dim.granularity,
            })
        
        # 添加度量
        for measure in semantic_output.measures:
            field_name = mapping_dict.get(measure.field, measure.field)
            fields.append({
                "fieldCaption": field_name,
                "function": measure.aggregation,
            })
        
        # 添加计算字段（如有）
        if semantic_output.computation:
            calc_field = self._build_calculation(
                semantic_output.computation,
                mapping_dict,
            )
            fields.append(calc_field)
        
        # 构建筛选条件
        filters = []
        for f in semantic_output.filters:
            field_name = mapping_dict.get(f.field, f.field)
            filters.append({
                "field": {"fieldCaption": field_name},
                "filterType": self._map_operator(f.operator),
                "values": f.value if isinstance(f.value, list) else [f.value],
            })
        
        return VizQLQuery(
            fields=fields,
            filters=filters,
        )
    
    def _build_calculation(
        self,
        computation: "Computation",
        mapping_dict: Dict[str, str],
    ) -> Dict:
        """构建计算字段"""
        target = mapping_dict.get(computation.target, computation.target)
        partition_by = [mapping_dict.get(p, p) for p in computation.partition_by]
        
        if computation.calc_type == "RANK":
            expression = f"RANK(SUM([{target}]))"
        elif computation.calc_type == "PERCENT":
            expression = f"SUM([{target}]) / TOTAL(SUM([{target}]))"
        elif computation.calc_type == "RUNNING":
            expression = f"RUNNING_SUM(SUM([{target}]))"
        elif computation.calc_type == "DIFF":
            expression = f"ZN(SUM([{target}])) - LOOKUP(ZN(SUM([{target}])), -1)"
        else:
            expression = computation.expression or f"SUM([{target}])"
        
        return {
            "fieldCaption": f"{computation.calc_type}_{target}",
            "calculation": expression,
        }
    
    def _map_operator(self, operator: str) -> str:
        """映射操作符到 VizQL 筛选类型"""
        mapping = {
            "=": "CATEGORICAL",
            "in": "CATEGORICAL",
            ">": "RANGE",
            "<": "RANGE",
            ">=": "RANGE",
            "<=": "RANGE",
            "between": "RANGE",
            "top": "TOP",
            "bottom": "TOP",
        }
        return mapping.get(operator.lower(), "CATEGORICAL")
```

## 5. ExecuteQuery 工具

### 5.1 设计原则

1. **API 调用**：调用 Tableau VizQL API
2. **错误处理**：处理 API 错误
3. **结果转换**：转换响应格式

### 5.2 实现

```python
class ExecuteQueryTool:
    """查询执行工具
    
    调用 Tableau VizQL API 执行查询。
    """
    
    def __init__(self, vizql_client: "VizQLClient"):
        self.client = vizql_client
    
    async def execute(
        self,
        query: "VizQLQuery",
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
    ) -> "QueryResult":
        """执行查询
        
        Args:
            query: VizQL 查询对象
            datasource_luid: 数据源 LUID
            api_key: API Key
            site: 站点
            
        Returns:
            查询结果
        """
        try:
            response = await self.client.query_datasource_async(
                datasource_luid=datasource_luid,
                query=query.to_dict(),
                api_key=api_key,
                site=site,
            )
            
            return QueryResult(
                success=True,
                data=response.get("data", []),
                row_count=len(response.get("data", [])),
            )
            
        except Exception as e:
            return QueryResult(
                success=False,
                error=str(e),
                error_type=self._classify_error(e),
            )
    
    def _classify_error(self, error: Exception) -> str:
        """分类错误类型"""
        error_str = str(error).lower()
        
        if "field" in error_str and "not found" in error_str:
            return "FIELD_NOT_FOUND"
        elif "permission" in error_str or "unauthorized" in error_str:
            return "PERMISSION_DENIED"
        elif "timeout" in error_str:
            return "TIMEOUT"
        elif "connection" in error_str:
            return "CONNECTION_ERROR"
        else:
            return "UNKNOWN"


class QueryResult(BaseModel):
    """查询结果"""
    success: bool = Field(description="是否成功")
    data: List[Dict] = Field(default_factory=list, description="数据")
    row_count: int = Field(default=0, description="行数")
    error: Optional[str] = Field(default=None, description="错误信息")
    error_type: Optional[str] = Field(default=None, description="错误类型")
```

## 6. 工具注册

### 6.1 工具注册表

```python
class ToolRegistry:
    """工具注册表"""
    
    def __init__(self):
        self._tools: Dict[str, BaseTool] = {}
    
    def register(self, name: str, tool: BaseTool) -> None:
        """注册工具"""
        self._tools[name] = tool
    
    def get(self, name: str) -> Optional[BaseTool]:
        """获取工具"""
        return self._tools.get(name)
    
    def list(self) -> List[str]:
        """列出所有工具"""
        return list(self._tools.keys())


def create_tool_registry(
    field_index: FieldIndex,
    vizql_client: VizQLClient,
    llm: Optional[BaseChatModel] = None,
) -> ToolRegistry:
    """创建工具注册表"""
    registry = ToolRegistry()
    
    # 注册工具
    registry.register("map_fields", MapFieldsTool(
        field_index=field_index,
        llm=llm,
    ))
    registry.register("build_query", BuildQueryTool())
    registry.register("execute_query", ExecuteQueryTool(vizql_client))
    
    return registry
```

## 7. 性能对比

### 7.1 Token 消耗

| 场景 | 当前（传完整模型） | 优化后（RAG 候选） | 减少 |
|------|------------------|-------------------|------|
| 100 字段数据源 | 3000+ tokens | 500 tokens | 83% |
| 50 字段数据源 | 1500+ tokens | 500 tokens | 67% |

### 7.2 LLM 调用

| 场景 | 当前 | 优化后 | 减少 |
|------|------|--------|------|
| 高置信度映射 | 1 | 0 | 100% |
| 低置信度映射 | 1 | 1 | 0% |
