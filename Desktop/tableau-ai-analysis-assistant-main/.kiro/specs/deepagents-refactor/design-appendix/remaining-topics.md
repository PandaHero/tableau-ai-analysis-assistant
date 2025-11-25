# 剩余主题概要

本文档包含渐进式洞察系统、语义字段映射、缓存系统、数据模型和 API 设计的概要说明。

---

## 1. 渐进式洞察系统

### 架构分层

**准备层**：
- **Coordinator** - 决定使用直接分析还是渐进式分析
- **DataProfiler** - 生成数据画像（分布、异常值位置）
- **SemanticChunker** - 智能分块（优先级：异常值 → Top → 中间 → 尾部）

**分析层**：
- **ChunkAnalyzer** - 分析每个数据块
- **PatternDetector** - 检测模式和趋势
- **AnomalyDetector** - 检测异常值

**累积层**：
- **InsightAccumulator** - 累积洞察
- **QualityFilter** - 过滤低质量洞察
- **DedupMerger** - 去重和合并

**合成层**：
- **InsightSynthesizer** - 合成最终洞察
- **SummaryGenerator** - 生成摘要
- **RecommendGenerator** - 生成建议

### 工作流程

```
大数据集（500 行）
  ↓
Coordinator: 检测规模 → 启动渐进式分析
  ↓
DataProfiler: 生成数据画像
  ├─ 分布特征
  ├─ 异常值位置
  └─ 数据质量评估
  ↓
SemanticChunker: 智能分块
  ├─ 第1块: Top 异常值（50行）
  ├─ 第2块: 高值区间（100行）
  └─ 第3块: 中值区间（200行）
  ↓
ChunkAnalyzer: 逐块分析
  ├─ 分析第1块 → 输出洞察1
  ├─ 分析第2块 → 输出洞察2
  └─ AI 判断: 趋势已清晰 → 早停
  ↓
InsightAccumulator: 累积洞察
  ↓
InsightSynthesizer: 合成最终洞察
```

---

## 2. 语义字段映射

### 系统架构

**Vector Store (FAISS)**：
- 存储字段向量索引
- 支持快速相似度检索
- 每个数据源独立索引

**Embedding Model**：
- 优先：bce-embedding-base-v1（中文，GPU）
- 备选：text-embedding-3-large（英文，API）

**Field Indexer**：
- 构建字段向量索引
- 包含字段名、描述、示例值
- 支持增量更新

**Semantic Mapper**：
- 向量检索 + LLM 语义判断
- 返回最佳匹配 + 置信度
- 支持同义词和多语言

### 映射流程

```
业务术语: "销售额"
  ↓
1. 向量检索 (Top-5)
   ├─ Sales Amount (0.95)
   ├─ Revenue (0.92)
   ├─ Quantity (0.65)
   ├─ Discount (0.45)
   └─ Cost (0.30)
  ↓
2. 过滤低相似度（< 0.6）
   ├─ 保留: Sales Amount, Revenue, Quantity
   └─ 过滤: Discount, Cost
  ↓
3. LLM 语义判断
   输入: 问题上下文 + 候选字段
   输出: 最佳匹配 + 推理
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

## 3. 缓存系统设计

### 四层缓存架构

**L1: Prompt Caching (Anthropic)**
- 存储：Anthropic API
- 有效期：5分钟
- 命中率：60-80%
- 节省成本：50-90%
- 适用：Claude 模型的系统提示词

**L2: Application Cache (PersistentStore)**
- 存储：SQLite
- 有效期：1小时
- 命中率：40-60%
- 节省成本：30-50%
- 适用：所有模型的 LLM 响应

**L3: Query Result Cache (PersistentStore)**
- 存储：SQLite
- 有效期：会话期间
- 命中率：20-40%
- 节省成本：10-30%
- 适用：VizQL 查询结果

**L4: Semantic Cache (Vector Store)**
- 存储：FAISS
- 有效期：永久
- 命中率：5-15%
- 节省成本：5-10%
- 适用：语义相似的查询（可选）

### 缓存策略

```python
# 缓存 Key 生成
def generate_cache_key(prompt: str, model: str) -> str:
    content = f"{model}:{prompt}"
    return hashlib.sha256(content.encode()).hexdigest()

# 缓存查询流程
async def call_llm_with_cache(prompt: str, model: str) -> str:
    # 1. 检查 L2 缓存
    cache_key = generate_cache_key(prompt, model)
    cached = store.get(("llm_cache", model), cache_key)
    if cached:
        return cached["content"]
    
    # 2. 调用 LLM（L1 自动生效）
    response = await llm.ainvoke(prompt)
    
    # 3. 保存到 L2 缓存
    store.put(
        ("llm_cache", model),
        cache_key,
        {"content": response, "timestamp": time.time()},
        ttl=3600
    )
    
    return response
```

---

## 4. 数据模型设计

### State 模型（LangGraph）

```python
from typing import TypedDict, Annotated, List, Dict, Any
import operator

class DeepAgentState(TypedDict):
    """DeepAgent 状态定义"""
    
    # 用户输入
    question: str
    boost_question: bool
    
    # Agent 输出
    boosted_question: Optional[str]
    understanding: Optional[Dict]
    query_plan: Optional[Dict]
    query_results: Annotated[List[Dict], operator.add]
    insights: Annotated[List[Dict], operator.add]
    replan_decision: Optional[Dict]
    final_report: Optional[Dict]
    
    # 控制流程
    current_round: int
    max_rounds: int
    needs_replan: bool
```

### Context 模型（运行时）

```python
from dataclasses import dataclass

@dataclass
class DeepAgentContext:
    """运行时上下文（不可变）"""
    
    datasource_luid: str
    user_id: str
    thread_id: str
    tableau_token: str
    max_replan: int = 3
```

### Question 模型

```python
from pydantic import BaseModel, Field

class QuestionUnderstanding(BaseModel):
    """问题理解结果"""
    
    question_type: List[str] = Field(description="问题类型")
    complexity: str = Field(description="复杂度")
    mentioned_dimensions: List[str] = Field(description="提到的维度")
    mentioned_measures: List[str] = Field(description="提到的度量")
    time_range: Optional[Dict] = Field(description="时间范围")
    confidence: float = Field(ge=0.0, le=1.0)
    reasoning: str = Field(description="推理过程")
```

### Query 模型

```python
class QuerySpec(BaseModel):
    """查询规格"""
    
    query_id: str
    question_text: str
    fields: List[Dict]
    filters: List[Dict]
    dependencies: List[str]
    cache_key: Optional[str]
    reasoning: str
```

### Insight 模型

```python
class Insight(BaseModel):
    """洞察"""
    
    type: str = Field(description="洞察类型")
    description: str = Field(description="洞察描述")
    evidence: List[str] = Field(description="支持证据")
    confidence: float = Field(ge=0.0, le=1.0)
    importance: str = Field(description="重要性")
```

---

## 5. API 设计

### REST API 端点

**POST /api/chat**
- 同步查询端点
- 返回完整的分析结果

**POST /api/chat/stream**
- 流式查询端点
- 返回 SSE 事件流

**GET /api/health**
- 健康检查端点

### 请求格式

```python
class ChatRequest(BaseModel):
    """聊天请求"""
    
    question: str = Field(description="用户问题")
    datasource_luid: str = Field(description="数据源 LUID")
    boost_question: bool = Field(default=False, description="是否优化问题")
    thread_id: Optional[str] = Field(default=None, description="会话 ID")
    model_config: Optional[Dict] = Field(default=None, description="模型配置")
```

### 响应格式

```python
class ChatResponse(BaseModel):
    """聊天响应"""
    
    executive_summary: str = Field(description="执行摘要")
    key_findings: List[str] = Field(description="关键发现")
    insights: List[Insight] = Field(description="洞察列表")
    recommendations: List[str] = Field(description="建议")
    performance_metrics: Dict = Field(description="性能指标")
    thread_id: str = Field(description="会话 ID")
```

### SSE 事件格式

```python
# Token 流
{"type": "token", "content": "华东"}

# Agent 进度
{"type": "agent_start", "agent": "understanding-agent"}
{"type": "agent_end", "agent": "understanding-agent"}

# 工具调用
{"type": "tool_start", "tool": "get_metadata"}
{"type": "tool_end", "tool": "get_metadata"}

# 洞察输出
{"type": "insight", "content": {...}}

# 完成
{"type": "done"}

# 错误
{"type": "error", "message": "..."}
```

### API 实现示例

```python
from fastapi import FastAPI, HTTPException
from fastapi.responses import StreamingResponse

app = FastAPI()

@app.post("/api/chat")
async def chat(request: ChatRequest) -> ChatResponse:
    """同步查询端点"""
    agent = create_deep_agent(...)
    
    result = await agent.ainvoke(
        {"question": request.question},
        config={
            "configurable": {
                "thread_id": request.thread_id or generate_thread_id(),
                "datasource_luid": request.datasource_luid
            }
        }
    )
    
    return ChatResponse(**result)

@app.post("/api/chat/stream")
async def chat_stream(request: ChatRequest):
    """流式查询端点"""
    agent = create_deep_agent(...)
    
    async def event_generator():
        async for event in agent.astream_events(
            {"question": request.question},
            config={...},
            version="v2"
        ):
            if event["event"] == "on_chat_model_stream":
                token = event["data"]["chunk"].content
                yield f"data: {json.dumps({'type': 'token', 'content': token})}\n\n"
            # ... 其他事件类型
        
        yield f"data: {json.dumps({'type': 'done'})}\n\n"
    
    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream"
    )
```

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**说明**: 本文档为概要版本，详细内容将在后续迭代中补充
