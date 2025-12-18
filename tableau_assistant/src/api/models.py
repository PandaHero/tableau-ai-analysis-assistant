"""
API输入输出模型定义

使用Pydantic定义API的输入输出类型，提供：
- 自动验证
- 自动文档生成
- 类型安全

注意：这些模型是平台无关的，不包含任何 BI 平台特定的概念。
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional


# ========== API输入模型 ==========

class ChatRequest(BaseModel):
    """
    聊天查询请求
    
    用于 POST /api/chat 和 POST /api/chat/stream 端点
    
    支持两种数据源指定方式：
    1. datasource_luid: 直接指定 LUID（优先）
    2. datasource_name: 指定名称，后端自动转换为 LUID
    """
    question: str = Field(
        ...,
        description="用户问题",
        min_length=1,
        max_length=1000,
        examples=["2016年各地区的销售额是多少？"]
    )
    
    datasource_luid: Optional[str] = Field(
        default=None,
        description="数据源LUID（优先使用）",
        examples=["abc123-def456-ghi789"]
    )
    
    datasource_name: Optional[str] = Field(
        default=None,
        description="数据源名称（如果未提供 LUID，则使用名称查找）",
        examples=["销售分析数据源"]
    )
    
    user_id: Optional[str] = Field(
        default=None,
        description="用户ID（可选，用于个性化）"
    )
    
    session_id: Optional[str] = Field(
        default=None,
        description="会话ID（可选，用于对话历史）"
    )
    
    analysis_depth: Optional[str] = Field(
        default="detailed",
        description="分析深度：detailed（标准）或 comprehensive（深入）"
    )
    
    language: Optional[str] = Field(
        default="zh",
        description="响应语言：zh（中文）或 en（英文）"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "2016年各地区的销售额是多少？",
                "datasource_name": "销售分析数据源",
                "user_id": "user_456",
                "session_id": "session_789",
                "analysis_depth": "detailed",
                "language": "zh"
            }
        }
    )


# ========== API输出模型 ==========

class KeyFinding(BaseModel):
    """Key finding"""
    finding: str = Field(..., description="Finding content")
    importance: str = Field(..., description="Importance (high/medium/low)")
    category: str = Field(..., description="Category (trend/anomaly/comparison etc.)")


class AnalysisStep(BaseModel):
    """Analysis step"""
    step_number: int = Field(..., description="Step number")
    agent_name: str = Field(..., description="Agent name")
    description: str = Field(..., description="Step description")
    duration_ms: Optional[int] = Field(None, description="Execution time (milliseconds)")


class Recommendation(BaseModel):
    """Follow-up recommendation"""
    question: str = Field(..., description="Recommended question")
    reason: str = Field(..., description="Recommendation reason")
    priority: str = Field(..., description="Priority (high/medium/low)")


class Visualization(BaseModel):
    """Visualization data"""
    viz_type: str = Field(..., description="Visualization type (table/bar/line etc.)")
    title: str = Field(..., description="Title")
    data: Dict[str, Any] = Field(..., description="Data")
    config: Optional[Dict[str, Any]] = Field(None, description="Configuration")


class ChatResponse(BaseModel):
    """
    聊天查询响应
    
    用于 POST /api/chat 端点的最终响应
    """
    executive_summary: str = Field(
        ...,
        description="执行摘要（一句话回答）"
    )
    
    key_findings: List[KeyFinding] = Field(
        default_factory=list,
        description="关键发现列表"
    )
    
    analysis_path: List[AnalysisStep] = Field(
        default_factory=list,
        description="分析路径（展示分析过程）"
    )
    
    recommendations: List[Recommendation] = Field(
        default_factory=list,
        description="后续探索建议"
    )
    
    visualizations: List[Visualization] = Field(
        default_factory=list,
        description="可视化数据"
    )
    
    metadata: Dict[str, Any] = Field(
        default_factory=dict,
        description="元数据（token消耗、执行时间等）"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "executive_summary": "2016年华东地区销售额最高（500万），但利润率偏低（5%）",
                "key_findings": [
                    {
                        "finding": "华东地区销售额500万，占总销售额的40%",
                        "importance": "high",
                        "category": "comparison"
                    }
                ],
                "analysis_path": [
                    {
                        "step_number": 1,
                        "agent_name": "问题理解Agent",
                        "description": "识别为对比类问题",
                        "duration_ms": 1500
                    }
                ],
                "recommendations": [
                    {
                        "question": "华东地区各产品类别的利润率分别是多少？",
                        "reason": "发现华东地区利润率异常低",
                        "priority": "high"
                    }
                ],
                "visualizations": [
                    {
                        "viz_type": "bar",
                        "title": "2016年各地区销售额",
                        "data": {"地区": ["华东", "华北"], "销售额": [500, 300]},
                        "config": {"sort": "desc"}
                    }
                ],
                "metadata": {
                    "token_count": 15000,
                    "execution_time_ms": 8500,
                    "llm_calls": 5
                }
            }
        }
    )


# ========== Error Response Models ==========

class ErrorDetail(BaseModel):
    """Error detail"""
    code: str = Field(..., description="Error code")
    message: str = Field(..., description="Error message")
    field: Optional[str] = Field(None, description="Error field (if validation error)")


class ErrorResponse(BaseModel):
    """
    错误响应
    
    统一的错误响应格式
    """
    error: str = Field(..., description="错误类型")
    message: str = Field(..., description="错误消息")
    details: Optional[List[ErrorDetail]] = Field(None, description="错误详情")
    request_id: Optional[str] = Field(None, description="请求ID（用于追踪）")
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "error": "ValidationError",
                "message": "请求参数验证失败",
                "details": [
                    {
                        "code": "value_error.missing",
                        "message": "question字段不能为空",
                        "field": "question"
                    }
                ],
                "request_id": "req_123456"
            }
        }
    )


# ========== 流式事件模型 ==========

class StreamEvent(BaseModel):
    """
    流式事件
    
    用于SSE流式输出
    """
    event_type: str = Field(
        ...,
        description="事件类型（token/agent_start/agent_complete/query_start/query_complete/error/done）"
    )
    
    data: Dict[str, Any] = Field(
        default_factory=dict,
        description="事件数据"
    )
    
    timestamp: float = Field(
        ...,
        description="时间戳"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "event_type": "token",
                "data": {"content": "2016年"},
                "timestamp": 1698765432.123
            }
        }
    )


# 向后兼容别名（将在未来版本移除）
VizQLQueryRequest = ChatRequest
VizQLQueryResponse = ChatResponse


# 示例用法
if __name__ == "__main__":
    # 创建请求示例
    request = ChatRequest(
        question="2016年各地区的销售额是多少？",
        datasource_luid="abc123",
        user_id="user_456",
        session_id="session_789"
    )
    
    print("请求示例:")
    print(request.model_dump_json(indent=2))
    
    # 创建响应示例
    response = ChatResponse(
        executive_summary="2016年华东地区销售额最高",
        key_findings=[
            KeyFinding(
                finding="华东地区销售额500万",
                importance="high",
                category="comparison"
            )
        ],
        analysis_path=[
            AnalysisStep(
                step_number=1,
                agent_name="问题理解Agent",
                description="识别为对比类问题",
                duration_ms=1500
            )
        ],
        recommendations=[
            Recommendation(
                question="华东地区各产品类别的利润率分别是多少？",
                reason="发现华东地区利润率异常低",
                priority="high"
            )
        ],
        visualizations=[],
        metadata={
            "token_count": 15000,
            "execution_time_ms": 8500
        }
    )
    
    print("\n响应示例:")
    print(response.model_dump_json(indent=2))
