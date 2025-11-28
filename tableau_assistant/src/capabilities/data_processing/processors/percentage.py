"""
Percentage (占比) 处理器

实现占比分析功能
"""
import pandas as pd
import logging
from typing import List, Dict, Any

from tableau_assistant.src.capabilities.data_processing.processor.base import ProcessorBase
from tableau_assistant.src.capabilities.data_processing.processor.exceptions import (
    ValidationError,
    CalculationError
)
from tableau_assistant.src.models.query_result import QueryResult, ProcessingResult
from tableau_assistant.src.models.query_plan import QuerySubTask, ProcessingInstruction

logger = logging.getLogger(__name__)


class PercentageProcessor(ProcessorBase):
    """
    占比处理器
    
    计算各维度值在总体中的占比
    """
    
    def validate_instruction(self, instruction: Any) -> bool:
        """验证处理指令"""
        if not hasattr(instruction, 'source_tasks'):
            return False
        
        if len(instruction.source_tasks) < 1:
            logger.error(f"Percentage requires at least 1 source task, got {len(instruction.source_tasks)}")
            return False
        
        return True
    
    def process(
        self,
        source_results: List[QueryResult],
        instruction: ProcessingInstruction,
        subtasks: Dict[str, QuerySubTask]
    ) -> ProcessingResult:
        """
        执行占比计算
        
        Args:
            source_results: 源查询结果列表
            instruction: 处理指令
            subtasks: 子任务字典，用于获取字段信息
            
        Returns:
            处理结果
        """
        import time
        start_time = time.time()
        
        # 验证指令
        if not self.validate_instruction(instruction):
            raise ValidationError("Invalid Percentage instruction")
        
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
            raise ValidationError("subtasks parameter is required for Percentage calculation")
        
        logger.info(
            f"Processing Percentage with {len(source_results)} source(s): "
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
            raise ValidationError("No measure columns found for Percentage calculation")
        
        logger.debug(f"Dimensions: {dimension_cols}, Measures: {measure_cols}")
        
        # 执行占比计算
        result_df = self._calculate_percentage(
            first_result.data,
            dimension_cols,
            measure_cols
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Percentage calculation completed: {len(result_df)} rows in {processing_time_ms}ms")
        
        # 返回ProcessingResult
        return ProcessingResult(
            task_id=instruction.source_tasks[0],
            data=result_df,
            row_count=len(result_df),
            columns=list(result_df.columns),
            processing_type="percentage",
            source_tasks=instruction.source_tasks,
            processing_time_ms=processing_time_ms,
            metadata={"dimension_cols": dimension_cols, "measure_cols": measure_cols}
        )
    
    def _calculate_percentage(
        self,
        df: pd.DataFrame,
        dimension_cols: list[str],
        measure_cols: list[str]
    ) -> pd.DataFrame:
        """
        计算占比
        
        Args:
            df: 源数据框
            dimension_cols: 维度列
            measure_cols: 度量列
            
        Returns:
            占比结果DataFrame
        """
        try:
            result_df = df.clone()
            
            # 为每个度量列计算占比
            for measure_col in measure_cols:
                # 计算总和
                total = df[measure_col].sum()
                
                if total == 0 or total is None:
                    logger.warning(f"Total for {measure_col} is zero or null, percentage will be null")
                    # 创建空的占比列
                    result_df = result_df.with_columns(
                        pl.lit(None).alias(f"{measure_col}_percentage")
                    )
                else:
                    # 计算占比：(值 / 总和) * 100
                    result_df = result_df.with_columns(
                        (pl.col(measure_col) / total * 100).alias(f"{measure_col}_percentage")
                    )
            
            return result_df
            
        except Exception as e:
            logger.error(f"Percentage calculation failed: {str(e)}")
            raise CalculationError(f"Percentage calculation failed: {str(e)}")


# ============= 导出 =============

__all__ = [
    "PercentageProcessor",
]
