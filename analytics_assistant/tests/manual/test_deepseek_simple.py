# -*- coding: utf-8 -*-
"""
DeepSeek API 简单测试

验证 ModelManager 与 DeepSeek API 的集成。
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.infra.ai import (
    get_model_manager,
    ModelCreateRequest,
    ModelType,
    TaskType,
)


def main():
    print("=" * 60)
    print("DeepSeek API 测试")
    print("=" * 60)
    
    manager = get_model_manager()
    
    # 测试 1: 创建 DeepSeek Chat 配置
    print("\n[1] 创建 DeepSeek Chat 配置...")
    chat_request = ModelCreateRequest(
        name="DeepSeek Chat V3.2",
        model_type=ModelType.LLM,
        provider="deepseek",
        api_base="https://api.deepseek.com",
        model_name="deepseek-chat",
        api_key="sk-9da1f26d50e1406394063aaa795421f0",
        openai_compatible=True,
        temperature=0.7,
        supports_streaming=True,
        supports_json_mode=True,
        suitable_tasks=[
            TaskType.SEMANTIC_PARSING,
            TaskType.FIELD_MAPPING,
            TaskType.INSIGHT_GENERATION,
        ],
        priority=10,
        is_default=True,
    )
    
    try:
        chat_config = manager.create(chat_request)
        print(f"✓ 配置创建成功: {chat_config.id}")
        print(f"  - 名称: {chat_config.name}")
        print(f"  - 模型: {chat_config.model_name}")
        print(f"  - API: {chat_config.api_base}")
    except ValueError as e:
        if "already exists" in str(e):
            print(f"✓ 配置已存在，跳过创建")
            chat_config = manager.get("deepseek-deepseek-chat")
        else:
            raise
    
    # 测试 2: 创建 DeepSeek Reasoner 配置（推理模型）
    print("\n[2] 创建 DeepSeek Reasoner 配置（推理模型）...")
    reasoner_request = ModelCreateRequest(
        name="DeepSeek Reasoner V3.2",
        model_type=ModelType.LLM,
        provider="deepseek",
        api_base="https://api.deepseek.com",
        model_name="deepseek-reasoner",
        api_key="sk-9da1f26d50e1406394063aaa795421f0",
        openai_compatible=True,
        temperature=0.7,
        supports_streaming=True,
        is_reasoning_model=True,  # 标记为推理模型
        suitable_tasks=[
            TaskType.REASONING,
            TaskType.INSIGHT_GENERATION,
        ],
        priority=15,
    )
    
    try:
        reasoner_config = manager.create(reasoner_request)
        print(f"✓ 配置创建成功: {reasoner_config.id}")
        print(f"  - 名称: {reasoner_config.name}")
        print(f"  - 模型: {reasoner_config.model_name}")
        print(f"  - 推理模型: {reasoner_config.is_reasoning_model}")
    except ValueError as e:
        if "already exists" in str(e):
            print(f"✓ 配置已存在，跳过创建")
            reasoner_config = manager.get("deepseek-deepseek-reasoner")
        else:
            raise
    
    # 测试 3: 基本调用
    print("\n[3] 测试基本调用...")
    try:
        llm = manager.create_llm(model_id="deepseek-deepseek-chat")
        response = llm.invoke("你好，请用一句话介绍你自己")
        print(f"✓ API 调用成功")
        print(f"响应: {response.content}")
    except Exception as e:
        print(f"✗ API 调用失败: {e}")
        import traceback
        traceback.print_exc()
        return False
    
    # 测试 4: JSON Mode
    print("\n[4] 测试 JSON Mode...")
    try:
        llm = manager.create_llm(
            model_id="deepseek-deepseek-chat",
            enable_json_mode=True
        )
        
        prompt = """请返回一个 JSON 对象，包含：
        {"name": "你的名字", "version": "你的版本", "type": "模型类型"}
        只返回 JSON，不要其他文字。"""
        
        response = llm.invoke(prompt)
        print(f"✓ JSON Mode 调用成功")
        print(f"响应: {response.content}")
        
        # 验证 JSON
        import json
        json_data = json.loads(response.content)
        print(f"✓ JSON 解析成功: {json_data}")
    except Exception as e:
        print(f"✗ JSON Mode 调用失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试 5: 流式输出
    print("\n[5] 测试流式输出...")
    try:
        llm = manager.create_llm(
            model_id="deepseek-deepseek-chat",
            streaming=True
        )
        
        print("响应（流式）: ", end="", flush=True)
        for chunk in llm.stream("请用一句话介绍人工智能"):
            print(chunk.content, end="", flush=True)
        print()  # 换行
        print(f"✓ 流式调用成功")
    except Exception as e:
        print(f"\n✗ 流式调用失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试 6: 任务路由
    print("\n[6] 测试任务路由...")
    try:
        llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
        response = llm.invoke("什么是语义解析？")
        print(f"✓ 任务路由成功")
        print(f"响应: {response.content[:100]}...")
    except Exception as e:
        print(f"✗ 任务路由失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 测试 7: 推理模型
    print("\n[7] 测试推理模型（DeepSeek Reasoner）...")
    try:
        llm = manager.create_llm(model_id="deepseek-deepseek-reasoner")
        response = llm.invoke("为什么天空是蓝色的？请简短回答。")
        print(f"✓ 推理模型调用成功")
        print(f"响应: {response.content}")
        
        # 检查是否有思考过程
        if hasattr(llm, '_is_reasoning_model') and llm._is_reasoning_model:
            print(f"✓ 推理模型标记正确")
    except Exception as e:
        print(f"✗ 推理模型调用失败: {e}")
        import traceback
        traceback.print_exc()
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except KeyboardInterrupt:
        print("\n\n测试被用户中断")
        sys.exit(1)
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
