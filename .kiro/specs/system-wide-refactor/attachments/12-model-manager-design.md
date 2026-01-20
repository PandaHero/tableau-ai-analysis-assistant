# ModelManager 详细设计

## 概述

ModelManager 是统一的模型管理器，负责管理所有 LLM 和 Embedding 模型的配置、路由和调用。

**设计目标**：
1. **统一接口**：屏蔽不同提供商的 API 差异
2. **灵活配置**：支持多模型、多提供商、动态切换
3. **智能路由**：根据任务类型自动选择最优模型
4. **可扩展性**：轻松添加新的模型提供商
5. **成本优化**：支持模型降级和成本控制

## 支持的模型提供商

### 国外主流模型

| 提供商 | 模型 | 用途 | API 兼容性 |
|--------|------|------|-----------|
| **OpenAI** | GPT-4, GPT-3.5-turbo | LLM | OpenAI API |
| **Anthropic** | Claude 3.5 Sonnet, Claude 3 Opus | LLM | Anthropic API |
| **Google** | Gemini Pro, Gemini Flash | LLM | Google AI API |
| **Cohere** | Command R+, Command | LLM | Cohere API |

### 国内主流模型

| 提供商 | 模型 | 用途 | API 兼容性 | 特点 |
|--------|------|------|-----------|------|
| **DeepSeek** | DeepSeek-V3, DeepSeek-R1 | LLM | OpenAI-compatible | 671B MoE，擅长代码、数学、推理 |
| **阿里云通义** | Qwen2.5-Max, Qwen2.5-Plus, Qwen-Turbo | LLM | OpenAI-compatible | 擅长中文、代码、长文本 |
| **智谱 AI** | GLM-4.7, GLM-4.6, GLM-4.5, GLM-4-9B | LLM | OpenAI-compatible | 擅长工具调用、多模态 |
| **字节豆包** | Doubao-pro, Doubao-lite | LLM | 火山引擎 API | 擅长联网搜索、对话 |
| **月之暗面** | Kimi-k1.5, Moonshot-v1 | LLM | OpenAI-compatible | 超长上下文（200K+） |
| **MiniMax** | abab6.5, abab6 | LLM | OpenAI-compatible | 擅长角色扮演、对话 |

### 自建模型（本地部署）

| 模型 | 部署方式 | API 兼容性 | 说明 |
|------|---------|-----------|------|
| **Qwen3** | vLLM / Ollama | OpenAI-compatible | 当前项目使用 |
| **DeepSeek** | vLLM / Ollama | OpenAI-compatible | 当前项目使用 |
| **LLaMA 3** | vLLM / Ollama | OpenAI-compatible | 可选 |
| **ChatGLM** | vLLM / Ollama | OpenAI-compatible | 可选 |

### Embedding 模型

| 提供商 | 模型 | 维度 | 说明 |
|--------|------|------|------|
| **OpenAI** | text-embedding-3-large | 3072 | 高质量 |
| **OpenAI** | text-embedding-3-small | 1536 | 性价比 |
| **智谱 AI** | embedding-2 | 1024 | 中文优化 |
| **阿里云** | text-embedding-v2 | 1536 | 中文优化 |
| **本地** | bge-large-zh-v1.5 | 1024 | 自建，中文 |
| **本地** | m3e-base | 768 | 自建，轻量 |


## 架构设计

### 1. 核心组件

```
ModelManager (单例)
  ↓
├── 配置管理
│   ├── ModelConfig (模型配置)
│   ├── CRUD 操作 (create, get, update, delete)
│   └── 持久化存储 (LangGraph SqliteStore)
│
├── 模型创建
│   ├── create_llm() - 创建 LLM 实例
│   ├── create_embedding() - 创建 Embedding 实例
│   └── 路由逻辑 (Azure / Custom / OpenAI-compatible)
│
├── 智能路由 (可选)
│   └── TaskBasedRouter (基于任务类型选择模型)
│
├── 健康检查
│   ├── health_check() - 单个模型检查
│   └── health_check_all() - 批量检查
│
├── 统计信息
│   ├── ModelStats (使用统计)
│   └── record_request() - 记录请求
│
└── 默认模型管理
    ├── get_default() - 获取默认模型
    └── set_default() - 设置默认模型
```

### 2. 类图设计

```python
# analytics-assistant/src/infra/ai/model_manager.py

from abc import ABC, abstractmethod
from typing import Dict, List, Optional, Union
from enum import Enum
from pydantic import BaseModel
from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings


class ModelType(str, Enum):
    """模型类型"""
    LLM = "llm"
    EMBEDDING = "embedding"


class AuthType(str, Enum):
    """认证类型"""
    BEARER = "bearer"           # Authorization: Bearer <token>
    API_KEY_HEADER = "apikey"   # Apikey: <token>
    CUSTOM_HEADER = "custom"    # 自定义 header
    NONE = "none"               # 无认证


class ModelStatus(str, Enum):
    """模型状态"""
    ACTIVE = "active"           # 正常可用
    INACTIVE = "inactive"       # 已禁用
    ERROR = "error"             # 连接错误
    TESTING = "testing"         # 测试中


class TaskType(str, Enum):
    """任务类型（用于智能路由）"""
    INTENT_CLASSIFICATION = "intent_classification"  # 意图分类
    SEMANTIC_PARSING = "semantic_parsing"  # 语义解析
    FIELD_MAPPING = "field_mapping"  # 字段映射
    DIMENSION_HIERARCHY = "dimension_hierarchy"  # 维度层级
    INSIGHT_GENERATION = "insight_generation"  # 洞察生成
    REPLANNING = "replanning"  # 重新规划
    EMBEDDING = "embedding"  # 向量化


class ModelConfig(BaseModel):
    """模型配置"""
    # 基本信息
    id: str  # 唯一标识
    name: str  # 模型显示名称
    description: str = ""
    model_type: ModelType
    
    # API 配置
    provider: str  # 提供商（openai, azure, zhipu, deepseek, qwen, kimi, custom 等）
    api_base: str  # API 基础 URL
    api_endpoint: str = ""  # API 端点路径（留空使用默认）
    model_name: str  # 模型名称（API 参数）
    
    # 兼容性标记
    openai_compatible: bool = True  # 是否使用 OpenAI 兼容模式
    
    # 认证配置
    auth_type: AuthType = AuthType.BEARER
    auth_header: str = "Authorization"
    api_key: str = ""
    
    # 模型参数（None 表示使用模型默认值）
    temperature: Optional[float] = None  # 温度参数
    max_tokens: Optional[int] = None  # 最大 token 数
    top_p: Optional[float] = None  # Top-p 采样
    
    # 特性配置
    supports_streaming: bool = True  # 是否支持流式输出
    supports_json_mode: Optional[bool] = None  # 是否支持 JSON Mode
    supports_function_calling: bool = False  # 是否支持函数调用
    supports_vision: bool = False  # 是否支持视觉
    
    # 任务适配（用于智能路由）
    suitable_tasks: List[TaskType] = []  # 适合的任务类型
    priority: int = 0  # 优先级（数字越大优先级越高）
    
    # 网络配置
    timeout: float = 120.0
    verify_ssl: bool = True
    proxy: str = ""
    
    # 额外配置
    extra_headers: Dict[str, str] = {}
    extra_body: Dict[str, Any] = {}
    
    # 状态和元数据
    status: ModelStatus = ModelStatus.ACTIVE
    is_default: bool = False
    tags: List[str] = []
    
    # 时间戳
    created_at: datetime
    updated_at: datetime
    last_used_at: Optional[datetime] = None


class ModelManager:
    """
    模型管理器（单例）
    
    职责：
    1. 管理所有模型配置（CRUD 操作）
    2. 提供统一的模型获取接口
    3. 智能路由（根据任务类型选择最优模型）
    4. 健康检查和统计信息
    5. 持久化存储（LangGraph SqliteStore）
    """
    
    _instance = None
    
    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            self._configs: Dict[str, ModelConfig] = {}
            self._stats: Dict[str, ModelStats] = {}
            self._defaults: Dict[ModelType, str] = {}
            self._store = None  # LangGraph SqliteStore
            self._router = None  # TaskBasedRouter（可选）
            self._init_store()
            self._load_from_store()
            self._load_from_env()
    
    # ═══════════════════════════════════════════════════════════════════════
    # CRUD 操作
    # ═══════════════════════════════════════════════════════════════════════
    
    def create(self, request: ModelCreateRequest) -> ModelConfig:
        """创建新模型配置"""
        pass
    
    def get(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        pass
    
    def list(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ModelConfig]:
        """列出模型配置"""
        pass
    
    def update(self, model_id: str, request: ModelUpdateRequest) -> Optional[ModelConfig]:
        """更新模型配置"""
        pass
    
    def delete(self, model_id: str) -> bool:
        """删除模型配置"""
        pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 模型实例创建
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_llm(
        self,
        model_id: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        创建 LLM 实例
        
        Args:
            model_id: 指定模型 ID（优先级最高）
            task_type: 任务类型（用于智能路由）
            **kwargs: 运行时参数，可覆盖配置中的默认值
                - temperature: 温度参数
                - max_tokens: 最大 token 数
                - top_p: top_p 参数
                - enable_json_mode: 是否启用 JSON Mode
                - streaming: 是否启用流式输出（默认 False）
        
        Returns:
            LangChain BaseChatModel 实例
        
        Examples:
            # 使用默认配置
            llm = manager.create_llm()
            
            # 使用任务类型路由
            llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
            
            # 覆盖参数
            llm = manager.create_llm(
                model_id="qwen3-local",
                temperature=0.8,
                enable_json_mode=True,
                streaming=True
            )
        """
        pass
    
    def create_embedding(
        self,
        model_id: Optional[str] = None,
        **kwargs
    ) -> Embeddings:
        """创建 Embedding 实例"""
        pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 默认模型管理
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_default(self, model_type: ModelType) -> Optional[ModelConfig]:
        """获取默认模型"""
        pass
    
    def set_default(self, model_id: str) -> bool:
        """设置默认模型"""
        pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 健康检查
    # ═══════════════════════════════════════════════════════════════════════
    
    async def health_check(self, model_id: str) -> HealthCheckResult:
        """执行模型健康检查"""
        pass
    
    async def health_check_all(self) -> List[HealthCheckResult]:
        """检查所有活跃模型的健康状态"""
        pass
    
    # ═══════════════════════════════════════════════════════════════════════
    # 统计信息
    # ═══════════════════════════════════════════════════════════════════════
    
    def record_request(
        self,
        model_id: str,
        success: bool,
        latency_ms: float,
        tokens: int = 0,
        error: Optional[str] = None,
    ) -> None:
        """记录请求统计"""
        pass
    
    def get_stats(self, model_id: str) -> Optional[ModelStats]:
        """获取模型统计信息"""
        pass
```


## 模型创建逻辑

### 1. LLM 创建路由

```python
# analytics-assistant/src/infra/ai/model_manager.py

def _create_llm_from_config(self, config: ModelConfig, **kwargs) -> BaseChatModel:
    """
    从配置创建 LLM 实例
    
    路由逻辑（按优先级）：
    1. Azure OpenAI → AzureChatOpenAI（可选，企业用户）
    2. 非 OpenAI 兼容（自定义端点）→ CustomLLMChat
    3. OpenAI 兼容 → ChatOpenAI（默认，支持大多数模型）
    
    参数处理：
    - kwargs 可覆盖配置中的参数
    - enable_json_mode: 是否启用 JSON Mode（作为参数传递）
    - streaming: 是否启用流式输出（默认 False）
    """
    from langchain_openai import ChatOpenAI, AzureChatOpenAI
    
    # 合并参数：kwargs 优先，然后是 config
    temperature = kwargs.get('temperature', config.temperature)
    max_tokens = kwargs.get('max_tokens', config.max_tokens)
    enable_json_mode = kwargs.pop('enable_json_mode', False)
    streaming = kwargs.pop('streaming', False)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 路由 1：Azure OpenAI（可选，企业用户）
    # ═══════════════════════════════════════════════════════════════════════
    if config.provider == "azure":
        azure_kwargs = {
            "azure_deployment": config.model_name,  # Azure 部署名称
            "azure_endpoint": config.api_base,      # Azure 端点
            "openai_api_key": config.api_key,
            "openai_api_version": config.extra_body.get("api_version", "2024-02-15-preview"),
            "streaming": streaming,
        }
        if temperature is not None:
            azure_kwargs["temperature"] = temperature
        if max_tokens is not None:
            azure_kwargs["max_tokens"] = max_tokens
        
        # JSON Mode 支持
        if enable_json_mode:
            azure_kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
        
        return AzureChatOpenAI(**azure_kwargs)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 路由 2：非 OpenAI 兼容模型（自定义端点）
    # ═══════════════════════════════════════════════════════════════════════
    if not config.openai_compatible:
        from tableau_assistant.src.infra.ai.custom_llm import CustomLLMChat, CustomLLMConfig
        
        custom_config = CustomLLMConfig(
            name=config.name,
            api_base=config.api_base,
            api_endpoint=config.api_endpoint or "/v1/chat/completions",
            model_name=config.model_name,
            api_key=config.api_key,
            temperature=temperature if temperature is not None else 0.2,
            max_tokens=max_tokens if max_tokens is not None else 4096,
            supports_streaming=config.supports_streaming and streaming,
            # JSON Mode 通过 extra_body 传递
            extra_body={"response_format": {"type": "json_object"}} if enable_json_mode else {},
        )
        return CustomLLMChat(config=custom_config)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 路由 3：OpenAI 兼容模型（默认，支持大多数模型）
    # ═══════════════════════════════════════════════════════════════════════
    # 支持：
    # - OpenAI 官方（gpt-4, gpt-3.5-turbo）
    # - 智谱 AI（glm-4）
    # - 阿里云 Qwen（qwen-max, qwen-plus）
    # - 月之暗面 Kimi（moonshot-v1）
    # - 字节豆包（doubao-pro）
    # - MiniMax（abab6.5）
    # - 自建模型（vLLM/Ollama 部署的 Qwen3、DeepSeek 等）
    
    openai_kwargs = {
        "model_name": config.model_name,
        "api_key": config.api_key,
        "streaming": streaming,
    }
    
    # 非 OpenAI 官方 API 设置 base_url
    if "api.openai.com" not in config.api_base:
        openai_kwargs["base_url"] = config.api_base
    
    if temperature is not None:
        openai_kwargs["temperature"] = temperature
    if max_tokens is not None:
        openai_kwargs["max_tokens"] = max_tokens
    
    # JSON Mode 支持
    if enable_json_mode:
        openai_kwargs["model_kwargs"] = {"response_format": {"type": "json_object"}}
    
    return ChatOpenAI(**openai_kwargs)
```

### 2. 流式输出支持

```python
# 非流式调用（默认）
llm = manager.create_llm(model_id="qwen3-local")
response = llm.invoke("你好")

# 流式调用
llm = manager.create_llm(model_id="qwen3-local", streaming=True)
for chunk in llm.stream("你好"):
    print(chunk.content, end="", flush=True)

# 异步流式调用
llm = manager.create_llm(model_id="qwen3-local", streaming=True)
async for chunk in llm.astream("你好"):
    print(chunk.content, end="", flush=True)
```

### 3. JSON Mode 支持

```python
# 启用 JSON Mode
llm = manager.create_llm(
    model_id="qwen3-local",
    enable_json_mode=True
)

# 结合流式输出
llm = manager.create_llm(
    model_id="qwen3-local",
    enable_json_mode=True,
    streaming=True
)
```

### 4. Azure OpenAI 配置示例（可选）

如果你的企业使用 Azure OpenAI Service：

```yaml
# analytics-assistant/config/models.yaml

llm_models:
  - id: "azure-gpt4"
    name: "Azure GPT-4"
    model_type: "llm"
    provider: "azure"  # 标记为 Azure
    api_base: "https://my-resource.openai.azure.com"
    model_name: "my-gpt4-deployment"  # Azure 部署名称
    api_key: "${AZURE_OPENAI_API_KEY}"
    openai_compatible: false  # Azure 使用特殊 API
    extra_body:
      api_version: "2024-02-15-preview"
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 8
    enabled: true
```


## 配置管理

### 1. 配置文件示例

```yaml
# analytics-assistant/config/models.yaml

llm_models:
  # 自建模型（当前项目使用）
  - model_id: "qwen3-local"
    model_name: "qwen3"
    provider: "local"
    model_type: "llm"
    api_base: "http://localhost:8000/v1"
    api_key: "EMPTY"
    temperature: 0.7
    max_tokens: 4096
    cost_per_1k_tokens: 0.0  # 自建模型无成本
    suitable_tasks:
      - "semantic_parsing"
      - "field_mapping"
      - "dimension_hierarchy"
    priority: 10
    enabled: true
  
  - model_id: "deepseek-local"
    model_name: "deepseek-chat"
    provider: "local"
    model_type: "llm"
    api_base: "http://localhost:8001/v1"
    api_key: "EMPTY"
    temperature: 0.7
    max_tokens: 4096
    cost_per_1k_tokens: 0.0
    suitable_tasks:
      - "insight_generation"
      - "replanning"
    priority: 10
    enabled: true
  
  # 智谱 AI（备用）
  - model_id: "glm-4"
    model_name: "glm-4"
    provider: "zhipu"
    model_type: "llm"
    api_base: "https://open.bigmodel.cn/api/paas/v4"
    api_key: "${ZHIPU_API_KEY}"
    temperature: 0.7
    max_tokens: 4096
    cost_per_1k_tokens: 0.1
    suitable_tasks:
      - "semantic_parsing"
      - "field_mapping"
    priority: 5
    enabled: false  # 默认禁用，作为备用
  
  # 阿里云 Qwen（备用）
  - model_id: "qwen-max"
    model_name: "qwen-max"
    provider: "qwen"
    model_type: "llm"
    api_base: "https://dashscope.aliyuncs.com/compatible-mode/v1"
    api_key: "${QWEN_API_KEY}"
    temperature: 0.7
    max_tokens: 4096
    cost_per_1k_tokens: 0.12
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 5
    enabled: false
  
  # 字节豆包（备用）
  - model_id: "doubao-pro"
    model_name: "doubao-pro-32k"
    provider: "doubao"
    model_type: "llm"
    api_base: "https://ark.cn-beijing.volces.com/api/v3"
    api_key: "${DOUBAO_API_KEY}"
    temperature: 0.7
    max_tokens: 4096
    cost_per_1k_tokens: 0.008
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 5
    enabled: false
  
  # 月之暗面 Kimi（备用，超长上下文）
  - model_id: "kimi-k1.5"
    model_name: "moonshot-v1-32k"
    provider: "moonshot"
    model_type: "llm"
    api_base: "https://api.moonshot.cn/v1"
    api_key: "${MOONSHOT_API_KEY}"
    temperature: 0.7
    max_tokens: 4096
    cost_per_1k_tokens: 0.012
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 4
    enabled: false
    metadata:
      max_context_length: 200000  # 200K 超长上下文
  
  # OpenAI（备用，高质量）
  - model_id: "gpt-4-turbo"
    model_name: "gpt-4-turbo-preview"
    provider: "openai"
    model_type: "llm"
    api_key: "${OPENAI_API_KEY}"
    temperature: 0.7
    max_tokens: 4096
    cost_per_1k_tokens: 0.01
    suitable_tasks:
      - "semantic_parsing"
      - "insight_generation"
    priority: 3
    enabled: false

embedding_models:
  # 本地 Embedding（当前使用）
  - model_id: "bge-large-zh"
    model_name: "BAAI/bge-large-zh-v1.5"
    provider: "local"
    model_type: "embedding"
    cost_per_1k_tokens: 0.0
    priority: 10
    enabled: true
    metadata:
      dimension: 1024
      device: "cuda"
  
  # 智谱 Embedding（备用）
  - model_id: "zhipu-embedding"
    model_name: "embedding-2"
    provider: "zhipu"
    model_type: "embedding"
    api_base: "https://open.bigmodel.cn/api/paas/v4"
    api_key: "${ZHIPU_API_KEY}"
    cost_per_1k_tokens: 0.0005
    priority: 5
    enabled: false
    metadata:
      dimension: 1024

# 路由策略
routing:
  strategy: "task_based"  # task_based, cost_based, load_balancing
  fallback_enabled: true  # 启用降级
  fallback_order:  # 降级顺序
    - "local"
    - "zhipu"
    - "qwen"
    - "openai"
```

### 2. 环境变量配置

```bash
# .env

# 自建模型
QWEN3_API_BASE=http://localhost:8000/v1
DEEPSEEK_API_BASE=http://localhost:8001/v1

# 国内模型（备用）
ZHIPU_API_KEY=your_zhipu_api_key
QWEN_API_KEY=your_qwen_api_key
MOONSHOT_API_KEY=your_moonshot_api_key
DOUBAO_API_KEY=your_doubao_api_key
MINIMAX_API_KEY=your_minimax_api_key

# 国外模型（备用）
OPENAI_API_KEY=your_openai_api_key
ANTHROPIC_API_KEY=your_anthropic_api_key
GOOGLE_API_KEY=your_google_api_key

# 模型路由策略
MODEL_ROUTING_STRATEGY=task_based
MODEL_FALLBACK_ENABLED=true
```


## 智能路由策略

### 1. 基于任务类型的路由

```python
# analytics-assistant/src/infra/ai/router.py

class TaskBasedRouter:
    """基于任务类型的模型路由器"""
    
    def __init__(self, model_manager: ModelManager):
        self.model_manager = model_manager
    
    def route(self, task_type: TaskType) -> Optional[str]:
        """
        根据任务类型选择最优模型
        
        路由规则：
        1. 筛选适合该任务的模型（suitable_tasks 包含该任务类型）
        2. 按优先级排序（priority 越大越优先）
        3. 选择优先级最高且已启用的模型
        4. 如果没有可用模型，返回默认模型
        
        Args:
            task_type: 任务类型
        
        Returns:
            模型 ID，未找到返回 None
        """
        # 获取适合该任务的模型
        suitable_models = []
        for config in self.model_manager.list(
            model_type=ModelType.LLM,
            status=ModelStatus.ACTIVE
        ):
            if task_type in config.suitable_tasks:
                suitable_models.append(config)
        
        if not suitable_models:
            # 降级到默认模型
            default_config = self.model_manager.get_default(ModelType.LLM)
            return default_config.id if default_config else None
        
        # 按优先级排序（优先级越大越优先）
        suitable_models.sort(key=lambda m: m.priority, reverse=True)
        
        return suitable_models[0].id


# 使用示例
router = TaskBasedRouter(model_manager)

# 路由到适合语义解析的模型
model_id = router.route(TaskType.SEMANTIC_PARSING)
if model_id:
    llm = model_manager.create_llm(model_id=model_id)
```

### 2. 集成到 ModelManager

```python
class ModelManager:
    def __init__(self):
        # ...
        self._router = TaskBasedRouter(self)  # 初始化路由器
    
    def create_llm(
        self,
        model_id: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        创建 LLM 实例
        
        优先级：
        1. model_id（显式指定）
        2. task_type（智能路由）
        3. 默认模型
        """
        # 1. 显式指定模型 ID
        if model_id:
            config = self.get(model_id)
        # 2. 使用任务类型路由
        elif task_type and self._router:
            routed_id = self._router.route(task_type)
            config = self.get(routed_id) if routed_id else None
        # 3. 使用默认模型
        else:
            config = self.get_default(ModelType.LLM)
        
        if not config:
            raise ValueError("未找到 LLM 模型配置")
        
        return self._create_llm_from_config(config, **kwargs)


# 使用示例
# 方式 1：显式指定模型
llm = manager.create_llm(model_id="qwen3-local")

# 方式 2：使用任务类型路由（自动选择最优模型）
llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)

# 方式 3：使用默认模型
llm = manager.create_llm()
```

### 3. 配置任务适配

在模型配置中指定适合的任务类型：

```yaml
# analytics-assistant/config/models.yaml

llm_models:
  - id: "qwen3-local"
    name: "Qwen3 本地"
    model_type: "llm"
    provider: "local"
    api_base: "http://localhost:8000/v1"
    model_name: "qwen3"
    openai_compatible: true
    # 任务适配配置
    suitable_tasks:
      - "semantic_parsing"      # 语义解析
      - "field_mapping"         # 字段映射
      - "dimension_hierarchy"   # 维度层级
    priority: 10  # 优先级最高
    enabled: true
  
  - id: "deepseek-local"
    name: "DeepSeek 本地"
    model_type: "llm"
    provider: "local"
    api_base: "http://localhost:8001/v1"
    model_name: "deepseek-chat"
    openai_compatible: true
    # 任务适配配置
    suitable_tasks:
      - "insight_generation"    # 洞察生成
      - "replanning"            # 重新规划
    priority: 10
    enabled: true
  
  - id: "glm-4"
    name: "智谱 GLM-4"
    model_type: "llm"
    provider: "zhipu"
    api_base: "https://open.bigmodel.cn/api/paas/v4"
    model_name: "glm-4"
    openai_compatible: true
    # 备用模型，优先级较低
    suitable_tasks:
      - "semantic_parsing"
      - "field_mapping"
      - "insight_generation"
    priority: 5  # 优先级低于本地模型
    enabled: false  # 默认禁用，作为备用
```


## 使用示例

### 1. 初始化和配置

```python
# analytics-assistant/src/infra/ai/model_manager.py

# 获取模型管理器单例
from tableau_assistant.src.infra.ai.model_manager import get_model_manager

manager = get_model_manager()

# 创建模型配置
from tableau_assistant.src.infra.ai.model_manager import ModelCreateRequest, ModelType

# 注册自建模型（Qwen3）
qwen3_request = ModelCreateRequest(
    name="Qwen3 本地",
    model_type=ModelType.LLM,
    provider="local",
    api_base="http://localhost:8000/v1",
    model_name="qwen3",
    api_key="EMPTY",
    openai_compatible=True,
    temperature=0.7,
    supports_streaming=True,
    supports_json_mode=True,
    suitable_tasks=[
        TaskType.SEMANTIC_PARSING,
        TaskType.FIELD_MAPPING,
        TaskType.DIMENSION_HIERARCHY
    ],
    priority=10,
    is_default=True,
)
qwen3_config = manager.create(qwen3_request)

# 注册自建模型（DeepSeek）
deepseek_request = ModelCreateRequest(
    name="DeepSeek 本地",
    model_type=ModelType.LLM,
    provider="local",
    api_base="http://localhost:8001/v1",
    model_name="deepseek-chat",
    api_key="EMPTY",
    openai_compatible=True,
    temperature=0.7,
    supports_streaming=True,
    supports_json_mode=True,
    suitable_tasks=[
        TaskType.INSIGHT_GENERATION,
        TaskType.REPLANNING
    ],
    priority=10,
)
deepseek_config = manager.create(deepseek_request)
```

### 2. Agent 层使用

```python
# analytics-assistant/src/agents/base/node.py

def get_llm(
    task_type: Optional[TaskType] = None,
    model_id: Optional[str] = None,
    **kwargs
) -> BaseChatModel:
    """
    获取 LLM 实例（便捷函数）
    
    Args:
        task_type: 任务类型（用于智能路由）
        model_id: 指定模型 ID
        **kwargs: 运行时参数
    
    Returns:
        LLM 实例
    """
    from tableau_assistant.src.infra.ai.model_manager import get_model_manager
    manager = get_model_manager()
    return manager.create_llm(task_type=task_type, model_id=model_id, **kwargs)


# 在 Agent 中使用
class SemanticParserNode:
    def __init__(self):
        # 自动路由到适合语义解析的模型（Qwen3）
        self.llm = get_llm(task_type=TaskType.SEMANTIC_PARSING)
    
    def parse(self, query: str):
        response = self.llm.invoke(query)
        return response


class InsightNode:
    def __init__(self):
        # 自动路由到适合洞察生成的模型（DeepSeek）
        self.llm = get_llm(task_type=TaskType.INSIGHT_GENERATION)
    
    def generate_insight(self, data: Dict):
        response = self.llm.invoke(data)
        return response
```

### 3. 手动指定模型

```python
# 场景 1：指定使用 Qwen3（使用默认配置）
llm = manager.create_llm(model_id="qwen3-local")

# 场景 2：指定使用 DeepSeek（使用默认配置）
llm = manager.create_llm(model_id="deepseek-local")

# 场景 3：覆盖温度参数
llm = manager.create_llm(
    model_id="qwen3-local",
    temperature=0.9  # 覆盖配置中的默认 0.7
)

# 场景 4：覆盖多个参数
llm = manager.create_llm(
    model_id="qwen3-local",
    temperature=0.8,
    max_tokens=8192,
    top_p=0.95
)

# 场景 5：使用任务类型路由，并覆盖参数
llm = manager.create_llm(
    task_type=TaskType.SEMANTIC_PARSING,
    temperature=0.5  # 更低的温度，更确定性的输出
)
```

### 4. 流式输出

```python
# 场景 1：非流式调用（默认）
llm = manager.create_llm(model_id="qwen3-local")
response = llm.invoke("你好，请介绍一下自己")
print(response.content)

# 场景 2：流式调用（同步）
llm = manager.create_llm(model_id="qwen3-local", streaming=True)
for chunk in llm.stream("你好，请介绍一下自己"):
    print(chunk.content, end="", flush=True)

# 场景 3：流式调用（异步）
llm = manager.create_llm(model_id="qwen3-local", streaming=True)
async for chunk in llm.astream("你好，请介绍一下自己"):
    print(chunk.content, end="", flush=True)

# 场景 4：结合任务类型路由和流式输出
llm = manager.create_llm(
    task_type=TaskType.INSIGHT_GENERATION,
    streaming=True,
    temperature=0.7
)
for chunk in llm.stream("分析销售数据"):
    print(chunk.content, end="", flush=True)
```

### 5. JSON Mode

```python
# 场景 1：启用 JSON Mode
llm = manager.create_llm(
    model_id="qwen3-local",
    enable_json_mode=True
)
response = llm.invoke("返回一个包含姓名和年龄的 JSON 对象")
# 输出：{"name": "张三", "age": 25}

# 场景 2：结合流式输出和 JSON Mode
llm = manager.create_llm(
    model_id="qwen3-local",
    enable_json_mode=True,
    streaming=True
)
for chunk in llm.stream("返回一个包含姓名和年龄的 JSON 对象"):
    print(chunk.content, end="", flush=True)

# 场景 3：结合任务类型路由、JSON Mode 和参数覆盖
llm = manager.create_llm(
    task_type=TaskType.SEMANTIC_PARSING,
    enable_json_mode=True,
    temperature=0.3,  # 更低的温度，确保 JSON 格式正确
    streaming=True
)
```

### 6. 动态切换模型

```python
# 运行时启用备用模型
manager.update("glm-4", ModelUpdateRequest(status=ModelStatus.ACTIVE))

# 运行时禁用模型
manager.update("qwen3-local", ModelUpdateRequest(status=ModelStatus.INACTIVE))

# 更新模型配置
manager.update(
    "qwen3-local",
    ModelUpdateRequest(temperature=0.8, max_tokens=8192)
)

# 设置默认模型
manager.set_default("glm-4")
```

### 5. 降级和容错

```python
# analytics-assistant/src/infra/ai/model_manager.py

class ModelManager:
    def get_llm(self, task_type: Optional[TaskType] = None, **kwargs):
        """
        获取 LLM 实例（带降级）
        
        降级策略：
        1. 尝试使用智能路由选择的模型
        2. 如果失败，尝试降级到备用模型
        3. 如果所有模型都失败，抛出异常
        
        Args:
            task_type: 任务类型（用于智能路由）
            **kwargs: 运行时参数，可覆盖配置中的默认值
        """
        # 1. 智能路由
        if task_type:
            model_id = self.router.route(task_type)
        else:
            model_id = kwargs.pop("model_id", None) or self._get_default_model()
        
        # 2. 尝试创建 LLM（传递运行时参数）
        try:
            return self._create_llm(model_id, **kwargs)
        except Exception as e:
            logger.warning(f"Failed to create LLM {model_id}: {e}")
            
            # 3. 降级到备用模型
            if self.fallback_enabled:
                for fallback_provider in self.fallback_order:
                    fallback_models = self.list_models(
                        provider=fallback_provider,
                        enabled_only=True
                    )
                    if fallback_models:
                        try:
                            return self._create_llm(
                                fallback_models[0].model_id,
                                **kwargs  # 传递运行时参数到备用模型
                            )
                        except Exception as e2:
                            logger.warning(
                                f"Fallback to {fallback_models[0].model_id} failed: {e2}"
                            )
                            continue
            
            # 4. 所有模型都失败
            raise RuntimeError("All models failed")
    
    def _create_llm(self, model_id: str, **kwargs) -> BaseChatModel:
        """
        创建 LLM 实例（内部方法）
        
        Args:
            model_id: 模型 ID
            **kwargs: 运行时参数，传递给 Provider
        """
        config = self.registry.get(model_id)
        if not config:
            raise ValueError(f"Model {model_id} not found")
        
        provider = self.providers.get(config.provider)
        if not provider:
            raise ValueError(f"Provider {config.provider} not found")
        
        # 传递运行时参数到 Provider
        return provider.create_llm(**kwargs)
```


## 部署建议

### 1. 自建模型部署（vLLM）

```bash
# 部署 Qwen3（端口 8000）
python -m vllm.entrypoints.openai.api_server \
    --model Qwen/Qwen2.5-7B-Instruct \
    --served-model-name qwen3 \
    --host 0.0.0.0 \
    --port 8000 \
    --tensor-parallel-size 1

# 部署 DeepSeek（端口 8001）
python -m vllm.entrypoints.openai.api_server \
    --model deepseek-ai/deepseek-coder-6.7b-instruct \
    --served-model-name deepseek-chat \
    --host 0.0.0.0 \
    --port 8001 \
    --tensor-parallel-size 1
```

### 2. 本地 Embedding 模型

```python
# 下载模型到本地
from huggingface_hub import snapshot_download

snapshot_download(
    repo_id="BAAI/bge-large-zh-v1.5",
    local_dir="./models/bge-large-zh-v1.5"
)

# 配置使用本地路径
embedding_config = ModelConfig(
    model_id="bge-large-zh",
    model_name="./models/bge-large-zh-v1.5",  # 本地路径
    provider=ProviderType.LOCAL,
    model_type=ModelType.EMBEDDING,
    metadata={"device": "cuda"}
)
```

### 3. Docker Compose 部署

```yaml
# docker-compose.yml

version: '3.8'

services:
  # Qwen3 模型服务
  qwen3:
    image: vllm/vllm-openai:latest
    ports:
      - "8000:8000"
    volumes:
      - ./models:/models
    command: >
      --model /models/Qwen2.5-7B-Instruct
      --served-model-name qwen3
      --host 0.0.0.0
      --port 8000
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
  
  # DeepSeek 模型服务
  deepseek:
    image: vllm/vllm-openai:latest
    ports:
      - "8001:8001"
    volumes:
      - ./models:/models
    command: >
      --model /models/deepseek-coder-6.7b-instruct
      --served-model-name deepseek-chat
      --host 0.0.0.0
      --port 8001
    deploy:
      resources:
        reservations:
          devices:
            - driver: nvidia
              count: 1
              capabilities: [gpu]
  
  # Analytics Assistant 主服务
  analytics-assistant:
    build: .
    ports:
      - "8080:8080"
    environment:
      - QWEN3_API_BASE=http://qwen3:8000/v1
      - DEEPSEEK_API_BASE=http://deepseek:8001/v1
    depends_on:
      - qwen3
      - deepseek
```

## 监控和日志

### 1. 模型调用监控

```python
# analytics-assistant/src/infra/ai/monitoring.py

from prometheus_client import Counter, Histogram

# 定义指标
model_requests_total = Counter(
    'model_requests_total',
    'Total model requests',
    ['model_id', 'task_type', 'status']
)

model_latency_seconds = Histogram(
    'model_latency_seconds',
    'Model request latency',
    ['model_id', 'task_type']
)

model_tokens_total = Counter(
    'model_tokens_total',
    'Total tokens consumed',
    ['model_id', 'task_type', 'token_type']
)


class MonitoredModelManager(ModelManager):
    """带监控的 ModelManager"""
    
    def get_llm(self, task_type: Optional[TaskType] = None, **kwargs):
        start_time = time.time()
        model_id = None
        
        try:
            llm = super().get_llm(task_type=task_type, **kwargs)
            model_id = kwargs.get("model_id") or self.router.route(task_type)
            
            # 记录成功
            model_requests_total.labels(
                model_id=model_id,
                task_type=task_type.value if task_type else "unknown",
                status="success"
            ).inc()
            
            return llm
            
        except Exception as e:
            # 记录失败
            model_requests_total.labels(
                model_id=model_id or "unknown",
                task_type=task_type.value if task_type else "unknown",
                status="error"
            ).inc()
            raise
            
        finally:
            # 记录延迟
            if model_id:
                model_latency_seconds.labels(
                    model_id=model_id,
                    task_type=task_type.value if task_type else "unknown"
                ).observe(time.time() - start_time)
```

### 2. 日志记录

```python
import logging

logger = logging.getLogger(__name__)

class ModelManager:
    def get_llm(self, task_type: Optional[TaskType] = None, **kwargs):
        logger.info(
            f"Getting LLM for task_type={task_type}, kwargs={kwargs}"
        )
        
        model_id = self.router.route(task_type) if task_type else None
        
        logger.info(f"Selected model: {model_id}")
        
        try:
            llm = self._create_llm(model_id, **kwargs)
            logger.info(f"Successfully created LLM: {model_id}")
            return llm
        except Exception as e:
            logger.error(
                f"Failed to create LLM {model_id}: {e}",
                exc_info=True
            )
            raise
```

## 总结

ModelManager 设计的核心特点：

1. **统一接口**：屏蔽不同提供商的 API 差异，提供一致的调用方式
2. **灵活配置**：支持 YAML 配置文件和环境变量，易于管理
3. **智能路由**：根据任务类型自动选择最优模型（TaskBasedRouter）
4. **参数覆盖**：运行时参数可覆盖配置中的默认值（temperature、max_tokens 等）
5. **流式输出**：支持同步和异步流式输出（streaming=True）
6. **JSON Mode**：支持 JSON Mode 作为参数传递（enable_json_mode=True）
7. **持久化存储**：使用 LangGraph SqliteStore 持久化配置
8. **健康检查**：异步健康检查，自动更新模型状态
9. **统计信息**：记录使用统计（请求数、成功率、延迟、token 消耗）
10. **可扩展性**：轻松添加新的模型提供商和模型

**当前项目配置**：
- **主力模型**：Qwen3（语义解析、字段映射）+ DeepSeek（洞察生成）
- **Embedding**：bge-large-zh-v1.5（本地部署）或智谱 Embedding
- **备用模型**：智谱 AI、阿里云 Qwen（可选启用）
- **部署方式**：vLLM + Docker Compose

**关键特性**：
- ✅ 支持流式输出（同步/异步）
- ✅ 支持 JSON Mode（作为参数）
- ✅ 支持任务类型路由（智能选择模型）
- ✅ 支持参数覆盖（运行时灵活配置）
- ✅ 支持健康检查（自动监控模型状态）
- ✅ 支持统计信息（使用情况追踪）

