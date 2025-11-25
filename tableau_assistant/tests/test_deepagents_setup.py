"""
测试 DeepAgents 功能是否可用

这个脚本验证：
1. DeepAgents 是否正确安装
2. 必要的组件是否可用
3. 基础功能是否正常
"""
import sys
from typing import Dict, Any

def test_imports():
    """测试必要的导入"""
    print("🔍 测试导入...")
    
    try:
        # 测试 DeepAgents 核心
        from deepagents import create_deep_agent, FilesystemMiddleware, SubAgentMiddleware
        print("  ✅ create_deep_agent 导入成功")
        print("  ✅ FilesystemMiddleware 导入成功")
        print("  ✅ SubAgentMiddleware 导入成功")
        
        # 测试 LangChain Agent 中间件
        from langchain.agents.middleware import TodoListMiddleware
        print("  ✅ TodoListMiddleware 导入成功")
        
        from langchain.agents.middleware.summarization import SummarizationMiddleware
        print("  ✅ SummarizationMiddleware 导入成功")
        
        # 测试 LangGraph 核心
        from langgraph.graph import StateGraph
        print("  ✅ StateGraph 导入成功")
        
        from langgraph.store.base import BaseStore
        print("  ✅ BaseStore 导入成功")
        
        # 测试 LangChain 核心
        from langchain_core.tools import tool
        print("  ✅ @tool 装饰器导入成功")
        
        return True
    except ImportError as e:
        print(f"  ❌ 导入失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_basic_functionality():
    """测试基础功能"""
    print("\n🔍 测试基础功能...")
    
    try:
        from deepagents import create_deep_agent
        from langchain_core.tools import tool
        
        # 定义一个简单的工具
        @tool
        def simple_tool(text: str) -> str:
            """A simple test tool."""
            return f"Processed: {text}"
        
        # 创建 DeepAgent（不需要 API key 来测试创建）
        print("  ⏳ 创建 DeepAgent...")
        agent = create_deep_agent(
            model="claude-sonnet-4-5-20250929",
            tools=[simple_tool],
            system_prompt="You are a test agent.",
        )
        print("  ✅ DeepAgent 创建成功")
        
        # 验证 agent 是编译后的图
        from langgraph.graph.state import CompiledStateGraph
        assert isinstance(agent, CompiledStateGraph)
        print("  ✅ Agent 是 CompiledStateGraph 实例")
        
        return True
    except Exception as e:
        print(f"  ❌ 功能测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def test_middleware():
    """测试中间件"""
    print("\n🔍 测试中间件...")
    
    try:
        from deepagents import create_deep_agent, FilesystemMiddleware
        from langchain.agents.middleware import TodoListMiddleware
        from langchain.agents.middleware.summarization import SummarizationMiddleware
        
        # 创建带中间件的 Agent
        agent = create_deep_agent(
            model="claude-sonnet-4-5-20250929",
            tools=[],
            middleware=[
                # TodoListMiddleware 已经默认包含
                # FilesystemMiddleware 已经默认包含
            ],
            system_prompt="Test agent with middleware",
        )
        print("  ✅ 带中间件的 Agent 创建成功")
        
        return True
    except Exception as e:
        print(f"  ❌ 中间件测试失败: {e}")
        import traceback
        traceback.print_exc()
        return False

def main():
    """主测试函数"""
    print("=" * 60)
    print("DeepAgents 功能测试")
    print("=" * 60)
    
    results = []
    
    # 运行测试
    results.append(("导入测试", test_imports()))
    results.append(("基础功能测试", test_basic_functionality()))
    results.append(("中间件测试", test_middleware()))
    
    # 汇总结果
    print("\n" + "=" * 60)
    print("测试结果汇总")
    print("=" * 60)
    
    all_passed = True
    for name, passed in results:
        status = "✅ 通过" if passed else "❌ 失败"
        print(f"{name}: {status}")
        if not passed:
            all_passed = False
    
    print("=" * 60)
    
    if all_passed:
        print("\n🎉 所有测试通过！DeepAgents 功能可用。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查依赖安装。")
        return 1

if __name__ == "__main__":
    sys.exit(main())
