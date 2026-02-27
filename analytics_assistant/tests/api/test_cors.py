# -*- coding: utf-8 -*-
"""
CORS 配置互斥属性测试

Property 4: CORS credentials 与 wildcard 互斥

使用 Hypothesis 生成随机 CORS 配置组合，验证当 allow_credentials=True
且 allowed_origins 包含 "*" 时，系统自动禁用 credentials。

验证: 需求 3.4
"""

from unittest.mock import patch

from fastapi.middleware.cors import CORSMiddleware
from fastapi.testclient import TestClient
from hypothesis import given, settings, strategies as st

from analytics_assistant.src.api.main import create_app

# ---------------------------------------------------------------------------
# 常量
# ---------------------------------------------------------------------------

_CREDENTIALS_HEADER = "Access-Control-Allow-Credentials"

# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

# 生成随机的 origin 列表（可能包含 "*"）
_origin_element = st.sampled_from([
    "*",
    "http://localhost:3000",
    "https://example.com",
    "https://app.example.org",
])

origins_strategy = st.lists(_origin_element, min_size=0, max_size=5)

# 不含 wildcard 的 origin 列表
_non_wildcard_element = st.sampled_from([
    "http://localhost:3000",
    "https://example.com",
    "https://app.example.org",
])


def _build_api_config(
    allowed_origins: list[str],
    allow_credentials: bool,
) -> dict:
    """构建包含 CORS 配置的 app.yaml 模拟返回值。"""
    return {
        "api": {
            "cors": {
                "allowed_origins": allowed_origins,
                "allow_credentials": allow_credentials,
            },
            "auth": {"enabled": False},
        }
    }


def _get_cors_middleware(app) -> CORSMiddleware:
    """从 FastAPI 应用中提取 CORSMiddleware 实例。

    需要先触发一次请求以构建 middleware_stack。
    """
    middleware = app.middleware_stack
    while middleware is not None:
        if isinstance(middleware, CORSMiddleware):
            return middleware
        middleware = getattr(middleware, "app", None)
    raise RuntimeError("未找到 CORSMiddleware")


def _credentials_enabled(cors: CORSMiddleware) -> bool:
    """检查 CORSMiddleware 是否启用了 credentials。

    Starlette 的 CORSMiddleware 将 allow_credentials 编码到
    simple_headers 和 preflight_headers 中，而非直接暴露属性。
    """
    return _CREDENTIALS_HEADER in cors.simple_headers


# ---------------------------------------------------------------------------
# Property 4: CORS credentials 与 wildcard 互斥
# ---------------------------------------------------------------------------


class TestCORSCredentialsWildcardMutualExclusionPBT:
    """Property 4: CORS credentials 与 wildcard 互斥

    **Validates: Requirements 3.4**

    *For any* CORS 配置组合，当 allow_credentials=True 且
    allowed_origins 包含 "*" 时，系统应自动禁用 allow_credentials。
    """

    @given(origins=origins_strategy)
    @settings(max_examples=100, deadline=10000)
    def test_wildcard_with_credentials_disables_credentials(self, origins):
        """allow_credentials=True 且 origins 包含 '*' 时，credentials 被禁用。"""
        config = _build_api_config(
            allowed_origins=origins,
            allow_credentials=True,
        )
        with patch(
            "analytics_assistant.src.api.main.get_config",
            return_value=config,
        ):
            app = create_app()
            # 触发一次请求以构建 middleware_stack
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/health")
            cors = _get_cors_middleware(app)

            if "*" in origins:
                # 互斥属性：wildcard + credentials=True → credentials 被自动禁用
                assert not _credentials_enabled(cors), (
                    f"allow_credentials 应被禁用（origins 包含 '*'），"
                    f"但 simple_headers 中仍包含 {_CREDENTIALS_HEADER}"
                )
            else:
                # 无 wildcard 时，credentials 保持 True
                assert _credentials_enabled(cors), (
                    f"allow_credentials 应保持启用（origins 不含 '*'），"
                    f"但 simple_headers 中缺少 {_CREDENTIALS_HEADER}"
                )

    @given(origins=origins_strategy)
    @settings(max_examples=100, deadline=10000)
    def test_credentials_false_unaffected_by_wildcard(self, origins):
        """allow_credentials=False 时，无论 origins 如何，credentials 始终为 False。"""
        config = _build_api_config(
            allowed_origins=origins,
            allow_credentials=False,
        )
        with patch(
            "analytics_assistant.src.api.main.get_config",
            return_value=config,
        ):
            app = create_app()
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/health")
            cors = _get_cors_middleware(app)

            assert not _credentials_enabled(cors), (
                f"allow_credentials=False 时不应启用 credentials，"
                f"但 simple_headers 中包含 {_CREDENTIALS_HEADER}"
            )

    @given(
        origins=st.lists(_non_wildcard_element, min_size=1, max_size=5)
    )
    @settings(max_examples=50, deadline=10000)
    def test_no_wildcard_preserves_credentials(self, origins):
        """origins 不含 '*' 时，allow_credentials=True 保持不变。"""
        config = _build_api_config(
            allowed_origins=origins,
            allow_credentials=True,
        )
        with patch(
            "analytics_assistant.src.api.main.get_config",
            return_value=config,
        ):
            app = create_app()
            client = TestClient(app, raise_server_exceptions=False)
            client.get("/health")
            cors = _get_cors_middleware(app)

            assert _credentials_enabled(cors), (
                f"无 wildcard 时 allow_credentials 应保持启用，"
                f"但 simple_headers 中缺少 {_CREDENTIALS_HEADER}"
            )
