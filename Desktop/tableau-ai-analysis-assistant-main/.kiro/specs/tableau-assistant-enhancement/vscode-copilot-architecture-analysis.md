# VSCode Copilot Chat 架构深度分析

## 目录

1. [项目概述](#项目概述)
2. [核心架构](#核心架构)
3. [关键功能模块](#关键功能模块)
4. [技术栈和设计模式](#技术栈和设计模式)
5. [与 Tableau Assistant 的对比](#与-tableau-assistant-的对比)
6. [可借鉴的设计](#可借鉴的设计)

---

## 项目概述

### 基本信息

**VSCode Copilot Chat** 是 Microsoft 开发的 AI 编程助手，集成在 Visual Studio Code 中。

**核心能力**：
- **Inline Suggestions**: 代码补全（Ghost Text）
- **Chat Interface**: 对话式编程助手
- **Agent Mode**: 自主多步骤编程（自动处理错误、迭代直到完成）
- **Edit Mode**: 多文件编辑
- **Tool Calling**: 调用外部工具（文件操作、终端、搜索等）
- **Multi-modal**: 支持图片输入
- **MCP Support**: 支持 Model Context Protocol

**支持的运行时**：
- Node.js（桌面版）
- Web Worker（浏览器版，无服务器）


---

## 核心架构

### 1. 分层架构（Layered Architecture）

VSCode Copilot 采用严格的分层架构，类似于 VSCode 本身：

```
┌─────────────────────────────────────────┐
│         Extension Layer                  │  ← 业务逻辑
│  (agents, chat, tools, intents)         │
├─────────────────────────────────────────┤
│         Platform Layer                   │  ← 平台服务
│  (telemetry, config, search, git)       │
├─────────────────────────────────────────┤
│         Util Layer                       │  ← 工具函数
│  (common utilities, types)               │
└─────────────────────────────────────────┘
```

**层级规则**：
- `common`: 纯 JavaScript，无运行时依赖
- `vscode`: 可访问 VSCode API
- `node`: 可访问 Node.js API
- `vscode-node`: 可访问 VSCode + Node.js API
- `worker`: Web Worker API
- `vscode-worker`: VSCode + Web Worker API

**依赖规则**：
- ✅ `extension` 可以导入 `platform` 和 `util`
- ✅ `platform` 可以导入 `util`
- ❌ `util` 不能导入 `platform` 或 `extension`
- ❌ 低层不能导入高层



### 2. 服务和贡献系统（Services & Contributions）

**依赖注入（Dependency Injection）**：

```typescript
// 服务定义
interface IMyService {
    doSomething(): void;
}

// 服务实现
class MyService implements IMyService {
    constructor(
        @IConfigurationService private readonly config: IConfigurationService,
        @ITelemetryService private readonly telemetry: ITelemetryService
    ) {}
    
    doSomething() {
        // 使用注入的服务
    }
}

// 服务注册
registerSingleton(IMyService, MyService);
```

**贡献（Contributions）**：
- 自动注册和激活
- 按运行时分离（vscode / vscode-node / vscode-worker）
- 生命周期管理

**文件位置**：
- `src/extension/extension/vscode/services.ts` - 通用服务
- `src/extension/extension/vscode-node/services.ts` - Node.js 服务
- `src/extension/extension/vscode/contributions.ts` - 通用贡献
- `src/extension/extension/vscode-node/contributions.ts` - Node.js 贡献



### 3. Prompt-TSX 系统

**核心创新**：使用 TSX 组件化方式构建 Prompt

**传统方式的问题**：
```typescript
// ❌ 传统字符串拼接
const prompt = `
System: You are a helpful assistant.
${safetyRules}
${metadata}
User: ${question}
`;
// 问题：难以管理优先级、Token 预算、动态组合
```

**Prompt-TSX 方式**：
```tsx
// ✅ 组件化 Prompt
class MyPrompt extends PromptElement<Props> {
    render() {
        return <>
            <SystemMessage priority={100}>
                You are a helpful assistant.
                <SafetyRules />
            </SystemMessage>
            <UserMessage priority={50}>
                <Metadata fields={this.props.fields} />
                {this.props.question}
            </UserMessage>
        </>;
    }
}
```

**优势**：
1. **优先级管理**：每个组件有 `priority`，超出 Token 预算时自动裁剪低优先级内容
2. **动态组合**：根据条件渲染不同组件
3. **可复用**：SafetyRules、Metadata 等可跨 Prompt 复用
4. **类型安全**：TypeScript 类型检查
5. **异步准备**：`prepare()` 方法可以异步加载数据



### 4. Prompt Registry（多模型适配）

**问题**：不同 LLM 模型需要不同的 Prompt 策略

**解决方案**：Prompt Registry 系统

```typescript
// Prompt Resolver
class GPTPromptResolver implements IAgentPrompt {
    static readonly familyPrefixes = ['gpt-4', 'gpt-3.5'];
    
    resolvePrompt(endpoint: IChatEndpoint): PromptConstructor {
        if (endpoint.model?.startsWith('gpt-4')) {
            return GPT4Prompt;  // 复杂 Prompt
        }
        return GPT35Prompt;  // 简化 Prompt
    }
}

// 注册
PromptRegistry.registerPrompt(GPTPromptResolver);
```

**支持的模型**：
- OpenAI (GPT-4, GPT-3.5)
- Anthropic (Claude)
- Google (Gemini)
- xAI (Grok)
- VSCode Models

**每个模型的 Prompt 优化**：
- GPT-4：详细指令，复杂思维链
- GPT-3.5：简化指令，减少 Token
- Claude：结构化标签（`<task>`, `<output_format>`）
- Gemini：特定格式要求



---

## 关键功能模块

### 1. Agent Mode（自主编程模式）

**核心文件**：
- `src/extension/intents/node/toolCallingLoop.ts` - Agent 循环
- `src/extension/prompts/node/agent/agentPrompt.tsx` - Agent Prompt
- `src/extension/conversation/vscode-node/chatParticipants.ts` - 注册 Agent

**工作流程**：

```
用户请求
    ↓
理解意图
    ↓
生成计划（TODO List）
    ↓
┌─────────────────────┐
│  Tool Calling Loop  │
│  ┌───────────────┐  │
│  │ 1. 调用工具   │  │
│  │ 2. 获取结果   │  │
│  │ 3. 分析结果   │  │
│  │ 4. 决定下一步 │  │
│  └───────────────┘  │
│         ↓           │
│    是否完成?        │
│    ↙     ↘         │
│  是       否        │
│  ↓       ↓         │
│ 结束    继续循环    │
└─────────────────────┘
    ↓
生成总结
```

**关键特性**：
1. **自动错误处理**：编译错误、测试失败自动修复
2. **迭代优化**：不断尝试直到任务完成
3. **进度追踪**：TODO List 管理
4. **并行执行**：多个工具并行调用
5. **上下文管理**：自动压缩历史对话



### 2. Tool System（工具系统）

**工具定义**：

```json
// package.json
{
  "contributes": {
    "languageModelTools": [
      {
        "name": "copilot_readFile",
        "toolReferenceName": "read_file",
        "modelDescription": "Read the contents of a file...",
        "inputSchema": {
          "type": "object",
          "properties": {
            "uri": {
              "type": "string",
              "description": "Absolute file path"
            }
          },
          "required": ["uri"]
        }
      }
    ]
  }
}
```

**工具实现**：

```typescript
// src/extension/tools/node/readFile.ts
export class ReadFileTool implements vscode.LanguageModelTool {
    async invoke(
        options: vscode.LanguageModelToolInvocationOptions,
        token: vscode.CancellationToken
    ): Promise<vscode.LanguageModelToolResult> {
        const { uri } = options.input;
        const content = await vscode.workspace.fs.readFile(uri);
        
        return {
            content: [
                new vscode.LanguageModelTextPart(content.toString())
            ]
        };
    }
}
```

**内置工具分类**：

| 类别 | 工具 | 功能 |
|------|------|------|
| **文件操作** | read_file | 读取文件 |
| | replace_string_in_file | 替换字符串 |
| | apply_patch | 应用补丁 |
| | insert_into_file | 插入内容 |
| **代码搜索** | semantic_search | 语义搜索 |
| | grep_search | 正则搜索 |
| | file_search | 文件名搜索 |
| **终端** | run_in_terminal | 执行命令 |
| **任务管理** | manage_todo_list | 管理 TODO |
| **诊断** | get_diagnostics | 获取编译错误 |



### 3. Context Management（上下文管理）

**挑战**：
- 对话历史越来越长
- 元数据可能很大
- Token 预算有限

**解决方案**：

#### 3.1 Prompt-TSX 优先级裁剪

```tsx
<SystemMessage priority={100}>  {/* 最高优先级，永不裁剪 */}
    <SafetyRules />
</SystemMessage>

<UserMessage priority={80}>  {/* 高优先级 */}
    <Metadata />
</UserMessage>

<UserMessage priority={50}>  {/* 中优先级 */}
    <ConversationHistory />
</UserMessage>

<UserMessage priority={20}>  {/* 低优先级，优先裁剪 */}
    <AdditionalContext />
</UserMessage>
```

#### 3.2 对话历史压缩

```typescript
// 保留策略
- 保留第一条（系统提示）
- 保留最近 N 条
- 中间的对话生成摘要

// 示例
[
    SystemMessage,  // 保留
    ...oldMessages.map(summarize),  // 摘要
    ...recentMessages  // 保留最近 5 条
]
```

#### 3.3 元数据过滤

```typescript
// 语义搜索相关字段
const relevantFields = semanticSearch(question, allFields, topK=10);

// 只传递相关字段给 LLM
<Metadata fields={relevantFields} />
```



### 4. Multi-modal Support（多模态支持）

**支持的输入类型**：
- 文本
- 图片（截图、UI 设计稿）
- 文件引用

**实现方式**：

```typescript
// 图片处理
interface ImageAttachment {
    uri: vscode.Uri;
    mimeType: string;
    data: Uint8Array;
}

// 在 Prompt 中包含图片
<UserMessage>
    <ImagePart data={image.data} mimeType={image.mimeType} />
    <TextPart>Analyze this screenshot</TextPart>
</UserMessage>
```

**应用场景**：
- 上传错误截图，AI 分析问题
- 上传 UI 设计稿，生成代码
- 上传数据表截图，分析数据



### 5. MCP (Model Context Protocol) 支持

**什么是 MCP？**
- 标准化的工具调用协议
- 类似于 LSP（Language Server Protocol）
- 允许第三方扩展提供工具

**架构**：

```
┌─────────────────┐
│  VSCode Copilot │
└────────┬────────┘
         │ MCP Protocol
    ┌────┴────┬────────┬────────┐
    │         │        │        │
┌───▼───┐ ┌──▼──┐ ┌───▼───┐ ┌──▼──┐
│Tableau│ │ Git │ │ Jira  │ │ ... │
│ MCP   │ │ MCP │ │  MCP  │ │     │
└───────┘ └─────┘ └───────┘ └─────┘
```

**配置示例**：

```json
// .vscode/mcp.json
{
  "mcpServers": {
    "tableau": {
      "command": "node",
      "args": ["tableau-mcp-server.js"],
      "env": {
        "TABLEAU_URL": "https://tableau.company.com"
      }
    }
  }
}
```

**优势**：
- 标准化接口
- 第三方可扩展
- 权限控制
- 错误处理统一



---

## 技术栈和设计模式

### 1. 技术栈

| 层级 | 技术 |
|------|------|
| **语言** | TypeScript |
| **UI 框架** | React (TSX) |
| **Prompt 框架** | Prompt-TSX (自研) |
| **测试** | Mocha, Vitest |
| **构建** | esbuild, Vite |
| **代码解析** | Tree-sitter (WASM) |
| **向量搜索** | Embeddings API |
| **LLM 调用** | OpenAI API, Anthropic API |

### 2. 核心设计模式

#### 2.1 依赖注入（Dependency Injection）

```typescript
// 服务接口
interface IConfigurationService {
    get<T>(key: string): T;
}

// 服务实现
class ConfigurationService implements IConfigurationService {
    get<T>(key: string): T {
        return vscode.workspace.getConfiguration().get(key);
    }
}

// 使用依赖注入
class MyFeature {
    constructor(
        @IConfigurationService private readonly config: IConfigurationService
    ) {}
}
```

**优势**：
- 解耦
- 可测试
- 可替换实现



#### 2.2 策略模式（Strategy Pattern）

```typescript
// Prompt Registry 使用策略模式
interface IAgentPrompt {
    resolvePrompt(endpoint: IChatEndpoint): PromptConstructor;
}

class GPTPromptResolver implements IAgentPrompt {
    resolvePrompt(endpoint: IChatEndpoint) {
        return GPT4Prompt;
    }
}

class ClaudePromptResolver implements IAgentPrompt {
    resolvePrompt(endpoint: IChatEndpoint) {
        return ClaudePrompt;
    }
}

// 运行时选择策略
const resolver = PromptRegistry.getResolver(endpoint.model);
const PromptClass = resolver.resolvePrompt(endpoint);
```

#### 2.3 组合模式（Composite Pattern）

```tsx
// Prompt-TSX 使用组合模式
<SystemMessage>
    <SafetyRules />
    <ToolInstructions>
        <FileEditInstructions />
        <TerminalInstructions />
    </ToolInstructions>
</SystemMessage>
```

#### 2.4 观察者模式（Observer Pattern）

```typescript
// 进度报告
const progress = new vscode.Progress<ChatResponsePart>();

progress.report({ kind: 'text', text: 'Analyzing...' });
progress.report({ kind: 'toolCall', tool: 'read_file' });
progress.report({ kind: 'text', text: 'Done!' });
```



### 3. 测试策略

#### 3.1 单元测试

```typescript
// 工具测试
describe('ReadFileTool', () => {
    it('should read file content', async () => {
        const tool = new ReadFileTool();
        const result = await tool.invoke({
            input: { uri: 'file:///test.txt' }
        });
        expect(result.content).toMatchSnapshot();
    });
});
```

#### 3.2 集成测试

```typescript
// 在 VSCode 环境中测试
describe('Agent Mode', () => {
    it('should complete task end-to-end', async () => {
        const request = createChatRequest('Add error handling');
        const response = await agent.handle(request);
        expect(response.edits).toHaveLength(1);
    });
});
```

#### 3.3 Simulation Tests（模拟测试）

```typescript
// 真实 LLM 调用测试
describe('Simulation', () => {
    it('should fix compilation errors', async () => {
        // 运行 10 次，测试随机性
        const results = await runSimulation(10, {
            task: 'Fix the TypeScript error',
            expectedOutcome: 'no errors'
        });
        
        // 快照测试
        expect(results).toMatchBaseline();
    });
});
```

**特点**：
- 真实 LLM 调用
- 结果缓存（避免重复调用）
- 基线对比（质量回归检测）
- 运行 10 次（处理随机性）



---

## 与 Tableau Assistant 的对比

### 架构对比

| 维度 | VSCode Copilot | Tableau Assistant |
|------|----------------|-------------------|
| **框架** | 自研 Prompt-TSX | LangGraph |
| **分层** | 严格分层（common/vscode/node） | 相对扁平 |
| **依赖注入** | 完整 DI 系统 | 手动传递依赖 |
| **Prompt 管理** | 组件化 TSX | 字符串模板 |
| **多模型支持** | Prompt Registry | 单一模板 |
| **工具系统** | 标准化 Tool API | 隐式工具 |
| **上下文管理** | 优先级裁剪 + 压缩 | 基础管理 |
| **错误处理** | 自动重试 + 修复 | 手动处理 |
| **测试** | 单元 + 集成 + 模拟 | 基础测试 |

### 功能对比

| 功能 | VSCode Copilot | Tableau Assistant |
|------|----------------|-------------------|
| **Agent Mode** | ✅ 完整实现 | ❌ 无 |
| **Tool Calling** | ✅ 显式工具系统 | ⚠️ 隐式工具 |
| **Multi-modal** | ✅ 支持图片 | ❌ 仅文本 |
| **MCP** | ✅ 支持 | ❌ 无 |
| **多模型适配** | ✅ Prompt Registry | ❌ 单一模板 |
| **错误修正** | ✅ 自动迭代 | ❌ 无 |
| **上下文压缩** | ✅ 智能裁剪 | ⚠️ 基础管理 |
| **并行执行** | ✅ 支持 | ⚠️ 部分支持 |



---

## 可借鉴的设计

### 1. 高优先级：立即可借鉴

#### 1.1 Prompt 组件化

**当前问题**：
```python
# Tableau Assistant - 字符串拼接
prompt = f"""
{role}
{task}
{metadata}
{constraints}
"""
```

**改进方案**：
```python
# 借鉴 Prompt-TSX 思想
class PromptComponent:
    def __init__(self, priority: int):
        self.priority = priority
    
    def render(self) -> str:
        pass

class UnderstandingPrompt:
    def render(self, token_budget: int):
        components = [
            SystemMessage(priority=100, content=self.role),
            UserMessage(priority=80, content=self.metadata),
            UserMessage(priority=50, content=self.question)
        ]
        
        # 按优先级裁剪
        return self._fit_to_budget(components, token_budget)
```

**收益**：
- 更好的 Token 管理
- 可复用组件
- 动态组合



#### 1.2 显式工具系统

**当前问题**：
```python
# Tableau Assistant - 隐式工具
metadata = metadata_manager.get_metadata()  # 隐式调用
result = execute_query(query)  # 隐式调用
```

**改进方案**：
```python
# 显式工具定义
class Tool:
    name: str
    description: str
    input_schema: Dict
    
    def execute(self, input: Dict) -> Any:
        pass

class GetMetadataTool(Tool):
    name = "get_metadata"
    description = "Get datasource metadata including fields, types, relationships"
    input_schema = {
        "type": "object",
        "properties": {
            "datasource_luid": {"type": "string"}
        }
    }
    
    def execute(self, input):
        return metadata_manager.get_metadata(input["datasource_luid"])

# LLM 可以决定调用哪个工具
tools = [GetMetadataTool(), SearchFieldsTool(), ExecuteQueryTool()]
```

**收益**：
- LLM 自主决定工具调用
- 更好的错误处理
- 可扩展性



#### 1.3 查询验证和错误修正

**当前问题**：
```python
# Tableau Assistant - 无验证
plan = query_planner_agent.execute(state)
result = execute_query(plan)  # 如果失败，直接返回错误
```

**改进方案**：
```python
# 借鉴 Agent Mode 的错误处理
def execute_with_retry(plan, max_retries=3):
    for attempt in range(max_retries):
        # 执行前验证
        errors = validate_plan(plan)
        if errors:
            plan = fix_plan_with_llm(plan, errors)
            continue
        
        # 执行查询
        try:
            result = execute_query(plan)
            return result
        except Exception as e:
            # 执行失败，LLM 修正
            plan = fix_plan_with_llm(plan, str(e))
    
    raise Exception("Max retries exceeded")
```

**收益**：
- 提高成功率（70% → 95%）
- 减少用户等待
- 更好的用户体验



#### 1.4 多模型 Prompt 适配

**当前问题**：
```python
# Tableau Assistant - 单一模板
UNDERSTANDING_PROMPT = """..."""  # 所有模型用同一个
```

**改进方案**：
```python
# Prompt Registry
class PromptRegistry:
    _prompts = {}
    
    @classmethod
    def register(cls, model_family: str, prompt_class):
        cls._prompts[model_family] = prompt_class
    
    @classmethod
    def get_prompt(cls, model_name: str):
        for family, prompt_class in cls._prompts.items():
            if model_name.startswith(family):
                return prompt_class
        return DefaultPrompt

# 注册不同模型的 Prompt
PromptRegistry.register("gpt-4", GPT4UnderstandingPrompt)
PromptRegistry.register("gpt-3.5", GPT35UnderstandingPrompt)
PromptRegistry.register("claude", ClaudeUnderstandingPrompt)

# 使用
prompt_class = PromptRegistry.get_prompt(model_name)
prompt = prompt_class(question=question, metadata=metadata)
```

**收益**：
- 针对不同模型优化
- 更好的输出质量
- 灵活的模型切换



### 2. 中优先级：需要重构

#### 2.1 分层架构

**改进方案**：

```
tableau_assistant/
├── util/           # 工具函数（无依赖）
│   ├── common/
│   └── types.py
├── platform/       # 平台服务
│   ├── config/
│   ├── telemetry/
│   └── llm/
├── src/            # 业务逻辑
│   ├── agents/
│   ├── workflows/
│   └── models/
└── tests/
```

**依赖规则**：
- `src` 可以导入 `platform` 和 `util`
- `platform` 可以导入 `util`
- `util` 不能导入其他层

#### 2.2 依赖注入系统

**改进方案**：

```python
# 服务接口
class IConfigService(Protocol):
    def get(self, key: str) -> Any: ...

class ILLMService(Protocol):
    def generate(self, prompt: str) -> str: ...

# 服务容器
class ServiceContainer:
    _services = {}
    
    @classmethod
    def register(cls, interface, implementation):
        cls._services[interface] = implementation
    
    @classmethod
    def get(cls, interface):
        return cls._services[interface]

# 使用
class UnderstandingAgent:
    def __init__(self):
        self.config = ServiceContainer.get(IConfigService)
        self.llm = ServiceContainer.get(ILLMService)
```



### 3. 低优先级：长期规划

#### 3.1 多模态支持

**应用场景**：
- 用户上传 Dashboard 截图："优化这个图表"
- 用户上传数据表截图："分析这个表格"
- 用户上传手绘草图："按这个样子做可视化"

**实现方案**：
```python
class MultimodalInput:
    text: str
    images: List[Image]
    
class UnderstandingAgent:
    def execute(self, input: MultimodalInput):
        # 处理文本 + 图片
        pass
```

#### 3.2 MCP 支持

**应用场景**：
- 第三方扩展提供工具
- 标准化接口
- 更好的生态

**实现方案**：
```python
# MCP Server
class TableauMCPServer:
    def list_tools(self):
        return [
            {"name": "get_metadata", "description": "..."},
            {"name": "execute_query", "description": "..."}
        ]
    
    def call_tool(self, name: str, args: Dict):
        if name == "get_metadata":
            return self.get_metadata(args)
```



---

## 总结

### VSCode Copilot 的核心优势

1. **Prompt-TSX 系统**：组件化、优先级管理、Token 优化
2. **Agent Mode**：自主编程、错误处理、迭代优化
3. **工具系统**：标准化、可扩展、LLM 自主决策
4. **多模型适配**：Prompt Registry、针对性优化
5. **严格分层**：清晰的架构、依赖管理
6. **完善测试**：单元 + 集成 + 模拟测试

### Tableau Assistant 可以借鉴的

**立即实施**（1-2 周）：
1. ✅ Prompt 组件化和优先级管理
2. ✅ 显式工具系统定义
3. ✅ 查询验证和错误修正循环
4. ✅ 多模型 Prompt 适配

**中期规划**（1-2 月）：
5. ⚠️ 分层架构重构
6. ⚠️ 依赖注入系统
7. ⚠️ 完善测试框架

**长期规划**（3-6 月）：
8. 🔮 多模态支持
9. 🔮 MCP 协议支持
10. 🔮 Agent Mode 实现

### 下一步行动

1. **创建详细的需求文档**（Requirements.md）
2. **设计技术方案**（Design.md）
3. **制定实施计划**（Tasks.md）
4. **逐步实施和验证**

