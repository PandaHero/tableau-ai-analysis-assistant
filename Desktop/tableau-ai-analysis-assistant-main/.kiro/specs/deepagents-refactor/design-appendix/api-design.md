# API设计详细文档

## 概述

本文档定义DeepAgent系统的REST API接口，包括同步和流式两种模式。

**设计原则**：
- ✅ **RESTful** - 遵循REST API设计规范
- ✅ **流式支持** - 支持SSE流式响应，提升用户体验
- ✅ **错误处理** - 统一的错误响应格式
- ✅ **版本控制** - API版本化，便于升级

---

## 1. API端点概览

| 端点 | 方法 | 描述 | 响应类型 |
|------|------|------|----------|
| `/api/v1/chat` | POST | 同步查询 | JSON |
| `/api/v1/chat/stream` | POST | 流式查询 | SSE |
| `/api/v1/health` | GET | 健康检查 | JSON |
| `/api/v1/datasources` | GET | 获取数据源列表 | JSON |
| `/api/v1/datasources/{luid}/metadata` | GET | 获取数据源元数据 | JSON |
| `/api/v1/threads/{thread_id}/history` | GET | 获取会话历史 | JSON |

---

## 2. 数据模型

### 2.1 请求模型

```python
from pydantic import BaseModel, Field
from typing import Optional, Dict, List

class ChatRequest(BaseModel):
    """聊天请求"""
    
    question: str = Field(
        description="用户问题",
        example="华东地区的销售趋势如何？"
    )
    
    datasource_luid: str = Field(
        description="数据源LUID",
        example="abc123-def456-ghi789"
    )
    
    boost_question: bool = Field(
        default=False,
        description="是否优化问题"
    )
    
    thread_id: Optional[str] = Field(
        default=None,
        description="会话ID（用于多轮对话）"
    )
    
    model_config: Optional[Dict] = Field(
        default=None,
        description="模型配置"
    )
    
    # 示例
    class Config:
        json_schema_extra = {
            "example": {
                "question": "华东地区的销售趋势如何？",
                "datasource_luid": "abc123-def456-ghi789",
                "boost_question": False,
                "thread_id": None,
                "model_config": {
                    "temperature": 0.0,
                    "max_tokens": 4000
                }
            }
        }
```

### 2.2 响应模型

```python
class Insight(BaseModel):
    """洞察"""
    type: str = Field(description="洞察类型")
    title: str = Field(description="洞察标题")
    description: str = Field(description="洞察描述")
    evidence: List[str] = Field(description="支持证据")
    confidence: float = Field(ge=0.0, le=1.0, description="置信度")
    importance: float = Field(ge=0.0, le=1.0, description="重要性")

class Recommendation(BaseModel):
    """建议"""
    type: str = Field(description="建议类型")
    priority: str = Field(description="优先级")
    description: str = Field(description="建议描述")
    rationale: str = Field(description="理由")

class PerformanceMetrics(BaseModel):
    """性能指标"""
    total_time: float = Field(description="总耗时（秒）")
    llm_calls: int = Field(description="LLM调用次数")
    total_tokens: int = Field(description="总Token数")
    cache_hit_rate: float = Field(description="缓存命中率")
    cost_estimate: float = Field(description="成本估算（美元）")

class ChatResponse(BaseModel):
    """聊天响应"""
    
    executive_summary: str = Field(description="执行摘要")
    
    key_findings: List[str] = Field(description="关键发现")
    
    insights: List[Insight] = Field(description="洞察列表")
    
    recommendations: List[Recommendation] = Field(description="建议列表")
    
    performance_metrics: PerformanceMetrics = Field(description="性能指标")
    
    thread_id: str = Field(description="会话ID")
    
    # 示例
    class Config:
        json_schema_extra = {
            "example": {
                "executive_summary": "基于对华东地区销售数据的分析...",
                "key_findings": [
                    "华东地区销售额呈上升趋势，Q3较Q1增长50%",
                    "上海市贡献了华东地区60%的销售额"
                ],
                "insights": [
                    {
                        "type": "trend",
                        "title": "华东地区销售额上升",
                        "description": "华东地区销售额从Q1的100万增长到Q3的150万",
                        "evidence": ["Q1: 100万", "Q2: 120万", "Q3: 150万"],
                        "confidence": 0.95,
                        "importance": 0.9
                    }
                ],
                "recommendations": [
                    {
                        "type": "business_action",
                        "priority": "high",
                        "description": "加大华东地区市场投入",
                        "rationale": "销售额持续上升，市场潜力大"
                    }
                ],
                "performance_metrics": {
                    "total_time": 5.2,
                    "llm_calls": 3,
                    "total_tokens": 5000,
                    "cache_hit_rate": 0.6,
                    "cost_estimate": 0.015
                },
                "thread_id": "thread_abc123"
            }
        }
```

---

