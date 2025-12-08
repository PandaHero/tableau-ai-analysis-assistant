"""
Tool Registry - 工具注册表

管理业务工具的注册和获取。

注意：
- 中间件提供的工具（如 write_todos, read_file）由中间件自动注入，不在此注册
- FieldMapper 是独立节点（RAG + LLM 混合），不是工具

工具分组：
- understanding: 语义理解工具（get_data_model, get_schema_module, parse_date, detect_date_format）
- insight: 洞察分析工具（暂无）
- replanner: 重规划工具（由 TodoListMiddleware 注入 write_todos）
"""
from typing import Dict, List, Optional, Callable, Any, Type
from dataclasses import dataclass, field
import logging
from enum import Enum

from langchain_core.tools import BaseTool

logger = logging.getLogger(__name__)


class NodeType(str, Enum):
    """节点类型枚举"""
    UNDERSTANDING = "understanding"
    INSIGHT = "insight"
    REPLANNER = "replanner"


@dataclass
class ToolMetadata:
    """工具元数据"""
    name: str
    description: str
    node_type: NodeType
    tool: BaseTool
    dependencies: List[str] = field(default_factory=list)
    tags: List[str] = field(default_factory=list)


class ToolRegistry:
    """
    工具注册表
    
    管理业务工具的注册、获取和依赖注入。
    
    特性：
    - 按节点分组工具
    - 支持依赖注入
    - 支持动态更新
    - 自动发现工具
    
    使用示例：
        >>> registry = ToolRegistry()
        >>> registry.auto_discover()
        >>> tools = registry.get_tools(NodeType.UNDERSTANDING)
    """
    
    _instance: Optional['ToolRegistry'] = None
    
    def __new__(cls) -> 'ToolRegistry':
        """单例模式"""
        if cls._instance is None:
            cls._instance = super().__new__(cls)
            cls._instance._initialized = False
        return cls._instance
    
    def __init__(self):
        """初始化工具注册表"""
        if self._initialized:
            return
        
        self._tools: Dict[NodeType, List[ToolMetadata]] = {
            NodeType.UNDERSTANDING: [],
            NodeType.INSIGHT: [],
            NodeType.REPLANNER: [],
        }
        self._tool_map: Dict[str, ToolMetadata] = {}
        self._dependencies: Dict[str, Any] = {}
        self._initialized = True
        
        logger.info("ToolRegistry initialized")
    
    def register(
        self,
        node_type: NodeType,
        tool: BaseTool,
        dependencies: Optional[List[str]] = None,
        tags: Optional[List[str]] = None
    ) -> None:
        """
        注册工具到指定节点
        
        Args:
            node_type: 节点类型
            tool: LangChain 工具实例
            dependencies: 依赖列表（如 ["data_model_manager", "date_manager"]）
            tags: 标签列表（用于过滤）
        
        Raises:
            ValueError: 如果工具已注册
        """
        tool_name = tool.name
        
        if tool_name in self._tool_map:
            logger.warning(f"Tool '{tool_name}' already registered, skipping")
            return
        
        metadata = ToolMetadata(
            name=tool_name,
            description=tool.description or "",
            node_type=node_type,
            tool=tool,
            dependencies=dependencies or [],
            tags=tags or []
        )
        
        self._tools[node_type].append(metadata)
        self._tool_map[tool_name] = metadata
        
        logger.info(f"Registered tool '{tool_name}' for node '{node_type.value}'")
    
    def unregister(self, tool_name: str) -> bool:
        """
        注销工具
        
        Args:
            tool_name: 工具名称
        
        Returns:
            是否成功注销
        """
        if tool_name not in self._tool_map:
            logger.warning(f"Tool '{tool_name}' not found")
            return False
        
        metadata = self._tool_map.pop(tool_name)
        self._tools[metadata.node_type].remove(metadata)
        
        logger.info(f"Unregistered tool '{tool_name}'")
        return True
    
    def get_tools(
        self,
        node_type: NodeType,
        tags: Optional[List[str]] = None
    ) -> List[BaseTool]:
        """
        获取节点的工具列表
        
        Args:
            node_type: 节点类型
            tags: 过滤标签（可选）
        
        Returns:
            工具列表
        """
        tools_metadata = self._tools.get(node_type, [])
        
        if tags:
            tools_metadata = [
                m for m in tools_metadata
                if any(tag in m.tags for tag in tags)
            ]
        
        return [m.tool for m in tools_metadata]
    
    def get_tool(self, tool_name: str) -> Optional[BaseTool]:
        """
        获取指定工具
        
        Args:
            tool_name: 工具名称
        
        Returns:
            工具实例，如果不存在返回 None
        """
        metadata = self._tool_map.get(tool_name)
        return metadata.tool if metadata else None
    
    def get_tool_metadata(self, tool_name: str) -> Optional[ToolMetadata]:
        """
        获取工具元数据
        
        Args:
            tool_name: 工具名称
        
        Returns:
            工具元数据，如果不存在返回 None
        """
        return self._tool_map.get(tool_name)
    
    def list_tools(self, node_type: Optional[NodeType] = None) -> List[str]:
        """
        列出工具名称
        
        Args:
            node_type: 节点类型（可选，不指定则返回所有）
        
        Returns:
            工具名称列表
        """
        if node_type:
            return [m.name for m in self._tools.get(node_type, [])]
        return list(self._tool_map.keys())
    
    def set_dependency(self, name: str, instance: Any) -> None:
        """
        设置依赖实例
        
        Args:
            name: 依赖名称
            instance: 依赖实例
        """
        self._dependencies[name] = instance
        logger.debug(f"Set dependency '{name}'")
    
    def get_dependency(self, name: str) -> Optional[Any]:
        """
        获取依赖实例
        
        Args:
            name: 依赖名称
        
        Returns:
            依赖实例，如果不存在返回 None
        """
        return self._dependencies.get(name)
    
    def auto_discover(self) -> int:
        """
        自动发现并注册业务工具
        
        Returns:
            注册的工具数量
        """
        count = 0
        
        # 延迟导入，避免循环依赖
        try:
            from tableau_assistant.src.tools.data_model_tool import get_data_model
            self.register(
                NodeType.UNDERSTANDING,
                get_data_model,
                dependencies=["data_model_manager"],
                tags=["data_model", "metadata", "boost"]
            )
            count += 1
        except ImportError as e:
            logger.warning(f"Failed to import get_data_model: {e}")
        
        try:
            from tableau_assistant.src.tools.schema_tool import get_schema_module
            self.register(
                NodeType.UNDERSTANDING,
                get_schema_module,
                tags=["schema", "token_optimization"]
            )
            count += 1
        except ImportError as e:
            logger.warning(f"Failed to import get_schema_module: {e}")
        
        try:
            from tableau_assistant.src.tools.date_tool import parse_date, detect_date_format
            self.register(
                NodeType.UNDERSTANDING,
                parse_date,
                dependencies=["date_manager"],
                tags=["date", "parsing"]
            )
            self.register(
                NodeType.UNDERSTANDING,
                detect_date_format,
                dependencies=["date_manager"],
                tags=["date", "detection"]
            )
            count += 2
        except ImportError as e:
            logger.warning(f"Failed to import date tools: {e}")
        
        logger.info(f"Auto-discovered {count} tools")
        return count
    
    def clear(self) -> None:
        """清空所有注册的工具"""
        for node_type in self._tools:
            self._tools[node_type].clear()
        self._tool_map.clear()
        self._dependencies.clear()
        logger.info("ToolRegistry cleared")
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取注册表统计信息
        
        Returns:
            统计信息字典
        """
        return {
            "total_tools": len(self._tool_map),
            "tools_by_node": {
                node_type.value: len(tools)
                for node_type, tools in self._tools.items()
            },
            "dependencies": list(self._dependencies.keys()),
            "tool_names": list(self._tool_map.keys())
        }


# 全局注册表实例
_registry: Optional[ToolRegistry] = None


def get_registry() -> ToolRegistry:
    """获取全局工具注册表实例"""
    global _registry
    if _registry is None:
        _registry = ToolRegistry()
    return _registry


def get_tools_for_node(node_type: NodeType, tags: Optional[List[str]] = None) -> List[BaseTool]:
    """
    便捷函数：获取节点的工具列表
    
    Args:
        node_type: 节点类型
        tags: 过滤标签（可选）
    
    Returns:
        工具列表
    """
    return get_registry().get_tools(node_type, tags)


def register_tool(
    node_type: NodeType,
    tool: BaseTool,
    dependencies: Optional[List[str]] = None,
    tags: Optional[List[str]] = None
) -> None:
    """
    便捷函数：注册工具
    
    Args:
        node_type: 节点类型
        tool: LangChain 工具实例
        dependencies: 依赖列表
        tags: 标签列表
    """
    get_registry().register(node_type, tool, dependencies, tags)


__all__ = [
    "ToolRegistry",
    "ToolMetadata",
    "NodeType",
    "get_registry",
    "get_tools_for_node",
    "register_tool",
]
