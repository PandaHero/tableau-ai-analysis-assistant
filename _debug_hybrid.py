"""测试新的分数判断逻辑"""
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

import asyncio
from tableau_assistant.src.capabilities.storage import StoreManager
from tableau_assistant.src.capabilities.data_model import DataModelManager
from tableau_assistant.src.models.workflow.context import VizQLContext, set_tableau_config
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
from tableau_assistant.src.agents.field_mapper import FieldMapperNode
from langgraph.runtime import Runtime
import os

async def main():
    datasource_luid = os.environ.get('DATASOURCE_LUID')
    store = StoreManager(db_path='data/test_hierarchy_optimization.db')
    context = VizQLContext(
        datasource_luid=datasource_luid,
        user_id='test_user',
        session_id='test_session',
        max_replan_rounds=3,
        parallel_upper_limit=3,
        max_retry_times=3,
        max_subtasks_per_round=10
    )
    runtime = Runtime(context=context, store=store)
    tableau_ctx = _get_tableau_context_from_env()
    set_tableau_config(
        store_manager=store,
        tableau_token=tableau_ctx.get('api_key', ''),
        tableau_site=tableau_ctx.get('site', ''),
        tableau_domain=tableau_ctx.get('domain', '')
    )
    manager = DataModelManager(runtime)
    metadata = await manager.get_data_model_async(use_cache=True, enhance=False)
    
    # 创建索引器和映射器
    field_indexer = FieldIndexer(datasource_luid=datasource_luid)
    field_indexer.index_fields(metadata.fields)
    semantic_mapper = SemanticMapper(field_indexer=field_indexer)
    
    print(f"配置:")
    print(f"  high_confidence_threshold: {semantic_mapper.config.high_confidence_threshold}")
    print(f"  confidence_threshold: {semantic_mapper.config.confidence_threshold}")
    print(f"  use_two_stage: {semantic_mapper.config.use_two_stage}")
    
    # 创建 FieldMapperNode（禁用缓存以便测试）
    mapper = FieldMapperNode(store_manager=None)
    mapper.set_semantic_mapper(semantic_mapper)
    mapper.config.enable_cache = False
    
    # 测试查询
    queries = [
        # 测试"利润"映射 - 应该映射到 groplamt
        ("利润", "各省份的利润", "measure"),
        ("毛利", "各省份的毛利", "measure"),
        # 测试"省份"映射
        ("省份", "各省份的利润", "dimension"),
    ]
    
    # 先看看 RAG 检索 "利润" 时返回了哪些候选
    print("\n[调试] RAG 检索 '利润' 的 top-10 候选:")
    rag_result = semantic_mapper.map_field(
        term="利润",
        context="各省份的利润",
        role_filter="measure"
    )
    for i, r in enumerate(rag_result.retrieval_results[:10], 1):
        print(f"  {i}. {r.field_chunk.field_name} (score={r.score:.4f})")
    
    # 看看 FieldMapperNode 的 top_k_candidates 配置
    print(f"\n[调试] FieldMapperNode 配置:")
    print(f"  top_k_candidates: {mapper.config.top_k_candidates}")
    
    # 看看 "毛利" 的 RAG 检索结果
    print("\n[调试] RAG 检索 '毛利' 的 top-10 候选:")
    rag_result2 = semantic_mapper.map_field(
        term="毛利",
        context="各省份的毛利",
        role_filter="measure"
    )
    for i, r in enumerate(rag_result2.retrieval_results[:10], 1):
        chunk = r.field_chunk
        print(f"  {i}. {chunk.field_name}")
        print(f"      caption: {chunk.field_caption}")
        print(f"      index_text: {chunk.index_text[:80]}...")
    
    for term, context_query, role in queries:
        print(f"\n{'='*70}")
        print(f"查询: '{term}' (上下文: '{context_query}', role: {role})")
        print(f"{'='*70}")
        
        # 先看 SemanticMapper 的结果
        rag_result = semantic_mapper.map_field(
            term=term,
            context=context_query,
            role_filter=role
        )
        
        print(f"\n[SemanticMapper 结果]")
        print(f"  匹配: {rag_result.matched_field}")
        print(f"  置信度: {rag_result.confidence:.4f}")
        print(f"  来源: {rag_result.source.value}")
        
        # 再看 FieldMapperNode 的结果
        result = await mapper.map_field(
            term=term,
            datasource_luid=datasource_luid,
            context=context_query,
            role_filter=role
        )
        
        print(f"\n[FieldMapperNode 结果]")
        print(f"  映射: {term} → {result.technical_field}")
        print(f"  置信度: {result.confidence:.4f}")
        print(f"  来源: {result.mapping_source}")
        if result.reasoning:
            print(f"  推理: {result.reasoning[:100]}...")

asyncio.run(main())
