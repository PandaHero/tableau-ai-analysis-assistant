"""
QueryBuilder主类

负责协调各个转换器，将QuerySubTask转换为VizQLQuery。

流程：
1. 使用IntentConverter转换dimension_intents、measure_intents、date_field_intents
2. 使用DateFilterConverter转换date_filter_intent
3. 使用FilterConverter转换filter_intents和topn_intent
4. 组装VizQLQuery对象
"""
import logging
from datetime import datetime
from typing import Optional, List
from tableau_assistant.src.models.query_plan import QuerySubTask
from tableau_assistant.src.models.vizql_types import (
    VizQLQuery,
    VizQLField,
    VizQLFilter,
)
from tableau_assistant.src.models.metadata import Metadata
from tableau_assistant.src.components.query_builder.intent_converter import IntentConverter
from tableau_assistant.src.components.query_builder.date_filter_converter import DateFilterConverter
from tableau_assistant.src.components.query_builder.filter_converter import FilterConverter

logger = logging.getLogger(__name__)


class QueryBuilder:
    """
    查询构建器（主协调器）
    
    负责将QuerySubTask（包含Intent模型）转换为VizQLQuery（包含VizQL模型）。
    """
    
    def __init__(
        self,
        metadata: Metadata,
        anchor_date: Optional[datetime] = None,
        week_start_day: int = 0
    ):
        """
        初始化查询构建器
        
        Args:
            metadata: Metadata模型对象
            anchor_date: 锚点日期（数据最新日期）
            week_start_day: 周开始日（0=周一，6=周日）
        """
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        
        # 初始化转换器
        self.intent_converter = IntentConverter(metadata=metadata)
        self.date_filter_converter = DateFilterConverter(
            metadata=metadata,
            anchor_date=anchor_date,
            week_start_day=week_start_day
        )
        self.filter_converter = FilterConverter(metadata=metadata)
        
        logger.info(
            f"QueryBuilder初始化完成 "
            f"(datasource={metadata.datasource_name}, "
            f"fields={metadata.field_count})"
        )
    
    def build_query(self, subtask: QuerySubTask) -> VizQLQuery:
        """
        构建VizQL查询
        
        流程：
        1. 转换dimension_intents为VizQLField
        2. 转换measure_intents为VizQLField
        3. 转换date_field_intents为VizQLField
        4. 转换date_filter_intent为VizQL日期筛选器
        5. 转换filter_intents为VizQLFilter
        6. 转换topn_intent为TopNFilter
        7. 组装VizQLQuery
        
        Args:
            subtask: QuerySubTask对象
        
        Returns:
            VizQLQuery对象
        
        Raises:
            ValueError: 如果转换失败
        """
        try:
            logger.info(
                f"开始构建查询: {subtask.question_id} - {subtask.question_text}"
            )
            
            fields: List[VizQLField] = []
            filters: List[VizQLFilter] = []
            
            # 收集所有date_field_intents中的字段名（用于去重）
            date_field_names = {intent.technical_field for intent in subtask.date_field_intents}
            
            # 1. 转换维度意图（跳过已在date_field_intents中的字段）
            for intent in subtask.dimension_intents:
                # 如果该字段已在date_field_intents中，跳过
                if intent.technical_field in date_field_names:
                    logger.debug(
                        f"⊘ 跳过维度字段 {intent.technical_field}（已在date_field_intents中）"
                    )
                    continue
                    
                field = self.intent_converter.convert_dimension_intent(intent)
                fields.append(field)
                logger.debug(
                    f"✓ 转换维度: {intent.business_term} → {field.fieldCaption}"
                )
            
            # 2. 转换度量意图
            for intent in subtask.measure_intents:
                field = self.intent_converter.convert_measure_intent(intent)
                fields.append(field)
                logger.debug(
                    f"✓ 转换度量: {intent.business_term} → {field.fieldCaption}"
                )
            
            # 3. 转换日期字段意图
            for intent in subtask.date_field_intents:
                # 检查是否是STRING类型的日期字段
                field_meta = self.metadata.get_field(intent.technical_field)
                if field_meta and field_meta.dataType == "STRING" and intent.date_function:
                    # STRING类型 + 日期函数：生成包含DATEPARSE和函数的单个计算字段
                    # 根据SDK文档，Field可以同时有fieldCaption和calculation
                    # 例如: { "fieldCaption": "月份", "calculation": "MONTH(DATEPARSE('yyyy-MM-dd', [日期]))" }
                    logger.debug(
                        f"检测到STRING类型日期字段: {intent.technical_field}，生成DATEPARSE+函数计算字段"
                    )
                    
                    # 检测日期格式
                    date_format = self.date_filter_converter.detect_date_format(
                        field_meta.sample_values or []
                    )
                    if not date_format:
                        logger.warning(
                            f"无法识别字段 '{intent.technical_field}' 的日期格式，使用默认格式 'yyyy-MM-dd'"
                        )
                        date_format = "yyyy-MM-dd"
                    
                    # 生成包含DATEPARSE和日期函数的计算字段
                    from tableau_assistant.src.models.vizql_types import (
                        CalculationField,
                        SortDirection
                    )
                    
                    dateparse_expr = f"DATEPARSE('{date_format}', [{intent.technical_field}])"
                    calculation = f"{intent.date_function}({dateparse_expr})"
                    
                    # 转换排序方向
                    sort_direction = None
                    if intent.sort_direction:
                        sort_direction = SortDirection[intent.sort_direction]
                    
                    calc_field = CalculationField(
                        fieldCaption=f"{intent.date_function}_{intent.technical_field}",
                        calculation=calculation,
                        sortDirection=sort_direction,
                        sortPriority=intent.sort_priority
                    )
                    
                    fields.append(calc_field)
                    logger.debug(
                        f"✓ 转换日期字段: {intent.business_term} → {calc_field.fieldCaption} (calculation={calculation})"
                    )
                else:
                    # DATE/DATETIME类型或无日期函数：直接转换
                    field = self.intent_converter.convert_date_field_intent(intent)
                    fields.append(field)
                    logger.debug(
                        f"✓ 转换日期字段: {intent.business_term} → {field.fieldCaption}"
                    )
            
            # 4. 转换日期筛选意图
            if subtask.date_filter_intent:
                filter_obj, dateparse_field = self.date_filter_converter.convert(
                    subtask.date_filter_intent
                )
                
                # 如果生成了DATEPARSE字段，添加到fields列表
                if dateparse_field:
                    fields.append(dateparse_field)
                    logger.debug(
                        f"✓ 添加DATEPARSE字段: {dateparse_field.calculation}"
                    )
                
                # 添加日期筛选器
                if filter_obj:
                    filters.append(filter_obj)
                    logger.debug(
                        f"✓ 转换日期筛选: {subtask.date_filter_intent.business_term}"
                    )
            
            # 5. 转换非日期筛选意图
            if subtask.filter_intents:
                for intent in subtask.filter_intents:
                    filter_obj = self.filter_converter.convert_filter_intent(intent)
                    filters.append(filter_obj)
                    logger.debug(
                        f"✓ 转换筛选: {intent.business_term} "
                        f"(type={intent.filter_type})"
                    )
            
            # 6. 转换TopN意图
            if subtask.topn_intent:
                filter_obj = self.filter_converter.convert_topn_intent(
                    subtask.topn_intent
                )
                filters.append(filter_obj)
                logger.debug(
                    f"✓ 转换TopN: {subtask.topn_intent.business_term} "
                    f"(n={subtask.topn_intent.n}, direction={subtask.topn_intent.direction})"
                )
            
            # 7. 验证字段列表
            if not fields:
                raise ValueError(
                    f"查询必须至少包含一个字段: {subtask.question_id}"
                )
            
            # 8. 分配排序优先级
            self._assign_sort_priorities(fields)
            
            # 9. 验证排序优先级
            self._validate_sort_priorities(fields)
            
            # 10. 组装VizQLQuery
            query = VizQLQuery(
                fields=fields,
                filters=filters if filters else None
            )
            
            logger.info(
                f"✓ 查询构建完成: {subtask.question_id} "
                f"(fields={len(fields)}, filters={len(filters)})"
            )
            
            return query
        
        except Exception as e:
            logger.error(
                f"✗ 查询构建失败: {subtask.question_id} - {e}"
            )
            raise ValueError(
                f"构建查询失败: {subtask.question_id}, 错误: {e}"
            ) from e
    
    def _assign_sort_priorities(self, fields: List[VizQLField]) -> None:
        """
        为字段分配唯一的sortPriority值
        
        规则：
        - 只为度量字段分配sortPriority（从0开始）
        - 维度字段不需要排序，移除其sortDirection和sortPriority
        - 每个度量字段获得唯一的sortPriority值
        
        Args:
            fields: VizQLField列表（会被原地修改）
        """
        priority = 0
        
        # 为度量字段分配优先级，同时移除维度字段的排序
        for field in fields:
            # 判断是否为度量字段（有function属性且function不为None）
            is_measure = hasattr(field, 'function') and field.function is not None
            
            if is_measure:
                # 度量字段：如果有sortDirection，分配sortPriority
                if hasattr(field, 'sortDirection') and field.sortDirection is not None:
                    field.sortPriority = priority
                    priority += 1
                    logger.debug(
                        f"分配度量字段排序优先级: {field.fieldCaption} → {field.sortPriority}"
                    )
            else:
                # 维度字段：移除排序相关属性
                if hasattr(field, 'sortDirection'):
                    if field.sortDirection is not None:
                        logger.debug(
                            f"移除维度字段排序: {field.fieldCaption}"
                        )
                    field.sortDirection = None
                if hasattr(field, 'sortPriority'):
                    field.sortPriority = None
    
    def _validate_sort_priorities(self, fields: List[VizQLField]) -> None:
        """
        验证排序优先级的唯一性
        
        确保没有重复的sortPriority值。
        
        Args:
            fields: VizQLField列表
        
        Raises:
            ValueError: 如果发现重复的sortPriority值
        """
        # 收集所有非None的sortPriority值
        priorities = []
        for field in fields:
            if hasattr(field, 'sortPriority') and field.sortPriority is not None:
                priorities.append((field.fieldCaption, field.sortPriority))
        
        # 检查是否有重复
        if priorities:
            priority_values = [p[1] for p in priorities]
            if len(priority_values) != len(set(priority_values)):
                # 找出重复的优先级
                duplicates = {}
                for caption, priority in priorities:
                    if priority not in duplicates:
                        duplicates[priority] = []
                    duplicates[priority].append(caption)
                
                duplicate_info = [
                    f"priority {p}: {', '.join(fields)}"
                    for p, fields in duplicates.items()
                    if len(fields) > 1
                ]
                
                raise ValueError(
                    f"发现重复的sortPriority值: {'; '.join(duplicate_info)}"
                )
        
        logger.debug(
            f"✓ 排序优先级验证通过: {len(priorities)} 个字段有排序"
        )


# ============= 导出 =============

__all__ = [
    "QueryBuilder",
]
