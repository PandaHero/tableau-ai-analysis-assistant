"""
元数据管理器（MetadataManager）

纯代码组件，负责：
1. 获取数据源元数据（通过Tableau Metadata API）
2. 缓存元数据到Store（1小时）
3. 调用维度层级推断Agent增强元数据

注意：这是纯组件，不是Agent，使用Runtime访问Store
"""
from typing import Dict, Any, Optional
import logging
from langgraph.runtime import Runtime

from tableau_assistant.src.models.context import VizQLContext
from tableau_assistant.src.components.store_manager import StoreManager
from tableau_assistant.src.models.metadata import Metadata, FieldMetadata

logger = logging.getLogger(__name__)


async def get_datasource_metadata(
    datasource_luid: str,
    tableau_token: str,
    tableau_site: str,
    tableau_domain: str
) -> Dict[str, Any]:
    """
    从Tableau API获取数据源元数据（异步版本）
    
    使用Tableau Metadata GraphQL API获取字段信息
    
    Args:
        datasource_luid: 数据源LUID
        tableau_token: Tableau认证token
        tableau_site: Tableau站点
        tableau_domain: Tableau域名
    
    Returns:
        元数据字典
    """
    from tableau_assistant.src.utils.tableau.metadata import get_data_dictionary_async
    
    try:
        # 调用真实的Tableau Metadata API（异步版本）
        metadata = await get_data_dictionary_async(
            api_key=tableau_token,
            domain=tableau_domain,
            datasource_luid=datasource_luid,
            site=tableau_site
        )
        
        # 标准化字段格式（确保同时有name和fieldCaption）
        fields = metadata.get("fields", [])
        standardized_fields = []
        
        for field in fields:
            # 确保字段有必要的属性
            field_name = field.get("name", "")
            standardized_field = {
                "name": field_name,
                "fieldCaption": field_name,  # 使用name作为fieldCaption
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
        
        # 分类维度和度量（注意：role可能是DIMENSION或dimension）
        dimensions = [f["name"] for f in standardized_fields if f["role"].upper() == "DIMENSION"]
        measures = [f["name"] for f in standardized_fields if f["role"].upper() == "MEASURE"]
        
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
            "raw_response": metadata.get("raw_graphql_response")  # 保留原始响应用于调试
        }
    
    except Exception as e:
        logger.error(f"获取元数据失败: {e}")
        raise RuntimeError(f"无法获取数据源元数据: {datasource_luid}") from e


class MetadataManager:
    """
    元数据管理器
    
    负责获取、缓存和增强数据源元数据
    使用Runtime访问Store和Context
    """
    
    def __init__(self, runtime: Runtime[VizQLContext]):
        """
        初始化元数据管理器
        
        Args:
            runtime: LangGraph运行时（包含context和store）
        """
        self.runtime = runtime
        self.store_manager = StoreManager(runtime.store)
    
    def _convert_to_metadata_model(self, raw_metadata: Dict[str, Any]) -> Metadata:
        """
        将原始元数据字典转换为Metadata模型对象
        
        Args:
            raw_metadata: 从Tableau API获取的原始元数据字典
        
        Returns:
            Metadata模型对象
        """
        # 转换字段列表为FieldMetadata对象
        field_metadata_list = []
        for field_dict in raw_metadata.get("fields", []):
            try:
                field_metadata = FieldMetadata(**field_dict)
                field_metadata_list.append(field_metadata)
            except Exception as e:
                logger.warning(f"转换字段元数据失败: {field_dict.get('name')}, 错误: {e}")
                continue
        
        # 创建Metadata对象
        metadata = Metadata(
            datasource_luid=raw_metadata["datasource_luid"],
            datasource_name=raw_metadata["datasource_name"],
            datasource_description=raw_metadata.get("datasource_description"),
            datasource_owner=raw_metadata.get("datasource_owner"),
            fields=field_metadata_list,
            field_count=len(field_metadata_list),
            dimension_hierarchy=raw_metadata.get("dimension_hierarchy"),
            raw_response=raw_metadata.get("raw_response")
        )
        
        return metadata
    
    def get_metadata(
        self,
        use_cache: bool = True,
        enhance: bool = False
    ) -> Metadata:
        """
        获取数据源元数据（同步版本，用于 LangGraph 节点）
        
        Args:
            use_cache: 是否使用缓存
            enhance: 是否增强元数据（调用维度层级推断Agent）
        
        Returns:
            Metadata模型对象
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
                    self.get_metadata_async(use_cache=use_cache, enhance=enhance)
                )
                return future.result()
        except RuntimeError:
            # 没有运行的事件循环，直接使用 asyncio.run
            return asyncio.run(self.get_metadata_async(use_cache=use_cache, enhance=enhance))
    
    async def get_metadata_async(
        self,
        use_cache: bool = True,
        enhance: bool = True  # 默认启用自动增强
    ) -> Metadata:
        """
        获取数据源元数据（异步版本）
        
        智能增强逻辑：
        - 如果缓存中没有维度层级，自动触发推断
        - 如果维度数量变化，自动重新推断
        - 如果缓存过期（24小时），自动重新推断
        
        Args:
            use_cache: 是否使用缓存
            enhance: 是否启用智能增强（默认True）
        
        Returns:
            Metadata模型对象
        """
        # 从runtime.context获取datasource_luid
        datasource_luid = self.runtime.context.datasource_luid
        
        # 从Store获取Tableau配置
        from tableau_assistant.src.models.context import get_tableau_config
        tableau_config = get_tableau_config(self.store_manager)
        tableau_token = tableau_config["tableau_token"]
        tableau_site = tableau_config["tableau_site"]
        tableau_domain = tableau_config["tableau_domain"]
        
        # 1. 尝试从缓存获取
        if use_cache:
            cached_metadata = self.store_manager.get_metadata(datasource_luid)
            if cached_metadata:
                logger.info(f"从缓存获取元数据: {datasource_luid}")
                
                # 智能增强：检查是否需要推断维度层级
                if enhance:
                    needs_inference = self._should_infer_hierarchy(cached_metadata)
                    if needs_inference:
                        logger.info(f"检测到需要推断维度层级: {needs_inference}")
                        await self._enhance_metadata(cached_metadata)
                
                return cached_metadata
        
        # 2. 从Tableau API获取元数据（异步调用）
        logger.info(f"从Tableau API获取元数据: {datasource_luid}")
        try:
            raw_metadata = await get_datasource_metadata(
                datasource_luid=datasource_luid,
                tableau_token=tableau_token,
                tableau_site=tableau_site,
                tableau_domain=tableau_domain
            )
        except Exception as e:
            logger.error(f"获取元数据失败: {e}")
            raise
        
        # 3. 转换为Metadata模型对象
        metadata = self._convert_to_metadata_model(raw_metadata)
        
        # 4. 保存到缓存
        self.store_manager.put_metadata(datasource_luid, metadata)
        logger.info(f"元数据已缓存（1小时）: {datasource_luid}")
        
        # 5. 智能增强元数据
        if enhance:
            needs_inference = self._should_infer_hierarchy(metadata)
            if needs_inference:
                # 需要推断维度层级（会同时查询 valid_max_date）
                logger.info(f"新元数据需要推断维度层级: {needs_inference}")
                await self._enhance_metadata(metadata)
            else:
                # 维度层级缓存存在，但需要更新日期最大值
                # 因为数据可能在一天中刷新多次，需要获取最新的日期范围
                logger.info(f"维度层级缓存存在，更新日期字段最大值")
                await self._update_date_field_max_values(metadata)
        
        return metadata
    
    def _should_infer_hierarchy(self, metadata: Metadata) -> str:
        """
        判断是否需要推断维度层级
        
        检查条件：
        1. SQLite缓存中没有维度层级数据
        2. 维度数量与缓存不匹配
        3. 缓存过期（通过store的TTL机制自动处理）
        
        Args:
            metadata: Metadata对象
        
        Returns:
            需要推断的原因，如果不需要则返回空字符串
        """
        datasource_luid = self.runtime.context.datasource_luid
        
        # 1. 优先从SQLite缓存中查询维度层级
        cached_hierarchy = self.store_manager.get_dimension_hierarchy(datasource_luid)
        if not cached_hierarchy:
            return "缓存中没有维度层级"
        
        # 2. 如果缓存中有，将其加载到metadata对象中
        if not metadata.dimension_hierarchy:
            metadata.dimension_hierarchy = cached_hierarchy
            logger.info(f"从SQLite缓存加载维度层级到metadata对象")
        
        # 3. 检查维度数量是否匹配
        # 计算当前维度数量
        current_dimensions = [f for f in metadata.fields if f.role.upper() == "DIMENSION"]
        current_dim_count = len(current_dimensions)
        
        # 计算缓存中的维度数量
        # cached_hierarchy 是 Dict[str, DimensionAttributes]
        cached_dim_count = len(cached_hierarchy)
        
        if current_dim_count != cached_dim_count:
            return f"维度数量不匹配（当前:{current_dim_count}, 缓存:{cached_dim_count}）"
        
        # 不需要推断
        return ""
    
    async def _enhance_metadata(self, metadata: Metadata) -> None:
        """
        增强元数据（添加维度层级）
        
        Args:
            metadata: Metadata模型对象（会被修改）
        """
        datasource_luid = self.runtime.context.datasource_luid
        
        # 1. 检查缓存
        hierarchy = self.store_manager.get_dimension_hierarchy(datasource_luid)
        
        if hierarchy:
            logger.info(f"从缓存获取维度层级: {datasource_luid}")
            metadata.dimension_hierarchy = hierarchy
            return
        
        # 2. 调用维度层级推断Agent
        logger.info(f"调用维度层级推断Agent: {datasource_luid}")
        try:
            from tableau_assistant.src.agents.dimension_hierarchy_agent import dimension_hierarchy_agent
            
            # 创建状态（传递 Metadata 对象）
            state = {
                "metadata": metadata,
                "datasource_luid": datasource_luid,
            }
            
            # 调用Agent（传递runtime）
            # 注意：dimension_hierarchy_agent 内部会调用 _update_date_field_max_values
            # 该函数会更新缓存中的 metadata（添加 valid_max_date）
            result = await dimension_hierarchy_agent.execute(
                state=state,
                runtime=self.runtime
            )
            
            # 提取层级结果
            hierarchy = result.get("dimension_hierarchy", {})
            
            # 3. 保存到缓存
            self.store_manager.put_dimension_hierarchy(datasource_luid, hierarchy)
            logger.info(f"维度层级已缓存（24小时）: {datasource_luid}")
            
            # 4. 添加到元数据
            metadata.dimension_hierarchy = hierarchy
            
            # 5. 从缓存重新读取 metadata，因为 _update_date_field_max_values 已经更新了字段的 valid_max_date
            updated_metadata = self.store_manager.get_metadata(datasource_luid)
            if updated_metadata:
                # 将更新后的字段复制到当前 metadata 对象
                for i, field in enumerate(metadata.fields):
                    updated_field = updated_metadata.get_field(field.name)
                    if updated_field and updated_field.valid_max_date:
                        metadata.fields[i].valid_max_date = updated_field.valid_max_date
                        logger.info(f"✓ 字段 {field.name} 的 valid_max_date 已更新: {updated_field.valid_max_date}")
            
            # 6. 将维度层级推断结果添加到对应的FieldMetadata对象
            for field_name, attrs in hierarchy.items():
                field = metadata.get_field(field_name)
                if field:
                    field.category = attrs.get("category")
                    field.category_detail = attrs.get("category_detail")
                    field.level = attrs.get("level")
                    field.granularity = attrs.get("granularity")
                    field.parent_dimension = attrs.get("parent_dimension")
                    field.child_dimension = attrs.get("child_dimension")
        
        except Exception as e:
            logger.error(f"维度层级推断失败: {e}")
            # 不抛出异常，允许继续使用未增强的元数据
    
    async def _update_date_field_max_values(self, metadata: Metadata) -> None:
        """
        更新日期字段的最大值（不依赖维度层级推断）
        
        当元数据缓存过期但维度层级缓存未过期时调用。
        确保获取最新的日期数据，因为数据可能在一天中刷新多次。
        
        缓存策略：
        - 维度层级：24小时（字段层级关系不常变）
        - valid_max_date：1小时（随元数据缓存，数据可能频繁刷新）
        
        Args:
            metadata: Metadata模型对象（会被修改）
        """
        import asyncio
        from tableau_assistant.src.utils.tableau.metadata import fetch_valid_max_date_async
        from tableau_assistant.src.models.context import get_tableau_config
        
        datasource_luid = self.runtime.context.datasource_luid
        
        # 1. 从维度层级缓存中识别日期字段
        hierarchy = self.store_manager.get_dimension_hierarchy(datasource_luid)
        if not hierarchy:
            logger.info("维度层级缓存不存在，跳过日期字段更新")
            return
        
        # 识别日期字段（category包含"时间"、"日期"、"temporal"等关键词）
        date_fields = []
        for field_name, attrs in hierarchy.items():
            category = attrs.get("category", "").lower()
            if any(keyword in category for keyword in ["时间", "日期", "time", "date", "temporal"]):
                date_fields.append(field_name)
        
        if not date_fields:
            logger.info("未识别到日期字段，跳过日期值更新")
            return
        
        logger.info(f"识别到 {len(date_fields)} 个日期字段: {date_fields}")
        
        # 2. 获取第一个度量字段（用于筛选有效数据）
        measures = metadata.get_measures()
        if not measures:
            logger.warning("未找到度量字段，无法查询有效最大日期")
            return
        
        measure_field = measures[0].fieldCaption
        logger.info(f"使用度量字段: {measure_field}")
        
        # 3. 获取 Tableau 配置
        tableau_config = get_tableau_config(self.store_manager)
        tableau_token = tableau_config["tableau_token"]
        tableau_site = tableau_config["tableau_site"]
        tableau_domain = tableau_config["tableau_domain"]
        
        # 4. 异步查询每个日期字段的有效最大值
        tasks = []
        for date_field in date_fields:
            task = fetch_valid_max_date_async(
                api_key=tableau_token,
                domain=tableau_domain,
                datasource_luid=datasource_luid,
                date_field_name=date_field,
                measure_field_name=measure_field,
                site=tableau_site
            )
            tasks.append((date_field, task))
        
        # 5. 并发执行所有查询
        results = await asyncio.gather(*[task for _, task in tasks], return_exceptions=True)
        
        # 6. 更新元数据
        for (date_field, _), valid_max_date in zip(tasks, results):
            if isinstance(valid_max_date, Exception):
                logger.warning(f"查询日期字段 {date_field} 失败: {valid_max_date}")
                continue
            
            if valid_max_date:
                field_obj = metadata.get_field(date_field)
                if field_obj:
                    field_obj.valid_max_date = valid_max_date
                    logger.info(f"✓ 更新日期字段 {date_field} 的最大值: {valid_max_date}")
    
    def refresh_metadata(self) -> Metadata:
        """
        强制刷新元数据（忽略缓存）
        
        Returns:
            Metadata模型对象
        """
        return self.get_metadata(use_cache=False, enhance=False)
    
    def clear_cache(self) -> bool:
        """
        清除元数据缓存
        
        Returns:
            是否成功
        """
        datasource_luid = self.runtime.context.datasource_luid
        
        # 清除元数据缓存
        logger.info(f"清除缓存: {datasource_luid}")
        return True


# ============= 导出 =============

__all__ = [
    "MetadataManager",
]
