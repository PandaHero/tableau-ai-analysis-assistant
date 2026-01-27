# -*- coding: utf-8 -*-
"""
Tableau 集成测试

使用真实 Tableau Server 环境测试：
- auth.py: 认证流程
- client.py: VizQL 客户端
- data_loader.py: 数据模型加载

运行方式：
    # 设置数据源 LUID（可选，不设置则跳过需要数据源的测试）
    $env:DATASOURCE_LUID = "your-datasource-luid"
    
    # 运行集成测试
    python -m pytest analytics_assistant/tests/platform/tableau/test_integration.py -v
"""

import os
import pytest
import asyncio
import logging
import warnings

# 忽略 SSL 警告
warnings.filterwarnings("ignore", message="Unverified HTTPS request")

# 配置日志
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


# 测试用数据源名称
TEST_DATASOURCE_NAME = "正大益生业绩总览数据 (IMPALA)"


# ═══════════════════════════════════════════════════════════════════════════
# Fixtures
# ═══════════════════════════════════════════════════════════════════════════

@pytest.fixture(scope="module")
def reset_config():
    """重置配置单例以确保加载最新配置"""
    from analytics_assistant.src.infra.config.config_loader import AppConfig
    AppConfig._instance = None
    yield
    AppConfig._instance = None


@pytest.fixture(scope="module")
def datasource_luid(reset_config):
    """获取测试用的数据源 LUID（通过名称查找）"""
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    
    # 使用同步方式获取认证
    auth = get_tableau_auth()
    
    # 使用 asyncio.run 运行异步代码
    async def get_luid():
        async with VizQLClient() as client:
            luid = await client.get_datasource_luid_by_name(
                datasource_name=TEST_DATASOURCE_NAME,
                api_key=auth.api_key,
            )
            return luid
    
    luid = asyncio.run(get_luid())
    if not luid:
        pytest.skip(f"未找到数据源: {TEST_DATASOURCE_NAME}")
    
    logger.info(f"测试数据源: {TEST_DATASOURCE_NAME} -> {luid}")
    return luid


# ═══════════════════════════════════════════════════════════════════════════
# Auth 集成测试
# ═══════════════════════════════════════════════════════════════════════════

class TestAuthIntegration:
    """认证集成测试"""
    
    def test_sync_auth(self, reset_config):
        """测试同步认证"""
        from analytics_assistant.src.platform.tableau.auth import (
            get_tableau_auth,
            clear_auth_cache,
        )
        
        clear_auth_cache()
        
        auth = get_tableau_auth()
        
        assert auth is not None
        assert auth.api_key is not None
        assert len(auth.api_key) > 0
        assert auth.domain is not None
        assert auth.auth_method in ("jwt", "pat")
        assert auth.remaining_seconds > 0
        
        logger.info(f"同步认证成功: method={auth.auth_method}, remaining={auth.remaining_seconds:.0f}s")
    
    @pytest.mark.asyncio
    async def test_async_auth(self, reset_config):
        """测试异步认证"""
        from analytics_assistant.src.platform.tableau.auth import (
            get_tableau_auth_async,
            clear_auth_cache,
        )
        
        clear_auth_cache()
        
        auth = await get_tableau_auth_async()
        
        assert auth is not None
        assert auth.api_key is not None
        assert len(auth.api_key) > 0
        assert auth.remaining_seconds > 0
        
        logger.info(f"异步认证成功: method={auth.auth_method}, remaining={auth.remaining_seconds:.0f}s")
    
    def test_auth_cache(self, reset_config):
        """测试认证缓存"""
        from analytics_assistant.src.platform.tableau.auth import (
            get_tableau_auth,
            clear_auth_cache,
        )
        
        clear_auth_cache()
        
        # 第一次调用
        auth1 = get_tableau_auth()
        
        # 第二次调用应该使用缓存
        auth2 = get_tableau_auth()
        
        # 应该是同一个对象（缓存命中）
        assert auth1.api_key == auth2.api_key
        
        logger.info("认证缓存测试通过")
    
    def test_force_refresh(self, reset_config):
        """测试强制刷新认证"""
        from analytics_assistant.src.platform.tableau.auth import (
            get_tableau_auth,
            clear_auth_cache,
        )
        
        clear_auth_cache()
        
        # 第一次调用
        auth1 = get_tableau_auth()
        
        # 强制刷新
        auth2 = get_tableau_auth(force_refresh=True)
        
        # 两次都应该成功
        assert auth1.api_key is not None
        assert auth2.api_key is not None
        
        logger.info("强制刷新测试通过")


# ═══════════════════════════════════════════════════════════════════════════
# VizQL Client 集成测试
# ═══════════════════════════════════════════════════════════════════════════

class TestVizQLClientIntegration:
    """VizQL 客户端集成测试"""
    
    @pytest.mark.asyncio
    async def test_client_init(self, reset_config):
        """测试客户端初始化"""
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        
        async with VizQLClient() as client:
            assert client.base_url is not None
            assert client.timeout > 0
            assert client.max_retries > 0
            
            logger.info(f"客户端初始化成功: base_url={client.base_url}")
    
    @pytest.mark.asyncio
    async def test_read_metadata(self, reset_config, datasource_luid):
        """测试读取元数据"""
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        
        auth = await get_tableau_auth_async()
        
        async with VizQLClient() as client:
            metadata = await client.read_metadata(
                datasource_luid=datasource_luid,
                api_key=auth.api_key,
                site=auth.site,
            )
            
            assert metadata is not None
            assert "data" in metadata
            
            fields = metadata.get("data", [])
            assert len(fields) > 0
            
            # 检查字段结构
            first_field = fields[0]
            assert "fieldCaption" in first_field or "fieldName" in first_field
            
            logger.info(f"读取元数据成功: {len(fields)} 个字段")
    
    @pytest.mark.asyncio
    async def test_get_datasource_model(self, reset_config, datasource_luid):
        """测试获取数据源模型
        
        注意：get-datasource-model API 是 VizQL Data Service 2025.3 (2025年10月) 新增的功能。
        如果 Tableau Server 版本低于 2025.3，此 API 会返回 500 错误。
        
        参考：https://help.tableau.com/current/api/vizql-data-service/en-us/docs/vds_whats_new.html
        """
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.core.exceptions import VizQLServerError
        
        auth = await get_tableau_auth_async()
        
        async with VizQLClient() as client:
            try:
                model = await client.get_datasource_model(
                    datasource_luid=datasource_luid,
                    api_key=auth.api_key,
                    site=auth.site,
                )
                
                assert model is not None
                assert "logicalTables" in model
                
                tables = model.get("logicalTables", [])
                logger.info(f"获取数据源模型成功: {len(tables)} 个逻辑表")
            except VizQLServerError as e:
                # get-datasource-model API 需要 VizQL Data Service 2025.3+
                # 低版本 Tableau Server 会返回 500 错误，这是预期行为
                logger.warning(
                    f"get-datasource-model API 不可用（需要 VizQL Data Service 2025.3+）: {e}"
                )
                # 测试通过 - API 不可用是预期的（版本限制）
                assert "500" in str(e) or "Internal Error" in str(e)
    
    @pytest.mark.asyncio
    async def test_graphql_metadata(self, reset_config, datasource_luid):
        """测试 GraphQL Metadata API"""
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        
        auth = await get_tableau_auth_async()
        
        async with VizQLClient() as client:
            result = await client.get_datasource_fields_metadata(
                datasource_luid=datasource_luid,
                api_key=auth.api_key,
            )
            
            assert result is not None
            assert "data" in result
            
            datasources = result.get("data", {}).get("publishedDatasources", [])
            assert len(datasources) > 0
            
            ds = datasources[0]
            fields = ds.get("fields", [])
            assert len(fields) > 0
            
            # 检查字段结构
            first_field = fields[0]
            assert "name" in first_field
            
            # 统计维度和度量
            dimensions = [f for f in fields if f.get("role") == "DIMENSION"]
            measures = [f for f in fields if f.get("role") == "MEASURE"]
            
            logger.info(f"GraphQL 元数据成功: {len(fields)} 字段 (维度: {len(dimensions)}, 度量: {len(measures)})")
    
    @pytest.mark.asyncio
    async def test_query_datasource(self, reset_config, datasource_luid):
        """测试查询数据源"""
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        
        auth = await get_tableau_auth_async()
        
        async with VizQLClient() as client:
            # 先获取元数据找一个可用字段
            metadata = await client.read_metadata(
                datasource_luid=datasource_luid,
                api_key=auth.api_key,
                site=auth.site,
            )
            
            fields = metadata.get("data", [])
            if not fields:
                pytest.skip("数据源没有字段")
            
            # 找一个字符串字段
            string_field = next(
                (f for f in fields if f.get("dataType") == "STRING"),
                fields[0]
            )
            field_caption = string_field.get("fieldCaption", string_field.get("fieldName"))
            
            # 执行查询（不使用 options 参数，因为 Tableau API 不支持 rowLimit）
            query = {
                "fields": [{"fieldCaption": field_caption}],
            }
            
            result = await client.query_datasource(
                datasource_luid=datasource_luid,
                query=query,
                api_key=auth.api_key,
                site=auth.site,
            )
            
            assert result is not None
            assert "data" in result
            
            rows = result.get("data", [])
            logger.info(f"查询成功: 返回 {len(rows)} 行")


# ═══════════════════════════════════════════════════════════════════════════
# DataLoader 集成测试
# ═══════════════════════════════════════════════════════════════════════════

class TestDataLoaderIntegration:
    """数据加载器集成测试"""
    
    @pytest.mark.asyncio
    async def test_load_data_model(self, reset_config, datasource_luid):
        """测试加载数据模型（GraphQL 方式）"""
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
            
            assert data_model is not None
            assert data_model.datasource_id == datasource_luid
            assert len(data_model.fields) > 0
            
            # 检查字段属性
            first_field = data_model.fields[0]
            assert first_field.name is not None
            assert first_field.caption is not None
            assert first_field.role in ("DIMENSION", "MEASURE", None)
            
            # 统计
            dimensions = data_model.dimensions
            measures = data_model.measures
            
            logger.info(
                f"数据模型加载成功: {len(data_model.fields)} 字段 "
                f"(维度: {len(dimensions)}, 度量: {len(measures)})"
            )
    
    @pytest.mark.asyncio
    async def test_load_data_model_with_vizql(self, reset_config, datasource_luid):
        """测试加载数据模型（VizQL + GraphQL 混合方式）"""
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model_with_vizql(datasource_id=datasource_luid)
            
            assert data_model is not None
            assert data_model.datasource_id == datasource_luid
            assert len(data_model.fields) > 0
            
            # 检查字段有 name（VizQL 的 fieldName）
            first_field = data_model.fields[0]
            assert first_field.name is not None
            
            logger.info(f"混合模式加载成功: {len(data_model.fields)} 字段")
    
    @pytest.mark.asyncio
    async def test_load_raw_metadata(self, reset_config, datasource_luid):
        """测试加载原始元数据"""
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async with TableauDataLoader() as loader:
            metadata = await loader.load_raw_metadata(datasource_id=datasource_luid)
            
            assert metadata is not None
            assert "data" in metadata
            
            fields = metadata.get("data", [])
            assert len(fields) > 0
            
            logger.info(f"原始元数据加载成功: {len(fields)} 字段")
    
    @pytest.mark.asyncio
    async def test_load_datasource_model(self, reset_config, datasource_luid):
        """测试加载数据源模型（逻辑表和关系）
        
        注意：此方法依赖 get-datasource-model API，该 API 是 VizQL Data Service 2025.3 (2025年10月) 新增的功能。
        如果 Tableau Server 版本低于 2025.3，此方法会返回 None（优雅降级）。
        
        对于低版本 Tableau Server，建议使用 load_data_model() 方法，它会自动从
        VizQL logicalTableId 获取逻辑表信息。
        
        参考：https://help.tableau.com/current/api/vizql-data-service/en-us/docs/vds_whats_new.html
        """
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async with TableauDataLoader() as loader:
            model = await loader.load_datasource_model(datasource_id=datasource_luid)
            
            if model is None:
                # get-datasource-model API 需要 VizQL Data Service 2025.3+
                # 低版本 Tableau Server 返回 None 是预期行为
                logger.info(
                    "load_datasource_model 返回 None（需要 VizQL Data Service 2025.3+）。"
                    "建议使用 load_data_model() 方法获取逻辑表信息。"
                )
            else:
                # API 可用，验证返回结构
                assert "logicalTables" in model
                
                tables = model.get("logicalTables", [])
                relationships = model.get("logicalTableRelationships", [])
                
                logger.info(f"数据源模型加载成功: {len(tables)} 表, {len(relationships)} 关系")
    
    @pytest.mark.asyncio
    async def test_data_model_properties(self, reset_config, datasource_luid):
        """测试 DataModel 的便捷属性"""
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
            
            # 测试便捷属性
            assert data_model.dimensions is not None
            assert data_model.measures is not None
            
            # 维度 + 度量 应该等于总字段数（或更少，因为有些字段可能没有 role）
            total_with_role = len(data_model.dimensions) + len(data_model.measures)
            assert total_with_role <= len(data_model.fields)
            
            # 测试 get_field 方法
            if data_model.fields:
                first_field = data_model.fields[0]
                found = data_model.get_field(first_field.name)
                assert found is not None
                assert found.name == first_field.name
            
            # 统计隐藏字段
            hidden_count = sum(1 for f in data_model.fields if f.hidden)
            visible_count = len(data_model.fields) - hidden_count
            
            logger.info(
                f"DataModel 属性测试通过: "
                f"总字段={len(data_model.fields)}, "
                f"维度={len(data_model.dimensions)}, "
                f"度量={len(data_model.measures)}, "
                f"可见={visible_count}, "
                f"隐藏={hidden_count}"
            )
    
    @pytest.mark.asyncio
    async def test_load_data_model_with_logical_tables(self, reset_config, datasource_luid):
        """测试 load_data_model 能正确获取逻辑表信息
        
        GraphQL 的 upstreamTables 只对 ColumnField 有效：
        - ColumnField（数据库原始列）有 upstreamTables
        - CalculatedField（计算字段）没有 upstreamTables（这是正确的，因为计算字段不属于任何原始表）
        """
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async with TableauDataLoader() as loader:
            data_model = await loader.load_data_model(datasource_id=datasource_luid)
            
            assert data_model is not None
            assert len(data_model.fields) > 0
            
            # 验证逻辑表信息
            assert data_model.tables is not None
            
            # 统计有 upstream_tables 的字段（只有 ColumnField 有）
            fields_with_tables = [f for f in data_model.fields if f.upstream_tables]
            # 统计计算字段（有 formula 的字段）
            calc_fields = [f for f in data_model.fields if f.calculation]
            
            logger.info(
                f"逻辑表测试通过: "
                f"逻辑表数={len(data_model.tables)}, "
                f"ColumnField（有 upstream_tables）={len(fields_with_tables)}, "
                f"CalculatedField（有 formula）={len(calc_fields)}, "
                f"总字段数={len(data_model.fields)}"
            )
            
            # 如果有逻辑表，验证字段的 upstream_tables 信息
            if data_model.tables:
                logger.info(f"逻辑表列表: {[(t.id, t.name) for t in data_model.tables]}")


# ═══════════════════════════════════════════════════════════════════════════
# 错误处理测试
# ═══════════════════════════════════════════════════════════════════════════

class TestErrorHandling:
    """错误处理测试"""
    
    @pytest.mark.asyncio
    async def test_invalid_datasource_luid(self, reset_config):
        """测试无效的数据源 LUID"""
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
        from analytics_assistant.src.core.exceptions import VizQLError
        
        auth = await get_tableau_auth_async()
        
        async with VizQLClient() as client:
            with pytest.raises(VizQLError):
                await client.read_metadata(
                    datasource_luid="invalid-luid-12345",
                    api_key=auth.api_key,
                    site=auth.site,
                )
        
        logger.info("无效 LUID 错误处理测试通过")
    
    @pytest.mark.asyncio
    async def test_invalid_api_key(self, reset_config, datasource_luid):
        """测试无效的 API Key"""
        from analytics_assistant.src.platform.tableau.client import VizQLClient
        from analytics_assistant.src.core.exceptions import VizQLAuthError
        
        async with VizQLClient() as client:
            with pytest.raises(VizQLAuthError):
                await client.read_metadata(
                    datasource_luid=datasource_luid,
                    api_key="invalid-api-key",
                    site="ZF",
                )
        
        logger.info("无效 API Key 错误处理测试通过")
    
    @pytest.mark.asyncio
    async def test_data_loader_missing_params(self, reset_config):
        """测试 DataLoader 缺少参数"""
        from analytics_assistant.src.platform.tableau.data_loader import TableauDataLoader
        
        async with TableauDataLoader() as loader:
            with pytest.raises(ValueError, match="必须提供"):
                await loader.load_data_model()
        
        logger.info("缺少参数错误处理测试通过")
