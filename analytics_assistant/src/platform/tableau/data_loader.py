# -*- coding: utf-8 -*-
"""
Tableau 数据模型加载器

从 Tableau 数据源加载字段元数据，转换为统一的 DataModel 格式。

推荐使用 GraphQL Metadata API（load_data_model 方法），它提供完整的字段信息：
- name: 用户友好的显示名称
- role: 字段角色（DIMENSION/MEASURE）
- dataType: 数据类型
- dataCategory: 数据类别
- aggregation: 默认聚合方式
- formula: 计算字段公式
- description: 字段描述
- isHidden: 是否隐藏

使用方式：
    from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
    
    loader = TableauDataLoader()
    data_model = await loader.load_data_model(datasource_id="xxx")
"""
import asyncio
import logging
from typing import Dict, Any, List, Optional

from analytics_assistant.src.core.schemas import DataModel, Field, LogicalTable, TableRelationship
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async, TableauAuthContext
from analytics_assistant.src.platform.tableau.client import VizQLClient


# 字段样例数据类型
FieldSamples = Dict[str, Dict[str, Any]]  # {field_caption: {sample_values: [...], unique_count: int}}


logger = logging.getLogger(__name__)


class TableauDataLoader:
    """
    Tableau 数据模型加载器
    
    推荐使用 load_data_model() 方法，它只使用 GraphQL Metadata API。
    可以获取完整的字段信息，包括用户友好的显示名称和字段角色。
    """
    
    def __init__(self, client: Optional[VizQLClient] = None):
        """
        初始化数据加载器
        
        Args:
            client: VizQL 客户端（可选，默认创建新实例）
        """
        self._client = client
        self._owns_client = client is None
    
    async def _get_client(self) -> VizQLClient:
        """获取 VizQL 客户端"""
        if self._client is None:
            self._client = VizQLClient()
        return self._client
    
    async def close(self) -> None:
        """关闭客户端连接"""
        if self._owns_client and self._client is not None:
            await self._client.close()
            self._client = None
    
    async def __aenter__(self) -> "TableauDataLoader":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()
    
    async def load_data_model(
        self,
        datasource_id: Optional[str] = None,
        datasource_name: Optional[str] = None,
        auth: Optional[TableauAuthContext] = None,
    ) -> DataModel:
        """
        加载数据源的数据模型（推荐方法）
        
        只使用 GraphQL Metadata API，可以获取完整的字段信息：
        - name: 用户友好的显示名称（等于 VizQL 的 fieldCaption）
        - role: 字段角色（DIMENSION/MEASURE）
        - dataType: 数据类型
        - dataCategory: 数据类别（NOMINAL/ORDINAL/QUANTITATIVE）
        - aggregation: 默认聚合方式
        - formula: 计算字段公式
        - description: 字段描述
        - isHidden: 是否隐藏
        
        Args:
            datasource_id: 数据源 LUID（与 datasource_name 二选一）
            datasource_name: 数据源名称（与 datasource_id 二选一）
            auth: 认证上下文（可选，默认自动获取）
        
        Returns:
            DataModel 数据模型
        
        Raises:
            ValueError: 未提供 datasource_id 或 datasource_name
        """
        if not datasource_id and not datasource_name:
            raise ValueError("必须提供 datasource_id 或 datasource_name")
        
        # 获取认证
        if auth is None:
            auth = await get_tableau_auth_async()
        
        # 获取客户端
        client = await self._get_client()
        
        # 如果只提供了名称，先获取 LUID
        if not datasource_id:
            logger.info(f"根据名称查找数据源: {datasource_name}")
            datasource_id = await client.get_datasource_luid_by_name(
                datasource_name=datasource_name,
                api_key=auth.api_key,
            )
            if not datasource_id:
                raise ValueError(f"未找到数据源: {datasource_name}")
            logger.info(f"找到数据源 LUID: {datasource_id}")
        
        # 使用 GraphQL 获取完整元数据
        logger.info(f"加载数据源元数据 (GraphQL): {datasource_id}")
        
        graphql_data = await client.get_datasource_fields_metadata(
            datasource_luid=datasource_id,
            api_key=auth.api_key,
        )
        
        # 解析 GraphQL 响应
        datasources = graphql_data.get("data", {}).get("publishedDatasources", [])
        if not datasources:
            raise ValueError(f"未找到数据源: {datasource_id}")
        
        ds = datasources[0]
        raw_fields = ds.get("fields", [])
        
        logger.info(f"GraphQL 获取到 {len(raw_fields)} 个字段")
        
        # 转换为 Field 对象，并提取逻辑表信息
        fields, tables = self._convert_graphql_fields(raw_fields)
        
        # 如果是多表数据源，获取表关系
        relationships = []
        if len(tables) > 1:
            try:
                relationships = await self._load_table_relationships(
                    datasource_id=datasource_id,
                    tables=tables,
                    auth=auth,
                )
            except Exception as e:
                logger.warning(f"获取表关系失败: {e}")
        
        # 统计
        dimensions = sum(1 for f in fields if f.role == "DIMENSION")
        measures = sum(1 for f in fields if f.role == "MEASURE")
        logger.info(f"字段统计: 维度 {dimensions}, 度量 {measures}, 逻辑表 {len(tables)}, 关系 {len(relationships)}")
        
        return DataModel(
            datasource_id=datasource_id,
            datasource_name=ds.get("name"),
            datasource_description=ds.get("description"),
            datasource_owner=ds.get("owner", {}).get("name"),
            tables=tables,
            relationships=relationships,
            fields=fields,
            raw_metadata=graphql_data,
        )
    
    def _convert_graphql_fields(self, raw_fields: List[Dict[str, Any]]) -> tuple[List[Field], List[LogicalTable]]:
        """
        从 GraphQL 字段数据转换为 Field 对象，并提取逻辑表信息
        
        GraphQL 的 name 就是用户友好的显示名称，不需要额外处理。
        
        Args:
            raw_fields: GraphQL 返回的字段列表
        
        Returns:
            (Field 对象列表, LogicalTable 对象列表)
        """
        fields = []
        table_field_count: Dict[str, Dict[str, Any]] = {}  # table_id -> {name, count}
        
        for raw in raw_fields:
            # GraphQL 的 name 就是显示名（等于 VizQL 的 fieldCaption）
            name = raw.get("name", "")
            
            # 处理上游表信息
            upstream_tables = []
            for table in raw.get("upstreamTables", []) or []:
                table_id = table.get("id", "")
                table_name = table.get("name", "")
                if table_id or table_name:
                    upstream_tables.append({
                        "id": table_id,
                        "name": table_name,
                    })
                    # 统计每个表的字段数量
                    if table_id:
                        if table_id not in table_field_count:
                            table_field_count[table_id] = {"name": table_name, "count": 0}
                        table_field_count[table_id]["count"] += 1
            
            # 处理 role 为 None 的情况（如 HierarchyField、SetField 等）
            role = raw.get("role") or "DIMENSION"
            
            field = Field(
                name=name,
                caption=name,  # GraphQL 的 name 就是 caption
                data_type=raw.get("dataType") or "STRING",
                role=role,
                data_category=raw.get("dataCategory"),
                aggregation=raw.get("aggregation"),
                description=raw.get("description"),
                folder=raw.get("folderName"),
                hidden=raw.get("isHidden", False),
                calculation=raw.get("formula"),
                upstream_tables=upstream_tables,
            )
            fields.append(field)
        
        # 构建逻辑表列表
        tables = [
            LogicalTable(
                id=table_id,
                name=info["name"],
                field_count=info["count"],
            )
            for table_id, info in table_field_count.items()
        ]
        
        return fields, tables
    
    async def load_data_model_with_vizql(
        self,
        datasource_id: str,
        auth: Optional[TableauAuthContext] = None,
    ) -> DataModel:
        """
        加载数据源的数据模型（混合模式，包含 VizQL 的 fieldName）
        
        结合 VizQL read_metadata 和 GraphQL Metadata API：
        - VizQL 提供: fieldName（内部名称）, logicalTableId
        - GraphQL 提供: role, dataCategory
        
        如果需要 fieldName 和 logicalTableId，使用此方法。
        
        Args:
            datasource_id: 数据源 LUID
            auth: 认证上下文（可选，默认自动获取）
        
        Returns:
            DataModel 数据模型
        """
        # 获取认证
        if auth is None:
            auth = await get_tableau_auth_async()
        
        # 获取客户端
        client = await self._get_client()
        
        # 读取 VizQL 元数据
        logger.info(f"加载数据源元数据 (VizQL + GraphQL): {datasource_id}")
        metadata = await client.read_metadata(
            datasource_luid=datasource_id,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        # 获取 GraphQL 字段元数据（包含 role 等信息）
        graphql_fields_map: Dict[str, Dict[str, Any]] = {}
        try:
            graphql_data = await client.get_datasource_fields_metadata(
                datasource_luid=datasource_id,
                api_key=auth.api_key,
            )
            # 构建字段名到元数据的映射
            # GraphQL 的 name 等于 VizQL 的 fieldCaption
            datasources = graphql_data.get("data", {}).get("publishedDatasources", [])
            if datasources:
                for field in datasources[0].get("fields", []):
                    field_name = field.get("name", "")
                    if field_name:
                        graphql_fields_map[field_name] = field
            logger.info(f"GraphQL 获取到 {len(graphql_fields_map)} 个字段元数据")
        except Exception as e:
            logger.warning(f"GraphQL 元数据获取失败，使用 VizQL 数据: {e}")
        
        # 转换为 DataModel，合并 GraphQL 信息
        fields = self._convert_vizql_fields(metadata.get("data", []), graphql_fields_map)
        
        return DataModel(
            datasource_id=datasource_id,
            fields=fields,
            raw_metadata=metadata,
        )
    
    def _convert_vizql_fields(
        self,
        raw_fields: List[Dict[str, Any]],
        graphql_fields_map: Optional[Dict[str, Dict[str, Any]]] = None,
    ) -> List[Field]:
        """
        从 VizQL 字段数据转换为 Field 对象，合并 GraphQL 信息
        
        Args:
            raw_fields: VizQL 原始字段列表
            graphql_fields_map: GraphQL 字段名到元数据的映射（可选）
        
        Returns:
            Field 对象列表
        """
        fields = []
        graphql_fields_map = graphql_fields_map or {}
        matched_count = 0
        
        for raw in raw_fields:
            field_name = raw.get("fieldName", "")
            field_caption = raw.get("fieldCaption", "")
            
            # 从 GraphQL 获取补充信息
            # GraphQL 的 name 等于 VizQL 的 fieldCaption
            graphql_info = graphql_fields_map.get(field_caption) or {}
            if graphql_info:
                matched_count += 1
            
            # 字段角色：优先使用 GraphQL 的 role
            role = graphql_info.get("role", "DIMENSION")
            
            field = Field(
                name=field_name,  # VizQL 的内部名称
                caption=field_caption or field_name,  # 显示名称
                data_type=raw.get("dataType", "STRING"),
                role=role,
                data_category=graphql_info.get("dataCategory"),
                aggregation=graphql_info.get("aggregation") or raw.get("defaultAggregation"),
                description=graphql_info.get("description") or raw.get("description"),
                folder=graphql_info.get("folderName") or raw.get("folder"),
                hidden=graphql_info.get("isHidden", raw.get("isHidden", False)),
                calculation=graphql_info.get("formula") or raw.get("calculation"),
            )
            fields.append(field)
        
        # 统计
        dimensions = sum(1 for f in fields if f.role == "DIMENSION")
        measures = sum(1 for f in fields if f.role == "MEASURE")
        logger.debug(f"转换为 {len(fields)} 个字段（维度: {dimensions}, 度量: {measures}），GraphQL 匹配: {matched_count}")
        
        return fields
    
    async def load_raw_metadata(
        self,
        datasource_id: str,
        auth: Optional[TableauAuthContext] = None,
    ) -> Dict[str, Any]:
        """
        加载 VizQL 原始元数据（不转换）
        
        Args:
            datasource_id: 数据源 LUID
            auth: 认证上下文（可选）
        
        Returns:
            原始元数据字典
        """
        if auth is None:
            auth = await get_tableau_auth_async()
        
        client = await self._get_client()
        return await client.read_metadata(
            datasource_luid=datasource_id,
            api_key=auth.api_key,
            site=auth.site,
        )
    
    async def load_datasource_model(
        self,
        datasource_id: str,
        auth: Optional[TableauAuthContext] = None,
    ) -> Dict[str, Any]:
        """
        加载数据源模型（逻辑表和关系）
        
        Args:
            datasource_id: 数据源 LUID
            auth: 认证上下文（可选）
        
        Returns:
            数据源模型字典
        """
        if auth is None:
            auth = await get_tableau_auth_async()
        
        client = await self._get_client()
        return await client.get_datasource_model(
            datasource_luid=datasource_id,
            api_key=auth.api_key,
            site=auth.site,
        )
    
    async def _load_table_relationships(
        self,
        datasource_id: str,
        tables: List[LogicalTable],
        auth: TableauAuthContext,
    ) -> List[TableRelationship]:
        """
        加载表关系信息
        
        通过 VizQL get-datasource-model 接口获取逻辑表之间的关系。
        
        Args:
            datasource_id: 数据源 LUID
            tables: 逻辑表列表（用于 ID 到名称的映射）
            auth: 认证上下文
        
        Returns:
            TableRelationship 列表
        """
        client = await self._get_client()
        
        # 调用 VizQL 获取数据源模型
        model = await client.get_datasource_model(
            datasource_luid=datasource_id,
            api_key=auth.api_key,
            site=auth.site,
        )
        
        # 构建表 ID 到名称的映射
        # VizQL 返回的 logicalTableId 格式: TableName_HEXID
        # 需要从 logicalTables 中获取 caption 作为表名
        table_id_to_name: Dict[str, str] = {}
        for lt in model.get("logicalTables", []):
            table_id = lt.get("logicalTableId", "")
            caption = lt.get("caption", "")
            if table_id and caption:
                table_id_to_name[table_id] = caption
        
        # 解析关系
        relationships = []
        for rel in model.get("logicalTableRelationships", []):
            from_table_id = rel.get("fromLogicalTable", {}).get("logicalTableId", "")
            to_table_id = rel.get("toLogicalTable", {}).get("logicalTableId", "")
            
            if not from_table_id or not to_table_id:
                continue
            
            # 解析关联条件
            join_conditions = []
            expression = rel.get("expression", {})
            for cond in expression.get("relationships", []):
                join_conditions.append({
                    "operator": cond.get("operator", "="),
                    "from_field": cond.get("fromField", ""),
                    "to_field": cond.get("toField", ""),
                })
            
            relationship = TableRelationship(
                from_table_id=from_table_id,
                from_table_name=table_id_to_name.get(from_table_id),
                to_table_id=to_table_id,
                to_table_name=table_id_to_name.get(to_table_id),
                join_conditions=join_conditions,
            )
            relationships.append(relationship)
        
        logger.info(f"加载了 {len(relationships)} 个表关系")
        return relationships
    
    # ══════════════════════════════════════════════════════════════════════════
    # 字段样例数据查询
    # ══════════════════════════════════════════════════════════════════════════
    
    async def fetch_field_samples(
        self,
        datasource_id: str,
        fields: List[Field],
        measure_field: str,
        auth: Optional[TableauAuthContext] = None,
        top_n: int = 20,
        sample_size: int = 5,
    ) -> Dict[str, Dict[str, Any]]:
        """
        获取字段样例数据（一次查询所有字段）
        
        一次查询所有维度字段，用 TOP N 过滤，然后在内存中统计每个字段的唯一值。
        
        Args:
            datasource_id: 数据源 LUID
            fields: 要查询的字段列表（只处理维度）
            measure_field: 用于 TOP 排序的度量字段名
            auth: 认证上下文（可选）
            top_n: TOP 过滤的行数（默认 100）
            sample_size: 每个字段保留的样例数量（默认 10）
        
        Returns:
            {field_caption: {sample_values: [...], unique_count: int}}
        """
        if auth is None:
            auth = await get_tableau_auth_async()
        
        client = await self._get_client()
        
        # 只查询维度字段
        dimension_fields = [f for f in fields if f.is_dimension and not f.hidden]
        if not dimension_fields:
            logger.warning("没有可查询的维度字段")
            return {}
        
        logger.info(f"一次查询{len(dimension_fields)} 个维度字段的样例数据 (TOP {top_n})")
        
        # 构建查询：所有维度字段
        field_captions = [f.caption or f.name for f in dimension_fields]
        query_fields = [{"fieldCaption": fc} for fc in field_captions]
        
        # 用第一个维度字段做 TOP 过滤
        first_dim = field_captions[0]
        query = {
            "fields": query_fields,
            "filters": [{
                "filterType": "TOP",
                "field": {"fieldCaption": first_dim},
                "fieldToMeasure": {
                    "fieldCaption": measure_field,
                    "function": "SUM"
                },
                "howMany": top_n,
                "direction": "TOP"
            }]
        }
        
        try:
            data = await client.query_datasource(
                datasource_luid=datasource_id,
                query=query,
                api_key=auth.api_key,
                site=auth.site,
            )
        except Exception as e:
            logger.error(f"查询字段样例失败: {e}")
            return {}
        
        rows = data.get("data", [])
        logger.info(f"查询返回 {len(rows)} 行数据")
        
        # 在内存中统计每个字段的唯一值
        results: Dict[str, Dict[str, Any]] = {}
        for fc in field_captions:
            unique_values: Dict[str, int] = {}  # value -> count
            
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value = row.get(fc)
                if value is not None:
                    value_str = str(value).strip()
                    if value_str:
                        unique_values[value_str] = unique_values.get(value_str, 0) + 1
            
            # 按出现次数排序，取前 sample_size 个
            sorted_values = sorted(unique_values.keys(), key=lambda v: -unique_values[v])
            results[fc] = {
                "sample_values": sorted_values[:sample_size],
                "unique_count": len(unique_values),
            }
        
        success_count = sum(1 for r in results.values() if r["sample_values"])
        logger.info(f"字段样例统计完成: {success_count}/{len(field_captions)} 有样例值")
        
        return results


# ══════════════════════════════════════════════════════════════════════════════
# 导出
# ══════════════════════════════════════════════════════════════════════════════

__all__ = ["TableauDataLoader"]
