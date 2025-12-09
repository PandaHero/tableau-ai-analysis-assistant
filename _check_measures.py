"""检查数据源中的度量字段"""
import sys
sys.path.insert(0, '.')
from dotenv import load_dotenv
load_dotenv()

import asyncio
from tableau_assistant.src.capabilities.storage import StoreManager
from tableau_assistant.src.capabilities.data_model import DataModelManager
from tableau_assistant.src.models.workflow.context import VizQLContext, set_tableau_config
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
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
    from langgraph.runtime import Runtime
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
    
    print("=" * 70)
    print("数据源中的度量字段 (role=measure):")
    print("=" * 70)
    
    measures = [f for f in metadata.fields if f.role == 'measure']
    for f in measures:
        caption = getattr(f, 'caption', None) or getattr(f, 'field_caption', None) or f.name
        print(f"  {f.name}: {caption}")
        desc = getattr(f, 'description', None)
        if desc:
            print(f"    描述: {desc}")
    
    print("\n" + "=" * 70)
    print("数据源中的维度字段 (role=dimension):")
    print("=" * 70)
    
    dimensions = [f for f in metadata.fields if f.role == 'dimension']
    for f in dimensions:
        caption = getattr(f, 'caption', None) or getattr(f, 'field_caption', None) or f.name
        category = getattr(f, 'category', None) or ''
        print(f"  {f.name}: {caption} [{category}]")

asyncio.run(main())
