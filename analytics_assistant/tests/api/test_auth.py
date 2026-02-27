# -*- coding: utf-8 -*-
"""
认证验证属性测试

Property 3: 无效认证凭证拒绝

使用 Hypothesis 生成随机无效凭证，验证 API 在认证启用时
对所有无效凭证返回 HTTP 401。
"""

import time
from unittest.mock import patch

import jwt
from fastapi import FastAPI, Depends
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.api.dependencies import get_tableau_username

# ---------------------------------------------------------------------------
# 测试用 FastAPI 应用（仅包含一个受保护端点）
# ---------------------------------------------------------------------------

_test_app = FastAPI()


@_test_app.get("/protected")
async def protected_endpoint(
    username: str = Depends(get_tableau_username),
) -> dict:
    """受认证保护的测试端点。"""
    return {"username": username}


# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_TEST_SECRET = "test-secret-key-for-property-testing"
_TEST_ALGORITHM = "HS256"
_WRONG_SECRET = "wrong-secret-key-definitely-not-correct"

# ---------------------------------------------------------------------------
# 认证启用时的配置 mock
# ---------------------------------------------------------------------------

_AUTH_ENABLED_CONFIG = {
    "api": {
        "auth": {
            "enabled": True,
            "secret_key": _TEST_SECRET,
            "algorithm": _TEST_ALGORITHM,
        }
    }
}

# ---------------------------------------------------------------------------
# 认证禁用时的配置 mock（开发模式）
# ---------------------------------------------------------------------------

_AUTH_DISABLED_CONFIG = {
    "api": {
        "auth": {
            "enabled": False,
        }
    }
}


def _make_auth_enabled_config():
    """返回认证启用的配置对象（模拟 get_config 返回值）。"""
    return _AUTH_ENABLED_CONFIG


def _make_auth_disabled_config():
    """返回认证禁用的配置对象（模拟 get_config 返回值）。"""
    return _AUTH_DISABLED_CONFIG


# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

# HTTP header 值必须是 ASCII 可编码的，因此限制字符范围
_ascii_printable = st.characters(
    whitelist_categories=("L", "N", "P", "S"),
    max_codepoint=127,
)

# 随机 ASCII 字符串 token（绝大多数不是合法 JWT）
random_token_strategy = st.text(
    alphabet=_ascii_printable,
    min_size=1,
    max_size=200,
)

# ASCII 安全的文本策略（用于 header 值）
ascii_text_strategy = st.text(
    alphabet=st.characters(max_codepoint=127, whitelist_categories=("L", "N", "P", "S", "Z")),
    min_size=1,
    max_size=50,
)

# 无效 Bearer 格式策略（不以 "Bearer " 开头的 Authorization 值）
invalid_bearer_format_strategy = ascii_text_strategy.filter(
    lambda s: not s.startswith("Bearer ")
)


# ---------------------------------------------------------------------------
# Property 3: 无效认证凭证拒绝
# ---------------------------------------------------------------------------


class TestInvalidCredentialRejectionPBT:
    """Property 3: 无效认证凭证拒绝

    **Validates: Requirements 3.1**

    *For any* HTTP 请求，当 API 认证启用时，如果请求不包含有效的
    JWT token，系统应返回 HTTP 401 状态码。
    """

    @given(data=st.data())
    @settings(max_examples=100, deadline=5000)
    def test_missing_authorization_header_returns_401(self, data):
        """认证启用时，缺少 Authorization 请求头返回 401。"""
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_ENABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get("/protected")
            assert response.status_code == 401

    @given(auth_value=invalid_bearer_format_strategy)
    @settings(max_examples=100, deadline=5000)
    def test_invalid_bearer_format_returns_401(self, auth_value):
        """认证启用时，非 'Bearer <token>' 格式的 Authorization 返回 401。"""
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_ENABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get(
                "/protected",
                headers={"Authorization": auth_value},
            )
            assert response.status_code == 401

    @given(token=random_token_strategy)
    @settings(max_examples=100, deadline=5000)
    def test_random_string_token_returns_401(self, token):
        """认证启用时，随机字符串作为 Bearer token 返回 401。"""
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_ENABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {token}"},
            )
            assert response.status_code == 401

    @given(
        sub=st.text(min_size=1, max_size=50),
        exp_offset=st.integers(min_value=-7200, max_value=-1),
    )
    @settings(max_examples=100, deadline=5000)
    def test_expired_jwt_token_returns_401(self, sub, exp_offset):
        """认证启用时，过期的 JWT token 返回 401。"""
        expired_token = jwt.encode(
            {"sub": sub, "exp": int(time.time()) + exp_offset},
            _TEST_SECRET,
            algorithm=_TEST_ALGORITHM,
        )
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_ENABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {expired_token}"},
            )
            assert response.status_code == 401

    @given(sub=st.text(min_size=1, max_size=50))
    @settings(max_examples=100, deadline=5000)
    def test_jwt_with_wrong_secret_returns_401(self, sub):
        """认证启用时，使用错误密钥签名的 JWT token 返回 401。"""
        wrong_token = jwt.encode(
            {"sub": sub, "exp": int(time.time()) + 3600},
            _WRONG_SECRET,
            algorithm=_TEST_ALGORITHM,
        )
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_ENABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {wrong_token}"},
            )
            assert response.status_code == 401

    @given(sub=st.text(min_size=1, max_size=50))
    @settings(max_examples=100, deadline=5000)
    def test_valid_jwt_returns_200(self, sub):
        """认证启用时，有效的 JWT token 返回 200（对照组）。"""
        valid_token = jwt.encode(
            {"sub": sub, "exp": int(time.time()) + 3600},
            _TEST_SECRET,
            algorithm=_TEST_ALGORITHM,
        )
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_ENABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get(
                "/protected",
                headers={"Authorization": f"Bearer {valid_token}"},
            )
            assert response.status_code == 200
            assert response.json()["username"] == sub


class TestDevModeAuthPBT:
    """开发模式（认证禁用）下的认证验证。

    **Validates: Requirements 3.1**

    认证禁用时，缺少 X-Tableau-Username 请求头应返回 401。
    """

    @given(data=st.data())
    @settings(max_examples=30, deadline=5000)
    def test_missing_username_header_returns_401(self, data):
        """开发模式下，缺少 X-Tableau-Username 请求头返回 401。"""
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_DISABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get("/protected")
            assert response.status_code == 401

    @given(username=ascii_text_strategy)
    @settings(max_examples=30, deadline=5000)
    def test_valid_username_header_returns_200(self, username):
        """开发模式下，提供 X-Tableau-Username 请求头返回 200（对照组）。"""
        with patch(
            "analytics_assistant.src.api.dependencies.get_config",
            return_value=_AUTH_DISABLED_CONFIG,
        ):
            client = TestClient(_test_app, raise_server_exceptions=False)
            response = client.get(
                "/protected",
                headers={"X-Tableau-Username": username},
            )
            assert response.status_code == 200
            assert response.json()["username"] == username
