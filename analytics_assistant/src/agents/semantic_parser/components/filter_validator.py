# -*- coding: utf-8 -*-
"""
Filter Value Validator - 筛选值验证器

验证 SemanticOutput 中的筛选条件值是否存在于数据源中。

验证策略（平衡性能和用户体验）：
1. 时间字段：跳过验证（LLM 已处理）
2. 数值范围筛选：跳过验证（不需要精确匹配）
3. 低基数字段：从缓存/数据源验证
   - 精确匹配 → is_valid=True
   - 有相似值 → needs_confirmation=True（触发 interrupt）
   - 无相似值 → is_unresolvable=True（返回澄清）

核心流程：
1. 遍历所有筛选条件
2. 根据字段类型决定是否验证
3. 通过平台适配器查询数据源获取字段唯一值
4. 执行精确匹配/模糊匹配
5. 汇总结果，返回 FilterValidationSummary

平台无关设计：
- 通过 BasePlatformAdapter.get_field_values() 获取字段值
- 支持 Tableau、Power BI 等不同平台

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.filter_validator
"""

import asyncio
import logging
from difflib import SequenceMatcher
from typing import List, Dict, Optional, Any

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.core.interfaces import BasePlatformAdapter
from analytics_assistant.src.core.schemas.data_model import DataModel
from analytics_assistant.src.core.schemas.filters import SetFilter, FilterType

from ..schemas.filters import (
    FilterValidationType,
    FilterValidationResult,
    FilterValidationSummary,
)
from ..schemas.output import SemanticOutput
from .field_value_cache import FieldValueCache


logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> Dict[str, Any]:
    """获取 filter_validator 配置。"""
    try:
        config = get_config()
        return config.config.get("semantic_parser", {}).get("filter_validator", {})
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}


# 默认配置（作为 fallback）
_DEFAULT_SIMILARITY_THRESHOLD = 0.6
_DEFAULT_TOP_K_SIMILAR = 5
_DEFAULT_HIGH_CARDINALITY_THRESHOLD = 500
_DEFAULT_TIME_DATA_TYPES = {"date", "datetime", "timestamp"}


def get_time_data_types() -> set:
    """获取时间相关数据类型。"""
    config = _get_config()
    types = config.get("time_data_types", list(_DEFAULT_TIME_DATA_TYPES))
    return set(types)


class FilterValueValidator:
    """筛选值验证器
    
    验证 SemanticOutput 中的筛选条件值是否存在于数据源中。
    集成了字段值查询、缓存、匹配和确认应用的完整功能。
    
    平台无关设计：
    - 通过 BasePlatformAdapter.get_field_values() 获取字段值
    - 支持 Tableau、Power BI 等不同平台
    
    配置来源：app.yaml -> semantic_parser.filter_validator
    
    使用方式：
        validator = FilterValueValidator(
            platform_adapter=adapter,
            field_value_cache=cache,
        )
        summary = await validator.validate(
            semantic_output=output,
            data_model=data_model,
            datasource_id=datasource_id,
            **platform_kwargs,  # 平台特定参数（如认证信息）
        )
    """
    
    def __init__(
        self,
        platform_adapter: BasePlatformAdapter,
        field_value_cache: FieldValueCache,
        similarity_threshold: Optional[float] = None,
        top_k_similar: Optional[int] = None,
        high_cardinality_threshold: Optional[int] = None,
    ):
        """初始化验证器
        
        Args:
            platform_adapter: 平台适配器，用于查询数据源
            field_value_cache: 字段值缓存
            similarity_threshold: 相似度阈值（None 从配置读取）
            top_k_similar: 返回的相似值数量（None 从配置读取）
            high_cardinality_threshold: 高基数阈值（None 从配置读取）
        """
        self._adapter = platform_adapter
        self._cache = field_value_cache
        
        # 从配置加载参数
        self._load_config(similarity_threshold, top_k_similar, high_cardinality_threshold)
    
    def _load_config(
        self,
        similarity_threshold: Optional[float],
        top_k_similar: Optional[int],
        high_cardinality_threshold: Optional[int],
    ) -> None:
        """从配置加载参数。"""
        config = _get_config()
        
        self._similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else config.get("similarity_threshold", _DEFAULT_SIMILARITY_THRESHOLD)
        )
        self._top_k_similar = (
            top_k_similar
            if top_k_similar is not None
            else config.get("top_k_similar", _DEFAULT_TOP_K_SIMILAR)
        )
        self._high_cardinality_threshold = (
            high_cardinality_threshold
            if high_cardinality_threshold is not None
            else config.get("high_cardinality_threshold", _DEFAULT_HIGH_CARDINALITY_THRESHOLD)
        )
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 数据源查询
    # ═══════════════════════════════════════════════════════════════════════════
    
    async def _fetch_field_values_from_datasource(
        self,
        field_name: str,
        datasource_id: str,
        **kwargs: Any,
    ) -> List[str]:
        """从数据源查询字段的唯一值
        
        通过平台适配器查询字段值，支持不同的数据平台。
        
        Args:
            field_name: 字段名（caption）
            datasource_id: 数据源标识符
            **kwargs: 平台特定参数（如认证信息）
            
        Returns:
            字段唯一值列表
        """
        return await self._adapter.get_field_values(
            field_name=field_name,
            datasource_id=datasource_id,
            **kwargs,
        )
    
    async def _get_field_values(
        self,
        field_name: str,
        datasource_id: str,
        **kwargs: Any,
    ) -> Optional[List[str]]:
        """获取字段的唯一值（先查缓存，未命中则查询数据源）
        
        Args:
            field_name: 字段名
            datasource_id: 数据源标识符
            **kwargs: 平台特定参数
            
        Returns:
            字段唯一值列表，如果无法获取则返回 None
        """
        # 1. 先查缓存
        cached_values = await self._cache.get(field_name, datasource_id)
        if cached_values is not None:
            return cached_values
        
        # 2. 缓存未命中，查询数据源
        try:
            values = await self._fetch_field_values_from_datasource(
                field_name=field_name,
                datasource_id=datasource_id,
                **kwargs,
            )
            
            if values:
                # 3. 写入缓存
                await self._cache.set(
                    field_name=field_name,
                    datasource_luid=datasource_id,
                    values=values,
                    cardinality=len(values),
                )
            
            return values if values else []
            
        except Exception as e:
            # 查询失败，返回 None 表示无法验证
            logger.warning(f"获取字段值失败: field_name={field_name}, error={e}")
            return None
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 匹配逻辑
    # ═══════════════════════════════════════════════════════════════════════════
    
    # 相似度匹配分数常量
    SUBSTRING_MATCH_SCORE = 0.95  # 目标是候选的子串
    SUPERSTRING_MATCH_SCORE = 0.90  # 候选是目标的子串
    
    def _find_similar(
        self,
        target: str,
        candidates: List[str],
        threshold: Optional[float] = None,
        top_k: Optional[int] = None,
    ) -> List[str]:
        """查找相似的候选值
        
        使用多种匹配策略：
        1. 包含关系（优先级最高）
        2. 编辑距离相似度
        
        Args:
            target: 目标值
            candidates: 候选值列表
            threshold: 相似度阈值
            top_k: 返回的最大数量
            
        Returns:
            相似值列表，按相似度降序排列
        """
        if threshold is None:
            threshold = self._similarity_threshold
        if top_k is None:
            top_k = self._top_k_similar
        
        if not target or not candidates:
            return []
        
        scored = []
        target_lower = target.lower()
        
        for c in candidates:
            c_lower = c.lower()
            
            # 包含关系优先（给予高分）
            if target_lower in c_lower:
                scored.append((c, self.SUBSTRING_MATCH_SCORE))
            elif c_lower in target_lower:
                scored.append((c, self.SUPERSTRING_MATCH_SCORE))
            else:
                # 编辑距离相似度
                ratio = SequenceMatcher(None, target_lower, c_lower).ratio()
                if ratio >= threshold:
                    scored.append((c, ratio))
        
        # 按相似度排序
        scored.sort(key=lambda x: x[1], reverse=True)
        return [c for c, _ in scored[:top_k]]
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 验证逻辑
    # ═══════════════════════════════════════════════════════════════════════════
    
    def should_validate(
        self,
        field_name: str,
        filter_type: FilterType,
        data_model: DataModel,
        datasource_id: str,
    ) -> tuple[bool, Optional[str]]:
        """判断是否需要验证该筛选条件
        
        Args:
            field_name: 字段名
            filter_type: 筛选类型
            data_model: 数据模型
            datasource_id: 数据源标识符
            
        Returns:
            (should_validate, skip_reason)
        """
        # 1. 只验证 SET 类型筛选（精确值匹配）
        if filter_type != FilterType.SET:
            return False, "non_set_filter"
        
        # 2. 查找字段
        field = data_model.get_field(field_name)
        if not field:
            return False, "field_not_found"
        
        # 3. 时间字段跳过
        time_data_types = get_time_data_types()
        if field.data_type and field.data_type.lower() in time_data_types:
            return False, "time_field"
        
        # 4. 检查缓存中的基数
        cardinality = self._cache.get_cardinality(field_name, datasource_id)
        if cardinality is not None and cardinality > self._high_cardinality_threshold:
            return False, "high_cardinality"
        
        return True, None
    
    async def _validate_single_value(
        self,
        field_name: str,
        filter_value: str,
        datasource_id: str,
        **kwargs: Any,
    ) -> FilterValidationResult:
        """验证单个筛选值
        
        Args:
            field_name: 字段名
            filter_value: 筛选值
            datasource_id: 数据源标识符
            **kwargs: 平台特定参数
            
        Returns:
            验证结果
        """
        # 1. 获取字段值
        field_values = await self._get_field_values(field_name, datasource_id, **kwargs)
        
        if field_values is None:
            # 无法获取字段值（查询失败），跳过验证
            return FilterValidationResult(
                is_valid=True,
                field_name=field_name,
                requested_value=filter_value,
                validation_type=FilterValidationType.SKIPPED,
                skip_reason="fetch_failed",
            )
        
        if not field_values:
            # 字段没有值（空字段），跳过验证
            return FilterValidationResult(
                is_valid=True,
                field_name=field_name,
                requested_value=filter_value,
                validation_type=FilterValidationType.SKIPPED,
                skip_reason="empty_field",
            )
        
        # 2. 精确匹配
        if filter_value in field_values:
            return FilterValidationResult(
                is_valid=True,
                field_name=field_name,
                requested_value=filter_value,
                matched_values=[filter_value],
                validation_type=FilterValidationType.EXACT_MATCH,
            )
        
        # 2.1 大小写不敏感匹配
        lower_value = filter_value.lower()
        for fv in field_values:
            if fv.lower() == lower_value:
                return FilterValidationResult(
                    is_valid=True,
                    field_name=field_name,
                    requested_value=filter_value,
                    matched_values=[fv],
                    validation_type=FilterValidationType.EXACT_MATCH,
                )
        
        # 3. 模糊匹配，找相似值
        similar = self._find_similar(filter_value, field_values)
        
        if not similar:
            # 没有相似值 → 无法解决
            return FilterValidationResult(
                is_valid=False,
                field_name=field_name,
                requested_value=filter_value,
                validation_type=FilterValidationType.NOT_FOUND,
                is_unresolvable=True,
                message=f"字段'{field_name}'中没有'{filter_value}'，也没有找到相似的值。请检查输入是否正确。",
            )
        
        # 4. 有相似值，需要用户确认
        return FilterValidationResult(
            is_valid=False,
            field_name=field_name,
            requested_value=filter_value,
            similar_values=similar,
            validation_type=FilterValidationType.NEEDS_CONFIRMATION,
            needs_confirmation=True,
            message=f"字段'{field_name}'中没有'{filter_value}'，找到相似值：{', '.join(similar)}。请选择正确的值。",
        )
    
    async def validate(
        self,
        semantic_output: SemanticOutput,
        data_model: DataModel,
        datasource_id: str,
        max_concurrency: Optional[int] = None,
        **kwargs: Any,
    ) -> FilterValidationSummary:
        """验证所有筛选条件（并行执行）
        
        Args:
            semantic_output: 语义理解输出
            data_model: 数据模型
            datasource_id: 数据源标识符
            max_concurrency: 最大并发数（默认 5）
            **kwargs: 平台特定参数（如认证信息）
            
        Returns:
            FilterValidationSummary
        """
        # 默认并发限制
        _DEFAULT_MAX_CONCURRENCY = 5
        actual_max_concurrency = max_concurrency or _DEFAULT_MAX_CONCURRENCY
        
        results: List[FilterValidationResult] = []
        filters = semantic_output.where.filters
        
        # 收集需要验证的任务
        validation_tasks = []
        task_metadata = []  # 保存任务元数据用于结果排序
        skipped_results = []  # 跳过验证的结果
        
        for filter_idx, f in enumerate(filters):
            # 只处理 SetFilter 类型
            if not isinstance(f, SetFilter):
                skipped_results.append((filter_idx, -1, FilterValidationResult(
                    is_valid=True,
                    field_name=f.field_name,
                    requested_value="",
                    validation_type=FilterValidationType.SKIPPED,
                    skip_reason="non_set_filter",
                )))
                continue
            
            # 检查是否需要验证
            should_val, skip_reason = self.should_validate(
                field_name=f.field_name,
                filter_type=f.filter_type,
                data_model=data_model,
                datasource_id=datasource_id,
            )
            
            if not should_val:
                skipped_results.append((filter_idx, -1, FilterValidationResult(
                    is_valid=True,
                    field_name=f.field_name,
                    requested_value="",
                    validation_type=FilterValidationType.SKIPPED,
                    skip_reason=skip_reason,
                )))
                continue
            
            # 收集需要验证的值
            for value_idx, value in enumerate(f.values):
                value_str = str(value) if value is not None else ""
                if not value_str:
                    continue
                
                task_metadata.append((filter_idx, value_idx, f.field_name, value_str))
                validation_tasks.append(
                    self._validate_single_value(
                        field_name=f.field_name,
                        filter_value=value_str,
                        datasource_id=datasource_id,
                        **kwargs,
                    )
                )
        
        # 使用 Semaphore 限制并发
        semaphore = asyncio.Semaphore(actual_max_concurrency)
        
        async def limited_validate(task):
            async with semaphore:
                return await task
        
        # 并行执行所有验证任务
        if validation_tasks:
            task_results = await asyncio.gather(
                *[limited_validate(task) for task in validation_tasks],
                return_exceptions=True,
            )
            
            # 处理结果，保持原始顺序
            for idx, result in enumerate(task_results):
                filter_idx, value_idx, field_name, value_str = task_metadata[idx]
                
                if isinstance(result, Exception):
                    # 单个验证失败不影响其他任务
                    logger.warning(f"验证失败 {field_name}={value_str}: {type(result).__name__}: {result}")
                    results.append(FilterValidationResult(
                        is_valid=True,
                        field_name=field_name,
                        requested_value=value_str,
                        validation_type=FilterValidationType.SKIPPED,
                        skip_reason=f"validation_error: {type(result).__name__}",
                    ))
                else:
                    results.append(result)
        
        # 合并跳过的结果
        for _, _, result in skipped_results:
            results.append(result)
        
        return FilterValidationSummary.from_results(results)
    
    # ═══════════════════════════════════════════════════════════════════════════
    # 确认应用
    # ═══════════════════════════════════════════════════════════════════════════
    
    def apply_confirmations(
        self,
        semantic_output: SemanticOutput,
        confirmations: Dict[str, str],
    ) -> SemanticOutput:
        """应用用户确认的值到 semantic_output
        
        Args:
            semantic_output: 原始语义输出
            confirmations: 确认映射 {original_value: confirmed_value}
            
        Returns:
            更新后的 SemanticOutput
        """
        updated_filters = []
        
        for f in semantic_output.where.filters:
            if isinstance(f, SetFilter):
                new_values = [
                    confirmations.get(str(v), v) for v in f.values
                ]
                updated_filters.append(f.model_copy(update={"values": new_values}))
            else:
                updated_filters.append(f)
        
        updated_where = semantic_output.where.model_copy(update={"filters": updated_filters})
        return semantic_output.model_copy(update={"where": updated_where})
    
    def apply_single_confirmation(
        self,
        semantic_output: SemanticOutput,
        field_name: str,
        original_value: str,
        confirmed_value: str,
    ) -> SemanticOutput:
        """应用单个确认到 semantic_output
        
        Args:
            semantic_output: 原始语义输出
            field_name: 字段名
            original_value: 原始值
            confirmed_value: 确认后的值
            
        Returns:
            更新后的 SemanticOutput
        """
        updated_filters = []
        
        for f in semantic_output.where.filters:
            if isinstance(f, SetFilter) and f.field_name == field_name:
                new_values = [
                    confirmed_value if str(v) == original_value else v
                    for v in f.values
                ]
                updated_filters.append(f.model_copy(update={"values": new_values}))
            else:
                updated_filters.append(f)
        
        updated_where = semantic_output.where.model_copy(update={"filters": updated_filters})
        return semantic_output.model_copy(update={"where": updated_where})


__all__ = ["FilterValueValidator"]
