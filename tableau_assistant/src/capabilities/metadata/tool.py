"""
Tableau Metadata Middleware

自动注入元数据查询工具的中间件。

设计原则：
- 只负责工具注入，不管理提示词
- 提示词由现有的 Prompt 类系统管理
- 复用现有的 MetadataManager 组件
"""
from typing import Dict, Any, List
from langchain_core.tools import tool
import logging

logger = logging.getLogger(__name__)


class TableauMetadataMiddleware:
    """
    Tableau 元数据中间件
    
    职责：
    - 注入 get_metadata 工具
    - 不设置系统提示词（使用现有 Prompt 类）
    
    使用方式：
        middleware = TableauMetadataMiddleware()
        agent = create_deep_agent(
            middleware=[middleware, ...],
            ...
        )
    """
    
    def __init__(self):
        """初始化中间件"""
        self.tools = [self._create_metadata_tool()]
        logger.info("TableauMetadataMiddleware initialized")
    
    def _create_metadata_tool(self):
        """
        创建元数据查询工具
        
        Returns:
            LangChain tool 对象
        """
        @tool
        def get_tableau_metadata(
            datasource_luid: str,
            use_cache: bool = True
        ) -> Dict[str, Any]:
            """Get Tableau datasource metadata including fields, hierarchies, and max date.
            
            This tool retrieves comprehensive metadata about a Tableau datasource,
            including field definitions, dimension hierarchies, and the latest data date.
            
            Args:
                datasource_luid: The unique identifier (LUID) of the Tableau datasource.
                    Format: 32-character hexadecimal string (e.g., "a1b2c3d4-e5f6-7890-abcd-ef1234567890")
                use_cache: Whether to use cached metadata (default: True).
                    Set to False to force refresh from Tableau server.
            
            Returns:
                Dictionary containing:
                    - fields: List of field definitions with:
                        - name: Field name
                        - dataType: Data type (string, integer, datetime, etc.)
                        - role: Field role (dimension or measure)
                        - aggregation: Default aggregation (sum, avg, count, etc.)
                        - description: Field description (if available)
                    - dimension_hierarchy: Hierarchical structure of dimensions
                    - valid_max_date: Latest date in the dataset (ISO format)
                    - datasource_name: Name of the datasource
                    - connection_type: Type of data connection
            
            Examples:
                # Get metadata with cache
                >>> get_tableau_metadata(
                ...     datasource_luid="a1b2c3d4-e5f6-7890-abcd-ef1234567890"
                ... )
                {
                    "fields": [
                        {"name": "Sales", "dataType": "real", "role": "measure", ...},
                        {"name": "Region", "dataType": "string", "role": "dimension", ...}
                    ],
                    "dimension_hierarchy": {...},
                    "valid_max_date": "2024-12-31"
                }
                
                # Force refresh metadata
                >>> get_tableau_metadata(
                ...     datasource_luid="a1b2c3d4-e5f6-7890-abcd-ef1234567890",
                ...     use_cache=False
                ... )
            
            Note:
                - Metadata is cached by default for performance
                - Cache TTL is typically 1 hour
                - Use use_cache=False when datasource schema changes
            """
            from tableau_assistant.src.capabilities.metadata.manager import MetadataManager
            
            try:
                logger.info(
                    f"Fetching metadata for datasource: {datasource_luid}, "
                    f"use_cache={use_cache}"
                )
                
                manager = MetadataManager()
                metadata = manager.get_metadata(
                    datasource_luid,
                    use_cache=use_cache,
                    enhance=True
                )
                
                logger.info(
                    f"✅ Metadata retrieved: {len(metadata.get('fields', []))} fields"
                )
                
                return metadata
                
            except Exception as e:
                error_msg = f"Failed to get metadata: {str(e)}"
                logger.error(error_msg)
                raise RuntimeError(error_msg)
        
        return get_tableau_metadata
    
    def get_tools(self) -> List:
        """
        获取中间件提供的工具列表
        
        Returns:
            工具列表
        """
        return self.tools


# 导出
__all__ = ["TableauMetadataMiddleware"]
