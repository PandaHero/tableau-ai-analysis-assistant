# -*- coding: utf-8 -*-
"""
Tableau 认证模块测试

测试内容：
- TableauAuthContext 数据模型
- JWT token 构建
- 缓存机制
- 同步/异步认证函数
"""
import time
import pytest
from datetime import datetime, timezone, timedelta
from unittest.mock import patch, MagicMock

from analytics_assistant.src.platform.tableau.auth import (
    TableauAuthContext,
    _build_jwt_token,
    _get_ssl_verify,
    get_tableau_auth,
    get_tableau_auth_async,
    clear_auth_cache,
)
from analytics_assistant.src.core.exceptions import TableauAuthError


class TestTableauAuthContext:
    """测试 TableauAuthContext 数据模型"""
    
    def test_create_context(self):
        """测试创建认证上下文"""
        ctx = TableauAuthContext(
            api_key="test_token",
            site="test_site",
            domain="https://tableau.example.com",
            auth_method="jwt",
        )
        
        assert ctx.api_key == "test_token"
        assert ctx.site == "test_site"
        assert ctx.domain == "https://tableau.example.com"
        assert ctx.auth_method == "jwt"
    
    def test_is_expired_not_expired(self):
        """测试未过期的 token"""
        ctx = TableauAuthContext(
            api_key="test_token",
            expires_at=time.time() + 600,  # 10 分钟后过期
        )
        
        assert not ctx.is_expired()
        assert not ctx.is_expired(buffer_seconds=60)
    
    def test_is_expired_with_buffer(self):
        """测试即将过期的 token（在缓冲时间内）"""
        ctx = TableauAuthContext(
            api_key="test_token",
            expires_at=time.time() + 30,  # 30 秒后过期
        )
        
        # 默认 60 秒缓冲，应该认为已过期
        assert ctx.is_expired(buffer_seconds=60)
        # 10 秒缓冲，应该认为未过期
        assert not ctx.is_expired(buffer_seconds=10)
    
    def test_is_expired_already_expired(self):
        """测试已过期的 token"""
        ctx = TableauAuthContext(
            api_key="test_token",
            expires_at=time.time() - 100,  # 100 秒前已过期
        )
        
        assert ctx.is_expired()
    
    def test_remaining_seconds(self):
        """测试剩余有效时间"""
        future_time = time.time() + 300
        ctx = TableauAuthContext(
            api_key="test_token",
            expires_at=future_time,
        )
        
        remaining = ctx.remaining_seconds
        assert 299 <= remaining <= 300
    
    def test_remaining_seconds_expired(self):
        """测试已过期 token 的剩余时间"""
        ctx = TableauAuthContext(
            api_key="test_token",
            expires_at=time.time() - 100,
        )
        
        assert ctx.remaining_seconds == 0


class TestBuildJwtToken:
    """测试 JWT token 构建"""
    
    def test_build_jwt_token(self):
        """测试构建 JWT token"""
        import jwt as pyjwt
        
        token = _build_jwt_token(
            client_id="test_client",
            secret_id="test_secret_id",
            secret="test_secret_key",
            user="test_user",
            scopes=["tableau:content:read"],
        )
        
        # 验证 token 格式
        assert isinstance(token, str)
        assert len(token.split(".")) == 3  # JWT 有三部分
        
        # 解码验证内容
        decoded = pyjwt.decode(token, "test_secret_key", algorithms=["HS256"], audience="tableau")
        assert decoded["iss"] == "test_client"
        assert decoded["sub"] == "test_user"
        assert decoded["aud"] == "tableau"
        assert decoded["scp"] == ["tableau:content:read"]
        assert "exp" in decoded
        assert "jti" in decoded
    
    def test_build_jwt_token_expiration(self):
        """测试 JWT token 过期时间"""
        import jwt as pyjwt
        
        before = datetime.now(timezone.utc)
        token = _build_jwt_token(
            client_id="test_client",
            secret_id="test_secret_id",
            secret="test_secret_key",
            user="test_user",
            scopes=[],
        )
        after = datetime.now(timezone.utc)
        
        decoded = pyjwt.decode(token, "test_secret_key", algorithms=["HS256"], audience="tableau")
        exp_time = datetime.fromtimestamp(decoded["exp"], tz=timezone.utc)
        
        # 过期时间应该在 5 分钟后（允许 1 秒误差）
        expected_min = before + timedelta(minutes=5) - timedelta(seconds=1)
        expected_max = after + timedelta(minutes=5) + timedelta(seconds=1)
        
        assert expected_min <= exp_time <= expected_max


class TestSSLVerify:
    """测试 SSL 验证配置"""
    
    def test_ssl_verify_disabled(self):
        """测试禁用 SSL 验证"""
        with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_ssl_verify.return_value = False
            mock_config.return_value = mock_cfg
            
            result = _get_ssl_verify()
            assert result is False
    
    def test_ssl_verify_with_ca_bundle(self):
        """测试使用自定义 CA 证书"""
        with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_ssl_verify.return_value = True
            mock_cfg.get_ssl_ca_bundle.return_value = "/path/to/ca-bundle.crt"
            mock_config.return_value = mock_cfg
            
            result = _get_ssl_verify()
            assert result == "/path/to/ca-bundle.crt"
    
    def test_ssl_verify_with_certifi(self):
        """测试使用 certifi"""
        with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_ssl_verify.return_value = True
            mock_cfg.get_ssl_ca_bundle.return_value = None
            mock_config.return_value = mock_cfg
            
            result = _get_ssl_verify()
            # 应该返回 certifi 路径或 True
            assert result is not False


class TestAuthCache:
    """测试认证缓存"""
    
    def test_clear_auth_cache(self):
        """测试清除缓存"""
        # 这个测试主要验证函数不会抛出异常
        clear_auth_cache()
    
    def test_cache_hit(self):
        """测试缓存命中"""
        clear_auth_cache()
        
        with patch("analytics_assistant.src.platform.tableau.auth._authenticate_from_config") as mock_auth:
            mock_auth.return_value = {
                "domain": "https://tableau.example.com",
                "site": "test_site",
                "api_key": "cached_token",
                "auth_method": "jwt",
            }
            
            with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
                mock_cfg = MagicMock()
                mock_cfg.get_tableau_token_cache_ttl.return_value = 600
                mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
                mock_config.return_value = mock_cfg
                
                # 第一次调用，应该调用认证
                ctx1 = get_tableau_auth()
                assert ctx1.api_key == "cached_token"
                assert mock_auth.call_count == 1
                
                # 第二次调用，应该使用缓存
                ctx2 = get_tableau_auth()
                assert ctx2.api_key == "cached_token"
                assert mock_auth.call_count == 1  # 没有再次调用
        
        clear_auth_cache()
    
    def test_force_refresh(self):
        """测试强制刷新"""
        clear_auth_cache()
        
        with patch("analytics_assistant.src.platform.tableau.auth._authenticate_from_config") as mock_auth:
            mock_auth.return_value = {
                "domain": "https://tableau.example.com",
                "site": "test_site",
                "api_key": "new_token",
                "auth_method": "jwt",
            }
            
            with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
                mock_cfg = MagicMock()
                mock_cfg.get_tableau_token_cache_ttl.return_value = 600
                mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
                mock_config.return_value = mock_cfg
                
                # 第一次调用
                get_tableau_auth()
                assert mock_auth.call_count == 1
                
                # 强制刷新
                get_tableau_auth(force_refresh=True)
                assert mock_auth.call_count == 2
        
        clear_auth_cache()


class TestAuthErrors:
    """测试认证错误处理"""
    
    def test_missing_domain(self):
        """测试缺少域名配置"""
        clear_auth_cache()
        
        with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = ""
            mock_cfg.get_tableau_token_cache_ttl.return_value = 600
            mock_config.return_value = mock_cfg
            
            with pytest.raises(TableauAuthError, match="域名未配置"):
                get_tableau_auth(force_refresh=True)
        
        clear_auth_cache()
    
    def test_no_auth_configured(self):
        """测试没有配置任何认证方式"""
        clear_auth_cache()
        
        with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
            mock_cfg = MagicMock()
            mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
            mock_cfg.get_tableau_site.return_value = ""
            mock_cfg.get_tableau_api_version.return_value = "3.24"
            mock_cfg.get_tableau_jwt_config.return_value = {}
            mock_cfg.get_tableau_pat_config.return_value = {}
            mock_cfg.get_tableau_token_cache_ttl.return_value = 600
            mock_config.return_value = mock_cfg
            
            with pytest.raises(TableauAuthError, match="所有认证方式均失败"):
                get_tableau_auth(force_refresh=True)
        
        clear_auth_cache()


class TestAsyncAuth:
    """测试异步认证"""
    
    @pytest.mark.asyncio
    async def test_async_auth_cache_hit(self):
        """测试异步认证缓存命中"""
        clear_auth_cache()
        
        with patch("analytics_assistant.src.platform.tableau.auth._authenticate_from_config_async") as mock_auth:
            mock_auth.return_value = {
                "domain": "https://tableau.example.com",
                "site": "test_site",
                "api_key": "async_token",
                "auth_method": "pat",
            }
            
            with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
                mock_cfg = MagicMock()
                mock_cfg.get_tableau_token_cache_ttl.return_value = 600
                mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
                mock_config.return_value = mock_cfg
                
                # 第一次调用
                ctx1 = await get_tableau_auth_async()
                assert ctx1.api_key == "async_token"
                assert mock_auth.call_count == 1
                
                # 第二次调用，应该使用缓存
                ctx2 = await get_tableau_auth_async()
                assert ctx2.api_key == "async_token"
                assert mock_auth.call_count == 1
        
        clear_auth_cache()
    
    @pytest.mark.asyncio
    async def test_async_force_refresh(self):
        """测试异步强制刷新"""
        clear_auth_cache()
        
        with patch("analytics_assistant.src.platform.tableau.auth._authenticate_from_config_async") as mock_auth:
            mock_auth.return_value = {
                "domain": "https://tableau.example.com",
                "site": "test_site",
                "api_key": "refreshed_token",
                "auth_method": "jwt",
            }
            
            with patch("analytics_assistant.src.platform.tableau.auth.get_config") as mock_config:
                mock_cfg = MagicMock()
                mock_cfg.get_tableau_token_cache_ttl.return_value = 600
                mock_cfg.get_tableau_domain.return_value = "https://tableau.example.com"
                mock_config.return_value = mock_cfg
                
                # 第一次调用
                await get_tableau_auth_async()
                assert mock_auth.call_count == 1
                
                # 强制刷新
                await get_tableau_auth_async(force_refresh=True)
                assert mock_auth.call_count == 2
        
        clear_auth_cache()


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
