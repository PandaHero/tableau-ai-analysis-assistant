"""
维度层级推断 Agent

功能：
1. 根据字段元数据推断维度层级
2. 识别维度的 category、level、granularity
3. 识别父子关系
4. RAG 增强：复用历史推断结果作为 few-shot 示例
5. 缓存机制：避免重复推断，支持增量推断

使用 base 包提供的基础能力：
- get_llm(): 获取 LLM 实例
- stream_llm_call(): 流式调用 LLM
- invoke_llm(): 非流式调用 LLM
- parse_json_response(): 解析 JSON 响应

输出：DimensionHierarchyResult 模型
"""
import json
import logging
import hashlib
from datetime import datetime, timedelta
from dataclasses import dataclass, field
from typing import Dict, Any, List, Optional, Set

from tableau_assistant.src.core.models import (
    Metadata,
    DimensionHierarchyResult,
    DimensionAttributes,
)
from tableau_assistant.src.agents.base import (
    get_llm,
    stream_llm_call,
    stream_llm_call_with_batch_id,
    invoke_llm,
    parse_json_response,
)
from .prompt import DIMENSION_HIERARCHY_PROMPT

logger = logging.getLogger(__name__)

# 缓存默认 TTL（7 天）
DEFAULT_CACHE_TTL_DAYS = 7


# ═══════════════════════════════════════════════════════════════════════════
# 缓存数据结构
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class HierarchyCacheEntry:
    """
    维度层级缓存条目
    
    Attributes:
        datasource_luid: 数据源 LUID
        field_hash: 字段列表的哈希值（用于检测字段变化）
        hierarchy_data: 推断结果（字典格式）
        created_at: 创建时间
        ttl_days: 过期天数
    """
    datasource_luid: str
    field_hash: str
    hierarchy_data: Dict[str, Any]
    created_at: datetime = field(default_factory=datetime.now)
    ttl_days: int = DEFAULT_CACHE_TTL_DAYS
    
    @property
    def is_expired(self) -> bool:
        """检查缓存是否过期"""
        expiry_time = self.created_at + timedelta(days=self.ttl_days)
        return datetime.now() > expiry_time
    
    @property
    def cached_fields(self) -> Set[str]:
        """获取缓存中的字段名集合"""
        return set(self.hierarchy_data.keys())
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典（用于存储）"""
        return {
            "datasource_luid": self.datasource_luid,
            "field_hash": self.field_hash,
            "hierarchy_data": self.hierarchy_data,
            "created_at": self.created_at.isoformat(),
            "ttl_days": self.ttl_days,
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "HierarchyCacheEntry":
        """从字典创建（用于读取）"""
        return cls(
            datasource_luid=data["datasource_luid"],
            field_hash=data["field_hash"],
            hierarchy_data=data["hierarchy_data"],
            created_at=datetime.fromisoformat(data["created_at"]),
            ttl_days=data.get("ttl_days", DEFAULT_CACHE_TTL_DAYS),
        )


# ═══════════════════════════════════════════════════════════════════════════
# 缓存辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def _get_cache_namespace() -> str:
    """获取缓存命名空间"""
    return "dimension_hierarchy_cache"


def _compute_field_hash(dimension_fields: List[Any]) -> str:
    """
    计算字段列表的哈希值
    
    用于检测字段是否发生变化（新增/删除/修改）
    
    Args:
        dimension_fields: 维度字段列表
    
    Returns:
        字段列表的 MD5 哈希值
    """
    # 提取字段关键信息
    field_info = []
    for f in sorted(dimension_fields, key=lambda x: x.name):
        info = {
            "name": f.name,
            "caption": f.fieldCaption,
            "dataType": f.dataType,
            "unique_count": f.unique_count or 0,
        }
        field_info.append(info)
    
    # 计算哈希
    content = json.dumps(field_info, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def _get_store_manager():
    """获取 StoreManager 实例"""
    try:
        from tableau_assistant.src.infra.storage import StoreManager
        return StoreManager()
    except Exception as e:
        logger.warning(f"无法获取 StoreManager: {e}")
        return None


def _get_from_cache(
    datasource_luid: str,
    store_manager=None
) -> Optional[HierarchyCacheEntry]:
    """
    从缓存获取维度层级推断结果
    
    Args:
        datasource_luid: 数据源 LUID
        store_manager: StoreManager 实例（可选）
    
    Returns:
        缓存条目，如果不存在或已过期则返回 None
    """
    if not datasource_luid:
        return None
    
    store = store_manager or _get_store_manager()
    if not store:
        return None
    
    try:
        namespace = (_get_cache_namespace(),)
        
        # 使用 StoreManager.get() 返回 StoreItem
        store_item = store.get(namespace, datasource_luid)
        if not store_item:
            logger.debug(f"缓存未命中: {datasource_luid}")
            return None
        
        # StoreItem.value 是实际的数据字典
        cached_data = store_item.value
        if not cached_data:
            logger.debug(f"缓存数据为空: {datasource_luid}")
            return None
        
        entry = HierarchyCacheEntry.from_dict(cached_data)
        
        # 检查是否过期
        if entry.is_expired:
            logger.info(f"缓存已过期: {datasource_luid}")
            return None
        
        logger.debug(f"缓存命中: {datasource_luid}, {len(entry.hierarchy_data)} 个字段")
        return entry
        
    except Exception as e:
        logger.warning(f"读取缓存失败: {e}")
        return None


def _put_to_cache(
    datasource_luid: str,
    field_hash: str,
    hierarchy_data: Dict[str, Any],
    store_manager=None,
    ttl_days: int = DEFAULT_CACHE_TTL_DAYS
) -> bool:
    """
    将维度层级推断结果存入缓存
    
    Args:
        datasource_luid: 数据源 LUID
        field_hash: 字段列表哈希值
        hierarchy_data: 推断结果
        store_manager: StoreManager 实例（可选）
        ttl_days: 缓存过期天数
    
    Returns:
        是否存储成功
    """
    if not datasource_luid:
        return False
    
    store = store_manager or _get_store_manager()
    if not store:
        return False
    
    try:
        entry = HierarchyCacheEntry(
            datasource_luid=datasource_luid,
            field_hash=field_hash,
            hierarchy_data=hierarchy_data,
            ttl_days=ttl_days,
        )
        
        namespace = (_get_cache_namespace(),)
        ttl_seconds = ttl_days * 24 * 60 * 60
        
        # 使用 StoreManager.put() 方法
        store.put(namespace, datasource_luid, entry.to_dict(), ttl=ttl_seconds)
        logger.info(f"缓存已更新: {datasource_luid}, {len(hierarchy_data)} 个字段")
        return True
        
    except Exception as e:
        logger.warning(f"写入缓存失败: {e}")
        return False


# ═══════════════════════════════════════════════════════════════════════════
# 增量推断辅助函数
# ═══════════════════════════════════════════════════════════════════════════

@dataclass
class IncrementalFields:
    """
    增量字段计算结果
    
    Attributes:
        new_fields: 新增字段名集合
        deleted_fields: 删除字段名集合
        unchanged_fields: 未变化字段名集合
    """
    new_fields: Set[str]
    deleted_fields: Set[str]
    unchanged_fields: Set[str]
    
    @property
    def has_changes(self) -> bool:
        """是否有变化"""
        return len(self.new_fields) > 0 or len(self.deleted_fields) > 0
    
    @property
    def needs_inference(self) -> bool:
        """是否需要推断（有新增字段）"""
        return len(self.new_fields) > 0


def _compute_incremental_fields(
    current_fields: List[Any],
    cache_entry: Optional[HierarchyCacheEntry]
) -> IncrementalFields:
    """
    计算增量字段
    
    比较当前字段与缓存字段，计算新增、删除、未变化的字段。
    
    Args:
        current_fields: 当前维度字段列表
        cache_entry: 缓存条目（可能为 None）
    
    Returns:
        IncrementalFields 对象
    """
    current_field_names = {f.name for f in current_fields}
    
    if cache_entry is None:
        # 无缓存，所有字段都是新增
        return IncrementalFields(
            new_fields=current_field_names,
            deleted_fields=set(),
            unchanged_fields=set()
        )
    
    cached_field_names = cache_entry.cached_fields
    
    # 计算差集
    new_fields = current_field_names - cached_field_names
    deleted_fields = cached_field_names - current_field_names
    unchanged_fields = current_field_names & cached_field_names
    
    logger.debug(
        f"增量计算: 新增={len(new_fields)}, "
        f"删除={len(deleted_fields)}, "
        f"未变化={len(unchanged_fields)}"
    )
    
    return IncrementalFields(
        new_fields=new_fields,
        deleted_fields=deleted_fields,
        unchanged_fields=unchanged_fields
    )


def _filter_fields_by_names(
    fields: List[Any],
    field_names: Set[str]
) -> List[Any]:
    """
    根据字段名过滤字段列表
    
    Args:
        fields: 字段列表
        field_names: 要保留的字段名集合
    
    Returns:
        过滤后的字段列表
    """
    return [f for f in fields if f.name in field_names]


def _merge_hierarchy_results(
    cached_data: Dict[str, Any],
    new_result: DimensionHierarchyResult,
    deleted_fields: Set[str]
) -> Dict[str, DimensionAttributes]:
    """
    合并缓存结果和新推断结果
    
    Args:
        cached_data: 缓存的层级数据（字典格式）
        new_result: 新推断的结果
        deleted_fields: 要删除的字段名集合
    
    Returns:
        合并后的层级字典
    """
    merged = {}
    
    # 1. 添加缓存中未删除的字段
    for field_name, attrs_dict in cached_data.items():
        if field_name not in deleted_fields:
            merged[field_name] = DimensionAttributes(**attrs_dict)
    
    # 2. 添加新推断的字段（覆盖同名字段）
    for field_name, attrs in new_result.dimension_hierarchy.items():
        merged[field_name] = attrs
    
    return merged


# ═══════════════════════════════════════════════════════════════════════════
# 分批推断辅助函数
# ═══════════════════════════════════════════════════════════════════════════

import asyncio

# 默认批次大小
DEFAULT_BATCH_SIZE = 5

# 默认最大并发数（防止 API 限流）
DEFAULT_MAX_CONCURRENCY = 3


def _split_into_batches(
    fields: List[Any],
    batch_size: int = DEFAULT_BATCH_SIZE
) -> List[List[Any]]:
    """
    将字段列表分成多个批次
    
    Args:
        fields: 字段列表
        batch_size: 每批大小
    
    Returns:
        批次列表
    """
    batches = []
    for i in range(0, len(fields), batch_size):
        batches.append(fields[i:i + batch_size])
    return batches


from typing import Callable, Union
from typing_extensions import Protocol


# 带批次标识的回调类型（与 base/node.py 保持一致）
class BatchStreamCallback(Protocol):
    """带批次标识的流式输出回调协议"""
    def __call__(self, batch_id: int, token: str) -> None: ...


class AsyncBatchStreamCallback(Protocol):
    """异步带批次标识的流式输出回调协议"""
    async def __call__(self, batch_id: int, token: str) -> None: ...


BatchStreamCallbackType = Union[BatchStreamCallback, AsyncBatchStreamCallback, None]


async def _infer_single_batch(
    batch_idx: int,
    batch_fields: List[Any],
    rag,
    total_batches: int,
    stream: bool = False,
    on_token: BatchStreamCallbackType = None,
) -> Dict[str, DimensionAttributes]:
    """
    推断单个批次的维度层级
    
    Args:
        batch_idx: 批次索引（从 0 开始）
        batch_fields: 该批次的字段列表
        rag: RAG 组件（可选）
        total_batches: 总批次数
        stream: 是否流式输出
        on_token: 流式输出回调 (batch_id, token) -> None
    
    Returns:
        该批次的推断结果字典 {field_name: DimensionAttributes}
    """
    logger.info(f"推断批次 {batch_idx + 1}/{total_batches}: {len(batch_fields)} 个字段")
    
    # 准备批次的维度信息
    dimensions_info = []
    all_few_shot_examples = []
    
    for field in batch_fields:
        info = {
            "name": field.name,
            "caption": field.fieldCaption,
            "dataType": field.dataType,
            "description": field.description or "",
            "unique_count": field.unique_count or 0,
            "sample_values": (field.sample_values or [])[:5],
        }
        dimensions_info.append(info)
        
        # RAG: 获取相似历史模式
        if rag:
            try:
                rag_context = rag.get_inference_context(
                    field_caption=field.fieldCaption,
                    data_type=field.dataType,
                    sample_values=field.sample_values or [],
                    unique_count=field.unique_count or 0,
                )
                if rag_context.get("has_similar_patterns"):
                    examples = rag_context.get("few_shot_examples", [])[:2]
                    all_few_shot_examples.extend(examples)
            except Exception as e:
                logger.warning(f"RAG 检索失败: {e}")
    
    few_shot_section = _build_few_shot_section(all_few_shot_examples[:3])
    
    # 构建输入数据
    dimensions_str = json.dumps(dimensions_info, ensure_ascii=False, indent=2)
    if few_shot_section:
        dimensions_str = few_shot_section + "\n" + dimensions_str
    
    input_data = {"dimensions": dimensions_str}
    
    try:
        llm = get_llm(agent_name="dimension_hierarchy")
        messages = DIMENSION_HIERARCHY_PROMPT.format_messages(**input_data)
        
        if stream and on_token:
            # 流式输出（带批次标识）
            response = await stream_llm_call_with_batch_id(
                llm, messages, batch_idx, on_token
            )
        else:
            # 非流式
            response = await invoke_llm(llm, messages)
        
        batch_result = parse_json_response(response, DimensionHierarchyResult)
        
        logger.debug(f"批次 {batch_idx + 1} 完成: {len(batch_result.dimension_hierarchy)} 个字段")
        return dict(batch_result.dimension_hierarchy)
        
    except Exception as e:
        logger.error(f"批次 {batch_idx + 1} 推断失败: {e}")
        return {}


async def _batch_inference(
    fields: List[Any],
    rag,
    stream: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    on_token: BatchStreamCallbackType = None,
) -> DimensionHierarchyResult:
    """
    并行分批推断维度层级（支持流式输出）
    
    将字段分成多个批次，并发调用 LLM，然后合并结果。
    使用 semaphore 控制并发数，防止 API 限流。
    
    Args:
        fields: 要推断的字段列表
        rag: RAG 组件（可选）
        stream: 是否流式输出
        batch_size: 每批大小（默认 5）
        max_concurrency: 最大并发数（默认 3）
        on_token: 流式输出回调 (batch_id: int, token: str) -> None
                  并行时每个批次的 token 都会带上 batch_id
    
    Returns:
        合并后的 DimensionHierarchyResult
    
    Example:
        # 并行 + 流式输出
        def handle_token(batch_id: int, token: str):
            print(f"[Batch {batch_id}] {token}", end="")
        
        result = await _batch_inference(
            fields, rag, stream=True, on_token=handle_token
        )
    """
    if not fields:
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    batches = _split_into_batches(fields, batch_size)
    total_batches = len(batches)
    logger.info(
        f"并行分批推断: {len(fields)} 个字段, 分成 {total_batches} 批, "
        f"最大并发 {max_concurrency}, 流式={stream}"
    )
    
    # 使用 semaphore 控制并发数
    semaphore = asyncio.Semaphore(max_concurrency)
    
    async def _limited_infer(batch_idx: int, batch_fields: List[Any]) -> Dict[str, DimensionAttributes]:
        """带并发限制的推断"""
        async with semaphore:
            return await _infer_single_batch(
                batch_idx, batch_fields, rag, total_batches,
                stream=stream, on_token=on_token
            )
    
    # 创建所有批次的任务
    tasks = [
        _limited_infer(idx, batch_fields)
        for idx, batch_fields in enumerate(batches)
    ]
    
    # 并发执行所有任务
    results = await asyncio.gather(*tasks, return_exceptions=True)
    
    # 合并结果
    all_hierarchy = {}
    success_count = 0
    error_count = 0
    
    for idx, result in enumerate(results):
        if isinstance(result, Exception):
            logger.error(f"批次 {idx + 1} 异常: {result}")
            error_count += 1
        elif isinstance(result, dict):
            all_hierarchy.update(result)
            success_count += 1
    
    logger.info(
        f"并行分批推断完成: 共 {len(all_hierarchy)} 个字段, "
        f"成功 {success_count} 批, 失败 {error_count} 批"
    )
    return DimensionHierarchyResult(dimension_hierarchy=all_hierarchy)


async def _batch_inference_serial(
    fields: List[Any],
    rag,
    stream: bool = False,
    batch_size: int = DEFAULT_BATCH_SIZE,
) -> DimensionHierarchyResult:
    """
    串行分批推断维度层级（保留原有实现，支持流式输出）
    
    当需要流式输出时使用此函数，因为并行模式下流式输出会混乱。
    
    Args:
        fields: 要推断的字段列表
        rag: RAG 组件（可选）
        stream: 是否流式输出
        batch_size: 每批大小（默认 5）
    
    Returns:
        合并后的 DimensionHierarchyResult
    """
    if not fields:
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    batches = _split_into_batches(fields, batch_size)
    total_batches = len(batches)
    logger.info(f"串行分批推断: {len(fields)} 个字段, 分成 {total_batches} 批")
    
    all_hierarchy = {}
    
    for batch_idx, batch_fields in enumerate(batches):
        logger.info(f"推断批次 {batch_idx + 1}/{total_batches}: {len(batch_fields)} 个字段")
        
        # 准备批次的维度信息
        dimensions_info = []
        all_few_shot_examples = []
        
        for field in batch_fields:
            info = {
                "name": field.name,
                "caption": field.fieldCaption,
                "dataType": field.dataType,
                "description": field.description or "",
                "unique_count": field.unique_count or 0,
                "sample_values": (field.sample_values or [])[:5],
            }
            dimensions_info.append(info)
            
            # RAG: 获取相似历史模式
            if rag:
                try:
                    rag_context = rag.get_inference_context(
                        field_caption=field.fieldCaption,
                        data_type=field.dataType,
                        sample_values=field.sample_values or [],
                        unique_count=field.unique_count or 0,
                    )
                    if rag_context.get("has_similar_patterns"):
                        examples = rag_context.get("few_shot_examples", [])[:2]
                        all_few_shot_examples.extend(examples)
                except Exception as e:
                    logger.warning(f"RAG 检索失败: {e}")
        
        few_shot_section = _build_few_shot_section(all_few_shot_examples[:3])
        
        # 构建输入数据
        dimensions_str = json.dumps(dimensions_info, ensure_ascii=False, indent=2)
        if few_shot_section:
            dimensions_str = few_shot_section + "\n" + dimensions_str
        
        input_data = {"dimensions": dimensions_str}
        
        # 调用 LLM
        try:
            llm = get_llm(agent_name="dimension_hierarchy")
            messages = DIMENSION_HIERARCHY_PROMPT.format_messages(**input_data)
            
            if stream:
                response = await stream_llm_call(llm, messages, print_output=True)
            else:
                response = await invoke_llm(llm, messages)
            
            batch_result = parse_json_response(response, DimensionHierarchyResult)
            
            # 合并结果
            for field_name, attrs in batch_result.dimension_hierarchy.items():
                all_hierarchy[field_name] = attrs
            
            logger.debug(f"批次 {batch_idx + 1} 完成: {len(batch_result.dimension_hierarchy)} 个字段")
            
        except Exception as e:
            logger.error(f"批次 {batch_idx + 1} 推断失败: {e}")
            # 继续处理下一批
    
    logger.info(f"串行分批推断完成: 共 {len(all_hierarchy)} 个字段")
    return DimensionHierarchyResult(dimension_hierarchy=all_hierarchy)


# ═══════════════════════════════════════════════════════════════════════════
# RAG 辅助函数
# ═══════════════════════════════════════════════════════════════════════════

def _get_dimension_rag():
    """
    延迟加载 DimensionHierarchyRAG 组件
    
    使用 EmbeddingProviderFactory.get_default() 自动检测可用的 Embedding 提供者。
    如果没有可用的提供者，返回 None（禁用 RAG）。
    """
    try:
        from tableau_assistant.src.infra.ai.rag.dimension_pattern import (
            DimensionHierarchyRAG,
        )
        from tableau_assistant.src.infra.ai import EmbeddingProviderFactory
        
        # 使用工厂方法自动检测 Embedding 提供者
        embedding_provider = EmbeddingProviderFactory.get_default()
        
        if embedding_provider is None:
            logger.info("未配置 Embedding API Key，RAG 功能将禁用")
            return None
        
        return DimensionHierarchyRAG(embedding_provider=embedding_provider)
    except Exception as e:
        logger.warning(f"无法加载 DimensionHierarchyRAG: {e}")
        return None


def _build_few_shot_section(few_shot_examples: List[str]) -> str:
    """构建 few-shot 示例部分"""
    if not few_shot_examples:
        return ""

    section = """**Historical Reference Examples (from similar fields):**

The following are inference results from similar fields in the past. Use them as reference:

"""
    for i, example in enumerate(few_shot_examples[:3], 1):
        section += f"Example {i}:\n{example}\n\n"

    return section


def _prepare_dimensions_info(
    metadata: Metadata, rag=None
) -> tuple[List[Dict[str, Any]], str]:
    """
    准备维度字段信息，并获取 RAG few-shot 示例
    
    Returns:
        (维度信息列表, few_shot_section)
    """
    dimension_fields = metadata.get_dimensions()

    if not dimension_fields:
        return [], ""

    dimension_info = []
    all_few_shot_examples = []

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

        # RAG: 获取相似历史模式
        if rag:
            try:
                rag_context = rag.get_inference_context(
                    field_caption=field.fieldCaption,
                    data_type=field.dataType,
                    sample_values=field.sample_values or [],
                    unique_count=field.unique_count or 0,
                )

                if rag_context.get("has_similar_patterns"):
                    examples = rag_context.get("few_shot_examples", [])[:2]
                    all_few_shot_examples.extend(examples)
                    logger.debug(
                        f"RAG: 字段 '{field.fieldCaption}' 找到 {len(examples)} 个相似模式"
                    )
            except Exception as e:
                logger.warning(f"RAG 检索失败: {e}")

    # 构建 few-shot section（最多 5 个示例）
    few_shot_section = _build_few_shot_section(all_few_shot_examples[:5])

    return dimension_info, few_shot_section


def _store_inference_results(
    result: DimensionHierarchyResult,
    metadata: Metadata,
    rag,
    datasource_luid: Optional[str] = None,
) -> None:
    """存储推断结果到 RAG（用于未来检索）"""
    if not rag:
        return

    try:
        stored_count = 0
        skipped_count = 0

        for field_name, attrs in result.dimension_hierarchy.items():
            confidence = attrs.level_confidence

            # 跳过置信度为 0 的结果
            if confidence <= 0:
                skipped_count += 1
                continue

            # 查找字段元数据
            field = None
            for f in metadata.get_dimensions():
                if f.name == field_name:
                    field = f
                    break

            if not field:
                skipped_count += 1
                continue

            try:
                rag.store_inference_result(
                    field_name=field_name,
                    field_caption=field.fieldCaption,
                    data_type=field.dataType,
                    sample_values=field.sample_values or [],
                    unique_count=field.unique_count or 0,
                    category=attrs.category,
                    category_detail=attrs.category_detail,
                    level=attrs.level,
                    granularity=attrs.granularity,
                    reasoning=attrs.reasoning,
                    confidence=confidence,
                    datasource_luid=datasource_luid,
                )
                stored_count += 1
            except Exception as e:
                logger.debug(f"存储推断结果失败: {field_name}, {e}")
                skipped_count += 1

        if stored_count > 0:
            logger.info(f"RAG: 存储了 {stored_count} 个推断结果 (跳过 {skipped_count} 个)")

    except Exception as e:
        logger.warning(f"存储推断结果到 RAG 失败: {e}")


# ═══════════════════════════════════════════════════════════════════════════
# 主节点函数
# ═══════════════════════════════════════════════════════════════════════════

async def dimension_hierarchy_node(
    metadata: Metadata,
    datasource_luid: Optional[str] = None,
    stream: bool = True,
    use_cache: bool = True,
    incremental: bool = True,
    use_batch: bool = True,
    batch_size: int = DEFAULT_BATCH_SIZE,
    parallel: bool = True,
    max_concurrency: int = DEFAULT_MAX_CONCURRENCY,
    on_token: BatchStreamCallbackType = None,
    store_manager=None
) -> DimensionHierarchyResult:
    """
    维度层级推断节点
    
    支持缓存机制、增量推断和分批推断（串行/并行），避免重复推断。
    支持并行 + 流式输出。
    
    Args:
        metadata: Metadata 对象（包含字段元数据）
        datasource_luid: 数据源 LUID（可选，用于缓存和 RAG 存储）
        stream: 是否流式输出（默认 True）
        use_cache: 是否使用缓存（默认 True）
        incremental: 是否启用增量推断（默认 True）
        use_batch: 是否启用分批推断（默认 True，仅用于首次全量推断）
        batch_size: 分批大小（默认 5）
        parallel: 是否启用并行推断（默认 True）
        max_concurrency: 最大并发数（默认 3，仅在 parallel=True 时生效）
        on_token: 流式输出回调函数
                  - 并行模式: (batch_id: int, token: str) -> None
                  - 串行模式: 使用 print 输出（兼容旧行为）
        store_manager: StoreManager 实例（可选）
    
    Returns:
        DimensionHierarchyResult 模型对象
    
    流程：
        1. 检查缓存（如果启用）
        2. 缓存命中且 field_hash 相同 → 直接返回
        3. 计算增量字段（如果启用增量推断）
        4. 增量推断：仅推断新增字段
        5. 全量推断：使用分批推断（并行或串行）
        6. 合并缓存结果与新推断结果
        7. 存储结果到缓存和 RAG
        8. 返回结果
    
    Example:
        # 并行 + 流式输出
        def handle_token(batch_id: int, token: str):
            print(f"[Batch {batch_id}] {token}", end="", flush=True)
        
        result = await dimension_hierarchy_node(
            metadata, 
            stream=True, 
            parallel=True,
            on_token=handle_token
        )
    """
    logger.info("维度层级推断开始")
    
    # 获取维度字段
    dimension_fields = metadata.get_dimensions()
    if not dimension_fields:
        logger.warning("未找到维度字段")
        return DimensionHierarchyResult(dimension_hierarchy={})
    
    # 计算当前字段哈希
    current_field_hash = _compute_field_hash(dimension_fields)
    logger.debug(f"当前字段哈希: {current_field_hash}")
    
    # 1. 检查缓存（如果启用）
    cache_entry = None
    if use_cache and datasource_luid:
        cache_entry = _get_from_cache(datasource_luid, store_manager)
        
        if cache_entry:
            # 检查字段是否变化
            if cache_entry.field_hash == current_field_hash:
                # 缓存有效，直接返回
                logger.info(
                    f"缓存命中（字段未变化）: {len(cache_entry.hierarchy_data)} 个维度"
                )
                # 转换为 DimensionHierarchyResult
                hierarchy = {}
                for field_name, attrs_dict in cache_entry.hierarchy_data.items():
                    hierarchy[field_name] = DimensionAttributes(**attrs_dict)
                return DimensionHierarchyResult(dimension_hierarchy=hierarchy)
    
    # 2. 计算增量字段
    incremental_fields = _compute_incremental_fields(dimension_fields, cache_entry)
    
    # 3. 决定推断策略
    is_full_inference = False
    if incremental and cache_entry and incremental_fields.needs_inference:
        # 增量推断：仅推断新增字段
        fields_to_infer = _filter_fields_by_names(
            dimension_fields, 
            incremental_fields.new_fields
        )
        is_full_inference = False
        logger.info(
            f"增量推断: 新增 {len(incremental_fields.new_fields)} 个字段, "
            f"删除 {len(incremental_fields.deleted_fields)} 个字段, "
            f"复用 {len(incremental_fields.unchanged_fields)} 个字段"
        )
    elif incremental and cache_entry and not incremental_fields.needs_inference:
        # 无新增字段，只需删除已删除字段
        logger.info(
            f"无新增字段，仅删除 {len(incremental_fields.deleted_fields)} 个字段"
        )
        merged_hierarchy = _merge_hierarchy_results(
            cache_entry.hierarchy_data,
            DimensionHierarchyResult(dimension_hierarchy={}),
            incremental_fields.deleted_fields
        )
        result = DimensionHierarchyResult(dimension_hierarchy=merged_hierarchy)
        
        # 更新缓存
        if use_cache and datasource_luid:
            hierarchy_data = {
                name: attrs.model_dump() 
                for name, attrs in result.dimension_hierarchy.items()
            }
            _put_to_cache(
                datasource_luid=datasource_luid,
                field_hash=current_field_hash,
                hierarchy_data=hierarchy_data,
                store_manager=store_manager
            )
        return result
    else:
        # 全量推断
        fields_to_infer = dimension_fields
        is_full_inference = True
        logger.info(f"全量推断: {len(fields_to_infer)} 个字段")

    # 4. 加载 RAG 组件
    rag = _get_dimension_rag()
    if rag:
        logger.debug("RAG 组件已加载")

    # 5. 执行推断
    try:
        # 判断是否使用分批推断（仅用于全量推断且字段数超过阈值）
        use_batch_inference = (
            use_batch 
            and is_full_inference 
            and len(fields_to_infer) > batch_size
        )
        
        if use_batch_inference:
            # 分批推断（根据 parallel 参数选择并行或串行）
            if parallel:
                logger.info(
                    f"使用并行分批推断: {len(fields_to_infer)} 个字段, "
                    f"每批 {batch_size} 个, 最大并发 {max_concurrency}, 流式={stream}"
                )
                new_result = await _batch_inference(
                    fields=fields_to_infer,
                    rag=rag,
                    stream=stream,
                    batch_size=batch_size,
                    max_concurrency=max_concurrency,
                    on_token=on_token,
                )
            else:
                logger.info(f"使用串行分批推断: {len(fields_to_infer)} 个字段, 每批 {batch_size} 个")
                new_result = await _batch_inference_serial(
                    fields=fields_to_infer,
                    rag=rag,
                    stream=stream,
                    batch_size=batch_size,
                )
        else:
            # 单次推断（增量推断或字段数较少）
            dimensions_info = []
            all_few_shot_examples = []
            
            for field in fields_to_infer:
                info = {
                    "name": field.name,
                    "caption": field.fieldCaption,
                    "dataType": field.dataType,
                    "description": field.description or "",
                    "unique_count": field.unique_count or 0,
                    "sample_values": (field.sample_values or [])[:5],
                }
                dimensions_info.append(info)
                
                # RAG: 获取相似历史模式
                if rag:
                    try:
                        rag_context = rag.get_inference_context(
                            field_caption=field.fieldCaption,
                            data_type=field.dataType,
                            sample_values=field.sample_values or [],
                            unique_count=field.unique_count or 0,
                        )
                        if rag_context.get("has_similar_patterns"):
                            examples = rag_context.get("few_shot_examples", [])[:2]
                            all_few_shot_examples.extend(examples)
                    except Exception as e:
                        logger.warning(f"RAG 检索失败: {e}")
            
            few_shot_section = _build_few_shot_section(all_few_shot_examples[:5])

            logger.info(
                f"推断 {len(dimensions_info)} 个维度的层级, "
                f"RAG 示例: {'有' if few_shot_section else '无'}"
            )

            # 构建输入数据
            dimensions_str = json.dumps(dimensions_info, ensure_ascii=False, indent=2)
            if few_shot_section:
                dimensions_str = few_shot_section + "\n" + dimensions_str

            input_data = {"dimensions": dimensions_str}

            # 调用 LLM 执行推断
            llm = get_llm(agent_name="dimension_hierarchy")
            messages = DIMENSION_HIERARCHY_PROMPT.format_messages(**input_data)
            
            if stream:
                response = await stream_llm_call(llm, messages, print_output=True)
            else:
                response = await invoke_llm(llm, messages)
            
            new_result = parse_json_response(response, DimensionHierarchyResult)

        # 8. 合并结果（如果是增量推断）
        if incremental and cache_entry:
            merged_hierarchy = _merge_hierarchy_results(
                cache_entry.hierarchy_data,
                new_result,
                incremental_fields.deleted_fields
            )
            result = DimensionHierarchyResult(dimension_hierarchy=merged_hierarchy)
            logger.info(
                f"增量推断完成: 新推断 {len(new_result.dimension_hierarchy)} 个, "
                f"合并后共 {len(result.dimension_hierarchy)} 个维度"
            )
        else:
            result = new_result

        # 计算平均置信度
        confidences = [
            attrs.level_confidence for attrs in result.dimension_hierarchy.values()
        ]
        avg_confidence = sum(confidences) / len(confidences) if confidences else 0.0

        logger.info(
            f"维度层级推断完成: "
            f"{len(result.dimension_hierarchy)} 个维度, "
            f"平均置信度: {avg_confidence:.2f}"
        )

        # 输出每个维度的推断结果
        for field_name, attrs in result.dimension_hierarchy.items():
            logger.debug(
                f"  → {field_name}: {attrs.category_detail} "
                f"L{attrs.level}({attrs.granularity}) "
                f"conf={attrs.level_confidence:.2f}"
            )

        # 9. 存储结果到缓存
        if use_cache and datasource_luid:
            hierarchy_data = {
                name: attrs.model_dump() 
                for name, attrs in result.dimension_hierarchy.items()
            }
            _put_to_cache(
                datasource_luid=datasource_luid,
                field_hash=current_field_hash,
                hierarchy_data=hierarchy_data,
                store_manager=store_manager
            )

        # 10. 存储结果到 RAG
        _store_inference_results(result, metadata, rag, datasource_luid)

        # 11. 将维度层级信息注入到 metadata 的各个 FieldMetadata 对象
        # 这样后续的 FieldIndexer 可以使用 category 等信息构建索引
        for field_name, attrs in result.dimension_hierarchy.items():
            field = metadata.get_field(field_name)
            if field:
                field.category = attrs.category
                field.category_detail = attrs.category_detail
                field.level = attrs.level
                field.granularity = attrs.granularity
                field.parent_dimension = attrs.parent_dimension
                field.child_dimension = attrs.child_dimension
        
        logger.debug(f"已将维度层级信息注入到 {len(result.dimension_hierarchy)} 个字段")

        return result

    except Exception as e:
        logger.error(f"维度层级推断失败: {e}", exc_info=True)
        return DimensionHierarchyResult(dimension_hierarchy={})


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
    store_result: bool = True
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
    
    # 加载 RAG 组件
    rag = _get_dimension_rag()
    
    # 准备字段信息
    dimensions_info = [{
        "name": field_name,
        "caption": field_caption,
        "dataType": data_type,
        "description": "",
        "unique_count": unique_count,
        "sample_values": sample_values[:5],
    }]
    
    # 获取 RAG few-shot 示例
    few_shot_examples = []
    if rag:
        try:
            rag_context = rag.get_inference_context(
                field_caption=field_caption,
                data_type=data_type,
                sample_values=sample_values,
                unique_count=unique_count,
            )
            if rag_context.get("has_similar_patterns"):
                few_shot_examples = rag_context.get("few_shot_examples", [])[:3]
        except Exception as e:
            logger.warning(f"RAG 检索失败: {e}")
    
    few_shot_section = _build_few_shot_section(few_shot_examples)
    
    # 构建输入数据
    dimensions_str = json.dumps(dimensions_info, ensure_ascii=False, indent=2)
    if few_shot_section:
        dimensions_str = few_shot_section + "\n" + dimensions_str
    
    input_data = {"dimensions": dimensions_str}
    
    try:
        llm = get_llm(agent_name="dimension_hierarchy")
        messages = DIMENSION_HIERARCHY_PROMPT.format_messages(**input_data)
        response = await invoke_llm(llm, messages)
        result = parse_json_response(response, DimensionHierarchyResult)
        
        # 获取推断结果
        attrs = result.dimension_hierarchy.get(field_name)
        
        if attrs and store_result and rag:
            try:
                rag.store_inference_result(
                    field_name=field_name,
                    field_caption=field_caption,
                    data_type=data_type,
                    sample_values=sample_values,
                    unique_count=unique_count,
                    category=attrs.category,
                    category_detail=attrs.category_detail,
                    level=attrs.level,
                    granularity=attrs.granularity,
                    reasoning=attrs.reasoning,
                    confidence=attrs.level_confidence,
                    datasource_luid=datasource_luid,
                )
            except Exception as e:
                logger.warning(f"存储推断结果失败: {e}")
        
        logger.debug(
            f"单字段推断完成: {field_caption} -> "
            f"{attrs.category_detail if attrs else 'None'}"
        )
        return attrs
        
    except Exception as e:
        logger.error(f"单字段推断失败: {field_caption}, {e}")
        return None


__all__ = ["dimension_hierarchy_node", "infer_single_field"]
