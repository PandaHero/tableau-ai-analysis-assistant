"""
维度层级推断优化测试

测试优化后的完整流程：
1. 首次推断 - 分批并行推断 + 缓存存储
2. 缓存命中 - 直接返回缓存结果
3. 增量推断 - 仅推断新增字段
4. 问题理解 - 使用维度层级信息
5. 字段映射 - RAG + LLM

使用真实的 Tableau 元数据和 LLM 模型。

使用方法：
    # 运行完整测试
    python tableau_assistant/tests/integration/test_dimension_hierarchy_optimization.py
    
    # 强制刷新缓存
    python tableau_assistant/tests/integration/test_dimension_hierarchy_optimization.py --force-refresh
    
    # 指定问题
    python tableau_assistant/tests/integration/test_dimension_hierarchy_optimization.py -q "2024年各省份销售额"
    
    # 测试并行流式输出
    python tableau_assistant/tests/integration/test_dimension_hierarchy_optimization.py --parallel-stream
"""
import asyncio
import logging
import os
import sys
import json
from pathlib import Path
from datetime import datetime
from typing import Optional, Dict, Any, List

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


class OptimizationTestRunner:
    """维度层级推断优化测试运行器"""
    
    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.metadata = None
        self.store = None
        self.data_model_manager = None
        self.datasource_luid = None
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
        
        self.datasource_luid = os.environ.get("DATASOURCE_LUID")
        if not self.datasource_luid:
            raise ValueError("缺少必要的环境变量: DATASOURCE_LUID")
        
        print(f"\n{'='*70}")
        print("维度层级推断优化测试")
        print(f"{'='*70}")
        print(f"\n数据源 LUID: {self.datasource_luid}")
        
        # 创建 StoreManager
        db_path = "data/test_hierarchy_optimization.db"
        self.store = StoreManager(db_path=db_path)
        print(f"持久化存储: {db_path}")
        
        # 创建 VizQLContext
        context = VizQLContext(
            datasource_luid=self.datasource_luid,
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


    async def get_metadata(self) -> Any:
        """获取元数据（不增强）"""
        print("\n[获取元数据]")
        self.metadata = await self.data_model_manager.get_data_model_async(
            use_cache=True,
            enhance=False
        )
        
        print(f"  数据源: {self.metadata.datasource_name}")
        print(f"  字段数: {self.metadata.field_count}")
        print(f"  维度数: {len(self.metadata.get_dimensions())}")
        print(f"  度量数: {len(self.metadata.get_measures())}")
        
        return self.metadata

    async def test_first_inference_with_batch(
        self,
        parallel: bool = True,
        stream: bool = True,
        batch_size: int = 5,
        max_concurrency: int = 3
    ) -> Dict[str, Any]:
        """
        测试 1: 首次推断（分批 + 并行 + 流式输出）
        
        验证：
        - 分批推断正确工作
        - 并行执行提升性能
        - 流式输出带批次标识
        - 结果正确存入缓存
        """
        print(f"\n{'='*70}")
        print("测试 1: 首次推断（分批并行 + 流式输出）")
        print(f"{'='*70}")
        
        from tableau_assistant.src.agents.dimension_hierarchy.node import (
            dimension_hierarchy_node,
            _get_from_cache,
            _put_to_cache,
        )
        
        # 清除缓存以模拟首次推断
        print("\n[1.1] 清除缓存...")
        namespace = ("dimension_hierarchy_cache",)
        try:
            self.store.delete(namespace, self.datasource_luid)
            print("  ✓ 缓存已清除")
        except Exception as e:
            print(f"  ⚠️ 清除缓存失败: {e}")
        
        # 验证缓存已清除
        cache_entry = _get_from_cache(self.datasource_luid, self.store)
        assert cache_entry is None, "缓存应该为空"
        print("  ✓ 验证缓存为空")
        
        # 定义流式输出回调（静默收集，推断完成后按批次顺序展示）
        batch_tokens = {}  # {batch_id: [tokens]}
        batch_complete = {}  # {batch_id: bool}
        
        def on_token(batch_id: int, token: str):
            """并行流式输出回调（静默收集）"""
            if batch_id not in batch_tokens:
                batch_tokens[batch_id] = []
            batch_tokens[batch_id].append(token)
        
        print("  (后台并行执行中，完成后按批次顺序展示...)")
        
        # 执行首次推断
        print(f"\n[1.2] 执行首次推断...")
        print(f"  并行: {parallel}, 流式: {stream}")
        print(f"  批次大小: {batch_size}, 最大并发: {max_concurrency}")
        print("-" * 60)
        
        start_time = datetime.now()
        
        result = await dimension_hierarchy_node(
            metadata=self.metadata,
            datasource_luid=self.datasource_luid,
            stream=stream,
            use_cache=True,
            incremental=True,
            use_batch=True,
            batch_size=batch_size,
            parallel=parallel,
            max_concurrency=max_concurrency,
            on_token=on_token if (parallel and stream) else None,
            store_manager=self.store
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        print("-" * 60)
        
        # 统计结果
        total_tokens = sum(len(tokens) for tokens in batch_tokens.values())
        
        # 按批次顺序展示完整输出（用户友好的串行展示）
        print(f"\n  推断输出（按批次顺序展示）:")
        for batch_id in sorted(batch_tokens.keys()):
            tokens = batch_tokens[batch_id]
            content = "".join(tokens)
            # 只显示前 200 字符，避免输出过长
            preview = content[:200] + "..." if len(content) > 200 else content
            print(f"\n  [批次 {batch_id}] ({len(tokens)} tokens)")
            print(f"  {preview}")
        
        print(f"\n[1.3] 推断结果:")
        print(f"  维度数: {len(result.dimension_hierarchy)}")
        print(f"  耗时: {duration:.2f}s")
        print(f"  批次数: {len(batch_tokens)}")
        print(f"  总 Token 数: {total_tokens}")
        
        # 按 category 分组显示
        by_category = {}
        for field_name, attrs in result.dimension_hierarchy.items():
            cat = attrs.category
            if cat not in by_category:
                by_category[cat] = []
            by_category[cat].append((field_name, attrs))
        
        print(f"\n  按类别分布:")
        for cat, fields in sorted(by_category.items()):
            print(f"    [{cat}]: {len(fields)} 个")
        
        # 验证缓存已写入
        print(f"\n[1.4] 验证缓存...")
        cache_entry = _get_from_cache(self.datasource_luid, self.store)
        assert cache_entry is not None, "缓存应该已写入"
        assert len(cache_entry.hierarchy_data) == len(result.dimension_hierarchy), \
            "缓存数据应与推断结果一致"
        print(f"  ✓ 缓存已写入: {len(cache_entry.hierarchy_data)} 个字段")
        print(f"  ✓ field_hash: {cache_entry.field_hash[:16]}...")
        
        self.results['first_inference'] = {
            'count': len(result.dimension_hierarchy),
            'duration': duration,
            'batch_count': len(batch_tokens),
            'token_count': total_tokens,
        }
        
        return result

    async def test_cache_hit(self) -> Dict[str, Any]:
        """
        测试 2: 缓存命中
        
        验证：
        - 缓存有效时直接返回
        - 不调用 LLM
        - 响应时间 < 100ms
        """
        print(f"\n{'='*70}")
        print("测试 2: 缓存命中")
        print(f"{'='*70}")
        
        from tableau_assistant.src.agents.dimension_hierarchy.node import (
            dimension_hierarchy_node,
        )
        
        # 执行推断（应该命中缓存）
        print("\n[2.1] 执行推断（应命中缓存）...")
        
        start_time = datetime.now()
        
        result = await dimension_hierarchy_node(
            metadata=self.metadata,
            datasource_luid=self.datasource_luid,
            stream=False,
            use_cache=True,
            store_manager=self.store
        )
        
        duration = (datetime.now() - start_time).total_seconds()
        
        print(f"\n[2.2] 结果:")
        print(f"  维度数: {len(result.dimension_hierarchy)}")
        print(f"  耗时: {duration*1000:.2f}ms")
        
        # 验证响应时间
        if duration < 0.5:
            print(f"  ✓ 响应时间 < 500ms，确认缓存命中")
        else:
            print(f"  ⚠️ 响应时间较长，可能未命中缓存")
        
        self.results['cache_hit'] = {
            'count': len(result.dimension_hierarchy),
            'duration_ms': duration * 1000,
        }
        
        return result


    async def test_incremental_inference(self) -> Dict[str, Any]:
        """
        测试 3: 增量推断
        
        模拟字段变化，验证：
        - 仅推断新增字段
        - 保留未变化字段的缓存结果
        - 删除已删除字段
        """
        print(f"\n{'='*70}")
        print("测试 3: 增量推断")
        print(f"{'='*70}")
        
        from tableau_assistant.src.agents.dimension_hierarchy.node import (
            dimension_hierarchy_node,
            _get_from_cache,
            _compute_incremental_fields,
            HierarchyCacheEntry,
        )
        
        # 获取当前缓存
        print("\n[3.1] 获取当前缓存...")
        cache_entry = _get_from_cache(self.datasource_luid, self.store)
        if not cache_entry:
            print("  ⚠️ 无缓存，跳过增量推断测试")
            return {'skipped': True}
        
        original_count = len(cache_entry.hierarchy_data)
        print(f"  缓存字段数: {original_count}")
        
        # 模拟字段变化：移除一个字段，添加一个"虚拟"字段
        # 注意：这里我们不能真正修改元数据，只是测试增量计算逻辑
        print("\n[3.2] 测试增量字段计算...")
        
        dimension_fields = self.metadata.get_dimensions()
        
        # 计算增量字段（当前字段 vs 缓存字段）
        incremental = _compute_incremental_fields(dimension_fields, cache_entry)
        
        print(f"  新增字段: {len(incremental.new_fields)}")
        print(f"  删除字段: {len(incremental.deleted_fields)}")
        print(f"  未变化字段: {len(incremental.unchanged_fields)}")
        
        if incremental.new_fields:
            print(f"  新增: {list(incremental.new_fields)[:5]}...")
        if incremental.deleted_fields:
            print(f"  删除: {list(incremental.deleted_fields)[:5]}...")
        
        # 如果没有变化，说明缓存与当前元数据一致
        if not incremental.has_changes:
            print("\n  ✓ 字段无变化，缓存完全有效")
        else:
            print(f"\n  需要增量推断: {incremental.needs_inference}")
        
        self.results['incremental'] = {
            'original_count': original_count,
            'new_fields': len(incremental.new_fields),
            'deleted_fields': len(incremental.deleted_fields),
            'unchanged_fields': len(incremental.unchanged_fields),
            'has_changes': incremental.has_changes,
        }
        
        return self.results['incremental']

    async def test_understanding_with_hierarchy(self, question: str) -> Dict[str, Any]:
        """
        测试 4: 问题理解（使用维度层级信息）
        """
        print(f"\n{'='*70}")
        print("测试 4: 问题理解")
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
        
        # 格式化元数据摘要（包含维度层级信息）
        def format_metadata_with_hierarchy(metadata):
            fields = metadata.fields
            dimensions = [f for f in fields if getattr(f, 'role', '').upper() == 'DIMENSION']
            measures = [f for f in fields if getattr(f, 'role', '').upper() == 'MEASURE']
            
            lines = []
            lines.append(f"Dimensions ({len(dimensions)}):")
            for f in dimensions[:10]:
                caption = getattr(f, 'fieldCaption', getattr(f, 'name', str(f)))
                # 添加维度层级信息
                hierarchy_info = ""
                if hasattr(metadata, 'dimension_hierarchy') and metadata.dimension_hierarchy:
                    h = metadata.dimension_hierarchy.get(f.name, {})
                    if h:
                        cat = h.get('category_detail', h.get('category', ''))
                        level = h.get('level', '')
                        if cat:
                            hierarchy_info = f" [{cat} L{level}]"
                lines.append(f"  - {caption}{hierarchy_info}")
            
            lines.append(f"\nMeasures ({len(measures)}):")
            for f in measures[:10]:
                caption = getattr(f, 'fieldCaption', getattr(f, 'name', str(f)))
                lines.append(f"  - {caption}")
            
            return "\n".join(lines)
        
        metadata_summary = format_metadata_with_hierarchy(self.metadata)
        current_date = datetime.now().strftime("%Y-%m-%d")
        
        print(f"\n[4.1] 元数据摘要（含维度层级）:")
        print(metadata_summary[:500] + "..." if len(metadata_summary) > 500 else metadata_summary)
        
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
        
        tool_map = {tool.name: tool for tool in tools}
        
        print(f"\n[4.2] 开始问题理解...")
        print("-" * 60)
        
        start_time = datetime.now()
        total_tokens = 0
        iteration = 0
        max_iterations = 5
        tool_calls_made = []
        
        while iteration < max_iterations:
            iteration += 1
            
            # 流式调用
            collected_content = []
            async for event in llm_with_tools.astream_events(langchain_messages, version="v2"):
                event_type = event.get("event")
                if event_type == "on_chat_model_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk and hasattr(chunk, "content") and chunk.content:
                        print(chunk.content, end="", flush=True)
                        collected_content.append(chunk.content)
                        total_tokens += 1
            
            print()
            
            # 获取完整响应
            response = await llm_with_tools.ainvoke(langchain_messages)
            langchain_messages.append(response)
            
            if not response.tool_calls:
                break
            
            # 处理工具调用
            for tool_call in response.tool_calls:
                tool_name = tool_call["name"]
                tool_args = tool_call["args"]
                tool_id = tool_call["id"]
                
                print(f"\n  🔧 {tool_name}({json.dumps(tool_args, ensure_ascii=False)[:50]})")
                tool_calls_made.append(tool_name)
                
                tool = tool_map.get(tool_name)
                if tool:
                    try:
                        if hasattr(tool, 'ainvoke'):
                            tool_result = await tool.ainvoke(tool_args)
                        else:
                            tool_result = tool.invoke(tool_args)
                    except Exception as e:
                        tool_result = f"Error: {str(e)}"
                else:
                    tool_result = f"Tool {tool_name} not found"
                
                langchain_messages.append(
                    ToolMessage(content=str(tool_result), tool_call_id=tool_id)
                )
        
        print("-" * 60)
        
        duration = (datetime.now() - start_time).total_seconds()
        
        # 获取最终内容
        final_content = ""
        for msg in reversed(langchain_messages):
            if hasattr(msg, 'content') and msg.content and not isinstance(msg, ToolMessage):
                final_content = msg.content
                break
        
        # 解析 SemanticQuery
        print(f"\n[4.3] 解析 SemanticQuery...")
        try:
            semantic_query = parse_json_response(final_content, SemanticQuery)
            
            print(f"\n✓ SemanticQuery:")
            print(f"  度量: {[m.name for m in semantic_query.measures]}")
            print(f"  维度: {[d.name for d in semantic_query.dimensions]}")
            print(f"  筛选: {len(semantic_query.filters)} 个")
            print(f"  耗时: {duration:.2f}s")
            
            self.results['understanding'] = {
                'success': True,
                'measures': [m.name for m in semantic_query.measures],
                'dimensions': [d.name for d in semantic_query.dimensions],
                'filters': len(semantic_query.filters),
                'tool_calls': tool_calls_made,
                'duration': duration,
            }
            
            return {'success': True, 'semantic_query': semantic_query}
            
        except Exception as e:
            print(f"❌ 解析失败: {e}")
            self.results['understanding'] = {'success': False, 'error': str(e)}
            return {'success': False, 'error': str(e)}


    async def test_field_mapping(self, semantic_query, question: str) -> Dict[str, Any]:
        """
        测试 5: 字段映射（RAG + LLM）
        """
        print(f"\n{'='*70}")
        print("测试 5: 字段映射")
        print(f"{'='*70}")
        
        try:
            from tableau_assistant.src.agents.field_mapper import FieldMapperNode
            from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
            from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
        except ImportError as e:
            print(f"\n⚠️ 字段映射模块未安装: {e}")
            return {'success': False, 'error': str(e)}
        
        # 验证维度层级信息是否已注入到字段元数据
        # 注意：正式代码中 DataModelManager._inject_hierarchy_to_fields() 会自动注入
        print("\n[5.0] 验证维度层级信息...")
        fields_with_category = sum(1 for f in self.metadata.fields if getattr(f, 'category', None))
        if fields_with_category > 0:
            print(f"  ✓ {fields_with_category} 个字段已有 category 信息")
        else:
            print("  ⚠️ 字段没有 category 信息（可能需要检查 DataModelManager）")
        
        # 创建字段索引器
        print("\n[5.1] 创建字段索引...")
        field_indexer = FieldIndexer(datasource_luid=self.metadata.datasource_luid)
        indexed_count = field_indexer.index_fields(self.metadata.fields)
        print(f"  索引字段数: {indexed_count}")
        
        # 调试：显示所有维度字段的 caption 和 category
        print("\n  所有维度字段详情:")
        for field in self.metadata.fields:
            if field.role.upper() == 'DIMENSION':
                cat = getattr(field, 'category', 'N/A')
                cat_detail = getattr(field, 'category_detail', 'N/A')
                print(f"    - {field.name}: caption='{field.fieldCaption}', category={cat}, detail={cat_detail}")
        
        # 显示所有 geographic 类别的字段
        print("\n  [调试] geographic 类别字段:")
        for field in self.metadata.fields:
            cat = getattr(field, 'category', None)
            if cat and 'geographic' in cat.lower():
                samples = getattr(field, 'sample_values', [])
                print(f"    - {field.name}: caption='{field.fieldCaption}', category={cat}")
                print(f"      samples: {samples[:3] if samples else 'N/A'}")
        
        # 特别检查 yyyymm 和 pro_name 字段的索引文本
        for field in self.metadata.fields:
            if field.name in ['yyyymm', 'pro_name']:
                cat = getattr(field, 'category', 'N/A')
                cat_detail = getattr(field, 'category_detail', 'N/A')
                samples = getattr(field, 'sample_values', [])
                print(f"\n  [调试] {field.name} 字段:")
                print(f"    name: {field.name}")
                print(f"    caption: {field.fieldCaption}")
                print(f"    role: {field.role}")
                print(f"    category: {cat}")
                print(f"    category_detail: {cat_detail}")
                print(f"    samples: {samples[:3] if samples else 'N/A'}")
                
                # 查看索引文本
                chunk = field_indexer.get_chunk(field.name)
                if chunk:
                    print(f"    index_text: {chunk.index_text}")
        
        # 创建语义映射器
        print("\n[5.2] 创建语义映射器...")
        semantic_mapper = SemanticMapper(field_indexer=field_indexer)
        
        # 调试：检查 Reranker 是否正常工作
        print(f"  Reranker: {type(semantic_mapper.reranker).__name__ if semantic_mapper.reranker else 'None'}")
        print(f"  use_two_stage: {semantic_mapper.config.use_two_stage}")
        print(f"  high_confidence_threshold: {semantic_mapper.config.high_confidence_threshold}")
        
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
        
        # 也映射筛选字段
        for filter_item in semantic_query.filters:
            if hasattr(filter_item, 'field') and filter_item.field:
                terms_to_map.append(filter_item.field)
                # 筛选字段通常是维度
                role_filters[filter_item.field] = "dimension"
        
        print(f"\n[5.3] 映射业务术语: {terms_to_map}")
        
        # 调试：直接调用 SemanticMapper 查看 RAG 检索结果
        print("\n  [调试] RAG 检索详情:")
        for term in terms_to_map:
            role_filter = role_filters.get(term)
            rag_result = semantic_mapper.map_field(
                term=term,
                context=question,
                role_filter=role_filter
            )
            print(f"\n    查询: '{term}' (role_filter={role_filter})")
            print(f"    匹配: {rag_result.matched_field}, 置信度: {rag_result.confidence:.4f}")
            print(f"    来源: {rag_result.source.value}")
            
            # 显示 top-3 检索结果
            if rag_result.retrieval_results:
                print(f"    Top-3 检索结果:")
                for i, r in enumerate(rag_result.retrieval_results[:3]):
                    chunk = r.field_chunk
                    print(f"      {i+1}. {chunk.field_name} (caption='{chunk.field_caption}')")
                    raw_score_str = f"{r.raw_score:.4f}" if r.raw_score is not None else "N/A"
                    print(f"         score={r.score:.4f}, raw_score={raw_score_str}")
                    print(f"         category={chunk.category}, role={chunk.role}")
                    print(f"         index_text: {chunk.index_text[:100]}...")
        
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
            category = result.category or "N/A"
            
            # 获取映射到的字段的 caption
            mapped_field = None
            if result.technical_field:
                mapped_field = next(
                    (f for f in self.metadata.fields if f.name == result.technical_field),
                    None
                )
            caption = mapped_field.fieldCaption if mapped_field else "N/A"
            
            print(f"  {status} {term} → {result.technical_field} (caption='{caption}', 置信度: {confidence}, 来源: {source})")
            
            # 显示备选字段（如果有）
            if result.alternatives:
                print(f"      备选: {result.alternatives[:3]}")
        
        self.results['field_mapping'] = {
            'success': True,
            'success_count': success_count,
            'total_count': len(terms_to_map),
            'duration': duration,
        }
        
        return self.results['field_mapping']

    async def run_full_test(
        self,
        question: str = "2024年各省份的利润",
        force_refresh: bool = False,
        parallel: bool = True,
        stream: bool = True,
    ):
        """
        运行完整的优化测试流程
        """
        try:
            await self.setup()
            await self.get_metadata()
            
            # 测试 1: 首次推断（或强制刷新）
            if force_refresh:
                print("\n⚠️ 强制刷新模式：将清除缓存并重新推断")
            
            hierarchy_result = await self.test_first_inference_with_batch(
                parallel=parallel,
                stream=stream,
            )
            
            # 测试 2: 缓存命中
            await self.test_cache_hit()
            
            # 测试 3: 增量推断
            await self.test_incremental_inference()
            
            # 更新 metadata 的维度层级（dimension_hierarchy_node 已自动注入到各字段）
            self.metadata.dimension_hierarchy = {
                name: attrs.model_dump() 
                for name, attrs in hierarchy_result.dimension_hierarchy.items()
            }
            
            # 测试 4: 问题理解
            understanding_result = await self.test_understanding_with_hierarchy(question)
            
            # 测试 5: 字段映射
            if understanding_result.get('success'):
                semantic_query = understanding_result['semantic_query']
                await self.test_field_mapping(semantic_query, question)
            
            # 输出总结
            self._print_summary()
            
        finally:
            await self.teardown()

    def _print_summary(self):
        """输出测试总结"""
        print(f"\n{'='*70}")
        print("测试总结")
        print(f"{'='*70}")
        
        if 'first_inference' in self.results:
            r = self.results['first_inference']
            print(f"\n1. 首次推断:")
            print(f"   维度数: {r['count']}")
            print(f"   耗时: {r['duration']:.2f}s")
            print(f"   批次数: {r['batch_count']}")
        
        if 'cache_hit' in self.results:
            r = self.results['cache_hit']
            print(f"\n2. 缓存命中:")
            print(f"   维度数: {r['count']}")
            print(f"   耗时: {r['duration_ms']:.2f}ms")
        
        if 'incremental' in self.results:
            r = self.results['incremental']
            print(f"\n3. 增量推断:")
            print(f"   新增字段: {r['new_fields']}")
            print(f"   删除字段: {r['deleted_fields']}")
            print(f"   未变化: {r['unchanged_fields']}")
        
        if 'understanding' in self.results:
            r = self.results['understanding']
            print(f"\n4. 问题理解:")
            print(f"   状态: {'✓ 成功' if r.get('success') else '❌ 失败'}")
            if r.get('success'):
                print(f"   度量: {r['measures']}")
                print(f"   维度: {r['dimensions']}")
                print(f"   耗时: {r['duration']:.2f}s")
        
        if 'field_mapping' in self.results:
            r = self.results['field_mapping']
            print(f"\n5. 字段映射:")
            print(f"   成功率: {r['success_count']}/{r['total_count']}")
            print(f"   耗时: {r['duration']:.2f}s")
        
        print(f"\n{'='*70}")
        print("✓ 测试完成")
        print(f"{'='*70}")


async def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description="维度层级推断优化测试")
    parser.add_argument(
        "--question", "-q",
        type=str,
        default="2024年各省份的利润",
        help="测试问题"
    )
    parser.add_argument(
        "--force-refresh",
        action="store_true",
        help="强制刷新缓存"
    )
    parser.add_argument(
        "--parallel-stream",
        action="store_true",
        help="测试并行流式输出"
    )
    parser.add_argument(
        "--serial",
        action="store_true",
        help="使用串行模式（禁用并行）"
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
    runner = OptimizationTestRunner(verbose=args.verbose)
    await runner.run_full_test(
        question=args.question,
        force_refresh=args.force_refresh,
        parallel=not args.serial,
        stream=True,
    )


if __name__ == "__main__":
    asyncio.run(main())
