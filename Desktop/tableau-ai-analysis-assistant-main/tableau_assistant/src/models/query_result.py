"""
查询和处理结果数据模型

定义查询执行器和数据处理器之间的数据结构
"""
from pydantic import BaseModel, Field, ConfigDict
from typing import List, Dict, Any, Optional
import polars as pl


class QueryResult(BaseModel):
    """
    查询结果模型
    
    封装查询执行器的返回结果
    """
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True  # 允许 Polars DataFrame
    )
    
    task_id: str = Field(
        description="任务ID（如 q1, q2）"
    )
    
    data: pl.DataFrame = Field(
        description="查询数据（Polars DataFrame）"
    )
    
    row_count: int = Field(
        ge=0,
        description="行数"
    )
    
    columns: List[str] = Field(
        description="列名列表"
    )
    
    query_time_ms: Optional[int] = Field(
        default=None,
        description="查询时间（毫秒）"
    )
    
    execution_time_ms: Optional[int] = Field(
        default=None,
        description="总执行时间（毫秒）"
    )
    
    retry_count: Optional[int] = Field(
        default=0,
        description="重试次数"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="额外的元数据"
    )
    
    @classmethod
    def from_executor_result(
        cls,
        task_id: str,
        executor_result: Dict[str, Any]
    ) -> "QueryResult":
        """
        从查询执行器的结果创建 QueryResult
        
        Args:
            task_id: 任务ID
            executor_result: 查询执行器返回的字典
            
        Returns:
            QueryResult 实例
        """
        # 将数据转换为 Polars DataFrame
        data_list = executor_result.get("data", [])
        if data_list:
            df = pl.DataFrame(data_list)
        else:
            df = pl.DataFrame()
        
        return cls(
            task_id=task_id,
            data=df,
            row_count=executor_result.get("row_count", len(data_list)),
            columns=executor_result.get("columns", list(df.columns) if not df.is_empty() else []),
            query_time_ms=executor_result.get("query_time_ms"),
            execution_time_ms=executor_result.get("execution_time_ms"),
            retry_count=executor_result.get("retry_count", 0),
            metadata={}
        )
    
    def to_pandas(self):
        """
        转换为 Pandas DataFrame（用于兼容性）
        
        Returns:
            Pandas DataFrame
        """
        return self.data.to_pandas()


class ProcessingResult(BaseModel):
    """
    数据处理结果模型
    
    封装数据处理器的返回结果
    """
    model_config = ConfigDict(
        extra="forbid",
        arbitrary_types_allowed=True  # 允许 Polars DataFrame
    )
    
    task_id: str = Field(
        description="处理任务ID（如 q3, q4）"
    )
    
    data: pl.DataFrame = Field(
        description="处理后的数据（Polars DataFrame）"
    )
    
    row_count: int = Field(
        ge=0,
        description="行数"
    )
    
    columns: List[str] = Field(
        description="列名列表"
    )
    
    processing_type: str = Field(
        description="处理类型（yoy, mom, growth_rate, percentage, custom）"
    )
    
    source_tasks: List[str] = Field(
        description="源任务ID列表"
    )
    
    processing_time_ms: Optional[int] = Field(
        default=None,
        description="处理时间（毫秒）"
    )
    
    metadata: Optional[Dict[str, Any]] = Field(
        default_factory=dict,
        description="额外的元数据"
    )
    
    def to_pandas(self):
        """
        转换为 Pandas DataFrame（用于兼容性）
        
        Returns:
            Pandas DataFrame
        """
        return self.data.to_pandas()


# ============= 导出 =============

__all__ = [
    "QueryResult",
    "ProcessingResult",
]
