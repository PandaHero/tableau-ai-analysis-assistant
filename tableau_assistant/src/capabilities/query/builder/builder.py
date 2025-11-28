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
from typing import Optional, List, TYPE_CHECKING

if TYPE_CHECKING:
    from tableau_assistant.src.capabilities.date_processing.manager import DateManager
    from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatType
from tableau_assistant.src.models.query_plan import QuerySubTask
from tableau_assistant.src.models.vizql_types import (
    VizQLQuery,
    VizQLField,
    VizQLFilter,
    TableCalcField,
    TableCalcFieldReference,
    RunningTotalTableCalcSpecification,
    MovingTableCalcSpecification,
    RankTableCalcSpecification,
    PercentileTableCalcSpecification,
    PercentOfTotalTableCalcSpecification,
    PercentFromTableCalcSpecification,
    PercentDifferenceFromTableCalcSpecification,
    DifferenceFromTableCalcSpecification,
    CustomTableCalcSpecification,
    NestedTableCalcSpecification,
    TableCalcComputedAggregation,
    SortDirection,
)
from tableau_assistant.src.models.metadata import Metadata
from tableau_assistant.src.models.intent import TableCalcIntent
from tableau_assistant.src.capabilities.query.builder.intent_converter import IntentConverter
from tableau_assistant.src.capabilities.query.builder.date_filter_converter import DateFilterConverter
from tableau_assistant.src.capabilities.query.builder.filter_converter import FilterConverter

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
        week_start_day: int = 0,
        date_manager: Optional['DateManager'] = None
    ):
        """
        初始化查询构建器
        
        Args:
            metadata: Metadata模型对象
            anchor_date: 锚点日期（数据最新日期）
            week_start_day: 周开始日（0=周一，6=周日）
            date_manager: 日期管理器（可选，用于处理STRING类型日期字段）
        """
        self.metadata = metadata
        self.anchor_date = anchor_date
        self.week_start_day = week_start_day
        self.date_manager = date_manager
        
        # 初始化转换器
        self.intent_converter = IntentConverter(metadata=metadata)
        self.date_filter_converter = DateFilterConverter(
            metadata=metadata,
            anchor_date=anchor_date,
            week_start_day=week_start_day,
            date_manager=date_manager
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
            
            # 7. 转换表计算意图
            if subtask.table_calc_intents:
                for intent in subtask.table_calc_intents:
                    field = self.build_table_calc_field(intent)
                    fields.append(field)
                    logger.debug(
                        f"✓ 转换表计算: {intent.business_term} "
                        f"(type={intent.table_calc_type})"
                    )
            
            # 8. 验证字段列表
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
    
    def build_table_calc_field(self, intent: TableCalcIntent) -> TableCalcField:
        """
        构建表计算字段
        
        根据TableCalcIntent生成对应的TableCalcField。
        
        Args:
            intent: TableCalcIntent对象
        
        Returns:
            TableCalcField对象
        
        Raises:
            ValueError: 如果table_calc_type不支持或配置无效
        """
        try:
            logger.info(
                f"开始构建表计算字段: {intent.business_term} "
                f"(type={intent.table_calc_type})"
            )
            
            # 根据table_calc_type创建对应的TableCalcSpecification
            if intent.table_calc_type == "RUNNING_TOTAL":
                spec = self._build_running_total_spec(intent)
            elif intent.table_calc_type == "MOVING_CALCULATION":
                spec = self._build_moving_calc_spec(intent)
            elif intent.table_calc_type == "RANK":
                spec = self._build_rank_spec(intent)
            elif intent.table_calc_type == "PERCENTILE":
                spec = self._build_percentile_spec(intent)
            elif intent.table_calc_type == "PERCENT_OF_TOTAL":
                spec = self._build_percent_of_total_spec(intent)
            elif intent.table_calc_type == "PERCENT_FROM":
                spec = self._build_percent_from_spec(intent)
            elif intent.table_calc_type == "PERCENT_DIFFERENCE_FROM":
                spec = self._build_percent_difference_from_spec(intent)
            elif intent.table_calc_type == "DIFFERENCE_FROM":
                spec = self._build_difference_from_spec(intent)
            elif intent.table_calc_type == "CUSTOM":
                spec = self._build_custom_spec(intent)
            elif intent.table_calc_type == "NESTED":
                spec = self._build_nested_spec(intent)
            else:
                raise ValueError(
                    f"不支持的表计算类型: {intent.table_calc_type}"
                )
            
            # 转换排序方向
            sort_direction = None
            if intent.sort_direction:
                sort_direction = SortDirection[intent.sort_direction]
            
            # 创建TableCalcField
            field = TableCalcField(
                fieldCaption=intent.business_term,
                tableCalculation=spec,
                sortDirection=sort_direction,
                sortPriority=intent.sort_priority
            )
            
            logger.info(
                f"✓ 表计算字段构建完成: {intent.business_term} "
                f"(type={intent.table_calc_type})"
            )
            
            return field
        
        except Exception as e:
            logger.error(
                f"✗ 表计算字段构建失败: {intent.business_term} - {e}"
            )
            raise ValueError(
                f"构建表计算字段失败: {intent.business_term}, 错误: {e}"
            ) from e
    
    def _build_dimensions(self, config: dict) -> list:
        """
        从config中构建dimensions列表
        
        Args:
            config: table_calc_config字典
        
        Returns:
            TableCalcFieldReference列表
        """
        dimensions = config.get("dimensions", [])
        if not dimensions:
            raise ValueError("dimensions字段是必需的")
        
        return [
            TableCalcFieldReference(fieldCaption=dim)
            if isinstance(dim, str)
            else TableCalcFieldReference(**dim)
            for dim in dimensions
        ]
    
    def _build_running_total_spec(
        self, intent: TableCalcIntent
    ) -> RunningTotalTableCalcSpecification:
        """构建RUNNING_TOTAL规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 可选字段
        aggregation = None
        if "aggregation" in config:
            aggregation = TableCalcComputedAggregation[config["aggregation"]]
        
        restart_every = None
        if "restartEvery" in config:
            restart_val = config["restartEvery"]
            restart_every = (
                TableCalcFieldReference(fieldCaption=restart_val)
                if isinstance(restart_val, str)
                else TableCalcFieldReference(**restart_val)
            )
        
        return RunningTotalTableCalcSpecification(
            dimensions=dimensions,
            aggregation=aggregation,
            restartEvery=restart_every
        )
    
    def _build_moving_calc_spec(
        self, intent: TableCalcIntent
    ) -> MovingTableCalcSpecification:
        """构建MOVING_CALCULATION规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 必需字段
        previous = config.get("previous", 0)
        next_val = config.get("next", 0)
        include_current = config.get("includeCurrent", True)
        
        # 可选字段
        aggregation = None
        if "aggregation" in config:
            aggregation = TableCalcComputedAggregation[config["aggregation"]]
        
        fill_in_null = config.get("fillInNull")
        
        return MovingTableCalcSpecification(
            dimensions=dimensions,
            aggregation=aggregation,
            previous=previous,
            next=next_val,
            includeCurrent=include_current,
            fillInNull=fill_in_null
        )
    
    def _build_rank_spec(
        self, intent: TableCalcIntent
    ) -> RankTableCalcSpecification:
        """构建RANK规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 必需字段
        rank_type = config.get("rankType", "COMPETITION")
        
        # 可选字段
        direction = None
        if "direction" in config:
            direction = SortDirection[config["direction"]]
        
        return RankTableCalcSpecification(
            dimensions=dimensions,
            rankType=rank_type,
            direction=direction
        )
    
    def _build_percentile_spec(
        self, intent: TableCalcIntent
    ) -> PercentileTableCalcSpecification:
        """构建PERCENTILE规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 可选字段
        direction = None
        if "direction" in config:
            direction = SortDirection[config["direction"]]
        
        return PercentileTableCalcSpecification(
            dimensions=dimensions,
            direction=direction
        )
    
    def _build_percent_of_total_spec(
        self, intent: TableCalcIntent
    ) -> PercentOfTotalTableCalcSpecification:
        """构建PERCENT_OF_TOTAL规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        return PercentOfTotalTableCalcSpecification(dimensions=dimensions)
    
    def _build_percent_from_spec(
        self, intent: TableCalcIntent
    ) -> PercentFromTableCalcSpecification:
        """构建PERCENT_FROM规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 可选字段
        relative_to = config.get("relativeTo")
        
        return PercentFromTableCalcSpecification(
            dimensions=dimensions,
            relativeTo=relative_to
        )
    
    def _build_percent_difference_from_spec(
        self, intent: TableCalcIntent
    ) -> PercentDifferenceFromTableCalcSpecification:
        """构建PERCENT_DIFFERENCE_FROM规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 可选字段
        relative_to = config.get("relativeTo")
        
        return PercentDifferenceFromTableCalcSpecification(
            dimensions=dimensions,
            relativeTo=relative_to
        )
    
    def _build_difference_from_spec(
        self, intent: TableCalcIntent
    ) -> DifferenceFromTableCalcSpecification:
        """构建DIFFERENCE_FROM规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 可选字段
        relative_to = config.get("relativeTo")
        
        return DifferenceFromTableCalcSpecification(
            dimensions=dimensions,
            relativeTo=relative_to
        )
    
    def _build_custom_spec(
        self, intent: TableCalcIntent
    ) -> CustomTableCalcSpecification:
        """构建CUSTOM规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        return CustomTableCalcSpecification(dimensions=dimensions)
    
    def _build_nested_spec(
        self, intent: TableCalcIntent
    ) -> NestedTableCalcSpecification:
        """构建NESTED规范"""
        config = intent.table_calc_config
        dimensions = self._build_dimensions(config)
        
        # 必需字段
        field_caption = config.get("fieldCaption")
        if not field_caption:
            raise ValueError("NESTED类型需要fieldCaption字段")
        
        return NestedTableCalcSpecification(
            dimensions=dimensions,
            fieldCaption=field_caption
        )
    
    def _build_date_filter_for_string_field(
        self,
        field_name: str,
        start_date: str,
        end_date: str,
        question_granularity: Optional['TimeGranularity'] = None
    ) -> Optional[VizQLFilter]:
        """
        为STRING类型日期字段构建日期筛选器
        
        核心逻辑：
        1. 检查字段是否为STRING类型
        2. 从DateManager获取字段的日期格式
        3. 确定字段粒度和问题粒度
        4. 根据粒度关系选择筛选策略：
           - 字段粒度 == 问题粒度：直接使用 SetFilter
           - 字段粒度 > 问题粒度（字段更细）：使用 CalculationField 提取 + SetFilter
           - 字段粒度 < 问题粒度（字段更粗）：无法实现，返回 None
        
        Args:
            field_name: 字段名称
            start_date: 开始日期（ISO格式 YYYY-MM-DD）
            end_date: 结束日期（ISO格式 YYYY-MM-DD）
            question_granularity: 问题的时间粒度（可选）
        
        Returns:
            VizQLFilter对象，如果无法处理则返回None
        
        Examples:
            >>> # 场景1：字段=日期，问题=月 → 提取月份
            >>> filter = query_builder._build_date_filter_for_string_field(
            ...     field_name="Order Date",  # "2024-01-15"
            ...     start_date="2024-01-01",
            ...     end_date="2024-03-31",
            ...     question_granularity=TimeGranularity.MONTH
            ... )
            
            >>> # 场景2：字段=月，问题=月 → 直接匹配
            >>> filter = query_builder._build_date_filter_for_string_field(
            ...     field_name="Month",  # "2024-01"
            ...     start_date="2024-01-01",
            ...     end_date="2024-03-31",
            ...     question_granularity=TimeGranularity.MONTH
            ... )
        """
        if not self.date_manager:
            logger.debug("DateManager未注入，无法处理STRING类型日期字段")
            return None
        
        # 1. 检查字段是否为STRING类型
        field_metadata = self.metadata.get_field(field_name)
        if not field_metadata or field_metadata.dataType != "STRING":
            logger.debug(f"字段 {field_name} 不是STRING类型")
            return None
        
        # 2. 从DateManager获取字段的日期格式
        format_type = self.date_manager.get_cached_field_format(field_name)
        if not format_type:
            logger.debug(f"字段 {field_name} 未检测到日期格式")
            return None
        
        # 3. 获取格式信息
        format_info = self.date_manager.get_format_info(format_type)
        date_format_pattern = format_info.get("pattern", "")
        format_name = format_info.get("name", "")
        
        logger.info(
            f"为STRING日期字段 {field_name} 构建筛选器 "
            f"(格式: {format_name}, 模式: {date_format_pattern})"
        )
        
        from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatType
        from tableau_assistant.src.models.vizql_types import SetFilter, CalculationField, QuantitativeDateFilter, FilterField
        from datetime import datetime as dt
        from dateutil.relativedelta import relativedelta
        
        # 4. 根据日期格式粒度选择筛选策略
        # VizQL API 支持 CalculationField，可以动态创建计算字段！
        # 策略选择：
        #   - 对于粒度较粗的格式（年月、年份）：使用 SetFilter（性能更好）
        #   - 对于完整日期格式：可以使用 CalculationField + DATEPARSE + QuantitativeDateFilter
        
        # 4.1 年月格式（YYYY-MM）- 使用SetFilter筛选年月值
        if format_type == DateFormatType.YEAR_MONTH:
            # 生成日期范围内的所有年月值
            start_dt = dt.strptime(start_date, "%Y-%m-%d")
            end_dt = dt.strptime(end_date, "%Y-%m-%d")
            
            year_months = []
            current = start_dt.replace(day=1)  # 月初
            while current <= end_dt:
                year_months.append(current.strftime("%Y-%m"))
                current += relativedelta(months=1)
            
            logger.info(
                f"✓ 使用SetFilter筛选年月字段: {field_name} "
                f"({len(year_months)} 个月份: {year_months[0]} 至 {year_months[-1]})"
            )
            
            # 使用SetFilter
            set_filter = SetFilter(
                field=FilterField(fieldCaption=field_name),
                filterType="SET",
                values=year_months
            )
            
            return set_filter
        
        # 4.2 年份格式（YYYY）- 使用SetFilter筛选年份值
        elif format_type == DateFormatType.YEAR_ONLY:
            # 生成日期范围内的所有年份
            start_year = int(start_date[:4])
            end_year = int(end_date[:4])
            
            years = [str(year) for year in range(start_year, end_year + 1)]
            
            logger.info(
                f"✓ 使用SetFilter筛选年份字段: {field_name} "
                f"({len(years)} 个年份: {years[0]} 至 {years[-1]})"
            )
            
            # 使用SetFilter
            set_filter = SetFilter(
                field=FilterField(fieldCaption=field_name),
                filterType="SET",
                values=years
            )
            
            return set_filter
        
        # 4.3 月年格式（MM/YYYY）- 使用SetFilter
        elif format_type == DateFormatType.MONTH_YEAR:
            # 生成日期范围内的所有月年值（MM/YYYY格式）
            start_dt = dt.strptime(start_date, "%Y-%m-%d")
            end_dt = dt.strptime(end_date, "%Y-%m-%d")
            
            month_years = []
            current = start_dt.replace(day=1)
            while current <= end_dt:
                month_years.append(current.strftime("%m/%Y"))
                current += relativedelta(months=1)
            
            logger.info(
                f"✓ 使用SetFilter筛选月年字段: {field_name} "
                f"({len(month_years)} 个月份)"
            )
            
            set_filter = SetFilter(
                field=FilterField(fieldCaption=field_name),
                filterType="SET",
                values=month_years
            )
            
            return set_filter
        
        # 4.4 季度格式（YYYY-QN）- 使用SetFilter
        elif format_type == DateFormatType.QUARTER:
            # 生成日期范围内的所有季度值（YYYY-Q1, YYYY-Q2, YYYY-Q3, YYYY-Q4）
            start_dt = dt.strptime(start_date, "%Y-%m-%d")
            end_dt = dt.strptime(end_date, "%Y-%m-%d")
            
            quarters = []
            current = start_dt
            
            while current <= end_dt:
                year = current.year
                quarter = (current.month - 1) // 3 + 1  # 计算季度：1-3月=Q1, 4-6月=Q2, 7-9月=Q3, 10-12月=Q4
                quarter_str = f"{year}-Q{quarter}"
                
                if not quarters or quarters[-1] != quarter_str:
                    quarters.append(quarter_str)
                
                # 移动到下一个季度的第一天
                if current.month <= 3:
                    current = current.replace(month=4, day=1)
                elif current.month <= 6:
                    current = current.replace(month=7, day=1)
                elif current.month <= 9:
                    current = current.replace(month=10, day=1)
                else:
                    current = current.replace(year=year + 1, month=1, day=1)
            
            logger.info(
                f"✓ 使用SetFilter筛选季度字段: {field_name} "
                f"({len(quarters)} 个季度: {quarters[0]} 至 {quarters[-1]})"
            )
            
            set_filter = SetFilter(
                field=FilterField(fieldCaption=field_name),
                filterType="SET",
                values=quarters
            )
            
            return set_filter
        
        # 4.5 年周格式（YYYY-WNN）- 使用SetFilter
        elif format_type == DateFormatType.YEAR_WEEK:
            # 生成日期范围内的所有周值（ISO week: YYYY-W01, YYYY-W02, ..., YYYY-W52/53）
            start_dt = dt.strptime(start_date, "%Y-%m-%d")
            end_dt = dt.strptime(end_date, "%Y-%m-%d")
            
            weeks = []
            current = start_dt
            
            while current <= end_dt:
                # 获取 ISO 周数
                iso_year, iso_week, _ = current.isocalendar()
                week_str = f"{iso_year}-W{iso_week:02d}"
                
                if not weeks or weeks[-1] != week_str:
                    weeks.append(week_str)
                
                # 移动到下一周
                current += relativedelta(weeks=1)
            
            logger.info(
                f"✓ 使用SetFilter筛选周字段: {field_name} "
                f"({len(weeks)} 周: {weeks[0]} 至 {weeks[-1]})"
            )
            
            set_filter = SetFilter(
                field=FilterField(fieldCaption=field_name),
                filterType="SET",
                values=weeks
            )
            
            return set_filter
        
        # 4.6 完整日期格式 - 使用 CalculationField + DATEPARSE
        else:
            # VizQL API 支持 CalculationField，可以使用 DATEPARSE 函数！
            # 策略：
            # 1. 创建一个 CalculationField，使用 DATEPARSE 将 STRING 转换为 DATE
            # 2. 对转换后的日期字段使用 QuantitativeDateFilter
            
            # 注意：这个 CalculationField 需要添加到查询的 fields 数组中
            # 但当前方法只返回 Filter，不返回 Field
            # 因此，我们需要在调用方（DateFilterConverter）中处理这个逻辑
            
            # 对于小范围日期，仍然使用 SetFilter（性能更好）
            start_dt = dt.strptime(start_date, "%Y-%m-%d")
            end_dt = dt.strptime(end_date, "%Y-%m-%d")
            days_diff = (end_dt - start_dt).days
            
            if days_diff <= 100:
                # 日期范围较小，使用SetFilter
                dates = []
                current = start_dt
                while current <= end_dt:
                    # 根据格式转换日期
                    if format_type == DateFormatType.US_DATE:
                        dates.append(current.strftime("%m/%d/%Y"))
                    elif format_type == DateFormatType.EU_DATE:
                        dates.append(current.strftime("%d/%m/%Y"))
                    elif format_type == DateFormatType.ISO_DATE:
                        dates.append(current.strftime("%Y-%m-%d"))
                    elif format_type == DateFormatType.TIMESTAMP:
                        # 对于时间戳，只取日期部分
                        dates.append(current.strftime("%Y-%m-%d"))
                    else:
                        # 默认使用ISO格式
                        dates.append(current.strftime("%Y-%m-%d"))
                    
                    current += relativedelta(days=1)
                
                logger.info(
                    f"✓ 使用SetFilter筛选日期字段: {field_name} "
                    f"({len(dates)} 天)"
                )
                
                set_filter = SetFilter(
                    field=FilterField(fieldCaption=field_name),
                    filterType="SET",
                    values=dates
                )
                
                return set_filter
            else:
                # 日期范围较大，使用 CalculationField + DATEPARSE
                # 注意：这需要在 DateFilterConverter 中实现完整逻辑
                logger.info(
                    f"✓ 日期范围较大（{days_diff}天），建议使用 DATEPARSE 计算字段"
                )
                logger.info(
                    f"提示：可以在查询中添加 CalculationField: "
                    f'DATEPARSE("{date_format_pattern}", [{field_name}])'
                )
                
                # 返回 None，表示需要特殊处理
                # TODO: 在 DateFilterConverter 中实现 CalculationField + QuantitativeDateFilter
                return None


# ============= 导出 =============

__all__ = [
    "QueryBuilder",
]
