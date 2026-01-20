"""
测试智谱 AI Embedding 配置
"""
import sys
import logging
from pathlib import Path

# 设置日志级别为 DEBUG
logging.basicConfig(level=logging.DEBUG, format='%(name)s - %(levelname)s - %(message)s')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent
sys.path.insert(0, str(project_root))

from src.infra.ai import ModelManager, get_embeddings


def test_zhipu_embedding_from_yaml():
    """测试从 YAML 加载智谱 Embedding 配置"""
    print("\n" + "="*60)
    print("测试 1: 从 YAML 加载智谱 Embedding 配置")
    print("="*60)
    
    # 初始化 ModelManager（会自动加载 YAML 配置）
    manager = ModelManager()
    
    # 列出所有模型
    all_models = manager.list()
    print(f"\n已加载的模型数量: {len(all_models)}")
    for model in all_models:
        print(f"  - {model.id} ({model.model_type.value}): {model.name}")
    
    # 获取智谱 embedding 模型
    try:
        embedding = manager.create_embedding(model_id="zhipu-embedding")
        
        print("\n[OK] 成功加载智谱 Embedding 模型")
        print(f"  模型类型: {type(embedding).__name__}")
        
        # 测试 embedding
        test_text = "这是一个测试文本"
        print(f"\n测试文本: {test_text}")
        
        try:
            result = embedding.embed_query(test_text)
            print(f"[OK] Embedding 成功")
            print(f"  向量维度: {len(result)}")
            print(f"  前5个值: {result[:5]}")
        except Exception as e:
            print(f"[FAIL] Embedding 失败: {e}")
            import traceback
            traceback.print_exc()
    except ValueError as e:
        print(f"\n[FAIL] 未找到智谱 Embedding 模型: {e}")


def test_zhipu_embedding_wrapper():
    """测试使用 get_embeddings() 便捷函数"""
    print("\n" + "="*60)
    print("测试 2: 使用 get_embeddings() 便捷函数")
    print("="*60)
    
    try:
        # 使用便捷函数获取 embedding
        embedding = get_embeddings("zhipu-embedding")
        print("[OK] 成功获取智谱 Embedding 模型")
        
        # 测试批量 embedding
        test_texts = [
            "数据分析",
            "商业智能",
            "可视化报表"
        ]
        print(f"\n测试文本列表: {test_texts}")
        
        results = embedding.embed_documents(test_texts)
        print(f"[OK] 批量 Embedding 成功")
        print(f"  文本数量: {len(results)}")
        print(f"  向量维度: {len(results[0])}")
        
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")


def test_default_embedding():
    """测试获取默认 Embedding 模型"""
    print("\n" + "="*60)
    print("测试 3: 获取默认 Embedding 模型")
    print("="*60)
    
    try:
        # 不指定 model_id，使用默认模型
        embedding = get_embeddings()
        print("[OK] 成功获取默认 Embedding 模型")
        
        # 测试
        test_text = "默认模型测试"
        result = embedding.embed_query(test_text)
        print(f"[OK] Embedding 成功")
        print(f"  向量维度: {len(result)}")
        
    except Exception as e:
        print(f"[FAIL] 测试失败: {e}")


if __name__ == "__main__":
    print("\n智谱 AI Embedding 配置测试")
    print("="*60)
    
    test_zhipu_embedding_from_yaml()
    test_zhipu_embedding_wrapper()
    test_default_embedding()
    
    print("\n" + "="*60)
    print("测试完成！")
    print("="*60)
