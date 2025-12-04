"""
性能诊断脚本 - 检查各环节耗时
"""
import os
import time
from dotenv import load_dotenv

load_dotenv()

def main():
    print("=== 环境变量检查 ===")
    domain = os.getenv("TABLEAU_DOMAIN") or os.getenv("TABLEAU_BASE_URL")
    luid = os.getenv("DATASOURCE_LUID")
    site = os.getenv("TABLEAU_SITE")
    zhipu_key = os.getenv("ZHIPUAI_API_KEY")
    
    print(f"TABLEAU_DOMAIN: {domain[:50] if domain else '未设置'}...")
    print(f"DATASOURCE_LUID: {luid or '未设置'}")
    print(f"ZHIPUAI_API_KEY: {'已设置' if zhipu_key else '未设置'}")
    
    # 1. Tableau 认证
    print("\n=== 1. Tableau 认证测试 ===")
    start = time.time()
    try:
        from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
        ctx = _get_tableau_context_from_env()
        auth_time = time.time() - start
        print(f"认证耗时: {auth_time:.2f}s")
        print(f"Token: {'已获取' if ctx.get('api_key') else '获取失败'}")
        api_key = ctx.get('api_key')
    except Exception as e:
        print(f"认证失败: {e}")
        return
    
    # 2. VizQL 元数据获取（不含样本）
    print("\n=== 2. VizQL 元数据获取（不含样本）===")
    start = time.time()
    try:
        from tableau_assistant.src.bi_platforms.tableau.vizql_client import VizQLClient, VizQLClientConfig
        
        config = VizQLClientConfig(base_url=domain, timeout=30)
        client = VizQLClient(config=config)
        
        # 2.1 read-metadata
        start_meta = time.time()
        meta_response = client.read_metadata(datasource_luid=luid, api_key=api_key, site=site)
        meta_time = time.time() - start_meta
        fields = meta_response.get("data", [])
        print(f"  read-metadata 耗时: {meta_time:.2f}s, 字段数: {len(fields)}")
        
        # 2.2 get-datasource-model
        start_model = time.time()
        model_response = client.get_datasource_model(datasource_luid=luid, api_key=api_key, site=site)
        model_time = time.time() - start_model
        tables = model_response.get("logicalTables", [])
        print(f"  get-datasource-model 耗时: {model_time:.2f}s, 表数: {len(tables)}")
        
        client.close()
        
        total_vizql = time.time() - start
        print(f"VizQL 总耗时: {total_vizql:.2f}s")
        
    except Exception as e:
        print(f"VizQL 获取失败: {e}")
        import traceback
        traceback.print_exc()
        fields = []
    
    # 3. Embedding 测试
    print("\n=== 3. Embedding 测试 ===")
    try:
        from tableau_assistant.src.model_manager.embeddings import ZhipuEmbedding
        provider = ZhipuEmbedding()
        
        # 3.1 单次 embedding
        start = time.time()
        vec = provider.embed_query("测试查询")
        single_time = time.time() - start
        print(f"  单次 Embedding 耗时: {single_time:.2f}s, 维度: {len(vec)}")
        
        # 3.2 批量 embedding (5个)
        texts = ["销售金额", "客户名称", "订单日期", "产品类别", "利润率"]
        start = time.time()
        vecs = provider.embed_documents(texts)
        batch_time = time.time() - start
        print(f"  批量 Embedding (5个) 耗时: {batch_time:.2f}s, 平均: {batch_time/5:.2f}s")
        
    except Exception as e:
        print(f"Embedding 失败: {e}")
        import traceback
        traceback.print_exc()
    
    # 4. 索引构建测试（使用少量字段）
    print("\n=== 4. 索引构建测试（前10个字段）===")
    if fields:
        from dataclasses import dataclass
        from typing import List, Optional
        
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
        
        # 只取前10个字段测试
        test_fields = []
        for f in fields[:10]:
            test_fields.append(FieldMetadata(
                name=f.get("fieldCaption") or f.get("fieldName", ""),
                fieldCaption=f.get("fieldCaption") or f.get("fieldName", ""),
                role="dimension" if not f.get("defaultAggregation") else "measure",
                dataType=f.get("dataType", "STRING"),
                columnClass=f.get("columnClass"),
            ))
        
        try:
            from tableau_assistant.src.capabilities.rag.field_indexer import FieldIndexer
            
            indexer = FieldIndexer(embedding_provider=provider, use_cache=False)
            
            start = time.time()
            indexer.index_fields(test_fields)
            index_time = time.time() - start
            print(f"  索引 {len(test_fields)} 个字段耗时: {index_time:.2f}s")
            print(f"  平均每字段: {index_time/len(test_fields):.2f}s")
            
        except Exception as e:
            print(f"索引构建失败: {e}")
            import traceback
            traceback.print_exc()
    
    # 5. 检索测试
    print("\n=== 5. 检索测试 ===")
    if fields:
        try:
            from tableau_assistant.src.capabilities.rag.retriever import EmbeddingRetriever
            
            retriever = EmbeddingRetriever(indexer)
            
            queries = ["销售", "客户", "日期"]
            for query in queries:
                start = time.time()
                results = retriever.retrieve(query, top_k=5)
                search_time = time.time() - start
                top_name = results[0].field_chunk.field_name if results else "无"
                print(f"  查询 '{query}': {search_time*1000:.0f}ms, top-1: {top_name}")
                
        except Exception as e:
            print(f"检索失败: {e}")
            import traceback
            traceback.print_exc()
    
    print("\n=== 诊断完成 ===")


if __name__ == "__main__":
    main()
