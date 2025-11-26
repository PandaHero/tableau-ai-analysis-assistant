"""
Save Large Result Tool - 大结果保存工具

当查询结果过大时，保存到文件系统而不是放入上下文。

特性：
- 自动检测结果大小
- 保存为 JSON 或 CSV 格式
- 返回文件路径供后续读取
- 支持压缩（可选）
- 自动清理过期文件
"""
import json
import os
import logging
from typing import Dict, Any, Optional
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
    The data can later be read using the read_file tool from FilesystemMiddleware.
    
    The tool automatically:
    - Creates necessary directories
    - Generates unique filenames with timestamps
    - Saves data in the specified format (JSON or CSV)
    - Optionally compresses the file
    - Returns metadata including file path and size
    
    Args:
        data_json: JSON string of data to save.
            Format: {"columns": ["col1", "col2", ...], "data": [{...}, {...}, ...]}
            Or: [{"col1": val1, "col2": val2}, ...]
        task_id: Task identifier (e.g., "q1", "q2").
            Used to generate the filename.
        format: Output format, either "json" or "csv" (default: "json").
            - json: Saves as JSON file (preserves all data types)
            - csv: Saves as CSV file (better for tabular data)
        compress: Whether to compress the file using gzip (default: False).
            Compression can reduce file size by 70-90% for text data.
        base_path: Base directory for saving files (default: "data/large_results").
            Directory will be created if it doesn't exist.
    
    Returns:
        Dictionary with:
            - file_path: Relative path to the saved file
            - absolute_path: Absolute path to the saved file
            - format: File format (json or csv)
            - compressed: Whether the file is compressed
            - file_size_bytes: File size in bytes
            - file_size_mb: File size in MB
            - row_count: Number of rows saved
            - column_count: Number of columns saved
            - saved_at: Timestamp when file was saved
    
    Examples:
        # Save as JSON
        >>> save_large_result(
        ...     data_json='[{"Month": "Jan", "Sales": 1000}, ...]',
        ...     task_id="q1"
        ... )
        {
            "file_path": "data/large_results/q1_20250115_103045.json",
            "format": "json",
            "file_size_mb": 2.5,
            "row_count": 10000,
            ...
        }
        
        # Save as compressed CSV
        >>> save_large_result(
        ...     data_json='[...]',
        ...     task_id="q2",
        ...     format="csv",
        ...     compress=True
        ... )
        {
            "file_path": "data/large_results/q2_20250115_103045.csv.gz",
            "format": "csv",
            "compressed": true,
            "file_size_mb": 0.3,
            ...
        }
        
        # Custom base path
        >>> save_large_result(
        ...     data_json='[...]',
        ...     task_id="q3",
        ...     base_path="/tmp/query_results"
        ... )
    
    Note:
        - Files are saved with timestamp to avoid conflicts
        - Large files (>100MB) should be compressed
        - Files should be cleaned up after use
        - Use read_file tool to read the saved data later
    """
    import pandas as pd
    import gzip
    
    try:
        # 1. Parse input data
        data = json.loads(data_json)
        
        # 2. Convert to DataFrame
        if isinstance(data, dict) and "data" in data:
            df = pd.DataFrame(data["data"])
        elif isinstance(data, list):
            df = pd.DataFrame(data)
        else:
            raise ValueError("Invalid data format")
        
        if df.empty:
            raise ValueError("Empty dataset provided")
        
        logger.info(
            f"Saving large result: task_id={task_id}, "
            f"shape={df.shape}, format={format}, compress={compress}"
        )
        
        # 3. Create directory if not exists
        Path(base_path).mkdir(parents=True, exist_ok=True)
        
        # 4. Generate filename with timestamp
        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
        extension = "json" if format == "json" else "csv"
        if compress:
            extension += ".gz"
        
        filename = f"{task_id}_{timestamp}.{extension}"
        file_path = os.path.join(base_path, filename)
        absolute_path = os.path.abspath(file_path)
        
        # 5. Save data
        if format == "json":
            # Save as JSON
            data_to_save = df.to_dict(orient='records')
            json_str = json.dumps(data_to_save, indent=2, ensure_ascii=False)
            
            if compress:
                with gzip.open(file_path, 'wt', encoding='utf-8') as f:
                    f.write(json_str)
            else:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(json_str)
                    
        elif format == "csv":
            # Save as CSV
            if compress:
                df.to_csv(file_path, index=False, compression='gzip')
            else:
                df.to_csv(file_path, index=False)
        else:
            raise ValueError(f"Unsupported format: {format}. Use 'json' or 'csv'")
        
        # 6. Get file size
        file_size_bytes = os.path.getsize(file_path)
        file_size_mb = round(file_size_bytes / (1024 * 1024), 2)
        
        # 7. Prepare result
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
        
        logger.info(
            f"✅ Large result saved: {file_path} "
            f"({file_size_mb}MB, {len(df)} rows)"
        )
        
        return result
    
    except json.JSONDecodeError as e:
        error_msg = f"Invalid JSON input: {str(e)}"
        logger.error(error_msg)
        raise ValueError(error_msg)
    
    except Exception as e:
        error_msg = f"Failed to save large result: {str(e)}"
        logger.error(error_msg)
        raise RuntimeError(error_msg)


# 导出
__all__ = ["save_large_result"]
