"""
DeepAgent 创建器

此模块负责创建配置了 6 个 DeepAgents 中间件的 Tableau Assistant Agent。

中间件列表：
1. AnthropicPromptCachingMiddleware (仅 Claude 模型)
2. SummarizationMiddleware
3. FilesystemMiddleware
4. PatchToolCallsMiddleware
5. TodoListMiddleware
6. HumanInTheLoopMiddleware

排除：SubAgentMiddleware (使用 StateGraph 替代)
"""
from typing import List, Dict, Any, Optional
from langchain_core.tools import BaseTool
from langgraph.graph.state import CompiledStateGraph
from langgraph.store.base import BaseStore

from deepagents import create_deep_agent
from deepagents.middleware import FilesystemMiddleware
from langchain.agents.middleware import (
    SummarizationMiddleware,
    TodoListMiddleware,
    HumanInTheLoopMiddleware,
    ToolRetryMiddleware,  # 用于工具调用错误恢复
)


def create_tableau_deep_agent(
    tools: List[BaseTool],
    model_config: Optional[Dict[str, Any]] = None,
    store: Optional[BaseStore] = None,
    system_prompt: Optional[str] = None
) -> CompiledStateGraph:
    """
    创建 Tableau Assistant 的 DeepAgent
    
    此函数创建一个配置了 6 个中间件的 DeepAgent：
    - AnthropicPromptCachingMiddleware (仅 Claude 模型)
    - SummarizationMiddleware
    - FilesystemMiddleware
    - PatchToolCallsMiddleware
    - TodoListMiddleware
    - HumanInTheLoopMiddleware
    
    Args:
        tools: 8 个 Tableau 工具列表
        model_config: 模型配置字典
            - provider: "claude", "deepseek", "qwen", "openai"
            - model_name: 模型名称
            - temperature: 温度设置
        store: SQLite Store 实例
        system_prompt: 可选的系统提示
    
    Returns:
        编译后的 DeepAgent 图
    
    Raises:
        ValueError: 如果配置无效
    """
    # 默认模型配置
    if model_config is None:
        model_config = {
            "provider": "local",
            "model_name": "deepseek-chat",
            "temperature": 0.0
        }
    
    # 获取模型
    from tableau_assistant.src.bi_platforms.tableau.models import select_model
    
    provider = model_config.get("provider", "local")
    model_name = model_config.get("model_name", "deepseek-chat")
    temperature = model_config.get("temperature", 0.0)
    
    model = select_model(
        provider=provider,
        model_name=model_name,
        temperature=temperature
    )
    
    # 配置中间件列表
    middleware = []
    
    # 1. AnthropicPromptCachingMiddleware (仅 Claude 模型)
    if provider == "claude":
        try:
            from langchain.agents.middleware import AnthropicPromptCachingMiddleware
            
            caching_middleware = AnthropicPromptCachingMiddleware(
                cache_control={"type": "ephemeral"},
                ttl=300  # 5 分钟
            )
            middleware.append(caching_middleware)
            print("✓ 启用 AnthropicPromptCachingMiddleware (Claude 模型)")
        except ImportError:
            print("⚠ AnthropicPromptCachingMiddleware 不可用，跳过")
    
    # 2. SummarizationMiddleware
    summarization_middleware = SummarizationMiddleware(
        trigger_threshold=10,  # 10 轮对话后触发
        summary_model=model,  # 使用相同模型
        preserve_insights=True  # 保留洞察内容
    )
    middleware.append(summarization_middleware)
    print("✓ 启用 SummarizationMiddleware")
    
    # 3. FilesystemMiddleware
    filesystem_middleware = FilesystemMiddleware(
        base_path="data/agent_files",
        size_threshold=10 * 1024 * 1024,  # 10MB
        cleanup_on_session_end=True
    )
    middleware.append(filesystem_middleware)
    print("✓ 启用 FilesystemMiddleware")
    
    # 4. ToolRetryMiddleware (用于工具调用错误恢复)
    retry_middleware = ToolRetryMiddleware(
        max_retries=3,
        retry_on_errors=True
    )
    middleware.append(retry_middleware)
    print("✓ 启用 ToolRetryMiddleware (工具调用错误恢复)")
    
    # 5. TodoListMiddleware
    todo_middleware = TodoListMiddleware(
        max_tasks=10,
        auto_execute=True,
        task_timeout=300  # 5 分钟
    )
    middleware.append(todo_middleware)
    print("✓ 启用 TodoListMiddleware")
    
    # 6. HumanInTheLoopMiddleware
    hitl_middleware = HumanInTheLoopMiddleware(
        approval_required=["replanning"],
        timeout=300,  # 5 分钟
        default_action="execute_all"  # 超时后默认执行所有
    )
    middleware.append(hitl_middleware)
    print("✓ 启用 HumanInTheLoopMiddleware")
    
    # 创建 DeepAgent
    # 注意：不使用 subagents 参数，因为我们使用 StateGraph 替代 SubAgentMiddleware
    agent = create_deep_agent(
        model=model,
        tools=tools,
        system_prompt=system_prompt,
        middleware=middleware,
        subagents=None,  # 明确不使用 SubAgentMiddleware
        store=store,
        checkpointer=True,  # 启用对话历史
        debug=False
    )
    
    print(f"✓ DeepAgent 创建成功，配置了 {len(middleware)} 个中间件")
    print(f"✓ 配置了 {len(tools)} 个工具")
    
    return agent


def get_middleware_info(agent: CompiledStateGraph) -> Dict[str, Any]:
    """
    获取 Agent 的中间件信息
    
    用于测试和调试，验证中间件配置是否正确
    
    Args:
        agent: DeepAgent 实例
    
    Returns:
        中间件信息字典
    """
    # 尝试从 agent 中提取中间件信息
    # 注意：这取决于 DeepAgents 的内部实现
    middleware_info = {
        "middleware_count": 0,
        "middleware_types": [],
        "has_caching": False,
        "has_summarization": False,
        "has_filesystem": False,
        "has_patch": False,
        "has_todo": False,
        "has_hitl": False,
        "has_subagent": False
    }
    
    # 如果 agent 有 middleware 属性，提取信息
    if hasattr(agent, 'middleware'):
        middlewares = agent.middleware
        middleware_info["middleware_count"] = len(middlewares)
        
        for mw in middlewares:
            mw_type = type(mw).__name__
            middleware_info["middleware_types"].append(mw_type)
            
            if "Caching" in mw_type:
                middleware_info["has_caching"] = True
            elif "Summarization" in mw_type:
                middleware_info["has_summarization"] = True
            elif "Filesystem" in mw_type:
                middleware_info["has_filesystem"] = True
            elif "Patch" in mw_type:
                middleware_info["has_patch"] = True
            elif "Todo" in mw_type:
                middleware_info["has_todo"] = True
            elif "HumanInTheLoop" in mw_type or "HITL" in mw_type:
                middleware_info["has_hitl"] = True
            elif "SubAgent" in mw_type:
                middleware_info["has_subagent"] = True
    
    return middleware_info


# 示例用法
if __name__ == "__main__":
    # 测试创建 DeepAgent
    print("=" * 60)
    print("测试 DeepAgent 创建器")
    print("=" * 60)
    
    # 创建空工具列表用于测试
    test_tools = []
    
    # 测试 1: 使用 Claude 模型
    print("\n测试 1: Claude 模型")
    print("-" * 60)
    try:
        agent_claude = create_tableau_deep_agent(
            tools=test_tools,
            model_config={
                "provider": "claude",
                "model_name": "claude-3-5-sonnet-20241022",
                "temperature": 0.0
            }
        )
        info = get_middleware_info(agent_claude)
        print(f"中间件数量: {info['middleware_count']}")
        print(f"中间件类型: {info['middleware_types']}")
        print(f"包含缓存中间件: {info['has_caching']}")
    except Exception as e:
        print(f"✗ 创建失败: {e}")
    
    # 测试 2: 使用非 Claude 模型
    print("\n测试 2: DeepSeek 模型")
    print("-" * 60)
    try:
        agent_deepseek = create_tableau_deep_agent(
            tools=test_tools,
            model_config={
                "provider": "local",
                "model_name": "deepseek-chat",
                "temperature": 0.0
            }
        )
        info = get_middleware_info(agent_deepseek)
        print(f"中间件数量: {info['middleware_count']}")
        print(f"中间件类型: {info['middleware_types']}")
        print(f"包含缓存中间件: {info['has_caching']}")
    except Exception as e:
        print(f"✗ 创建失败: {e}")
