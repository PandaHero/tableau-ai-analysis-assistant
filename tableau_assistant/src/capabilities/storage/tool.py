"""
Storage Tools - 存储工具

封装存储组件为 LangChain 工具。

工具列表：
- save_large_result: 大结果保存工具
"""
import json
import os
import logging
from typing import Dict, Any
from pathlib import Path
from datetime import datetime
from langchain_core.tools import tool

logger = logging.getLogger(__name__)


@tool
def save_large_result(
    data_json: str,
    task_id: str,
    format: str = "json",
    compress: bool = False,
    base_path: str = "data/large_results"
) -> Dict[str, Any]:
    """Save large query results to filesystem to avoid context overflow.
    
    This tool is used when query results are too large to fit in the LLM context.
    Instead of passing the full data, we save it to a file and return the file path.
    
    Args:
        data_json: JSON string of data to save
        task_id: Task identifier (e.g., "q1", "q2")
        format: Output format, either "json" or "csv" (default: "json")
        compress: Whether to compress the file using gzip (default: False)
        base_path: Base directory for saving files (default: "data/large_results")
    
    Returns:
        Dictionary with file_path, format, file_size_mb, row_count, etc.
    """
    import pandas as pd
    import gzip
    
    try:
        data = json.loads(data_json)
        
        if isinstance(data, dict) and "data" in data:
            df = pd.DataFrame(data["data"])
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            raise ValueError("Invalid data format")
        
        if df.empty:
            raise ValueError("Empty dataset provided")
        
        Path(base_path).mkdir(parents=True, exist_ok=True)
        
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = "json" if format == "json" else "csv"
        if compress:
            extension += ".gz"
        
        filename = f"{task_id}_{timestamp}.{extension}"
        file_path = os.path.join(base_path, filename)
        absolute_path = os.path.abspath(file_path)
        
        if format == "json":
            data_to_save = df.to_dict(orient='records')
            json_str = json.dumps(data_to_save, indent=2, ensure_ascii=False)
            
            if compress:
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    f.write(json_str)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                    
        elif format == "csv":
            if compress:
                df.to_csv(file_path, index=False, compression='gzip')
            else:
                df.to_csv(file_path, index=False)
        else:
            raise ValueError(f"Unsupported format: {format}")
        
        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
        
        result = {
            "file_path": file_path,
            "absolute_path": absolute_path,
            "format": format,
            "compressed": compress,
            "file_size_bytes": file_size_bytes,
            "file_size_mb": file_size_mb,
            "row_count": len(df),
            "column_count": len(df.columns),
            "saved_at": datetime.now().isoformat()
        }
        
        logger.info(f"✅ Large result saved: {file_path} ({file_size_mb}MB)")
        return result
    
    except Exception as e:
        logger.error(f"Failed to save large result: {e}")
        raise


__all__ = ["save_large_result"]
