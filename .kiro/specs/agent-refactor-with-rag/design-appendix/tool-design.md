# 工具层设计

## 概述

本文档描述工具层的详细设计，包括所有业务工具和工具注册表。

对应项目结构：`src/tools/`

---

## 工具分类

| 类型 | 说明 | 示例 |
|------|------|------|
| 业务工具 | 我们实现的工具，封装现有组件 | get_metadata, parse_date, get_schema_module |
| 中间件工具 | 由中间件自动注入的工具 | write_todos, read_file |

---

## 1. 工具注册表

```python
# tableau_assistant/src/tools/registry.py

class ToolRegistry:
    """
    工具注册表
    
    管理业务工具的注册。
    注意：中间件提供的工具（如 write_todos）由中间件自动注入，不在此注册。
    """
    
    _tools: Dict[str, List[BaseTool]] = {
        "boost": [],
        "understanding": [],
        "query_builder": [],
        "insight": [],
        "replanner": [],
    }
    
    @classmethod
    def register(cls, node_type: str, tool: BaseTool):
        """注册工具到指定节点"""
        cls._tools[node_type].append(tool)
    
    @classmethod
    def get_tools(cls, node_type: str) -> List[BaseTool]:
        """获取节点的工具列表"""
        return cls._tools.get(node_type, [])
    
    @classmethod
    def auto_discover(cls):
        """自动发现并注册业务工具"""
        # boost_tools
        cls.register("boost", get_metadata)
        
        # understanding_tools
        cls.register("understanding", get_schema_module)
        cls.register("understanding", parse_date)
        cls.register("understanding", detect_date_format)
        
        # query_builder_tools (用于 FieldMapper 组件)
        cls.register("query_builder", semantic_map_fields)
        
        # replanner_tools
        # 注意：write_todos 由 TodoListMiddleware 自动注入
```

---

## 2. 元数据工具

```python
# tableau_assistant/src/tools/metadata_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.metadata import MetadataManager


@tool
async def get_metadata(
    use_cache: bool = True,
    enhance: bool = True,
    filter_role: Optional[str] = None,
    filter_category: Optional[str] = None
) -> str:
    """
    获取数据源元数据
    
    Args:
        use_cache: 是否使用缓存 (默认 True)
        enhance: 是否增强元数据 (默认 True)
        filter_role: 按角色过滤 (dimension/measure)
        filter_category: 按类别过滤
    
    Returns:
        LLM 友好的字段列表（全量返回，大结果由 FilesystemMiddleware 处理）
    """
    metadata = await metadata_manager.get_metadata_async(
        use_cache=use_cache,
        enhance=enhance
    )
    
    # 应用过滤
    fields = metadata.fields
    if filter_role:
        fields = [f for f in fields if f.role == filter_role]
    if filter_category:
        fields = [f for f in fields if f.category == filter_category]
    
    # 转换为 LLM 友好格式（全量返回）
    return _format_metadata_for_llm(fields)
```

---

## 3. 日期工具

```python
# tableau_assistant/src/tools/date_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.date_processing import DateManager


@tool
def parse_date(
    expression: str,
    reference_date: Optional[str] = None
) -> Dict[str, Any]:
    """
    解析日期表达式
    
    Args:
        expression: 日期表达式 (如 "最近3个月", "2024年1月")
        reference_date: 参考日期 (默认当前日期)
    
    Returns:
        {"start_date": "YYYY-MM-DD", "end_date": "YYYY-MM-DD"} 或 {"error": "..."}
    """
    try:
        time_range = _parse_expression_to_time_range(expression)
        start, end = date_manager.parse_time_range(time_range, reference_date)
        return {"start_date": start, "end_date": end}
    except Exception as e:
        return {"start_date": None, "end_date": None, "error": str(e)}


@tool
def detect_date_format(sample_values: List[str]) -> Dict[str, Any]:
    """
    检测日期格式
    
    Args:
        sample_values: 样本值列表
    
    Returns:
        {"format_type": "ISO_DATE", "pattern": "YYYY-MM-DD", "conversion_hint": "..."}
    """
    format_type = date_manager.detect_field_date_format(sample_values)
    if format_type:
        info = date_manager.get_format_info(format_type)
        return {
            "format_type": format_type.value,
            "pattern": info["pattern"],
            "conversion_hint": f"使用 {info['pattern']} 格式解析"
        }
    return {"format_type": None, "error": "无法检测日期格式"}
```

---

## 4. RAG 工具

```python
# tableau_assistant/src/tools/rag_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.rag import SemanticMapper


@tool
async def semantic_map_fields(
    business_terms: List[str],
    context: Optional[str] = None
) -> List[Dict[str, Any]]:
    """
    将业务术语映射到技术字段
    
    Args:
        business_terms: 业务术语列表
        context: 问题上下文
    
    Returns:
        映射结果列表，每个包含 matched_field, confidence, alternatives
    """
    results = await semantic_mapper.map_fields_batch(business_terms, context)
    return [
        {
            "term": r.term,
            "matched_field": r.matched_field.fieldCaption if r.matched_field else None,
            "confidence": r.confidence,
            "category": r.matched_field.category if r.matched_field else None,
            "level": r.matched_field.level if r.matched_field else None,
            "alternatives": [
                {"field": a.field.fieldCaption, "score": a.score}
                for a in r.alternatives[:3]
            ] if r.confidence < 0.7 else []
        }
        for r in results
    ]
```

---

## 5. Schema 模块选择工具

```python
# tableau_assistant/src/tools/schema_tool.py

from langchain_core.tools import tool
from tableau_assistant.src.capabilities.schema.registry import SchemaModuleRegistry


@tool
def get_schema_module(module_names: List[str]) -> str:
    """
    获取指定数据模型模块的详细填写规则。
    
    在生成结构化输出之前调用此工具，只获取你需要的模块！
    这样可以减少 token 消耗，提高响应速度。
    
    Args:
        module_names: 需要的模块列表，可选值:
            - measures: 度量字段（销售额、利润等数值）
            - dimensions: 维度字段（分组、分类）
            - date_fields: 日期分组字段（按年、按月）
            - date_filters: 日期筛选条件（2024年、最近3个月）
            - filters: 非日期筛选条件（华东地区、销售额>1000）
            - topn: TopN 筛选（前10名、TOP5）
            - table_calcs: 表计算（累计、排名、占比）
    
    Returns:
        所选模块的详细填写规则
    """
    valid_modules = SchemaModuleRegistry.get_all_module_names()
    invalid_modules = [m for m in module_names if m not in valid_modules]
    
    if invalid_modules:
        return f"<error>无效的模块名称: {invalid_modules}。可用模块: {valid_modules}</error>"
    
    return SchemaModuleRegistry.get_modules(module_names)
```

### Schema 模块注册表

```python
# tableau_assistant/src/capabilities/schema/registry.py

SCHEMA_MODULES = {
    "measures": SchemaModule(
        name="measures",
        description="度量字段（销售额、利润等数值概念）",
        content="..."  # 详细填写规则
    ),
    "dimensions": SchemaModule(
        name="dimensions",
        description="维度字段（分组、分类概念）",
        content="..."
    ),
    "date_fields": SchemaModule(
        name="date_fields",
        description="日期分组字段（按年、按月）",
        content="..."
    ),
    "date_filters": SchemaModule(
        name="date_filters",
        description="日期筛选条件（2024年、最近3个月）",
        content="..."
    ),
    "filters": SchemaModule(
        name="filters",
        description="非日期筛选条件（华东地区、销售额>1000）",
        content="..."
    ),
    "topn": SchemaModule(
        name="topn",
        description="TopN 筛选（前10名、TOP5）",
        content="..."
    ),
    "table_calcs": SchemaModule(
        name="table_calcs",
        description="表计算（累计、排名、占比）",
        content="..."
    ),
}
```

### Token 节省效果

```
传统方式（全量注入）：
  Prompt = 系统指令 + 完整 Schema（所有模块）+ 用户问题
  Token 消耗: ~1400 tokens

新方式（按需拉取）：
  Prompt = 系统指令 + 模块索引（只有名称和简介）+ 用户问题
  LLM 调用 get_schema_module(["measures", "dimensions"])
  Token 消耗: ~600 tokens

节省: ~57%
```
