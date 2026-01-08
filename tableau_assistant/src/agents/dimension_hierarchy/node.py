# -*- coding: utf-8 -*-
"""
维度层级推断 Agent（优化版）

功能：
1. RAG 优先推断：复用历史推断结果
2. LLM 兜底：RAG 未命中时调用 LLM
3. 增量推断：只对新增/变更字段进行推断
4. 延迟加载：只对 RAG 未命中字段查询样例数据
5. 自学习：高置信度结果存入 RAG

使用新的推断系统：
- DimensionHierarchyInference: 主推断类
- DimensionPatternFAISS: FAISS 向量索引
- DimensionHierarchyCacheStorage: 缓存存储
- DimensionRAGRetriever: RAG 检索器

输出：DimensionHierarchyResult 模型

Requirements: 1.1, 1.2, 1.3, 1.4
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional, Callable, Awaitable

from tableau_assistant.src.infra.storage.data_model import DataModel
from tableau_assistant.src.agents.dimension_hierarchy.models import (
    DimensionHierarchyResult,
    DimensionAttributes,
)

logger = logging.getLogger(__name__)

# 默认索引路径
DEFAULT_INDEX_PATH = "data/indexes/dimension_patterns"


# ═══════════════════════════════════════════════════════════════════════════
# 全局单例（延迟初始化）
# ═══════════════════════════════════════════════════════════════════════════

_inference_instance = None
_inference_lock = asyncio.Lock()


async def _get_inference_instance():
    """
    获取 DimensionHierarchyInference 单例实例
    
    延迟初始化，首次调用时创建实例。
    """
    global _inference_instance
    
    if _inference_instance is not None:
        return _inference_instance
    
    async with _inference_lock:
        # 双重检查
        if _inference_instance is not None:
            return _inference_instance
        
        try:
            from tableau_assistant.src.infra.ai.embeddings import EmbeddingProviderFactory
            from tableau_assistant.src.agents.dimension_hierarchy.faiss_store import (
                DimensionPatternFAISS,
                DEFAULT_DIMENSION,
            )
            from tableau_assistant.src.agents.dimension_hierarchy.cache_storage import (
                DimensionHierarchyCacheStorage,
            )
            from tableau_assistant.src.agents.dimension_hierarchy.rag_retriever import (
                DimensionRAGRetriever,
            )
            from tableau_assistant.src.agents.dimension_hierarchy.inference import (
                DimensionHierarchyInference,
            )
            
            # 获取 Embedding 提供者
            embedding_provider = EmbeddingProviderFactory.get_default()
            if embedding_provider is None:
                logger.warning("未配置 Embedding API Key，使用降级模式（仅 LLM）")
                return None
            
            # 创建 FAISS 存储
            faiss_store = DimensionPatternFAISS(
                embedding_provider=embedding_provider,
                index_path=DEFAULT_INDEX_PATH,
                dimension=DEFAULT_DIMENSION,
            )
            faiss_store.load_or_create()
            
            # 创建缓存存储
            cache_storage = DimensionHierarchyCacheStorage()
            
            # 创建 RAG 检索器
            rag_retriever = DimensionRAGRetriever(
                faiss_store=faiss_store,
                cache_storage=cache_storage,
            )
            
            # 创建推断实例
            _inference_instance = DimensionHierarchyInference(
                faiss_store=faiss_store,
                cache_storage=cache_storage,
                rag_retriever=rag_retriever,
            )
            
            logger.info("DimensionHierarchyInference 实例已创建")
            return _inference_instance
            
        except Exception as e:
            logger.error(f"创建 DimensionHierarchyInference 实例失败: {e}")
            return None


# ═══════════════════════════════════════════════════════════════════════════
# 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def _convert_fields_to_dicts(dimension_fields: List[Any]) -> List[Dict[str, Any]]:
    """
    将 FieldMetadata 对象列表转换为字典列表
    
    Args:
        dimension_fields: FieldMetadata 对象列表
    
    Returns:
        字典列表，每个字典包含 field_name, field_caption, data_type 等
    
    Note:
        unique_count 语义：None 表示未知，0 表示真实的 0 个唯一值
    """
    result = []
    for f in dimension_fields:
        field_dict = {
            "field_name": f.name,
            "field_caption": f.fieldCaption,
            "data_type": f.dataType,
        }
        # 可选字段 - 使用 is not None 判断，保留 0 值的语义
        if hasattr(f, "sample_values") and f.sample_values:
            field_dict["sample_values"] = f.sample_values[:10]
        if hasattr(f, "unique_count") and f.unique_count is not None:
            field_dict["unique_count"] = f.unique_count
        
        result.append(field_dict)
    
    return result


def _update_fields_with_hierarchy(
    data_model: DataModel,
    result: DimensionHierarchyResult,
) -> None:
    """
    将维度层级信息注入到 DataModel 的各个 FieldMetadata 对象
    
    Args:
        data_model: DataModel 对象
        result: 推断结果
    """
    for field_name, attrs in result.dimension_hierarchy.items():
        field = data_model.get_field(field_name)
        if field:
            field.category = attrs.category
            field.category_detail = attrs.category_detail
            field.level = attrs.level
            field.granularity = attrs.granularity
            field.parent_dimension = attrs.parent_dimension
            field.child_dimension = attrs.child_dimension
    
    logger.debug(f"已将维度层级信息注入到 {len(result.dimension_hierarchy)} 个字段")


async def _create_sample_value_fetcher(
    data_model: DataModel,
    datasource_luid: str,
    auth_context: Optional[Any] = None,
) -> Callable[[List[str]], Awaitable[Dict[str, Dict[str, Any]]]]:
    """
    创建样例值获取函数（真正的延迟加载）
    
    只对 RAG 未命中的字段调用 Tableau API 获取样例数据。
    
    Args:
        data_model: DataModel 对象
        datasource_luid: 数据源 LUID
        auth_context: Tableau 认证上下文（可选）
    
    Returns:
        异步函数，接收字段名列表，返回 {field_name: {"sample_values": [...], "unique_count": int}}
    """
    async def fetcher(field_names: List[str]) -> Dict[str, Dict[str, Any]]:
        """获取指定字段的样例值和唯一值数量（延迟加载）"""
        if not field_names:
            return {}
        
        # 首先尝试从 data_model 中获取已有的样例数据
        result: Dict[str, Dict[str, Any]] = {}
        fields_to_fetch = []
        
        for field_name in field_names:
            field = data_model.get_field(field_name)
            if field and hasattr(field, "sample_values") and field.sample_values:
                # 已有样例数据，直接使用（包含 unique_count）
                result[field_name] = {
                    "sample_values": field.sample_values[:10],
                    "unique_count": getattr(field, "unique_count", None) or 0,
                }
            else:
                # 需要从 Tableau API 获取
                fields_to_fetch.append(field_name)
        
        # 如果有需要获取的字段，调用 Tableau API
        if fields_to_fetch and auth_context:
            try:
                from tableau_assistant.src.platforms.tableau import fetch_dimension_samples_for_fields
                
                # 获取一个度量字段用于 TOP 过滤
                measures = data_model.get_measures()
                measure_field = measures[0].name if measures else None
                
                if measure_field:
                    logger.info(f"延迟加载样例数据: {len(fields_to_fetch)} 个字段")
                    
                    samples_dict = await fetch_dimension_samples_for_fields(
                        api_key=auth_context.api_key,
                        domain=auth_context.domain,
                        datasource_luid=datasource_luid,
                        field_names=fields_to_fetch,
                        measure_field=measure_field,
                        site=auth_context.site,
                    )
                    
                    # 合并结果（包含 sample_values 和 unique_count）
                    for field_name, data in samples_dict.items():
                        sample_values = data.get("sample_values", [])
                        unique_count = data.get("unique_count", 0)
                        
                        result[field_name] = {
                            "sample_values": sample_values[:10] if sample_values else [],
                            "unique_count": unique_count,
                        }
                        
                        # 同时更新 data_model 中的字段（缓存）
                        field = data_model.get_field(field_name)
                        if field:
                            field.sample_values = sample_values
                            field.unique_count = unique_count
                    
                    logger.info(f"延迟加载完成: 获取到 {len(samples_dict)} 个字段的样例")
                else:
                    logger.warning("无度量字段，无法获取样例数据")
                    
            except Exception as e:
                logger.warning(f"延迟加载样例数据失败: {e}")
        
        return result
    
    return fetcher


# ═══════════════════════════════════════════════════════════════════════════
# 主节点函数
# ═══════════════════════════════════════════════════════════════════════════

async def dimension_hierarchy_node(
    data_model: DataModel,
    datasource_luid: Optional[str] = None,
    logical_table_id: Optional[str] = None,
    force_refresh: bool = False,
    skip_rag_store: bool = False,
    auth_context: Optional[Any] = None,  # Tableau 认证上下文（用于延迟加载样例数据）
    **kwargs,  # 兼容旧参数
) -> DimensionHierarchyResult:
    """
    维度层级推断节点（优化版）
    
    使用 RAG 优先 + LLM 兜底 + 延迟加载样例数据的推断策略。
    自动检测多表数据源并分发到多表推断逻辑。
    
    Args:
        data_model: DataModel 对象（包含字段元数据）
        datasource_luid: 数据源 LUID（用于缓存和 RAG 存储）
        logical_table_id: 逻辑表 ID（可选，多表数据源时使用）
        force_refresh: 是否强制刷新（跳过缓存）
        skip_rag_store: 是否跳过 RAG 存储
        auth_context: Tableau 认证上下文（用于延迟加载样例数据）
        **kwargs: 兼容旧参数（stream, use_cache, incremental 等）
    
    Returns:
        DimensionHierarchyResult 模型对象
    """
    logger.info("维度层级推断开始（优化版）")
    
    # 自动检测多表数据源，分发到多表推断逻辑（符合 design.md 要求）
    is_multi_table = getattr(data_model, "is_multi_table", False)
    logical_tables = getattr(data_model, "logical_tables", None)
    
    if is_multi_table and logical_tables and len(logical_tables) > 1 and logical_table_id is None:
        logger.info(f"检测到多表数据源 ({len(logical_tables)} 个逻辑表)，使用多表推断模式")
        return await dimension_hierarchy_node_multi_table(
            data_model=data_model,
            datasource_luid=datasource_luid,
            force_refresh=force_refresh,
            skip_rag_store=skip_rag_store,
            auth_context=auth_context,
            **kwargs,
        )
    
    # 获取维度字段
    dimension_fields = data_model.get_dimensions()
    if not dimension_fields:
        logger.warning("未找到维度字段")
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    logger.info(f"待推断维度字段: {len(dimension_fields)} 个")
    
    # 获取推断实例
    inference = await _get_inference_instance()
    
    if inference is None:
        # 降级模式：使用旧的 LLM 推断
        logger.warning("推断实例不可用，使用降级模式")
        return await _fallback_inference(data_model, datasource_luid)
    
    # 转换字段格式
    fields = _convert_fields_to_dicts(dimension_fields)
    
    # 创建样例值获取函数（真正的延迟加载）
    sample_value_fetcher = await _create_sample_value_fetcher(
        data_model=data_model,
        datasource_luid=datasource_luid or "unknown",
        auth_context=auth_context,
    )
    
    # 执行推断
    try:
        result = await inference.infer(
            datasource_luid=datasource_luid or "unknown",
            fields=fields,
            logical_table_id=logical_table_id,
            force_refresh=force_refresh,
            skip_rag_store=skip_rag_store,
            sample_value_fetcher=sample_value_fetcher,
        )
        
        # 获取统计信息
        stats = inference.get_stats()
        logger.info(
            f"维度层级推断完成: {len(result.dimension_hierarchy)} 个维度, "
            f"RAG 命中率: {stats['rag_hit_rate']:.1%}, "
            f"耗时: {stats['total_time_ms']:.0f}ms"
        )
        
        # 将维度层级信息注入到 data_model
        _update_fields_with_hierarchy(data_model, result)
        
        # 设置 merged_hierarchy（兼容旧接口）
        if hasattr(data_model, "merged_hierarchy"):
            data_model.merged_hierarchy = result.dimension_hierarchy
        
        return result
        
    except Exception as e:
        logger.error(f"维度层级推断失败: {e}", exc_info=True)
        return DimensionHierarchyResult(dimension_hierarchy={})



async def dimension_hierarchy_node_multi_table(
    data_model: DataModel,
    datasource_luid: Optional[str] = None,
    force_refresh: bool = False,
    skip_rag_store: bool = False,
    auth_context: Optional[Any] = None,  # Tableau 认证上下文
    **kwargs,
) -> DimensionHierarchyResult:
    """
    多表数据源维度层级推断节点
    
    按逻辑表分组，并发推断，合并结果。
    
    Args:
        data_model: DataModel 对象（包含多个逻辑表）
        datasource_luid: 数据源 LUID
        force_refresh: 是否强制刷新
        skip_rag_store: 是否跳过 RAG 存储
        auth_context: Tableau 认证上下文（用于延迟加载样例数据）
        **kwargs: 兼容旧参数
    
    Returns:
        DimensionHierarchyResult 模型对象（合并后的结果）
    """
    logger.info("多表数据源维度层级推断开始")
    
    # 获取所有逻辑表（List[LogicalTable]）
    logical_tables = getattr(data_model, "logical_tables", None)
    if not logical_tables:
        # 单表数据源，直接调用单表推断
        return await dimension_hierarchy_node(
            data_model=data_model,
            datasource_luid=datasource_luid,
            force_refresh=force_refresh,
            skip_rag_store=skip_rag_store,
            auth_context=auth_context,
            **kwargs,
        )
    
    logger.info(f"检测到 {len(logical_tables)} 个逻辑表")
    
    # 获取推断实例
    inference = await _get_inference_instance()
    
    if inference is None:
        logger.warning("推断实例不可用，使用降级模式")
        return await _fallback_inference(data_model, datasource_luid)
    
    # 按逻辑表分组字段（修复：logical_tables 是 List[LogicalTable]，不是 Dict）
    table_fields: Dict[str, List[Dict[str, Any]]] = {}
    
    for table in logical_tables:
        # LogicalTable 对象有 logicalTableId 属性
        table_id = table.logicalTableId
        # 使用 DataModel.get_fields_by_table() 方法获取该表的字段
        fields = data_model.get_fields_by_table(table_id)
        # 只处理维度字段
        dimension_fields = [f for f in fields if f.role == "dimension"]
        if dimension_fields:
            table_fields[table_id] = _convert_fields_to_dicts(dimension_fields)
            logger.debug(f"逻辑表 {table.caption} ({table_id}): {len(dimension_fields)} 个维度字段")
    
    if not table_fields:
        logger.warning("未找到任何逻辑表字段")
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    # 创建样例值获取函数（真正的延迟加载）
    sample_value_fetcher = await _create_sample_value_fetcher(
        data_model=data_model,
        datasource_luid=datasource_luid or "unknown",
        auth_context=auth_context,
    )
    
    # 并发推断各逻辑表
    async def infer_table(table_id: str, fields: List[Dict[str, Any]]) -> Dict[str, DimensionAttributes]:
        """推断单个逻辑表"""
        try:
            result = await inference.infer(
                datasource_luid=datasource_luid or "unknown",
                fields=fields,
                logical_table_id=table_id,
                force_refresh=force_refresh,
                skip_rag_store=skip_rag_store,
                sample_value_fetcher=sample_value_fetcher,
            )
            return dict(result.dimension_hierarchy)
        except Exception as e:
            logger.error(f"逻辑表 {table_id} 推断失败: {e}")
            return {}
    
    # 并发执行
    table_ids = list(table_fields.keys())
    tasks = [
        infer_table(table_id, fields)
        for table_id, fields in table_fields.items()
    ]
    
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 合并结果（检测同名字段冲突）
    merged_hierarchy: Dict[str, DimensionAttributes] = {}
    field_source: Dict[str, str] = {}  # 记录字段来源的表 ID
    conflict_count = 0
    
    for idx, result in enumerate(results):
        table_id = table_ids[idx]
        if isinstance(result, Exception):
            logger.error(f"逻辑表推断异常: {result}")
        elif isinstance(result, dict):
            for field_name, attrs in result.items():
                if field_name in merged_hierarchy:
                    # 检测到同名字段冲突
                    conflict_count += 1
                    existing_table = field_source.get(field_name, "unknown")
                    logger.warning(
                        f"多表合并冲突: 字段 '{field_name}' 同时存在于表 "
                        f"'{existing_table}' 和 '{table_id}'，使用后者覆盖"
                    )
                merged_hierarchy[field_name] = attrs
                field_source[field_name] = table_id
    
    if conflict_count > 0:
        logger.warning(f"多表合并完成，共 {conflict_count} 个字段冲突被覆盖")
    
    logger.info(f"多表推断完成: 共 {len(merged_hierarchy)} 个维度")
    
    # 将维度层级信息注入到 data_model
    final_result = DimensionHierarchyResult(dimension_hierarchy=merged_hierarchy)
    _update_fields_with_hierarchy(data_model, final_result)
    
    # 设置 merged_hierarchy
    if hasattr(data_model, "merged_hierarchy"):
        data_model.merged_hierarchy = merged_hierarchy
    
    return final_result


# ═══════════════════════════════════════════════════════════════════════════
# 降级模式（无 RAG 时使用）
# ═══════════════════════════════════════════════════════════════════════════

# 降级模式的最大字段数（与 llm_inference.MAX_FIELDS_PER_INFERENCE 保持一致）
FALLBACK_MAX_FIELDS_PER_BATCH = 30


async def _fallback_inference(
    data_model: DataModel,
    datasource_luid: Optional[str] = None,
) -> DimensionHierarchyResult:
    """
    降级推断模式（无 RAG 时使用）
    
    直接调用 LLM 推断，不使用 RAG 和缓存。
    支持分批处理，避免字段数超过 30 时报错。
    """
    from tableau_assistant.src.agents.dimension_hierarchy.llm_inference import (
        infer_dimensions_once,
    )
    
    dimension_fields = data_model.get_dimensions()
    if not dimension_fields:
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    # 转换字段格式
    fields = _convert_fields_to_dicts(dimension_fields)
    
    # 分批推断（每批最多 30 个字段）
    all_results: Dict[str, DimensionAttributes] = {}
    
    try:
        for i in range(0, len(fields), FALLBACK_MAX_FIELDS_PER_BATCH):
            batch = fields[i:i + FALLBACK_MAX_FIELDS_PER_BATCH]
            logger.info(f"降级模式分批推断: 第 {i // FALLBACK_MAX_FIELDS_PER_BATCH + 1} 批, {len(batch)} 个字段")
            
            result = await infer_dimensions_once(batch)
            all_results.update(result.dimension_hierarchy)
        
        final_result = DimensionHierarchyResult(dimension_hierarchy=all_results)
        
        # 将维度层级信息注入到 data_model
        _update_fields_with_hierarchy(data_model, final_result)
        
        return final_result
        
    except Exception as e:
        logger.error(f"降级推断失败: {e}")
        return DimensionHierarchyResult(dimension_hierarchy=all_results if all_results else {})


# ═══════════════════════════════════════════════════════════════════════════
# 单字段推断函数（供 FieldMapper 调用）
# ═══════════════════════════════════════════════════════════════════════════

async def infer_single_field(
    field_name: str,
    field_caption: str,
    data_type: str,
    sample_values: List[str],
    unique_count: int,
    datasource_luid: Optional[str] = None,
    store_result: bool = True,
) -> Optional[DimensionAttributes]:
    """
    推断单个字段的维度层级
    
    供 FieldMapper 调用，用于获取单个字段的层级信息。
    
    Args:
        field_name: 技术字段名
        field_caption: 显示名称
        data_type: 数据类型
        sample_values: 样本值列表
        unique_count: 唯一值数量
        datasource_luid: 数据源标识（可选）
        store_result: 是否存储结果到 RAG
    
    Returns:
        DimensionAttributes 对象，如果推断失败则返回 None
    """
    logger.info(f"单字段推断: {field_caption}")
    
    # 获取推断实例
    inference = await _get_inference_instance()
    
    if inference is None:
        # 降级模式
        from tableau_assistant.src.agents.dimension_hierarchy.llm_inference import (
            infer_dimensions_once,
        )
        
        fields = [{
            "field_name": field_name,
            "field_caption": field_caption,
            "data_type": data_type,
            "sample_values": sample_values[:10] if sample_values else [],
            "unique_count": unique_count,
        }]
        
        try:
            result = await infer_dimensions_once(fields)
            return result.dimension_hierarchy.get(field_name)
        except Exception as e:
            logger.error(f"单字段推断失败: {e}")
            return None
    
    # 使用新推断系统
    fields = [{
        "field_name": field_name,
        "field_caption": field_caption,
        "data_type": data_type,
        "sample_values": sample_values[:10] if sample_values else [],
        "unique_count": unique_count,
    }]
    
    try:
        result = await inference.infer(
            datasource_luid=datasource_luid or "single_field",
            fields=fields,
            skip_rag_store=not store_result,
        )
        
        attrs = result.dimension_hierarchy.get(field_name)
        
        if attrs:
            logger.debug(
                f"单字段推断完成: {field_caption} -> "
                f"{attrs.category_detail}"
            )
        
        return attrs
        
    except Exception as e:
        logger.error(f"单字段推断失败: {field_caption}, {e}")
        return None


# ═══════════════════════════════════════════════════════════════════════════
# 统计接口
# ═══════════════════════════════════════════════════════════════════════════

async def get_inference_stats() -> Dict[str, Any]:
    """
    获取推断统计数据
    
    Returns:
        统计数据字典
    """
    inference = await _get_inference_instance()
    
    if inference is None:
        return {"error": "推断实例不可用"}
    
    return inference.get_stats()


async def reset_inference_stats() -> None:
    """重置推断统计数据"""
    inference = await _get_inference_instance()
    
    if inference:
        inference.reset_stats()


__all__ = [
    "dimension_hierarchy_node",
    "dimension_hierarchy_node_multi_table",
    "infer_single_field",
    "get_inference_stats",
    "reset_inference_stats",
]
