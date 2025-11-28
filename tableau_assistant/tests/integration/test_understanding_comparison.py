"""
对比测试：新旧 UnderstandingAgent

对比：
- 旧版: tableau_assistant.src.agents.understanding_agent (BaseVizQLAgent)
- 新版: tableau_assistant.src.deepagents.subagents.understanding_agent (BaseSubAgent)

目的：验证迁移后的功能是否一致
"""
import sys
from pathlib import Path
import asyncio
import logging

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
if str(project_root) not in sys.path:
    sys.path.insert(0, str(project_root))

# 导入旧版 Agent
from tableau_assistant.src.agents.understanding_agent import understanding_agent as old_understanding_agent

# 导入新版 Agent
from tableau_assistant.src.deepagents.subagents.understanding_agent import UnderstandingAgent as NewUnderstandingAgent

from tableau_assistant.src.config.settings import settings
from tableau_assistant.src.utils.tableau.auth import jwt_connected_app_async
from tableau_assistant.src.utils.tableau.metadata import get_data_dictionary_async

# 配置日志
logging.basicConfig(
    level=logging.WARNING,  # 减少日志输出
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


async def get_tableau_metadata():
    """获取 Tableau 元数据"""
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
        
        # 获取元数据
        metadata = await get_data_dictionary_async(
            api_key=token,
            domain=settings.tableau_domain,
            datasource_luid=settings.datasource_luid,
            site=settings.tableau_site
        )
        
        return metadata
        
    except Exception as e:
        logger.error(f"获取元数据失败: {e}")
        raise


async def test_understanding_comparison():
    """对比测试新旧 UnderstandingAgent"""
    
    print("\n" + "="*80)
    print("  新旧 UnderstandingAgent 对比测试")
    print("="*80)
    
    # 1. 获取元数据
    print("\n[1/3] 获取 Tableau 元数据...")
    metadata = await get_tableau_metadata()
    print(f"✓ 元数据获取完成 (字段数: {len(metadata.get('fields', []))})")
    
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
    
    # 3. 测试用例（只测试一个）
    test_cases = [
        "最近一个月各省份的销售额"
    ]
    
    # 4. 执行对比测试
    for i, question in enumerate(test_cases, 1):
        print(f"\n{'='*80}")
        print(f"测试用例 {i}/{len(test_cases)}: {question}")
        print(f"{'='*80}")
        
        # 测试旧版 Agent
        print(f"\n[旧版 UnderstandingAgent]")
        try:
            old_result = await old_understanding_agent.execute(
                state={"question": question},
                runtime=runtime,
                metadata=metadata,
                use_metadata=True
            )
            
            old_understanding = old_result.get("understanding")
            if old_understanding:
                print(f"✓ 理解完成")
                print(f"  问题类型: {old_understanding.question_type}")
                print(f"  复杂度: {old_understanding.complexity}")
                print(f"  子问题数: {len(old_understanding.sub_questions)}")
                
                if old_understanding.sub_questions:
                    first_sub = old_understanding.sub_questions[0]
                    print(f"  第一个子问题:")
                    print(f"    文本: {first_sub.text}")
                    if hasattr(first_sub, 'mentioned_dimensions') and first_sub.mentioned_dimensions:
                        dims = ', '.join(first_sub.mentioned_dimensions[:5])
                        print(f"    维度 ({len(first_sub.mentioned_dimensions)}): {dims}")
                    if hasattr(first_sub, 'mentioned_measures') and first_sub.mentioned_measures:
                        measures = ', '.join(first_sub.mentioned_measures[:5])
                        print(f"    度量 ({len(first_sub.mentioned_measures)}): {measures}")
                    if hasattr(first_sub, 'time_range') and first_sub.time_range:
                        tr = first_sub.time_range
                        print(f"    时间: type={tr.type}, relative={tr.relative_type}, period={tr.period_type}")
            else:
                print(f"✗ 理解失败")
                
        except Exception as e:
            print(f"✗ 执行失败: {e}")
        
        # 测试新版 Agent
        print(f"\n[新版 UnderstandingAgent]")
        try:
            new_agent = NewUnderstandingAgent()
            new_result = await new_agent.execute(
                state={},
                runtime=runtime,
                question=question,
                metadata=metadata
            )
            
            new_understanding = new_result.get("understanding")
            if new_understanding:
                print(f"✓ 理解完成")
                print(f"  问题类型: {new_understanding.question_type}")
                print(f"  复杂度: {new_understanding.complexity}")
                print(f"  子问题数: {len(new_understanding.sub_questions)}")
                
                if new_understanding.sub_questions:
                    first_sub = new_understanding.sub_questions[0]
                    print(f"  第一个子问题:")
                    print(f"    文本: {first_sub.text}")
                    if hasattr(first_sub, 'mentioned_dimensions') and first_sub.mentioned_dimensions:
                        dims = ', '.join(first_sub.mentioned_dimensions[:5])
                        print(f"    维度 ({len(first_sub.mentioned_dimensions)}): {dims}")
                    if hasattr(first_sub, 'mentioned_measures') and first_sub.mentioned_measures:
                        measures = ', '.join(first_sub.mentioned_measures[:5])
                        print(f"    度量 ({len(first_sub.mentioned_measures)}): {measures}")
                    if hasattr(first_sub, 'time_range') and first_sub.time_range:
                        tr = first_sub.time_range
                        print(f"    时间: type={tr.type}, relative={tr.relative_type}, period={tr.period_type}")
            else:
                print(f"✗ 理解失败")
                
        except Exception as e:
            print(f"✗ 执行失败: {e}")
            import traceback
            traceback.print_exc()
        
        # 对比结果
        print(f"\n[对比分析]")
        if old_understanding and new_understanding:
            # 对比问题类型
            if old_understanding.question_type == new_understanding.question_type:
                print(f"  ✓ 问题类型一致")
            else:
                print(f"  ✗ 问题类型不一致")
                print(f"    旧版: {old_understanding.question_type}")
                print(f"    新版: {new_understanding.question_type}")
            
            # 对比复杂度
            if old_understanding.complexity == new_understanding.complexity:
                print(f"  ✓ 复杂度一致")
            else:
                print(f"  ✗ 复杂度不一致")
                print(f"    旧版: {old_understanding.complexity}")
                print(f"    新版: {new_understanding.complexity}")
            
            # 对比维度
            if old_understanding.sub_questions and new_understanding.sub_questions:
                old_dims = set(old_understanding.sub_questions[0].mentioned_dimensions or [])
                new_dims = set(new_understanding.sub_questions[0].mentioned_dimensions or [])
                
                if old_dims == new_dims:
                    print(f"  ✓ 维度识别一致")
                else:
                    print(f"  ✗ 维度识别不一致")
                    only_old = old_dims - new_dims
                    only_new = new_dims - old_dims
                    if only_old:
                        print(f"    仅旧版有: {', '.join(list(only_old)[:3])}")
                    if only_new:
                        print(f"    仅新版有: {', '.join(list(only_new)[:3])}")
                
                # 对比度量
                old_measures = set(old_understanding.sub_questions[0].mentioned_measures or [])
                new_measures = set(new_understanding.sub_questions[0].mentioned_measures or [])
                
                if old_measures == new_measures:
                    print(f"  ✓ 度量识别一致")
                else:
                    print(f"  ✗ 度量识别不一致")
                    only_old = old_measures - new_measures
                    only_new = new_measures - old_measures
                    if only_old:
                        print(f"    仅旧版有: {', '.join(list(only_old)[:3])}")
                    if only_new:
                        print(f"    仅新版有: {', '.join(list(only_new)[:3])}")
    
    print("\n" + "="*80)
    print("  对比测试完成")
    print("="*80)


async def main():
    """主函数"""
    print("\n" + "="*80)
    print("  新旧 UnderstandingAgent 对比测试套件")
    print("="*80)
    
    # 显示环境配置
    print("\n[环境配置]")
    print(f"   Tableau Domain: {settings.tableau_domain}")
    print(f"   Datasource LUID: {settings.datasource_luid}")
    import os
    print(f"   LLM Model: {os.getenv('TOOLING_LLM_MODEL', 'qwen3')}")
    
    # 运行测试
    await test_understanding_comparison()


if __name__ == "__main__":
    asyncio.run(main())
