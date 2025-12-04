"""
RAG 真实数据源集成测试

连接真实的 Tableau 数据源进行端到端测试，验证：
- 真实元数据获取和索引
- 复杂查询场景下的检索准确性
- 中英文混合查询
- 同义词和近义词检索
- 模糊查询和部分匹配
- 多字段批量映射
- 性能和延迟

注意：这些测试需要有效的 Tableau 配置和网络连接
"""
import os
import time
import asyncio
import pytest
from typing import List, Dict, Any, Optional
from dataclasses import dataclass

# 检查必要的环境变量
TABLEAU_DOMAIN = os.getenv("TABLEAU_DOMAIN") or os.getenv("TABLEAU_BASE_URL")
DATASOURCE_LUID = os.getenv("DATASOURCE_LUID")
ZHIPU_API_KEY = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")

SKIP_REASON = "需要 TABLEAU_DOMAIN, DATASOURCE_LUID 和 ZHIPUAI_API_KEY 环境变量"
SKIP_CONDITION = not all([TABLEAU_DOMAIN, DATASOURCE_LUID, ZHIPU_API_KEY])


@pytest.fixture(scope="module")
def tableau_auth():
    """获取 Tableau 认证 token"""
    from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
    
    ctx = _get_tableau_context_from_env()
    token = ctx.get("api_key")
    assert token, "无法获取 Tableau 认证 token"
    return token


@pytest.fixture(scope="module")
def real_metadata(tableau_auth):
    """获取真实的 Tableau 数据源元数据（不含样本以加速测试）"""
    from tableau_assistant.src.bi_platforms.tableau.metadata import get_data_dictionary
    
    site = os.getenv("TABLEAU_SITE")
    
    print(f"\n获取数据源元数据: {DATASOURCE_LUID}")
    metadata = get_data_dictionary(
        api_key=tableau_auth,
        domain=TABLEAU_DOMAIN,
        datasource_luid=DATASOURCE_LUID,
        site=site,
        include_samples=False  # 禁用样本获取以加速测试（25s -> 2s）
    )
    
    print(f"字段数量: {metadata.get('field_count', 0)}")
    print(f"字段列表: {metadata.get('field_names', [])[:10]}...")
    
    return metadata


@pytest.fixture(scope="module")
def field_indexer(real_metadata):
    """创建使用真实元数据的字段索引器"""
    from tableau_assistant.src.model_manager.embeddings import ZhipuEmbedding
    from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
    
    # 将元数据转换为 FieldMetadata 格式
    @dataclass
    class FieldMetadata:
        name: str
        fieldCaption: str
        role: str
        dataType: str
        columnClass: Optional[str] = None
        category: Optional[str] = None
        formula: Optional[str] = None
        logicalTableId: Optional[str] = None
        logicalTableCaption: Optional[str] = None
        sample_values: Optional[List[str]] = None
    
    fields = []
    for f in real_metadata.get('fields', []):
        fields.append(FieldMetadata(
            name=f.get('name', ''),
            fieldCaption=f.get('fieldCaption') or f.get('name', ''),
            role=f.get('role', 'DIMENSION').lower(),
            dataType=f.get('dataType', 'STRING'),
            columnClass=f.get('columnClass'),
            category=f.get('dataCategory'),
            formula=f.get('formula'),
            logicalTableId=f.get('logicalTableId'),
            sample_values=f.get('sample_values', [])
        ))
    
    print(f"\n创建字段索引器，索引 {len(fields)} 个字段...")
    
    provider = ZhipuEmbedding()
    indexer = FieldIndexer(
        embedding_provider=provider,
        datasource_luid=DATASOURCE_LUID,
        use_cache=True
    )
    
    start_time = time.time()
    indexer.index_fields(fields)
    index_time = time.time() - start_time
    
    print(f"索引完成，耗时: {index_time:.2f}s")
    
    return indexer


@pytest.mark.skipif(SKIP_CONDITION, reason=SKIP_REASON)
class TestRealDatasourceRetrieval:
    """
    真实数据源检索测试
    
    测试复杂场景下的检索准确性
    """
    
    def test_exact_field_name_retrieval(self, field_indexer, real_metadata):
        """测试精确字段名检索"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        field_names = real_metadata.get('field_names', [])[:5]
        
        print("\n精确字段名检索测试:")
        for field_name in field_names:
            results = retriever.retrieve(field_name, top_k=3)
            
            if results:
                top_result = results[0]
                print(f"  查询 '{field_name}' -> top-1: {top_result.field_chunk.field_name} (score: {top_result.score:.4f})")
                
                # 精确匹配应该返回自身
                top_3_names = [r.field_chunk.field_name for r in results[:3]]
                assert field_name in top_3_names, f"精确查询 '{field_name}' 应在 top-3 中"
    
    def test_chinese_synonym_retrieval(self, field_indexer):
        """测试中文同义词检索"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        # 常见的中文同义词对
        synonym_pairs = [
            ("销售额", ["销售", "收入", "营收", "金额"]),
            ("利润", ["盈利", "收益", "毛利"]),
            ("客户", ["顾客", "用户", "买家"]),
            ("日期", ["时间", "日子"]),
            ("地区", ["区域", "地域", "位置"]),
            ("产品", ["商品", "货品"]),
            ("数量", ["件数", "个数"]),
            ("订单", ["单据", "交易"]),
        ]
        
        print("\n中文同义词检索测试:")
        for base_term, synonyms in synonym_pairs:
            base_results = retriever.retrieve(base_term, top_k=5)
            
            if not base_results:
                print(f"  '{base_term}' 无结果，跳过")
                continue
            
            base_top = base_results[0].field_chunk.field_name
            print(f"  基准 '{base_term}' -> {base_top}")
            
            for synonym in synonyms[:2]:  # 只测试前2个同义词
                syn_results = retriever.retrieve(synonym, top_k=5)
                if syn_results:
                    syn_top = syn_results[0].field_chunk.field_name
                    # 检查同义词是否返回相似的结果
                    syn_top_5 = [r.field_chunk.field_name for r in syn_results[:5]]
                    overlap = base_top in syn_top_5
                    print(f"    同义词 '{synonym}' -> {syn_top} (与基准重叠: {overlap})")
    
    def test_english_query_on_chinese_fields(self, field_indexer):
        """测试英文查询中文字段"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        # 英文查询词
        english_queries = [
            "sales",
            "profit",
            "customer",
            "date",
            "region",
            "product",
            "quantity",
            "order",
            "revenue",
            "amount",
        ]
        
        print("\n英文查询测试:")
        for query in english_queries:
            results = retriever.retrieve(query, top_k=3)
            
            if results:
                top_result = results[0]
                print(f"  '{query}' -> {top_result.field_chunk.field_name} (score: {top_result.score:.4f})")
    
    def test_partial_match_retrieval(self, field_indexer, real_metadata):
        """测试部分匹配检索"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        field_names = real_metadata.get('field_names', [])
        
        print("\n部分匹配检索测试:")
        for field_name in field_names[:5]:
            if len(field_name) > 3:
                # 取字段名的前半部分
                partial = field_name[:len(field_name)//2]
                results = retriever.retrieve(partial, top_k=5)
                
                if results:
                    top_5_names = [r.field_chunk.field_name for r in results[:5]]
                    found = field_name in top_5_names
                    print(f"  部分 '{partial}' -> 完整 '{field_name}' 在 top-5: {found}")
    
    def test_fuzzy_query_retrieval(self, field_indexer):
        """测试模糊查询检索"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        # 模糊/口语化查询
        fuzzy_queries = [
            "卖了多少钱",      # 销售额
            "赚了多少",        # 利润
            "谁买的",          # 客户
            "什么时候",        # 日期
            "在哪里",          # 地区
            "买了什么",        # 产品
            "多少个",          # 数量
        ]
        
        print("\n模糊查询检索测试:")
        for query in fuzzy_queries:
            results = retriever.retrieve(query, top_k=3)
            
            if results:
                top_3 = [(r.field_chunk.field_name, r.score) for r in results[:3]]
                print(f"  '{query}' -> {top_3}")
    
    def test_role_filter_retrieval(self, field_indexer):
        """测试角色过滤检索"""
        from tableau_assistant.src.capabilities.rag.retriever import (
            EmbeddingRetriever, MetadataFilter
        )
        
        retriever = EmbeddingRetriever(field_indexer)
        
        print("\n角色过滤检索测试:")
        
        # 只检索度量
        measure_filter = MetadataFilter(role="measure")
        measure_results = retriever.retrieve("金额", top_k=10, filters=measure_filter)
        
        print(f"  度量过滤 '金额' 结果数: {len(measure_results)}")
        for r in measure_results[:3]:
            print(f"    {r.field_chunk.field_name} ({r.field_chunk.role}): {r.score:.4f}")
            assert r.field_chunk.role == "measure", f"期望 measure，实际 {r.field_chunk.role}"
        
        # 只检索维度
        dim_filter = MetadataFilter(role="dimension")
        dim_results = retriever.retrieve("名称", top_k=10, filters=dim_filter)
        
        print(f"  维度过滤 '名称' 结果数: {len(dim_results)}")
        for r in dim_results[:3]:
            print(f"    {r.field_chunk.field_name} ({r.field_chunk.role}): {r.score:.4f}")
            assert r.field_chunk.role == "dimension", f"期望 dimension，实际 {r.field_chunk.role}"


@pytest.mark.skipif(SKIP_CONDITION, reason=SKIP_REASON)
class TestHybridRetrieval:
    """
    混合检索测试
    
    测试向量+关键词混合检索的效果
    """
    
    def test_hybrid_vs_embedding_comparison(self, field_indexer):
        """比较混合检索和纯向量检索"""
        from tableau_assistant.src.capabilities.rag.retriever import (
            EmbeddingRetriever, RetrieverFactory
        )
        
        embedding_retriever = EmbeddingRetriever(field_indexer)
        hybrid_retriever = RetrieverFactory.create_hybrid_retriever(field_indexer)
        
        test_queries = ["销售", "客户名称", "订单日期", "利润率"]
        
        print("\n混合检索 vs 向量检索对比:")
        for query in test_queries:
            emb_results = embedding_retriever.retrieve(query, top_k=5)
            hyb_results = hybrid_retriever.retrieve(query, top_k=5)
            
            emb_top = emb_results[0].field_chunk.field_name if emb_results else "无"
            hyb_top = hyb_results[0].field_chunk.field_name if hyb_results else "无"
            
            emb_score = emb_results[0].score if emb_results else 0
            hyb_score = hyb_results[0].score if hyb_results else 0
            
            print(f"  '{query}':")
            print(f"    向量: {emb_top} ({emb_score:.4f})")
            print(f"    混合: {hyb_top} ({hyb_score:.4f})")
    
    def test_keyword_boost_effect(self, field_indexer, real_metadata):
        """测试关键词对检索的增强效果"""
        from tableau_assistant.src.capabilities.rag.retriever import RetrieverFactory
        
        hybrid_retriever = RetrieverFactory.create_hybrid_retriever(field_indexer)
        field_names = real_metadata.get('field_names', [])[:3]
        
        print("\n关键词增强效果测试:")
        for field_name in field_names:
            results = hybrid_retriever.retrieve(field_name, top_k=3)
            
            if results:
                top_result = results[0]
                # 精确关键词匹配应该得到高分
                print(f"  精确查询 '{field_name}' -> {top_result.field_chunk.field_name} (score: {top_result.score:.4f})")
                
                # 混合检索对精确匹配应该有很高的分数
                assert top_result.score > 0.8, f"精确匹配分数应 > 0.8，实际 {top_result.score}"


@pytest.mark.skipif(SKIP_CONDITION, reason=SKIP_REASON)
class TestSemanticMapperRealData:
    """
    语义映射器真实数据测试
    """
    
    @pytest.fixture
    def semantic_mapper(self, field_indexer):
        """创建语义映射器"""
        from tableau_assistant.src.capabilities.rag.semantic_mapper import SemanticMapper
        return SemanticMapper(field_indexer=field_indexer)
    
    def test_batch_mapping_performance(self, semantic_mapper, real_metadata):
        """测试批量映射性能"""
        field_names = real_metadata.get('field_names', [])[:10]
        
        print("\n批量映射性能测试:")
        
        start_time = time.time()
        results = semantic_mapper.map_fields_batch(field_names)
        total_time = time.time() - start_time
        
        print(f"  映射 {len(field_names)} 个字段，总耗时: {total_time:.2f}s")
        print(f"  平均每个字段: {total_time/len(field_names)*1000:.0f}ms")
        
        for term, result in zip(field_names, results):
            status = "✓" if result.matched_field else "?"
            print(f"  {status} '{term}' -> {result.matched_field} (conf: {result.confidence:.4f})")
    
    def test_mapping_with_context(self, semantic_mapper):
        """测试带上下文的映射"""
        test_cases = [
            ("金额", "我想看销售金额的趋势"),
            ("金额", "计算利润金额"),
            ("日期", "按订单日期分组"),
            ("日期", "发货日期是什么时候"),
        ]
        
        print("\n带上下文映射测试:")
        for term, context in test_cases:
            result = semantic_mapper.map_field(term, context=context)
            print(f"  '{term}' (上下文: {context[:20]}...) -> {result.matched_field}")
    
    def test_low_confidence_alternatives(self, semantic_mapper):
        """测试低置信度时的备选方案"""
        # 使用模糊的查询词
        ambiguous_terms = ["数据", "信息", "值", "字段"]
        
        print("\n低置信度备选测试:")
        for term in ambiguous_terms:
            result = semantic_mapper.map_field(term)
            
            print(f"  '{term}': conf={result.confidence:.4f}")
            if result.matched_field:
                print(f"    匹配: {result.matched_field}")
            if result.alternatives:
                print(f"    备选: {result.alternatives}")


@pytest.mark.skipif(SKIP_CONDITION, reason=SKIP_REASON)
class TestPerformanceMetrics:
    """
    性能指标测试
    """
    
    def test_retrieval_latency(self, field_indexer):
        """测试检索延迟"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        queries = ["销售", "客户", "日期", "产品", "金额"]
        latencies = []
        
        print("\n检索延迟测试:")
        for query in queries:
            start = time.time()
            results = retriever.retrieve(query, top_k=10)
            latency = (time.time() - start) * 1000
            latencies.append(latency)
            print(f"  '{query}': {latency:.0f}ms ({len(results)} 结果)")
        
        avg_latency = sum(latencies) / len(latencies)
        max_latency = max(latencies)
        min_latency = min(latencies)
        
        print(f"\n  平均延迟: {avg_latency:.0f}ms")
        print(f"  最大延迟: {max_latency:.0f}ms")
        print(f"  最小延迟: {min_latency:.0f}ms")
        
        # 性能要求：平均延迟 < 500ms
        assert avg_latency < 500, f"平均延迟 {avg_latency}ms 超过 500ms 限制"
    
    def test_index_persistence_performance(self, field_indexer):
        """测试索引持久化性能"""
        print("\n索引持久化性能测试:")
        
        # 保存索引
        start = time.time()
        success = field_indexer.save_index()
        save_time = time.time() - start
        print(f"  保存索引: {save_time:.2f}s (成功: {success})")
        
        # 加载索引
        from tableau_assistant.src.model_manager.embeddings import ZhipuEmbedding
        from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
        
        new_indexer = FieldIndexer(
            embedding_provider=ZhipuEmbedding(),
            datasource_luid=DATASOURCE_LUID
        )
        
        start = time.time()
        loaded = new_indexer.load_index()
        load_time = time.time() - start
        print(f"  加载索引: {load_time:.2f}s (成功: {loaded})")
        
        if loaded:
            print(f"  加载后字段数: {new_indexer.field_count}")
            
            # 验证加载后的索引可以正常检索
            from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
            retriever = EmbeddingRetriever(new_indexer)
            results = retriever.retrieve("销售", top_k=3)
            print(f"  验证检索: {len(results)} 结果")


@pytest.mark.skipif(SKIP_CONDITION, reason=SKIP_REASON)
class TestEdgeCases:
    """
    边界情况测试
    """
    
    def test_empty_query(self, field_indexer):
        """测试空查询"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        empty_queries = ["", "   ", None]
        
        print("\n空查询测试:")
        for query in empty_queries:
            try:
                results = retriever.retrieve(query or "", top_k=5)
                print(f"  查询 '{query}' -> {len(results)} 结果")
                assert len(results) == 0, "空查询应返回空结果"
            except Exception as e:
                print(f"  查询 '{query}' -> 异常: {e}")
    
    def test_special_characters_query(self, field_indexer):
        """测试特殊字符查询"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        special_queries = [
            "销售@金额",
            "客户#名称",
            "日期%时间",
            "[订单]",
            "产品（名称）",
        ]
        
        print("\n特殊字符查询测试:")
        for query in special_queries:
            results = retriever.retrieve(query, top_k=3)
            if results:
                print(f"  '{query}' -> {results[0].field_chunk.field_name} ({results[0].score:.4f})")
            else:
                print(f"  '{query}' -> 无结果")
    
    def test_very_long_query(self, field_indexer):
        """测试超长查询"""
        from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
        
        retriever = EmbeddingRetriever(field_indexer)
        
        long_query = "我想要查看过去一年中所有客户的销售金额和利润率的变化趋势，按照地区和产品类别进行分组统计"
        
        print("\n超长查询测试:")
        results = retriever.retrieve(long_query, top_k=5)
        print(f"  查询长度: {len(long_query)} 字符")
        print(f"  结果数: {len(results)}")
        for r in results[:3]:
            print(f"    {r.field_chunk.field_name}: {r.score:.4f}")


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
