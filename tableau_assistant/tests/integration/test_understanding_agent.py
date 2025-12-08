"""
Agent 功能测试

使用真实的 Tableau 元数据和 LLM 模型测试已实现的 agent：
1. Understanding Agent - 问题理解（带工具调用）
2. Dimension Hierarchy Agent - 维度层级推断（流式输出）

测试选项：
    # 运行默认测试（Understanding Agent 多问题测试）
    python tableau_assistant/tests/integration/test_understanding_agent.py
    
    # 运行所有测试（Understanding + Dimension Hierarchy + Token 流式）
    python tableau_assistant/tests/integration/test_understanding_agent.py -a
    
    # 交互式测试
    python tableau_assistant/tests/integration/test_understanding_agent.py -i
    
    # 单个问题测试
    python tableau_assistant/tests/integration/test_understanding_agent.py -q "各省份销售额"
    
    # 同时测试字段映射
    python tableau_assistant/tests/integration/test_understanding_agent.py -q "各省份销售额" -m
    
    # 测试维度层级推断（流式输出）
    python tableau_assistant/tests/integration/test_understanding_agent.py -d
    
    # 测试 Token 级别流式输出（真实数据）
    python tableau_assistant/tests/integration/test_understanding_agent.py -t
    
    # 测试 Understanding Agent 流式输出（带工具调用）
    python tableau_assistant/tests/integration/test_understanding_agent.py -u
    python tableau_assistant/tests/integration/test_understanding_agent.py -u -q "2024年各省份销售额"

注意：
    - 需要配置 .env 文件中的 LLM 和 Tableau 相关配置
    - 测试会调用真实的 LLM API
    - 所有测试都使用真实的 Tableau 元数据
"""
import asyncio
import logging
import os
import sys
from pathlib import Path
from datetime import datetime

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


async def setup_test_environment():
    """
    设置测试环境，使用 DataModelManager 获取元数据
    
    Returns:
        tuple: (metadata, cleanup_func)
    """
    from dotenv import load_dotenv
    from langgraph.runtime import Runtime
    
    from tableau_assistant.src.models.workflow.context import VizQLContext, set_tableau_config
    from tableau_assistant.src.capabilities.storage import StoreManager
    from tableau_assistant.src.capabilities.data_model import DataModelManager
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    
    # 加载环境变量
    load_dotenv()
    
    # 获取数据源 LUID
    datasource_luid = os.environ.get("DATASOURCE_LUID")
    if not datasource_luid:
        raise ValueError("缺少必要的环境变量: DATASOURCE_LUID")
    
    print(f"✓ 数据源 LUID: {datasource_luid}")
    
    # 创建 StoreManager
    db_path = "data/test_understanding.db"
    store = StoreManager(db_path=db_path)
    print(f"✓ 使用持久化存储: {db_path}")
    
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
    
    # 创建 Runtime（store 是 StoreManager 实例）
    runtime = Runtime(context=context, store=store)
    
    # 设置 Tableau 配置
    tableau_ctx = _get_tableau_context_from_env()
    set_tableau_config(
        store_manager=store,
        tableau_token=tableau_ctx.get("api_key", ""),
        tableau_site=tableau_ctx.get("site", ""),
        tableau_domain=tableau_ctx.get("domain", "")
    )
    print("✓ Tableau 配置已设置")
    
    # 创建 DataModelManager
    data_model_manager = DataModelManager(runtime)
    
    # 获取元数据（使用 DataModelManager）
    print("\n[1/2] 获取元数据...")
    metadata = await data_model_manager.get_data_model_async(
        use_cache=True,
        enhance=True
    )
    
    print(f"✓ 元数据获取成功:")
    print(f"  - 数据源: {metadata.datasource_name}")
    print(f"  - 字段数: {metadata.field_count}")
    print(f"  - 维度数: {len(metadata.get_dimensions())}")
    print(f"  - 度量数: {len(metadata.get_measures())}")
    
    # 打印部分字段信息
    print(f"\n  维度字段示例:")
    for f in metadata.get_dimensions()[:5]:
        print(f"    - {f.fieldCaption} ({f.dataType})")
    
    print(f"\n  度量字段示例:")
    for f in metadata.get_measures()[:5]:
        print(f"    - {f.fieldCaption} ({f.dataType})")
    
    # 打印维度层级信息
    if metadata.dimension_hierarchy:
        # 过滤掉 _cached_at 等元数据字段
        hierarchy = {k: v for k, v in metadata.dimension_hierarchy.items() if not k.startswith("_")}
        print(f"\n[2/2] 维度层级推断结果:")
        print(f"  - 维度层级数: {len(hierarchy)}")
        
        # 按 category 分组显示摘要
        by_category = {}
        for field_name, attrs in hierarchy.items():
            cat = attrs.get("category", "other") if isinstance(attrs, dict) else getattr(attrs, "category", "other")
            if cat not in by_category:
                by_category[cat] = []
            level = attrs.get("level", 0) if isinstance(attrs, dict) else getattr(attrs, "level", 0)
            by_category[cat].append((field_name, level))
        
        print(f"\n  按类别分组:")
        for cat, fields in sorted(by_category.items()):
            print(f"  - {cat}: {', '.join([f'{name}(L{level})' for name, level in sorted(fields, key=lambda x: x[1])])}")
        
        # 显示详细信息
        print(f"\n  详细推断结果:")
        for field_name, attrs in sorted(hierarchy.items()):
            if isinstance(attrs, dict):
                cat = attrs.get("category", "other")
                cat_detail = attrs.get("category_detail", "")
                level = attrs.get("level", 0)
                granularity = attrs.get("granularity", "")
                confidence = attrs.get("level_confidence", 0)
                reasoning = attrs.get("reasoning", "")[:50]  # 截断推理
                parent = attrs.get("parent_dimension")
                child = attrs.get("child_dimension")
            else:
                cat = getattr(attrs, "category", "other")
                cat_detail = getattr(attrs, "category_detail", "")
                level = getattr(attrs, "level", 0)
                granularity = getattr(attrs, "granularity", "")
                confidence = getattr(attrs, "level_confidence", 0)
                reasoning = getattr(attrs, "reasoning", "")[:50]
                parent = getattr(attrs, "parent_dimension", None)
                child = getattr(attrs, "child_dimension", None)
            
            rel_info = ""
            if parent:
                rel_info += f" ↑{parent}"
            if child:
                rel_info += f" ↓{child}"
            
            print(f"    {field_name}: {cat_detail} L{level}({granularity}) conf={confidence:.2f}{rel_info}")
    else:
        print(f"\n[2/2] 维度层级: 未推断")
    
    # 设置 metadata_tool 的 manager（用于工具调用）
    from tableau_assistant.src.tools.metadata_tool import set_metadata_manager
    set_metadata_manager(data_model_manager)
    print("✓ MetadataManager 已注入到 metadata_tool")
    
    # 创建清理函数
    class CleanupContext:
        def __init__(self, store):
            self.store = store
        
        async def teardown(self):
            if hasattr(self.store, 'close'):
                self.store.close()
            print("✓ 测试环境已清理")
    
    cleanup = CleanupContext(store)
    
    return metadata, cleanup


async def test_understanding_node(metadata, question: str, with_field_mapping: bool = False):
    """
    测试 understanding_node
    
    Args:
        metadata: Metadata 对象
        question: 测试问题
        with_field_mapping: 是否同时测试字段映射
    
    Returns:
        dict: 测试结果
    """
    from tableau_assistant.src.agents.understanding.node import understanding_node
    
    print(f"\n{'='*60}")
    print(f"问题: {question}")
    print(f"{'='*60}")
    
    # 构建状态
    state = {
        "question": question,
        "metadata": metadata,
    }
    
    # 调用 understanding_node
    start_time = datetime.now()
    result = await understanding_node(state)
    duration = (datetime.now() - start_time).total_seconds()
    
    # 输出结果
    print(f"\n执行时间: {duration:.2f}s")
    print(f"是否分析类问题: {result.get('is_analysis_question')}")
    print(f"理解是否完成: {result.get('understanding_complete')}")
    
    if result.get('error'):
        print(f"❌ 错误: {result.get('error')}")
    elif result.get('semantic_query'):
        semantic_query = result['semantic_query']
        print(f"\n✓ SemanticQuery 解析成功:")
        print(f"  - 度量: {[m.name for m in semantic_query.measures]}")
        print(f"  - 维度: {[d.name for d in semantic_query.dimensions]}")
        print(f"  - 筛选: {len(semantic_query.filters)} 个")
        print(f"  - 分析: {[a.type.value for a in semantic_query.analyses]}")
        
        # 打印完整 JSON
        print(f"\n完整 SemanticQuery:")
        print(semantic_query.model_dump_json(indent=2, exclude_none=True))
        
        # 如果需要测试字段映射
        if with_field_mapping:
            await test_field_mapping(metadata, semantic_query, question)
            
    elif result.get('non_analysis_response'):
        print(f"\n非分析类问题响应: {result.get('non_analysis_response')}")
    
    return result


async def test_field_mapping(metadata, semantic_query, question: str):
    """
    测试字段映射（RAG + LLM）
    
    Args:
        metadata: Metadata 对象
        semantic_query: SemanticQuery 对象
        question: 原始问题（用于上下文）
    """
    print(f"\n{'='*60}")
    print("字段映射测试 (RAG + LLM)")
    print(f"{'='*60}")
    
    try:
        from tableau_assistant.src.nodes.field_mapper.node import FieldMapperNode, field_mapper_node
        from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
        from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
        
        # 创建字段索引器
        print("\n[1/3] 创建字段索引...")
        field_indexer = FieldIndexer(datasource_luid=metadata.datasource_luid)
        indexed_count = field_indexer.index_fields(metadata.fields)
        print(f"✓ 索引创建完成，共 {indexed_count} 个字段")
        
        # 创建语义映射器
        print("\n[2/3] 创建语义映射器...")
        semantic_mapper = SemanticMapper(field_indexer=field_indexer)
        print("✓ 语义映射器创建完成")
        
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
        
        print(f"\n[3/3] 映射业务术语: {terms_to_map}")
        
        # 执行字段映射
        start_time = datetime.now()
        mapping_results = await mapper.map_fields_batch(
            terms=terms_to_map,
            datasource_luid=metadata.datasource_luid,
            context=question,
            role_filters=role_filters
        )
        duration = (datetime.now() - start_time).total_seconds()
        
        print(f"\n✓ 字段映射完成 (耗时: {duration:.2f}s)")
        print(f"\n映射结果:")
        for term, result in mapping_results.items():
            status = "✓" if result.technical_field else "❌"
            confidence = f"{result.confidence:.2f}" if result.confidence else "N/A"
            source = result.mapping_source
            print(f"  {status} {term} → {result.technical_field} (置信度: {confidence}, 来源: {source})")
            
            if result.alternatives:
                print(f"      备选: {[a['field'] for a in result.alternatives]}")
        
        # 输出统计
        stats = mapper.get_stats()
        print(f"\n映射统计:")
        print(f"  - 总映射数: {stats['total_mappings']}")
        print(f"  - 缓存命中: {stats['cache_hits']}")
        print(f"  - 快速路径: {stats['fast_path_hits']}")
        print(f"  - LLM 回退: {stats['llm_fallback_count']}")
        
    except ImportError as e:
        print(f"\n⚠️ 字段映射模块未安装或导入失败: {e}")
        print("  跳过字段映射测试")
    except Exception as e:
        print(f"\n❌ 字段映射失败: {e}")
        logger.error("字段映射失败", exc_info=True)


async def test_dimension_hierarchy_node(metadata, stream: bool = True):
    """
    测试 dimension_hierarchy_node（流式输出）
    
    Args:
        metadata: Metadata 对象
        stream: 是否使用流式输出（默认 True）
    
    Returns:
        DimensionHierarchyResult 对象
    """
    from tableau_assistant.src.agents.dimension_hierarchy.node import dimension_hierarchy_node
    
    print(f"\n{'='*60}")
    print("维度层级推断测试")
    print(f"{'='*60}")
    
    print(f"\n输入维度数: {len(metadata.get_dimensions())}")
    print(f"流式输出: {'是' if stream else '否'}")
    
    # 调用 dimension_hierarchy_node
    start_time = datetime.now()
    
    print(f"\n开始推断...")
    result = await dimension_hierarchy_node(
        metadata=metadata,
        datasource_luid=metadata.datasource_luid,
        stream=stream
    )
    
    duration = (datetime.now() - start_time).total_seconds()
    
    # 输出结果
    print(f"\n执行时间: {duration:.2f}s")
    print(f"推断维度数: {len(result.dimension_hierarchy)}")
    
    if result.dimension_hierarchy:
        # 按 category 分组显示
        by_category = {}
        for field_name, attrs in result.dimension_hierarchy.items():
            cat = attrs.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((field_name, attrs))
        
        print(f"\n✓ 推断结果按类别分组:")
        for cat, fields in sorted(by_category.items()):
            print(f"\n  [{cat}] ({len(fields)} 个)")
            for field_name, attrs in sorted(fields, key=lambda x: x[1].level):
                rel_info = ""
                if attrs.parent_dimension:
                    rel_info += f" ↑{attrs.parent_dimension}"
                if attrs.child_dimension:
                    rel_info += f" ↓{attrs.child_dimension}"
                print(f"    - {field_name}: {attrs.category_detail} L{attrs.level}({attrs.granularity}) "
                      f"conf={attrs.level_confidence:.2f}{rel_info}")
        
        # 计算统计
        confidences = [attrs.level_confidence for attrs in result.dimension_hierarchy.values()]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0
        
        print(f"\n统计:")
        print(f"  - 平均置信度: {avg_confidence:.2f}")
        print(f"  - 最高置信度: {max(confidences):.2f}")
        print(f"  - 最低置信度: {min(confidences):.2f}")
    else:
        print("❌ 未推断出任何维度层级")
    
    return result


async def test_token_streaming(metadata):
    """
    测试 Token 级别流式输出（使用真实元数据）
    
    直接调用 base/node.py 中的流式函数，
    展示 token 级别的实时输出效果。
    
    Args:
        metadata: 真实的 Metadata 对象
    """
    from tableau_assistant.src.agents.base import get_llm, parse_json_response
    from tableau_assistant.src.agents.base.node import convert_messages
    from tableau_assistant.src.agents.dimension_hierarchy.prompt import DIMENSION_HIERARCHY_PROMPT
    from tableau_assistant.src.models.dimension_hierarchy import DimensionHierarchyResult
    import json
    
    print(f"\n{'='*60}")
    print("Token 级别流式输出测试（真实数据）")
    print(f"{'='*60}")
    
    # 使用真实元数据准备维度信息
    dimension_fields = metadata.get_dimensions()
    
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
    
    print(f"\n数据源: {metadata.datasource_name}")
    print(f"输入维度数: {len(dimension_info)}")
    print(f"维度: {[d['caption'] for d in dimension_info[:10]]}{'...' if len(dimension_info) > 10 else ''}")
    
    # 获取 LLM
    print(f"\n初始化 LLM...")
    llm = get_llm(agent_name="dimension_hierarchy")
    print(f"✓ LLM 已初始化")
    
    # 格式化消息
    messages = DIMENSION_HIERARCHY_PROMPT.format_messages(dimensions=dimensions_str)
    
    # Token 级流式调用
    print(f"\n开始 Token 级流式输出:")
    print("-" * 60)
    
    start_time = datetime.now()
    
    langchain_messages = convert_messages(messages)
    
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
    
    # 统计
    full_content = "".join(collected_content)
    print(f"\n流式输出统计:")
    print(f"  - Token 数: {token_count}")
    print(f"  - 总字符数: {len(full_content)}")
    print(f"  - 耗时: {duration:.2f}s")
    print(f"  - 速度: {token_count / duration:.1f} tokens/s" if duration > 0 else "  - 速度: N/A")
    
    # 解析结果
    print(f"\n解析 JSON 结果...")
    try:
        result = parse_json_response(full_content, DimensionHierarchyResult)
        print(f"✓ 解析成功，推断了 {len(result.dimension_hierarchy)} 个维度")
        
        # 按 category 分组显示
        by_category = {}
        for field_name, attrs in result.dimension_hierarchy.items():
            cat = attrs.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((field_name, attrs))
        
        print(f"\n推断结果:")
        for cat, fields in sorted(by_category.items()):
            print(f"  [{cat}]")
            for field_name, attrs in sorted(fields, key=lambda x: x[1].level):
                print(f"    - {field_name}: {attrs.category_detail} L{attrs.level} conf={attrs.level_confidence:.2f}")
                
    except Exception as e:
        print(f"❌ 解析失败: {e}")
        logger.error("JSON 解析失败", exc_info=True)
    
    return full_content


async def test_understanding_streaming(metadata, question: str):
    """
    测试 Understanding Agent 的流式输出（带工具调用）
    
    Args:
        metadata: Metadata 对象
        question: 测试问题
    """
    from tableau_assistant.src.agents.base import get_llm, convert_messages
    from tableau_assistant.src.agents.understanding.prompt import UNDERSTANDING_PROMPT
    from tableau_assistant.src.tools.metadata_tool import get_metadata
    from tableau_assistant.src.tools.date_tool import parse_date, detect_date_format
    from tableau_assistant.src.tools.schema_tool import get_schema_module
    from langchain_core.messages import ToolMessage
    
    print(f"\n{'='*60}")
    print("Understanding Agent 流式输出测试（带工具调用）")
    print(f"{'='*60}")
    
    print(f"\n问题: {question}")
    
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
                getattr(f, 'fieldCaption', getattr(f, 'name', str(f))) for f in dimensions[:10]
            ))
            lines.append(f"Measures ({len(measures)}): " + ", ".join(
                getattr(f, 'fieldCaption', getattr(f, 'name', str(f))) for f in measures[:10]
            ))
            return "\n".join(lines)
        return str(metadata)
    
    metadata_summary = format_metadata_summary(metadata)
    current_date = datetime.now().strftime("%Y-%m-%d")
    
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
    
    print(f"\n开始流式输出（带工具调用）:")
    print("-" * 40)
    
    start_time = datetime.now()
    total_tokens = 0
    iteration = 0
    max_iterations = 5
    
    while iteration < max_iterations:
        iteration += 1
        print(f"\n[迭代 {iteration}] LLM 调用...")
        
        collected_content = []
        tool_calls_data = []
        
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
                    
                    # 工具调用
                    if hasattr(chunk, "tool_call_chunks") and chunk.tool_call_chunks:
                        for tc in chunk.tool_call_chunks:
                            if tc.get("name"):
                                print(f"\n  🔧 工具调用: {tc['name']}", end="", flush=True)
        
        print()  # 换行
        
        # 获取完整响应
        response = await llm_with_tools.ainvoke(langchain_messages)
        langchain_messages.append(response)
        
        # 检查工具调用
        if not response.tool_calls:
            print(f"\n✓ 无工具调用，返回最终结果")
            break
        
        # 处理工具调用
        for tool_call in response.tool_calls:
            tool_name = tool_call["name"]
            tool_args = tool_call["args"]
            tool_id = tool_call["id"]
            
            print(f"\n  执行工具: {tool_name}({tool_args})")
            
            tool = tool_map.get(tool_name)
            if tool:
                try:
                    if hasattr(tool, 'ainvoke'):
                        tool_result = await tool.ainvoke(tool_args)
                    else:
                        tool_result = tool.invoke(tool_args)
                    print(f"  工具结果: {str(tool_result)[:100]}...")
                except Exception as e:
                    tool_result = f"Error: {str(e)}"
                    print(f"  工具错误: {tool_result}")
            else:
                tool_result = f"Tool {tool_name} not found"
            
            langchain_messages.append(
                ToolMessage(content=str(tool_result), tool_call_id=tool_id)
            )
    
    print("-" * 40)
    
    duration = (datetime.now() - start_time).total_seconds()
    
    print(f"\n流式输出统计:")
    print(f"  - 迭代次数: {iteration}")
    print(f"  - 总 Token 数: {total_tokens}")
    print(f"  - 耗时: {duration:.2f}s")
    
    # 获取最终内容
    final_content = ""
    for msg in reversed(langchain_messages):
        if hasattr(msg, 'content') and msg.content and not isinstance(msg, ToolMessage):
            final_content = msg.content
            break
    
    if final_content:
        print(f"\n最终响应长度: {len(final_content)} 字符")
    
    return final_content


async def run_tests():
    """运行所有测试"""
    # 加载环境变量
    load_env()
    
    # 设置测试环境
    metadata, env = await setup_test_environment()
    
    # 测试问题列表
    test_questions = [
        # 简单聚合
        "各省份的销售额",
        
        # 单维度累计
        "按月累计销售额",
        
        # 多维度累计
        "各省份按月累计销售额",
        
        # 排名
        "销售额排名前10的产品",
        
        # 占比
        "各省份销售额占比",
        
        # 时间筛选
        "2024年各省份的销售额",
        
        # 相对时间
        "最近3个月的销售趋势",
        
        # 非分析类问题
        "你好",
    ]
    
    # 运行测试
    results = []
    for question in test_questions:
        try:
            result = await test_understanding_node(metadata, question)
            results.append({
                "question": question,
                "success": result.get('understanding_complete', False) and not result.get('error'),
                "result": result
            })
        except Exception as e:
            logger.error(f"测试失败: {question}", exc_info=True)
            results.append({
                "question": question,
                "success": False,
                "error": str(e)
            })
    
    # 输出汇总
    print(f"\n{'='*60}")
    print("测试汇总")
    print(f"{'='*60}")
    
    success_count = sum(1 for r in results if r['success'])
    print(f"成功: {success_count}/{len(results)}")
    
    for r in results:
        status = "✓" if r['success'] else "❌"
        print(f"  {status} {r['question'][:30]}...")
    
    # 清理环境
    await env.teardown()
    
    return results


async def interactive_test():
    """交互式测试"""
    # 加载环境变量
    load_env()
    
    # 设置测试环境
    metadata, env = await setup_test_environment()
    
    print("\n" + "="*60)
    print("交互式测试模式")
    print("输入问题进行测试，输入 'quit' 或 'exit' 退出")
    print("="*60)
    
    while True:
        try:
            question = input("\n请输入问题: ").strip()
            
            if question.lower() in ['quit', 'exit', 'q']:
                break
            
            if not question:
                continue
            
            await test_understanding_node(metadata, question)
            
        except KeyboardInterrupt:
            break
        except Exception as e:
            logger.error(f"测试失败: {e}", exc_info=True)
    
    # 清理环境
    await env.teardown()
    print("\n测试结束")


async def run_dimension_hierarchy_test():
    """运行维度层级推断测试"""
    # 加载环境变量
    load_env()
    
    # 设置测试环境（不使用缓存的维度层级，强制重新推断）
    from dotenv import load_dotenv
    from langgraph.runtime import Runtime
    
    from tableau_assistant.src.models.workflow.context import VizQLContext, set_tableau_config
    from tableau_assistant.src.capabilities.storage import StoreManager
    from tableau_assistant.src.capabilities.data_model import DataModelManager
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    
    load_dotenv()
    
    datasource_luid = os.environ.get("DATASOURCE_LUID")
    if not datasource_luid:
        raise ValueError("缺少必要的环境变量: DATASOURCE_LUID")
    
    print(f"✓ 数据源 LUID: {datasource_luid}")
    
    # 创建 StoreManager
    db_path = "data/test_dimension_hierarchy.db"
    store = StoreManager(db_path=db_path)
    print(f"✓ 使用持久化存储: {db_path}")
    
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
    
    runtime = Runtime(context=context, store=store)
    
    # 设置 Tableau 配置
    tableau_ctx = _get_tableau_context_from_env()
    set_tableau_config(
        store_manager=store,
        tableau_token=tableau_ctx.get("api_key", ""),
        tableau_site=tableau_ctx.get("site", ""),
        tableau_domain=tableau_ctx.get("domain", "")
    )
    print("✓ Tableau 配置已设置")
    
    # 创建 DataModelManager
    data_model_manager = DataModelManager(runtime)
    
    # 获取元数据（不增强，不使用缓存的维度层级）
    print("\n获取元数据（不使用缓存的维度层级）...")
    metadata = await data_model_manager.get_data_model_async(
        use_cache=True,
        enhance=False  # 不增强，这样不会使用缓存的维度层级
    )
    
    print(f"✓ 元数据获取成功:")
    print(f"  - 数据源: {metadata.datasource_name}")
    print(f"  - 维度数: {len(metadata.get_dimensions())}")
    
    # 测试维度层级推断（流式输出）
    result = await test_dimension_hierarchy_node(metadata, stream=True)
    
    # 清理
    if hasattr(store, 'close'):
        store.close()
    print("\n✓ 测试完成")
    
    return result


if __name__ == "__main__":
    import argparse
    
    parser = argparse.ArgumentParser(description="Agent 功能测试")
    parser.add_argument(
        "--interactive", "-i",
        action="store_true",
        help="交互式测试模式"
    )
    parser.add_argument(
        "--question", "-q",
        type=str,
        help="单个问题测试"
    )
    parser.add_argument(
        "--with-mapping", "-m",
        action="store_true",
        help="同时测试字段映射 (RAG + LLM)"
    )
    parser.add_argument(
        "--dimension-hierarchy", "-d",
        action="store_true",
        help="测试维度层级推断（流式输出）"
    )
    parser.add_argument(
        "--token-stream", "-t",
        action="store_true",
        help="测试 Token 级别流式输出"
    )
    parser.add_argument(
        "--understanding-stream", "-u",
        action="store_true",
        help="测试 Understanding Agent 流式输出（带工具调用）"
    )
    parser.add_argument(
        "--all", "-a",
        action="store_true",
        help="运行所有测试（Understanding + Dimension Hierarchy + 流式）"
    )
    
    args = parser.parse_args()
    
    if args.token_stream:
        # Token 级流式输出测试（使用真实数据）
        async def token_stream_test():
            load_env()
            metadata, env = await setup_test_environment()
            await test_token_streaming(metadata)
            await env.teardown()
        asyncio.run(token_stream_test())
    elif args.understanding_stream:
        # Understanding 流式输出测试
        async def understanding_stream_test():
            load_env()
            metadata, env = await setup_test_environment()
            question = args.question or "各省份的销售额"
            await test_understanding_streaming(metadata, question)
            await env.teardown()
        asyncio.run(understanding_stream_test())
    elif args.dimension_hierarchy:
        asyncio.run(run_dimension_hierarchy_test())
    elif args.interactive:
        asyncio.run(interactive_test())
    elif args.question:
        async def single_test():
            load_env()
            metadata, env = await setup_test_environment()
            await test_understanding_node(metadata, args.question, with_field_mapping=args.with_mapping)
            await env.teardown()
        asyncio.run(single_test())
    elif args.all:
        async def all_tests():
            # 运行 Understanding 测试
            print("\n" + "="*60)
            print("Part 1: Understanding Agent 测试")
            print("="*60)
            await run_tests()
            
            # 运行 Dimension Hierarchy 测试
            print("\n" + "="*60)
            print("Part 2: Dimension Hierarchy Agent 测试（流式输出）")
            print("="*60)
            await run_dimension_hierarchy_test()
            
            # 运行 Token 级流式输出测试
            print("\n" + "="*60)
            print("Part 3: Token 级别流式输出测试（真实数据）")
            print("="*60)
            # 重新获取元数据（不使用缓存的维度层级）
            load_env()
            metadata2, env2 = await setup_test_environment()
            await test_token_streaming(metadata2)
            await env2.teardown()
        asyncio.run(all_tests())
    else:
        asyncio.run(run_tests())
