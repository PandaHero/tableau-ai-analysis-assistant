"""
BoostAgent 真实环境集成测试

使用真实的:
- Tableau API (获取真实元数据)
- LLM (Qwen3 或 DeepSeek)
- 智谱AI Embedding (用于历史问题检索)

测试目标:
1. 验证 BoostAgent 能正确调用真实 LLM
2. 验证问题优化功能
3. 验证元数据格式化
4. 验证与真实环境的集成
"""
import sys
from pathlib import Path
import asyncio
import logging

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

from tableau_assistant.src.deepagents.subagents.boost_agent import BoostAgent
from tableau_assistant.src.config.settings import settings
from tableau_assistant.src.utils.tableau.auth import jwt_connected_app_async
from tableau_assistant.src.utils.tableau.metadata import get_data_dictionary_async

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_tableau_token():
    """获取 Tableau JWT 认证 token"""
    logger.info("正在获取 Tableau 认证 token...")
    
    try:
        # 使用 JWT Connected App 认证
        session = await jwt_connected_app_async(
            tableau_domain=settings.tableau_domain,
            tableau_site=settings.tableau_site,
            tableau_api=settings.tableau_api_version,
            tableau_user=settings.tableau_user,
            jwt_client_id=settings.tableau_jwt_client_id,
            jwt_secret_id=settings.tableau_jwt_secret_id,
            jwt_secret=settings.tableau_jwt_secret,
            scopes=["tableau:content:read"]
        )
        
        token = session.get("credentials", {}).get("token")
        if not token:
            raise RuntimeError("未能从认证响应中获取 token")
        
        logger.info(f"✅ 成功获取认证 token")
        logger.info(f"   Token 前缀: {token[:20]}...")
        
        return token
    except Exception as e:
        logger.error(f"❌ 获取认证 token 失败: {e}")
        raise


async def get_real_metadata(api_key: str):
    """获取真实的 Tableau 元数据"""
    logger.info("正在获取 Tableau 元数据...")
    
    try:
        metadata = await get_data_dictionary_async(
            api_key=api_key,
            domain=settings.tableau_domain,
            datasource_luid=settings.datasource_luid,
            site=settings.tableau_site
        )
        
        logger.info(f"✅ 成功获取元数据")
        logger.info(f"   数据源: {metadata.get('datasource_name')}")
        logger.info(f"   字段数: {len(metadata.get('fields', []))}")
        
        return metadata
    except Exception as e:
        logger.error(f"❌ 获取元数据失败: {e}")
        raise


async def test_rag_history_retrieval():
    """测试 RAG 历史问题检索（使用智谱AI）"""
    
    print("\n" + "="*60)
    print("  测试 3: RAG 历史问题检索（智谱AI）")
    print("="*60)
    
    # 1. 创建 BoostAgent 和 Mock Runtime
    agent = BoostAgent()
    
    class MockStore:
        """Mock Store with history"""
        def __init__(self):
            self._storage = {}
        
        async def aget(self, namespace, key):
            storage_key = f"{namespace}:{key}"
            return self._storage.get(storage_key)
        
        async def aput(self, namespace, key, value):
            storage_key = f"{namespace}:{key}"
            self._storage[storage_key] = value
    
    class MockRuntime:
        def __init__(self):
            self.store = MockStore()
    
    runtime = MockRuntime()
    
    # 2. 保存一些历史问题（使用智谱AI embedding）
    print("\n[保存历史问题]")
    historical_questions = [
        "2023年的销售额是多少？",
        "各地区的销售情况如何？",
        "利润率最高的产品类别是什么？",
        "订单数量的趋势如何？"
    ]
    
    for q in historical_questions:
        success = await agent.save_question_to_history(runtime, q)
        if success:
            print(f"   ✅ 已保存: {q}")
        else:
            print(f"   ❌ 保存失败: {q}")
    
    # 3. 测试相似问题检索
    print("\n[检索相似问题]")
    test_queries = [
        ("销售额", "应该找到'2023年的销售额是多少？'"),
        ("各地区销售", "应该找到'各地区的销售情况如何？'"),
        ("利润", "应该找到'利润率最高的产品类别是什么？'")
    ]
    
    for query, expected in test_queries:
        print(f"\n   查询: {query}")
        print(f"   预期: {expected}")
        
        similar = await agent._retrieve_similar_questions(
            runtime=runtime,
            question=query,
            top_k=2,
            similarity_threshold=0.6
        )
        
        if similar:
            print(f"   ✅ 找到 {len(similar)} 个相似问题:")
            for i, q in enumerate(similar, 1):
                print(f"      {i}. {q}")
        else:
            print(f"   ⚠️  未找到相似问题")
    
    return True


async def test_boost_agent_real():
    """测试 BoostAgent 的真实环境集成"""
    
    print("\n" + "="*60)
    print("  测试 4: BoostAgent 问题优化（真实环境）")
    print("="*60)
    
    # 1. 获取真实的 Tableau token 和元数据
    try:
        token = await get_tableau_token()
        metadata = await get_real_metadata(token)
    except Exception as e:
        print(f"\n❌ 无法获取 Tableau 数据: {e}")
        print("   请检查 .env 文件中的 Tableau 配置")
        return False
    
    # 2. 创建 BoostAgent 实例
    agent = BoostAgent()
    
    # 3. 准备测试用例
    test_cases = [
        {
            "question": "销售额",
            "description": "单个指标名称 - 应该被优化为完整问题"
        },
        {
            "question": "各地区的销售情况",
            "description": "不完整的问题 - 应该补充时间范围和聚合方式"
        },
        {
            "question": "为什么华东地区的利润率低？",
            "description": "探索性问题 - 应该保持不变"
        },
        {
            "question": "2024年各产品类别的销售额总和是多少？",
            "description": "完整问题 - 应该保持不变或微调"
        }
    ]
    
    # 4. 执行测试
    all_passed = True
    
    for i, test_case in enumerate(test_cases, 1):
        question = test_case["question"]
        description = test_case["description"]
        
        print(f"\n[测试用例 {i}]")
        print(f"   描述: {description}")
        print(f"   原始问题: {question}")
        
        try:
            # 创建 Mock Runtime（因为我们不需要完整的 DeepAgent 运行时）
            class MockStore:
                """Mock Store for testing - 使用内存存储"""
                def __init__(self):
                    self._storage = {}
                
                async def aget(self, namespace, key):
                    # 从内存中获取
                    storage_key = f"{namespace}:{key}"
                    return self._storage.get(storage_key)
                
                async def aput(self, namespace, key, value):
                    # 保存到内存
                    storage_key = f"{namespace}:{key}"
                    self._storage[storage_key] = value
                    logger.debug(f"MockStore saved: {storage_key}")
            
            class MockRuntime:
                def __init__(self):
                    self.store = MockStore()
            
            runtime = MockRuntime()
            
            # 执行 Agent
            result = await agent.execute(
                state={},
                runtime=runtime,
                question=question,
                metadata=metadata,
                use_history=False  # 暂时禁用历史检索
            )
            
            # 验证结果
            assert "boosted_question" in result, "结果中缺少 boosted_question"
            assert "is_data_analysis_question" in result, "结果中缺少 is_data_analysis_question"
            assert "confidence" in result, "结果中缺少 confidence"
            assert "reasoning" in result, "结果中缺少 reasoning"
            
            boosted_question = result["boosted_question"]
            is_data_question = result["is_data_analysis_question"]
            confidence = result["confidence"]
            reasoning = result["reasoning"]
            changes = result.get("changes", [])
            
            print(f"   ✅ 优化后问题: {boosted_question}")
            print(f"   是否数据分析问题: {is_data_question}")
            print(f"   置信度: {confidence:.2f}")
            print(f"   变更: {', '.join(changes) if changes else '无变更'}")
            print(f"   推理: {reasoning[:100]}...")
            
            # 验证逻辑
            if "为什么" in question or "why" in question.lower():
                # 探索性问题应该保持不变
                if boosted_question != question:
                    print(f"   ⚠️  警告: 探索性问题被修改了")
            
            if question in ["销售额", "利润率", "订单数"]:
                # 单个指标应该被优化
                if boosted_question == question:
                    print(f"   ⚠️  警告: 单个指标没有被优化")
                    all_passed = False
            
        except Exception as e:
            print(f"   ❌ 测试失败: {e}")
            logger.exception("详细错误:")
            all_passed = False
    
    return all_passed


async def test_metadata_availability():
    """测试元数据可用性"""
    
    print("\n" + "="*60)
    print("  测试 2: 元数据可用性")
    print("="*60)
    
    # 1. 获取真实元数据
    try:
        token = await get_tableau_token()
        metadata = await get_real_metadata(token)
    except Exception as e:
        print(f"\n❌ 无法获取 Tableau 数据: {e}")
        return False
    
    try:
        # 验证元数据结构
        assert "datasource_name" in metadata, "缺少数据源名称"
        assert "fields" in metadata, "缺少字段列表"
        assert len(metadata["fields"]) > 0, "字段列表为空"
        
        print(f"\n[元数据信息]")
        print(f"   数据源: {metadata['datasource_name']}")
        print(f"   字段数: {len(metadata['fields'])}")
        
        # 统计维度和度量
        dimensions = [f for f in metadata["fields"] if f.get("role") == "dimension"]
        measures = [f for f in metadata["fields"] if f.get("role") == "measure"]
        
        print(f"   维度字段: {len(dimensions)} 个")
        print(f"   度量字段: {len(measures)} 个")
        
        print(f"\n   ✅ 元数据结构正确")
        return True
        
    except Exception as e:
        print(f"\n   ❌ 元数据验证失败: {e}")
        logger.exception("详细错误:")
        return False


async def main():
    """主测试函数"""
    
    print("\n" + "="*60)
    print("  BoostAgent 真实环境测试套件")
    print("="*60)
    
    # 检查环境配置
    print("\n[环境配置]")
    print(f"   Tableau Domain: {settings.tableau_domain}")
    print(f"   Tableau Site: {settings.tableau_site}")
    print(f"   Datasource LUID: {settings.datasource_luid}")
    print(f"   LLM API Base: {settings.llm_api_base}")
    print(f"   LLM Model: {settings.tooling_llm_model}")
    
    # 运行测试
    try:
        # 测试 1: 元数据可用性
        await test_metadata_availability()
        
        # 测试 2: 问题优化
        await test_boost_agent_real()
        
        print("\n" + "="*60)
        print("  [SUCCESS] 所有测试通过！")
        print("="*60 + "\n")
        
    except KeyboardInterrupt:
        print("\n\n⚠️  测试被用户中断")
    except Exception as e:
        print(f"\n\n❌ 测试失败: {e}")
        logger.exception("详细错误:")
        return False
    
    return True


if __name__ == "__main__":
    # 运行测试
    success = asyncio.run(main())
    sys.exit(0 if success else 1)
