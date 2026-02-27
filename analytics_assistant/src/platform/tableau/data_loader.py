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
from typing import Any, Optional

from analytics_assistant.src.core.schemas import DataModel, Field, LogicalTable, TableRelationship
from analytics_assistant.src.core.exceptions import VizQLServerError, VizQLError
from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async, TableauAuthContext
from analytics_assistant.src.platform.tableau.client import VizQLClient
from analytics_assistant.src.agents.field_semantic import (
    infer_field_semantic,
    build_enhanced_index_text,
)
from analytics_assistant.src.infra.rag import get_rag_service, IndexConfig, IndexDocument, IndexBackend
from analytics_assistant.src.infra.config import get_config

# 字段样例数据类型
FieldSamples = dict[str, dict[str, Any]]  # {field_caption: {sample_values: [...], unique_count: int}}

# 字段索引名称前缀
FIELD_INDEX_PREFIX = "fields_"

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
        skip_index_creation: bool = False,
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
        # 注意：GraphQL 的 upstreamTables 只对 ColumnField 有效
        # CalculatedField 没有 upstreamTables 是正确的（计算字段不属于任何原始表）
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
        
        data_model = DataModel(
            datasource_id=datasource_id,
            datasource_name=ds.get("name"),
            datasource_description=ds.get("description"),
            datasource_owner=ds.get("owner", {}).get("name"),
            tables=tables,
            relationships=relationships,
            fields=fields,
            raw_metadata=graphql_data,
        )
        
        # 创建字段索引（等待完成，确保后续 FieldRetriever 能使用 RAG 检索）
        if not skip_index_creation:
            await self._ensure_field_index_async(datasource_id, data_model)
            logger.info("字段索引创建完成")
        
        return data_model
    
    async def _ensure_field_index_async(
        self,
        datasource_id: str,
        data_model: DataModel,
    ) -> None:
        """
        异步创建字段索引（后台执行，不阻塞主流程）
        
        Args:
            datasource_id: 数据源 LUID
            data_model: 数据模型
        """
        try:
            await self._ensure_field_index(datasource_id, data_model)
        except Exception as e:
            logger.warning(f"后台创建字段索引失败: {e}")
    
    async def _ensure_field_index(
        self,
        datasource_id: str,
        data_model: DataModel,
    ) -> None:
        """
        确保字段索引存在（使用字段语义推断结果）
        
        流程：
        1. 检查索引是否已存在
        2. 获取字段样例数据（sample_values）
        3. 调用 FieldSemanticInference 进行推断（传入样例值提升准确性）
        4. 使用推断结果创建字段索引（包含语义属性和样例值）
        
        索引文本格式：
        {caption}: {business_description}。别名: {aliases}。类型: {role}, {data_type}
        
        Args:
            datasource_id: 数据源 LUID
            data_model: 数据模型
        """
        index_name = f"{FIELD_INDEX_PREFIX}{datasource_id}"
        
        try:
            rag_service = get_rag_service()
            
            # 检查索引是否已存在
            existing_index = rag_service.index.get_index(index_name)
            if existing_index is not None:
                logger.debug(f"字段索引已存在: {index_name}")
                # 从索引 metadata 恢复 queryable 标志到 DataModel
                self._restore_queryable_flags(rag_service, index_name, data_model)
                return
            
            logger.info(f"创建字段索引: {index_name}")
            
            # 先获取字段样例数据，再进行语义推断（样例值能显著提升推断准确性）
            field_samples: FieldSamples = {}
            unqueryable_captions: set[str] = set()
            try:
                measure_field = next(
                    (f.caption or f.name for f in data_model.fields
                     if f.role and f.role.upper() == "MEASURE" and not f.hidden),
                    None,
                )
                if measure_field:
                    field_samples, unqueryable_captions = await self.fetch_field_samples(
                        datasource_id=datasource_id,
                        fields=data_model.fields,
                        measure_field=measure_field,
                    )
                    logger.info(f"字段样例获取完成: {len(field_samples)} 个字段有样例")
                else:
                    logger.warning("无可用度量字段，跳过字段样例获取")
            except Exception as e:
                logger.warning(f"获取字段样例失败，语义推断将不使用样例值: {e}")
            
            # 调用字段语义推断（传入样例值提升准确性）
            logger.info(f"开始语义推断，字段数: {len(data_model.fields)}")
            semantic_result = await infer_field_semantic(
                datasource_luid=datasource_id,
                fields=data_model.fields,
                field_samples=field_samples,
            )
            logger.info("语义推断完成")
            logger.debug(f"语义结果字段数: {len(semantic_result.field_semantic)}")
            
            # 将推断结果缓存到 DataModel 扩展属性，供后续复用
            try:
                data_model._field_semantic_cache = semantic_result.field_semantic
            except AttributeError:
                pass  # DataModel 不支持动态属性，忽略
            
            # 构建 IndexDocument 列表
            documents = []
            semantic_hit_count = 0
            for field in data_model.fields:
                field_caption = field.caption or field.name
                role_str = field.role.lower() if field.role else "dimension"
                data_type_str = field.data_type.lower() if field.data_type else "string"
                
                # 获取字段语义信息
                semantic_attrs = semantic_result.field_semantic.get(field_caption)
                
                # 构建增强索引文本
                if semantic_attrs:
                    semantic_hit_count += 1
                    # 获取该字段的样例值
                    field_sample_values = None
                    if field_caption in field_samples:
                        field_sample_values = field_samples[field_caption].get("sample_values")
                    
                    # 提取语义类别
                    sem_category = None
                    sem_measure_category = None
                    if semantic_attrs.role == "dimension" and semantic_attrs.category:
                        sem_category = semantic_attrs.category.value
                    elif semantic_attrs.role == "measure" and semantic_attrs.measure_category:
                        sem_measure_category = semantic_attrs.measure_category.value
                    
                    index_text = build_enhanced_index_text(
                        caption=field_caption,
                        business_description=semantic_attrs.business_description,
                        aliases=semantic_attrs.aliases,
                        role=role_str,
                        data_type=data_type_str,
                        category=sem_category,
                        measure_category=sem_measure_category,
                        sample_values=field_sample_values,
                    )
                else:
                    # 无语义信息时使用基本格式
                    index_text = f"{field_caption}: {field.description or field_caption}。类型: {role_str}, {data_type_str}"
                
                # 构建元数据
                metadata = {
                    "field_caption": field_caption,
                    "field_name": field.name,
                    "role": role_str,
                    "data_type": data_type_str,
                    "description": field.description or "",
                    "formula": field.calculation or "",
                }
                
                # 添加语义信息
                if semantic_attrs:
                    metadata["business_description"] = semantic_attrs.business_description
                    metadata["aliases"] = semantic_attrs.aliases
                    metadata["confidence"] = semantic_attrs.confidence
                    
                    # 维度特定属性
                    if semantic_attrs.role == "dimension":
                        metadata["category"] = semantic_attrs.category.value if semantic_attrs.category else ""
                        metadata["category_detail"] = semantic_attrs.category_detail or ""
                        metadata["level"] = semantic_attrs.level
                        metadata["granularity"] = semantic_attrs.granularity or ""
                    # 度量特定属性
                    elif semantic_attrs.role == "measure":
                        metadata["measure_category"] = semantic_attrs.measure_category.value if semantic_attrs.measure_category else ""
                
                # 添加逻辑表信息
                if field.upstream_tables:
                    table_names = [t.get("name", "") for t in field.upstream_tables if t.get("name")]
                    if table_names:
                        metadata["logical_table_caption"] = table_names[0]
                
                doc = IndexDocument(
                    id=field.name,
                    content=index_text,
                    metadata=metadata,
                )
                documents.append(doc)
            
            logger.info(f"语义信息命中: {semantic_hit_count}/{len(data_model.fields)}")
            
            # 标记不可查询的幽灵字段（在 DataModel 和索引 metadata 中同步标记）
            if unqueryable_captions:
                for field in data_model.fields:
                    field_caption = field.caption or field.name
                    if field_caption in unqueryable_captions:
                        field.queryable = False
                logger.info(
                    f"已标记 {len(unqueryable_captions)} 个幽灵字段为不可查询: "
                    f"{sorted(unqueryable_captions)}"
                )
            
            # 将 sample_values 和 queryable 标志写入对应字段的 metadata
            for doc in documents:
                field_caption = doc.metadata.get("field_caption", "")
                # 标记不可查询字段
                if field_caption in unqueryable_captions:
                    doc.metadata["queryable"] = False
                else:
                    doc.metadata["queryable"] = True
                # 写入样例值
                if field_caption in field_samples:
                    sample_info = field_samples[field_caption]
                    sample_values = sample_info.get("sample_values", [])
                    if sample_values:
                        doc.metadata["sample_values"] = sample_values
            
            # 获取索引配置
            app_config = get_config()
            vector_cfg = app_config.config.get("vector_storage", {})
            index_dir = vector_cfg.get("index_dir", "data/indexes")
            retrieval_cfg = vector_cfg.get("retrieval", {})
            
            # 创建索引配置
            config = IndexConfig(
                backend=IndexBackend.FAISS,
                persist_directory=index_dir,
                default_top_k=retrieval_cfg.get("default_top_k", 10),
                score_threshold=retrieval_cfg.get("score_threshold", 0.5),
            )
            
            # 创建索引
            rag_service.index.create_index(
                name=index_name,
                config=config,
                documents=documents,
            )
            
            logger.info(f"字段索引创建完成: {index_name}, {len(documents)} 个字段")
            
        except Exception as e:
            # 索引创建失败不应阻塞数据模型加载
            logger.warning(f"创建字段索引失败: {e}")
    
    def _restore_queryable_flags(
        self,
        rag_service: Any,
        index_name: str,
        data_model: DataModel,
    ) -> None:
        """从已有索引的 metadata 恢复 queryable 标志到 DataModel。
        
        当索引已存在时，幽灵字段信息已经记录在索引 metadata 中。
        需要将这些信息同步回 DataModel，确保 FieldRetriever 能正确过滤。
        
        Args:
            rag_service: RAG 服务实例
            index_name: 索引名称
            data_model: 数据模型
        """
        try:
            index_fields = rag_service.index.get_index_fields(index_name)
            if not index_fields:
                return
            
            # 收集不可查询的字段标题
            unqueryable_captions: set[str] = set()
            for field_info in index_fields:
                if not isinstance(field_info, dict):
                    continue
                if field_info.get("queryable") is False:
                    caption = field_info.get("field_caption", "")
                    if caption:
                        unqueryable_captions.add(caption)
            
            if not unqueryable_captions:
                return
            
            # 在 DataModel 中标记对应字段
            for field in data_model.fields:
                field_caption = field.caption or field.name
                if field_caption in unqueryable_captions:
                    field.queryable = False
            
            logger.info(
                f"从索引恢复 {len(unqueryable_captions)} 个幽灵字段的 queryable=False 标志: "
                f"{sorted(unqueryable_captions)}"
            )
        except Exception as e:
            logger.debug(f"恢复 queryable 标志失败（索引可能不含此信息）: {e}")
    
    def _convert_graphql_fields(
        self,
        raw_fields: list[dict[str, Any]],
    ) -> tuple[list[Field], list[LogicalTable]]:
        """
        从 GraphQL 字段数据转换为 Field 对象，并提取逻辑表信息
        
        GraphQL 的 name 就是用户友好的显示名称，不需要额外处理。
        
        逻辑表信息来自 GraphQL 的 upstreamTables：
        - ColumnField 有 upstreamTables（来自数据库表的列）
        - CalculatedField 没有 upstreamTables（在 Tableau 中定义的计算字段，不属于任何原始表）
        
        Args:
            raw_fields: GraphQL 返回的字段列表
        
        Returns:
            (Field 对象列表, LogicalTable 对象列表)
        """
        fields = []
        table_field_count: dict[str, dict[str, Any]] = {}  # table_id -> {name, count}
        
        for raw in raw_fields:
            # GraphQL 的 name 就是显示名（等于 VizQL 的 fieldCaption）
            name = raw.get("name", "")
            
            # 处理上游表信息（来自 GraphQL 的 upstreamTables）
            # 只有 ColumnField 有 upstreamTables，CalculatedField 没有（这是正确的）
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
        graphql_fields_map: dict[str, dict[str, Any]] = {}
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
        raw_fields: list[dict[str, Any]],
        graphql_fields_map: Optional[dict[str, dict[str, Any]]] = None,
    ) -> list[Field]:
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
    ) -> dict[str, Any]:
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
    ) -> Optional[dict[str, Any]]:
        """
        加载数据源模型（逻辑表和关系）
        
        注意：此方法依赖 get-datasource-model API，该 API 是 VizQL Data Service 2025.3 (2025年10月) 新增的功能。
        如果 Tableau Server 版本低于 2025.3，此方法会返回 None（优雅降级）。
        
        对于低版本 Tableau Server，建议使用 load_data_model() 方法，它会自动从
        GraphQL upstreamTables 或 VizQL logicalTableId 获取逻辑表信息。
        
        参考：https://help.tableau.com/current/api/vizql-data-service/en-us/docs/vds_whats_new.html
        
        Args:
            datasource_id: 数据源 LUID
            auth: 认证上下文（可选）
        
        Returns:
            数据源模型字典，如果 API 不可用则返回 None
        """
        if auth is None:
            auth = await get_tableau_auth_async()
        
        client = await self._get_client()
        
        try:
            return await client.get_datasource_model(
                datasource_luid=datasource_id,
                api_key=auth.api_key,
                site=auth.site,
            )
        except VizQLServerError as e:
            # get-datasource-model API 需要 VizQL Data Service 2025.3+
            # 低版本 Tableau Server 会返回 500 错误，优雅降级返回 None
            logger.warning(
                f"get-datasource-model API 不可用（需要 VizQL Data Service 2025.3+）: {e}。"
                f"建议使用 load_data_model() 方法获取逻辑表信息。"
            )
            return None
        except VizQLError as e:
            # 其他 VizQL 错误也优雅降级
            logger.warning(f"获取数据源模型失败: {e}")
            return None
    
    async def _load_table_relationships(
        self,
        datasource_id: str,
        tables: list[LogicalTable],
        auth: TableauAuthContext,
    ) -> list[TableRelationship]:
        """
        加载表关系信息
        
        通过 VizQL get-datasource-model 接口获取逻辑表之间的关系。
        
        注意：get-datasource-model API 是 VizQL Data Service 2025.3 (2025年10月) 新增的功能。
        如果 Tableau Server 版本低于 2025.3，此方法会返回空列表（优雅降级）。
        
        对于低版本 Tableau Server，表关系信息无法获取，但逻辑表信息仍然可以从
        GraphQL upstreamTables 或 VizQL logicalTableId 获取。
        
        Args:
            datasource_id: 数据源 LUID
            tables: 逻辑表列表（用于 ID 到名称的映射）
            auth: 认证上下文
        
        Returns:
            TableRelationship 列表，如果 API 不可用则返回空列表
        """
        client = await self._get_client()
        
        # 调用 VizQL 获取数据源模型
        try:
            model = await client.get_datasource_model(
                datasource_luid=datasource_id,
                api_key=auth.api_key,
                site=auth.site,
            )
        except VizQLServerError as e:
            # get-datasource-model API 需要 VizQL Data Service 2025.3+
            # 低版本 Tableau Server 会返回 500 错误，优雅降级返回空列表
            logger.warning(
                f"get-datasource-model API 不可用（需要 VizQL Data Service 2025.3+），"
                f"跳过表关系加载。逻辑表信息仍可从 GraphQL/VizQL 获取: {e}"
            )
            return []
        except VizQLError as e:
            # 其他 VizQL 错误也优雅降级
            logger.warning(f"获取数据源模型失败，跳过表关系加载: {e}")
            return []
        
        # 构建表 ID 到名称的映射
        # VizQL 返回的 logicalTableId 格式: TableName_HEXID
        # 需要从 logicalTables 中获取 caption 作为表名
        table_id_to_name: dict[str, str] = {}
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
        fields: list[Field],
        measure_field: str,
        auth: Optional[TableauAuthContext] = None,
        top_n: int = 20,
        sample_size: int = 5,
    ) -> tuple[dict[str, dict[str, Any]], set[str]]:
        """
        获取字段样例数据（一次查询所有字段）
        
        一次查询所有维度字段，用 TOP N 过滤，然后在内存中统计每个字段的唯一值。
        同时跟踪 VizQL 查询失败的"幽灵字段"。
        
        Args:
            datasource_id: 数据源 LUID
            fields: 要查询的字段列表（只处理维度）
            measure_field: 用于 TOP 排序的度量字段名
            auth: 认证上下文（可选）
            top_n: TOP 过滤的行数（默认 100）
            sample_size: 每个字段保留的样例数量（默认 10）
        
        Returns:
            (results, unqueryable_captions) 元组：
            - results: {field_caption: {sample_values: [...], unique_count: int}}
            - unqueryable_captions: VizQL 查询失败的字段标题集合
        """
        if auth is None:
            auth = await get_tableau_auth_async()
        
        client = await self._get_client()
        
        # 查询所有维度字段（包括计算字段，排除隐藏字段和 TABLE 类型）
        # 计算字段（如 门店名称、分类二级编码）大多可查询，个别不可查询的会在批次失败时逐个重试
        dimension_fields = [
            f for f in fields
            if f.is_dimension and not f.hidden
            and (f.data_type or "").upper() not in ("TABLE",)
        ]
        if not dimension_fields:
            logger.warning("没有可查询的维度字段")
            return {}, set()
        
        # 分批查询，每批最多 batch_size 个字段，避免 VizQL 超时
        _DEFAULT_BATCH_SIZE = 5
        try:
            config = get_config()
            platform_config = config.get("platform", {}).get("tableau", {}).get("data_loader", {})
            batch_size = platform_config.get("batch_size", _DEFAULT_BATCH_SIZE)
        except Exception:
            batch_size = _DEFAULT_BATCH_SIZE
        field_captions = [f.caption or f.name for f in dimension_fields]
        all_results: dict[str, dict[str, Any]] = {}
        all_unqueryable: set[str] = set()
        
        for batch_start in range(0, len(field_captions), batch_size):
            batch_captions = field_captions[batch_start:batch_start + batch_size]
            logger.info(
                f"查询字段样例批次 {batch_start // batch_size + 1}: "
                f"{len(batch_captions)} 个维度字段 (TOP {top_n})"
            )
            
            batch_results, batch_unqueryable = await self._query_field_samples_batch(
                client=client,
                datasource_id=datasource_id,
                batch_captions=batch_captions,
                measure_field=measure_field,
                auth=auth,
                top_n=top_n,
                sample_size=sample_size,
            )
            all_results.update(batch_results)
            all_unqueryable.update(batch_unqueryable)
        
        success_count = sum(1 for r in all_results.values() if r.get("sample_values"))
        logger.info(f"字段样例统计完成: {success_count}/{len(field_captions)} 有样例值")
        if all_unqueryable:
            logger.warning(
                f"发现 {len(all_unqueryable)} 个幽灵字段（GraphQL 存在但 VizQL 不可查询）: "
                f"{sorted(all_unqueryable)}"
            )
        
        return all_results, all_unqueryable
    
    async def _query_field_samples_batch(
        self,
        client: VizQLClient,
        datasource_id: str,
        batch_captions: list[str],
        measure_field: str,
        auth: TableauAuthContext,
        top_n: int,
        sample_size: int,
    ) -> tuple[dict[str, dict[str, Any]], list[str]]:
        """查询一批字段的样例数据。
        
        如果批次查询失败（可能包含不可查询的计算字段），
        自动降级为逐个字段查询，跳过有问题的字段。
        
        Args:
            client: VizQL 客户端
            datasource_id: 数据源 LUID
            batch_captions: 字段标题列表
            measure_field: 用于 TOP 排序的度量字段名
            auth: 认证上下文
            top_n: TOP 过滤的行数
            sample_size: 每个字段保留的样例数量
        
        Returns:
            (results, unqueryable_captions) 元组：
            - results: {field_caption: {sample_values: [...], unique_count: int}}
            - unqueryable_captions: VizQL 查询失败的字段标题列表
        """
        results: dict[str, dict[str, Any]] = {}
        unqueryable: list[str] = []
        
        # 先尝试批量查询
        query_fields = [{"fieldCaption": fc} for fc in batch_captions]
        first_dim = batch_captions[0]
        query = {
            "fields": query_fields,
            "filters": [{
                "filterType": "TOP",
                "field": {"fieldCaption": first_dim},
                "fieldToMeasure": {
                    "fieldCaption": measure_field,
                    "function": "SUM",
                },
                "howMany": top_n,
                "direction": "TOP",
            }],
        }
        
        try:
            data = await client.query_datasource(
                datasource_luid=datasource_id,
                query=query,
                api_key=auth.api_key,
                site=auth.site,
            )
            rows = data.get("data", [])
            results = self._parse_sample_rows(rows, batch_captions, sample_size)
            return results, unqueryable
        except Exception as e:
            logger.warning(
                f"批次查询失败（{len(batch_captions)} 个字段），降级为逐个查询: {e}"
            )
        
        # 批量失败 → 逐个字段查询，跳过有问题的字段
        for fc in batch_captions:
            single_query = {
                "fields": [{"fieldCaption": fc}],
                "filters": [{
                    "filterType": "TOP",
                    "field": {"fieldCaption": fc},
                    "fieldToMeasure": {
                        "fieldCaption": measure_field,
                        "function": "SUM",
                    },
                    "howMany": top_n,
                    "direction": "TOP",
                }],
            }
            try:
                data = await client.query_datasource(
                    datasource_luid=datasource_id,
                    query=single_query,
                    api_key=auth.api_key,
                    site=auth.site,
                )
                rows = data.get("data", [])
                single_result = self._parse_sample_rows(rows, [fc], sample_size)
                results.update(single_result)
            except Exception as e:
                logger.warning(f"字段 '{fc}' 不可查询（幽灵字段），已标记: {e}")
                unqueryable.append(fc)
        
        return results, unqueryable
    
    @staticmethod
    def _parse_sample_rows(
        rows: list[dict[str, Any]],
        field_captions: list[str],
        sample_size: int,
    ) -> dict[str, dict[str, Any]]:
        """从查询结果行中解析每个字段的唯一值。
        
        Args:
            rows: VizQL 查询返回的数据行
            field_captions: 要解析的字段标题列表
            sample_size: 每个字段保留的样例数量
        
        Returns:
            {field_caption: {sample_values: [...], unique_count: int}}
        """
        results: dict[str, dict[str, Any]] = {}
        for fc in field_captions:
            unique_values: dict[str, int] = {}
            for row in rows:
                if not isinstance(row, dict):
                    continue
                value = row.get(fc)
                if value is not None:
                    value_str = str(value).strip()
                    if value_str:
                        unique_values[value_str] = unique_values.get(value_str, 0) + 1
            
            sorted_values = sorted(
                unique_values.keys(), key=lambda v: -unique_values[v]
            )
            results[fc] = {
                "sample_values": sorted_values[:sample_size],
                "unique_count": len(unique_values),
            }
        return results

# ══════════════════════════════════════════════════════════════════════════════
# 导出
# ══════════════════════════════════════════════════════════════════════════════

__all__ = ["TableauDataLoader"]
