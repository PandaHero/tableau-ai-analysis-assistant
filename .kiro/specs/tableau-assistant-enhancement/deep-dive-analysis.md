# VSCode Copilot 深度分析 - 回答你的 10 个问题

## 1. 理解意图是怎么做的？

### VSCode Copilot 的意图理解

**流程**：

```
用户输入
    ↓
Intent Classification（意图分类）
    ↓
Context Gathering（上下文收集）
    ↓
Prompt Construction（Prompt 构建）
    ↓
LLM 调用
    ↓
结构化输出（JSON Schema 验证）
```

**关键代码**（简化版）：

```typescript
// 1. 意图分类
class IntentClassifier {
    async classify(userMessage: string): Promise<Intent> {
        // 使用 LLM 分类意图
        const prompt = `
        User message: ${userMessage}
        
        Classify the intent:
        - code_edit: User wants to edit code
        - code_explain: User wants explanation
        - code_generate: User wants to generate new code
        - question: General question
        `;
        
        const intent = await llm.generate(prompt);
        return intent;
    }
}

// 2. 上下文收集
class ContextGatherer {
    async gather(intent: Intent): Promise<Context> {
        const context = {};
        
        // 根据意图收集不同的上下文
        if (intent === 'code_edit') {
            context.currentFile = await readCurrentFile();
            context.selection = await getSelection();
            context.diagnostics = await getDiagnostics();
        }
        
        return context;
    }
}

// 3. Prompt 构建
class PromptBuilder {
    build(intent: Intent, context: Context): Prompt {
        // 使用 Prompt-TSX 组件化构建
        return <AgentPrompt>
            <SystemMessage priority={100}>
                You are a coding assistant.
            </SystemMessage>
            <UserMessage priority={80}>
                <CurrentFile content={context.currentFile} />
                <Diagnostics errors={context.diagnostics} />
            </UserMessage>
            <UserMessage priority={50}>
                {userMessage}
            </UserMessage>
        </AgentPrompt>;
    }
}
```



### Tableau Assistant 的意图理解

**你们的流程**：

```python
# Understanding Agent
def understanding_agent_node(state, runtime):
    # 1. 获取问题
    question = state.get("boosted_question") or state.get("question")
    
    # 2. 获取元数据
    metadata = metadata_manager.get_metadata()
    
    # 3. 构建 Prompt
    prompt = UNDERSTANDING_PROMPT.format_messages(
        question=question,
        metadata=metadata,
        max_date=metadata.max_date
    )
    
    # 4. LLM 调用
    result = llm.generate(prompt)
    
    # 5. Pydantic 验证
    understanding = QuestionUnderstanding(**result)
    
    return {"understanding": understanding}
```

**对比**：

| 维度 | VSCode Copilot | Tableau Assistant |
|------|----------------|-------------------|
| **意图分类** | 显式分类（code_edit/explain/generate） | 隐式（通过 Prompt 引导） |
| **上下文收集** | 根据意图动态收集 | 固定收集元数据 |
| **Prompt 构建** | 组件化（Prompt-TSX） | 模板化（字符串格式化） |
| **输出验证** | JSON Schema + 运行时验证 | Pydantic 验证 ✅ |

**你们做得好的地方**：
- ✅ 使用 Pydantic 进行输出验证
- ✅ 结构化的数据模型（QuestionUnderstanding）
- ✅ 清晰的字段定义和描述

**可以改进的地方**：
- ⚠️ 元数据可以根据问题动态过滤（减少 Token）
- ⚠️ Prompt 可以组件化（更好的维护性）



---

## 2. 如何生成的计划？

### VSCode Copilot 的计划生成

**Agent Mode 的计划生成流程**：

```typescript
// 1. 理解任务
const understanding = await understandTask(userRequest);

// 2. 生成 TODO List
const todoList = await generateTodoList(understanding);

// 示例 TODO List
{
    "tasks": [
        {
            "id": 1,
            "description": "Read the authentication module",
            "status": "pending",
            "tool": "read_file"
        },
        {
            "id": 2,
            "description": "Add error handling to login function",
            "status": "pending",
            "tool": "replace_string_in_file",
            "depends_on": [1]
        },
        {
            "id": 3,
            "description": "Run tests",
            "status": "pending",
            "tool": "run_in_terminal",
            "depends_on": [2]
        }
    ]
}

// 3. 执行计划
for (const task of todoList.tasks) {
    // 检查依赖
    if (task.depends_on) {
        await waitForDependencies(task.depends_on);
    }
    
    // 执行任务
    const result = await executeTool(task.tool, task.params);
    
    // 更新状态
    task.status = "completed";
    
    // 报告进度
    progress.report(`✓ ${task.description}`);
}
```

**关键特性**：
1. **依赖管理**：任务之间有依赖关系
2. **动态调整**：执行过程中可以添加/修改任务
3. **进度追踪**：实时更新 TODO List
4. **错误处理**：失败时自动添加修复任务



### Tableau Assistant 的计划生成

**你们的流程**：

```python
# Query Planner Agent
def query_planner_agent_node(state, runtime):
    # 1. 获取理解结果
    understanding = state["understanding"]
    
    # 2. 获取元数据和维度层级
    metadata = metadata_manager.get_metadata()
    dimension_hierarchy = store_manager.get_dimension_hierarchy()
    
    # 3. 构建 Prompt
    prompt = PLANNING_PROMPT.format_messages(
        understanding=understanding,
        metadata=metadata,
        dimension_hierarchy=dimension_hierarchy
    )
    
    # 4. LLM 生成查询计划
    plan = llm.generate(prompt)
    
    # 5. 验证和返回
    query_plan = QueryPlan(**plan)
    return {"query_plan": query_plan}
```

**你们的查询计划结构**：

```python
class QueryPlan(BaseModel):
    sub_queries: List[SubQuery]  # 子查询列表
    post_processing: Optional[PostProcessing]  # 后处理
    
class SubQuery(BaseModel):
    dimensions: List[str]
    measures: List[str]
    filters: List[Filter]
    sorts: List[Sort]
    limit: Optional[int]
```

**对比**：

| 维度 | VSCode Copilot | Tableau Assistant |
|------|----------------|-------------------|
| **计划类型** | 任务列表（TODO List） | 查询计划（Query Plan） |
| **依赖管理** | 显式依赖（depends_on） | 隐式依赖（执行顺序） |
| **动态调整** | 支持（可添加/修改任务） | 不支持（一次性生成） |
| **进度追踪** | 实时更新 TODO | 无进度追踪 |
| **错误处理** | 自动添加修复任务 | 无自动修复 |

**你们做得好的地方**：
- ✅ 清晰的查询计划结构
- ✅ 支持子查询和后处理
- ✅ 使用 Pydantic 验证

**可以改进的地方**：
- ⚠️ 添加依赖管理（sub_queries 之间的依赖）
- ⚠️ 添加进度追踪（让用户知道执行到哪一步）
- ⚠️ 支持动态调整（执行失败时重新规划）



---

## 3. 调用工具是 LLM 自己调用的？还是怎么调用呢？

### VSCode Copilot 的工具调用机制

**完整流程**：

```typescript
// 1. 工具定义（package.json）
{
  "contributes": {
    "languageModelTools": [
      {
        "name": "copilot_readFile",
        "modelDescription": "Read the contents of a file at the specified path...",
        "inputSchema": {
          "type": "object",
          "properties": {
            "uri": { "type": "string", "description": "Absolute file path" }
          },
          "required": ["uri"]
        }
      }
    ]
  }
}

// 2. 工具实现
class ReadFileTool implements vscode.LanguageModelTool {
    async invoke(options, token) {
        const { uri } = options.input;
        const content = await vscode.workspace.fs.readFile(uri);
        return { content: [new vscode.LanguageModelTextPart(content.toString())] };
    }
}

// 3. LLM 调用工具（OpenAI Function Calling）
const response = await openai.chat.completions.create({
    model: "gpt-4",
    messages: [
        { role: "system", content: "You are a coding assistant." },
        { role: "user", content: "Read the file auth.ts" }
    ],
    tools: [
        {
            type: "function",
            function: {
                name: "copilot_readFile",
                description: "Read the contents of a file...",
                parameters: {
                    type: "object",
                    properties: {
                        uri: { type: "string", description: "Absolute file path" }
                    },
                    required: ["uri"]
                }
            }
        }
    ]
});

// 4. LLM 返回工具调用请求
{
    "role": "assistant",
    "content": null,
    "tool_calls": [
        {
            "id": "call_123",
            "type": "function",
            "function": {
                "name": "copilot_readFile",
                "arguments": "{\"uri\": \"file:///path/to/auth.ts\"}"
            }
        }
    ]
}

// 5. 执行工具
const toolResult = await readFileTool.invoke({
    input: { uri: "file:///path/to/auth.ts" }
});

// 6. 将结果返回给 LLM
const nextResponse = await openai.chat.completions.create({
    model: "gpt-4",
    messages: [
        ...previousMessages,
        {
            role: "tool",
            tool_call_id: "call_123",
            content: toolResult.content
        }
    ]
});
```

**关键点**：
1. **LLM 自己决定**：LLM 根据工具描述决定调用哪个工具
2. **标准协议**：使用 OpenAI Function Calling 协议
3. **循环调用**：LLM 可以连续调用多个工具
4. **结果反馈**：工具结果返回给 LLM，LLM 继续处理



### Tableau Assistant 的工具调用

**你们当前的方式**：

```python
# 隐式工具调用（代码硬编码）
def understanding_agent_node(state, runtime):
    # 工具1：获取元数据（隐式）
    metadata = metadata_manager.get_metadata()
    
    # 工具2：LLM 生成理解结果（隐式）
    understanding = llm.generate(prompt)
    
    return {"understanding": understanding}

def query_planner_agent_node(state, runtime):
    # 工具1：获取元数据（隐式）
    metadata = metadata_manager.get_metadata()
    
    # 工具2：获取维度层级（隐式）
    dimension_hierarchy = store_manager.get_dimension_hierarchy()
    
    # 工具3：LLM 生成查询计划（隐式）
    plan = llm.generate(prompt)
    
    return {"query_plan": plan}
```

**问题**：
- ❌ LLM 不知道有哪些工具可用
- ❌ LLM 不能自己决定调用哪个工具
- ❌ 工具调用顺序是硬编码的
- ❌ 无法动态调整工具调用策略

**改进方案：显式工具系统**

```python
# 1. 工具定义
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

class SearchFieldsTool(Tool):
    name = "search_fields"
    description = "Search for fields by name or description using semantic search"
    input_schema = {
        "type": "object",
        "properties": {
            "query": {"type": "string"},
            "top_k": {"type": "integer", "default": 10}
        }
    }
    
    def execute(self, input):
        return semantic_search(input["query"], top_k=input["top_k"])

# 2. 注册工具
tools = [GetMetadataTool(), SearchFieldsTool(), ExecuteQueryTool()]

# 3. LLM 调用工具
response = llm.generate(
    prompt=prompt,
    tools=tools  # LLM 可以看到所有可用工具
)

# 4. 执行工具
if response.tool_calls:
    for tool_call in response.tool_calls:
        tool = find_tool(tool_call.name)
        result = tool.execute(tool_call.arguments)
        # 将结果返回给 LLM
```

**收益**：
- ✅ LLM 自主决定工具调用
- ✅ 更灵活的执行策略
- ✅ 更好的错误处理
- ✅ 可扩展性



---

## 4. 任务管理工具是如何做的呢？

### VSCode Copilot 的 TODO List 管理

**工具定义**：

```typescript
// package.json
{
  "name": "copilot_manageTodoList",
  "modelDescription": "Create, update, or mark TODO items as complete. Use this to track progress on multi-step tasks.",
  "inputSchema": {
    "type": "object",
    "properties": {
      "action": {
        "type": "string",
        "enum": ["create", "update", "complete", "list"],
        "description": "Action to perform on TODO list"
      },
      "task_id": {
        "type": "integer",
        "description": "Task ID (for update/complete actions)"
      },
      "description": {
        "type": "string",
        "description": "Task description (for create/update actions)"
      }
    }
  }
}

// 工具实现
class ManageTodoListTool implements vscode.LanguageModelTool {
    private todoList: Map<number, TodoItem> = new Map();
    
    async invoke(options) {
        const { action, task_id, description } = options.input;
        
        switch (action) {
            case "create":
                const id = this.todoList.size + 1;
                this.todoList.set(id, {
                    id,
                    description,
                    status: "pending",
                    created_at: new Date()
                });
                return { message: `Created task ${id}: ${description}` };
            
            case "update":
                const task = this.todoList.get(task_id);
                task.description = description;
                return { message: `Updated task ${task_id}` };
            
            case "complete":
                const completedTask = this.todoList.get(task_id);
                completedTask.status = "completed";
                completedTask.completed_at = new Date();
                return { message: `Completed task ${task_id}` };
            
            case "list":
                return { tasks: Array.from(this.todoList.values()) };
        }
    }
}
```

**使用示例**：

```
User: Add error handling to the authentication module

LLM: I'll break this down into tasks:

[Tool Call: manage_todo_list]
{
  "action": "create",
  "description": "Read authentication module to understand current implementation"
}

[Tool Call: manage_todo_list]
{
  "action": "create",
  "description": "Identify error-prone areas in authentication flow"
}

[Tool Call: manage_todo_list]
{
  "action": "create",
  "description": "Add try-catch blocks and error handling"
}

[Tool Call: manage_todo_list]
{
  "action": "create",
  "description": "Add error logging"
}

[Tool Call: manage_todo_list]
{
  "action": "create",
  "description": "Run tests to verify error handling"
}

Now I'll start executing these tasks...

[Tool Call: read_file]
{ "uri": "file:///auth.ts" }

[Tool Call: manage_todo_list]
{
  "action": "complete",
  "task_id": 1
}

✓ Task 1 completed: Read authentication module

[继续执行其他任务...]
```

**关键特性**：
1. **动态创建**：LLM 根据任务复杂度动态创建 TODO
2. **实时更新**：执行过程中实时更新状态
3. **进度可见**：用户可以看到当前进度
4. **灵活调整**：可以添加/修改/删除任务



### Tableau Assistant 可以借鉴的任务管理

**你们当前的状态**：
- ❌ 无任务管理
- ❌ 无进度追踪
- ❌ 用户不知道执行到哪一步

**改进方案**：

```python
# 1. 定义任务管理工具
class ManageTasksTool(Tool):
    name = "manage_tasks"
    description = "Create, update, or complete tasks for complex queries"
    
    def __init__(self):
        self.tasks = {}
    
    def execute(self, input):
        action = input["action"]
        
        if action == "create":
            task_id = len(self.tasks) + 1
            self.tasks[task_id] = {
                "id": task_id,
                "description": input["description"],
                "status": "pending"
            }
            return {"task_id": task_id}
        
        elif action == "complete":
            task_id = input["task_id"]
            self.tasks[task_id]["status"] = "completed"
            return {"message": f"Task {task_id} completed"}
        
        elif action == "list":
            return {"tasks": list(self.tasks.values())}

# 2. 在 Agent 中使用
def query_planner_agent_node(state, runtime):
    understanding = state["understanding"]
    
    # 如果是复杂问题，创建任务列表
    if understanding.complexity == "Complex":
        # LLM 创建任务
        tasks = llm.generate_with_tools(
            prompt="Create a task list for this query",
            tools=[ManageTasksTool()]
        )
        
        # 保存任务列表
        state["tasks"] = tasks
    
    # 继续执行...

# 3. 执行过程中更新任务
def execute_query_node(state, runtime):
    tasks = state.get("tasks", [])
    
    for task in tasks:
        # 执行任务
        result = execute_task(task)
        
        # 更新状态
        manage_tasks_tool.execute({
            "action": "complete",
            "task_id": task["id"]
        })
        
        # 报告进度
        progress.report(f"✓ {task['description']}")
```

**收益**：
- ✅ 用户可以看到执行进度
- ✅ 复杂查询更容易理解
- ✅ 更好的用户体验



---

## 5. LangChain 的上下文管理 vs VSCode Copilot

### LangChain 1.0+ 的上下文管理能力

**LangChain 提供的功能**：

```python
from langchain.memory import ConversationBufferMemory, ConversationSummaryMemory
from langchain.retrievers import ContextualCompressionRetriever
from langchain.retrievers.document_compressors import LLMChainExtractor

# 1. 对话历史管理
memory = ConversationBufferMemory(
    memory_key="chat_history",
    return_messages=True,
    max_token_limit=2000  # 限制 Token 数量
)

# 2. 对话摘要
summary_memory = ConversationSummaryMemory(
    llm=llm,
    memory_key="chat_history",
    return_messages=True
)

# 3. 上下文压缩
compressor = LLMChainExtractor.from_llm(llm)
compression_retriever = ContextualCompressionRetriever(
    base_compressor=compressor,
    base_retriever=retriever
)

# 4. 使用示例
from langchain.chains import ConversationChain

chain = ConversationChain(
    llm=llm,
    memory=summary_memory,  # 自动压缩历史
    verbose=True
)

# 对话1
response1 = chain.run("What is the sales in 2016?")

# 对话2（历史会被自动管理）
response2 = chain.run("How about 2017?")

# 对话3（早期对话会被摘要）
response3 = chain.run("Compare them")
```

**LangChain 的能力**：
- ✅ 对话历史管理（ConversationBufferMemory）
- ✅ 自动摘要（ConversationSummaryMemory）
- ✅ 上下文压缩（ContextualCompressionRetriever）
- ✅ Token 限制（max_token_limit）
- ⚠️ 但没有优先级管理



### VSCode Copilot 的上下文管理

**Prompt-TSX 的优先级管理**：

```tsx
// 每个组件有优先级
<SystemMessage priority={100}>  {/* 最高优先级 */}
    <SafetyRules />
</SystemMessage>

<UserMessage priority={80}>  {/* 高优先级 */}
    <Metadata />
</UserMessage>

<UserMessage priority={50}>  {/* 中优先级 */}
    <ConversationHistory />
</UserMessage>

<UserMessage priority={20}>  {/* 低优先级 */}
    <AdditionalContext />
</UserMessage>

// 渲染时自动裁剪
const renderer = new PromptRenderer(prompt, tokenBudget=4000);
const messages = renderer.render();  // 自动裁剪低优先级内容
```

**对比**：

| 功能 | LangChain | VSCode Copilot |
|------|-----------|----------------|
| **对话历史管理** | ✅ ConversationBufferMemory | ✅ 手动管理 |
| **自动摘要** | ✅ ConversationSummaryMemory | ✅ 手动调用 LLM |
| **上下文压缩** | ✅ ContextualCompressionRetriever | ✅ 手动实现 |
| **Token 限制** | ✅ max_token_limit | ✅ tokenBudget |
| **优先级管理** | ❌ 无 | ✅ priority-based pruning |
| **组件化** | ❌ 无 | ✅ Prompt-TSX |

**结论**：
- **LangChain 可以做到基本的上下文管理**（历史、摘要、压缩）
- **但 LangChain 没有优先级管理**，这是 VSCode Copilot 的核心优势
- **你们可以结合两者**：
  - 使用 LangChain 的 Memory 管理对话历史
  - 实现自己的优先级裁剪系统



### 你们可以这样实现

```python
from langchain.memory import ConversationSummaryMemory

# 1. 使用 LangChain 管理对话历史
class ContextManager:
    def __init__(self, llm):
        self.memory = ConversationSummaryMemory(
            llm=llm,
            max_token_limit=2000
        )
        
    def add_message(self, role, content):
        self.memory.save_context(
            {"input": content if role == "user" else ""},
            {"output": content if role == "assistant" else ""}
        )
    
    def get_history(self):
        return self.memory.load_memory_variables({})

# 2. 实现优先级裁剪
class PriorityPromptBuilder:
    def __init__(self, token_budget=4000):
        self.token_budget = token_budget
        self.components = []
    
    def add_component(self, content, priority):
        self.components.append({
            "content": content,
            "priority": priority,
            "tokens": count_tokens(content)
        })
    
    def build(self):
        # 按优先级排序
        sorted_components = sorted(
            self.components,
            key=lambda x: x["priority"],
            reverse=True
        )
        
        # 裁剪到 Token 预算
        total_tokens = 0
        selected = []
        
        for comp in sorted_components:
            if total_tokens + comp["tokens"] <= self.token_budget:
                selected.append(comp["content"])
                total_tokens += comp["tokens"]
            else:
                break
        
        return "\n\n".join(selected)

# 3. 使用
context_manager = ContextManager(llm)
prompt_builder = PriorityPromptBuilder(token_budget=4000)

# 添加组件（按优先级）
prompt_builder.add_component(
    content="You are a helpful assistant.",
    priority=100  # 最高优先级
)

prompt_builder.add_component(
    content=f"Metadata: {metadata}",
    priority=80  # 高优先级
)

prompt_builder.add_component(
    content=context_manager.get_history(),
    priority=50  # 中优先级
)

prompt_builder.add_component(
    content=f"Question: {question}",
    priority=90  # 高优先级
)

# 构建最终 Prompt
final_prompt = prompt_builder.build()
```

**收益**：
- ✅ 结合 LangChain 的对话管理
- ✅ 实现优先级裁剪
- ✅ 更好的 Token 控制



---

## 6. 元数据过滤 - 深入分析

### 为什么需要元数据过滤？

**问题场景**：

```python
# 你们当前的做法
metadata = get_all_metadata()  # 100+ 字段
prompt = f"""
Metadata: {metadata}  # 可能有 5000+ tokens

Question: {question}
"""

# 问题：
# 1. Token 浪费：大部分字段与问题无关
# 2. 干扰 LLM：太多无关信息影响理解
# 3. 成本高：更多 Token = 更高成本
# 4. 速度慢：更多 Token = 更慢响应
```

**示例**：

```
用户问题："2016年各地区的销售额"

相关字段（需要）：
- sales_amount (销售额)
- region_name (地区)
- order_date (订单日期)

无关字段（不需要）：
- customer_name (客户名称)
- product_category (产品类别)
- shipping_address (配送地址)
- ... 其他 90+ 字段
```



### VSCode Copilot 的元数据过滤策略

**1. 语义搜索（Semantic Search）**

```typescript
// 使用 Embeddings 进行语义搜索
class SemanticFieldSearch {
    private embeddings: Map<string, number[]>;
    
    async search(query: string, topK: number = 10): Promise<Field[]> {
        // 1. 生成查询的 Embedding
        const queryEmbedding = await generateEmbedding(query);
        
        // 2. 计算与所有字段的相似度
        const similarities = [];
        for (const [fieldName, fieldEmbedding] of this.embeddings) {
            const similarity = cosineSimilarity(queryEmbedding, fieldEmbedding);
            similarities.push({ fieldName, similarity });
        }
        
        // 3. 返回 Top K 相似字段
        return similarities
            .sort((a, b) => b.similarity - a.similarity)
            .slice(0, topK)
            .map(s => this.fields.get(s.fieldName));
    }
}

// 使用
const searcher = new SemanticFieldSearch(allFields);
const relevantFields = await searcher.search("2016年各地区的销售额", topK=10);

// 结果：
// 1. sales_amount (0.95)
// 2. region_name (0.92)
// 3. order_date (0.88)
// 4. sales_quantity (0.75)
// 5. region_code (0.72)
// ...
```

**2. 关键词匹配（Keyword Matching）**

```typescript
class KeywordFieldSearch {
    search(query: string, topK: number = 10): Field[] {
        const keywords = extractKeywords(query);
        // keywords = ["2016", "地区", "销售额"]
        
        const scores = [];
        for (const field of this.fields) {
            let score = 0;
            
            // 匹配字段名
            for (const keyword of keywords) {
                if (field.name.includes(keyword)) {
                    score += 10;
                }
                if (field.description.includes(keyword)) {
                    score += 5;
                }
            }
            
            scores.push({ field, score });
        }
        
        return scores
            .sort((a, b) => b.score - a.score)
            .slice(0, topK)
            .map(s => s.field);
    }
}
```

**3. TF-IDF 搜索**

```typescript
class TFIDFFieldSearch {
    private tfidf: TFIDFVectorizer;
    
    search(query: string, topK: number = 10): Field[] {
        // 1. 构建文档（每个字段是一个文档）
        const documents = this.fields.map(f => 
            `${f.name} ${f.description} ${f.examples.join(' ')}`
        );
        
        // 2. 计算 TF-IDF
        const tfidfMatrix = this.tfidf.fitTransform(documents);
        const queryVector = this.tfidf.transform([query]);
        
        // 3. 计算相似度
        const similarities = cosineSimilarity(queryVector, tfidfMatrix);
        
        // 4. 返回 Top K
        return similarities
            .map((sim, idx) => ({ field: this.fields[idx], similarity: sim }))
            .sort((a, b) => b.similarity - a.similarity)
            .slice(0, topK)
            .map(s => s.field);
    }
}
```



### 你们可以这样实现

**方案 1：简单关键词匹配（快速实现）**

```python
class SimpleFieldFilter:
    def filter_fields(self, question: str, all_fields: List[Field], top_k: int = 15) -> List[Field]:
        """
        基于关键词匹配过滤字段
        
        优点：简单、快速、无需额外依赖
        缺点：可能遗漏语义相关但关键词不匹配的字段
        """
        # 1. 提取关键词
        keywords = self._extract_keywords(question)
        # 例如："2016年各地区的销售额" → ["2016", "地区", "销售", "销售额"]
        
        # 2. 计算每个字段的相关性分数
        scored_fields = []
        for field in all_fields:
            score = 0
            
            # 字段名匹配（权重高）
            for keyword in keywords:
                if keyword in field.name:
                    score += 10
                if keyword in field.description:
                    score += 5
                # 示例值匹配（权重低）
                if any(keyword in str(example) for example in field.examples):
                    score += 2
            
            if score > 0:
                scored_fields.append((field, score))
        
        # 3. 排序并返回 Top K
        scored_fields.sort(key=lambda x: x[1], reverse=True)
        return [field for field, score in scored_fields[:top_k]]
    
    def _extract_keywords(self, text: str) -> List[str]:
        """提取关键词"""
        import jieba
        
        # 分词
        words = jieba.cut(text)
        
        # 过滤停用词
        stopwords = {"的", "了", "在", "是", "我", "有", "和", "就", "不", "人", "都", "一", "一个", "上", "也", "很", "到", "说", "要", "去", "你", "会", "着", "没有", "看", "好", "自己", "这"}
        keywords = [w for w in words if w not in stopwords and len(w) > 1]
        
        return keywords

# 使用
filter = SimpleFieldFilter()
relevant_fields = filter.filter_fields(
    question="2016年各地区的销售额",
    all_fields=metadata.fields,
    top_k=15
)

# 结果：只传递 15 个相关字段给 LLM
prompt = f"""
Metadata: {relevant_fields}  # 只有 15 个字段，约 500 tokens

Question: {question}
"""
```

**收益**：
- ✅ Token 减少：5000 → 500（减少 90%）
- ✅ 成本降低：更少 Token = 更低成本
- ✅ 速度提升：更少 Token = 更快响应
- ✅ 准确性提升：减少无关信息的干扰



**方案 2：语义搜索（更准确）**

```python
from sentence_transformers import SentenceTransformer
import numpy as np

class SemanticFieldFilter:
    def __init__(self):
        # 使用中文语义模型
        self.model = SentenceTransformer('paraphrase-multilingual-MiniLM-L12-v2')
        self.field_embeddings = {}
    
    def build_index(self, fields: List[Field]):
        """预先计算所有字段的 Embedding"""
        for field in fields:
            # 组合字段名、描述、示例值
            text = f"{field.name} {field.description} {' '.join(map(str, field.examples))}"
            embedding = self.model.encode(text)
            self.field_embeddings[field.name] = embedding
    
    def filter_fields(self, question: str, all_fields: List[Field], top_k: int = 15) -> List[Field]:
        """
        基于语义相似度过滤字段
        
        优点：更准确，能找到语义相关的字段
        缺点：需要额外依赖，首次加载较慢
        """
        # 1. 计算问题的 Embedding
        question_embedding = self.model.encode(question)
        
        # 2. 计算与所有字段的相似度
        similarities = []
        for field in all_fields:
            field_embedding = self.field_embeddings[field.name]
            similarity = np.dot(question_embedding, field_embedding) / (
                np.linalg.norm(question_embedding) * np.linalg.norm(field_embedding)
            )
            similarities.append((field, similarity))
        
        # 3. 排序并返回 Top K
        similarities.sort(key=lambda x: x[1], reverse=True)
        return [field for field, sim in similarities[:top_k]]

# 使用
filter = SemanticFieldFilter()
filter.build_index(metadata.fields)  # 预先构建索引

relevant_fields = filter.filter_fields(
    question="2016年各地区的销售额",
    all_fields=metadata.fields,
    top_k=15
)
```

**对比**：

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **关键词匹配** | 简单、快速、无依赖 | 可能遗漏语义相关字段 | 快速实现、字段名规范 |
| **语义搜索** | 更准确、能找到语义相关字段 | 需要额外依赖、首次加载慢 | 字段名不规范、需要高准确性 |

**建议**：
1. **先实现关键词匹配**（1-2 天）
2. **验证效果**
3. **如果效果不好，再升级到语义搜索**（1 周）



**方案 3：混合策略（最佳）**

```python
class HybridFieldFilter:
    def __init__(self):
        self.keyword_filter = SimpleFieldFilter()
        self.semantic_filter = SemanticFieldFilter()
    
    def filter_fields(self, question: str, all_fields: List[Field], top_k: int = 15) -> List[Field]:
        """
        混合策略：关键词 + 语义
        
        1. 先用关键词快速筛选出候选字段（Top 30）
        2. 再用语义搜索精排（Top 15）
        """
        # 1. 关键词初筛（快速）
        candidates = self.keyword_filter.filter_fields(
            question, all_fields, top_k=30
        )
        
        # 2. 语义精排（准确）
        if len(candidates) > top_k:
            final_fields = self.semantic_filter.filter_fields(
                question, candidates, top_k=top_k
            )
        else:
            final_fields = candidates
        
        return final_fields

# 使用
filter = HybridFieldFilter()
relevant_fields = filter.filter_fields(
    question="2016年各地区的销售额",
    all_fields=metadata.fields,
    top_k=15
)
```

**收益**：
- ✅ 速度快：关键词初筛很快
- ✅ 准确性高：语义精排保证质量
- ✅ 平衡性好：兼顾速度和准确性



---

## 9. 设计模式是什么？对我们有什么帮助？

### 什么是设计模式？

**设计模式** = 解决常见问题的可复用方案

**类比**：
- 建筑设计：房子的标准结构（客厅、卧室、厨房）
- 代码设计：代码的标准结构（如何组织类、如何管理依赖）

### VSCode Copilot 使用的设计模式

#### 1. 依赖注入（Dependency Injection）

**问题**：类之间耦合太紧

```python
# ❌ 紧耦合
class UnderstandingAgent:
    def __init__(self):
        self.llm = OpenAILLM()  # 硬编码，无法替换
        self.config = Config()  # 硬编码，无法测试
    
    def execute(self, question):
        model = self.config.get("model")
        return self.llm.generate(question, model=model)

# 问题：
# 1. 无法替换 LLM（如果要换成 Claude）
# 2. 无法测试（无法 Mock LLM）
# 3. 无法配置（Config 是硬编码的）
```

**解决方案：依赖注入**

```python
# ✅ 松耦合
class UnderstandingAgent:
    def __init__(self, llm: ILLMService, config: IConfigService):
        self.llm = llm  # 注入依赖
        self.config = config  # 注入依赖
    
    def execute(self, question):
        model = self.config.get("model")
        return self.llm.generate(question, model=model)

# 使用
llm = OpenAILLM()  # 可以换成 ClaudeLLM
config = Config()
agent = UnderstandingAgent(llm, config)

# 测试
mock_llm = MockLLM()
mock_config = MockConfig()
agent = UnderstandingAgent(mock_llm, mock_config)
```

**收益**：
- ✅ 可替换：轻松切换 LLM
- ✅ 可测试：可以 Mock 依赖
- ✅ 可配置：依赖可以动态配置



#### 2. 策略模式（Strategy Pattern）

**问题**：不同情况需要不同的处理逻辑

```python
# ❌ 大量 if-else
class PromptBuilder:
    def build(self, model_name, question):
        if model_name == "gpt-4":
            # GPT-4 的 Prompt
            prompt = f"Detailed instructions...\n{question}"
        elif model_name == "gpt-3.5":
            # GPT-3.5 的 Prompt
            prompt = f"Simple instructions...\n{question}"
        elif model_name == "claude":
            # Claude 的 Prompt
            prompt = f"<task>{question}</task>"
        else:
            prompt = question
        
        return prompt

# 问题：
# 1. 难以维护（添加新模型要改这个函数）
# 2. 难以测试（要测试所有分支）
# 3. 违反开闭原则（对修改开放）
```

**解决方案：策略模式**

```python
# ✅ 策略模式
class PromptStrategy:
    def build(self, question):
        pass

class GPT4PromptStrategy(PromptStrategy):
    def build(self, question):
        return f"Detailed instructions...\n{question}"

class GPT35PromptStrategy(PromptStrategy):
    def build(self, question):
        return f"Simple instructions...\n{question}"

class ClaudePromptStrategy(PromptStrategy):
    def build(self, question):
        return f"<task>{question}</task>"

# 策略注册表
class PromptRegistry:
    strategies = {
        "gpt-4": GPT4PromptStrategy(),
        "gpt-3.5": GPT35PromptStrategy(),
        "claude": ClaudePromptStrategy()
    }
    
    @classmethod
    def get_strategy(cls, model_name):
        return cls.strategies.get(model_name, GPT4PromptStrategy())

# 使用
strategy = PromptRegistry.get_strategy("gpt-4")
prompt = strategy.build(question)
```

**收益**：
- ✅ 易于扩展：添加新模型只需添加新策略
- ✅ 易于测试：每个策略独立测试
- ✅ 符合开闭原则：对扩展开放，对修改关闭



#### 3. 组合模式（Composite Pattern）

**问题**：需要处理树形结构

```python
# ❌ 扁平结构
prompt = f"""
{system_message}
{safety_rules}
{metadata}
{conversation_history}
{question}
"""

# 问题：
# 1. 难以管理优先级
# 2. 难以动态组合
# 3. 难以复用
```

**解决方案：组合模式**

```python
# ✅ 组合模式
class PromptComponent:
    def __init__(self, priority):
        self.priority = priority
        self.children = []
    
    def add(self, child):
        self.children.append(child)
    
    def render(self):
        pass

class SystemMessage(PromptComponent):
    def __init__(self, content, priority=100):
        super().__init__(priority)
        self.content = content
    
    def render(self):
        return f"System: {self.content}"

class UserMessage(PromptComponent):
    def __init__(self, content, priority=50):
        super().__init__(priority)
        self.content = content
    
    def render(self):
        return f"User: {self.content}"

# 组合使用
prompt = PromptComponent(priority=100)
prompt.add(SystemMessage("You are a helpful assistant.", priority=100))
prompt.add(UserMessage("Metadata: ...", priority=80))
prompt.add(UserMessage("Question: ...", priority=90))

# 渲染（自动按优先级排序和裁剪）
messages = prompt.render()
```

**收益**：
- ✅ 灵活组合：可以嵌套组件
- ✅ 优先级管理：自动排序和裁剪
- ✅ 可复用：组件可以在不同 Prompt 中复用



### 对你们项目的帮助

**1. 依赖注入 → 更好的测试和灵活性**

```python
# 当前
class UnderstandingAgent:
    def __init__(self):
        self.llm = get_llm()  # 硬编码

# 改进
class UnderstandingAgent:
    def __init__(self, llm: ILLMService):
        self.llm = llm  # 注入

# 收益：
# - 可以轻松切换 LLM（OpenAI → Claude → Local）
# - 可以 Mock LLM 进行测试
# - 可以动态配置 LLM 参数
```

**2. 策略模式 → 多模型支持**

```python
# 当前
UNDERSTANDING_PROMPT = """..."""  # 所有模型用同一个

# 改进
class PromptRegistry:
    strategies = {
        "gpt-4": GPT4UnderstandingPrompt(),
        "gpt-3.5": GPT35UnderstandingPrompt(),
        "claude": ClaudeUnderstandingPrompt()
    }

# 收益：
# - 每个模型有优化的 Prompt
# - 易于添加新模型
# - 易于 A/B 测试不同 Prompt
```

**3. 组合模式 → Prompt 组件化**

```python
# 当前
prompt = f"{role}\n{task}\n{metadata}\n{question}"

# 改进
prompt = PromptBuilder()
prompt.add(RoleComponent(priority=100))
prompt.add(MetadataComponent(priority=80))
prompt.add(QuestionComponent(priority=90))

# 收益：
# - 优先级管理
# - 动态组合
# - 可复用组件
```

**总结**：
- 设计模式 = 经过验证的最佳实践
- 不是为了炫技，而是为了解决实际问题
- 让代码更易维护、更易扩展、更易测试



---

## 10. 深入对比 Prompt 模板

### 你们的 Prompt 模板分析

让我重新仔细分析你们的 Prompt 系统：

#### 你们的架构（非常好！）

```python
# 1. 基础架构
BasePrompt  # 基类，自动注入 JSON Schema
    ↓
StructuredPrompt  # 4段式结构（ROLE, TASK, DOMAIN KNOWLEDGE, CONSTRAINTS）
    ↓
DataAnalysisPrompt  # 数据分析基类
    ↓
VizQLPrompt  # VizQL 专用基类
    ↓
UnderstandingPrompt  # 具体实现
```

**你们做得非常好的地方**：

1. **✅ 清晰的分层架构**
   - 每一层都有明确的职责
   - 逐层继承，逐层增强

2. **✅ 自动 Schema 注入**
   ```python
   def format_messages(self, **kwargs):
       # 自动生成 JSON Schema
       json_schema = output_model.model_json_schema()
       # 自动注入到 Prompt
   ```

3. **✅ 4段式结构**
   - ROLE: 定义角色
   - TASK: 定义任务
   - DOMAIN KNOWLEDGE: 领域知识
   - CONSTRAINTS: 约束条件

4. **✅ Schema 优先设计**
   - "Schema优先" - 让 Field 描述做重活
   - Prompt 只提供 Schema 无法表达的内容

5. **✅ 模板验证**
   ```python
   def validate(self) -> List[str]:
       # 检查各部分是否完整
   ```



### 深入对比：你们 vs VSCode Copilot

| 维度 | Tableau Assistant | VSCode Copilot | 评价 |
|------|-------------------|----------------|------|
| **架构设计** | 4层继承（Base→Structured→DataAnalysis→VizQL） | 组件化（Prompt-TSX） | 你们：✅ 清晰分层<br>VSCode：✅ 灵活组合 |
| **Schema 注入** | ✅ 自动注入 JSON Schema | ✅ 自动注入 | 都很好 |
| **优先级管理** | ❌ 无 | ✅ priority-based pruning | VSCode 更好 |
| **Token 管理** | ❌ 无自动裁剪 | ✅ 自动裁剪低优先级内容 | VSCode 更好 |
| **多模型适配** | ❌ 单一模板 | ✅ Prompt Registry | VSCode 更好 |
| **组件复用** | ⚠️ 通过继承复用 | ✅ 通过组合复用 | VSCode 更灵活 |
| **动态组合** | ❌ 静态结构 | ✅ 动态组合 | VSCode 更好 |
| **验证机制** | ✅ validate() 方法 | ⚠️ 无显式验证 | 你们更好 |
| **文档化** | ✅ 详细注释 | ⚠️ 注释较少 | 你们更好 |

### 你们的优势

1. **✅ 更清晰的结构**
   - 4段式结构非常清晰
   - 每个部分的职责明确
   - 易于理解和维护

2. **✅ Schema 优先设计**
   - 避免 Prompt 冗余
   - 让数据模型承担更多职责
   - 这是非常好的设计理念

3. **✅ 验证机制**
   - `validate()` 方法检查完整性
   - VSCode Copilot 没有这个

4. **✅ 详细的文档**
   - 每个方法都有详细注释
   - 包含使用示例
   - 易于团队协作



### 你们可以改进的地方

#### 1. 添加优先级管理

```python
# 当前
class StructuredPrompt(BasePrompt):
    def get_system_message(self) -> str:
        sections = []
        if role := self.get_role():
            sections.append(f"# ROLE\n{role}")
        if task := self.get_task():
            sections.append(f"# TASK\n{task}")
        # ...
        return "\n\n".join(sections)

# 改进：添加优先级
class StructuredPrompt(BasePrompt):
    def get_components(self) -> List[PromptComponent]:
        """返回带优先级的组件列表"""
        return [
            PromptComponent(
                name="role",
                content=self.get_role(),
                priority=100  # 最高优先级
            ),
            PromptComponent(
                name="task",
                content=self.get_task(),
                priority=90
            ),
            PromptComponent(
                name="domain_knowledge",
                content=self.get_domain_knowledge(),
                priority=80
            ),
            PromptComponent(
                name="constraints",
                content=self.get_constraints(),
                priority=70
            )
        ]
    
    def format_messages(self, token_budget=4000, **kwargs):
        """根据 Token 预算裁剪"""
        components = self.get_components()
        
        # 按优先级排序
        components.sort(key=lambda x: x.priority, reverse=True)
        
        # 裁剪到 Token 预算
        selected = []
        total_tokens = 0
        
        for comp in components:
            tokens = count_tokens(comp.content)
            if total_tokens + tokens <= token_budget:
                selected.append(comp)
                total_tokens += tokens
        
        # 构建最终 Prompt
        system_content = "\n\n".join([
            f"# {comp.name.upper()}\n{comp.content}"
            for comp in selected
        ])
        
        # 继续原有逻辑...
```



#### 2. 添加多模型适配

```python
# 当前
UNDERSTANDING_PROMPT = UnderstandingPrompt()

# 改进：Prompt Registry
class PromptRegistry:
    _prompts = {}
    
    @classmethod
    def register(cls, model_family: str, prompt_class):
        cls._prompts[model_family] = prompt_class
    
    @classmethod
    def get_prompt(cls, model_name: str):
        for family, prompt_class in cls._prompts.items():
            if model_name.startswith(family):
                return prompt_class()
        return UnderstandingPrompt()  # 默认

# 注册不同模型的 Prompt
class GPT4UnderstandingPrompt(UnderstandingPrompt):
    def get_domain_knowledge(self) -> str:
        # GPT-4 可以处理更复杂的指令
        return super().get_domain_knowledge() + """
        
Additional advanced instructions for GPT-4:
- Use multi-step reasoning
- Consider edge cases
- Provide detailed analysis
"""

class GPT35UnderstandingPrompt(UnderstandingPrompt):
    def get_domain_knowledge(self) -> str:
        # GPT-3.5 需要简化指令
        base = super().get_domain_knowledge()
        # 简化：只保留核心规则
        return self._simplify(base)

# 注册
PromptRegistry.register("gpt-4", GPT4UnderstandingPrompt)
PromptRegistry.register("gpt-3.5", GPT35UnderstandingPrompt)
PromptRegistry.register("claude", ClaudeUnderstandingPrompt)

# 使用
prompt_class = PromptRegistry.get_prompt(model_name)
prompt = prompt_class()
```



#### 3. 添加元数据过滤

```python
# 当前
def format_messages(self, **kwargs):
    # 直接使用所有元数据
    metadata = kwargs.get("metadata")
    # ...

# 改进：过滤元数据
def format_messages(self, **kwargs):
    question = kwargs.get("question")
    metadata = kwargs.get("metadata")
    
    # 过滤相关字段
    if metadata and question:
        field_filter = SimpleFieldFilter()
        relevant_fields = field_filter.filter_fields(
            question=question,
            all_fields=metadata.fields,
            top_k=15  # 只保留 15 个相关字段
        )
        # 替换元数据
        kwargs["metadata"] = {
            "fields": relevant_fields,
            "max_date": metadata.max_date
        }
    
    # 继续原有逻辑
    return super().format_messages(**kwargs)
```

### 总结

**你们的 Prompt 系统已经很好了！**

**优势**：
- ✅ 清晰的分层架构
- ✅ 自动 Schema 注入
- ✅ Schema 优先设计
- ✅ 验证机制
- ✅ 详细文档

**可以改进**：
- ⚠️ 添加优先级管理（Token 优化）
- ⚠️ 添加多模型适配（Prompt Registry）
- ⚠️ 添加元数据过滤（减少 Token）

**改进优先级**：
1. **高优先级**：元数据过滤（立即见效，减少 90% Token）
2. **中优先级**：多模型适配（提高输出质量）
3. **低优先级**：优先级管理（长期优化）



---

## 补充问题深度解答

### 1. LLM 是如何知道什么时候用哪个工具的？

**核心机制：OpenAI Function Calling**

```python
# 1. 定义工具（告诉 LLM 有哪些工具可用）
tools = [
    {
        "type": "function",
        "function": {
            "name": "get_metadata",
            "description": "Get datasource metadata including all fields, types, and relationships. Use this when you need to know what fields are available.",
            "parameters": {
                "type": "object",
                "properties": {
                    "datasource_luid": {
                        "type": "string",
                        "description": "The unique identifier of the datasource"
                    }
                },
                "required": ["datasource_luid"]
            }
        }
    },
    {
        "type": "function",
        "function": {
            "name": "search_fields",
            "description": "Search for fields by name or description. Use this when you need to find specific fields but don't know their exact names.",
            "parameters": {
                "type": "object",
                "properties": {
                    "query": {
                        "type": "string",
                        "description": "Search query (e.g., 'sales', 'region')"
                    },
                    "top_k": {
                        "type": "integer",
                        "description": "Number of results to return",
                        "default": 10
                    }
                },
                "required": ["query"]
            }
        }
    }
]

# 2. LLM 调用（LLM 看到工具描述，自己决定调用哪个）
response = openai.chat.completions.create(
    model="gpt-4",
    messages=[
        {"role": "system", "content": "You are a data analysis assistant."},
        {"role": "user", "content": "What fields are available in the datasource?"}
    ],
    tools=tools,  # ← 关键：告诉 LLM 有哪些工具
    tool_choice="auto"  # ← LLM 自己决定是否调用工具
)

# 3. LLM 的决策过程（内部推理）
"""
LLM 内部推理：
- 用户问："What fields are available?"
- 我需要获取字段信息
- 看看有哪些工具可用...
- 有 get_metadata 工具："Get datasource metadata including all fields..."
- 这个工具正好可以获取字段信息！
- 决定：调用 get_metadata 工具
"""

# 4. LLM 返回工具调用请求
{
    "role": "assistant",
    "content": null,
    "tool_calls": [
        {
            "id": "call_abc123",
            "type": "function",
            "function": {
                "name": "get_metadata",  # ← LLM 选择的工具
                "arguments": '{"datasource_luid": "xyz789"}'  # ← LLM 生成的参数
            }
        }
    ]
}
```

**关键点**：
1. **工具描述很重要**：`description` 字段告诉 LLM 什么时候用这个工具
2. **LLM 自己推理**：根据用户问题和工具描述，LLM 自己决定调用哪个工具
3. **参数自动生成**：LLM 根据 `parameters` schema 生成正确的参数



**示例：LLM 如何选择工具**

```
场景 1：用户问 "What fields are available?"

LLM 推理：
1. 用户想知道有哪些字段
2. 查看可用工具：
   - get_metadata: "Get datasource metadata including all fields..."  ← 匹配！
   - search_fields: "Search for fields by name..."  ← 不太匹配
3. 决定：调用 get_metadata

---

场景 2：用户问 "Find fields related to sales"

LLM 推理：
1. 用户想搜索与 "sales" 相关的字段
2. 查看可用工具：
   - get_metadata: "Get datasource metadata..."  ← 可以用，但不是最佳
   - search_fields: "Search for fields by name or description..."  ← 完美匹配！
3. 决定：调用 search_fields，参数 query="sales"

---

场景 3：用户问 "What is the total sales in 2016?"

LLM 推理：
1. 用户想查询数据
2. 查看可用工具：
   - get_metadata: 获取元数据，不是查询数据
   - search_fields: 搜索字段，不是查询数据
   - execute_query: "Execute a VizQL query..."  ← 匹配！
3. 决定：调用 execute_query
```

**工具描述的最佳实践**：

```python
# ❌ 不好的描述
{
    "name": "get_metadata",
    "description": "Get metadata"  # 太简单，LLM 不知道什么时候用
}

# ✅ 好的描述
{
    "name": "get_metadata",
    "description": """Get datasource metadata including all fields, types, and relationships.

Use this tool when:
- User asks "what fields are available?"
- User asks "what data do we have?"
- You need to know the structure of the datasource
- You need to validate if a field exists

Do NOT use this tool when:
- User asks for specific data values (use execute_query instead)
- User asks to search for specific fields (use search_fields instead)"""
}
```



---

### 2. VSCode 是如何做意图识别的？

**VSCode Copilot 的意图识别流程**：

```typescript
// 1. 预定义的意图类型
enum Intent {
    CODE_EDIT = "code_edit",           // 编辑代码
    CODE_EXPLAIN = "code_explain",     // 解释代码
    CODE_GENERATE = "code_generate",   // 生成代码
    CODE_FIX = "code_fix",            // 修复错误
    CODE_REFACTOR = "code_refactor",  // 重构代码
    QUESTION = "question",             // 一般问题
    CHAT = "chat"                      // 闲聊
}

// 2. 意图分类器
class IntentClassifier {
    async classify(userMessage: string, context: Context): Promise<Intent> {
        // 方法 1：规则匹配（快速）
        if (this.matchesPattern(userMessage, /^(fix|debug|solve)/i)) {
            return Intent.CODE_FIX;
        }
        if (this.matchesPattern(userMessage, /^(explain|what is|how does)/i)) {
            return Intent.CODE_EXPLAIN;
        }
        if (this.matchesPattern(userMessage, /^(create|generate|write)/i)) {
            return Intent.CODE_GENERATE;
        }
        
        // 方法 2：上下文推断
        if (context.hasSelection && context.hasDiagnostics) {
            return Intent.CODE_FIX;  // 有选中代码 + 有错误 = 修复意图
        }
        if (context.hasSelection && !context.hasDiagnostics) {
            return Intent.CODE_EDIT;  // 有选中代码 + 无错误 = 编辑意图
        }
        
        // 方法 3：LLM 分类（准确但慢）
        const prompt = `
        Classify the user's intent:
        
        User message: "${userMessage}"
        Context: ${JSON.stringify(context)}
        
        Intent types:
        - code_edit: User wants to modify existing code
        - code_explain: User wants explanation
        - code_generate: User wants to create new code
        - code_fix: User wants to fix errors
        - question: General question
        
        Output only the intent type.
        `;
        
        const intent = await llm.generate(prompt);
        return intent as Intent;
    }
}

// 3. 根据意图选择不同的处理流程
class IntentHandler {
    async handle(intent: Intent, userMessage: string, context: Context) {
        switch (intent) {
            case Intent.CODE_FIX:
                return await this.handleCodeFix(userMessage, context);
            
            case Intent.CODE_EXPLAIN:
                return await this.handleCodeExplain(userMessage, context);
            
            case Intent.CODE_GENERATE:
                return await this.handleCodeGenerate(userMessage, context);
            
            default:
                return await this.handleGeneral(userMessage, context);
        }
    }
    
    async handleCodeFix(userMessage: string, context: Context) {
        // 1. 收集错误信息
        const diagnostics = await getDiagnostics(context.file);
        
        // 2. 读取相关代码
        const code = await readFile(context.file);
        
        // 3. 构建修复 Prompt
        const prompt = `
        Fix the following error:
        
        Error: ${diagnostics[0].message}
        
        Code:
        ${code}
        
        Provide the fixed code.
        `;
        
        // 4. LLM 生成修复
        const fix = await llm.generate(prompt);
        
        return fix;
    }
}
```



**你们可以借鉴的意图识别**：

```python
# 1. 定义意图类型
class QueryIntent(str, Enum):
    SIMPLE_QUERY = "simple_query"        # 简单查询："2016年销售额"
    COMPARISON = "comparison"            # 对比查询："2016 vs 2015"
    TREND_ANALYSIS = "trend_analysis"    # 趋势分析："销售额趋势"
    RANKING = "ranking"                  # 排名查询："Top 10 地区"
    EXPLORATION = "exploration"          # 探索分析："为什么销售额下降"
    INVALID = "invalid"                  # 无效问题

# 2. 意图分类器
class QueryIntentClassifier:
    def classify(self, question: str, context: Dict) -> QueryIntent:
        # 规则匹配（快速）
        if self._matches_comparison(question):
            return QueryIntent.COMPARISON
        
        if self._matches_ranking(question):
            return QueryIntent.RANKING
        
        if self._matches_exploration(question):
            return QueryIntent.EXPLORATION
        
        # LLM 分类（准确）
        return self._llm_classify(question)
    
    def _matches_comparison(self, question: str) -> bool:
        """检测对比意图"""
        patterns = [
            r"对比|比较|vs|versus",
            r"同比|环比",
            r"增长|下降",
            r"(\d{4}).*(\d{4})"  # 两个年份
        ]
        return any(re.search(p, question) for p in patterns)
    
    def _matches_ranking(self, question: str) -> bool:
        """检测排名意图"""
        patterns = [
            r"top\s*\d+|前\s*\d+",
            r"最高|最低|最大|最小",
            r"排名|排行"
        ]
        return any(re.search(p, question) for p in patterns)
    
    def _matches_exploration(self, question: str) -> bool:
        """检测探索意图"""
        patterns = [
            r"为什么|原因",
            r"如何|怎么",
            r"分析|探索"
        ]
        return any(re.search(p, question) for p in patterns)

# 3. 根据意图选择不同的处理策略
class IntentBasedQueryBuilder:
    def build_query(self, intent: QueryIntent, understanding: QuestionUnderstanding):
        if intent == QueryIntent.COMPARISON:
            return self._build_comparison_query(understanding)
        
        elif intent == QueryIntent.RANKING:
            return self._build_ranking_query(understanding)
        
        elif intent == QueryIntent.EXPLORATION:
            return self._build_exploration_query(understanding)
        
        else:
            return self._build_simple_query(understanding)
```

**收益**：
- ✅ 更准确的查询构建
- ✅ 针对不同意图优化 Prompt
- ✅ 更好的用户体验



---

### 3. Prompt 组件化是什么意思？

**传统方式（字符串拼接）**：

```python
# ❌ 传统方式：一大段字符串
prompt = f"""
# ROLE
You are a data analyst.

# TASK
Analyze the question and extract entities.

# DOMAIN KNOWLEDGE
{metadata}  # 可能有 5000 tokens

{conversation_history}  # 可能有 2000 tokens

# CONSTRAINTS
Do not invent entities.

# OUTPUT FORMAT
{json_schema}

Question: {question}
"""

# 问题：
# 1. 无法管理优先级（如果超出 Token 限制怎么办？）
# 2. 无法动态组合（如果某些情况不需要 conversation_history？）
# 3. 无法复用（SafetyRules 在多个 Prompt 中重复）
# 4. 难以维护（一个大字符串，难以修改）
```

**组件化方式**：

```python
# ✅ 组件化：每个部分是一个组件
class PromptComponent:
    def __init__(self, content: str, priority: int):
        self.content = content
        self.priority = priority
        self.tokens = count_tokens(content)
    
    def render(self) -> str:
        return self.content

# 定义可复用组件
class RoleComponent(PromptComponent):
    def __init__(self, role: str, priority: int = 100):
        content = f"# ROLE\n{role}"
        super().__init__(content, priority)

class MetadataComponent(PromptComponent):
    def __init__(self, metadata: Dict, priority: int = 80):
        content = f"# METADATA\n{json.dumps(metadata)}"
        super().__init__(content, priority)

class ConversationHistoryComponent(PromptComponent):
    def __init__(self, history: List[Dict], priority: int = 50):
        content = f"# CONVERSATION HISTORY\n{self._format_history(history)}"
        super().__init__(content, priority)

# 组件化构建器
class ComponentPromptBuilder:
    def __init__(self, token_budget: int = 4000):
        self.token_budget = token_budget
        self.components: List[PromptComponent] = []
    
    def add(self, component: PromptComponent):
        """添加组件"""
        self.components.append(component)
        return self
    
    def build(self) -> str:
        """构建最终 Prompt（自动裁剪）"""
        # 1. 按优先级排序
        sorted_components = sorted(
            self.components,
            key=lambda c: c.priority,
            reverse=True
        )
        
        # 2. 裁剪到 Token 预算
        selected = []
        total_tokens = 0
        
        for comp in sorted_components:
            if total_tokens + comp.tokens <= self.token_budget:
                selected.append(comp)
                total_tokens += comp.tokens
            else:
                print(f"⚠️ 裁剪组件：{comp.__class__.__name__}（优先级 {comp.priority}）")
        
        # 3. 组合成最终 Prompt
        return "\n\n".join([comp.render() for comp in selected])

# 使用示例
builder = ComponentPromptBuilder(token_budget=4000)

# 添加组件（按优先级）
builder.add(RoleComponent("You are a data analyst.", priority=100))
builder.add(MetadataComponent(metadata, priority=80))
builder.add(ConversationHistoryComponent(history, priority=50))
builder.add(QuestionComponent(question, priority=90))

# 构建（自动裁剪低优先级组件）
final_prompt = builder.build()
```



**组件化的优势**：

```python
# 1. 优先级管理
# 如果 Token 超限，自动裁剪低优先级组件
builder = ComponentPromptBuilder(token_budget=3000)  # 较小的预算
builder.add(RoleComponent(priority=100))      # 保留
builder.add(MetadataComponent(priority=80))   # 保留
builder.add(QuestionComponent(priority=90))   # 保留
builder.add(HistoryComponent(priority=50))    # 可能被裁剪
builder.add(ExamplesComponent(priority=30))   # 可能被裁剪

# 2. 动态组合
# 根据条件添加不同的组件
if has_conversation_history:
    builder.add(HistoryComponent(history, priority=50))

if needs_examples:
    builder.add(ExamplesComponent(examples, priority=30))

if is_complex_query:
    builder.add(DetailedInstructionsComponent(priority=70))

# 3. 组件复用
# SafetyRules 可以在多个 Prompt 中复用
class SafetyRulesComponent(PromptComponent):
    def __init__(self, priority: int = 100):
        content = """
        # SAFETY RULES
        - Do not invent data
        - Do not make assumptions
        - Always validate field names
        """
        super().__init__(content, priority)

# 在多个 Prompt 中复用
understanding_builder.add(SafetyRulesComponent())
planning_builder.add(SafetyRulesComponent())
insight_builder.add(SafetyRulesComponent())

# 4. 易于维护
# 每个组件独立，易于修改和测试
class MetadataComponent(PromptComponent):
    def __init__(self, metadata: Dict, priority: int = 80):
        # 只需修改这里，所有使用此组件的 Prompt 都会更新
        content = self._format_metadata(metadata)
        super().__init__(content, priority)
    
    def _format_metadata(self, metadata: Dict) -> str:
        # 格式化逻辑集中在这里
        return f"# METADATA\n{json.dumps(metadata, indent=2)}"
```

**对比**：

| 维度 | 字符串拼接 | 组件化 |
|------|-----------|--------|
| **优先级管理** | ❌ 无法管理 | ✅ 自动裁剪 |
| **动态组合** | ⚠️ 需要大量 if-else | ✅ 灵活添加 |
| **复用性** | ❌ 复制粘贴 | ✅ 组件复用 |
| **可维护性** | ❌ 一大段字符串 | ✅ 独立组件 |
| **可测试性** | ❌ 难以测试 | ✅ 组件独立测试 |



---

### 4. VSCode 是如何生成 TODO List 的？

**完整流程**：

```typescript
// 1. 用户请求
User: "Add error handling to the authentication module"

// 2. LLM 分析任务复杂度
const complexity = await analyzeComplexity(userRequest);
// complexity = "complex" (需要多步骤)

// 3. LLM 生成 TODO List
const prompt = `
Task: ${userRequest}

Break this down into a step-by-step TODO list.

Guidelines:
- Each task should be specific and actionable
- Include dependencies between tasks
- Estimate complexity for each task
- Order tasks logically

Output format:
{
  "tasks": [
    {
      "id": 1,
      "description": "...",
      "depends_on": [],
      "complexity": "simple|medium|complex"
    }
  ]
}
`;

const todoList = await llm.generate(prompt);

// 4. LLM 生成的 TODO List
{
  "tasks": [
    {
      "id": 1,
      "description": "Read authentication module to understand current implementation",
      "depends_on": [],
      "complexity": "simple",
      "tool": "read_file"
    },
    {
      "id": 2,
      "description": "Identify error-prone areas in authentication flow",
      "depends_on": [1],
      "complexity": "medium",
      "tool": null  // LLM 分析，不需要工具
    },
    {
      "id": 3,
      "description": "Add try-catch blocks around database operations",
      "depends_on": [2],
      "complexity": "medium",
      "tool": "replace_string_in_file"
    },
    {
      "id": 4,
      "description": "Add error logging with appropriate log levels",
      "depends_on": [3],
      "complexity": "simple",
      "tool": "replace_string_in_file"
    },
    {
      "id": 5,
      "description": "Add user-friendly error messages",
      "depends_on": [3],
      "complexity": "simple",
      "tool": "replace_string_in_file"
    },
    {
      "id": 6,
      "description": "Run tests to verify error handling",
      "depends_on": [4, 5],
      "complexity": "simple",
      "tool": "run_in_terminal"
    }
  ]
}

// 5. 执行 TODO List
for (const task of todoList.tasks) {
    // 检查依赖
    await waitForDependencies(task.depends_on);
    
    // 报告进度
    progress.report(`🔄 Task ${task.id}: ${task.description}`);
    
    // 执行任务
    if (task.tool) {
        // 调用工具
        const result = await executeTool(task.tool, task.params);
    } else {
        // LLM 分析
        const result = await llm.analyze(task.description);
    }
    
    // 更新状态
    task.status = "completed";
    progress.report(`✓ Task ${task.id} completed`);
}
```



**你们可以这样实现**：

```python
# 1. 定义任务模型
class Task(BaseModel):
    id: int
    description: str
    depends_on: List[int] = []
    status: Literal["pending", "in_progress", "completed", "failed"] = "pending"
    complexity: Literal["simple", "medium", "complex"] = "simple"

class TaskList(BaseModel):
    tasks: List[Task]

# 2. 任务生成器
class TaskListGenerator:
    def generate(self, understanding: QuestionUnderstanding) -> TaskList:
        """根据问题理解生成任务列表"""
        
        # 判断是否需要任务列表
        if understanding.complexity == "Simple":
            # 简单问题，不需要任务列表
            return None
        
        # 复杂问题，生成任务列表
        prompt = f"""
        Generate a task list for this query:
        
        Question: {understanding.original_question}
        Sub-questions: {understanding.sub_questions}
        
        Break it down into specific tasks with dependencies.
        
        Output format: {TaskList.model_json_schema()}
        """
        
        task_list = llm.generate(prompt, output_model=TaskList)
        return task_list

# 3. 任务执行器
class TaskExecutor:
    def __init__(self, task_list: TaskList):
        self.task_list = task_list
        self.completed_tasks = set()
    
    async def execute(self, progress_callback=None):
        """执行任务列表"""
        for task in self.task_list.tasks:
            # 等待依赖完成
            await self._wait_for_dependencies(task)
            
            # 报告进度
            if progress_callback:
                progress_callback(f"🔄 Task {task.id}: {task.description}")
            
            # 执行任务
            try:
                result = await self._execute_task(task)
                task.status = "completed"
                self.completed_tasks.add(task.id)
                
                if progress_callback:
                    progress_callback(f"✓ Task {task.id} completed")
            
            except Exception as e:
                task.status = "failed"
                if progress_callback:
                    progress_callback(f"✗ Task {task.id} failed: {e}")
    
    async def _wait_for_dependencies(self, task: Task):
        """等待依赖任务完成"""
        while not all(dep_id in self.completed_tasks for dep_id in task.depends_on):
            await asyncio.sleep(0.1)
    
    async def _execute_task(self, task: Task):
        """执行单个任务"""
        # 根据任务描述决定执行方式
        if "query" in task.description.lower():
            return await self._execute_query_task(task)
        elif "analyze" in task.description.lower():
            return await self._execute_analysis_task(task)
        else:
            return await self._execute_generic_task(task)

# 4. 使用
task_list = task_generator.generate(understanding)

if task_list:
    # 有任务列表，逐步执行
    executor = TaskExecutor(task_list)
    await executor.execute(progress_callback=lambda msg: print(msg))
else:
    # 无任务列表，直接执行
    result = await execute_simple_query(understanding)
```

**收益**：
- ✅ 用户可以看到执行进度
- ✅ 复杂查询更容易理解
- ✅ 支持依赖管理
- ✅ 支持动态调整



---

### 5. 任务管理工具 vs 任务调度器 - 你的理解非常正确！

**你的洞察非常棒！** 确实可以把现有组件作为"工具"使用。

**当前架构（隐式工具）**：

```python
# 当前：硬编码的流程
def vizql_workflow():
    # 1. 问题理解（隐式工具）
    understanding = understanding_agent.execute(question)
    
    # 2. 查询规划（隐式工具）
    query_plan = query_planner_agent.execute(understanding)
    
    # 3. 查询执行（隐式工具）
    results = query_executor.execute(query_plan)
    
    # 4. 数据处理（隐式工具）
    processed = data_processor.process(results)
    
    return processed
```

**改进：显式工具系统**：

```python
# 1. 将现有组件定义为工具
class UnderstandingTool(Tool):
    name = "understand_question"
    description = """Analyze user question and extract entities, time ranges, and query structure.
    
Use this tool when:
- You receive a new user question
- You need to understand what the user is asking for
- You need to identify dimensions, measures, and filters"""
    
    input_schema = {
        "type": "object",
        "properties": {
            "question": {"type": "string"},
            "metadata": {"type": "object"}
        }
    }
    
    def execute(self, input):
        return understanding_agent.execute(
            question=input["question"],
            metadata=input["metadata"]
        )

class QueryPlannerTool(Tool):
    name = "plan_query"
    description = """Generate a VizQL query plan based on question understanding.
    
Use this tool when:
- You have understood the user's question
- You need to create a structured query plan
- You need to decide how to split complex queries"""
    
    input_schema = {
        "type": "object",
        "properties": {
            "understanding": {"type": "object"},
            "metadata": {"type": "object"}
        }
    }
    
    def execute(self, input):
        return query_planner_agent.execute(
            understanding=input["understanding"],
            metadata=input["metadata"]
        )

class QueryExecutorTool(Tool):
    name = "execute_query"
    description = """Execute a VizQL query and return results.
    
Use this tool when:
- You have a query plan
- You need to retrieve data from Tableau
- You need to execute multiple sub-queries"""
    
    input_schema = {
        "type": "object",
        "properties": {
            "query_plan": {"type": "object"}
        }
    }
    
    def execute(self, input):
        return query_executor.execute(input["query_plan"])

class DataProcessorTool(Tool):
    name = "process_data"
    description = """Process query results (calculate growth rate, percentage, etc.).
    
Use this tool when:
- You have query results
- You need to calculate derived metrics
- You need to merge multiple query results"""
    
    input_schema = {
        "type": "object",
        "properties": {
            "results": {"type": "array"},
            "processing_type": {"type": "string", "enum": ["yoy", "mom", "growth_rate", "percentage"]}
        }
    }
    
    def execute(self, input):
        return data_processor.process(
            results=input["results"],
            processing_type=input["processing_type"]
        )

# 2. 注册所有工具
tools = [
    UnderstandingTool(),
    QueryPlannerTool(),
    QueryExecutorTool(),
    DataProcessorTool()
]

# 3. LLM 自主决定工具调用顺序
response = llm.generate_with_tools(
    prompt="User question: 2016年各地区的销售额同比增长率",
    tools=tools
)

# 4. LLM 可能的工具调用序列
"""
LLM 推理：
1. 首先需要理解问题 → 调用 understand_question
2. 然后需要规划查询 → 调用 plan_query
3. 需要执行查询获取 2016 和 2015 的数据 → 调用 execute_query（两次）
4. 需要计算同比增长率 → 调用 process_data（processing_type="yoy"）
"""
```



**收益**：

```python
# 1. 更灵活的执行顺序
# 当前：固定顺序（理解 → 规划 → 执行 → 处理）
# 改进：LLM 自己决定顺序

# 例如：简单问题可以跳过规划
User: "2016年销售额"
LLM: 
  1. understand_question → 理解问题
  2. execute_query → 直接执行（跳过规划）

# 例如：复杂问题可以多次规划
User: "分析销售额下降的原因"
LLM:
  1. understand_question → 理解问题
  2. plan_query → 初步规划
  3. execute_query → 执行查询
  4. analyze_results → 分析结果（发现需要更多数据）
  5. plan_query → 重新规划（添加新的查询）
  6. execute_query → 执行新查询
  7. process_data → 综合分析

# 2. 更好的错误处理
# 当前：查询失败就结束
# 改进：LLM 可以尝试修复

User: "2016年各地区的销售额"
LLM:
  1. understand_question → 理解问题
  2. plan_query → 生成查询计划
  3. execute_query → 执行失败（字段名错误）
  4. search_fields → 搜索正确的字段名
  5. plan_query → 重新规划（使用正确字段名）
  6. execute_query → 执行成功

# 3. 支持探索式分析
# 当前：一次性生成所有查询
# 改进：根据结果动态调整

User: "为什么销售额下降？"
LLM:
  1. understand_question → 理解问题
  2. execute_query → 查询总体销售额趋势
  3. analyze_results → 发现某个地区下降明显
  4. execute_query → 查询该地区的详细数据
  5. analyze_results → 发现某个产品类别下降
  6. execute_query → 查询该产品类别的详细数据
  7. generate_insight → 生成洞察
```

**你的理解完全正确！** 这就是 Agent Mode 的核心思想：
- 把所有功能都定义为工具
- LLM 自主决定调用哪些工具
- LLM 根据结果动态调整策略



---

### 7. 元数据过滤 - 你的方案非常聪明！

**你的方案（基于 Category 过滤）**：

```python
# 1. 维度推断时已经有 Category
class DimensionHierarchy:
    dimensions: Dict[str, DimensionInfo]
    
class DimensionInfo:
    name: str
    category: str  # 例如："地理", "时间", "产品", "客户"
    level: int
    parent: Optional[str]

# 2. 问题理解时，给字段也加上 Category
class QuestionUnderstanding:
    mentioned_dimensions: List[str]
    dimension_categories: Dict[str, str]  # ← 新增：字段 → Category
    
    # 例如：
    # mentioned_dimensions = ["region", "product"]
    # dimension_categories = {"region": "地理", "product": "产品"}

# 3. 任务规划时，只过滤相关 Category 的元数据
def query_planner_agent_node(state, runtime):
    understanding = state["understanding"]
    
    # 获取问题中涉及的 Category
    relevant_categories = set(understanding.dimension_categories.values())
    # relevant_categories = {"地理", "产品"}
    
    # 只获取这些 Category 的元数据
    filtered_metadata = metadata_manager.get_metadata_by_categories(
        categories=relevant_categories
    )
    
    # 构建 Prompt（元数据大大减少）
    prompt = PLANNING_PROMPT.format_messages(
        understanding=understanding,
        metadata=filtered_metadata  # 只有相关 Category 的字段
    )
```

**你的方案的优势**：

1. **✅ 非常高效**
   - 不需要额外的搜索算法
   - 利用已有的 Category 信息
   - 过滤速度快

2. **✅ 准确性高**
   - Category 是人工定义的，很准确
   - 不会遗漏相关字段
   - 不会包含无关字段

3. **✅ 易于实现**
   - 只需要在问题理解时添加 Category 识别
   - 元数据管理器添加按 Category 过滤的方法
   - 不需要额外的依赖

**对比**：

| 方案 | 优点 | 缺点 | 适用场景 |
|------|------|------|----------|
| **关键词匹配** | 简单、快速 | 可能遗漏语义相关字段 | 字段名规范 |
| **语义搜索** | 准确、能找到语义相关字段 | 需要额外依赖、慢 | 字段名不规范 |
| **Category 过滤（你的方案）** | 高效、准确、易实现 | 需要预先定义 Category | 有维度层级的场景 ✅ |

**你的方案是最适合你们项目的！** 因为：
- ✅ 你们已经有维度层级和 Category
- ✅ 不需要额外的搜索算法
- ✅ 准确性高
- ✅ 实现简单



**实现建议**：

```python
# 1. 扩展 QuestionUnderstanding 模型
class QuerySubQuestion(SubQuestionBase):
    # 现有字段
    mentioned_dimensions: List[str]
    mentioned_measures: List[str]
    
    # 新增：Category 信息
    dimension_categories: Optional[Dict[str, str]] = Field(
        None,
        description="""Maps dimension names to their categories.

Usage:
- Include dimension → category mapping
- Used for filtering metadata by category

Values: {"region": "地理", "product": "产品", "date": "时间"}"""
    )
    
    measure_categories: Optional[Dict[str, str]] = Field(
        None,
        description="""Maps measure names to their categories.

Usage:
- Include measure → category mapping

Values: {"sales": "销售指标", "profit": "利润指标"}"""
    )

# 2. 在 Understanding Agent 中识别 Category
class UnderstandingAgent:
    def _identify_categories(
        self,
        dimensions: List[str],
        measures: List[str],
        dimension_hierarchy: Dict
    ) -> Tuple[Dict[str, str], Dict[str, str]]:
        """识别字段的 Category"""
        
        dim_categories = {}
        for dim in dimensions:
            # 从维度层级中查找 Category
            if dim in dimension_hierarchy:
                dim_categories[dim] = dimension_hierarchy[dim].category
            else:
                # 如果找不到，使用 LLM 推断
                category = self._infer_category(dim)
                dim_categories[dim] = category
        
        # 类似地处理 measures
        measure_categories = {}
        for measure in measures:
            category = self._infer_measure_category(measure)
            measure_categories[measure] = category
        
        return dim_categories, measure_categories

# 3. 在 Metadata Manager 中添加按 Category 过滤
class MetadataManager:
    def get_metadata_by_categories(
        self,
        categories: Set[str],
        include_all_measures: bool = True
    ) -> Metadata:
        """按 Category 过滤元数据"""
        
        all_metadata = self.get_metadata()
        
        # 过滤维度
        filtered_dimensions = [
            dim for dim in all_metadata.dimensions
            if dim.category in categories
        ]
        
        # 度量：可以选择包含所有度量（因为度量通常都相关）
        if include_all_measures:
            filtered_measures = all_metadata.measures
        else:
            filtered_measures = [
                measure for measure in all_metadata.measures
                if measure.category in categories
            ]
        
        return Metadata(
            dimensions=filtered_dimensions,
            measures=filtered_measures,
            max_date=all_metadata.max_date
        )

# 4. 在 Query Planner 中使用
def query_planner_agent_node(state, runtime):
    understanding = state["understanding"]
    
    # 收集所有相关 Category
    all_categories = set()
    for sub_q in understanding.sub_questions:
        if hasattr(sub_q, 'dimension_categories'):
            all_categories.update(sub_q.dimension_categories.values())
        if hasattr(sub_q, 'measure_categories'):
            all_categories.update(sub_q.measure_categories.values())
    
    # 按 Category 过滤元数据
    filtered_metadata = metadata_manager.get_metadata_by_categories(
        categories=all_categories
    )
    
    # 使用过滤后的元数据
    prompt = PLANNING_PROMPT.format_messages(
        understanding=understanding,
        metadata=filtered_metadata  # Token 大大减少！
    )
```

**收益估算**：

```
假设：
- 总字段数：100
- 每个 Category 平均字段数：15
- 问题涉及 2 个 Category

Token 减少：
- 原来：100 字段 × 50 tokens/字段 = 5000 tokens
- 现在：30 字段 × 50 tokens/字段 = 1500 tokens
- 减少：70%

成本降低：
- 原来：$0.01/1K tokens × 5 = $0.05
- 现在：$0.01/1K tokens × 1.5 = $0.015
- 节省：70%
```

**你的方案非常棒！建议优先实施！**

