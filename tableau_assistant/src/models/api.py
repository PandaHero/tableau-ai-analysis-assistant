"""
API输入输出模型定义

使用Pydantic定义API的输入输出类型，提供：
- 自动验证
- 自动文档生成
- 类型安全
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional


# ========== API输入模型 ==========

class VizQLQueryRequest(BaseModel):
    """
    VizQL查询请求
    
    用于 POST /api/chat 端点
    """
    question: str = Field(
        ...,
        description="用户问题",
        min_length=1,
        max_length=1000,
        examples=["2016年各地区的销售额是多少？"]
    )
    
    datasource_luid: str = Field(
        ...,
        description="数据源LUID",
        min_length=1,
        examples=["abc123-def456-ghi789"]
    )
    
    boost_question: bool = Field(
        default=False,
        description="是否使用问题Boost优化问题"
    )
    
    user_id: Optional[str] = Field(
        default=None,
        description="用户ID（可选，用于个性化）"
    )
    
    session_id: Optional[str] = Field(
        default=None,
        description="会话ID（可选，用于对话历史）"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "2016年各地区的销售额是多少？",
                "datasource_luid": "abc123-def456-ghi789",
                "boost_question": False,
                "user_id": "user_456",
                "session_id": "session_789"
            }
        }
    )


class QuestionBoostRequest(BaseModel):
    """
    问题Boost请求
    
    用于 POST /api/boost-question 端点
    """
    question: str = Field(
        ...,
        description="用户原始问题",
        min_length=1,
        max_length=1000,
        examples=["最近的销售情况"]
    )
    
    datasource_luid: str = Field(
        ...,
        description="数据源LUID",
        min_length=1,
        examples=["abc123-def456-ghi789"]
    )
    
    user_id: Optional[str] = Field(
        default=None,
        description="用户ID（可选，用于个性化）"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "question": "最近的销售情况",
                "datasource_luid": "abc123-def456-ghi789",
                "user_id": "user_456"
            }
        }
    )


class MetadataInitRequest(BaseModel):
    """
    元数据初始化请求
    
    用于 POST /api/metadata/init-hierarchy 端点
    """
    datasource_luid: str = Field(
        ...,
        description="数据源LUID",
        min_length=1,
        examples=["abc123-def456-ghi789"]
    )
    
    force_refresh: bool = Field(
        default=False,
        description="是否强制刷新（忽略缓存）"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "datasource_luid": "abc123-def456-ghi789",
                "force_refresh": False
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


class VizQLQueryResponse(BaseModel):
    """
    VizQL查询响应
    
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


class QuestionBoostResponse(BaseModel):
    """
    问题Boost响应
    
    用于 POST /api/boost-question 端点
    """
    boosted_question: str = Field(
        ...,
        description="优化后的问题"
    )
    
    suggestions: List[str] = Field(
        default_factory=list,
        description="相关问题建议（3-5个）"
    )
    
    reasoning: str = Field(
        ...,
        description="优化理由"
    )
    
    changes: List[str] = Field(
        default_factory=list,
        description="具体改动说明"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "boosted_question": "最近一个月各地区的销售额、订单量和客户数分别是多少？",
                "suggestions": [
                    "最近一个月销售额TOP10的门店是哪些？",
                    "最近一个月各产品类别的销售额占比",
                    "最近一个月的销售额趋势（按日统计）"
                ],
                "reasoning": "原问题过于宽泛，补充了时间范围、维度和度量",
                "changes": [
                    "补充时间范围：最近一个月",
                    "明确维度：地区",
                    "明确度量：销售额、订单量、客户数"
                ]
            }
        }
    )


class MetadataInitResponse(BaseModel):
    """
    元数据初始化响应
    
    用于 POST /api/metadata/init-hierarchy 端点
    """
    status: str = Field(
        ...,
        description="状态（initializing/completed/cached）"
    )
    
    datasource_luid: str = Field(
        ...,
        description="数据源LUID"
    )
    
    message: str = Field(
        ...,
        description="状态消息"
    )
    
    cached: bool = Field(
        default=False,
        description="是否使用缓存"
    )
    
    duration_ms: Optional[int] = Field(
        None,
        description="执行时间（毫秒）"
    )
    
    model_config = ConfigDict(
        json_schema_extra={
            "example": {
                "status": "initializing",
                "datasource_luid": "abc123-def456-ghi789",
                "message": "后台正在初始化维度层级，预计3-5秒完成",
                "cached": False,
                "duration_ms": None
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


# 示例用法
if __name__ == "__main__":
    # 创建请求示例
    request = VizQLQueryRequest(
        question="2016年各地区的销售额是多少？",
        datasource_luid="abc123",
        boost_question=False,
        user_id="user_456",
        session_id="session_789"
    )
    
    print("请求示例:")
    print(request.model_dump_json(indent=2))
    
    # 创建响应示例
    response = VizQLQueryResponse(
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
