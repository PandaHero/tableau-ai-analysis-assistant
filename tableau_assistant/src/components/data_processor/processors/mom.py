"""
MoM (Month-over-Month) 处理器

实现环比分析功能
"""
import polars as pl
import logging
from typing import List, Dict, Any

from tableau_assistant.src.components.data_processor.base import ProcessorBase
from tableau_assistant.src.components.data_processor.exceptions import (
    ValidationError,
    CalculationError
)
from tableau_assistant.src.models.query_result import QueryResult, ProcessingResult
from tableau_assistant.src.models.query_plan import QuerySubTask, ProcessingInstruction

logger = logging.getLogger(__name__)


class MoMProcessor(ProcessorBase):
    """
    环比处理器
    
    计算多个连续时间段的环比变化（支持2个或更多时间段的对比）
    """
    
    def validate_instruction(self, instruction: Any) -> bool:
        """验证处理指令"""
        if not hasattr(instruction, 'source_tasks'):
            return False
        
        if len(instruction.source_tasks) < 2:
            logger.error(f"MoM requires at least 2 source tasks, got {len(instruction.source_tasks)}")
            return False
        
        return True
    
    def process(
        self,
        source_results: List[QueryResult],
        instruction: ProcessingInstruction,
        subtasks: Dict[str, QuerySubTask]
    ) -> ProcessingResult:
        """
        执行环比计算
        
        Args:
            source_results: 源查询结果列表
            instruction: 处理指令
            subtasks: 子任务字典，用于获取字段和时间信息
            
        Returns:
            处理结果
        """
        import time
        start_time = time.time()
        
        # 验证指令
        if not self.validate_instruction(instruction):
            raise ValidationError("Invalid MoM instruction")
        
        # 验证source_results
        if not source_results:
            raise ValidationError("source_results cannot be empty")
        
        if len(source_results) != len(instruction.source_tasks):
            raise ValidationError(
                f"Expected {len(instruction.source_tasks)} source results, "
                f"got {len(source_results)}"
            )
        
        # 验证subtasks参数
        if not subtasks:
            raise ValidationError("subtasks parameter is required for MoM calculation")
        
        logger.info(
            f"Processing MoM with {len(source_results)} time periods: "
            f"{[r.task_id for r in source_results]}"
        )
        
        # 获取第一个任务的字段信息
        first_result = source_results[0]
        first_task_id = first_result.task_id
        
        if first_task_id not in subtasks:
            raise ValidationError(f"Subtask {first_task_id} not found in subtasks dict")
        
        # 从subtask获取维度和度量信息
        dimension_cols, measure_cols = self._get_field_info_from_subtask(
            subtasks[first_task_id],
            first_result.data
        )
        
        if not measure_cols:
            raise ValidationError("No measure columns found for MoM calculation")
        
        logger.debug(f"Dimensions: {dimension_cols}, Measures: {measure_cols}")
        
        # 从filters中提取时间标签
        time_labels = self._extract_time_labels_from_filters(source_results, subtasks)
        
        # 执行环比计算
        result_df = self._calculate_mom_multi(
            source_results,
            dimension_cols,
            measure_cols,
            time_labels
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"MoM calculation completed: {len(result_df)} rows in {processing_time_ms}ms")
        
        # 返回ProcessingResult
        return ProcessingResult(
            task_id=instruction.source_tasks[0],
            data=result_df,
            row_count=len(result_df),
            columns=list(result_df.columns),
            processing_type="mom",
            source_tasks=instruction.source_tasks,
            processing_time_ms=processing_time_ms,
            metadata={"time_labels": time_labels}
        )
    
    def _extract_time_labels_from_filters(
        self,
        source_results: List[QueryResult],
        subtasks: Dict[str, QuerySubTask]
    ) -> list[str]:
        """
        从subtask的filters中提取时间标签
        
        Args:
            source_results: 源查询结果列表
            subtasks: 子任务字典
            
        Returns:
            时间标签列表
        """
        time_labels = []
        
        for result in source_results:
            task_id = result.task_id
            
            if task_id not in subtasks:
                time_labels.append(task_id)
                continue
            
            subtask = subtasks[task_id]
            
            # 从filters中提取时间信息
            time_label = self._extract_time_from_filters(subtask.filters)
            
            if time_label:
                time_labels.append(time_label)
            else:
                time_labels.append(task_id)
        
        logger.debug(f"Extracted time labels: {time_labels}")
        return time_labels
    
    def _extract_time_from_filters(self, filters: list) -> str:
        """
        从filters中提取时间标签
        
        Args:
            filters: 筛选器列表
            
        Returns:
            时间标签字符串
        """
        if not filters:
            return ""
        
        from tableau_assistant.src.models.vizql_types import RelativeDateFilter, QuantitativeDateFilter
        
        for filter_obj in filters:
            # 检查RelativeDateFilter
            if isinstance(filter_obj, RelativeDateFilter):
                anchor_date = filter_obj.anchorDate
                
                if anchor_date and anchor_date.startswith("OFFSET:"):
                    # 格式: "OFFSET:-1:MONTHS" -> "上月"
                    parts = anchor_date.split(":")
                    if len(parts) == 3:
                        offset_value = int(parts[1])
                        offset_unit = parts[2]
                        
                        if offset_unit == "MONTHS":
                            if offset_value == -1:
                                return "上月"
                            elif offset_value == -2:
                                return "上上月"
                            else:
                                return f"{offset_value:+d}月"
                        elif offset_unit == "WEEKS":
                            if offset_value == -1:
                                return "上周"
                            else:
                                return f"{offset_value:+d}周"
            
            # 检查QuantitativeDateFilter
            elif isinstance(filter_obj, QuantitativeDateFilter):
                if filter_obj.minDate:
                    # 从日期中提取月份
                    import re
                    month_match = re.search(r'(\d{4})-(\d{2})', filter_obj.minDate)
                    if month_match:
                        return f"{month_match.group(1)}年{int(month_match.group(2))}月"
        
        return ""
    
    def _calculate_mom_multi(
        self,
        source_results: List[QueryResult],
        dimension_cols: list[str],
        measure_cols: list[str],
        time_labels: list[str]
    ) -> pl.DataFrame:
        """
        计算多个时间段的环比
        
        Args:
            source_results: 源查询结果列表
            dimension_cols: 维度列
            measure_cols: 度量列
            time_labels: 时间标签列表
            
        Returns:
            环比结果DataFrame
        """
        try:
            # 获取所有数据框
            dfs = [result.data for result in source_results]
            
            # 为每个数据框的度量列添加时间标签后缀
            renamed_dfs = []
            for i, (df, time_label) in enumerate(zip(dfs, time_labels)):
                if i == 0:
                    # 第一个数据框保持原列名
                    renamed_dfs.append(df)
                else:
                    # 其他数据框的度量列添加时间标签后缀
                    rename_map = {
                        col: f"{col}_{time_label}" for col in measure_cols
                    }
                    renamed_dfs.append(df.rename(rename_map))
            
            # 合并所有数据框
            if dimension_cols:
                # 有维度列：按维度进行outer join
                result_df = renamed_dfs[0]
                for df in renamed_dfs[1:]:
                    result_df = result_df.join(
                        df,
                        on=dimension_cols,
                        how="outer",
                        coalesce=True  # 合并join键，避免产生重复列
                    )
            else:
                # 无维度列：只保留度量列进行横向拼接
                # 从第一个数据框中选择度量列
                result_df = renamed_dfs[0].select(measure_cols)
                
                # 从其他数据框中选择重命名后的度量列
                for i, (df, time_label) in enumerate(zip(renamed_dfs[1:], time_labels[1:]), start=1):
                    renamed_measure_cols = [f"{col}_{time_label}" for col in measure_cols]
                    result_df = pl.concat([result_df, df.select(renamed_measure_cols)], how="horizontal")
            
            # 计算环比变化和增长率（相对于第一个时间段）
            base_time_label = time_labels[0]
            for i in range(1, len(time_labels)):
                compare_time_label = time_labels[i]
                
                for measure_col in measure_cols:
                    base_col = measure_col
                    compare_col = f"{measure_col}_{compare_time_label}"
                    
                    # 环比变化：基准期 - 对比期
                    # 列名格式：度量名_mom_change_基准vs对比
                    change_col = f"{measure_col}_mom_change_{base_time_label}vs{compare_time_label}"
                    result_df = result_df.with_columns(
                        (pl.col(base_col) - pl.col(compare_col)).alias(change_col)
                    )
                    
                    # 环比增长率：(基准期 - 对比期) / 对比期 * 100
                    # 列名格式：度量名_mom_rate_基准vs对比
                    rate_col = f"{measure_col}_mom_rate_{base_time_label}vs{compare_time_label}"
                    result_df = result_df.with_columns(
                        ((pl.col(base_col) - pl.col(compare_col)) / pl.col(compare_col) * 100)
                        .alias(rate_col)
                    )
            
            return result_df
            
        except Exception as e:
            logger.error(f"MoM calculation failed: {str(e)}")
            raise CalculationError(f"MoM calculation failed: {str(e)}")


# ============= 导出 =============

__all__ = [
    "MoMProcessor",
]
