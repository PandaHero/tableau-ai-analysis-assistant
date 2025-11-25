"""
主数据处理器

协调所有数据处理任务的执行
"""
from typing import Dict, Any
import polars as pl
import logging

from tableau_assistant.src.components.data_processor.factory import ProcessorFactory
from tableau_assistant.src.components.data_processor.exceptions import (
    ProcessingError,
    ValidationError,
    CalculationError,
    DependencyError
)
from tableau_assistant.src.models.query_result import QueryResult, ProcessingResult
import time

logger = logging.getLogger(__name__)


class DataProcessor:
    """
    主数据处理器
    
    负责：
    1. 协调处理任务的执行
    2. 使用 Polars 进行高效数据处理
    3. 输入输出验证
    4. 错误处理
    
    设计说明：
    - 输入：Dict[str, QueryResult] - 多个查询任务的结果
    - 输出：ProcessingResult - 单个处理任务的结果
    - 内部全程使用 Polars，避免不必要的转换
    
    数据流：
    QueryResult (q1) ─┐
    QueryResult (q2) ─┤→ DataProcessor → ProcessingResult (q3)
    QueryResult (...) ─┘
    """
    
    def __init__(self):
        """初始化数据处理器"""
        self.factory = ProcessorFactory()
        logger.info("DataProcessor initialized")
    
    def process_subtask(
        self,
        subtask: Any,  # ProcessingSubTask
        query_results: Dict[str, QueryResult]
    ) -> ProcessingResult:
        """
        处理单个ProcessingSubTask
        
        Args:
            subtask: 处理子任务（ProcessingSubTask实例）
            query_results: 查询结果字典 {task_id: QueryResult}
            
        Returns:
            处理后的数据（ProcessingResult）
            
        Raises:
            ValidationError: 输入验证失败
            CalculationError: 计算失败
            ProcessingError: 其他处理错误
        """
        start_time = time.time()
        
        try:
            logger.info(f"Processing subtask: {subtask.question_id}")
            
            # 1. 验证输入
            self._validate_input(subtask, query_results)
            
            # 2. 获取处理指令
            instruction = subtask.processing_instruction
            
            # 3. 创建对应的处理器
            processor = self.factory.create_processor(instruction.processing_type)
            
            # 4. 验证指令
            if not processor.validate_instruction(instruction):
                raise ValidationError(
                    f"Invalid processing instruction for {instruction.processing_type}"
                )
            
            # 5. 准备源数据（Polars DataFrame）
            source_data = self._prepare_source_data(instruction.source_tasks, query_results)
            
            # 6. 执行处理
            result_df = processor.process(source_data, instruction)
            
            # 7. 验证输出
            self._validate_output(result_df)
            
            # 8. 计算处理时间
            processing_time_ms = int((time.time() - start_time) * 1000)
            
            # 9. 封装为 ProcessingResult
            result = ProcessingResult(
                task_id=subtask.question_id,
                data=result_df,
                row_count=len(result_df),
                columns=list(result_df.columns),
                processing_type=instruction.processing_type,
                source_tasks=instruction.source_tasks,
                processing_time_ms=processing_time_ms,
                metadata={
                    "question_text": subtask.question_text,
                    "calculation_formula": instruction.calculation_formula
                }
            )
            
            logger.info(
                f"Processing completed: {subtask.question_id}, "
                f"output shape: {result_df.shape}, "
                f"time: {processing_time_ms}ms"
            )
            
            return result
            
        except ValidationError as e:
            logger.error(f"Validation failed for {subtask.question_id}: {e}")
            raise
        except CalculationError as e:
            logger.error(f"Calculation failed for {subtask.question_id}: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error in {subtask.question_id}: {e}", exc_info=True)
            raise ProcessingError(f"Processing failed: {e}")
    
    def _validate_input(
        self,
        subtask: Any,
        query_results: Dict[str, QueryResult]
    ) -> None:
        """
        验证输入数据
        
        检查：
        - 所有依赖任务的结果都存在
        - 数据格式正确
        - 数据不为空
        
        Args:
            subtask: 处理子任务
            query_results: 查询结果字典
            
        Raises:
            DependencyError: 依赖数据缺失
            ValidationError: 数据验证失败
        """
        instruction = subtask.processing_instruction
        
        for task_id in instruction.source_tasks:
            if task_id not in query_results:
                raise DependencyError(f"Missing source data for task {task_id}")
            
            result = query_results[task_id]
            if result.data.is_empty():
                raise ValidationError(f"Empty data from task {task_id}")
            
            logger.debug(f"Validated source data: {task_id}, shape: {result.data.shape}")
    
    def _prepare_source_data(
        self,
        source_tasks: list[str],
        query_results: Dict[str, QueryResult]
    ) -> Dict[str, pl.DataFrame]:
        """
        准备源数据（提取 Polars DataFrame）
        
        Args:
            source_tasks: 源任务ID列表
            query_results: 查询结果字典（QueryResult）
            
        Returns:
            源数据字典（Polars DataFrame）
        """
        source_data = {}
        
        for task_id in source_tasks:
            result = query_results[task_id]
            source_data[task_id] = result.data
            logger.debug(f"Prepared source data: {task_id}, shape: {result.data.shape}")
        
        return source_data
    
    def _validate_output(self, result: pl.DataFrame) -> None:
        """
        验证输出数据
        
        检查：
        - 结果不为空
        - 数值计算正确（无NaN、Inf）
        
        Args:
            result: 处理结果
            
        Raises:
            ValidationError: 输出验证失败
            CalculationError: 计算结果异常
        """
        if result.is_empty():
            raise ValidationError("Processing result is empty")
        
        # 检查数值列是否有异常值
        for col in result.columns:
            dtype = result[col].dtype
            
            # 只检查数值类型列
            if dtype in [pl.Float32, pl.Float64, pl.Int8, pl.Int16, pl.Int32, pl.Int64]:
                # 检查 NaN
                null_count = result[col].null_count()
                if null_count > 0:
                    logger.warning(f"Column {col} contains {null_count} null values")
                
                # 检查 Inf（只对浮点数）
                if dtype in [pl.Float32, pl.Float64]:
                    has_inf = result[col].is_infinite().any()
                    if has_inf:
                        raise CalculationError(f"Column {col} contains infinite values")
        
        logger.debug(f"Output validation passed: {result.shape}")


# ============= 导出 =============

__all__ = [
    "DataProcessor",
]
