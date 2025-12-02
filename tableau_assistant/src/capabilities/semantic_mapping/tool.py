"""
Semantic Map Fields Tool - 语义字段映射工具（RAG+LLM）

封装 SemanticMapper 组件为 LangChain 工具，实现智能字段映射。

特性：
- RAG 向量检索：快速找到语义相似的候选字段
- LLM 语义判断：理解业务上下文，选择最佳匹配
- Store 缓存：缓存映射结果，提高性能
- 自动重试：处理网络错误
"""
import json
import logging
from typing import Dict, Any, Optional
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


# 定义需要重试的异常类型
RETRIABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    RuntimeError,
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True
)
async def _map_field_with_retry(
    semantic_mapper,
    business_term: str,
    question_context: str,
    top_k: int,
    threshold: float,
    use_llm: bool
) -> Dict[str, Any]:
    """带重试机制的字段映射函数"""
    try:
        result = semantic_mapper.map_field(
            business_term=business_term,
            question_context=question_context,
            top_k=top_k,
            threshold=threshold,
            use_llm=use_llm
        )
        return result
    except Exception as e:
        logger.error(f"字段映射失败: {e}")
        raise


@tool
async def semantic_map_fields(
    business_term: str,
    question_context: Optional[str] = None,
    top_k: int = 5,
    threshold: float = 0.3,
    use_llm: bool = True,
    use_cache: bool = True
) -> Dict[str, Any]:
    """Map business terms to technical field names using RAG+LLM hybrid model.
    
    This tool uses a two-stage approach for intelligent field mapping:
    
    Stage 1 - RAG Vector Retrieval:
    - Uses FAISS vector database for semantic similarity search
    - Retrieves top-K candidate fields based on embedding similarity
    
    Stage 2 - LLM Semantic Judgment:
    - Understands business context and question semantics
    - Considers field descriptions, roles, and data types
    
    Args:
        business_term: Business term to map (e.g., "销售额", "Sales Amount")
        question_context: Full question context (optional but recommended)
        top_k: Number of candidate fields to retrieve (default: 5)
        threshold: Similarity threshold for filtering candidates (0-1, default: 0.3)
        use_llm: Whether to use LLM for semantic judgment (default: True)
        use_cache: Whether to use cached mapping results (default: True)
    
    Returns:
        Dictionary containing:
        - matched_field: The matched technical field name (or None if no match)
        - confidence: Confidence score (0-1)
        - reasoning: Explanation of why this field was selected
        - alternatives: List of alternative field matches with scores
    """
    from langgraph.runtime import get_runtime
    from tableau_assistant.src.capabilities.semantic_mapping.semantic_mapper import SemanticMapper
    from tableau_assistant.src.capabilities.semantic_mapping.embeddings_provider import EmbeddingsProvider
    from tableau_assistant.src.bi_platforms.tableau.models import select_model
    from tableau_assistant.src.models.metadata import Metadata
    
    runtime = get_runtime()
    store = runtime.store
    
    cache_key = f"mapping_{business_term}_{question_context or 'no_context'}"
    
    if use_cache:
        try:
            cached_result = await store.get(("semantic_mapping", cache_key))
            if cached_result:
                logger.info(f"✅ 使用缓存的映射结果: '{business_term}' -> '{cached_result.get('matched_field')}'")
                return cached_result
        except Exception as e:
            logger.warning(f"读取缓存失败: {e}")
    
    try:
        metadata_dict = await store.get(("metadata", "current"))
        if not metadata_dict:
            from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
            metadata_manager = MetadataManager(runtime)
            metadata_dict = await metadata_manager.get_metadata_async(use_cache=True, enhance=False)
            metadata_dict = metadata_dict.model_dump()
        
        metadata = Metadata(**metadata_dict)
        embeddings_provider = EmbeddingsProvider(provider="openai")
        llm = select_model(provider="openai", model_name="gpt-4o-mini")
        
        semantic_mapper = SemanticMapper(
            metadata=metadata,
            llm=llm,
            embeddings_provider=embeddings_provider
        )
        
        result = await _map_field_with_retry(
            semantic_mapper=semantic_mapper,
            business_term=business_term,
            question_context=question_context or "",
            top_k=top_k,
            threshold=threshold,
            use_llm=use_llm
        )
        
        if use_cache and result.get("matched_field"):
            try:
                await store.put(namespace=("semantic_mapping", cache_key), 
                    value={**result, "_cached_at": time.time()},ttl=3600)  # 1小时
            except Exception as e:
                logger.warning(f"保存缓存失败: {e}")
        
        logger.info(f"✅ 字段映射成功: '{business_term}' -> '{result.get('matched_field')}'")
        return result
    
    except Exception as e:
        logger.error(f"❌ 字段映射失败: {e}")
        return {
            "matched_field": None,
            "confidence": 0.0,
            "reasoning": f"映射失败: {str(e)}",
            "alternatives": []
        }


__all__ = ["semantic_map_fields"]
