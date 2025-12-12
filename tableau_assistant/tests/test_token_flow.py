"""
Token 流程验证测试

验证 Tableau 认证 token 在整个工作流中的传递和缓存机制。
使用真实环境数据，不使用 mock。
"""
import pytest
import time


class TestTableauAuthContext:
    """测试 TableauAuthContext 模型"""
    
    def test_auth_context_creation(self):
        """测试创建认证上下文"""
        from tableau_assistant.src.bi_platforms.tableau import TableauAuthContext
        
        auth_ctx = TableauAuthContext(
            api_key="test_token",
            site="test_site",
            domain="https://test.tableau.com",
            expires_at=time.time() + 600,
            auth_method="jwt",
        )
        
        assert auth_ctx.api_key == "test_token"
        assert auth_ctx.site == "test_site"
        assert auth_ctx.domain == "https://test.tableau.com"
        assert auth_ctx.auth_method == "jwt"
        assert not auth_ctx.is_expired()
    
    def test_auth_context_expired(self):
        """测试过期检测"""
        from tableau_assistant.src.bi_platforms.tableau import TableauAuthContext
        
        # 创建已过期的上下文
        auth_ctx = TableauAuthContext(
            api_key="test_token",
            site="test_site",
            domain="https://test.tableau.com",
            expires_at=time.time() - 100,  # 已过期
            auth_method="jwt",
        )
        
        assert auth_ctx.is_expired()
        assert auth_ctx.remaining_seconds == 0
    
    def test_auth_context_remaining_seconds(self):
        """测试剩余时间计算"""
        from tableau_assistant.src.bi_platforms.tableau import TableauAuthContext
        
        auth_ctx = TableauAuthContext(
            api_key="test_token",
            site="test_site",
            domain="https://test.tableau.com",
            expires_at=time.time() + 300,  # 5分钟后过期
            auth_method="jwt",
        )
        
        # 剩余时间应该在 299-300 秒之间
        assert 299 <= auth_ctx.remaining_seconds <= 300


class TestGetTableauAuth:
    """测试 get_tableau_auth 函数（使用真实环境）"""
    
    def test_get_auth_from_env(self):
        """测试从环境变量获取认证"""
        from tableau_assistant.src.bi_platforms.tableau import (
            get_tableau_auth,
            TableauAuthError,
        )
        
        try:
            auth_ctx = get_tableau_auth()
            
            # 验证返回的是有效的认证上下文
            assert auth_ctx.api_key is not None
            assert len(auth_ctx.api_key) > 0
            assert auth_ctx.domain is not None
            assert not auth_ctx.is_expired()
            
            print(f"认证成功: method={auth_ctx.auth_method}, "
                  f"domain={auth_ctx.domain}, "
                  f"remaining={auth_ctx.remaining_seconds:.0f}s")
            
        except TableauAuthError as e:
            pytest.skip(f"Tableau 认证未配置: {e}")
    
    def test_auth_caching(self):
        """测试认证缓存机制"""
        from tableau_assistant.src.bi_platforms.tableau import (
            get_tableau_auth,
            TableauAuthError,
        )
        
        try:
            # 第一次获取
            auth1 = get_tableau_auth()
            
            # 第二次获取（应该使用缓存）
            auth2 = get_tableau_auth()
            
            # 两次获取的 token 应该相同（因为使用了缓存）
            assert auth1.api_key == auth2.api_key
            
        except TableauAuthError as e:
            pytest.skip(f"Tableau 认证未配置: {e}")
    
    def test_force_refresh(self):
        """测试强制刷新"""
        from tableau_assistant.src.bi_platforms.tableau import (
            get_tableau_auth,
            TableauAuthError,
        )
        
        try:
            # 强制刷新获取新 token
            auth = get_tableau_auth(force_refresh=True)
            
            assert auth.api_key is not None
            assert not auth.is_expired()
            
        except TableauAuthError as e:
            pytest.skip(f"Tableau 认证未配置: {e}")


class TestCreateConfigWithAuth:
    """测试 create_config_with_auth 函数"""
    
    def test_create_config(self):
        """测试创建带认证的配置"""
        from tableau_assistant.src.bi_platforms.tableau import (
            TableauAuthContext,
            create_config_with_auth,
        )
        
        auth_ctx = TableauAuthContext(
            api_key="test_token",
            site="test_site",
            domain="https://test.tableau.com",
            expires_at=time.time() + 600,
            auth_method="jwt",
        )
        
        config = create_config_with_auth("thread_123", auth_ctx)
        
        assert config["configurable"]["thread_id"] == "thread_123"
        assert config["configurable"]["tableau_auth"]["api_key"] == "test_token"
        assert config["configurable"]["tableau_auth"]["site"] == "test_site"
    
    def test_create_config_with_extra(self):
        """测试创建带额外配置的配置"""
        from tableau_assistant.src.bi_platforms.tableau import (
            TableauAuthContext,
            create_config_with_auth,
        )
        
        auth_ctx = TableauAuthContext(
            api_key="test_token",
            site="test_site",
            domain="https://test.tableau.com",
            expires_at=time.time() + 600,
            auth_method="jwt",
        )
        
        config = create_config_with_auth(
            "thread_123",
            auth_ctx,
            custom_param="custom_value",
        )
        
        assert config["configurable"]["custom_param"] == "custom_value"


class TestEnsureValidAuth:
    """测试 ensure_valid_auth 函数"""
    
    def test_ensure_valid_auth_from_config(self):
        """测试从 config 获取有效认证"""
        from tableau_assistant.src.bi_platforms.tableau import (
            TableauAuthContext,
            create_config_with_auth,
            ensure_valid_auth,
        )
        
        # 创建有效的认证上下文
        auth_ctx = TableauAuthContext(
            api_key="valid_token",
            site="test_site",
            domain="https://test.tableau.com",
            expires_at=time.time() + 600,
            auth_method="jwt",
        )
        
        config = create_config_with_auth("thread_123", auth_ctx)
        
        # 获取认证
        result = ensure_valid_auth(config)
        
        assert result.api_key == "valid_token"
        assert not result.is_expired()
    
    def test_ensure_valid_auth_refresh_when_expired(self):
        """测试 token 过期时自动刷新"""
        from tableau_assistant.src.bi_platforms.tableau import (
            TableauAuthContext,
            create_config_with_auth,
            ensure_valid_auth,
            TableauAuthError,
        )
        
        # 创建已过期的认证上下文
        expired_auth = TableauAuthContext(
            api_key="expired_token",
            site="test_site",
            domain="https://test.tableau.com",
            expires_at=time.time() - 100,  # 已过期
            auth_method="jwt",
        )
        
        config = create_config_with_auth("thread_123", expired_auth)
        
        try:
            # 应该自动刷新获取新 token
            result = ensure_valid_auth(config)
            
            # 新 token 应该不同于过期的 token
            assert result.api_key != "expired_token"
            assert not result.is_expired()
            
        except TableauAuthError as e:
            pytest.skip(f"Tableau 认证未配置: {e}")
    
    def test_ensure_valid_auth_without_config(self):
        """测试没有 config 时获取认证"""
        from tableau_assistant.src.bi_platforms.tableau import (
            ensure_valid_auth,
            TableauAuthError,
        )
        
        try:
            # 没有 config，应该直接获取新 token
            result = ensure_valid_auth(None)
            
            assert result.api_key is not None
            assert not result.is_expired()
            
        except TableauAuthError as e:
            pytest.skip(f"Tableau 认证未配置: {e}")


if __name__ == "__main__":
    pytest.main([__file__, "-v"])
