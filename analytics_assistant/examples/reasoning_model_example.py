# -*- coding: utf-8 -*-
"""
推理模型使用示例

演示如何配置和使用推理模型（如 DeepSeek-R1）
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

from src.infra.ai import (
    get_model_manager,
    ModelCreateRequest,
    ModelType,
    TaskType,
)


def setup_reasoning_model():
    """配置推理模型"""
    manager = get_model_manager()
    
    # 注册 DeepSeek-R1（推理模型）
    deepseek_r1_request = ModelCreateRequest(
        name="DeepSeek-R1",
        model_type=ModelType.LLM,
        provider="deepseek",
        api_base="http://localhost:8001/v1",  # 本地部署
        model_name="deepseek-reasoner",
        api_key="EMPTY",
        openai_compatible=True,
        temperature=0.7,
        max_tokens=8192,
        supports_streaming=True,
        is_reasoning_model=True,  # 标记为推理模型
        suitable_tasks=[
            TaskType.REASONING,  # 推理任务
            TaskType.INSIGHT_GENERATION,  # 洞察生成
            TaskType.REPLANNING,  # 重新规划
        ],
        priority=10,
    )
    
    config = manager.create(deepseek_r1_request)
    print(f"✅ 已注册推理模型: {config.name}")
    print(f"   - 模型 ID: {config.id}")
    print(f"   - 是否推理模型: {config.is_reasoning_model}")
    print(f"   - 适合任务: {[t.value for t in config.suitable_tasks]}")
    
    return manager


def example_basic_reasoning():
    """示例 1：基本推理"""
    print("\n" + "="*60)
    print("示例 1：基本推理")
    print("="*60)
    
    manager = get_model_manager()
    
    # 使用任务类型路由到推理模型
    llm = manager.create_llm(task_type=TaskType.REASONING)
    
    # 调用模型
    query = "为什么销售额在第三季度下降了15%？请分析可能的原因。"
    print(f"\n问题: {query}")
    print("\n正在思考...")
    
    # 注意：这里只是演示，实际调用需要真实的模型服务
    # response = llm.invoke(query)
    # print(f"\n思考过程: {response.additional_kwargs.get('thinking', '')}")
    # print(f"\n最终答案: {response.content}")
    
    print("（需要真实的 DeepSeek-R1 服务才能运行）")


def example_streaming_reasoning():
    """示例 2：流式推理"""
    print("\n" + "="*60)
    print("示例 2：流式推理（实时显示思考过程）")
    print("="*60)
    
    manager = get_model_manager()
    
    # 启用流式输出
    llm = manager.create_llm(
        task_type=TaskType.REASONING,
        streaming=True
    )
    
    query = "分析用户流失率上升的根本原因，并提供改进建议。"
    print(f"\n问题: {query}")
    print("\n思考过程:")
    
    # 注意：这里只是演示
    # for chunk in llm.stream(query):
    #     print(chunk.content, end="", flush=True)
    
    print("（需要真实的 DeepSeek-R1 服务才能运行）")


def example_hybrid_model_selection():
    """示例 3：混合模型选择（根据复杂度）"""
    print("\n" + "="*60)
    print("示例 3：混合模型选择")
    print("="*60)
    
    manager = get_model_manager()
    
    # 简单查询 - 使用普通模型
    simple_query = "显示销售额"
    print(f"\n简单查询: {simple_query}")
    try:
        llm_simple = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
        print(f"选择模型: 普通模型（快速）")
    except ValueError:
        print(f"选择模型: 未配置普通模型，使用默认模型")
    
    # 复杂查询 - 使用推理模型
    complex_query = "分析为什么北京地区的销售额在过去三个月持续下降，并预测未来趋势"
    print(f"\n复杂查询: {complex_query}")
    try:
        llm_complex = manager.create_llm(task_type=TaskType.REASONING)
        print(f"选择模型: 推理模型（深度思考）")
    except ValueError:
        print(f"选择模型: 未配置推理模型")


def example_extract_reasoning():
    """示例 4：提取思考过程和答案"""
    print("\n" + "="*60)
    print("示例 4：提取思考过程和答案")
    print("="*60)
    
    # 模拟推理模型的响应
    class MockResponse:
        def __init__(self):
            self.content = "销售额下降的主要原因是市场竞争加剧和季节性因素。"
            self.additional_kwargs = {
                'thinking': """
                让我分析一下销售额下降的可能原因：
                1. 市场因素：竞争对手推出了新产品
                2. 季节性：第三季度通常是淡季
                3. 内部因素：营销预算减少
                综合考虑，主要是市场竞争和季节性因素。
                """,
                'answer': "销售额下降的主要原因是市场竞争加剧和季节性因素。",
                'raw_content': "<think>思考过程...</think>\n最终答案..."
            }
    
    response = MockResponse()
    
    # 提取信息
    print("\n最终答案:")
    print(response.content)
    
    print("\n思考过程:")
    print(response.additional_kwargs.get('thinking', ''))
    
    print("\n原始输出:")
    print(response.additional_kwargs.get('raw_content', '')[:100] + "...")


def main():
    """主函数"""
    print("推理模型使用示例")
    print("="*60)
    
    # 配置推理模型
    try:
        manager = setup_reasoning_model()
    except Exception as e:
        print(f"⚠️  配置推理模型失败: {e}")
        print("提示：确保已设置环境变量或修改配置")
        return
    
    # 运行示例
    example_basic_reasoning()
    example_streaming_reasoning()
    example_hybrid_model_selection()
    example_extract_reasoning()
    
    print("\n" + "="*60)
    print("✅ 所有示例运行完成")
    print("="*60)
    print("\n提示：")
    print("1. 推理模型适合复杂分析任务")
    print("2. 普通模型适合简单快速任务")
    print("3. 根据任务复杂度选择合适的模型")
    print("4. 推理模型会输出思考过程，便于理解推理逻辑")


if __name__ == "__main__":
    main()
