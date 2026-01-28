# Analytics Assistant 编码规范

本规范适用于 `analytics_assistant/src/` 目录下的所有代码。

## 1. 目录结构规范

### 1.1 顶层目录结构

```
analytics_assistant/src/
├── agents/              # Agent 模块（LangGraph 工作流）
│   ├── base/            # Agent 基础设施
│   ├── semantic_parser/ # 语义解析 Agent
│   ├── field_mapper/    # 字段映射 Agent
│   └── dimension_hierarchy/  # 维度层级 Agent
├── core/                # 核心模块（接口、异常、通用 Schema）
│   ├── schemas/         # 通用数据模型
│   ├── interfaces.py    # 抽象接口定义
│   └── exceptions.py    # 自定义异常
├── infra/               # 基础设施（AI、存储、配置）
│   ├── ai/              # LLM、Embedding 封装
│   ├── storage/         # 存储（SqliteStore、缓存）
│   ├── config/          # 配置管理
│   └── rag/             # RAG 检索
├── platform/            # 平台适配器（Tableau、Power BI 等）
│   ├── base.py          # 平台适配器基类
│   └── tableau/         # Tableau 平台实现
└── config/              # 配置文件目录
    └── app.yaml         # 应用配置
```

### 1.2 Agent 模块目录结构

每个 Agent 模块应遵循以下结构：

```
{agent_name}/
├── components/          # 业务组件（纯逻辑，无 Prompt）
│   ├── __init__.py
│   └── ...
├── prompts/             # Prompt 相关
│   ├── __init__.py
│   ├── templates/       # Prompt 模板文件（可选）
│   └── {feature}_prompt.py
├── schemas/             # Pydantic 数据模型
│   ├── __init__.py
│   └── ...
├── state.py             # LangGraph State 定义
├── graph.py             # LangGraph 图定义
├── keywords_data.py     # 关键词数据（可选）
├── rules_data.py        # 规则模式数据（可选）
└── seed_data.py         # 种子数据（可选）
```

## 2. 配置管理规范

### 2.1 所有可配置参数必须放入 `app.yaml`

**禁止**在代码中硬编码以下类型的值：
- 阈值（threshold）
- 超时时间（timeout）
- 最大重试次数（max_retries）
- 缓存 TTL
- 置信度参数
- API 端点（非敏感）

**正确做法**：在 `analytics_assistant/config/app.yaml` 中添加配置节：

```yaml
# app.yaml
semantic_parser:
  semantic_understanding:
    low_confidence_threshold: 0.7
    default_timezone: "Asia/Shanghai"
  
  error_corrector:
    max_retries: 3
    max_same_error_count: 2

field_mapper:
  similarity_threshold: 0.8
  max_candidates: 10

dimension_hierarchy:
  confidence_threshold: 0.7
```

### 2.2 代码中读取配置的模式

```python
from analytics_assistant.src.infra.config import get_config

class MyComponent:
    # 默认值作为 fallback
    _DEFAULT_THRESHOLD = 0.7
    
    def __init__(self):
        self._load_config()
    
    def _load_config(self) -> None:
        """从 YAML 配置加载参数"""
        try:
            config = get_config()
            my_config = config.get("my_agent", {}).get("my_component", {})
            
            self.threshold = my_config.get("threshold", self._DEFAULT_THRESHOLD)
            # ... 其他配置
            
        except Exception as e:
            logger.warning(f"加载配置失败，使用默认值: {e}")
            self.threshold = self._DEFAULT_THRESHOLD
```

## 3. Prompt 模板规范

### 3.1 Prompt 文件组织

**正确做法**：在 `prompts/` 目录下创建独立的 `{feature}_prompt.py` 文件：

```python
# prompts/error_correction_prompt.py
"""
错误修正 Prompt 定义

分为系统提示和用户提示：
- SYSTEM_PROMPT: 定义任务、规则、输出格式
- build_user_prompt(): 构建用户输入
"""

SYSTEM_PROMPT = """你是一个语义解析修正助手。
...
"""

def build_user_prompt(question: str, ...) -> str:
    """构建用户提示"""
    ...

def get_system_prompt() -> str:
    """获取系统提示"""
    return SYSTEM_PROMPT
```

### 3.2 禁止在组件中直接写 Prompt

**禁止**：
```python
# components/some_component.py
def _build_prompt(self, ...):
    prompt = f"""你是一个助手...  # ❌ 不应该在这里写
    ...
    """
    return prompt
```

**正确做法**：从 prompts 模块导入使用。

### 3.3 Prompt 文件位置规范

Prompt 文件必须放在 `prompts/` 目录下，**禁止**放在模块根目录：

```
# ❌ 错误：prompt.py 放在模块根目录
field_mapper/
├── prompt.py        # 错误位置
├── node.py
└── schemas/

# ✅ 正确：prompt.py 放在 prompts/ 目录
field_mapper/
├── prompts/
│   ├── __init__.py
│   └── prompt.py    # 正确位置
├── node.py
└── schemas/
```

## 4. Schema 规范

### 4.1 数据模型放在 `schemas/` 目录

所有 Pydantic 模型必须放在 `schemas/` 目录下，按功能分文件：
- `output.py` - LLM 输出模型
- `intermediate.py` - 中间数据模型
- `cache.py` - 缓存相关模型
- `enums.py` - 枚举类型

### 4.2 禁止在 schemas 中定义静态配置类

**禁止**在 `schemas/` 目录中创建存放静态配置的 Pydantic 模型。

**区分"静态配置"和"运行时上下文"**：

| 类型 | 特点 | 存放位置 |
|------|------|----------|
| 静态配置 | 阈值、超时、TTL 等固定参数 | `app.yaml` |
| 运行时上下文 | 每次调用时的动态参数（如当前日期） | `schemas/` 中的数据模型 |

**允许**（运行时上下文）：
```python
# ✅ 正确：运行时上下文可以用 Pydantic 模型
class SemanticConfig(BaseModel):
    """运行时上下文，不是配置！"""
    current_date: date  # 每次调用时传入的动态值
    timezone: str = "Asia/Shanghai"  # 默认值从 app.yaml 读取
```

### 4.3 禁止在 components 中定义数据模型

**禁止**：
```python
# components/some_component.py
class MyModel(BaseModel):  # ❌ 不应该在这里定义
    field_name: str
```

**正确做法**：
```python
# schemas/output.py
class MyModel(BaseModel):  # ✅ 在 schemas 中定义
    field_name: str

# components/some_component.py
from ..schemas.output import MyModel  # ✅ 导入使用
```

### 4.4 禁止重复定义功能相同的数据模型

**禁止**为同一概念创建多个数据模型（如 dataclass + Pydantic 两个版本）：

```python
# ❌ 错误：重复定义
@dataclass
class MappingResult:  # dataclass 版本
    business_term: str
    technical_field: str
    confidence: float

class FieldMapping(BaseModel):  # Pydantic 版本，字段几乎一样
    business_term: str
    technical_field: str
    confidence: float
```

**正确做法**：只保留一个，统一使用：

```python
# ✅ 正确：只定义一次
class FieldMapping(BaseModel):
    business_term: str
    technical_field: str
    confidence: float
```

### 4.5 禁止创建兼容层或重新导出文件

项目尚未上线，**禁止**为了向后兼容而创建重新导出的文件：

```python
# ❌ 错误：创建兼容层
# old_schema.py
from .schemas.output import MyModel  # 只是为了兼容旧导入路径
```

**正确做法**：直接修改所有调用方的导入路径。

## 5. 领域数据规范

### 5.1 关键词数据保持独立（keywords_data.py）

关键词是领域知识，**禁止**将其放入 `app.yaml` 配置文件。

**关键词数据的特点**：
- 用于意图识别和复杂度检测的领域词汇
- 相对稳定，不需要运行时动态调整
- 数量较多，放入 YAML 会使配置文件臃肿

**正确做法**：关键词保持在独立的 `keywords_data.py` 文件中。

### 5.2 规则模式保持独立（rules_data.py）

正则表达式等规则模式是领域知识，**禁止**将其放入 `app.yaml`。

**正确做法**：规则模式保持在独立的 `rules_data.py` 文件中。

### 5.3 种子数据保持独立（seed_data.py）

种子数据是用于 RAG 检索和 Few-shot 示例的领域知识数据，**禁止**将其移入 `app.yaml`。

**区分配置和领域数据**：
- **配置（app.yaml）**：阈值、超时、置信度等运行时参数
- **领域数据（*_data.py）**：关键词、规则模式、种子数据等

## 6. 测试规范

### 6.1 使用真实服务，不使用 Mock

- LLM: 使用真实 DeepSeek API
- Embedding: 使用真实 Zhipu API
- Storage: 使用真实 SqliteStore

### 6.2 测试配置

- 配置文件: `analytics_assistant/config/app.yaml`
- 测试运行目录: `analytics_assistant`
- 环境变量: `$env:PYTHONPATH = ".."`

### 6.3 PBT 测试使用 Hypothesis

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1))
def test_property(value: str):
    ...
```

### 6.4 测试文件导入规范

测试文件应从 `schemas/` 目录导入，**禁止**从已删除的兼容层文件导入：

```python
# ❌ 错误：从旧的兼容层导入
from analytics_assistant.src.agents.dimension_hierarchy.schema import DimensionAttributes

# ✅ 正确：从 schemas 目录导入
from analytics_assistant.src.agents.dimension_hierarchy.schemas import DimensionAttributes
```

## 7. 导入规范

### 7.1 禁止使用 TYPE_CHECKING 解决循环依赖

如果出现循环依赖，应该重构代码结构，而不是使用 `TYPE_CHECKING`。

### 7.2 延迟导入规范

**禁止**在函数或方法内部进行导入（延迟导入）：

```python
# ❌ 错误：延迟导入
def some_method(self):
    from analytics_assistant.src.infra.storage import get_kv_store
    store = get_kv_store()
```

**例外情况**（必须添加注释说明原因）：
1. 在 `__init__` 方法中获取全局单例时
2. 避免循环导入时（但应优先考虑重构）
3. 可选依赖的条件导入

```python
# ✅ 正确：例外情况需添加注释
def __init__(self):
    # 延迟导入：获取全局单例，避免模块加载时初始化
    from analytics_assistant.src.infra.storage import get_kv_store
    self._store = get_kv_store()
```

### 7.3 导入位置和引用方式

- **包内引用**：使用相对导入
- **跨包引用**：使用绝对导入路径

```python
# ✅ 正确：包内使用相对导入
from ..schemas.output import SemanticOutput

# ✅ 正确：跨包使用绝对导入
from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.core.schemas.data_model import DataModel
```

### 7.4 导入顺序

1. 标准库
2. 第三方库（LangChain、LangGraph、Pydantic 等）
3. 本项目跨包模块（绝对导入）
4. 本项目包内模块（相对导入）

## 8. 命名规范

- 类名: PascalCase (`SemanticUnderstanding`)
- 函数/方法: snake_case (`_load_config`)
- 常量: UPPER_SNAKE_CASE (`MAX_RETRIES`)
- 私有方法: 前缀下划线 (`_compute_hash`)
- 配置键: snake_case (`max_retries`)

## 9. 项目状态规范

### 9.1 不考虑向下兼容

项目尚未上线，**禁止**为了向下兼容而：
- 保留废弃的类属性
- 保留旧的 API 签名
- 添加兼容层或适配器

**正确做法**：直接修改为新的实现方式，同时更新所有调用方。

## 10. 框架使用规范

### 10.1 基于 LangChain 和 LangGraph 开发

本项目基于 LangChain 和 LangGraph 框架开发，**禁止**重复造轮子。

**必须使用框架提供的功能**：
- LLM 调用：使用 `langchain_core.language_models`
- 消息构建：使用 `langchain_core.messages`
- 状态管理：使用 `langgraph.graph.StateGraph`
- 存储：使用 `langgraph.store`
- Embedding：使用 `langchain_core.embeddings`

### 10.2 复用项目基础设施

优先使用 `analytics_assistant/src/infra/` 和 `analytics_assistant/src/agents/base/` 中的基础设施：

```python
# ✅ 正确：使用项目封装的 LLM 获取函数
from analytics_assistant.src.agents.base.node import get_llm, stream_llm_structured

# ✅ 正确：使用项目封装的存储
from analytics_assistant.src.infra.storage import get_kv_store, CacheManager

# ✅ 正确：使用项目封装的 Embedding
from analytics_assistant.src.infra.ai import get_embeddings
```

## 11. 核心模块规范（core/）

### 11.1 接口定义放在 interfaces.py

所有抽象基类和接口定义放在 `core/interfaces.py`：

```python
# core/interfaces.py
from abc import ABC, abstractmethod

class BasePlatformAdapter(ABC):
    @abstractmethod
    async def get_field_values(self, field_name: str, ...) -> List[str]:
        ...
```

### 11.2 异常定义放在 exceptions.py

所有自定义异常放在 `core/exceptions.py`：

```python
# core/exceptions.py
class AnalyticsAssistantError(Exception):
    """基础异常类"""
    pass

class FieldNotFoundError(AnalyticsAssistantError):
    """字段未找到"""
    pass
```

### 11.3 通用 Schema 放在 core/schemas/

跨 Agent 共享的数据模型放在 `core/schemas/`：
- `data_model.py` - 数据模型定义
- `fields.py` - 字段定义
- `filters.py` - 筛选器定义
- `enums.py` - 通用枚举
- `field_candidate.py` - 字段候选模型（跨模块共享）

### 11.4 跨模块共享的数据模型

当多个 Agent 模块需要使用相同的数据模型时，应将其放在 `core/schemas/` 中：

```python
# ✅ 正确：共享模型放在 core/schemas/
# core/schemas/field_candidate.py
class FieldCandidate(BaseModel):
    """跨模块共享的字段候选模型"""
    field_name: str
    confidence: float
    ...

# 各模块从 core 导入
from analytics_assistant.src.core.schemas import FieldCandidate
```

**禁止**在多个模块中重复定义相同概念的数据模型。

## 12. 平台适配器规范（platform/）

### 12.1 继承 BasePlatformAdapter

所有平台适配器必须继承 `core/interfaces.py` 中的 `BasePlatformAdapter`：

```python
# platform/tableau/adapter.py
from analytics_assistant.src.core.interfaces import BasePlatformAdapter

class TableauAdapter(BasePlatformAdapter):
    async def get_field_values(self, field_name: str, ...) -> List[str]:
        # Tableau 特定实现
        ...
```

### 12.2 平台特定代码隔离

平台特定的代码（如 Tableau VizQL）只能放在对应的 `platform/{platform}/` 目录下，不能污染 `agents/` 或 `core/`。
