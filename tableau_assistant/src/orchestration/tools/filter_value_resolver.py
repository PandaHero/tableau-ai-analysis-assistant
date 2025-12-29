"""
SetFilter 值解析器

解析并验证 SetFilter 的值，支持：
- 精确匹配
- RAG 语义匹配
- 智能降级为 MatchFilter（单值模糊匹配）
- 触发澄清

流程：
1. 从 DataModel 的 sample_values 获取字段唯一值
2. 对每个用户值进行匹配（精确 → RAG）
3. 根据匹配结果决定：
   - 全部匹配 → SetFilter
   - 单值未匹配 → MatchFilter（contains 模糊匹配）
   - 多值未匹配 → SetFilter（使用 RAG 匹配到的相似值）
4. 执行后无结果 → 触发澄清

重要限制（VizQL API）：
- SetFilter、MatchFilter、RelativeDateFilter 都不支持 CalculatedFilterField
- MatchFilter 只支持单个 pattern（contains/startsWith/endsWith）
- 因此多值模糊匹配需要使用 SetFilter + RAG 匹配到的相似值
"""
import logging
from dataclasses import dataclass, field
from typing import List, Optional, Dict, Any, Union

from langgraph.types import RunnableConfig

from tableau_assistant.src.core.models.filters import SetFilter, TextMatchFilter
from tableau_assistant.src.core.models.enums import TextMatchType

logger = logging.getLogger(__name__)

# RAG 匹配置信度阈值
RAG_CONFIDENCE_THRESHOLD = 0.9


@dataclass
class MatchFilterFallback:
    """
    MatchFilter 降级方案（单值模糊匹配）
    
    用于单值模糊匹配，生成的 VizQL 格式：
    {
        "field": {"fieldCaption": "Field"},
        "filterType": "MATCH",
        "contains": "value"
    }
    
    注意：VizQL API 限制 - SetFilter 不支持 CalculatedFilterField！
    因此多值模糊匹配需要使用其他策略（如 RAG 匹配相似值）。
    """
    field_name: str  # 字段名
    pattern: str  # 匹配模式
    match_type: str = "contains"  # contains, startsWith, endsWith
    exclude: bool = False
    
    def to_vizql_filter(self) -> Dict[str, Any]:
        """转换为 VizQL filter 格式"""
        filter_dict = {
            "field": {"fieldCaption": self.field_name},
            "filterType": "MATCH",
            "exclude": self.exclude,
        }
        filter_dict[self.match_type] = self.pattern
        return filter_dict
    
    def model_dump(self) -> Dict[str, Any]:
        """兼容 Pydantic 的序列化方法"""
        return {
            "field_name": self.field_name,
            "pattern": self.pattern,
            "match_type": self.match_type,
            "exclude": self.exclude,
            "_type": "MatchFilterFallback",
        }


@dataclass
class FilterResolveResult:
    """筛选值解析结果"""
    
    # 解析后的筛选器（SetFilter, TextMatchFilter, 或 MatchFilterFallback）
    resolved_filter: Optional[Union[SetFilter, TextMatchFilter, MatchFilterFallback]] = None
    
    # 是否为降级查询（从 SetFilter 降级为模糊匹配）
    is_fallback: bool = False
    
    # 降级原因
    fallback_reason: Optional[str] = None
    
    # 未匹配的用户值
    unmatched_values: List[str] = field(default_factory=list)
    
    # 匹配到的真实值
    matched_values: List[str] = field(default_factory=list)
    
    # 字段的可用值（用于澄清）
    available_values: List[str] = field(default_factory=list)
    
    # 警告信息
    warning: Optional[str] = None


@dataclass
class Clarification:
    """澄清信息"""
    type: str  # FILTER_VALUE_NOT_FOUND
    message: str
    field: str
    user_values: List[str]
    available_values: List[str]


class FilterValueResolver:
    """
    SetFilter 值解析器
    
    解析 SetFilter 的值，支持精确匹配和 RAG 语义匹配。
    如果无法匹配，降级为 CalculatedFilterField + SetFilter（多值模糊匹配）。
    """
    
    def __init__(
        self,
        datasource_luid: str,
        config: Optional[RunnableConfig] = None,
        data_model: Optional[Any] = None,
    ):
        """
        初始化解析器
        
        Args:
            datasource_luid: 数据源 LUID
            config: LangGraph 配置
            data_model: DataModel 实例（用于获取 sample_values）
        """
        self.datasource_luid = datasource_luid
        self.config = config
        self.data_model = data_model
        
        # 延迟初始化 FieldValueIndexer
        self._value_indexer = None
    
    def _get_value_indexer(self):
        """获取或创建 FieldValueIndexer"""
        if self._value_indexer is None:
            from tableau_assistant.src.infra.ai.rag.field_value_indexer import FieldValueIndexer
            self._value_indexer = FieldValueIndexer(datasource_luid=self.datasource_luid)
        return self._value_indexer
    
    async def resolve_set_filter(
        self,
        filter_spec: SetFilter,
        technical_field_name: str,
    ) -> FilterResolveResult:
        """
        解析 SetFilter 值
        
        Args:
            filter_spec: 原始 SetFilter
            technical_field_name: 映射后的技术字段名
        
        Returns:
            FilterResolveResult
        """
        if not filter_spec.values:
            # 没有值，直接返回原始筛选器
            return FilterResolveResult(resolved_filter=filter_spec)
        
        indexer = self._get_value_indexer()
        
        # 从 DataModel 加载字段值
        distinct_values = []
        if self.data_model:
            result = indexer.load_values_from_data_model(
                field_name=technical_field_name,
                data_model=self.data_model,
            )
            distinct_values = result.values
        else:
            # 尝试从缓存获取
            distinct_values = indexer.get_cached_values(technical_field_name) or []
        
        if not distinct_values:
            logger.warning(f"字段 '{technical_field_name}' 没有 sample_values，无法验证筛选值")
            # 无法验证，降级为模糊匹配
            return self._create_fallback_result(
                filter_spec=filter_spec,
                technical_field_name=technical_field_name,
                unmatched_values=[str(v) for v in filter_spec.values],
                reason="无法获取字段 sample_values",
                available_values=[],
            )
        
        # 对每个用户值进行匹配
        matched_values = []
        unmatched_values = []
        
        for user_value in filter_spec.values:
            match_result = await indexer.match_value(
                user_value=str(user_value),
                field_name=technical_field_name,
                data_model=self.data_model,
            )
            
            if match_result.matched_value:
                matched_values.append(match_result.matched_value)
                logger.info(
                    f"筛选值匹配: '{user_value}' → '{match_result.matched_value}' "
                    f"(type={match_result.match_type}, confidence={match_result.confidence:.2f})"
                )
            else:
                unmatched_values.append(str(user_value))
                logger.info(
                    f"筛选值未匹配: '{user_value}' "
                    f"(best_confidence={match_result.confidence:.2f})"
                )
        
        # 根据匹配结果决定策略
        if not unmatched_values:
            # 全部匹配成功 → 使用 SetFilter
            return FilterResolveResult(
                resolved_filter=SetFilter(
                    field_name=filter_spec.field_name,
                    values=matched_values,
                    exclude=filter_spec.exclude,
                ),
                is_fallback=False,
                matched_values=matched_values,
                available_values=distinct_values[:20],
            )
        
        # 有未匹配的值 → 降级为 CalculatedFilterField + SetFilter
        # 注意：即使部分匹配，也统一降级，避免结果不一致
        return self._create_fallback_result(
            filter_spec=filter_spec,
            technical_field_name=technical_field_name,
            unmatched_values=unmatched_values,
            matched_values=matched_values,
            reason=f"部分值未匹配: {unmatched_values}" if matched_values else f"所有值未匹配: {unmatched_values}",
            available_values=distinct_values[:20],
        )
    
    def _create_fallback_result(
        self,
        filter_spec: SetFilter,
        technical_field_name: str,
        unmatched_values: List[str],
        reason: str,
        available_values: List[str],
        matched_values: List[str] = None,
    ) -> FilterResolveResult:
        """
        创建降级结果
        
        策略：
        1. 如果只有一个未匹配值 → 使用 MatchFilter (contains)
        2. 如果有多个未匹配值 → 使用 SetFilter + RAG 匹配到的相似值
           （如果 RAG 也没有匹配到，则使用原始值尝试）
        
        注意：VizQL API 限制 - SetFilter 不支持 CalculatedFilterField！
        """
        all_values = [str(v) for v in filter_spec.values]
        matched_values = matched_values or []
        
        # 策略 1: 单值 → MatchFilter (contains)
        if len(all_values) == 1:
            match_filter = MatchFilterFallback(
                field_name=technical_field_name,
                pattern=all_values[0],
                match_type="contains",
                exclude=filter_spec.exclude,
            )
            
            warning_msg = f"SetFilter 降级为 MatchFilter: {reason}"
            warning_msg += f" (使用 contains 匹配: '{all_values[0]}')"
            
            return FilterResolveResult(
                resolved_filter=match_filter,
                is_fallback=True,
                fallback_reason=reason,
                unmatched_values=unmatched_values,
                matched_values=matched_values,
                available_values=available_values,
                warning=warning_msg,
            )
        
        # 策略 2: 多值 → 使用 RAG 匹配到的相似值 + 原始值
        # 如果有 RAG 匹配到的值，优先使用；否则使用原始值尝试
        final_values = list(set(matched_values + all_values))
        
        # 创建 SetFilter（使用所有可能的值）
        set_filter = SetFilter(
            field_name=filter_spec.field_name,
            values=final_values,
            exclude=filter_spec.exclude,
        )
        
        warning_msg = f"SetFilter 值解析: {reason}"
        if matched_values:
            warning_msg += f" (RAG 匹配: {matched_values}, 原始值: {all_values})"
        else:
            warning_msg += f" (使用原始值尝试: {all_values})"
        
        return FilterResolveResult(
            resolved_filter=set_filter,
            is_fallback=True,
            fallback_reason=reason,
            unmatched_values=unmatched_values,
            matched_values=matched_values,
            available_values=available_values,
            warning=warning_msg,
        )
    
    def create_clarification(
        self,
        field_name: str,
        field_caption: str,
        user_values: List[str],
        available_values: List[str],
    ) -> Clarification:
        """
        创建澄清信息
        
        当模糊匹配也没有结果时调用。
        """
        return Clarification(
            type="FILTER_VALUE_NOT_FOUND",
            message=f"筛选值 {user_values} 在字段 '{field_caption}' 中没有找到匹配的数据",
            field=field_name,
            user_values=user_values,
            available_values=available_values,
        )


__all__ = [
    "FilterValueResolver",
    "FilterResolveResult",
    "MatchFilterFallback",
    "Clarification",
    "RAG_CONFIDENCE_THRESHOLD",
]
