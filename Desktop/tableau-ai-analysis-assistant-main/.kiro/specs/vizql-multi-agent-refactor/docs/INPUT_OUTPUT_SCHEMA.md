# Input/Output Schema 使用指南

## 概述

本文档说明如何使用LangGraph 1.0的`input_schema`和`output_schema`特性，实现自动验证和类型安全。

## 为什么使用input/output_schema？

### 优势

1. **自动验证** - LangGraph自动验证输入输出格式，无需手动检查
2. **类型安全** - TypedDict提供编译时类型检查
3. **自动文档** - FastAPI自动生成OpenAPI文档
4. **错误提示** - 验证失败时提供详细的错误信息
5. **IDE支持** - 完整的代码补全和类型提示

### 与传统方式对比

**传统方式（无schema）**：
```python
# 需要手动验证
def my_workflow(input_data: dict):
    if "question" not in input_data:
        raise ValueError("question is required")
    if not isinstance(input_data["question"], str):
        raise ValueError("question must be string")
    # ... 更多验证代码
```

**使用schema**：
```python
# 自动验证
class MyInput(TypedDict):
    question: str

graph = StateGraph(
    state_schema=MyState,
    input_schema=MyInput  # ← 自动验证
)
```

## 实现方式

### 1. 定义Schema

在`tableau_assistant/src/models/state.py`中定义：

```python
from typing import TypedDict, List, Dict, Any

class VizQLInput(TypedDict):
    """工作流输入schema"""
    question: str  # 用户问题
    boost_question: bool  # 是否使用问题Boost

class VizQLOutput(TypedDict):
    """工作流输出schema"""
    final_report: Dict[str, Any]  # 最终报告
    executive_summary: str  # 执行摘要
    key_findings: List[str]  # 关键发现
    analysis_path: List[Dict[str, Any]]  # 分析路径
    recommendations: List[str]  # 后续建议
    visualizations: List[Dict[str, Any]]  # 可视化数据
```

### 2. 在StateGraph中使用

```python
from langgraph.graph import StateGraph

graph = StateGraph(
    state_schema=VizQLState,
    context_schema=VizQLContext,
    input_schema=VizQLInput,  # ← 输入验证
    output_schema=VizQLOutput  # ← 输出验证
)
```

### 3. 自动验证

```python
# 正确的输入 - 验证通过
input_data = {
    "question": "2016年各地区的销售额",
    "boost_question": False
}
result = app.invoke(input_data, config)  # ✓ 验证通过

# 错误的输入 - 验证失败
input_data = {
    "boost_question": False
    # 缺少question字段
}
result = app.invoke(input_data, config)  # ✗ 抛出ValidationError
```

## API层集成

### 1. 定义Pydantic模型

在`tableau_assistant/src/models/api.py`中定义：

```python
from pydantic import BaseModel, Field

class VizQLQueryRequest(BaseModel):
    """API请求模型"""
    question: str = Field(
        ...,
        description="用户问题",
        min_length=1,
        max_length=1000
    )
    datasource_luid: str = Field(
        ...,
        description="数据源LUID"
    )
    boost_question: bool = Field(
        default=False,
        description="是否使用问题Boost"
    )

class VizQLQueryResponse(BaseModel):
    """API响应模型"""
    executive_summary: str
    key_findings: List[KeyFinding]
    analysis_path: List[AnalysisStep]
    recommendations: List[Recommendation]
    visualizations: List[Visualization]
    metadata: Dict[str, Any]
```

### 2. 在FastAPI中使用

```python
from fastapi import APIRouter, HTTPException

@router.post("/chat", response_model=VizQLQueryResponse)
async def chat_query(request: VizQLQueryRequest) -> VizQLQueryResponse:
    """
    VizQL查询API
    
    FastAPI自动：
    - 验证请求格式（基于VizQLQueryRequest）
    - 生成OpenAPI文档
    - 验证响应格式（基于VizQLQueryResponse）
    """
    # 执行工作流
    result = run_vizql_workflow_sync(
        question=request.question,
        datasource_luid=request.datasource_luid,
        boost_question=request.boost_question
    )
    
    # 返回响应（自动验证）
    return VizQLQueryResponse(**result)
```

## 验证流程

### 输入验证流程

```
用户请求
  ↓
FastAPI验证（Pydantic模型）
  ↓ 验证通过
转换为TypedDict
  ↓
LangGraph验证（input_schema）
  ↓ 验证通过
执行工作流
```

### 输出验证流程

```
工作流执行完成
  ↓
LangGraph验证（output_schema）
  ↓ 验证通过
转换为Pydantic模型
  ↓
FastAPI验证（response_model）
  ↓ 验证通过
返回给用户
```

## 错误处理

### 输入验证错误

```python
try:
    result = app.invoke(input_data, config)
except ValidationError as e:
    # 捕获验证错误
    print(f"输入验证失败: {e}")
    # 返回详细错误信息
    return ErrorResponse(
        error="ValidationError",
        message="输入格式不正确",
        details=[
            {
                "code": err["type"],
                "message": err["msg"],
                "field": err["loc"][0]
            }
            for err in e.errors()
        ]
    )
```

### 输出验证错误

```python
try:
    result = app.invoke(input_data, config)
    # 验证输出格式
    validated_output = VizQLOutput(**result)
except ValidationError as e:
    # 输出格式不正确
    print(f"输出验证失败: {e}")
    # 记录错误日志
    logger.error(f"工作流输出格式错误: {e}")
```

## 最佳实践

### 1. 使用明确的字段类型

```python
# ✓ 好的做法
class MyInput(TypedDict):
    question: str  # 明确类型
    count: int  # 明确类型
    enabled: bool  # 明确类型

# ✗ 不好的做法
class MyInput(TypedDict):
    data: Any  # 类型不明确
```

### 2. 使用Optional标记可选字段

```python
from typing import Optional

class MyInput(TypedDict):
    question: str  # 必需字段
    user_id: Optional[str]  # 可选字段
```

### 3. 使用Annotated添加元数据

```python
from typing import Annotated

class MyInput(TypedDict):
    question: Annotated[str, "用户问题"]
    count: Annotated[int, "数量限制"]
```

### 4. 分离API模型和工作流模型

```python
# API模型（Pydantic） - 用于FastAPI
class VizQLQueryRequest(BaseModel):
    question: str = Field(..., min_length=1)
    datasource_luid: str

# 工作流模型（TypedDict） - 用于LangGraph
class VizQLInput(TypedDict):
    question: str
    boost_question: bool
```

### 5. 提供详细的文档

```python
class VizQLInput(TypedDict):
    """
    VizQL工作流输入
    
    Attributes:
        question: 用户问题（必需）
        boost_question: 是否使用问题Boost（可选，默认False）
    """
    question: str
    boost_question: bool
```

## 测试

### 单元测试

```python
import pytest
from pydantic import ValidationError

def test_input_validation():
    """测试输入验证"""
    # 正确的输入
    valid_input = VizQLInput(
        question="2016年各地区的销售额",
        boost_question=False
    )
    assert valid_input["question"] == "2016年各地区的销售额"
    
    # 错误的输入
    with pytest.raises(ValidationError):
        invalid_input = VizQLInput(
            boost_question=False
            # 缺少question字段
        )

def test_output_validation():
    """测试输出验证"""
    # 正确的输出
    valid_output = VizQLOutput(
        final_report={},
        executive_summary="摘要",
        key_findings=[],
        analysis_path=[],
        recommendations=[],
        visualizations=[]
    )
    assert valid_output["executive_summary"] == "摘要"
    
    # 错误的输出
    with pytest.raises(ValidationError):
        invalid_output = VizQLOutput(
            final_report={}
            # 缺少其他必需字段
        )
```

### 集成测试

```python
def test_workflow_with_schema():
    """测试工作流的输入输出验证"""
    app = create_vizql_workflow()
    
    # 测试正确的输入
    input_data = {
        "question": "2016年各地区的销售额",
        "boost_question": False
    }
    result = app.invoke(input_data, config)
    
    # 验证输出格式
    assert "final_report" in result
    assert "executive_summary" in result
    assert isinstance(result["key_findings"], list)
```

## 常见问题

### Q1: TypedDict vs Pydantic BaseModel？

**A**: 
- **TypedDict**: 用于LangGraph的schema定义，轻量级，只提供类型提示
- **Pydantic BaseModel**: 用于FastAPI的模型定义，提供运行时验证和序列化

### Q2: 如何处理嵌套结构？

**A**: 使用嵌套的TypedDict或Pydantic模型：

```python
class KeyFinding(BaseModel):
    finding: str
    importance: str

class VizQLQueryResponse(BaseModel):
    key_findings: List[KeyFinding]  # 嵌套模型
```

### Q3: 如何添加自定义验证？

**A**: 在Pydantic模型中使用validator：

```python
from pydantic import validator

class VizQLQueryRequest(BaseModel):
    question: str
    
    @validator("question")
    def validate_question(cls, v):
        if len(v) < 5:
            raise ValueError("问题太短")
        return v
```

### Q4: 如何生成示例数据？

**A**: 使用Pydantic的Config.json_schema_extra：

```python
class VizQLQueryRequest(BaseModel):
    question: str
    
    class Config:
        json_schema_extra = {
            "example": {
                "question": "2016年各地区的销售额"
            }
        }
```

## 参考资料

- [LangGraph 1.0 文档](https://langchain-ai.github.io/langgraph/)
- [Pydantic 文档](https://docs.pydantic.dev/)
- [FastAPI 文档](https://fastapi.tiangolo.com/)
- [TypedDict 文档](https://docs.python.org/3/library/typing.html#typing.TypedDict)

## 总结

使用`input_schema`和`output_schema`可以：

1. ✅ **自动验证** - 减少手动验证代码
2. ✅ **类型安全** - 编译时类型检查
3. ✅ **自动文档** - 生成OpenAPI文档
4. ✅ **错误提示** - 详细的验证错误信息
5. ✅ **IDE支持** - 完整的代码补全

这是LangGraph 1.0的重要特性，强烈推荐在生产环境中使用。
