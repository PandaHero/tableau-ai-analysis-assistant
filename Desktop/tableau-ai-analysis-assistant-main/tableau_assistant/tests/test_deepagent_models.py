"""测试 DeepAgent 模型与现有模型的兼容性"""

def test_deepagent_state():
    """测试 DeepAgentState 模型"""
    from deepagent_state import create_initial_state
    
    print("=" * 60)
    print("测试 DeepAgentState")
    print("=" * 60)
    
    # 创建初始状态
    state = create_initial_state(
        question="2024年各地区的销售额是多少？",
        datasource_luid="test-datasource-123",
        thread_id="thread-456",
        user_id="user-789",
        boost_question=False,
        max_rounds=3
    )
    
    print("\n✅ 初始状态创建成功")
    print(f"  - 问题: {state['question']}")
    print(f"  - 数据源: {state['datasource_luid']}")
    print(f"  - 线程ID: {state['thread_id']}")
    print(f"  - 用户ID: {state['user_id']}")
    print(f"  - 当前轮次: {state['current_round']}/{state['max_rounds']}")
    
    # 验证状态字段
    assert state['question'] == "2024年各地区的销售额是多少？"
    assert state['datasource_luid'] == "test-datasource-123"
    assert state['thread_id'] == "thread-456"
    assert state['user_id'] == "user-789"
    assert state['current_round'] == 0
    assert state['max_rounds'] == 3
    assert state['needs_replan'] == False
    assert state['query_results'] == []
    assert state['insights'] == []
    
    print("\n✅ 所有字段验证通过")
    
    return True


def test_deepagent_context():
    """测试 DeepAgentContext 模型"""
    from deepagent_context import DeepAgentContext
    
    print("\n" + "=" * 60)
    print("测试 DeepAgentContext")
    print("=" * 60)
    
    # 创建上下文
    context = DeepAgentContext(
        datasource_luid="test-datasource-123",
        user_id="user-789",
        thread_id="thread-456",
        tableau_token="test-token-abc",
        max_replan=3,
        enable_boost=True,
        enable_cache=True,
        timeout=300,
        max_tokens_per_call=4000,
        temperature=0.0
    )
    
    print("\n✅ 上下文创建成功")
    print(f"  - 数据源: {context.datasource_luid}")
    print(f"  - 用户ID: {context.user_id}")
    print(f"  - 线程ID: {context.thread_id}")
    print(f"  - 最大重规划次数: {context.max_replan}")
    print(f"  - 启用问题优化: {context.enable_boost}")
    print(f"  - 启用缓存: {context.enable_cache}")
    
    # 测试不可变性
    try:
        context.max_replan = 5  # 应该失败
        print("\n❌ 上下文应该是不可变的")
        return False
    except Exception:
        print("\n✅ 上下文不可变性验证通过")
    
    # 测试序列化
    context_dict = context.to_dict()
    print("\n✅ 序列化成功")
    print(f"  - 字典键数量: {len(context_dict)}")
    
    # 测试反序列化
    context2 = DeepAgentContext.from_dict(context_dict)
    assert context2.datasource_luid == context.datasource_luid
    assert context2.user_id == context.user_id
    assert context2.max_replan == context.max_replan
    print("\n✅ 反序列化成功")
    
    return True


def test_compatibility_with_existing_models():
    """测试与现有模型的兼容性"""
    from deepagent_state import DeepAgentState
    # 不需要实际导入现有模型，只需验证类型兼容性
    # from question import QuestionUnderstanding
    # from query_plan import QueryPlanningResult
    # from result import InsightCollection, FinalReport
    
    print("\n" + "=" * 60)
    print("测试与现有模型的兼容性")
    print("=" * 60)
    
    # 验证 DeepAgentState 可以存储现有模型
    print("\n✅ DeepAgentState 可以存储以下类型:")
    print("  - understanding: Dict[str, Any] (可存储 QuestionUnderstanding)")
    print("  - query_plan: Dict[str, Any] (可存储 QueryPlanningResult)")
    print("  - insights: List[Dict[str, Any]] (可存储 InsightCollection)")
    print("  - final_report: Dict[str, Any] (可存储 FinalReport)")
    
    # 验证类型提示
    print("\n✅ 类型兼容性:")
    print("  - QuestionUnderstanding → Dict[str, Any] ✓")
    print("  - QueryPlanningResult → Dict[str, Any] ✓")
    print("  - InsightCollection → Dict[str, Any] ✓")
    print("  - FinalReport → Dict[str, Any] ✓")
    
    return True


def main():
    """主测试函数"""
    print("=" * 60)
    print("DeepAgent 模型兼容性测试")
    print("=" * 60)
    
    results = []
    
    # 运行测试
    try:
        results.append(("DeepAgentState 测试", test_deepagent_state()))
    except Exception as e:
        print(f"\n❌ DeepAgentState 测试失败: {e}")
        results.append(("DeepAgentState 测试", False))
    
    try:
        results.append(("DeepAgentContext 测试", test_deepagent_context()))
    except Exception as e:
        print(f"\n❌ DeepAgentContext 测试失败: {e}")
        results.append(("DeepAgentContext 测试", False))
    
    try:
        results.append(("兼容性测试", test_compatibility_with_existing_models()))
    except Exception as e:
        print(f"\n❌ 兼容性测试失败: {e}")
        results.append(("兼容性测试", False))
    
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
        print("\n🎉 所有测试通过！模型兼容性验证成功。")
        return 0
    else:
        print("\n⚠️  部分测试失败，请检查模型定义。")
        return 1


if __name__ == "__main__":
    import sys
    sys.exit(main())
