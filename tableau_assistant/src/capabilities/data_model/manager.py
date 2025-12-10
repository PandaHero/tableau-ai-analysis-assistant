"""
数据模型管理器（DataModelManager）

纯代码组件，负责：
1. 获取数据源数据模型（通过 Tableau Metadata API 和 VizQL API）
2. 缓存数据模型到 Store（1小时）
3. 调用维度层级推断 Agent 增强数据模型
4. 检测 STRING 类型日期字段的格式

数据模型包含：
- 字段元数据（FieldMetadata）
- 逻辑表（LogicalTable）
- 表关系（LogicalTableRelationship）
- 维度层级（DimensionHierarchy）

注意：这是纯组件，不是 Agent，使用 Runtime 访问 Store
"""
from typing import Dict, Any, Optional, TYPE_CHECKING
import logging
from langgraph.runtime import Runtime

from tableau_assistant.src.models.workflow.context import VizQLContext
from tableau_assistant.src.capabilities.storage.store_manager import StoreManager
from tableau_assistant.src.models.metadata import (
    Metadata,
    FieldMetadata,
    DataModel,
    LogicalTable,
    LogicalTableRelationship,
)

if TYPE_CHECKING:
    from tableau_assistant.src.capabilities.date_processing.manager import DateManager
    from tableau_assistant.src.capabilities.date_processing.format_detector import DateFormatType

logger = logging.getLogger(__name__)


async def get_datasource_metadata(
    datasource_luid: str,
    tableau_token: str,
    tableau_site: str,
    tableau_domain: str
) -> Dict[str, Any]:
    """
    从 Tableau API 获取数据源元数据（异步版本）
    
    使用 Tableau Metadata GraphQL API 获取字段信息
    
    Args:
        datasource_luid: 数据源 LUID
        tableau_token: Tableau 认证 token
        tableau_site: Tableau 站点
        tableau_domain: Tableau 域名
    
    Returns:
        元数据字典
    """
    from tableau_assistant.src.bi_platforms.tableau.metadata import get_data_dictionary_async
    
    try:
        # 调用真实的 Tableau Metadata API（异步版本）
        metadata = await get_data_dictionary_async(
            api_key=tableau_token,
            domain=tableau_domain,
            datasource_luid=datasource_luid,
            site=tableau_site
        )
        
        # 标准化字段格式（确保同时有 name 和 fieldCaption）
        fields = metadata.get("fields", [])
        standardized_fields = []
        
        for field in fields:
            # 确保字段有必要的属性
            field_name = field.get("name", "")
            standardized_field = {
                "name": field_name,
                "fieldCaption": field_name,  # 使用 name 作为 fieldCaption
                "role": field.get("role", "dimension").lower(),  # 统一为小写
                "dataType": field.get("dataType", "STRING"),
                "dataCategory": field.get("dataCategory"),
                "aggregation": field.get("aggregation"),
            }
            
            # 添加可选字段
            if "formula" in field:
                standardized_field["formula"] = field["formula"]
            if "description" in field:
                standardized_field["description"] = field["description"]
            if "sample_values" in field:
                standardized_field["sample_values"] = field["sample_values"]
            if "unique_count" in field:
                standardized_field["unique_count"] = field["unique_count"]
            
            standardized_fields.append(standardized_field)
        
        # 分类维度和度量（注意：role 可能是 DIMENSION 或 dimension）
        dimensions = [f["name"] for f in standardized_fields if f["role"].upper() == "DIMENSION"]
        measures = [f["name"] for f in standardized_fields if f["role"].upper() == "MEASURE"]
        
        # 解析数据模型（如果存在）
        data_model_dict = metadata.get("data_model")
        data_model = None
        if data_model_dict:
            try:
                logical_tables = [
                    LogicalTable(
                        logicalTableId=t.get("logicalTableId", ""),
                        caption=t.get("caption", "")
                    )
                    for t in data_model_dict.get("logicalTables", [])
                ]
                relationships = [
                    LogicalTableRelationship(
                        fromLogicalTableId=r.get("fromLogicalTable", {}).get("logicalTableId", ""),
                        toLogicalTableId=r.get("toLogicalTable", {}).get("logicalTableId", "")
                    )
                    for r in data_model_dict.get("logicalTableRelationships", [])
                ]
                data_model = DataModel(
                    logicalTables=logical_tables,
                    logicalTableRelationships=relationships
                )
                logger.info(f"解析数据模型: {len(logical_tables)} 个逻辑表, {len(relationships)} 个关系")
            except Exception as e:
                logger.warning(f"解析数据模型失败: {e}")
        
        return {
            "datasource_luid": datasource_luid,
            "datasource_name": metadata.get("datasource_name", "Unknown"),
            "datasource_description": metadata.get("datasource_description"),
            "datasource_owner": metadata.get("datasource_owner"),
            "fields": standardized_fields,
            "field_count": len(standardized_fields),
            "field_names": [f["name"] for f in standardized_fields],
            "dimensions": dimensions,
            "measures": measures,
            "data_model": data_model,  # 数据模型
            "raw_response": metadata.get("raw_graphql_response")  # 保留原始响应用于调试
        }
    
    except Exception as e:
        logger.error(f"获取数据模型失败: {e}")
        raise RuntimeError(f"无法获取数据源数据模型: {datasource_luid}") from e


class DataModelManager:
    """
    数据模型管理器
    
    负责获取、缓存和增强数据源数据模型。
    数据模型包含字段元数据、逻辑表、表关系和维度层级。
    
    使用 Runtime 访问 Store 和 Context。
    """
    
    def __init__(
        self,
        runtime: Runtime[VizQLContext],
        date_manager: Optional['DateManager'] = None
    ):
        """
        初始化数据模型管理器
        
        Args:
            runtime: LangGraph 运行时（包含 context 和 store）
            date_manager: 日期管理器（可选，用于检测 STRING 类型日期字段格式）
        """
        self.runtime = runtime
        # 如果 runtime.store 已经是 StoreManager 实例，直接使用
        # 否则创建新的 StoreManager
        if isinstance(runtime.store, StoreManager):
            self.store_manager = runtime.store
        else:
            self.store_manager = StoreManager(runtime.store)
        self.date_manager = date_manager
    
    def _convert_to_metadata_model(self, raw_metadata: Dict[str, Any]) -> Metadata:
        """
        将原始元数据字典转换为 Metadata 模型对象
        
        Args:
            raw_metadata: 从 Tableau API 获取的原始元数据字典
        
        Returns:
            Metadata 模型对象
        """
        # 转换字段列表为 FieldMetadata 对象
        field_metadata_list = []
        for field_dict in raw_metadata.get("fields", []):
            try:
                field_metadata = FieldMetadata(**field_dict)
                field_metadata_list.append(field_metadata)
            except Exception as e:
                logger.warning(f"转换字段元数据失败: {field_dict.get('name')}, 错误: {e}")
                continue
        
        # 创建 Metadata 对象
        metadata = Metadata(
            datasource_luid=raw_metadata["datasource_luid"],
            datasource_name=raw_metadata["datasource_name"],
            datasource_description=raw_metadata.get("datasource_description"),
            datasource_owner=raw_metadata.get("datasource_owner"),
            fields=field_metadata_list,
            field_count=len(field_metadata_list),
            dimension_hierarchy=raw_metadata.get("dimension_hierarchy"),
            data_model=raw_metadata.get("data_model"),  # 数据模型
            raw_response=raw_metadata.get("raw_response")
        )
        
        return metadata
    
    # ============= 数据模型获取方法 =============
    
    def get_data_model(
        self,
        use_cache: bool = True,
        enhance: bool = False
    ) -> Metadata:
        """
        获取数据源数据模型（同步版本，用于 LangGraph 节点）
        
        Args:
            use_cache: 是否使用缓存
            enhance: 是否增强数据模型（调用维度层级推断 Agent）
        
        Returns:
            Metadata 模型对象（包含字段元数据、逻辑表、关系等）
        """
        import asyncio
        
        # 检查是否已经在事件循环中
        try:
            loop = asyncio.get_running_loop()
            # 如果已经在事件循环中，使用 run_in_executor
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.get_data_model_async(use_cache=use_cache, enhance=enhance)
                )
                return future.result()
        except RuntimeError:
            # 没有运行的事件循环，直接使用 asyncio.run
            return asyncio.run(self.get_data_model_async(use_cache=use_cache, enhance=enhance))
    
    async def get_data_model_async(
        self,
        use_cache: bool = True,
        enhance: bool = True  # 默认启用自动增强
    ) -> Metadata:
        """
        获取数据源数据模型（异步版本）
        
        智能增强逻辑：
        - 如果缓存中没有维度层级，自动触发推断
        - 如果维度数量变化，自动重新推断
        - 如果缓存过期（24小时），自动重新推断
        
        Args:
            use_cache: 是否使用缓存
            enhance: 是否启用智能增强（默认 True）
        
        Returns:
            Metadata 模型对象（包含字段元数据、逻辑表、关系等）
        """
        # 从 runtime.context 获取 datasource_luid
        datasource_luid = self.runtime.context.datasource_luid
        
        # 从 Store 获取 Tableau 配置
        from tableau_assistant.src.models.workflow.context import get_tableau_config
        tableau_config = get_tableau_config(self.store_manager)
        tableau_token = tableau_config["tableau_token"]
        tableau_site = tableau_config["tableau_site"]
        tableau_domain = tableau_config["tableau_domain"]
        
        # 1. 尝试从缓存获取
        if use_cache:
            cached_metadata = self.store_manager.get_metadata(datasource_luid)
            if cached_metadata:
                logger.info(f"从缓存获取数据模型: {datasource_luid}")
                
                # 检测 STRING 类型日期字段格式（如果 DateManager 缓存为空）
                if self.date_manager and not self.date_manager.field_formats_cache:
                    await self._detect_date_field_formats(cached_metadata)
                
                # 智能增强：检查是否需要推断维度层级
                if enhance:
                    needs_inference = self._should_infer_hierarchy(cached_metadata)
                    if needs_inference:
                        logger.info(f"检测到需要推断维度层级: {needs_inference}")
                        await self._enhance_data_model(cached_metadata)
                
                return cached_metadata
        
        # 2. 从 Tableau API 获取数据模型（异步调用）
        logger.info(f"从 Tableau API 获取数据模型: {datasource_luid}")
        try:
            raw_metadata = await get_datasource_metadata(
                datasource_luid=datasource_luid,
                tableau_token=tableau_token,
                tableau_site=tableau_site,
                tableau_domain=tableau_domain
            )
        except Exception as e:
            logger.error(f"获取数据模型失败: {e}")
            raise
        
        # 3. 转换为 Metadata 模型对象
        metadata = self._convert_to_metadata_model(raw_metadata)
        
        # 4. 保存到缓存
        self.store_manager.put_metadata(datasource_luid, metadata)
        logger.info(f"数据模型已缓存（1小时）: {datasource_luid}")
        
        # 5. 检测 STRING 类型日期字段格式
        await self._detect_date_field_formats(metadata)
        
        # 6. 智能增强数据模型
        if enhance:
            needs_inference = self._should_infer_hierarchy(metadata)
            if needs_inference:
                # 需要推断维度层级（会同时查询 valid_max_date）
                logger.info(f"新数据模型需要推断维度层级: {needs_inference}")
                await self._enhance_data_model(metadata)
            # 维度层级缓存存在，无需额外操作
        
        return metadata
    
    # ============= 内部方法 =============
    
    def _should_infer_hierarchy(self, metadata: Metadata) -> str:
        """
        判断是否需要推断维度层级
        
        检查条件：
        1. SQLite 缓存中没有维度层级数据
        2. 维度数量与缓存不匹配
        3. 缓存过期（通过 store 的 TTL 机制自动处理）
        
        Args:
            metadata: Metadata 对象
        
        Returns:
            需要推断的原因，如果不需要则返回空字符串
        """
        datasource_luid = self.runtime.context.datasource_luid
        
        # 1. 优先从 SQLite 缓存中查询维度层级
        cached_hierarchy = self.store_manager.get_dimension_hierarchy(datasource_luid)
        if not cached_hierarchy:
            return "缓存中没有维度层级"
        
        # 2. 如果缓存中有，将其加载到 metadata 对象中
        # 过滤掉 _cached_at 等元数据字段
        filtered_hierarchy = {
            k: v for k, v in cached_hierarchy.items() 
            if not k.startswith("_")
        }
        
        if not metadata.dimension_hierarchy:
            metadata.dimension_hierarchy = filtered_hierarchy
            logger.info(f"从 SQLite 缓存加载维度层级到 metadata 对象")
        
        # 3. 将维度层级信息注入到各个 FieldMetadata 对象
        self._inject_hierarchy_to_fields(metadata, filtered_hierarchy)
        
        # 4. 检查维度数量是否匹配
        # 计算当前维度数量
        current_dimensions = [f for f in metadata.fields if f.role.upper() == "DIMENSION"]
        current_dim_count = len(current_dimensions)
        
        # 计算缓存中的维度数量（排除 _cached_at 等元数据字段）
        cached_dim_count = len(filtered_hierarchy)
        
        if current_dim_count != cached_dim_count:
            return f"维度数量不匹配（当前:{current_dim_count}, 缓存:{cached_dim_count}）"
        
        # 不需要推断
        return ""
    
    def _inject_hierarchy_to_fields(
        self, 
        metadata: Metadata, 
        hierarchy_dict: Dict[str, Any]
    ) -> None:
        """
        将维度层级信息注入到各个 FieldMetadata 对象
        
        这样 FieldIndexer 在构建索引时可以使用 category 等信息。
        
        Args:
            metadata: Metadata 对象
            hierarchy_dict: 维度层级字典
        """
        injected_count = 0
        for field_name, attrs in hierarchy_dict.items():
            field = metadata.get_field(field_name)
            if field and isinstance(attrs, dict):
                field.category = attrs.get('category')
                field.category_detail = attrs.get('category_detail')
                field.level = attrs.get('level')
                field.granularity = attrs.get('granularity')
                field.parent_dimension = attrs.get('parent_dimension')
                field.child_dimension = attrs.get('child_dimension')
                injected_count += 1
        
        if injected_count > 0:
            logger.debug(f"已将维度层级信息注入到 {injected_count} 个字段")
    
    async def _enhance_data_model(self, metadata: Metadata) -> None:
        """
        增强数据模型（添加维度层级）
        
        Args:
            metadata: Metadata 模型对象（会被修改）
        """
        datasource_luid = self.runtime.context.datasource_luid
        
        # 1. 检查缓存
        hierarchy = self.store_manager.get_dimension_hierarchy(datasource_luid)
        
        if hierarchy:
            logger.info(f"从缓存获取维度层级: {datasource_luid}")
            metadata.dimension_hierarchy = hierarchy
            return
        
        # 2. 调用维度层级推断 Agent（函数式）
        logger.info(f"调用维度层级推断 Agent: {datasource_luid}")
        try:
            from tableau_assistant.src.agents.dimension_hierarchy.node import (
                dimension_hierarchy_node,
            )

            # 调用函数式 Agent，返回 DimensionHierarchyResult 模型
            result = await dimension_hierarchy_node(
                metadata=metadata, datasource_luid=datasource_luid
            )

            # 转换为字典格式（用于缓存和存储）
            hierarchy_dict = {}
            for field_name, attrs in result.dimension_hierarchy.items():
                hierarchy_dict[field_name] = attrs.model_dump()

            # 3. 保存到缓存
            self.store_manager.put_dimension_hierarchy(datasource_luid, hierarchy_dict)
            logger.info(f"维度层级已缓存（24小时）: {datasource_luid}")

            # 4. 添加到数据模型
            metadata.dimension_hierarchy = hierarchy_dict

            # 5. 将维度层级推断结果添加到对应的 FieldMetadata 对象
            for field_name, attrs in result.dimension_hierarchy.items():
                field = metadata.get_field(field_name)
                if field:
                    field.category = attrs.category
                    field.category_detail = attrs.category_detail
                    field.level = attrs.level
                    field.granularity = attrs.granularity
                    field.parent_dimension = attrs.parent_dimension
                    field.child_dimension = attrs.child_dimension

        except Exception as e:
            logger.error(f"维度层级推断失败: {e}")
            # 不抛出异常，允许继续使用未增强的数据模型
    
    async def _detect_date_field_formats(self, metadata: Metadata) -> None:
        """
        检测 STRING 类型日期字段的格式
        
        遍历所有 STRING 类型字段，使用 DateManager 检测其日期格式。
        如果检测成功，将格式信息缓存到 DateManager 中。
        
        Args:
            metadata: Metadata 模型对象（会被修改）
        """
        if not self.date_manager:
            logger.debug("DateManager 未注入，跳过日期格式检测")
            return
        
        # 获取所有 STRING 类型字段
        string_fields = [
            field for field in metadata.fields
            if field.dataType == "STRING" and field.sample_values
        ]
        
        if not string_fields:
            logger.debug("未找到 STRING 类型字段，跳过日期格式检测")
            return
        
        logger.info(f"开始检测 {len(string_fields)} 个 STRING 字段的日期格式")
        
        # 检测每个字段的日期格式
        for field in string_fields:
            try:
                # 使用 DateManager 检测格式
                format_type = self.date_manager.detect_field_date_format(
                    sample_values=field.sample_values,
                    confidence_threshold=0.7
                )
                
                if format_type:
                    # 缓存格式信息到 DateManager
                    self.date_manager.field_formats_cache[field.name] = format_type
                    
                    # 获取格式信息
                    format_info = self.date_manager.get_format_info(format_type)
                    
                    logger.info(
                        f"✓ 检测到日期字段: {field.name}, "
                        f"格式: {format_info['name']}, "
                        f"示例: {format_info['example']}"
                    )
                else:
                    logger.debug(f"字段 {field.name} 不是日期格式")
                    
            except Exception as e:
                logger.warning(f"检测字段 {field.name} 格式失败: {e}")
                continue
    
    def get_field_date_format(self, field_name: str) -> Optional['DateFormatType']:
        """
        获取字段的日期格式（从 DateManager 缓存读取）
        
        Args:
            field_name: 字段名称
        
        Returns:
            日期格式类型，如果未检测到则返回 None
        """
        if not self.date_manager:
            logger.debug("DateManager 未注入，无法获取日期格式")
            return None
        
        return self.date_manager.field_formats_cache.get(field_name)
    
    def refresh_data_model(self) -> Metadata:
        """
        强制刷新数据模型（忽略缓存）
        
        Returns:
            Metadata 模型对象
        """
        return self.get_data_model(use_cache=False, enhance=False)
    
    def clear_cache(self) -> bool:
        """
        清除数据模型缓存
        
        Returns:
            是否成功
        """
        datasource_luid = self.runtime.context.datasource_luid
        
        # 清除数据模型缓存
        logger.info(f"清除缓存: {datasource_luid}")
        return True
    
    async def get_logical_tables_async(
        self,
        datasource_luid: Optional[str] = None,
        use_cache: bool = True
    ) -> Optional[DataModel]:
        """
        获取数据源逻辑表和关系（异步版本）
        
        数据模型包含逻辑表和表之间的关系，来自 VizQL /get-datasource-model API。
        
        缓存策略：
        - 使用 SQLite 缓存数据模型
        - 默认 24 小时 TTL
        - 支持强制刷新
        
        Args:
            datasource_luid: 数据源 LUID（可选，默认从 context 获取）
            use_cache: 是否使用缓存（默认 True）
        
        Returns:
            DataModel 对象，如果获取失败返回 None
        """
        # 获取 datasource_luid
        if datasource_luid is None:
            datasource_luid = self.runtime.context.datasource_luid
        
        # 1. 尝试从缓存获取
        if use_cache:
            cached_model = self.store_manager.get_data_model(datasource_luid)
            if cached_model:
                logger.info(f"从缓存获取逻辑表: {datasource_luid}")
                return cached_model
        
        # 2. 从 VizQL API 获取数据模型
        logger.info(f"从 VizQL API 获取逻辑表: {datasource_luid}")
        try:
            from tableau_assistant.src.bi_platforms.tableau.metadata_service import TableauMetadataService
            from tableau_assistant.src.models.workflow.context import get_tableau_config
            
            # 获取 Tableau 配置
            tableau_config = get_tableau_config(self.store_manager)
            
            # 创建元数据服务
            service = TableauMetadataService(
                domain=tableau_config["tableau_domain"],
                site=tableau_config["tableau_site"]
            )
            
            # 获取数据模型
            data_model = service.get_data_model(
                datasource_luid=datasource_luid,
                api_key=tableau_config["tableau_token"]
            )
            
            if data_model:
                # 3. 保存到缓存
                self.store_manager.put_data_model(datasource_luid, data_model)
                
                logger.info(
                    f"逻辑表已获取并缓存: {datasource_luid}, "
                    f"逻辑表数: {len(data_model.logicalTables)}, "
                    f"关系数: {len(data_model.logicalTableRelationships)}"
                )
            
            return data_model
            
        except Exception as e:
            logger.warning(f"获取逻辑表失败，启用优雅降级: {e}")
            logger.info(
                f"优雅降级: 数据模型 API 不可用，将继续使用字段元数据。"
                f"功能影响: 无法获取逻辑表名称和表关系信息。"
            )
            # 优雅降级：返回 None，允许继续使用字段元数据
            # 调用方应检查返回值并相应处理
            return None
    
    async def get_full_data_model_async(
        self,
        use_cache: bool = True,
        enhance: bool = True
    ) -> Metadata:
        """
        获取完整数据模型（包含逻辑表和关系）
        
        这是一个便捷方法，会：
        1. 获取字段元数据
        2. 尝试获取逻辑表和关系
        3. 如果数据模型可用，将 logicalTableCaption 映射到字段
        4. 如果数据模型不可用，优雅降级继续使用字段元数据
        
        Args:
            use_cache: 是否使用缓存
            enhance: 是否增强数据模型
        
        Returns:
            Metadata 对象（可能包含或不包含逻辑表信息）
        """
        # 1. 获取字段元数据
        metadata = await self.get_data_model_async(use_cache=use_cache, enhance=enhance)
        
        # 2. 尝试获取逻辑表和关系
        data_model = await self.get_logical_tables_async(use_cache=use_cache)
        
        if data_model:
            # 3. 将数据模型关联到元数据
            metadata.data_model = data_model
            
            # 4. 映射 logicalTableCaption 到字段
            for field in metadata.fields:
                if field.logicalTableId:
                    table_caption = data_model.get_table_caption(field.logicalTableId)
                    if table_caption:
                        field.logicalTableCaption = table_caption
            
            logger.info(
                f"数据模型已关联: "
                f"{len(data_model.logicalTables)} 个逻辑表, "
                f"{len(data_model.logicalTableRelationships)} 个关系"
            )
        else:
            # 5. 优雅降级：记录日志但继续
            logger.info(
                f"逻辑表不可用，继续使用字段元数据。"
                f"字段的 logicalTableCaption 将为空。"
            )
        
        return metadata
    
    def get_logical_tables(
        self,
        datasource_luid: Optional[str] = None,
        use_cache: bool = True
    ) -> Optional[DataModel]:
        """
        获取数据源逻辑表和关系（同步版本）
        
        Args:
            datasource_luid: 数据源 LUID（可选，默认从 context 获取）
            use_cache: 是否使用缓存（默认 True）
        
        Returns:
            DataModel 对象，如果获取失败返回 None
        """
        import asyncio
        
        try:
            loop = asyncio.get_running_loop()
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as executor:
                future = executor.submit(
                    asyncio.run,
                    self.get_logical_tables_async(datasource_luid, use_cache)
                )
                return future.result()
        except RuntimeError:
            return asyncio.run(self.get_logical_tables_async(datasource_luid, use_cache))


# ============= 导出 =============

__all__ = [
    "DataModelManager",
]
