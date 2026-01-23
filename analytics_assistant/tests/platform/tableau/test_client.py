# -*- coding: utf-8 -*-
"""
VizQL 客户端测试

测试内容：
- VizQLClient 初始化
- 错误处理
- 请求重试逻辑
- API 方法
"""
import pytest
from unittest.mock import patch, MagicMock, AsyncMock
import httpx

from analytics_assistant.src.platform.tableau.client import (
    VizQLClient,
    _get_ssl_verify,
)
from analytics_assistant.src.core.exceptions import (
    VizQLError,
    VizQLAuthError,
    VizQLValidationError,
    VizQLServerError,
    VizQLRateLimitError,
    VizQLTimeoutError,
    VizQLNetworkError,
)


class TestVizQLClientInit:
    """测试 VizQLClient 初始化"""
    
    def test_init_with_defaults(self):
        """测试使用默认配置初始化"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            
            assert client.base_url == "https://tableau.example.com"
            assert client.timeout == 30
            assert client.max_retries == 3
    
    def test_init_with_custom_values(self):
        """测试使用自定义配置初始化"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://default.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient(
                base_url="https://custom.example.com",
                timeout=60,
                max_retries=5,
            )
            
            assert client.base_url == "https://custom.example.com"
            assert client.timeout == 60
            assert client.max_retries == 5
    
    def test_init_strips_trailing_slash(self):
        """测试初始化时去除尾部斜杠"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com/"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            
            assert client.base_url == "https://tableau.example.com"


class TestVizQLClientErrorHandling:
    """测试错误处理"""
    
    def test_handle_401_error(self):
        """测试 401 认证错误"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 401
            mock_response.text = "Unauthorized"
            mock_response.json.return_value = {"message": "Invalid token"}
            
            with pytest.raises(VizQLAuthError, match="认证失败"):
                client._handle_error(mock_response)
    
    def test_handle_403_error(self):
        """测试 403 权限错误"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 403
            mock_response.text = "Forbidden"
            mock_response.json.return_value = {"message": "Access denied"}
            
            with pytest.raises(VizQLAuthError, match="认证失败"):
                client._handle_error(mock_response)
    
    def test_handle_400_error(self):
        """测试 400 验证错误"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 400
            mock_response.text = "Bad Request"
            mock_response.json.return_value = {"message": "Invalid query"}
            
            with pytest.raises(VizQLValidationError, match="验证错误"):
                client._handle_error(mock_response)
    
    def test_handle_429_error(self):
        """测试 429 限流错误"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 429
            mock_response.text = "Too Many Requests"
            mock_response.headers = {"Retry-After": "60"}
            mock_response.json.return_value = {"message": "Rate limited"}
            
            with pytest.raises(VizQLRateLimitError, match="请求限流"):
                client._handle_error(mock_response)
    
    def test_handle_500_error(self):
        """测试 500 服务器错误"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            
            mock_response = MagicMock()
            mock_response.status_code = 500
            mock_response.text = "Internal Server Error"
            mock_response.json.return_value = {"message": "Server error"}
            
            with pytest.raises(VizQLServerError, match="服务器错误"):
                client._handle_error(mock_response)


class TestVizQLClientContextManager:
    """测试上下文管理器"""
    
    @pytest.mark.asyncio
    async def test_context_manager(self):
        """测试 async with 上下文管理器"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            async with VizQLClient() as client:
                assert client is not None
                assert client.base_url == "https://tableau.example.com"
    
    @pytest.mark.asyncio
    async def test_close(self):
        """测试关闭连接"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_vizql_timeout.return_value = 30
            mock_cfg.get_vizql_max_retries.return_value = 3
            mock_config.return_value = mock_cfg
            
            client = VizQLClient()
            # 初始化客户端
            await client._get_client()
            assert client._client is not None
            
            # 关闭
            await client.close()
            assert client._client is None


class TestVizQLExceptions:
    """测试 VizQL 异常类"""
    
    def test_vizql_error_is_retryable(self):
        """测试 VizQLError 可重试属性"""
        error = VizQLError("Test error", status_code=500)
        assert error.is_retryable is True
        
        error = VizQLError("Test error", status_code=400)
        assert error.is_retryable is False
    
    def test_vizql_auth_error_not_retryable(self):
        """测试 VizQLAuthError 不可重试"""
        error = VizQLAuthError("Auth failed")
        assert error.is_retryable is False
    
    def test_vizql_validation_error_not_retryable(self):
        """测试 VizQLValidationError 不可重试"""
        error = VizQLValidationError("Invalid input")
        assert error.is_retryable is False
    
    def test_vizql_server_error_retryable(self):
        """测试 VizQLServerError 可重试"""
        error = VizQLServerError("Server error", status_code=503)
        assert error.is_retryable is True
    
    def test_vizql_rate_limit_error_retryable(self):
        """测试 VizQLRateLimitError 可重试"""
        error = VizQLRateLimitError("Rate limited", retry_after=60)
        assert error.is_retryable is True
        assert error.retry_after == 60
    
    def test_vizql_timeout_error_retryable(self):
        """测试 VizQLTimeoutError 可重试"""
        error = VizQLTimeoutError("Timeout")
        assert error.is_retryable is True
    
    def test_vizql_network_error_retryable(self):
        """测试 VizQLNetworkError 可重试"""
        error = VizQLNetworkError("Network error")
        assert error.is_retryable is True


class TestSSLVerify:
    """测试 SSL 验证配置"""
    
    def test_ssl_verify_disabled(self):
        """测试禁用 SSL 验证"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_ssl_verify.return_value = False
            mock_config.return_value = mock_cfg
            
            result = _get_ssl_verify()
            assert result is False
    
    def test_ssl_verify_with_ca_bundle(self):
        """测试使用自定义 CA 证书"""
        with patch("analytics_assistant.src.platform.tableau.client.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_ssl_verify.return_value = True
            mock_cfg.get_ssl_ca_bundle.return_value = "/path/to/ca-bundle.crt"
            mock_config.return_value = mock_cfg
            
            result = _get_ssl_verify()
            assert result == "/path/to/ca-bundle.crt"


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
