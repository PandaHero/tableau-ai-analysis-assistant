# VSCode Copilot 模块化深度分析

## 📚 目录

1. [模块 1：意图识别系统](#模块-1意图识别系统)
2. [模块 2：Tool Calling Loop（核心循环）](#模块-2tool-calling-loop核心循环)
3. [模块 3：TODO List 工具](#模块-3todo-list-工具)
4. [模块 4：Prompt 构建系统](#模块-4prompt-构建系统)
5. [模块 5：完整工作流程](#模块-5完整工作流程)

---

## 模块 1：意图识别系统

### 1.1 意图的本质

**关键发现**：VSCode Copilot 的"意图识别"**不是通过 LLM 动态识别的**！

而是通过以下三种方式：

#### 方式 1：斜杠命令（Slash Commands）

```typescript
// 用户输入
"/explain this code"

// VSCode 解析
const command = "/explain";  // 提取斜杠命令
const intent = Intent.Explain;  // 映射到预定义的意图枚举

// 调用对应的 Intent 类
const explainIntent = new ExplainIntent();
const invocation = await explainIntent.invoke(context);
```

**代码位置**：`src/extension/common/constants.ts`

```typescript
export const enum Intent {
    Explain = 'explain',
    Review = 'review',
    Tests = 'tests',
    Fix = 'fix',
    Edit = 'edit',
    Agent = 'editAgent',
    // ... 20+ 种预定义意图
}
```

#### 方式 2：上下文推断（Context Inference）

```typescript
// 根据当前上下文自动选择意图
function inferIntent(context: Context): Intent {
    // 规则 1：有选中代码 + 有编译错误 → Fix 意图
    if (context.hasSelection && context.hasDiagnostics) {
        return Intent.Fix;
    }
    
    // 规则 2：有选中代码 + 无错误 → Edit 意图
    if (context.hasSelection && !context.hasDiagnostics) {
        return Intent.Edit;
    }
    
    // 规则 3：在终端 → Terminal 意图
    if (context.location === ChatLocation.Terminal) {
        return Intent.Terminal;
    }
    
    // 规则 4：在编辑器 → Editor 意图
    if (context.location === ChatLocation.Editor) {
        return Intent.Editor;
    }
    
    // 默认：Workspace 意图
    return Intent.Workspace;
}
```

#### 方式 3：Agent 映射表（Agent to Intent Mapping）

```typescript
// 代码位置：src/extension/common/constants.ts
export const agentsToCommands: Partial<Record<Intent, Record<string, Intent>>> = {
    // Workspace Agent 的子命令
    [Intent.Workspace]: {
        'explain': Intent.Explain,
        'edit': Intent.Edit,
        'review': Intent.Review,
        'tests': Intent.Tests,
        'fix': Intent.Fix,
        'new': Intent.New,
    },
    
    // VSCode Agent 的子命令
    [Intent.VSCode]: {
        'search': Intent.Search,
    },
    
    // Terminal Agent 的子命令
    [Intent.Terminal]: {
        'explain': Intent.TerminalExplain
    },
    
    // Editor Agent 的子命令
    [Intent.Editor]: {
        'doc': Intent.Doc,
        'fix': Intent.Fix,
        'explain': Intent.Explain,
        'tests': Intent.Tests,
        'edit': Intent.Edit,
    }
};
```

### 1.2 意图接口（IIntent）

每个意图都是一个类，实现 `IIntent` 接口：

```typescript
export interface IIntent {
    // 意图的 ID
    readonly id: string;
    
    // 意图的描述
    readonly description: string;
    
    // 可以调用此意图的位置（panel 或 inline）
    readonly locations: ChatLocation[];
    
    // 调用此意图，返回一个 invocation 对象
    invoke(context: IIntentInvocationContext): Promise<IIntentInvocation>;
}
```

**示例：WorkspaceIntent**

```typescript
export class WorkspaceIntent implements IIntent {
    readonly id = 'workspace';
    readonly description = 'Ask a question about the files in your current workspace';
    readonly locations = [ChatLocation.Panel, ChatLocation.Other];
    
    async invoke(context: IIntentInvocationContext): Promise<IIntentInvocation> {
        // 创建一个 invocation 对象
        return new WorkspaceIntentInvocation(this, context.location, endpoint);
    }
}
```

### 1.3 对 Tableau Assistant 的启示

**你们不需要 LLM 来识别意图！**

可以使用规则匹配：

```python
class QueryIntent(str, Enum):
    SIMPLE_QUERY = "simple_query"
    COMPARISON = "comparison"
    TREND_ANALYSIS = "trend_analysis"
    RANKING = "ranking"
    EXPLORATION = "exploration"

class IntentClassifier:
    def classify(self, question: str, context: Dict) -> QueryIntent:
        # 规则 1：对比关键词
        if re.search(r"对比|比较|vs|同比|环比", question):
            return QueryIntent.COMPARISON
        
        # 规则 2：排名关键词
        if re.search(r"top\s*\d+|前\s*\d+|最高|最低|排名", question):
            return QueryIntent.RANKING
        
        # 规则 3：探索关键词
        if re.search(r"为什么|原因|如何|分析", question):
            return QueryIntent.EXPLORATION
        
        # 规则 4：趋势关键词
        if re.search(r"趋势|变化|增长|下降", question):
            return QueryIntent.TREND_ANALYSIS
        
        # 默认：简单查询
        return QueryIntent.SIMPLE_QUERY
```

**收益**：
- ✅ 快速、准确
- ✅ 不消耗 Token
- ✅ 可控、可调试
- ✅ 不依赖 LLM



---

## 模块 2：Tool Calling Loop（核心循环）

### 2.1 Tool Calling Loop 的本质

**这是 Agent Mode 的心脏！**

**代码位置**：`src/extension/intents/node/toolCallingLoop.ts`

### 2.2 核心数据结构

```typescript
// Tool Calling Loop 的配置
export interface IToolCallingLoopOptions {
    conversation: Conversation;           // 对话历史
    toolCallLimit: number;                // 最大工具调用次数（默认 200）
    onHitToolCallLimit?: ToolCallLimitBehavior;  // 达到限制时的行为
    streamParticipants?: ResponseStreamParticipant[];  // 流式输出参与者
    responseProcessor?: IResponseProcessor;  // 响应处理器
    request: ChatRequest;                 // 当前请求
}

// 单次工具调用的结果
interface IToolCallSingleResult {
    response: ChatResponse;               // LLM 响应
    round: IToolCallRound;                // 本轮工具调用信息
    lastRequestMessages: Raw.ChatMessage[];  // 发送给 LLM 的消息
    hadIgnoredFiles: boolean;             // 是否有被忽略的文件
    chatResult?: ChatResult;              // 聊天结果
}

// 工具调用轮次
interface IToolCallRound {
    id: string;                           // 轮次 ID
    toolCalls: IToolCall[];               // 本轮调用的工具列表
    thinkingData?: ThinkingDataItem[];    // 思考过程数据
}

// 单个工具调用
interface IToolCall {
    id: string;                           // 工具调用 ID
    name: string;                         // 工具名称
    arguments: string;                    // 工具参数（JSON 字符串）
}
```

### 2.3 Tool Calling Loop 的完整流程

```typescript
export abstract class ToolCallingLoop extends Disposable {
    // 核心方法：运行循环
    public async run(
        outputStream: ChatResponseStream,
        token: CancellationToken
    ): Promise<IToolCallLoopResult> {
        
        let i = 0;  // 迭代计数器
        let lastResult: IToolCallSingleResult | undefined;
        
        // 主循环
        while (true) {
            // 1. 检查是否达到工具调用限制
            if (lastResult && i++ >= this.options.toolCallLimit) {
                lastResult = this.hitToolCallLimit(outputStream, lastResult);
                break;
            }
            
            try {
                // 2. 执行一次工具调用循环
                const result = await this.runOne(outputStream, i, token);
                
                // 3. 保存结果
                lastResult = result;
                this.toolCallRounds.push(result.round);
                
                // 4. 检查是否需要继续
                // 如果没有工具调用，或者响应失败，则退出循环
                if (!result.round.toolCalls.length || 
                    result.response.type !== ChatFetchResponseType.Success) {
                    break;
                }
                
            } catch (e) {
                // 5. 处理取消错误
                if (isCancellationError(e) && lastResult) {
                    break;
                }
                throw e;
            }
        }
        
        // 6. 返回最终结果
        return {
            ...lastResult,
            toolCallRounds: this.toolCallRounds,
            toolCallResults: this.toolCallResults
        };
    }
}
```

### 2.4 单次循环（runOne）的详细流程

```typescript
public async runOne(
    outputStream: ChatResponseStream,
    iterationNumber: number,
    token: CancellationToken
): Promise<IToolCallSingleResult> {
    
    // ===== 步骤 1：获取可用工具 =====
    let availableTools = await this.getAvailableTools(outputStream, token);
    
    // ===== 步骤 2：创建 Prompt 上下文 =====
    const context = this.createPromptContext(availableTools, outputStream);
    
    // context 包含：
    // - query: 用户问题
    // - history: 对话历史
    // - toolCallResults: 之前的工具调用结果
    // - toolCallRounds: 之前的工具调用轮次
    // - availableTools: 可用工具列表
    
    // ===== 步骤 3：构建 Prompt =====
    const buildPromptResult = await this.buildPrompt(context, outputStream, token);
    
    // buildPromptResult 包含：
    // - messages: 发送给 LLM 的消息列表
    // - references: 引用的文件/代码
    // - tokenCount: Token 数量
    
    // ===== 步骤 4：调用 LLM =====
    const response = await this.fetch({
        messages: buildPromptResult.messages,
        finishedCb: (response) => { /* 完成回调 */ },
        requestOptions: { /* 请求选项 */ },
        userInitiatedRequest: true
    }, token);
    
    // ===== 步骤 5：处理 LLM 响应 =====
    const toolCalls: IToolCall[] = [];
    
    // 从响应中提取工具调用
    for await (const part of response.stream) {
        if (part.type === 'tool_call') {
            toolCalls.push({
                id: part.toolCallId,
                name: part.toolName,
                arguments: part.arguments
            });
        }
    }
    
    // ===== 步骤 6：执行工具调用 =====
    for (const toolCall of toolCalls) {
        try {
            // 调用工具
            const toolResult = await this.invokeTool(
                toolCall.name,
                JSON.parse(toolCall.arguments),
                token
            );
            
            // 保存工具结果
            this.toolCallResults[toolCall.id] = toolResult;
            
            // 报告进度
            outputStream.progress(`✓ ${toolCall.name} completed`);
            
        } catch (error) {
            // 工具调用失败
            this.toolCallResults[toolCall.id] = {
                error: error.message
            };
            
            outputStream.progress(`✗ ${toolCall.name} failed: ${error.message}`);
        }
    }
    
    // ===== 步骤 7：创建本轮结果 =====
    const round: IToolCallRound = {
        id: generateUuid(),
        toolCalls: toolCalls,
        thinkingData: [] // 思考过程数据
    };
    
    // ===== 步骤 8：返回结果 =====
    return {
        response: response,
        round: round,
        lastRequestMessages: buildPromptResult.messages,
        hadIgnoredFiles: buildPromptResult.hasIgnoredFiles,
        chatResult: { /* 聊天结果 */ }
    };
}
```

### 2.5 关键点解析

#### 关键点 1：循环终止条件

```typescript
// 循环会在以下情况终止：

// 1. 达到工具调用限制（默认 200 次）
if (i >= this.options.toolCallLimit) {
    break;
}

// 2. LLM 不再调用工具（任务完成）
if (!result.round.toolCalls.length) {
    break;
}

// 3. LLM 响应失败
if (result.response.type !== ChatFetchResponseType.Success) {
    break;
}

// 4. 用户取消
if (token.isCancellationRequested) {
    break;
}
```

#### 关键点 2：工具调用限制处理

```typescript
private hitToolCallLimit(
    stream: ChatResponseStream,
    lastResult: IToolCallSingleResult
) {
    // 如果配置为确认模式
    if (this.options.onHitToolCallLimit === ToolCallLimitBehavior.Confirm) {
        // 询问用户是否继续
        stream.confirmation(
            'Continue to iterate?',
            'Copilot has been working on this problem for a while...',
            { copilotRequestedRoundLimit: Math.round(this.options.toolCallLimit * 3 / 2) },
            ['Continue', 'Cancel']
        );
    }
    
    // 标记达到限制
    lastResult.chatResult = {
        ...lastResult.chatResult,
        metadata: {
            maxToolCallsExceeded: true
        }
    };
    
    return lastResult;
}
```

#### 关键点 3：Prompt 上下文构建

```typescript
protected createPromptContext(
    availableTools: LanguageModelToolInformation[],
    outputStream: ChatResponseStream
): IBuildPromptContext {
    
    return {
        // 当前请求
        requestId: this.turn.id,
        query: this.turn.request.message,
        
        // 对话历史（排除错误的轮次）
        history: this.options.conversation.turns
            .slice(0, -1)
            .filter(turn => turn.responseStatus !== TurnStatus.PromptFiltered),
        
        // 工具调用历史
        toolCallResults: this.toolCallResults,  // 之前的工具调用结果
        toolCallRounds: this.toolCallRounds,    // 之前的工具调用轮次
        
        // 可用工具
        tools: {
            toolReferences: request.toolReferences,
            toolInvocationToken: request.toolInvocationToken,
            availableTools: availableTools
        },
        
        // 其他上下文
        editedFileEvents: this.options.request.editedFileEvents,
        request: this.options.request,
        stream: outputStream,
        conversation: this.options.conversation,
    };
}
```



### 2.6 完整示例：一次 Agent Mode 执行

让我用一个具体例子来说明整个流程：

```
用户请求："Add error handling to the authentication module"

┌─────────────────────────────────────────────────────────────┐
│ 第 1 轮（i=0）                                               │
├─────────────────────────────────────────────────────────────┤
│ 1. 获取可用工具：                                            │
│    - read_file                                              │
│    - replace_string_in_file                                 │
│    - run_in_terminal                                        │
│    - manage_todo_list                                       │
│                                                             │
│ 2. 构建 Prompt：                                            │
│    System: You are a coding assistant...                   │
│    User: Add error handling to the authentication module   │
│    Available tools: [read_file, replace_string_in_file...] │
│                                                             │
│ 3. LLM 响应：                                               │
│    "I'll help you add error handling. Let me first read    │
│     the authentication module."                             │
│    Tool calls:                                              │
│      - read_file(path="src/auth.ts")                       │
│                                                             │
│ 4. 执行工具：                                               │
│    ✓ read_file completed                                   │
│    Result: [auth.ts 的内容]                                │
│                                                             │
│ 5. 保存结果到 toolCallResults                              │
│                                                             │
│ 6. 继续循环（因为有工具调用）                               │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 第 2 轮（i=1）                                               │
├─────────────────────────────────────────────────────────────┤
│ 1. 构建 Prompt（包含上一轮的工具调用结果）：                 │
│    System: You are a coding assistant...                   │
│    User: Add error handling to the authentication module   │
│    Assistant: [Tool call: read_file]                       │
│    Tool: [auth.ts 的内容]                                  │
│    Available tools: [...]                                  │
│                                                             │
│ 2. LLM 响应：                                               │
│    "I can see the authentication module. I'll add          │
│     try-catch blocks around the database operations."      │
│    Tool calls:                                              │
│      - replace_string_in_file(                             │
│          path="src/auth.ts",                               │
│          old_str="const user = await db.findUser(...)",    │
│          new_str="try {\n  const user = await db.findUser(...)\n} catch (e) {...}" │
│        )                                                    │
│                                                             │
│ 3. 执行工具：                                               │
│    ✓ replace_string_in_file completed                      │
│                                                             │
│ 4. 继续循环                                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 第 3 轮（i=2）                                               │
├─────────────────────────────────────────────────────────────┤
│ 1. 构建 Prompt（包含前两轮的工具调用结果）                   │
│                                                             │
│ 2. LLM 响应：                                               │
│    "I've added error handling. Let me run the tests to     │
│     verify everything works."                               │
│    Tool calls:                                              │
│      - run_in_terminal(command="npm test")                 │
│                                                             │
│ 3. 执行工具：                                               │
│    ✓ run_in_terminal completed                             │
│    Result: "All tests passed"                              │
│                                                             │
│ 4. 继续循环                                                 │
└─────────────────────────────────────────────────────────────┘

┌─────────────────────────────────────────────────────────────┐
│ 第 4 轮（i=3）                                               │
├─────────────────────────────────────────────────────────────┤
│ 1. 构建 Prompt                                              │
│                                                             │
│ 2. LLM 响应：                                               │
│    "I've successfully added error handling to the          │
│     authentication module. All tests are passing."         │
│    Tool calls: []  ← 没有工具调用                          │
│                                                             │
│ 3. 循环终止（因为没有工具调用）                             │
└─────────────────────────────────────────────────────────────┘

最终结果：
- 总共 4 轮
- 调用了 3 个工具
- 任务完成
```

### 2.7 对 Tableau Assistant 的启示

**Tool Calling Loop 的核心思想**：

1. **循环执行**：不断调用 LLM → 执行工具 → 再调用 LLM
2. **上下文累积**：每一轮都包含之前所有轮次的工具调用结果
3. **自动终止**：LLM 不再调用工具时自动停止
4. **错误处理**：工具调用失败时，LLM 可以看到错误信息并尝试修复

**你们可以这样实现**：

```python
class QueryExecutionLoop:
    def __init__(self, max_iterations=5):
        self.max_iterations = max_iterations
        self.tool_call_history = []
        self.tool_results = {}
    
    async def run(self, question: str) -> QueryResult:
        """运行查询执行循环"""
        
        for i in range(self.max_iterations):
            # 1. 构建 Prompt（包含历史）
            prompt = self._build_prompt(
                question=question,
                tool_call_history=self.tool_call_history,
                tool_results=self.tool_results
            )
            
            # 2. 调用 LLM（带工具）
            response = await llm.generate_with_tools(
                prompt=prompt,
                tools=[
                    UnderstandingTool(),
                    QueryPlannerTool(),
                    ExecuteQueryTool(),
                    ValidateQueryTool()
                ]
            )
            
            # 3. 提取工具调用
            tool_calls = response.tool_calls
            
            # 4. 如果没有工具调用，任务完成
            if not tool_calls:
                return self._create_result(response)
            
            # 5. 执行工具
            for tool_call in tool_calls:
                try:
                    result = await self._execute_tool(tool_call)
                    self.tool_results[tool_call.id] = result
                    print(f"✓ {tool_call.name} completed")
                except Exception as e:
                    self.tool_results[tool_call.id] = {"error": str(e)}
                    print(f"✗ {tool_call.name} failed: {e}")
            
            # 6. 保存本轮历史
            self.tool_call_history.append({
                "iteration": i,
                "tool_calls": tool_calls,
                "llm_response": response.text
            })
        
        # 达到最大迭代次数
        raise Exception("Max iterations exceeded")
```

**关键优势**：
- ✅ LLM 自己决定调用哪些工具
- ✅ LLM 可以看到工具执行结果
- ✅ LLM 可以根据结果调整策略
- ✅ 自动错误处理和重试

