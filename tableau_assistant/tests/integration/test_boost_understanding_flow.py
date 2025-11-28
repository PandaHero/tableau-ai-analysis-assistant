"""
BoostAgent → UnderstandingAgent 流程测试

测试完整的问题处理流程：
1. BoostAgent 优化问题
2. UnderstandingAgent 理解优化后的问题

使用真实环境：
- 真实的 Tableau 元数据
- 真实的 LLM (Qwen3)
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
from tableau_assistant.src.deepagents.subagents.understanding_agent import UnderstandingAgent
from tableau_assistant.src.config.settings import settings
from tableau_assistant.src.utils.tableau.auth import jwt_connected_app_async
from tableau_assistant.src.utils.tableau.metadata import get_data_dictionary_async

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_tableau_metadata():
    """获取 Tableau 元数据"""
    logger.info("正在获取 Tableau 元数据...")
    
    try:
        # 获取认证 token
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
        
        # 获取元数据
        metadata = await get_data_dictionary_async(
            api_key=token,
            domain=settings.tableau_domain,
            datasource_luid=settings.datasource_luid,
            site=settings.tableau_site
        )
        
        logger.info(f"✅ 成功获取元数据")
        logger.info(f"   数据源: {metadata.get('datasource_name', 'Unknown')}")
        logger.info(f"   字段数: {len(metadata.get('fields', []))}")
        
        return metadata
        
    except Exception as e:
        logger.error(f"❌ 获取元数据失败: {e}")
        raise


async def test_boost_understanding_flow():
    """测试 Boost → Understanding 完整流程"""
    
    print("\n" + "="*60)
    print("  Boost → Understanding 流程测试")
    print("="*60)
    
    # 1. 获取元数据
    print("\n[1/4] 获取 Tableau 元数据...")
    metadata = await get_tableau_metadata()
    
    # 2. 创建 Mock Runtime
    class MockStore:
        async def aget(self, namespace, key):
            return None
        
        async def aput(self, namespace, key, value):
            pass
    
    class MockContext:
        user_id = "test_user"
        session_id = "test_session"
    
    class MockRuntime:
        def __init__(self):
            self.store = MockStore()
            self.context = MockContext()
    
    runtime = MockRuntime()
    
    # 3. 测试用例
    test_cases = [
        {
            "name": "简单查询",
            "question": "销售额"
        },
        {
            "name": "带时间的查询",
            "question": "最近一个月各省份的销售额"
        },
        {
            "name": "复杂对比查询",
            "question": "对比今年和去年各门店的销售额"
        }
    ]
    
    # 4. 执行测试
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"测试用例 {i}/{len(test_cases)}: {test_case['name']}")
        print(f"{'='*60}")
        print(f"原始问题: {test_case['question']}")
        
        try:
            # Step 1: BoostAgent 优化问题
            print(f"\n[2/4] BoostAgent 优化问题...")
            boost_agent = BoostAgent()
            
            boost_result = await boost_agent.execute(
                state={},
                runtime=runtime,
                question=test_case["question"],
                metadata=metadata,
                use_history=False  # 简化测试，不使用历史
            )
            
            boost = boost_result.get("boost_result")
            if boost:
                print(f"✅ 问题优化完成")
                print(f"   优化后问题: {boost.boosted_question}")
                print(f"   是否数据分析问题: {boost.is_data_analysis_question}")
                print(f"   置信度: {boost.confidence:.2f}")
                if boost.changes:
                    print(f"   变更: {', '.join(boost.changes[:3])}")
            else:
                print(f"❌ 问题优化失败")
                continue
            
            # Step 2: UnderstandingAgent 理解问题（不需要 metadata，纯语义理解）
            print(f"\n[3/4] UnderstandingAgent 理解问题...")
            understanding_agent = UnderstandingAgent()
            
            understanding_result = await understanding_agent.execute(
                state={},
                runtime=runtime,
                question=boost.boosted_question  # 使用优化后的问题，不传递 metadata
            )
            
            understanding = understanding_result.get("understanding")
            if understanding:
                print(f"✅ 问题理解完成")
                print(f"   问题类型: {understanding.question_type}")
                print(f"   复杂度: {understanding.complexity}")
                print(f"   是否有效: {understanding.is_valid_question}")
                print(f"   需要拆分: {understanding_result.get('needs_split', False)}")
                print(f"   子问题数量: {len(understanding.sub_questions)}")
                
                # 显示第一个子问题的详细信息
                if understanding.sub_questions:
                    first_sub = understanding.sub_questions[0]
                    print(f"\n   第一个子问题:")
                    print(f"      文本: {first_sub.text}")
                    if hasattr(first_sub, 'mentioned_dimensions') and first_sub.mentioned_dimensions:
                        print(f"      维度: {', '.join(first_sub.mentioned_dimensions[:3])}")
                    if hasattr(first_sub, 'mentioned_measures') and first_sub.mentioned_measures:
                        print(f"      度量: {', '.join(first_sub.mentioned_measures[:3])}")
                    if hasattr(first_sub, 'time_range') and first_sub.time_range:
                        print(f"      时间范围: {first_sub.time_range}")
            else:
                print(f"❌ 问题理解失败")
            
            print(f"\n[4/4] 流程完成 ✓")
            
        except Exception as e:
            print(f"❌ 测试失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n" + "="*60)
    print("  测试完成")
    print("="*60)


async def main():
    """主函数"""
    print("\n" + "="*60)
    print("  Boost → Understanding 流程测试套件")
    print("="*60)
    
    # 显示环境配置
    print("\n[环境配置]")
    print(f"   Tableau Domain: {settings.tableau_domain}")
    print(f"   Tableau Site: {settings.tableau_site}")
    print(f"   Datasource LUID: {settings.datasource_luid}")
    print(f"   LLM API Base: {settings.llm_api_base}")
    import os
    print(f"   LLM Model: {os.getenv('TOOLING_LLM_MODEL', 'qwen3')}")
    
    # 运行测试
    await test_boost_understanding_flow()


if __name__ == "__main__":
    asyncio.run(main())
