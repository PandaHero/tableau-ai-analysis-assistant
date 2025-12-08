"""
端到端工作流测试

测试完整的工作流程：
1. 维度层级推断（Dimension Hierarchy Agent）- Token 级流式输出
2. 问题理解（Understanding Agent）- 带工具调用
3. 字段映射（Field Mapper）- RAG + LLM

所有测试都使用真实的 Tableau 元数据和 LLM 模型。

使用方法：
    # 运行完整端到端测试
    python tableau_assistant/tests/integration/test_e2e_workflow.py
    
    # 指定问题
    python tableau_assistant/tests/integration/test_e2e_workflow.py -q "2024年各省份销售额"
    
    # 跳过维度层级推断（使用缓存）
    python tableau_assistant/tests/integration/test_e2e_workflow.py --skip-hierarchy
    
    # 详细输出模式
    python tableau_assistant/tests/integration/test_e2e_workflow.py -v
"""
import asyncio
import logging
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any

# 设置 UTF-8 编码（Windows）
if sys.platform == 'win32':
    import io
    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')

# 添加项目根目录到 Python 路径
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


def load_env():
    """加载环境变量"""
    env_file = project_root / ".env"
    if env_file.exists():
        with open(env_file, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                if '=' in line:
                    key, _, value = line.partition('=')
                    key = key.strip()
                    value = value.strip()
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    if key and key not in os.environ:
                        os.environ[key] = value
        print(f"✓ 已加载环境变量: {env_file}")
    else:
        print(f"⚠️ 未找到 .env 文件: {env_file}")


class E2ETestRunner:
    """端到端测试运行器"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.metadata = None
        self.store = None
        self.data_model_manager = None
        self.results = {}
        
    async def setup(self):
        """设置测试环境"""
        from dotenv import load_dotenv
        from langgraph.runtime import Runtime
        
        from tableau_assistant.src.models.workflow.context import VizQLContext, set_tableau_config
        from tableau_assistant.src.capabilities.storage import StoreManager
        from tableau_assistant.src.capabilities.data_model import DataModelManager
        from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
        
        load_dotenv()
        
        # 获取数据源 LUID
        datasource_luid = os.environ.get("DATASOURCE_LUID")
        if not datasource_luid:
            raise ValueError("缺少必要的环境变量: DATASOURCE_LUID")
        
        print(f"\n{'='*70}")
        print("端到端工作流测试")
        print(f"{'='*70}")
        print(f"\n数据源 LUID: {datasource_luid}")
        
        # 创建 StoreManager
        db_path = "data/test_e2e_workflow.db"
        self.store = StoreManager(db_path=db_path)
        print(f"持久化存储: {db_path}")
        
        # 创建 VizQLContext
        context = VizQLContext(
            datasource_luid=datasource_luid,
            user_id="test_user",
            session_id="test_session",
            max_replan_rounds=3,
            parallel_upper_limit=3,
            max_retry_times=3,
            max_subtasks_per_round=10
        )
        
        runtime = Runtime(context=context, store=self.store)
        
        # 设置 Tableau 配置
        tableau_ctx = _get_tableau_context_from_env()
        set_tableau_config(
            store_manager=self.store,
            tableau_token=tableau_ctx.get("api_key", ""),
            tableau_site=tableau_ctx.get("site", ""),
            tableau_domain=tableau_ctx.get("domain", "")
        )
        
        # 创建 DataModelManager
        self.data_model_manager = DataModelManager(runtime)
        
        # 设置 metadata_tool 的 manager
        from tableau_assistant.src.tools.metadata_tool import set_metadata_manager
        set_metadata_manager(self.data_model_manager)
        
        print("✓ 测试环境已设置")
        
    async def teardown(self):
        """清理测试环境"""
        if self.store and hasattr(self.store, 'close'):
            self.store.close()
        print("\n✓ 测试环境已清理")
        
    async def step1_dimension_hierarchy(self, skip_if_cached: bool = False) -> Dict[str, Any]:
        """
        步骤 1: 维度层级推断（Token 级流式输出）
        """
        print(f"\n{'='*70}")
        print("步骤 1: 维度层级推断 (Token 级流式输出)")
        print(f"{'='*70}")
        
        # 获取元数据（不增强，不使用缓存的维度层级）
        print("\n[1.1] 获取元数据...")
        self.metadata = await self.data_model_manager.get_data_model_async(
            use_cache=True,
            enhance=False  # 不增强，这样不��使用缓存的维度层级
        )
        
        print(f"  数据源: {self.metadata.datasource_name}")
        print(f"  字段数: {self.metadata.field_count}")
        print(f"  维度数: {len(self.metadata.get_dimensions())}")
        print(f"  度量数: {len(self.metadata.get_measures())}")
        
        # 检查是否有缓存的维度层级
        if skip_if_cached and self.metadata.dimension_hierarchy:
            hierarchy = {k: v for k, v in self.metadata.dimension_hierarchy.items() if not k.startswith("_")}
            if hierarchy:
                print(f"\n[1.2] 使用缓存的维度层级 ({len(hierarchy)} 个维度)")
                self.results['dimension_hierarchy'] = hierarchy
                return {'cached': True, 'count': len(hierarchy)}
        
        # 执行维度层级推断（Token 级流式输出）
        print(f"\n[1.2] 开始维度层级推断 (Token 级流式输出)...")
        print("-" * 60)
        
        from tableau_assistant.src.agents.base import get_llm, parse_json_response
        from tableau_assistant.src.agents.base.node import convert_messages
        from tableau_assistant.src.agents.dimension_hierarchy.prompt import DIMENSION_HIERARCHY_PROMPT
        from tableau_assistant.src.models.dimension_hierarchy import DimensionHierarchyResult
        
        # 准备维度信息
        dimension_fields = self.metadata.get_dimensions()
        dimension_info = []
        for field in dimension_fields:
            info = {
                "name": field.name,
                "caption": field.fieldCaption,
                "dataType": field.dataType,
                "description": field.description or "",
                "unique_count": field.unique_count or 0,
                "sample_values": (field.sample_values or [])[:5],
            }
            dimension_info.append(info)
        
        dimensions_str = json.dumps(dimension_info, ensure_ascii=False, indent=2)
        
        # 获取 LLM
        llm = get_llm(agent_name="dimension_hierarchy")
        
        # 格式化消息
        messages = DIMENSION_HIERARCHY_PROMPT.format_messages(dimensions=dimensions_str)
        langchain_messages = convert_messages(messages)
        
        # Token 级流式调用
        start_time = datetime.now()
        collected_content = []
        token_count = 0
        
        async for event in llm.astream_events(langchain_messages, version="v2"):
            event_type = event.get("event")
            if event_type == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk and hasattr(chunk, "content"):
                    token = chunk.content
                    if token:
                        # 实时打印每个 token
                        print(token, end="", flush=True)
                        collected_content.append(token)
                        token_count += 1
        
        print()  # 换行
        print("-" * 60)
        
        duration = (datetime.now() - start_time).total_seconds()
        full_content = "".join(collected_content)
        
        print(f"\n流式输出统计:")
        print(f"  Token 数: {token_count}")
        print(f"  耗时: {duration:.2f}s")
        print(f"  速度: {token_count / duration:.1f} tokens/s" if duration > 0 else "  速度: N/A")
        
        # 解析结果
        print(f"\n[1.3] 解析推断结果...")
        result = parse_json_response(full_content, DimensionHierarchyResult)
        
        # 按 category 分组显示
        by_category = {}
        for field_name, attrs in result.dimension_hierarchy.items():
            cat = attrs.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((field_name, attrs))
        
        print(f"\n✓ 推断完成: {len(result.dimension_hierarchy)} 个维度")
        for cat, fields in sorted(by_category.items()):
            print(f"\n  [{cat}] ({len(fields)} 个)")
            for field_name, attrs in sorted(fields, key=lambda x: x[1].level)[:5]:
                rel_info = ""
                if attrs.parent_dimension:
                    rel_info += f" ↑{attrs.parent_dimension}"
                if attrs.child_dimension:
                    rel_info += f" ↓{attrs.child_dimension}"
                print(f"    - {field_name}: {attrs.category_detail} L{attrs.level} conf={attrs.level_confidence:.2f}{rel_info}")
            if len(fields) > 5:
                print(f"    ... 还有 {len(fields) - 5} 个")
        
        # 更新 metadata 的维度层级
        self.metadata.dimension_hierarchy = {
            name: attrs.model_dump() for name, attrs in result.dimension_hierarchy.items()
        }
        
        self.results['dimension_hierarchy'] = result.dimension_hierarchy
        
        return {
            'cached': False,
            'count': len(result.dimension_hierarchy),
            'token_count': token_count,
            'duration': duration
        }

    async def step2_understanding(self, question: str) -> Dict[str, Any]:
        """
        步骤 2: 问题理解（带工具调用，Token 级流式输出）
        """
        print(f"\n{'='*70}")
        print("步骤 2: 问题理解 (Token 级流式输出 + 工具调用)")
        print(f"{'='*70}")
        print(f"\n问题: {question}")
        
        from tableau_assistant.src.agents.base import get_llm, parse_json_response
        from tableau_assistant.src.agents.base.node import convert_messages
        from tableau_assistant.src.agents.understanding.prompt import UNDERSTANDING_PROMPT
        from tableau_assistant.src.tools.metadata_tool import get_metadata
        from tableau_assistant.src.tools.date_tool import parse_date, detect_date_format
        from tableau_assistant.src.tools.schema_tool import get_schema_module
        from tableau_assistant.src.models.semantic.query import SemanticQuery
        from langchain_core.messages import ToolMessage
        
        # 格式化元数据摘要
        def format_metadata_summary(metadata):
            if metadata is None:
                return "No metadata available"
            if hasattr(metadata, 'fields'):
                fields = metadata.fields
                dimensions = [f for f in fields if getattr(f, 'role', '').upper() == 'DIMENSION']
                measures = [f for f in fields if getattr(f, 'role', '').upper() == 'MEASURE']
                lines = []
                lines.append(f"Dimensions ({len(dimensions)}): " + ", ".join(
                    getattr(f, 'fieldCaption', getattr(f, 'name', str(f))) for f in dimensions[:15]
                ))
                lines.append(f"Measures ({len(measures)}): " + ", ".join(
                    getattr(f, 'fieldCaption', getattr(f, 'name', str(f))) for f in measures[:15]
                ))
                return "\n".join(lines)
            return str(metadata)
        
        metadata_summary = format_metadata_summary(self.metadata)
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"\n[2.1] 初始化 LLM 和工具...")
        
        # 获取 LLM 和工具
        llm = get_llm(agent_name="understanding")
        tools = [get_metadata, get_schema_module, parse_date, detect_date_format]
        llm_with_tools = llm.bind_tools(tools)
        
        # 格式化消息
        messages = UNDERSTANDING_PROMPT.format_messages(
            question=question,
            metadata_summary=metadata_summary,
            current_date=current_date,
        )
        langchain_messages = convert_messages(messages)
        
        # 构建工具映射
        tool_map = {tool.name: tool for tool in tools}
        
        print(f"  可用工具: {list(tool_map.keys())}")
        
        print(f"\n[2.2] 开始 Token 级流式输出 (带工具调用)...")
        print("-" * 60)
        
        start_time = datetime.now()
        total_tokens = 0
        iteration = 0
        max_iterations = 5
        tool_calls_made = []
        
        while iteration < max_iterations:
            iteration += 1
            print(f"\n[迭代 {iteration}]", end="", flush=True)
            
            collected_content = []
            current_tool_calls = []
            
            # 流式调用
            async for event in llm_with_tools.astream_events(langchain_messages, version="v2"):
                event_type = event.get("event")
                
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk:
                        # Token 内容
                        if hasattr(chunk, "content") and chunk.content:
                            print(chunk.content, end="", flush=True)
                            collected_content.append(chunk.content)
                            total_tokens += 1
                        
                        # 工具调用检测
                        if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                            for tc in chunk.tool_call_chunks:
                                if tc.get("name"):
                                    print(f"\n  🔧 调用工具: {tc['name']}", end="", flush=True)
            
            print()  # 换行
            
            # 获取完整响应
            response = await llm_with_tools.ainvoke(langchain_messages)
            langchain_messages.append(response)
            
            # 检查工具调用
            if not response.tool_calls:
                print(f"  ✓ 无工具调用，返回最终结果")
                break
            
            # 处理工具调用
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                print(f"  执行: {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:50]}...)")
                tool_calls_made.append(tool_name)
                
                tool = tool_map.get(tool_name)
                if tool:
                    try:
                        if hasattr(tool, 'ainvoke'):
                            tool_result = await tool.ainvoke(tool_args)
                        else:
                            tool_result = tool.invoke(tool_args)
                        result_preview = str(tool_result)[:100]
                        print(f"  结果: {result_preview}...")
                    except Exception as e:
                        tool_result = f"Error: {str(e)}"
                        print(f"  错误: {tool_result}")
                else:
                    tool_result = f"Tool {tool_name} not found"
                
                langchain_messages.append(
                    ToolMessage(content=str(tool_result), tool_call_id=tool_id)
                )
        
        print("-" * 60)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        print(f"\n流式输出统计:")
        print(f"  迭代次数: {iteration}")
        print(f"  工具调用: {tool_calls_made}")
        print(f"  总 Token 数: {total_tokens}")
        print(f"  耗时: {duration:.2f}s")
        
        # 获取最终内容
        final_content = ""
        for msg in reversed(langchain_messages):
            if hasattr(msg, 'content') and msg.content and not isinstance(msg, ToolMessage):
                final_content = msg.content
                break
        
        # 解析 SemanticQuery
        print(f"\n[2.3] 解析 SemanticQuery...")
        try:
            semantic_query = parse_json_response(final_content, SemanticQuery)
            
            print(f"\n✓ SemanticQuery 解析成功:")
            print(f"  度量: {[m.name for m in semantic_query.measures]}")
            print(f"  维度: {[d.name for d in semantic_query.dimensions]}")
            print(f"  筛选: {len(semantic_query.filters)} 个")
            print(f"  分析: {[a.type.value for a in semantic_query.analyses]}")
            
            if self.verbose:
                print(f"\n完整 SemanticQuery:")
                print(semantic_query.model_dump_json(indent=2, exclude_none=True))
            
            self.results['semantic_query'] = semantic_query
            
            return {
                'success': True,
                'semantic_query': semantic_query,
                'token_count': total_tokens,
                'tool_calls': tool_calls_made,
                'duration': duration
            }
            
        except Exception as e:
            print(f"❌ SemanticQuery 解析失败: {e}")
            return {
                'success': False,
                'error': str(e),
                'raw_content': final_content[:500]
            }
    
    async def step3_field_mapping(self, semantic_query, question: str) -> Dict[str, Any]:
        """
        步骤 3: 字段映射（RAG + LLM）
        """
        print(f"\n{'='*70}")
        print("步骤 3: 字段映射 (RAG + LLM)")
        print(f"{'='*70}")
        
        try:
            from tableau_assistant.src.nodes.field_mapper.node import FieldMapperNode
            from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
            from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
        except ImportError as e:
            print(f"\n⚠️ 字段映射模块未安装: {e}")
            return {'success': False, 'error': str(e)}
        
        # 创建字段索引器（自动选择 Embedding 提供者）
        print("\n[3.1] 创建字段索引...")
        field_indexer = FieldIndexer(datasource_luid=self.metadata.datasource_luid)
        indexed_count = field_indexer.index_fields(self.metadata.fields)
        print(f"  索引字段数: {indexed_count}")
        print(f"  Embedding 提供者: {type(field_indexer.embedding_provider).__name__}")
        
        # 创建语义映射器
        print("\n[3.2] 创建语义映射器...")
        semantic_mapper = SemanticMapper(field_indexer=field_indexer)
        
        # 创建 FieldMapper 节点
        mapper = FieldMapperNode()
        mapper.set_semantic_mapper(semantic_mapper)
        
        # 提取业务术语
        terms_to_map = []
        role_filters = {}
        
        for measure in semantic_query.measures:
            terms_to_map.append(measure.name)
            role_filters[measure.name] = "measure"
        
        for dimension in semantic_query.dimensions:
            terms_to_map.append(dimension.name)
            role_filters[dimension.name] = "dimension"
        
        print(f"\n[3.3] 映射业务术语: {terms_to_map}")
        
        # 执行字段映射
        start_time = datetime.now()
        mapping_results = await mapper.map_fields_batch(
            terms=terms_to_map,
            datasource_luid=self.metadata.datasource_luid,
            context=question,
            role_filters=role_filters
        )
        duration = (datetime.now() - start_time).total_seconds()
        
        print(f"\n✓ 字段映射完成 (耗时: {duration:.2f}s)")
        print(f"\n映射结果:")
        
        success_count = 0
        for term, result in mapping_results.items():
            status = "✓" if result.technical_field else "❌"
            if result.technical_field:
                success_count += 1
            confidence = f"{result.confidence:.2f}" if result.confidence else "N/A"
            source = result.mapping_source
            print(f"  {status} {term} → {result.technical_field} (置信度: {confidence}, 来源: {source})")
            
            if result.alternatives and self.verbose:
                print(f"      备选: {[a['field'] for a in result.alternatives]}")
        
        # 输出统计
        stats = mapper.get_stats()
        print(f"\n映射统计:")
        print(f"  成功率: {success_count}/{len(terms_to_map)}")
        print(f"  缓存命中: {stats['cache_hits']}")
        print(f"  快速路径: {stats['fast_path_hits']}")
        print(f"  LLM 回退: {stats['llm_fallback_count']}")
        
        self.results['field_mapping'] = mapping_results
        
        return {
            'success': True,
            'mapping_results': mapping_results,
            'success_count': success_count,
            'total_count': len(terms_to_map),
            'duration': duration
        }
    
    async def run_e2e_test(
        self, 
        question: str = "各省份的销售额",
        skip_hierarchy: bool = False
    ):
        """
        运行完整的端到端测试
        """
        try:
            await self.setup()
            
            # 步骤 1: 维度层级推断
            step1_result = await self.step1_dimension_hierarchy(skip_if_cached=skip_hierarchy)
            
            # 步骤 2: 问题理解
            step2_result = await self.step2_understanding(question)
            
            if not step2_result.get('success'):
                print(f"\n❌ 问题理解失败，无法继续字段映射")
                return
            
            # 步骤 3: 字段映射
            semantic_query = step2_result.get('semantic_query')
            if semantic_query:
                step3_result = await self.step3_field_mapping(semantic_query, question)
            
            # 输出总结
            print(f"\n{'='*70}")
            print("端到端测试总结")
            print(f"{'='*70}")
            
            print(f"\n步骤 1 - 维度层级推断:")
            if step1_result.get('cached'):
                print(f"  使用缓存: {step1_result['count']} 个维度")
            else:
                print(f"  推断维度: {step1_result['count']} 个")
                print(f"  Token 数: {step1_result.get('token_count', 'N/A')}")
                print(f"  耗时: {step1_result.get('duration', 'N/A'):.2f}s")
            
            print(f"\n步骤 2 - 问题理解:")
            print(f"  状态: {'✓ 成功' if step2_result.get('success') else '❌ 失败'}")
            if step2_result.get('success'):
                sq = step2_result['semantic_query']
                print(f"  度量: {[m.name for m in sq.measures]}")
                print(f"  维度: {[d.name for d in sq.dimensions]}")
                print(f"  Token 数: {step2_result.get('token_count', 'N/A')}")
                print(f"  工具调用: {step2_result.get('tool_calls', [])}")
            
            if 'step3_result' in dir() and step3_result:
                print(f"\n步骤 3 - 字段映射:")
                print(f"  状态: {'✓ 成功' if step3_result.get('success') else '❌ 失败'}")
                if step3_result.get('success'):
                    print(f"  成功率: {step3_result['success_count']}/{step3_result['total_count']}")
                    print(f"  耗时: {step3_result.get('duration', 'N/A'):.2f}s")
            
            print(f"\n✓ 端到端测试完成")
            
        finally:
            await self.teardown()


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="端到端工作流测试")
    parser.add_argument(
        "--question", "-q",
        type=str,
        default="各省份的销售额",
        help="测试问题"
    )
    parser.add_argument(
        "--skip-hierarchy",
        action="store_true",
        help="跳过维度层级推断（使用缓存）"
    )
    parser.add_argument(
        "--verbose", "-v",
        action="store_true",
        help="详细输出模式"
    )
    
    args = parser.parse_args()
    
    # 加载环境变量
    load_env()
    
    # 运行测试
    runner = E2ETestRunner(verbose=args.verbose)
    await runner.run_e2e_test(
        question=args.question,
        skip_hierarchy=args.skip_hierarchy
    )


if __name__ == "__main__":
    asyncio.run(main())
