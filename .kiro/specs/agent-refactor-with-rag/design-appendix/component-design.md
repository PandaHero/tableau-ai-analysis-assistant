# 组件层设计

## 概述

本文档描述组件层的详细设计，包括 FieldMapper、ImplementationResolver、ExpressionGenerator。

对应项目结构：`src/components/`

**注意**：洞察系统组件（AnalysisCoordinator 等）在 [insight-design.md](./insight-design.md) 中单独描述。

---

## 组件 vs 工具 的区别

| 特性 | 组件 (Component) | 工具 (Tool) |
|------|-----------------|-------------|
| 调用方式 | 代码直接调用 | Agent 通过 tool_calls 调用 |
| LLM 可见性 | 不可见 | 可见（在 Agent 的工具列表中） |
| 内部实现 | 可以使用 LLM | 通常是薄封装 |

---

## 1. FieldMapper

### 职责

- 将业务术语映射到技术字段名
- RAG + LLM 混合模式

### 实现

```python
# tableau_assistant/src/components/field_mapper/mapper.py

class FieldMapper:
    """
    字段映射器（RAG + LLM 混合）
    
    策略：
    1. RAG 检索候选字段
    2. 置信度 >= 0.9 → 直接返回
    3. 置信度 < 0.9 → LLM 判断
    """
    
    def __init__(self, metadata: Metadata, semantic_mapper: SemanticMapper):
        self.metadata = metadata
        self.semantic_mapper = semantic_mapper
        self.cache = FieldMappingCache()
    
    async def map(
        self,
        business_terms: List[str],
        context: Optional[str] = None
    ) -> Dict[str, str]:
        """
        映射业务术语到技术字段
        
        Args:
            business_terms: 业务术语列表
            context: 问题上下文
        
        Returns:
            {业务术语: 技术字段名} 映射
        """
        result = {}
        terms_need_llm = []
        
        for term in business_terms:
            # 1. 检查缓存
            cached = self.cache.get(term)
            if cached:
                result[term] = cached
                continue
            
            # 2. RAG 检索
            candidates = await self.semantic_mapper.search(term, top_k=3)
            
            if candidates and candidates[0].score >= 0.9:
                # 高置信度，直接使用
                result[term] = candidates[0].field.fieldCaption
                self.cache.set(term, candidates[0].field.fieldCaption)
            else:
                # 低置信度，需要 LLM 判断
                terms_need_llm.append((term, candidates))
        
        # 3. LLM 批量判断
        if terms_need_llm:
            llm_results = await self._llm_judge(terms_need_llm, context)
            result.update(llm_results)
        
        return result
    
    async def _llm_judge(
        self,
        terms_with_candidates: List[Tuple[str, List[Candidate]]],
        context: Optional[str]
    ) -> Dict[str, str]:
        """LLM 判断低置信度映射"""
        prompt = self._build_judge_prompt(terms_with_candidates, context)
        response = await self.llm.ainvoke(prompt)
        return self._parse_judge_response(response.content)
```

### 缓存逻辑

```python
# tableau_assistant/src/components/field_mapper/cache.py

class FieldMappingCache:
    """字段映射缓存"""
    
    def __init__(self, ttl: int = 3600):
        self._cache: Dict[str, Tuple[str, float]] = {}
        self.ttl = ttl
    
    def get(self, term: str) -> Optional[str]:
        if term in self._cache:
            field, timestamp = self._cache[term]
            if time.time() - timestamp < self.ttl:
                return field
            del self._cache[term]
        return None
    
    def set(self, term: str, field: str):
        self._cache[term] = (field, time.time())
```

---

## 2. ImplementationResolver

### 职责

- 判断使用表计算还是 LOD
- 解析 addressing 维度
- 代码规则优先，复杂场景 LLM fallback

### 表计算 vs LOD 决策规则

```
用户需求
    ↓
是否需要访问视图外的维度？
    ├─ 是 → 必须用 LOD
    └─ 否 → 是否需要不同于视图的聚合粒度？
              ├─ 是 → 优先用 LOD
              └─ 否 → 用表计算
```

### 实现

```python
# tableau_assistant/src/components/implementation_resolver/resolver.py

class ImplementationResolver:
    """
    实现方式解析器（代码规则 + LLM fallback）
    """
    
    def resolve(
        self,
        analysis: AnalysisSpec,
        dimensions: List[DimensionSpec],
        mapped_fields: Dict[str, str],
        view_dimensions: List[str]
    ) -> Implementation:
        """
        解析实现方式
        
        Returns:
            Implementation(
                implementation_type: "table_calc" | "lod",
                addressing_dimensions: List[str]
            )
        """
        # 1. 判断是否需要 LOD
        if self._needs_lod(analysis, view_dimensions):
            return self._resolve_lod(analysis, mapped_fields)
        
        # 2. 表计算：解析 addressing
        addressing = self._resolve_addressing(analysis, dimensions, mapped_fields)
        
        return Implementation(
            implementation_type="table_calc",
            addressing_dimensions=addressing
        )
    
    def _needs_lod(self, analysis: AnalysisSpec, view_dimensions: List[str]) -> bool:
        """判断是否需要 LOD"""
        # 规则 1: requires_external_dimension=True → LOD
        if analysis.requires_external_dimension:
            return True
        
        # 规则 2: aggregation_at_level 且 target_granularity 不在视图维度中 → LOD
        if analysis.type == AnalysisType.AGGREGATION_AT_LEVEL:
            if analysis.target_granularity:
                for dim in analysis.target_granularity:
                    if dim not in view_dimensions:
                        return True
        
        return False
    
    def _resolve_addressing(
        self,
        analysis: AnalysisSpec,
        dimensions: List[DimensionSpec],
        mapped_fields: Dict[str, str]
    ) -> List[str]:
        """解析 addressing 维度"""
        # 规则 1: 用户显式指定 along_dimension
        if analysis.along_dimension:
            return [mapped_fields[analysis.along_dimension]]
        
        # 规则 2: 单维度 → addressing = 该维度
        if len(dimensions) == 1:
            return [mapped_fields[dimensions[0].name]]
        
        # 规则 3: 多维度 + computation_scope
        if analysis.computation_scope == ComputationScope.PER_GROUP:
            # per_group: addressing = 时间维度（最细粒度）
            time_dims = [d for d in dimensions if d.is_time]
            if time_dims:
                return [mapped_fields[time_dims[0].name]]
            # 无时间维度：取最后一个维度
            return [mapped_fields[dimensions[-1].name]]
        
        elif analysis.computation_scope == ComputationScope.ACROSS_ALL:
            # across_all: addressing = 所有维度
            return [mapped_fields[d.name] for d in dimensions]
        
        # 规则 4: 默认按分析类型推断
        return self._infer_addressing_by_type(analysis, dimensions, mapped_fields)
    
    def _infer_addressing_by_type(
        self,
        analysis: AnalysisSpec,
        dimensions: List[DimensionSpec],
        mapped_fields: Dict[str, str]
    ) -> List[str]:
        """根据分析类型推断 addressing"""
        time_dims = [d for d in dimensions if d.is_time]
        non_time_dims = [d for d in dimensions if not d.is_time]
        
        if analysis.type in [AnalysisType.CUMULATIVE, AnalysisType.MOVING, AnalysisType.PERIOD_COMPARE]:
            # 累计/移动/同比环比 → 沿时间维度
            if time_dims:
                return [mapped_fields[time_dims[0].name]]
        
        elif analysis.type in [AnalysisType.RANKING, AnalysisType.PERCENTAGE]:
            # 排名/占比 → 沿非时间维度
            if non_time_dims:
                return [mapped_fields[non_time_dims[0].name]]
        
        # 默认：所有维度
        return [mapped_fields[d.name] for d in dimensions]
```

---

## 3. ExpressionGenerator

### 职责

- 根据分析类型生成 VizQL 表达式
- 100% 确定性代码模板

### 实现

```python
# tableau_assistant/src/components/expression_generator/generator.py

class ExpressionGenerator:
    """
    表达式生成器（代码模板）
    """
    
    def generate(
        self,
        analysis: AnalysisSpec,
        implementation: Implementation,
        technical_field: str
    ) -> str:
        """生成 VizQL 表达式"""
        agg = analysis.aggregation.upper()
        field_ref = f"[{technical_field}]"
        
        if implementation.implementation_type == "lod":
            return self._generate_lod(analysis, technical_field)
        
        return self._generate_table_calc(analysis, agg, field_ref)
    
    def _generate_table_calc(
        self,
        analysis: AnalysisSpec,
        agg: str,
        field_ref: str
    ) -> str:
        """生成表计算表达式"""
        templates = EXPRESSION_TEMPLATES[analysis.type]
        
        if analysis.type == AnalysisType.CUMULATIVE:
            return templates["sum"].format(agg=agg, field=field_ref)
        
        elif analysis.type == AnalysisType.MOVING:
            window = analysis.window_size or 3
            return templates["avg"].format(
                agg=agg, field=field_ref, start=-(window-1), end=0
            )
        
        elif analysis.type == AnalysisType.RANKING:
            order = analysis.order or "desc"
            return templates["default"].format(agg=agg, field=field_ref, order=order)
        
        elif analysis.type == AnalysisType.PERCENTAGE:
            return templates["default"].format(agg=agg, field=field_ref)
        
        elif analysis.type == AnalysisType.PERIOD_COMPARE:
            offset = self._get_period_offset(analysis.compare_type)
            return templates["rate"].format(agg=agg, field=field_ref, offset=offset)
        
        raise ValueError(f"Unsupported analysis type: {analysis.type}")
    
    def _generate_lod(self, analysis: AnalysisSpec, technical_field: str) -> str:
        """生成 LOD 表达式"""
        agg = analysis.aggregation.upper()
        dims = analysis.target_granularity or []
        
        if not dims:
            # 全局聚合
            return f"{{FIXED : {agg}([{technical_field}])}}"
        
        dim_str = ", ".join(f"[{d}]" for d in dims)
        return f"{{FIXED {dim_str} : {agg}([{technical_field}])}}"
    
    def _get_period_offset(self, compare_type: str) -> int:
        """获取周期偏移量"""
        offsets = {
            "yoy": -12,   # 同比（年）
            "mom": -1,    # 环比（月）
            "wow": -1,    # 环比（周）
            "dod": -1,    # 环比（日）
            "prev": -1,   # 上期
        }
        return offsets.get(compare_type, -1)
```

### 表达式模板

```python
# tableau_assistant/src/components/expression_generator/templates.py

EXPRESSION_TEMPLATES = {
    AnalysisType.CUMULATIVE: {
        "sum": "RUNNING_SUM({agg}({field}))",
        "avg": "RUNNING_AVG({agg}({field}))",
        "min": "RUNNING_MIN({agg}({field}))",
        "max": "RUNNING_MAX({agg}({field}))",
        "count": "RUNNING_COUNT({agg}({field}))",
    },
    AnalysisType.MOVING: {
        "sum": "WINDOW_SUM({agg}({field}), {start}, {end})",
        "avg": "WINDOW_AVG({agg}({field}), {start}, {end})",
        "min": "WINDOW_MIN({agg}({field}), {start}, {end})",
        "max": "WINDOW_MAX({agg}({field}), {start}, {end})",
        "count": "WINDOW_COUNT({agg}({field}), {start}, {end})",
    },
    AnalysisType.RANKING: {
        "default": "RANK({agg}({field}), '{order}')",
        "dense": "RANK_DENSE({agg}({field}), '{order}')",
        "percentile": "RANK_PERCENTILE({agg}({field}), '{order}')",
    },
    AnalysisType.PERCENTAGE: {
        "default": "{agg}({field}) / TOTAL({agg}({field}))",
    },
    AnalysisType.PERIOD_COMPARE: {
        "diff": "{agg}({field}) - LOOKUP({agg}({field}), {offset})",
        "rate": "({agg}({field}) - LOOKUP({agg}({field}), {offset})) / ABS(LOOKUP({agg}({field}), {offset}))",
    },
}
```
