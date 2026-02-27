# Analytics Assistant 编码规范

---

## ⚠️⚠️⚠️ 重要警告 - 必读 ⚠️⚠️⚠️

**本文档会在每次对话开始时自动注入到上下文中。**

**所有规则必须无条件遵守，没有例外！**

### 编码前必做检查清单

在编写任何代码之前，**必须**检查以下高频违规项：

| 检查项 | 规则编号 | 常见错误 |
|--------|----------|----------|
| ❌ 延迟导入 | 7.2 | 在函数内部写 `from xxx import yyy` |
| ❌ 重复逻辑 | 4.4, 10.3 | 在多个地方实现相同功能，或重新实现 infra 已有功能 |
| ❌ 硬编码配置 | 2.1, 2.2 | 在代码中写死阈值、超时、策略等参数 |
| ❌ Prompt 位置错误 | 3.3 | Prompt 不在 `prompts/` 目录下 |
| ❌ Schema 位置错误 | 4.1 | 数据模型不在 `schemas/` 目录下 |
| ❌ 简化实现 | 13.1 | 跳过设计要求，返回假的成功结果 |
| ❌ 大小写不一致 | 8.1 | 存储用大写，检索用小写，导致匹配失败 |
| ❌ 裸异常捕获 | 14.2 | `except Exception` 不记录日志、不包含上下文 |
| ❌ 异步阻塞 | 16.3 | 在 async 函数中调用 `time.sleep` 等阻塞 IO |
| ❌ 敏感信息泄露 | 18.1 | API key、token 出现在日志或代码中 |
| ❌ 大写泛型 | 17.4 | 使用 `List[str]` 而非 `list[str]` |
| ❌ 依赖方向错误 | 12A.2 | Agent 导入 orchestration，或 core 导入 infra |
| ❌ 逐个调用外部 API | 23.2 | 未使用批处理调用 LLM/Embedding |
| ❌ 重复创建索引 | 23.3 | 未检查索引是否已存在就创建 |

### 违规后果

- 违反这些规则会导致代码被拒绝
- 用户会要求重写代码
- 浪费时间和资源

### 正确的编码流程

1. **先读本文档** - 确认要写的代码不会违反任何规则
2. **分析依赖方向** - 确定导入是否会造成循环依赖
3. **检查是否重复** - 确认功能是否已在其他地方实现
4. **编写代码** - 遵循所有规范
5. **自查** - 对照检查清单确认没有违规

---

本规范适用于 `analytics_assistant/src/` 目录下的所有代码。

## 1. 目录结构规范

### 1.1 顶层目录结构

```
analytics_assistant/src/
├── agents/              # Agent 模块（LangGraph 工作流）
│   ├── base/            # Agent 基础设施（node.py, middleware_runner.py）
│   ├── semantic_parser/ # 语义解析 Agent
│   ├── field_mapper/    # 字段映射 Agent
│   └── field_semantic/  # 字段语义推断 Agent (维度+度量)
├── core/                # 核心模块（接口、异常、通用 Schema）
│   ├── schemas/         # 通用数据模型
│   ├── interfaces.py    # 抽象接口定义
│   └── exceptions.py    # 自定义异常
├── infra/               # 基础设施（AI、存储、配置、RAG、种子数据）
│   ├── ai/              # LLM、Embedding 封装
│   ├── storage/         # 存储（SqliteStore、缓存）
│   ├── config/          # 配置管理
│   ├── rag/             # RAG 检索
│   └── seeds/           # 全局种子数据（关键词、模式、种子）
├── orchestration/       # 工作流编排
│   └── workflow/        # 工作流上下文（WorkflowContext）
├── platform/            # 平台适配器（Tableau、Power BI 等）
│   ├── base.py          # 平台注册表和工厂
│   └── tableau/         # Tableau 平台实现

# 注意：配置文件在 analytics_assistant/config/app.yaml（与 src/ 同级）
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
├── seeds/               # 种子数据和匹配器（可选）
│   ├── __init__.py
│   └── matchers/        # 基于种子数据的匹配器
├── state.py             # LangGraph State 定义
├── graph.py             # LangGraph 图定义
├── inference.py         # 推理入口（可选，如 field_semantic）
├── utils.py             # 模块内工具函数（可选）
├── keywords_data.py     # 关键词数据（可选，已迁移到 infra/seeds/）
├── rules_data.py        # 规则模式数据（可选，已迁移到 infra/seeds/）
└── seed_data.py         # 种子数据（可选，已迁移到 infra/seeds/）
```

## 2. 配置管理规范 ⚠️ 高频违规

### 2.1 所有可配置参数必须放入 `app.yaml` 🚨

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

field_semantic:
  high_confidence_threshold: 0.85
  rag_threshold_seed: 0.5
  rag_threshold_unverified: 0.6
  llm_batch:
    batch_size: 5
    max_parallel_batches: 6
```

### 2.2 禁止硬编码策略或行为参数 🚨

**禁止**在代码中硬编码应该由配置决定的策略或行为参数：

```python
# ❌ 错误：硬编码检索策略
results = await rag_service.search_async(
    index_name=index_name,
    query=query,
    strategy="hybrid",  # 不应该写死！
)

# ✅ 正确：不传 strategy，使用 app.yaml 中配置的默认值
results = await rag_service.search_async(
    index_name=index_name,
    query=query,
    # strategy 由 app.yaml -> rag.retrieval.retriever_type 决定
)
```

**原则**：如果某个参数在 `app.yaml` 中有配置项，代码中就不应该硬编码该参数。

### 2.3 代码中读取配置的模式

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

## 3. Prompt 模板规范 ⚠️ 高频违规

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

### 3.3 Prompt 文件位置规范 🚨

Prompt 文件必须放在 `prompts/` 目录下，**禁止**放在模块根目录：

> 注意：`infra/` 模块（如 `infra/rag/`）也可以有自己的 `prompts/` 子目录，遵循相同规范。

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

## 4. Schema 规范 ⚠️ 高频违规

### 4.1 数据模型放在 `schemas/` 目录 🚨

所有 Pydantic 模型必须放在 `schemas/` 目录下，按功能分文件：
- `output.py` - LLM 输出模型
- `intermediate.py` - 中间数据模型
- `cache.py` - 缓存相关模型
- `enums.py` - 枚举类型

> 注意：`infra/` 模块（如 `infra/rag/`）也可以有自己的 `schemas/` 子目录，用于定义基础设施内部的验证模型。参见 11.4。

### 4.2 schemas 目录的内容边界

`schemas/` 目录用于存放以下类型的模型：
- Pydantic 数据模型（LLM 输出、中间数据、缓存模型等）
- 运行时上下文模型（每次调用时的动态参数）
- 枚举类型

**禁止**在 `schemas/` 中存放静态配置值（阈值、超时、TTL 等），这些应放在 `app.yaml`。

**配置类的位置**：定义配置参数结构的类（如 `FieldMappingConfig`）可以放在 `schemas/config.py` 中，因为它定义的是数据结构而非配置值本身。配置值从 `app.yaml` 读取。

**区分"静态配置"和"运行时上下文"**：

| 类型 | 特点 | 存放位置 |
|------|------|----------|
| 静态配置值 | 阈值、超时、TTL 等固定参数 | `app.yaml` |
| 配置类定义 | 定义有哪些配置参数、默认值、加载逻辑 | `schemas/config.py` 或模块根目录 `config.py` |
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

### 4.4 禁止重复定义功能相同的数据模型 🚨

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

### 5.1 种子数据的两级组织

种子数据分为两级：

| 级别 | 位置 | 用途 |
|------|------|------|
| 全局种子 | `infra/seeds/` | 跨 Agent 共享的种子数据（维度、度量、计算模式、关键词、正则模式） |
| Agent 种子 | `agents/{name}/seeds/` | Agent 特有的种子匹配器和数据 |

**全局种子目录结构**：
```
infra/seeds/
├── keywords/            # 关键词数据
│   ├── complexity.py    # 复杂度关键词
│   └── intent.py        # 意图关键词
├── patterns/            # 正则模式
│   └── irrelevant.py    # 无关查询模式
├── computation.py       # 计算种子数据
├── dimension.py         # 维度种子数据
└── measure.py           # 度量种子数据
```

### 5.2 关键词数据保持独立

关键词是领域知识，**禁止**将其放入 `app.yaml` 配置文件。

**正确做法**：关键词保持在 `infra/seeds/keywords/` 或 Agent 级别的独立文件中。

### 5.3 规则模式保持独立

正则表达式等规则模式是领域知识，**禁止**将其放入 `app.yaml`。

**正确做法**：规则模式保持在 `infra/seeds/patterns/` 或 Agent 级别的独立文件中。

### 5.4 种子数据保持独立

种子数据是用于 RAG 检索和 Few-shot 示例的领域知识数据，**禁止**将其移入 `app.yaml`。

**区分配置和领域数据**：
- **配置（app.yaml）**：阈值、超时、置信度等运行时参数
- **领域数据（seeds/）**：关键词、规则模式、种子数据等

## 6. 测试规范

### 6.1 测试 Mock 策略

根据测试类型区分 Mock 策略：

| 测试类型 | Mock 策略 | 说明 |
|----------|-----------|------|
| 集成测试 | **禁止 Mock** | 使用真实服务（DeepSeek LLM、Zhipu Embedding、SqliteStore） |
| 单元测试 | **允许 Mock 外部 API** | 可 Mock LLM、Embedding 等外部调用，提高速度和确定性 |
| PBT 属性测试 | **禁止 Mock** | 使用真实服务，确保属性在真实环境下成立。例外：对于纯逻辑属性（如序列化/反序列化对称性），可 Mock 外部依赖以提高测试速度 |

**单元测试 Mock 原则**：
- 只 Mock 外部 API 调用（LLM、Embedding、HTTP 请求）
- **禁止** Mock 内部逻辑（如配置读取、数据模型转换）
- Mock 返回值必须符合真实 API 的数据结构

### 6.2 测试目录结构

测试目录镜像源代码目录结构：

```
analytics_assistant/tests/
├── agents/              # Agent 模块测试
│   ├── base/
│   ├── field_mapper/
│   ├── field_semantic/
│   └── semantic_parser/
├── core/                # 核心模块测试
├── infra/               # 基础设施测试
│   ├── ai/
│   ├── rag/
│   └── storage/
├── orchestration/       # 编排层测试
│   └── workflow/
├── platform/            # 平台适配器测试
│   └── tableau/
├── integration/         # 集成测试（跨模块、端到端）
├── performance/         # 性能基准测试
├── manual/              # 手动测试脚本（按功能分子目录）
│   ├── components/
│   ├── debug/
│   ├── diagnostics/
│   ├── infra/
│   └── integration/
└── test_outputs/        # 测试输出文件（已 gitignore）
```

**规则**：
- 单元测试文件命名：`test_{module_name}.py`
- 测试目录结构必须与源代码目录结构一一对应
- 手动测试脚本按功能分类放入 `manual/` 子目录

### 6.3 测试配置

- 配置文件: `analytics_assistant/config/app.yaml`
- 测试运行目录: `analytics_assistant`
- 环境变量: `$env:PYTHONPATH = ".."`

### 6.4 conftest.py 约定

- 共享 fixture 放在对应测试目录的 `conftest.py` 中
- 全局 fixture（如 LLM mock、配置 mock）放在 `analytics_assistant/tests/conftest.py`
- fixture scope 选择：`function`（默认）用于隔离测试，`session` 用于昂贵的初始化（如真实 LLM 连接）
- **禁止**在 `conftest.py` 中定义业务逻辑或工具函数

### 6.5 PBT 测试使用 Hypothesis

```python
from hypothesis import given, strategies as st

@given(st.text(min_size=1))
def test_property(value: str):
    ...
```

### 6.6 测试文件导入规范

测试文件应从 `schemas/` 目录导入，**禁止**从已删除的兼容层文件导入：

```python
# ❌ 错误：从旧的兼容层导入
from analytics_assistant.src.agents.field_semantic.schema import FieldSemanticAttributes

# ✅ 正确：从 schemas 目录导入
from analytics_assistant.src.agents.field_semantic.schemas import FieldSemanticAttributes
```

## 7. 导入规范 ⚠️⚠️ 最高频违规 ⚠️⚠️

### 7.1 TYPE_CHECKING 使用规范 🚨

优先通过重构代码结构解决循环依赖，而不是使用 `TYPE_CHECKING`。

**允许使用 `TYPE_CHECKING` 的场景**：
- 类型注解必须引用高层模块（如 `orchestration/` 中的类型），且该引用仅用于类型提示而非运行时逻辑
- 两个模块之间存在运行时单向依赖，但类型注解需要双向引用

**使用时必须**：
- 添加注释说明为什么不能通过重构解决
- 确保 `TYPE_CHECKING` 块内的导入仅用于类型注解，不用于运行时逻辑

### 7.2 延迟导入规范 🚨🚨🚨 最高优先级 🚨🚨🚨

⚠️ **重要提醒：这是高频违规项，编码前必须先分析依赖关系！**

⚠️ **每次写代码前，必须检查是否有延迟导入！**

⚠️ **"避免循环依赖"不是延迟导入的借口！先分析依赖方向！**

**禁止**在函数或方法内部进行导入（延迟导入）：

```python
# ❌ 错误：延迟导入
def some_method(self):
    from analytics_assistant.src.infra.storage import get_kv_store
    store = get_kv_store()

# ❌ 错误：以"避免循环依赖"为借口的延迟导入
def _format_history(self, ...):
    # 延迟导入避免循环依赖  ← 这种注释不能作为延迟导入的理由！
    from ..components.history_manager import get_history_manager
```

**编码前必须先分析依赖方向**：

```
正常的依赖方向（不会循环）：
- prompts/ → components/  ✅ 可以直接在顶部导入
- prompts/ → schemas/     ✅ 可以直接在顶部导入
- components/ → schemas/  ✅ 可以直接在顶部导入

可能循环的依赖（需要重构）：
- components/ → prompts/  ⚠️ 反向依赖，需要重构代码结构
```

**例外情况**（以下场景允许延迟导入，必须添加注释说明原因）：
1. 在 `__init__` 方法中获取全局单例时
2. 可选依赖的条件导入（参见 19.1 可选依赖处理规范）
3. 重量级可选依赖仅在特定代码路径使用时（如 `faiss`、`torch`）
4. 启动性能敏感的入口文件，需要延迟加载非关键模块时

> ⚠️ "避免循环导入"**不是**合法的延迟导入理由。实践证明所谓的"循环依赖"往往并不存在（如 `prompt_builder.py` 导入 `HistoryManager` 的案例）。遇到循环依赖时应重构代码结构。

```python
# ✅ 正确：例外情况需添加注释
def __init__(self):
    # 延迟导入：获取全局单例，避免模块加载时初始化
    from analytics_assistant.src.infra.storage import get_kv_store
    self._store = get_kv_store()
```

**正确做法**：在文件顶部导入，与其他导入放在一起：

```python
# ✅ 正确：在文件顶部导入
from ..components.history_manager import HistoryManager

class DynamicPromptBuilder:
    def _format_history(self, ...):
        manager = HistoryManager()  # 直接使用，无需延迟导入
        return manager.format_history_for_prompt(history)
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
- 模块文件: snake_case (`config_loader.py`)
- 枚举成员: UPPER_SNAKE_CASE (`DimensionCategory.TIME`)
- 测试函数: `test_` 前缀 + 描述性名称 (`test_cache_hit_returns_cached_result`)

### 8.1 域模型字段命名约定

项目中常用的字段命名后缀，必须保持一致：

| 后缀 | 含义 | 示例 |
|------|------|------|
| `_luid` | Tableau 全局唯一标识 | `datasource_luid` |
| `_id` | 通用标识符 | `table_id`, `pattern_id` |
| `_key` | 缓存/存储键 | `cache_key` |
| `_ns` | 命名空间 | `cache_ns`, `pattern_ns` |
| `_index` | 索引/字典映射 | `_dimension_seed_index` |
| `_count` | 计数器 | `seed_hit_count`, `retry_count` |
| `_threshold` | 阈值 | `_high_confidence`, `similarity_threshold` |
| `_enabled` | 布尔开关 | `_incremental_enabled` |

**禁止**混用同义后缀（如同时使用 `_id` 和 `_luid` 表示同一概念）。

### 8.2 字段属性大小写约定 🚨

对于 `role`、`data_type` 等字段属性，必须遵循以下约定：

| 场景 | 大小写 | 示例 |
|------|--------|------|
| 内部存储（索引、缓存） | 小写 | `"measure"`, `"dimension"`, `"string"` |
| 检索过滤条件 | 小写 | `filters={"role": "measure"}` |
| 比较判断 | 小写 | `if role.lower() == "measure":` |
| 显示给用户 | 保持原始 | 从数据源获取的原始值 |
| Enum 成员定义 | UPPER_SNAKE_CASE | `DimensionCategory.TIME`（遵循规则 8 命名规范） |
| Enum 成员的 value | 小写 | `TIME = "time"`（存储和比较时使用 `.value`） |

**原因**：避免大小写不一致导致的检索失败。

```python
# ❌ 错误：存储时使用大写，检索时使用小写，导致匹配失败
# 存储
doc = IndexDocument(metadata={"role": "MEASURE"})  # 大写
# 检索
results = search(filters={"role": "measure"})  # 小写，匹配不到！

# ✅ 正确：统一使用小写
# 存储时转小写
role_str = role.lower() if isinstance(role, str) else str(role).lower()
doc = IndexDocument(metadata={"role": role_str})
# 检索时使用小写
results = search(filters={"role": "measure"})
```

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

### 10.2 复用项目基础设施 🚨

优先使用 `analytics_assistant/src/infra/` 和 `analytics_assistant/src/agents/base/` 中的基础设施：

```python
# ✅ 正确：使用项目封装的 LLM 获取函数
from analytics_assistant.src.agents.base import get_llm, stream_llm_structured

# ✅ 正确：使用项目封装的存储
from analytics_assistant.src.infra.storage import get_kv_store, CacheManager

# ✅ 正确：使用项目封装的 Embedding
from analytics_assistant.src.infra.ai import get_embeddings
```

### 10.3 禁止重复实现已有功能 🚨

**禁止**在组件中重新实现 `infra/` 已提供的功能：

```python
# ❌ 错误：自己实现向量检索逻辑
class FieldRetriever:
    async def _embedding_search_by_terms(self, terms, fields):
        # 自己调用 embedding 模型
        embeddings = await self._embeddings.aembed_documents(...)
        # 自己计算相似度
        similarities = cosine_similarity(...)
        # 自己排序返回
        ...

# ✅ 正确：使用 RAG 服务的 search_async 方法
class FieldRetriever:
    async def _retrieve_by_terms(self, terms, fields, index_name):
        # 直接使用 RAG 服务，策略由配置决定
        results = await self._rag_service.retrieval.search_async(
            index_name=index_name,
            query=" ".join(terms),
            top_k=self.top_k,
            filters={"role": role},
        )
```

**检查清单**：
- 需要向量检索？→ 使用 `RAGService.retrieval.search_async()`
- 需要缓存？→ 使用 `CacheManager` 或 `get_kv_store()`
- 需要 LLM 调用？→ 使用 `get_llm()` 或 `stream_llm_structured()`
- 需要 Embedding？→ 使用 `get_embeddings()`

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

自定义异常的放置规则：

| 异常类型 | 位置 | 示例 |
|----------|------|------|
| 全局/跨模块异常 | `core/exceptions.py` | `ValidationError`, `TableauAuthError`, `VizQLError` |
| 基础设施异常 | `infra/{module}/exceptions.py` | `RAGError`, `EmbeddingError`, `StorageError` |
| Agent 特有异常 | 对应 Agent 的 `exceptions.py`（如需要） | 目前未使用 |

```python
# core/exceptions.py - 全局异常
class ValidationError(Exception):
    """验证错误"""
    pass

# infra/rag/exceptions.py - RAG 基础设施异常
class RAGError(Exception):
    """RAG 服务基础异常"""
    pass

class RetrievalError(RAGError):
    """检索相关错误"""
    pass
```

**禁止**在 `components/` 或 `prompts/` 中定义异常类。

### 11.3 通用 Schema 放在 core/schemas/

跨 Agent 共享的数据模型放在 `core/schemas/`：
- `data_model.py` - 数据模型定义
- `fields.py` - 字段定义
- `filters.py` - 筛选器定义
- `computations.py` - 计算模型定义
- `validation.py` - 验证结果模型
- `enums.py` - 通用枚举
- `field_candidate.py` - 字段候选模型（跨模块共享）
- `execute_result.py` - 执行结果模型

### 11.4 基础设施数据模型

`infra/` 模块可以有自己的数据模型文件（如 `infra/rag/models.py`），用于定义基础设施内部的数据结构。这些模型可以使用 `dataclass`（轻量级、无需验证的内部数据）或 `Pydantic`（需要验证的数据）。

```python
# ✅ 正确：infra 内部数据模型使用 dataclass
# infra/rag/models.py
@dataclass
class FieldChunk:
    """字段分块，用于 RAG 索引。"""
    field_name: str
    index_text: str
    ...
```

### 11.5 跨模块共享的数据模型

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

### 12.3 平台工具模块

平台目录下可以有共享的工具模块（如 `ssl_utils.py`），用于消除同一平台内多个文件之间的重复逻辑：

```python
# ✅ 正确：平台内共享工具放在平台目录下
# platform/tableau/ssl_utils.py
def get_ssl_verify() -> Any:
    """获取 SSL 验证配置，供 auth.py 和 client.py 共用。"""
    ...

# platform/tableau/auth.py
from analytics_assistant.src.platform.tableau.ssl_utils import get_ssl_verify

# platform/tableau/client.py
from analytics_assistant.src.platform.tableau.ssl_utils import get_ssl_verify
```

## 12A. 编排层规范（orchestration/）

### 12A.1 WorkflowContext 职责

`orchestration/workflow/context.py` 中的 `WorkflowContext` 是工作流的运行时上下文，负责：
- 管理认证状态和刷新
- 缓存字段值
- 跟踪 schema 变更
- 加载字段语义信息

**禁止**在 `agents/` 中直接管理认证或缓存状态，应通过 `WorkflowContext` 统一管理。

### 12A.2 编排层依赖方向

全局模块间依赖方向（箭头表示"可以导入"）：

```
orchestration/ → agents/    ✅
orchestration/ → platform/  ✅
orchestration/ → infra/     ✅
orchestration/ → core/      ✅
agents/        → core/      ✅
agents/        → infra/     ✅
platform/      → core/      ✅
platform/      → infra/     ✅
infra/         → core/      ✅（仅 schemas、exceptions）
core/          → (无依赖)   ✅ 最底层模块

agents/ → orchestration/    ❌ Agent 不应该导入编排层
agents/ → platform/         ❌ Agent 不应该直接导入平台适配器
core/   → agents/           ❌ 核心模块不应该导入 Agent
core/   → infra/            ❌ 核心模块不应该导入基础设施
infra/  → agents/           ❌ 基础设施不应该导入 Agent
```

## 12B. 大型组件拆分规范

### 12B.1 何时拆分

当一个组件类超过 500 行时，应评估是否需要拆分。判断标准是职责是否单一，而非单纯看行数。如果类职责单一、逻辑连贯，超过 500 行也可以接受；如果职责混杂，即使不到 500 行也应拆分。

拆分后的子模块全部放在 `components/` 目录下：

```
{agent_name}/
├── components/
│   ├── __init__.py
│   ├── cache_mixin.py       # 缓存相关方法
│   ├── rag_mixin.py         # RAG 检索相关方法
│   ├── llm_mixin.py         # LLM 调用相关方法
│   └── seed_match_mixin.py  # 种子匹配相关方法
├── inference.py              # 主类，组合所有 components
└── utils.py                  # 纯函数工具
```

**禁止**为拆分创建独立的 `mixins/` 包。拆分后的子模块统一放在 `components/` 中。

### 12B.2 拆分规则

| 规则 | 说明 |
|------|------|
| 位置 | 拆分后的子模块放在 `components/` 目录下 |
| 命名 | 按功能领域命名，如 `cache_mixin.py`、`rag_mixin.py` |
| 职责 | 每个子模块只负责一个功能领域 |
| 组合方式 | 主类通过继承（Mixin）或组合（委托）使用子模块 |
| 工具函数 | 不依赖 `self` 的纯函数放在 `utils.py` 中 |

```python
# ✅ 正确：Mixin 放在 components/ 中
# components/cache_mixin.py
class CacheMixin:
    """缓存相关方法。依赖主类初始化 self._cache_manager。"""
    
    async def _get_cached_result(self, key: str) -> Optional[Dict]:
        return await self._cache_manager.get(key)

# inference.py
from .components.cache_mixin import CacheMixin
from .components.rag_mixin import RAGMixin

class FieldSemanticInference(CacheMixin, RAGMixin):
    def __init__(self):
        self._cache_manager = CacheManager()  # CacheMixin 依赖
        self._rag_service = RAGService()       # RAGMixin 依赖
```


## 13. 实现完整性规范 ⚠️ 高频违规

### 13.1 禁止简化处理或跳过设计要求 🚨

**禁止**在实现代码时使用"简化处理"、"跳过验证"、"占位实现"等方式绕过设计文档中的功能要求。

**例外情况**：如果存在以下情况之一，可以暂时使用占位实现：

1. **后续任务依赖**：`tasks.md` 中存在后续任务明确负责实现该功能
2. **前置任务阻塞**：该功能依赖的前置任务尚未完成（如依赖 WorkflowContext 扩展）

使用占位实现时，**必须**满足以下要求：

| 要求 | 说明 |
|------|------|
| 代码注释 | 明确标注依赖的任务编号和阻塞原因 |
| 任务标记 | 在 `tasks.md` 中将该任务标记为 `[-]`（进行中）而非 `[x]`（完成） |
| 日志警告 | 运行时输出警告日志，说明当前是占位实现 |
| 不假装完成 | 不能返回假的成功结果（如 `all_valid=True`），应明确标识为占位状态 |

**错误示例**：
```python
# ❌ 错误：简化处理，没有说明原因，假装功能已完成
async def filter_validator_node(state):
    # 这里简化处理，跳过验证
    return {"filter_validation_result": {"all_valid": True}}
```

**正确示例**：
```python
# ✅ 正确：明确标注依赖和阻塞原因
async def filter_validator_node(state):
    """
    ⚠️ 当前状态：占位实现
    
    依赖阻塞：
    - Task 19 (WorkflowContext 扩展) 未完成
      - 需要 WorkflowContext.platform_adapter
      - 需要 WorkflowContext.field_value_cache
    
    完整实现参考：filter_validator_node_full()
    """
    logger.warning(
        "filter_validator_node: 占位实现 - 跳过验证。"
        "依赖 Task 19 (WorkflowContext 扩展) 完成后实现完整功能。"
    )
    # 返回占位结果，但不假装验证通过
    return {
        "filter_validation_result": {
            "results": [],
            "all_valid": True,  # 占位：跳过验证视为通过
            "has_unresolvable_filters": False,
            "needs_confirmation": False,
        }
    }
```

### 13.2 设计文档是实现的唯一标准

- 设计文档（`design.md`）中定义的所有组件、接口、流程都必须完整实现
- 不允许以"性能优化"、"简化"、"临时方案"为由跳过设计要求
- 如果发现设计不合理，应该先修改设计文档，再修改实现

### 13.3 渐进式查询必须完整实现

渐进式查询是核心功能，以下组件必须完整实现：

| 组件 | 设计要求 | 禁止简化 |
|------|----------|----------|
| FilterValueValidator | 验证筛选值是否存在于字段中 | 不能跳过验证直接返回 `all_valid=True` |
| FieldValueCache | 缓存字段值，支持 LRU 淘汰 | 不能省略缓存直接查询数据库 |
| interrupt() 机制 | 筛选值确认时暂停执行等待用户选择 | 不能跳过用户确认直接继续 |
| 多轮确认累积 | `confirmed_filters` 累积所有确认结果 | 不能丢失之前的确认结果 |

### 13.4 依赖注入不是跳过实现的理由

当组件需要依赖（如 `platform_adapter`、`field_value_cache`）时：
- **禁止**因为"依赖未传入"而跳过功能实现
- **正确做法**：通过依赖注入、闭包、或工厂函数提供依赖

```python
# ❌ 错误：因为依赖未传入而跳过
async def filter_validator_node(state):
    # 注意：实际使用时需要传入 platform_adapter
    # 这里简化处理，跳过验证
    return {"all_valid": True}

# ✅ 正确：通过闭包注入依赖
def create_filter_validator_node(
    platform_adapter: BasePlatformAdapter,
    field_value_cache: FieldValueCache,
):
    async def filter_validator_node(state):
        validator = FilterValueValidator(
            platform_adapter=platform_adapter,
            field_value_cache=field_value_cache,
        )
        # 完整实现验证逻辑
        ...
    return filter_validator_node
```


## 14. 错误处理规范

### 14.1 异常类型选择

| 错误类型 | 使用的异常 | 示例 |
|----------|-----------|------|
| 领域/业务错误 | `core/exceptions.py` 中的自定义异常 | `FieldNotFoundError`, `ConfigurationError` |
| 编程错误 | Python 内置异常 | `ValueError`, `TypeError`, `KeyError` |
| 外部服务错误 | 捕获后包装为自定义异常 | `LLMServiceError`, `StorageError` |

### 14.2 禁止裸异常捕获 🚨

**禁止**捕获异常后不记录日志、不包含上下文信息：

```python
# ❌ 错误：裸异常捕获，吞掉错误
try:
    result = await llm.ainvoke(messages)
except Exception:
    return None

# ❌ 错误：捕获但没有上下文
try:
    result = await llm.ainvoke(messages)
except Exception as e:
    logger.error(f"调用失败: {e}")  # 缺少上下文：哪个 LLM？什么输入？

# ✅ 正确：包含上下文信息 + 异常链
try:
    result = await llm.ainvoke(messages)
except Exception as e:
    logger.error(
        f"LLM 调用失败: model={self.model_name}, "
        f"message_count={len(messages)}, error={e}"
    )
    raise LLMServiceError(
        f"LLM 调用失败: {self.model_name}"
    ) from e
```

### 14.3 必须使用异常链

重新抛出异常时，**必须**使用 `from e` 保留原始异常栈：

```python
# ❌ 错误：丢失原始异常
except ValueError as e:
    raise ConfigurationError("配置解析失败")

# ✅ 正确：保留异常链
except ValueError as e:
    raise ConfigurationError("配置解析失败") from e
```

### 14.4 日志级别指南

| 级别 | 使用场景 | 示例 |
|------|----------|------|
| `logger.warning` | 可恢复的降级 | 配置加载失败使用默认值、缓存未命中 |
| `logger.error` | 不可恢复的失败 | API 调用失败、数据完整性错误 |
| `logger.exception` | 意外异常（需要 traceback） | 未预期的运行时错误 |

```python
# ✅ 正确：根据严重程度选择日志级别
try:
    config = get_config()
except FileNotFoundError:
    logger.warning("配置文件未找到，使用默认值")  # 可恢复
    config = DEFAULT_CONFIG
except Exception as e:
    logger.exception(f"配置加载异常: {e}")  # 意外错误，需要 traceback
    raise
```

## 15. 日志规范

### 15.1 Logger 获取方式

每个模块使用 `__name__` 获取 logger：

```python
import logging

logger = logging.getLogger(__name__)
```

**禁止**使用硬编码的 logger 名称或 `print` 语句。

### 15.2 结构化日志字段

关键业务操作应包含可追踪的上下文字段：

```python
# ✅ 正确：包含追踪字段
logger.info(
    f"字段映射完成: datasource_luid={datasource_luid}, "
    f"field_count={len(fields)}, duration={elapsed:.2f}s"
)

# ✅ 正确：RAG 检索日志
logger.debug(
    f"RAG 检索: index={index_name}, query='{query[:50]}', "
    f"top_k={top_k}, results={len(results)}"
)
```

### 15.3 敏感数据脱敏 🚨

**禁止**在日志中输出以下敏感信息：
- API Key / Token / Secret
- 用户密码
- 完整的认证头（Authorization header）

```python
# ❌ 错误：泄露 API Key
logger.info(f"使用 API Key: {api_key}")

# ✅ 正确：脱敏处理
logger.info(f"使用 API Key: {api_key[:8]}***")
```

### 15.4 日志级别使用规范

| 级别 | 用途 | 示例 |
|------|------|------|
| DEBUG | 内部状态、调试信息 | 中间计算结果、缓存命中/未命中 |
| INFO | 业务事件、流程节点 | Agent 启动、字段映射完成、查询生成成功 |
| WARNING | 降级、非预期但可恢复 | 配置缺失用默认值、重试成功 |
| ERROR | 失败、需要关注 | API 调用失败、数据不一致 |

## 16. 异步编程规范

### 16.1 并发执行独立操作

对于互不依赖的异步操作，使用 `asyncio.gather` 并发执行：

```python
# ❌ 错误：串行执行独立操作
result_a = await fetch_data_a()
result_b = await fetch_data_b()

# ✅ 正确：并发执行
result_a, result_b = await asyncio.gather(
    fetch_data_a(),
    fetch_data_b(),
)
```

### 16.2 并发限制

使用 `asyncio.Semaphore` 控制并发度，避免过载外部服务：

```python
# ✅ 正确：限制并发（参考 filter_validator.py 的模式）
semaphore = asyncio.Semaphore(max_concurrent)

async def limited_task(item):
    async with semaphore:
        return await process(item)

results = await asyncio.gather(*[limited_task(item) for item in items])
```

### 16.3 禁止在异步函数中使用阻塞调用 🚨

**禁止**在 `async def` 函数中使用阻塞 IO：

```python
# ❌ 错误：阻塞调用
async def fetch_data():
    time.sleep(1)  # 阻塞整个事件循环！
    response = requests.get(url)  # 同步 HTTP！

# ✅ 正确：使用异步替代
async def fetch_data():
    await asyncio.sleep(1)
    async with httpx.AsyncClient() as client:
        response = await client.get(url)
```

### 16.4 超时控制

对外部调用设置超时，防止无限等待：

```python
# ✅ 正确：使用 asyncio.wait_for 设置超时
try:
    result = await asyncio.wait_for(
        external_api_call(),
        timeout=self.timeout,  # 从 app.yaml 读取
    )
except asyncio.TimeoutError:
    logger.error(f"外部调用超时: timeout={self.timeout}s")
    raise
```

## 17. 类型注解规范

### 17.1 公开函数必须有完整类型注解

所有公开函数（不以 `_` 开头）**必须**包含参数类型和返回值类型注解：

```python
# ❌ 错误：缺少类型注解
def process_fields(fields, threshold):
    ...

# ✅ 正确：完整类型注解
def process_fields(
    fields: List[FieldCandidate],
    threshold: float,
) -> List[FieldMapping]:
    ...
```

### 17.2 Optional 类型约定

使用 `Optional[X]` 而非 `X | None`，与现有代码库保持一致：

```python
# ❌ 错误：使用 X | None（Python 3.10+ 语法）
def get_field(name: str) -> FieldCandidate | None:
    ...

# ✅ 正确：使用 Optional
from typing import Optional

def get_field(name: str) -> Optional[FieldCandidate]:
    ...
```

### 17.3 泛型类型

使用 `TypeVar` 定义泛型类型（参考 `agents/base/node.py` 的模式）：

```python
from typing import TypeVar

T = TypeVar("T", bound=BaseModel)

async def stream_llm_structured(
    messages: List[BaseMessage],
    output_schema: Type[T],
) -> T:
    ...
```

### 17.4 泛型类型语法

统一使用 Python 3.9+ 的内置泛型语法（小写 `list`, `dict`, `tuple`），不再使用 `typing` 模块的大写版本：

```python
# ❌ 过时：使用 typing 模块的大写泛型
from typing import Dict, List

def process(items: List[str]) -> Dict[str, int]:
    ...

# ✅ 正确：使用内置泛型（Python 3.9+ 语法）
def process(items: list[str]) -> dict[str, int]:
    ...
```

| 过时 | 正确 |
|------|------|
| `List[str]` | `list[str]` |
| `Dict[str, int]` | `dict[str, int]` |
| `Tuple[str, ...]` | `tuple[str, ...]` |
| `Set[str]` | `set[str]` |

> 注意：`Optional[X]` 和 `X | None` 的选择见规则 17.2，保持使用 `Optional[X]`。

## 18. 安全规范

### 18.1 敏感配置必须使用环境变量 🚨

API Key、密码、Token 等敏感信息**禁止**硬编码在 `app.yaml` 或源代码中：

```yaml
# ❌ 错误：硬编码 API Key
ai:
  deepseek:
    api_key: "sk-1234567890abcdef"

# ✅ 正确：使用环境变量展开
ai:
  deepseek:
    api_key: "${DEEPSEEK_API_KEY}"
```

```python
# ❌ 错误：代码中硬编码
API_KEY = "sk-1234567890abcdef"

# ✅ 正确：从环境变量读取
import os
API_KEY = os.environ.get("DEEPSEEK_API_KEY")
```

### 18.2 SSL 验证

生产环境**必须**启用 SSL 验证：

```python
# ❌ 错误：禁用 SSL 验证
async with httpx.AsyncClient(verify=False) as client:
    ...

# ✅ 正确：启用 SSL（默认行为）
async with httpx.AsyncClient() as client:
    ...
```

> 开发/调试环境如需禁用 SSL，必须通过 `app.yaml` 配置控制，不能硬编码。

## 19. 可选依赖处理规范

### 19.1 标准模式

可选依赖使用模块级 `try/except` + `_XXX_AVAILABLE` 标志：

```python
# ✅ 正确：可选依赖标准模式（参考 semantic_cache.py）
import logging

logger = logging.getLogger(__name__)

try:
    import faiss
    _FAISS_AVAILABLE = True
except ImportError:
    _FAISS_AVAILABLE = False
    logger.info("faiss 未安装，语义缓存功能不可用")


class SemanticCache:
    def __init__(self):
        if not _FAISS_AVAILABLE:
            raise ImportError(
                "语义缓存需要 faiss 库，请安装: pip install faiss-cpu"
            )
        self._index = faiss.IndexFlatIP(self._dimension)
```

**规则**：
- `try/except ImportError` 必须在模块顶层（不在函数内）
- 标志变量命名：`_XXX_AVAILABLE`（大写，前缀下划线）
- 使用处检查标志，给出清晰的错误提示

## 20. Docstring 规范

### 20.1 使用 Google 风格

与现有代码库保持一致，使用 Google 风格 docstring：

```python
def search_fields(
    query: str,
    top_k: int = 10,
    filters: Optional[Dict[str, str]] = None,
) -> List[FieldCandidate]:
    """根据查询文本检索匹配的字段候选。

    Args:
        query: 用户输入的自然语言查询。
        top_k: 返回的最大候选数量。
        filters: 可选的过滤条件，如 {"role": "measure"}。

    Returns:
        按相关性排序的字段候选列表。

    Raises:
        RAGServiceError: RAG 检索服务调用失败时抛出。
    """
    ...
```

### 20.2 必须编写 Docstring 的场景

| 场景 | 要求 |
|------|------|
| 公开类 | 必须，说明类的职责和使用方式 |
| 公开方法（非 trivial） | 必须，包含 Args / Returns / Raises |
| 公开函数（非 trivial） | 必须，包含 Args / Returns / Raises |
| 简单的 getter/setter/属性方法 | 可省略，如果函数名已经完全说明了意图（如 `get_stats`、`set_retriever`） |
| 私有方法（复杂逻辑） | 建议，说明算法或关键决策 |
| 模块文件 | 建议，在文件顶部说明模块职责 |

### 20.3 Docstring 应提供额外信息

Docstring 应补充函数签名无法表达的信息（如副作用、使用约束、算法说明），而不是简单重复函数名：

```python
# ❌ 错误：重复函数名，没有额外信息
def get_config():
    """获取配置。"""  # 这和函数名说的一样
    ...

# ✅ 正确：提供有价值的信息
def get_config():
    """加载并返回 app.yaml 配置，使用单例模式缓存。"""
    ...

# ✅ 也正确：简单方法可以省略 Docstring
@property
def field_count(self) -> int:
    return len(self._field_chunks)
```

## 21. 注释规范

### 21.1 行内注释

行内注释用于解释"为什么"而非"做什么"：

```python
# ❌ 错误：描述代码在做什么（代码本身已经说明）
role_str = role.lower()  # 转为小写

# ✅ 正确：解释为什么这样做
role_str = role.lower()  # 统一小写，避免存储/检索大小写不一致（Rule 8.2）
```

### 21.2 TODO/FIXME 格式

使用统一格式标记待办事项，便于全局搜索和追踪：

```python
# TODO: 简要描述待完成的工作
# TODO: 实现 L1 小模型分类（参见 design.md 3.2 节）

# FIXME: 简要描述已知问题
# FIXME: 高并发下 pattern_index 可能丢失更新
```

**规则**：
- `TODO` 用于计划中的功能或改进
- `FIXME` 用于已知的 bug 或需要修复的问题
- **禁止**使用 `HACK`、`XXX` 等非标准标记
- 每个 TODO/FIXME 必须有简要描述，不能只写标记

### 21.3 复杂逻辑注释

对于非显而易见的算法或业务逻辑，**必须**添加块注释说明：

```python
# ✅ 正确：解释复杂的业务逻辑
# 推断策略优先级：
# 1. 种子匹配且有 aliases → 直接使用（置信度 1.0）
# 2. 种子匹配但无 aliases → 走 LLM 补充 aliases
# 3. RAG 匹配 → 作为 LLM 参考上下文
# 4. 未匹配 → 完全由 LLM 推断
for f in fields_to_infer:
    ...
```

## 22. 重试与降级策略规范

### 22.1 异常可重试分类

异常必须明确是否可重试，参考 `VizQLError.is_retryable` 模式：

| 异常类型 | 可重试 | 策略 |
|----------|--------|------|
| 网络错误 / 超时 | ✅ | 指数退避重试 |
| 服务器错误 (5xx) | ✅ | 指数退避重试 |
| 限流 (429) | ✅ | 等待 `Retry-After` 后重试 |
| 认证错误 (401/403) | ❌ | 立即失败，刷新凭证 |
| 客户端错误 (400) | ❌ | 立即失败，修正输入 |
| 验证错误 | ❌ | 立即失败，修正数据 |

### 22.2 重试参数从配置读取

重试次数、超时等参数**必须**从 `app.yaml` 读取：

```python
# ✅ 正确：重试参数从配置读取
class ErrorCorrector:
    def __init__(self):
        config = get_config().get("semantic_parser", {}).get("error_corrector", {})
        self._max_retries = config.get("max_retries", 3)
        self._max_same_error_count = config.get("max_same_error_count", 2)
```

### 22.3 降级策略

当外部服务不可用时，必须有明确的降级路径：

| 服务 | 降级策略 |
|------|----------|
| RAG 检索失败 | 跳过 RAG，直接走 LLM 推断 |
| LLM 调用失败 | 使用默认属性值（`_default_attrs`） |
| 缓存不可用 | 跳过缓存，每次重新计算 |
| 配置加载失败 | 使用代码中的 `_DEFAULT_*` 常量 |

**禁止**在降级时静默失败，必须记录 `logger.warning` 日志。

## 23. 性能优化规范

### 23.1 缓存策略

| 缓存类型 | 实现 | 适用场景 |
|----------|------|----------|
| 结果缓存 | `CacheManager` (KV Store) | 字段语义推断结果、字段映射结果 |
| 查询缓存 | `QueryCache` (FAISS 语义) | 相似查询复用 |
| 字段值缓存 | `FieldValueCache` (LRU) | 筛选值验证 |
| 配置缓存 | `AppConfig` (单例) | 全局配置 |

**规则**：
- 缓存 TTL 从 `app.yaml` 读取
- 缓存键必须包含足够的区分信息（如 `datasource_luid` + `table_id`）
- 增量更新优先于全量刷新（参考 `compute_incremental_fields`）

### 23.2 批处理

对外部 API 调用（LLM、Embedding）**必须**使用批处理：

```python
# ❌ 错误：逐个调用 LLM
for field in fields:
    result = await llm.ainvoke(build_prompt(field))

# ✅ 正确：批量调用（参考 llm_mixin.py 的模式）
field_batches = [fields[i:i + batch_size] for i in range(0, len(fields), batch_size)]
results = await asyncio.gather(*[process_batch(batch) for batch in field_batches])
```

**批处理参数**从 `app.yaml` 读取：
- `batch_size`: 每批处理的字段数
- `max_parallel_batches`: 最大并行批次数

### 23.3 索引复用

RAG 索引创建成本高，**必须**复用已有索引：

```python
# ✅ 正确：检查索引是否已存在，避免重复创建
existing_index = rag_service.index.get_index(index_name)
if existing_index is not None:
    logger.info(f"RAG 索引已存在: {index_name}")
    return

# 只在索引不存在时创建
rag_service.index.create_index(name=index_name, config=config, documents=documents)
```

**规则**：
- 索引创建前必须检查是否已存在
- 新增文档使用 `add_documents` 增量更新，而非重建索引
- 索引持久化目录从 `app.yaml` 的 `vector_storage.index_dir` 读取

## 24. 适用范围

### 24.1 本规范的适用范围

本规范**仅适用于 Python 后端代码**，即 `analytics_assistant/src/` 和 `analytics_assistant/tests/` 目录下的所有代码。

**不在本规范范围内**：
- 前端代码（如有）
- 部署脚本和 CI/CD 配置
- 文档和 Markdown 文件（除本规范自身）

---

## 📋 编码完成后自查清单

在提交代码前，**必须**逐项检查：

### 导入检查
- [ ] 所有导入都在文件顶部（没有延迟导入）
- [ ] 包内使用相对导入，跨包使用绝对导入
- [ ] 导入顺序正确（标准库 → 第三方 → 项目跨包 → 项目包内）
- [ ] 依赖方向正确（参见 12A.2 全局依赖方向图）

### 文件位置检查
- [ ] Prompt 文件在 `prompts/` 目录下
- [ ] Schema 文件在 `schemas/` 目录下
- [ ] 异常类在 `core/exceptions.py` 或 `infra/{module}/exceptions.py` 中
- [ ] 配置参数在 `app.yaml` 中
- [ ] 种子数据在 `infra/seeds/` 或 Agent 级别的 `seeds/` 中

### 代码质量检查
- [ ] 没有重复定义相同功能的数据模型
- [ ] 没有重复实现相同的逻辑
- [ ] 没有硬编码的配置参数
- [ ] 没有简化处理或跳过设计要求

### 框架使用检查
- [ ] 使用 LangChain/LangGraph 提供的功能
- [ ] 复用 `infra/` 和 `agents/base/` 中的基础设施

### 错误处理检查
- [ ] 异常包含上下文信息（字段名、数据源 ID 等）
- [ ] 重新抛出异常使用 `from e` 异常链
- [ ] 日志级别正确（warning 可恢复 / error 不可恢复 / exception 意外）
- [ ] 降级路径有 `logger.warning` 日志（Rule 22.3）

### 类型注解检查
- [ ] 所有公开函数有完整类型注解（参数 + 返回值）
- [ ] 使用 `Optional[X]` 而非 `X | None`
- [ ] 使用 `list[x]` / `dict[k, v]` 而非 `List[X]` / `Dict[K, V]`（Python 3.9+ 内置泛型）

### 性能检查
- [ ] 外部 API 调用使用批处理（Rule 23.2）
- [ ] RAG 索引创建前检查是否已存在（Rule 23.3）
- [ ] 缓存 TTL 和批处理参数从 `app.yaml` 读取

### 安全检查
- [ ] 无硬编码的 API Key、Token、密码
- [ ] 日志中敏感信息已脱敏
- [ ] 生产环境 SSL 验证已启用

---

**记住：遵守规范不是可选的，是必须的！**
