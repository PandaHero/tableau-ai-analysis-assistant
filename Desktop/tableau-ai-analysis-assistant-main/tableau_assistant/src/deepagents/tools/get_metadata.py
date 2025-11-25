"""get_metadata 工具

封装 MetadataManager 组件，提供数据源元数据查询功能。

特性：
- 使用 Store 缓存元数据（TTL: 1小时）
- 自动重试机制（处理网络错误）
- 支持强制刷新
"""
import logging
from typing import Dict, Any
from langchain_core.tools import tool
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception_type

logger = logging.getLogger(__name__)


# 定义需要重试的异常类型
RETRIABLE_EXCEPTIONS = (
    ConnectionError,
    TimeoutError,
    RuntimeError,  # MetadataManager 抛出的异常
)


@retry(
    stop=stop_after_attempt(3),
    wait=wait_exponential(multiplier=1, min=2, max=10),
    retry=retry_if_exception_type(RETRIABLE_EXCEPTIONS),
    reraise=True
)
async def _fetch_metadata_with_retry(
    metadata_manager,
    use_cache: bool,
    enhance: bool
) -> Dict[str, Any]:
    """
    带重试机制的元数据获取函数
    
    Args:
        metadata_manager: MetadataManager 实例
        use_cache: 是否使用缓存
        enhance: 是否增强元数据
    
    Returns:
        元数据字典
    
    Raises:
        ConnectionError: 网络连接错误
        TimeoutError: 请求超时
        RuntimeError: 其他运行时错误
    """
    try:
        # 调用 MetadataManager 获取元数据
        metadata = await metadata_manager.get_metadata_async(
            use_cache=use_cache,
            enhance=enhance
        )
        
        # 转换为字典格式
        return metadata.model_dump()
    
    except Exception as e:
        logger.error(f"获取元数据失败: {e}")
        raise


@tool
async def get_metadata(
    use_cache: bool = True,
    enhance: bool = True,
    force_refresh: bool = False
) -> Dict[str, Any]:
    """Get datasource metadata including fields, dimensions, measures, and hierarchy.
    
    This tool retrieves comprehensive metadata about the Tableau datasource:
    - Field names, types, and roles (dimension/measure)
    - Dimension hierarchy and relationships
    - Date field information with valid ranges
    - Field descriptions and sample values
    
    The metadata is cached for 1 hour to improve performance. Use force_refresh=True
    to bypass cache and get the latest metadata.
    
    Args:
        use_cache: Whether to use cached metadata (default: True).
                  Set to False to always fetch fresh data.
        enhance: Whether to enhance metadata with dimension hierarchy (default: True).
                Hierarchy inference is cached for 24 hours.
        force_refresh: Force refresh metadata, ignoring cache (default: False).
                      Equivalent to use_cache=False.
    
    Returns:
        Dictionary containing:
        - datasource_luid: Datasource unique identifier
        - datasource_name: Datasource name
        - fields: List of field metadata (name, type, role, etc.)
        - dimensions: List of dimension field names
        - measures: List of measure field names
        - dimension_hierarchy: Dimension relationships and hierarchy
        - field_count: Total number of fields
    
    Examples:
        # Get cached metadata with hierarchy
        metadata = await get_metadata()
        
        # Force refresh metadata
        metadata = await get_metadata(force_refresh=True)
        
        # Get metadata without hierarchy enhancement
        metadata = await get_metadata(enhance=False)
    
    Note:
        - Metadata is cached for 1 hour
        - Dimension hierarchy is cached for 24 hours
        - Automatically retries up to 3 times on network errors
        - Date field max values are updated with each metadata refresh
    """
    from langgraph.runtime import get_runtime
    from tableau_assistant.src.components.metadata_manager import MetadataManager
    
    # 获取当前 runtime
    runtime = get_runtime()
    
    # 创建 MetadataManager
    metadata_manager = MetadataManager(runtime)
    
    # 处理 force_refresh 参数
    if force_refresh:
        use_cache = False
    
    try:
        # 使用重试机制获取元数据
        metadata_dict = await _fetch_metadata_with_retry(
            metadata_manager=metadata_manager,
            use_cache=use_cache,
            enhance=enhance
        )
        
        logger.info(
            f"✅ 成功获取元数据: {metadata_dict.get('datasource_name')} "
            f"({metadata_dict.get('field_count')} 个字段)"
        )
        
        return metadata_dict
    
    except Exception as e:
        logger.error(f"❌ 获取元数据失败（重试3次后）: {e}")
        raise RuntimeError(f"无法获取数据源元数据: {e}") from e


# 导出
__all__ = ["get_metadata"]
