# -*- coding: utf-8 -*-
"""
YAML 配置加载测试

验证 ModelManager 从 YAML 文件加载配置的功能。
"""
import sys
from pathlib import Path

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.infra.ai import get_model_manager, ModelType


def main():
    print("=" * 60)
    print("YAML 配置加载测试")
    print("=" * 60)
    
    # 获取 ModelManager 实例（会自动加载 YAML 配置）
    manager = get_model_manager()
    
    # 列出所有配置
    print("\n[1] 列出所有模型配置...")
    all_configs = manager.list()
    print(f"总计: {len(all_configs)} 个模型")
    
    for config in all_configs:
        print(f"\n  - ID: {config.id}")
        print(f"    名称: {config.name}")
        print(f"    类型: {config.model_type.value}")
        print(f"    提供商: {config.provider}")
        print(f"    模型: {config.model_name}")
        print(f"    状态: {config.status.value}")
        print(f"    默认: {config.is_default}")
        print(f"    推理模型: {config.is_reasoning_model}")
        print(f"    优先级: {config.priority}")
    
    # 列出 LLM 模型
    print("\n[2] 列出 LLM 模型...")
    llm_configs = manager.list(model_type=ModelType.LLM)
    print(f"LLM 模型数量: {len(llm_configs)}")
    
    # 列出 Embedding 模型
    print("\n[3] 列出 Embedding 模型...")
    embedding_configs = manager.list(model_type=ModelType.EMBEDDING)
    print(f"Embedding 模型数量: {len(embedding_configs)}")
    
    # 获取默认 LLM
    print("\n[4] 获取默认 LLM...")
    default_llm = manager.get_default(ModelType.LLM)
    if default_llm:
        print(f"默认 LLM: {default_llm.name} ({default_llm.id})")
    else:
        print("未设置默认 LLM")
    
    # 测试 DeepSeek Chat
    print("\n[5] 测试 DeepSeek Chat...")
    deepseek_chat = manager.get("deepseek-chat")
    if deepseek_chat:
        print(f"✓ 找到配置: {deepseek_chat.name}")
        print(f"  API: {deepseek_chat.api_base}")
        print(f"  模型: {deepseek_chat.model_name}")
        print(f"  支持 JSON Mode: {deepseek_chat.supports_json_mode}")
        print(f"  支持流式: {deepseek_chat.supports_streaming}")
        
        # 尝试创建 LLM 实例
        try:
            llm = manager.create_llm(model_id="deepseek-chat")
            print(f"✓ LLM 实例创建成功")
            
            # 测试调用
            response = llm.invoke("你好")
            print(f"✓ API 调用成功")
            print(f"  响应: {response.content[:50]}...")
        except Exception as e:
            print(f"✗ 测试失败: {e}")
    else:
        print("✗ 未找到 DeepSeek Chat 配置")
    
    # 测试 DeepSeek Reasoner
    print("\n[6] 测试 DeepSeek Reasoner（推理模型）...")
    deepseek_reasoner = manager.get("deepseek-reasoner")
    if deepseek_reasoner:
        print(f"✓ 找到配置: {deepseek_reasoner.name}")
        print(f"  推理模型: {deepseek_reasoner.is_reasoning_model}")
        print(f"  优先级: {deepseek_reasoner.priority}")
        
        # 尝试创建 LLM 实例
        try:
            llm = manager.create_llm(model_id="deepseek-reasoner")
            print(f"✓ LLM 实例创建成功")
            
            # 验证推理模型标记
            if hasattr(llm, '_is_reasoning_model'):
                print(f"✓ 推理模型标记正确: {llm._is_reasoning_model}")
        except Exception as e:
            print(f"✗ 测试失败: {e}")
    else:
        print("✗ 未找到 DeepSeek Reasoner 配置")
    
    print("\n" + "=" * 60)
    print("测试完成！")
    print("=" * 60)
    
    return True


if __name__ == "__main__":
    try:
        success = main()
        sys.exit(0 if success else 1)
    except Exception as e:
        print(f"\n\n测试失败: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)
