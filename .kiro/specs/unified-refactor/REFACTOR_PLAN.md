# Capabilities 包重构计划

## 问题总结

### 🔴 严重问题

1. **文件放错位置**
   - `metadata/vizql_query.py` - 查询中间件放在 metadata 包中
   - `metadata/tool.py` - 元数据中间件，但与 `query/get_metadata.py` 功能重复

2. **代码重复**
   - `metadata/tool.py` vs `query/get_metadata.py` - 都是获取元数据的工具
   - `metadata/vizql_query.py` vs `query/tool.py` - 都是执行查询的工具

3. **导入路径错误**
   - `src/tools/factory.py` 中的路径与实际不匹配

### 🟡 中等问题

4. **包命名不一致**
   - `date_processing` 应该是 `date`
   - `data_processing` 应该是 `data`
   - `semantic_mapping` 应该是 `semantic`

5. **Middleware 模式与 Tool 模式混用**
   - 应该统一使用 `@tool` 装饰器模式

6. **`__init__.py` 文件为空**
   - 没有导出任何内容

## 重构方案

### 阶段 1: 删除重复代码

删除以下文件（未被任何代码引用）：
- `capabilities/metadata/tool.py`
- `capabilities/metadata/vizql_query.py`

### 阶段 2: 修复导入路径

更新 `src/tools/factory.py` 中的导入路径：
```python
# 错误
from tableau_assistant.src.capabilities.date.manager import DateManager
from tableau_assistant.src.capabilities.semantic.mapper import SemanticMapper
from tableau_assistant.src.capabilities.data.processor import DataProcessor
from tableau_assistant.src.capabilities.statistics.detector import StatisticsDetector

# 正确
from tableau_assistant.src.capabilities.date_processing.manager import DateManager
from tableau_assistant.src.capabilities.semantic_mapping.semantic_mapper import SemanticMapper
from tableau_assistant.src.capabilities.data_processing.processor import DataProcessor
from tableau_assistant.src.capabilities.data_processing.statistics import StatisticsDetector
```

### 阶段 3: 完善 `__init__.py` 导出

为每个包添加清晰的导出。

### 阶段 4: 统一工具模式（可选）

将所有工具统一到 `src/tools/` 目录，使用 `@tool` 装饰器模式。

## 依赖关系

### `date_processing` 包被以下文件引用：
- `tests/test_string_date_filter_builder.py`
- `tests/test_query_builder_string_date.py`
- `tests/test_date_manager.py`
- `tests/test_date_format_properties.py`
- `src/models/time_granularity.py`
- `src/capabilities/date_processing/__init__.py`
- `src/capabilities/date_processing/parser.py`
- `src/capabilities/date_processing/manager.py`
- `src/capabilities/query/builder/string_date_filter_builder.py`
- `src/capabilities/metadata/manager.py`
- `src/capabilities/query/builder/builder.py`
- `src/capabilities/query/builder/date_filter_converter.py`

### `metadata/tool.py` 和 `metadata/vizql_query.py` 被引用：
- **无引用** - 可以安全删除

## 执行顺序

1. ✅ 删除 `metadata/tool.py`
2. ✅ 删除 `metadata/vizql_query.py`
3. ✅ 修复 `src/tools/factory.py` 导入路径
4. ✅ 完善各包的 `__init__.py`
5. ✅ 运行测试验证
