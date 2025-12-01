"""
VizQL Client Integration Tests

使用真实 Tableau Cloud 环境进行测试：
- 真实 API 请求
- 真实响应解析
- 真实错误处理
- 连接池复用验证
"""
import os
import pytest
from dotenv import load_dotenv

from tableau_assistant.src.bi_platforms.tableau.vizql_client import (
    VizQLClient,
    VizQLClientConfig,
    _is_retryable_error,
)
from tableau_assistant.src.bi_platforms.tableau.auth import _get_tableau_context_from_env
from tableau_assistant.src.exceptions import (
    VizQLError,
    VizQLAuthError,
    VizQLValidationError,
    VizQLServerError,
    VizQLRateLimitError,
)

# 加载环境变量
load_dotenv()


@pytest.fixture(scope="module")
def tableau_context():
    """获取 Tableau 认证上下文"""
    ctx = _get_tableau_context_from_env()
    if not ctx.get("api_key"):
        pytest.skip("Tableau 认证失败，跳过集成测试")
    return ctx


@pytest.fixture(scope="module")
def vizql_client(tableau_context):
    """创建 VizQL 客户端"""
    config = VizQLClientConfig(
        base_url=tableau_context["domain"],
        timeout=30,
        max_retries=2
    )
    client = VizQLClient(config=config)
    yield client
    client.close()


@pytest.fixture
def datasource_luid():
    """获取数据源 LUID"""
    luid = os.getenv("DATASOURCE_LUID")
    if not luid:
        pytest.skip("未配置 DATASOURCE_LUID")
    return luid


# ============================================================
# 配置模型测试
# ============================================================

class TestVizQLClientConfig:
    """测试配置模型"""
    
    def test_default_values(self):
        """测试默认配置值"""
        config = VizQLClientConfig(base_url="https://tableau.example.com")
        
        assert config.base_url == "https://tableau.example.com"
        assert config.verify_ssl is True
        assert config.ca_bundle is None
        assert config.timeout == 30
        assert config.max_retries == 3
        assert config.pool_connections == 10
        assert config.pool_maxsize == 10
    
    def test_custom_values(self):
        """测试自定义配置值"""
        config = VizQLClientConfig(
            base_url="https://custom.tableau.com",
            verify_ssl=False,
            ca_bundle="/path/to/ca.pem",
            timeout=60,
            max_retries=5,
            pool_connections=20,
            pool_maxsize=25
        )
        
        assert config.base_url == "https://custom.tableau.com"
        assert config.verify_ssl is False
        assert config.ca_bundle == "/path/to/ca.pem"
        assert config.timeout == 60
        assert config.max_retries == 5
        assert config.pool_connections == 20
        assert config.pool_maxsize == 25
    
    def test_extra_fields_forbidden(self):
        """测试禁止额外字段"""
        with pytest.raises(Exception):
            VizQLClientConfig(
                base_url="https://tableau.example.com",
                unknown_field="value"
            )


class TestVizQLClientInitFromEnv:
    """测试从环境变量初始化客户端"""
    
    def test_init_from_env_variables(self):
        """测试从环境变量读取配置"""
        # 保存原始环境变量
        original_env = {
            "TABLEAU_DOMAIN": os.environ.get("TABLEAU_DOMAIN"),
            "VIZQL_VERIFY_SSL": os.environ.get("VIZQL_VERIFY_SSL"),
            "VIZQL_CA_BUNDLE": os.environ.get("VIZQL_CA_BUNDLE"),
            "VIZQL_TIMEOUT": os.environ.get("VIZQL_TIMEOUT"),
            "VIZQL_MAX_RETRIES": os.environ.get("VIZQL_MAX_RETRIES"),
        }
        
        try:
            # 设置测试环境变量
            os.environ["TABLEAU_DOMAIN"] = "https://test-env.tableau.com"
            os.environ["VIZQL_VERIFY_SSL"] = "false"
            os.environ["VIZQL_CA_BUNDLE"] = "/custom/ca.pem"
            os.environ["VIZQL_TIMEOUT"] = "45"
            os.environ["VIZQL_MAX_RETRIES"] = "5"
            
            # 不传入 config，应该从环境变量读取
            client = VizQLClient()
            
            assert client.config.base_url == "https://test-env.tableau.com"
            assert client.config.verify_ssl is False
            assert client.config.ca_bundle == "/custom/ca.pem"
            assert client.config.timeout == 45
            assert client.config.max_retries == 5
            
            client.close()
            print("\n✅ 从环境变量初始化测试通过")
        finally:
            # 恢复原始环境变量
            for key, value in original_env.items():
                if value is None:
                    os.environ.pop(key, None)
                else:
                    os.environ[key] = value
    
    def test_init_with_explicit_config_overrides_env(self):
        """测试显式配置覆盖环境变量"""
        # 设置环境变量
        os.environ["TABLEAU_DOMAIN"] = "https://env.tableau.com"
        os.environ["VIZQL_TIMEOUT"] = "100"
        
        try:
            # 显式传入 config
            config = VizQLClientConfig(
                base_url="https://explicit.tableau.com",
                timeout=20
            )
            client = VizQLClient(config=config)
            
            # 应该使用显式配置，而非环境变量
            assert client.config.base_url == "https://explicit.tableau.com"
            assert client.config.timeout == 20
            
            client.close()
            print("\n✅ 显式配置覆盖环境变量测试通过")
        finally:
            os.environ.pop("TABLEAU_DOMAIN", None)
            os.environ.pop("VIZQL_TIMEOUT", None)
    
    def test_init_from_real_env(self):
        """测试从真实 .env 文件读取配置"""
        # 重新加载 .env
        load_dotenv(override=True)
        
        # 验证环境变量已加载
        domain = os.getenv("TABLEAU_DOMAIN")
        if not domain:
            pytest.skip("未配置 TABLEAU_DOMAIN")
        
        client = VizQLClient()
        
        assert client.config.base_url == domain
        assert client.config.base_url.startswith("https://")
        
        client.close()
        print(f"\n✅ 从真实环境变量初始化: {domain}")


# ============================================================
# 重试逻辑测试
# ============================================================

class TestIsRetryableError:
    """测试可重试错误判断"""
    
    def test_server_error_is_retryable(self):
        """服务器错误可重试"""
        error = VizQLServerError(message="Server error", status_code=500)
        assert _is_retryable_error(error) is True
    
    def test_rate_limit_is_retryable(self):
        """限流错误可重试"""
        error = VizQLRateLimitError(message="Rate limit")
        assert _is_retryable_error(error) is True
    
    def test_auth_error_not_retryable(self):
        """认证错误不可重试"""
        error = VizQLAuthError(message="Auth error")
        assert _is_retryable_error(error) is False
    
    def test_validation_error_not_retryable(self):
        """验证错误不可重试"""
        error = VizQLValidationError(message="Validation error")
        assert _is_retryable_error(error) is False


# ============================================================
# 真实 API 集成测试
# ============================================================

class TestVizQLClientReadMetadata:
    """测试读取元数据（真实 API）"""
    
    def test_read_metadata_success(self, vizql_client, tableau_context, datasource_luid):
        """测试成功读取元数据"""
        result = vizql_client.read_metadata(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        # 验证返回结构
        assert result is not None
        assert "data" in result
        
        # 验证字段信息
        data = result["data"]
        assert "fields" in data or "columns" in data or isinstance(data, list)
        
        print(f"\n✅ 成功读取元数据，返回 keys: {result.keys()}")
    
    def test_read_metadata_invalid_luid(self, vizql_client, tableau_context):
        """测试无效 LUID 返回错误"""
        with pytest.raises(VizQLError):
            vizql_client.read_metadata(
                datasource_luid="invalid-luid-12345",
                api_key=tableau_context["api_key"],
                site=tableau_context["site"]
            )


class TestVizQLClientQueryDatasource:
    """测试查询数据源（真实 API）"""
    
    def test_simple_query(self, vizql_client, tableau_context, datasource_luid):
        """测试简单查询（使用聚合减少数据量）"""
        import json
        
        # 先获取元数据，找到可用字段
        metadata = vizql_client.read_metadata(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        # 打印元数据
        print("\n" + "=" * 60)
        print("📋 元数据 (Metadata):")
        print("=" * 60)
        print(json.dumps(metadata, indent=2, ensure_ascii=False))
        
        # 从元数据中提取字段列表
        data = metadata.get("data", [])
        if isinstance(data, list):
            fields = data
        else:
            fields = data.get("fields", data.get("columns", []))
        
        if not fields:
            pytest.skip("数据源没有可用字段")
        
        # 找一个维度字段和一个度量字段
        dim_field = None
        measure_field = None
        for f in fields:
            dtype = f.get("dataType", "").upper()
            field_name = f.get("fieldCaption") or f.get("name") or f.get("fieldName")
            if dtype == "STRING" and not dim_field:
                dim_field = field_name
            elif dtype in ("REAL", "INTEGER") and not measure_field:
                measure_field = field_name
        
        if not dim_field or not measure_field:
            pytest.skip("数据源缺少维度或度量字段")
        
        # 使用 TopNFilter 限制返回行数
        query = {
            "fields": [
                {"fieldCaption": dim_field},
                {"fieldCaption": measure_field, "function": "SUM"}
            ],
            "filters": [
                {
                    "filterType": "TOP",
                    "field": {"fieldCaption": dim_field},
                    "howMany": 5,
                    "direction": "TOP",
                    "fieldToMeasure": {"fieldCaption": measure_field, "function": "SUM"}
                }
            ]
        }
        
        # 打印查询语句
        print("\n" + "=" * 60)
        print("🔍 VizQL 查询语句 (Query):")
        print("=" * 60)
        print(json.dumps(query, indent=2, ensure_ascii=False))
        
        result = vizql_client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        # 打印查询结果
        print("\n" + "=" * 60)
        print("📊 查询结果 (Result):")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        assert result is not None
        assert "data" in result
        assert len(result.get("data", [])) <= 5
        print(f"\n✅ 查询成功，返回 {len(result.get('data', []))} 条记录")
    
    def test_query_with_aggregation(self, vizql_client, tableau_context, datasource_luid):
        """测试带聚合的查询（全局聚合，只返回一行）"""
        import json
        
        # 先获取元数据
        metadata = vizql_client.read_metadata(
            datasource_luid=datasource_luid,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        data = metadata.get("data", [])
        if isinstance(data, list):
            fields = data
        else:
            fields = data.get("fields", data.get("columns", []))
        
        # 找一个数值字段
        numeric_field = None
        for f in fields:
            dtype = f.get("dataType", "").upper()
            if dtype in ("REAL", "INTEGER"):
                numeric_field = f.get("fieldCaption") or f.get("name") or f.get("fieldName")
                break
        
        if not numeric_field:
            pytest.skip("数据源没有数值字段")
        
        # 全局聚合查询（无维度），只返回一行
        query = {
            "fields": [
                {"fieldCaption": numeric_field, "function": "SUM"},
                {"fieldCaption": numeric_field, "function": "AVG"},
                {"fieldCaption": numeric_field, "function": "COUNT"}
            ]
        }
        
        # 打印查询语句
        print("\n" + "=" * 60)
        print("🔍 聚合查询语句 (Aggregation Query):")
        print("=" * 60)
        print(json.dumps(query, indent=2, ensure_ascii=False))
        
        result = vizql_client.query_datasource(
            datasource_luid=datasource_luid,
            query=query,
            api_key=tableau_context["api_key"],
            site=tableau_context["site"]
        )
        
        # 打印查询结果
        print("\n" + "=" * 60)
        print("📊 聚合查询结果 (Aggregation Result):")
        print("=" * 60)
        print(json.dumps(result, indent=2, ensure_ascii=False))
        
        assert result is not None
        assert "data" in result
        # 全局聚合只返回一行
        assert len(result.get("data", [])) == 1
        print(f"\n✅ 聚合查询成功，返回 {len(result.get('data', []))} 条记录")
    
    def test_query_invalid_field(self, vizql_client, tableau_context, datasource_luid):
        """测试查询不存在的字段"""
        query = {
            "fields": [
                {"fieldCaption": "NonExistentField12345"}
            ]
        }
        
        with pytest.raises(VizQLError):
            vizql_client.query_datasource(
                datasource_luid=datasource_luid,
                query=query,
                api_key=tableau_context["api_key"],
                site=tableau_context["site"]
            )


class TestVizQLClientErrorHandling:
    """测试错误处理（真实 API）"""
    
    def test_invalid_api_key(self, datasource_luid):
        """测试无效 API Key"""
        config = VizQLClientConfig(
            base_url=os.getenv("TABLEAU_DOMAIN", "https://10ax.online.tableau.com")
        )
        client = VizQLClient(config=config)
        
        try:
            with pytest.raises(VizQLAuthError):
                client.read_metadata(
                    datasource_luid=datasource_luid,
                    api_key="invalid-api-key",
                    site=os.getenv("TABLEAU_SITE", "")
                )
        finally:
            client.close()
    
    def test_invalid_datasource_luid(self, vizql_client, tableau_context):
        """测试无效数据源 LUID"""
        with pytest.raises(VizQLError):
            vizql_client.read_metadata(
                datasource_luid="00000000-0000-0000-0000-000000000000",
                api_key=tableau_context["api_key"],
                site=tableau_context["site"]
            )


class TestVizQLClientConnectionPool:
    """测试连接池复用"""
    
    def test_session_reused(self, vizql_client, tableau_context, datasource_luid):
        """测试 HTTP Session 复用"""
        # 获取初始 session
        session1 = vizql_client._session
        
        # 执行多次请求
        for _ in range(3):
            vizql_client.read_metadata(
                datasource_luid=datasource_luid,
                api_key=tableau_context["api_key"],
                site=tableau_context["site"]
            )
        
        # 验证 session 未变
        session2 = vizql_client._session
        assert session1 is session2
        print("\n✅ Session 复用验证通过")
    
    def test_context_manager(self, tableau_context, datasource_luid):
        """测试上下文管理器"""
        config = VizQLClientConfig(base_url=tableau_context["domain"])
        
        with VizQLClient(config=config) as client:
            result = client.read_metadata(
                datasource_luid=datasource_luid,
                api_key=tableau_context["api_key"],
                site=tableau_context["site"]
            )
            assert result is not None
        
        print("\n✅ 上下文管理器测试通过")


class TestVizQLClientSSL:
    """测试 SSL 配置"""
    
    def test_ssl_verification(self, tableau_context, datasource_luid):
        """测试 SSL 验证"""
        config = VizQLClientConfig(
            base_url=tableau_context["domain"],
            verify_ssl=True
        )
        client = VizQLClient(config=config)
        
        try:
            result = client.read_metadata(
                datasource_luid=datasource_luid,
                api_key=tableau_context["api_key"],
                site=tableau_context["site"]
            )
            assert result is not None
            print("\n✅ SSL 验证测试通过")
        finally:
            client.close()


if __name__ == "__main__":
    pytest.main([__file__, "-v", "-s"])
