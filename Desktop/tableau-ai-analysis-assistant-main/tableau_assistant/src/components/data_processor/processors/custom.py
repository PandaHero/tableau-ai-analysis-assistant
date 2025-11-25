"""
Custom (自定义) 处理器

实现基于自定义公式的计算功能
"""
import polars as pl
import logging
from typing import List, Dict, Any
import re

from tableau_assistant.src.components.data_processor.base import ProcessorBase
from tableau_assistant.src.components.data_processor.exceptions import (
    ValidationError,
    CalculationError
)
from tableau_assistant.src.models.query_result import QueryResult, ProcessingResult
from tableau_assistant.src.models.query_plan import QuerySubTask, ProcessingInstruction

logger = logging.getLogger(__name__)


class CustomProcessor(ProcessorBase):
    """
    自定义处理器
    
    基于calculation_formula执行自定义计算
    """
    
    def validate_instruction(self, instruction: Any) -> bool:
        """验证处理指令"""
        if not hasattr(instruction, 'source_tasks'):
            return False
        
        if len(instruction.source_tasks) < 1:
            logger.error(f"Custom requires at least 1 source task, got {len(instruction.source_tasks)}")
            return False
        
        if not hasattr(instruction, 'calculation_formula') or not instruction.calculation_formula:
            logger.error("Custom processor requires calculation_formula")
            return False
        
        return True
    
    def process(
        self,
        source_results: List[QueryResult],
        instruction: ProcessingInstruction,
        subtasks: Dict[str, QuerySubTask]
    ) -> ProcessingResult:
        """
        执行自定义计算
        
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
            raise ValidationError("Invalid Custom instruction")
        
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
            raise ValidationError("subtasks parameter is required for Custom calculation")
        
        logger.info(
            f"Processing Custom with {len(source_results)} source(s): "
            f"{[r.task_id for r in source_results]}"
        )
        
        # 执行自定义计算
        result_df = self._execute_custom_formula(
            source_results,
            instruction.calculation_formula,
            subtasks
        )
        
        processing_time_ms = int((time.time() - start_time) * 1000)
        
        logger.info(f"Custom calculation completed: {len(result_df)} rows in {processing_time_ms}ms")
        
        # 返回ProcessingResult
        return ProcessingResult(
            task_id=instruction.source_tasks[0],
            data=result_df,
            row_count=len(result_df),
            columns=list(result_df.columns),
            processing_type="custom",
            source_tasks=instruction.source_tasks,
            processing_time_ms=processing_time_ms,
            metadata={"formula": instruction.calculation_formula}
        )
    
    def _execute_custom_formula(
        self,
        source_results: List[QueryResult],
        formula: str,
        subtasks: Dict[str, QuerySubTask]
    ) -> pl.DataFrame:
        """
        执行自定义公式
        
        Args:
            source_results: 源查询结果列表
            formula: 计算公式
            subtasks: 子任务字典
            
        Returns:
            计算结果DataFrame
        """
        try:
            # 如果只有一个源，直接使用该数据框
            if len(source_results) == 1:
                result_df = source_results[0].data.clone()
            else:
                # 多个源：需要合并数据框
                result_df = self._merge_source_results(source_results, subtasks)
            
            # 解析公式并执行计算
            result_df = self._apply_formula(result_df, formula)
            
            return result_df
            
        except Exception as e:
            logger.error(f"Custom calculation failed: {str(e)}")
            raise CalculationError(f"Custom calculation failed: {str(e)}")
    
    def _merge_source_results(
        self,
        source_results: List[QueryResult],
        subtasks: Dict[str, QuerySubTask]
    ) -> pl.DataFrame:
        """
        合并多个源数据框
        
        Args:
            source_results: 源查询结果列表
            subtasks: 子任务字典
            
        Returns:
            合并后的DataFrame
        """
        # 获取第一个任务的字段信息
        first_result = source_results[0]
        first_task_id = first_result.task_id
        
        if first_task_id not in subtasks:
            raise ValidationError(f"Subtask {first_task_id} not found in subtasks dict")
        
        dimension_cols, measure_cols = self._get_field_info_from_subtask(
            subtasks[first_task_id],
            first_result.data
        )
        
        # 为每个数据框的度量列添加任务ID后缀
        renamed_dfs = []
        for i, result in enumerate(source_results):
            df = result.data
            task_id = result.task_id
            
            if i == 0:
                # 第一个数据框保持原列名
                renamed_dfs.append(df)
            else:
                # 其他数据框的度量列添加任务ID后缀
                rename_map = {
                    col: f"{col}_{task_id}" for col in measure_cols
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
            # 无维度列：横向拼接
            result_df = pl.concat(renamed_dfs, how="horizontal")
        
        return result_df
    
    def _apply_formula(
        self,
        df: pl.DataFrame,
        formula: str
    ) -> pl.DataFrame:
        """
        应用计算公式
        
        支持的公式格式示例：
        - "col1 + col2" -> 创建新列 "result"
        - "col1 / col2 * 100" -> 创建新列 "result"
        - "result = col1 - col2" -> 创建新列 "result"
        
        Args:
            df: 数据框
            formula: 计算公式
            
        Returns:
            应用公式后的DataFrame
        """
        try:
            # 解析公式：检查是否有显式的输出列名
            if "=" in formula:
                parts = formula.split("=", 1)
                output_col = parts[0].strip()
                expression = parts[1].strip()
            else:
                output_col = "result"
                expression = formula.strip()
            
            # 将公式中的列名替换为Polars表达式
            # 支持基本的算术运算：+, -, *, /, ()
            polars_expr = self._convert_to_polars_expr(expression, df.columns)
            
            # 应用公式
            result_df = df.with_columns(
                polars_expr.alias(output_col)
            )
            
            logger.debug(f"Applied formula: {output_col} = {expression}")
            
            return result_df
            
        except Exception as e:
            logger.error(f"Failed to apply formula '{formula}': {str(e)}")
            raise CalculationError(f"Failed to apply formula '{formula}': {str(e)}")
    
    def _convert_to_polars_expr(
        self,
        expression: str,
        available_columns: list[str]
    ) -> pl.Expr:
        """
        将字符串表达式转换为Polars表达式
        
        Args:
            expression: 字符串表达式
            available_columns: 可用的列名列表
            
        Returns:
            Polars表达式
        """
        # 简单实现：将列名替换为pl.col()
        # 注意：这是一个简化版本，实际生产环境需要更复杂的解析
        
        # 按列名长度降序排序，避免短列名匹配到长列名的一部分
        sorted_columns = sorted(available_columns, key=len, reverse=True)
        
        # 替换列名为pl.col()
        expr_str = expression
        for col in sorted_columns:
            # 使用单词边界匹配，避免部分匹配
            pattern = r'\b' + re.escape(col) + r'\b'
            expr_str = re.sub(pattern, f'pl.col("{col}")', expr_str)
        
        # 评估表达式
        try:
            # 使用eval执行表达式（注意：生产环境需要更安全的方式）
            polars_expr = eval(expr_str, {"pl": pl})
            return polars_expr
        except Exception as e:
            raise CalculationError(f"Failed to evaluate expression '{expr_str}': {str(e)}")


# ============= 导出 =============

__all__ = [
    "CustomProcessor",
]
