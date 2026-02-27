# -*- coding: utf-8 -*-
"""
API Key 加密属性测试

使用 Hypothesis 验证加密/解密的正确性属性。
"""
import os
from unittest.mock import patch

from cryptography.fernet import Fernet
from hypothesis import given, settings, strategies as st


def _create_persistence_with_key(fernet_key: str):
    """创建带加密密钥的 ModelPersistence 实例（跳过存储初始化）"""
    from analytics_assistant.src.infra.ai.model_persistence import ModelPersistence

    with patch.dict(os.environ, {"ANALYTICS_ASSISTANT_ENCRYPTION_KEY": fernet_key}):
        with patch.object(ModelPersistence, "_init_storage"):
            p = ModelPersistence()
    return p


# 生成测试用 Fernet 密钥（模块级别，所有测试共享）
_TEST_FERNET_KEY = Fernet.generate_key().decode()
_TEST_PERSISTENCE = _create_persistence_with_key(_TEST_FERNET_KEY)


@given(st.text(min_size=1, max_size=200))
@settings(max_examples=100)
def test_api_key_encryption_roundtrip(api_key: str):
    """Feature: code-quality-remediation, Property 1: API Key 加密 round-trip

    验证: 对任意非空 API Key，decrypt(encrypt(key)) == key 且 encrypt(key) != key。

    **Validates: Requirements 2.1, 2.2**
    """
    persistence = _TEST_PERSISTENCE
    assert persistence._fernet is not None, "Fernet 加密器应已初始化"

    # 跳过环境变量引用格式（${...} 不会被加密，这是设计行为）
    if api_key.startswith("${"):
        return

    encrypted = persistence._encrypt_api_key(api_key)
    # 加密后不等于明文
    assert encrypted != api_key, f"加密后应不等于原始值: {api_key!r}"
    # 加密后应有 ENC: 前缀
    assert encrypted.startswith("ENC:"), f"加密值应以 'ENC:' 开头: {encrypted!r}"

    decrypted = persistence._decrypt_api_key(encrypted)
    # 解密后等于原始值
    assert decrypted == api_key, (
        f"解密后应等于原始值: 原始={api_key!r}, 解密={decrypted!r}"
    )


# ═══════════════════════════════════════════════════════════════════════════
# Property 2: ModelConfig 序列化完整性
# ═══════════════════════════════════════════════════════════════════════════

from datetime import datetime

from hypothesis import strategies as st
from hypothesis.strategies import composite

from analytics_assistant.src.infra.ai.models import (
    AuthType,
    ModelConfig,
    ModelStatus,
    ModelType,
    TaskType,
)

# ModelConfig 所有字段名集合（用于验证 model_dump 完整性）
_MODEL_CONFIG_FIELDS = set(ModelConfig.model_fields.keys())


@composite
def model_config_strategy(draw):
    """生成有效的 ModelConfig 实例的 Hypothesis 策略"""
    # 基本信息
    id_ = draw(st.text(min_size=1, max_size=50, alphabet=st.characters(
        whitelist_categories=("L", "N"), whitelist_characters="-_"
    )))
    name = draw(st.text(min_size=1, max_size=100))
    description = draw(st.text(max_size=200))
    model_type = draw(st.sampled_from(list(ModelType)))

    # API 配置
    provider = draw(st.text(min_size=1, max_size=50))
    api_base = draw(st.text(min_size=1, max_size=200))
    api_endpoint = draw(st.text(max_size=200))
    model_name = draw(st.text(min_size=1, max_size=100))

    # 兼容性标记
    openai_compatible = draw(st.booleans())

    # 认证配置
    auth_type = draw(st.sampled_from(list(AuthType)))
    auth_header = draw(st.text(min_size=1, max_size=50))
    api_key = draw(st.text(max_size=100))

    # 模型参数（Optional）
    temperature = draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=2.0)))
    max_tokens = draw(st.one_of(st.none(), st.integers(min_value=1, max_value=100000)))
    top_p = draw(st.one_of(st.none(), st.floats(min_value=0.0, max_value=1.0)))

    # 特性配置
    supports_streaming = draw(st.booleans())
    supports_json_mode = draw(st.one_of(st.none(), st.booleans()))
    supports_function_calling = draw(st.booleans())
    supports_vision = draw(st.booleans())
    is_reasoning_model = draw(st.booleans())

    # 任务适配
    suitable_tasks = draw(st.lists(
        st.sampled_from(list(TaskType)), max_size=5, unique=True
    ))
    priority = draw(st.integers(min_value=0, max_value=100))

    # 网络配置
    timeout = draw(st.floats(min_value=1.0, max_value=600.0))
    verify_ssl = draw(st.booleans())
    proxy = draw(st.text(max_size=200))

    # 额外配置（使用简单的 key-value 对）
    extra_headers = draw(st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="-_"
        )),
        values=st.text(max_size=50),
        max_size=3,
    ))
    extra_body = draw(st.dictionaries(
        keys=st.text(min_size=1, max_size=20, alphabet=st.characters(
            whitelist_categories=("L", "N"), whitelist_characters="-_"
        )),
        values=st.one_of(st.text(max_size=50), st.integers(), st.booleans()),
        max_size=3,
    ))

    # 状态和元数据
    status = draw(st.sampled_from(list(ModelStatus)))
    is_default = draw(st.booleans())
    tags = draw(st.lists(st.text(min_size=1, max_size=30), max_size=5))

    # 时间戳 — 使用固定精度避免浮点精度问题
    created_at = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
    ))
    updated_at = draw(st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
    ))
    last_used_at = draw(st.one_of(st.none(), st.datetimes(
        min_value=datetime(2020, 1, 1),
        max_value=datetime(2030, 12, 31),
    )))

    return ModelConfig(
        id=id_,
        name=name,
        description=description,
        model_type=model_type,
        provider=provider,
        api_base=api_base,
        api_endpoint=api_endpoint,
        model_name=model_name,
        openai_compatible=openai_compatible,
        auth_type=auth_type,
        auth_header=auth_header,
        api_key=api_key,
        temperature=temperature,
        max_tokens=max_tokens,
        top_p=top_p,
        supports_streaming=supports_streaming,
        supports_json_mode=supports_json_mode,
        supports_function_calling=supports_function_calling,
        supports_vision=supports_vision,
        is_reasoning_model=is_reasoning_model,
        suitable_tasks=suitable_tasks,
        priority=priority,
        timeout=timeout,
        verify_ssl=verify_ssl,
        proxy=proxy,
        extra_headers=extra_headers,
        extra_body=extra_body,
        status=status,
        is_default=is_default,
        tags=tags,
        created_at=created_at,
        updated_at=updated_at,
        last_used_at=last_used_at,
    )


@given(config=model_config_strategy())
@settings(max_examples=100)
def test_model_config_serialization_completeness(config: ModelConfig):
    """Feature: code-quality-remediation, Property 2: ModelConfig 序列化完整性

    验证: 对任意有效 ModelConfig 实例，model_dump() 包含所有字段，
    且 ModelConfig(**config.model_dump()) 产生等价对象。

    **Validates: Requirements 2.3**
    """
    # 1. model_dump() 应包含所有字段
    dumped = config.model_dump()
    assert isinstance(dumped, dict), "model_dump() 应返回字典"
    assert set(dumped.keys()) == _MODEL_CONFIG_FIELDS, (
        f"model_dump() 字段不完整: "
        f"缺少={_MODEL_CONFIG_FIELDS - set(dumped.keys())}, "
        f"多余={set(dumped.keys()) - _MODEL_CONFIG_FIELDS}"
    )

    # 2. 从 model_dump() 重建的对象应与原始对象等价
    reconstructed = ModelConfig(**dumped)
    assert reconstructed == config, (
        f"重建对象应与原始对象等价: "
        f"原始={config!r}, 重建={reconstructed!r}"
    )
