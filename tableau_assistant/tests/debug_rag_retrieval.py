"""
调试脚本：测试 RAG 检索效果

用于诊断中文业务术语到英文字段名的映射问题。
"""
import asyncio
import os
import sys

# 添加项目根目录到 path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))))

from dotenv import load_dotenv
load_dotenv()


async def test_rag_retrieval():
    """测试 RAG 检索效果"""
    from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
    from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
    from tableau_assistant.src.capabilities.data_model.manager import get_datasource_metadata
    from tableau_assistant.src.models.metadata import Metadata, FieldMetadata
    from tableau_assistant.src.bi_platforms.tableau import ensure_valid_auth_async
    
    # 1. 加载数据模型
    print("=" * 60)
    print("1. 加载数据模型")
    print("=" * 60)
    
    # 从 settings 获取配置
    from tableau_assistant.src.config.settings import settings
    
    datasource_luid = settings.datasource_luid
    if not datasource_luid:
        print("错误: 请在 .env 中设置 DATASOURCE_LUID")
        return
    
    # 获取认证
    auth_ctx = await ensure_valid_auth_async()
    
    # 尝试从缓存获取元数据
    from tableau_assistant.src.capabilities.storage.store_manager import get_store_manager
    
    store = get_store_manager()
    cached_metadata = store.get_metadata(datasource_luid)
    
    if cached_metadata:
        print("从缓存加载元数据")
        metadata = cached_metadata
    else:
        print("缓存中没有元数据，从 API 获取...")
        # 从 settings 获取配置
        from tableau_assistant.src.config.settings import settings
        
        raw_metadata = await get_datasource_metadata(
            datasource_luid=datasource_luid,
            tableau_token=auth_ctx.api_key,
            tableau_site=settings.tableau_site,
            tableau_domain=settings.tableau_domain,
        )
        
        # 转换为 Metadata 对象
        fields = [FieldMetadata(**f) for f in raw_metadata.get("fields", [])]
        metadata = Metadata(
            datasource_luid=datasource_luid,
            datasource_name=raw_metadata.get("datasource_name", "Unknown"),
            fields=fields,
            field_count=len(fields),
            dimension_hierarchies=raw_metadata.get("dimension_hierarchies", []),
        )
    print(f"数据源: {datasource_luid}")
    print(f"字段数量: {len(metadata.fields)}")
    
    # 2. 打印所有字段信息
    print("\n" + "=" * 60)
    print("2. 数据源字段列表")
    print("=" * 60)
    
    for i, field in enumerate(metadata.fields[:30], 1):  # 只显示前30个
        print(f"{i:2}. {field.name:30} | caption: {field.fieldCaption:25} | role: {field.role}")
    
    if len(metadata.fields) > 30:
        print(f"... 还有 {len(metadata.fields) - 30} 个字段")
    
    # 3. 初始化 FieldIndexer 和 SemanticMapper
    print("\n" + "=" * 60)
    print("3. 初始化 RAG 组件")
    print("=" * 60)
    
    field_indexer = FieldIndexer(datasource_luid=datasource_luid)
    count = field_indexer.index_fields(metadata.fields)
    print(f"索引字段数: {count}")
    print(f"RAG 可用: {field_indexer.rag_available}")
    
    if not field_indexer.rag_available:
        print("警告: RAG 不可用，将回退到 LLM 匹配")
    
    # 打印索引文本示例
    print("\n--- 索引文本示例 ---")
    for chunk in field_indexer.get_all_chunks():
        print(f"字段: {chunk.field_name}")
        print(f"  索引文本: {chunk.index_text}")
        print(f"  样例值: {chunk.sample_values}")
        print()
    
    semantic_mapper = SemanticMapper(field_indexer=field_indexer)
    
    # 检查 Reranker 配置
    print(f"SemanticMapper 配置:")
    print(f"  use_two_stage: {semantic_mapper.config.use_two_stage}")
    print(f"  use_hybrid: {semantic_mapper.config.use_hybrid}")
    print(f"  reranker: {semantic_mapper.reranker}")
    print(f"  confidence_threshold: {semantic_mapper.config.confidence_threshold}")
    print(f"  high_confidence_threshold: {semantic_mapper.config.high_confidence_threshold}")
    
    # 4. 测试完整的 FieldMapperNode 流程
    print("\n" + "=" * 60)
    print("4. 测试 FieldMapperNode 完整流程")
    print("=" * 60)
    
    from tableau_assistant.src.agents.field_mapper.node import FieldMapperNode
    
    mapper = FieldMapperNode()
    mapper.set_semantic_mapper(semantic_mapper)
    
    test_terms_full = [
        ("订单", "dimension"),  # Order ID 是 dimension
        ("订单", None),  # 不过滤角色
        ("地区", "dimension"),
    ]
    
    for term, role in test_terms_full:
        print(f"\n--- FieldMapperNode: '{term}' (角色: {role}) ---")
        result = await mapper.map_field(
            term=term,
            datasource_luid=datasource_luid,
            context="各地区有多少订单",
            role_filter=role
        )
        print(f"映射结果: {result.technical_field}")
        print(f"置信度: {result.confidence:.4f}")
        print(f"来源: {result.mapping_source}")
        if result.alternatives:
            print(f"备选: {result.alternatives[:3]}")
    
    # 5. 测试中文术语检索
    print("\n" + "=" * 60)
    print("5. 测试中文术语 RAG 检索")
    print("=" * 60)
    
    test_terms = [
        ("订单", "dimension"),
        ("产品", "dimension"),
        ("销售额", "measure"),
        ("利润", "measure"),
        ("地区", "dimension"),
        ("类别", "dimension"),
        ("客户", "dimension"),
        ("数量", "measure"),
    ]
    
    for term, expected_role in test_terms:
        print(f"\n--- 查询: '{term}' (期望角色: {expected_role}) ---")
        
        result = semantic_mapper.map_field(
            term=term,
            role_filter=expected_role
        )
        
        print(f"匹配字段: {result.matched_field}")
        print(f"置信度: {result.confidence:.4f}")
        print(f"来源: {result.source.value}")
        
        if result.retrieval_results:
            print("Top-5 候选:")
            for r in result.retrieval_results[:5]:
                print(f"  - {r.field_chunk.field_name:25} | caption: {r.field_chunk.field_caption:20} | score: {r.score:.4f}")
        
        if result.alternatives:
            print(f"备选: {result.alternatives}")
    
    # 5. 测试英文术语检索（对比）
    print("\n" + "=" * 60)
    print("5. 测试英文术语 RAG 检索（对比）")
    print("=" * 60)
    
    english_terms = [
        ("Order ID", "dimension"),
        ("Product Name", "dimension"),
        ("Sales", "measure"),
        ("Profit", "measure"),
        ("Region", "dimension"),
        ("Category", "dimension"),
    ]
    
    for term, expected_role in english_terms:
        print(f"\n--- 查询: '{term}' (期望角色: {expected_role}) ---")
        
        result = semantic_mapper.map_field(
            term=term,
            role_filter=expected_role
        )
        
        print(f"匹配字段: {result.matched_field}")
        print(f"置信度: {result.confidence:.4f}")
        print(f"来源: {result.source.value}")
    
    # 6. 检查 Embedding 提供者
    print("\n" + "=" * 60)
    print("6. Embedding 提供者信息")
    print("=" * 60)
    
    provider = field_indexer.embedding_provider
    print(f"提供者类型: {type(provider).__name__}")
    
    if hasattr(provider, '_provider'):
        print(f"底层提供者: {type(provider._provider).__name__}")
    
    # 测试向量相似度
    if provider:
        print("\n测试向量相似度:")
        
        pairs = [
            ("订单", "Order ID"),
            ("销售额", "Sales"),
            ("利润", "Profit"),
            ("地区", "Region"),
        ]
        
        for cn, en in pairs:
            vec_cn = provider.embed_query(cn)
            vec_en = provider.embed_query(en)
            
            # 计算余弦相似度
            import numpy as np
            vec_cn = np.array(vec_cn)
            vec_en = np.array(vec_en)
            similarity = np.dot(vec_cn, vec_en) / (np.linalg.norm(vec_cn) * np.linalg.norm(vec_en))
            
            print(f"  '{cn}' vs '{en}': {similarity:.4f}")


if __name__ == "__main__":
    asyncio.run(test_rag_retrieval())
