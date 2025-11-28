"""
UnderstandingAgent 真实环境集成测试

使用真实的:
- Tableau API (获取真实元数据)
- LLM (Claude 或其他主模型)

测试目标:
1. 验证 UnderstandingAgent 能正确调用真实 LLM
2. 验证问题理解功能
3. 验证问题拆分功能
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
        logger.info(f"   Token 前缀: {token[:20]}...")
        
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


async def test_understanding_agent_real():
    """测试 UnderstandingAgent 的真实环境集成"""
    
    print("\n" + "="*60)
    print("  UnderstandingAgent 真实环境测试")
    print("="*60)
    
    # 1. 获取元数据
    print("\n[1/3] 获取 Tableau 元数据...")
    metadata = await get_tableau_metadata()
    
    # 2. 创建 UnderstandingAgent 实例
    print("\n[2/3] 创建 UnderstandingAgent...")
    agent = UnderstandingAgent()
    
    # 3. 准备测试用例
    test_cases = [
        {
            "name": "简单查询",
            "question": "2024年各地区的销售额",
            "expected_type": ["对比"],
            "expected_complexity": "Simple"
        },
        {
            "name": "排名查询",
            "question": "显示各产品类别的销售额和利润，按销售额降序排列",
            "expected_type": ["对比", "排名"],
            "expected_complexity": "Simple"
        },
        {
            "name": "复杂对比查询",
            "question": "对比今年春节期间每天和去年春节期间每天各门店的销售额",
            "expected_type": ["对比", "趋势"],
            "expected_complexity": "Complex"
        },
        {
            "name": "探索性查询",
            "question": "哪个门店的利润最高？为什么？",
            "expected_type": ["排名", "诊断"],
            "expected_complexity": "Complex",
            "expected_exploration": True
        }
    ]
    
    # 4. Mock Runtime（简化测试）
    class MockStore:
        async def aget(self, namespace, key):
            return None
        
        async def aput(self, namespace, key, value):
            pass
    
    class MockRuntime:
        def __init__(self):
            self.store = MockStore()
    
    runtime = MockRuntime()
    
    # 5. 执行测试
    print("\n[3/3] 执行测试用例...")
    
    for i, test_case in enumerate(test_cases, 1):
        print(f"\n{'='*60}")
        print(f"测试用例 {i}/{len(test_cases)}: {test_case['name']}")
        print(f"{'='*60}")
        print(f"问题: {test_case['question']}")
        
        try:
            # 执行 Agent
            result = await agent.execute(
                state={},
                runtime=runtime,
                question=test_case["question"],
                metadata=metadata
            )
            
            understanding = result.get("understanding")
            
            if understanding:
                print(f"\n✅ 理解成功")
                print(f"   问题类型: {understanding.question_type}")
                print(f"   复杂度: {understanding.complexity}")
                print(f"   需要拆分: {understanding.needs_split}")
                
                if understanding.mentioned_dimensions:
                    print(f"   提及的维度: {', '.join(understanding.mentioned_dimensions)}")
                
                if understanding.mentioned_measures:
                    print(f"   提及的度量: {', '.join(understanding.mentioned_measures)}")
                
                if understanding.time_range:
                    print(f"   时间范围: {understanding.time_range}")
                
                if understanding.needs_exploration:
                    print(f"   需要探索: {understanding.needs_exploration}")
                
                if understanding.needs_split and understanding.sub_questions:
                    print(f"   子问题数量: {len(understanding.sub_questions)}")
                    for j, sub_q in enumerate(understanding.sub_questions, 1):
                        print(f"      {j}. {sub_q.question}")
                
                print(f"   置信度: {understanding.confidence:.2f}")
                print(f"   推理: {understanding.reasoning}")
                
                # 验证预期结果
                if "expected_type" in test_case:
                    type_match = any(t in understanding.question_type for t in test_case["expected_type"])
                    if type_match:
                        print(f"   ✓ 问题类型匹配预期")
                    else:
                        print(f"   ⚠ 问题类型不匹配预期: 期望 {test_case['expected_type']}, 实际 {understanding.question_type}")
                
                if "expected_complexity" in test_case:
                    if understanding.complexity == test_case["expected_complexity"]:
                        print(f"   ✓ 复杂度匹配预期")
                    else:
                        print(f"   ⚠ 复杂度不匹配预期: 期望 {test_case['expected_complexity']}, 实际 {understanding.complexity}")
                
                if "expected_exploration" in test_case:
                    if understanding.needs_exploration == test_case["expected_exploration"]:
                        print(f"   ✓ 探索性标记匹配预期")
                    else:
                        print(f"   ⚠ 探索性标记不匹配预期")
            else:
                print(f"❌ 理解失败: 没有返回 understanding 结果")
                
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
    print("  UnderstandingAgent 真实环境测试套件")
    print("="*60)
    
    # 显示环境配置
    print("\n[环境配置]")
    print(f"   Tableau Domain: {settings.tableau_domain}")
    print(f"   Tableau Site: {settings.tableau_site}")
    print(f"   Datasource LUID: {settings.datasource_luid}")
    print(f"   LLM API Base: {settings.llm_api_base}")
    import os
    print(f"   LLM Model: {os.getenv('MAIN_LLM_MODEL', 'claude-3-5-sonnet-20241022')}")
    
    # 运行测试
    await test_understanding_agent_real()


if __name__ == "__main__":
    asyncio.run(main())
