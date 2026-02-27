# -*- coding: utf-8 -*-
"""
ModelPersistence 单元测试

验证 API Key 加密/解密功能和 model_dump() 序列化。
"""
import os
import sys
from unittest.mock import patch, MagicMock

import pytest
from cryptography.fernet import Fernet


def _create_persistence_with_key(fernet_key: str):
    """创建带加密密钥的 ModelPersistence 实例（跳过存储初始化）"""
    from analytics_assistant.src.infra.ai.model_persistence import ModelPersistence

    with patch.dict(os.environ, {"ANALYTICS_ASSISTANT_ENCRYPTION_KEY": fernet_key}):
        with patch.object(ModelPersistence, "_init_storage"):
            p = ModelPersistence()
    return p


def _create_persistence_without_key():
    """创建无加密密钥的 ModelPersistence 实例（跳过存储初始化）"""
    from analytics_assistant.src.infra.ai.model_persistence import ModelPersistence

    env = os.environ.copy()
    env.pop("ANALYTICS_ASSISTANT_ENCRYPTION_KEY", None)
    with patch.dict(os.environ, env, clear=True):
        with patch.object(ModelPersistence, "_init_storage"):
            p = ModelPersistence()
    return p


@pytest.fixture
def fernet_key():
    """生成测试用 Fernet 密钥"""
    return Fernet.generate_key().decode()


@pytest.fixture
def persistence_with_key(fernet_key):
    """创建带加密密钥的 ModelPersistence 实例"""
    return _create_persistence_with_key(fernet_key)


@pytest.fixture
def persistence_without_key():
    """创建无加密密钥的 ModelPersistence 实例"""
    return _create_persistence_without_key()


class TestInitFernet:
    """测试 Fernet 初始化"""

    def test_init_with_valid_key(self, persistence_with_key):
        """有效密钥时应成功初始化 Fernet"""
        assert persistence_with_key._fernet is not None

    def test_init_without_key(self, persistence_without_key):
        """无密钥时 Fernet 应为 None"""
        assert persistence_without_key._fernet is None

    def test_init_with_invalid_key(self):
        """无效密钥格式时应回退到 None"""
        from analytics_assistant.src.infra.ai.model_persistence import ModelPersistence

        with patch.dict(os.environ, {"ANALYTICS_ASSISTANT_ENCRYPTION_KEY": "not-a-valid-key"}):
            with patch.object(ModelPersistence, "_init_storage"):
                p = ModelPersistence()
        assert p._fernet is None


class TestEncryptApiKey:
    """测试 API Key 加密"""

    def test_encrypt_produces_enc_prefix(self, persistence_with_key):
        """加密后应以 'ENC:' 前缀开头"""
        result = persistence_with_key._encrypt_api_key("sk-test-key-123")
        assert result.startswith("ENC:")

    def test_encrypt_differs_from_original(self, persistence_with_key):
        """加密后不应等于原始值"""
        original = "sk-test-key-123"
        result = persistence_with_key._encrypt_api_key(original)
        assert result != original

    def test_encrypt_empty_string_returns_empty(self, persistence_with_key):
        """空字符串不加密"""
        assert persistence_with_key._encrypt_api_key("") == ""

    def test_encrypt_env_var_ref_passthrough(self, persistence_with_key):
        """环境变量引用格式 ${...} 不加密"""
        ref = "${DEEPSEEK_API_KEY}"
        assert persistence_with_key._encrypt_api_key(ref) == ref

    def test_encrypt_without_fernet_returns_original(self, persistence_without_key):
        """无加密器时返回原始值"""
        original = "sk-test-key-123"
        assert persistence_without_key._encrypt_api_key(original) == original


class TestDecryptApiKey:
    """测试 API Key 解密"""

    def test_decrypt_roundtrip(self, persistence_with_key):
        """加密后解密应还原原始值"""
        original = "sk-test-key-123"
        encrypted = persistence_with_key._encrypt_api_key(original)
        decrypted = persistence_with_key._decrypt_api_key(encrypted)
        assert decrypted == original

    def test_decrypt_non_encrypted_passthrough(self, persistence_with_key):
        """非加密格式直接返回"""
        plain = "sk-plain-key"
        assert persistence_with_key._decrypt_api_key(plain) == plain

    def test_decrypt_env_var_ref_passthrough(self, persistence_with_key):
        """环境变量引用格式直接返回"""
        ref = "${DEEPSEEK_API_KEY}"
        assert persistence_with_key._decrypt_api_key(ref) == ref

    def test_decrypt_without_fernet_returns_original(self, persistence_without_key):
        """无加密器时返回原始值（包括 ENC: 前缀的值）"""
        encrypted = "ENC:some-encrypted-data"
        assert persistence_without_key._decrypt_api_key(encrypted) == encrypted

    def test_decrypt_with_wrong_key_returns_original(self, fernet_key):
        """密钥变更后解密失败应返回原始值"""
        p1 = _create_persistence_with_key(fernet_key)
        encrypted = p1._encrypt_api_key("sk-secret")

        # 用另一个密钥尝试解密
        new_key = Fernet.generate_key().decode()
        p2 = _create_persistence_with_key(new_key)
        result = p2._decrypt_api_key(encrypted)
        # 解密失败应返回原始加密值
        assert result == encrypted


class TestSaveUsesModelDump:
    """测试 save 方法使用 model_dump() 替代 _config_to_dict"""

    def test_save_calls_model_dump(self, persistence_with_key):
        """save 应使用 model_dump() 序列化"""
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {
            "id": "test-id",
            "api_key": "sk-test",
            "model_type": "llm",
        }

        persistence_with_key._enabled = True
        persistence_with_key._cache_manager = MagicMock()

        persistence_with_key.save([mock_config])

        mock_config.model_dump.assert_called_once_with(mode="python")

    def test_save_encrypts_api_key(self, persistence_with_key):
        """save 应加密 api_key 字段"""
        mock_config = MagicMock()
        mock_config.model_dump.return_value = {
            "id": "test-id",
            "api_key": "sk-test-key",
        }

        mock_cache = MagicMock()
        persistence_with_key._enabled = True
        persistence_with_key._cache_manager = mock_cache

        persistence_with_key.save([mock_config])

        # 验证存储的数据中 api_key 已加密
        saved_data = mock_cache.set.call_args[0][1]
        assert len(saved_data) == 1
        assert saved_data[0]["api_key"].startswith("ENC:")
