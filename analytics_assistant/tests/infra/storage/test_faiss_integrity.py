# -*- coding: utf-8 -*-
"""
FAISS 索引完整性属性测试

Property 5: FAISS 索引完整性校验

验证哈希不匹配时加载失败，哈希匹配时加载成功，
无哈希文件时向前兼容（跳过验证）。

验证: 需求 6.1
"""

import os
from pathlib import Path

from hypothesis import given, settings, strategies as st

from analytics_assistant.src.infra.storage.vector_store import (
    _compute_file_sha256,
    _save_index_hash,
    _verify_index_integrity,
    _FAISS_INDEX_FILE,
)

# ---------------------------------------------------------------------------
# Hypothesis 策略
# ---------------------------------------------------------------------------

# 随机二进制内容模拟索引文件
_index_content_strategy = st.binary(min_size=16, max_size=4096)

# 用于篡改的随机字节
_tamper_byte_strategy = st.binary(min_size=1, max_size=64)


# ---------------------------------------------------------------------------
# Property 5: FAISS 索引完整性校验
# ---------------------------------------------------------------------------


class TestFAISSIndexIntegrityPBT:
    """Property 5: FAISS 索引完整性校验

    **Validates: Requirements 6.1**

    *For any* FAISS 索引文件，如果对应的 SHA-256 哈希文件存在且
    哈希值不匹配，加载操作应失败并报告完整性错误。
    """

    @given(content=_index_content_strategy)
    @settings(max_examples=100, deadline=5000)
    def test_valid_hash_passes_verification(self, content, tmp_path_factory):
        """索引文件与哈希匹配时，校验通过。"""
        index_dir = tmp_path_factory.mktemp("faiss_valid")
        faiss_file = index_dir / _FAISS_INDEX_FILE
        faiss_file.write_bytes(content)

        # 写入正确的哈希
        _save_index_hash(index_dir)

        assert _verify_index_integrity(index_dir) is True

    @given(
        content=_index_content_strategy,
        tamper=_tamper_byte_strategy,
    )
    @settings(max_examples=100, deadline=5000)
    def test_tampered_index_fails_verification(
        self, content, tamper, tmp_path_factory
    ):
        """索引文件被篡改后，哈希不匹配，校验失败。"""
        index_dir = tmp_path_factory.mktemp("faiss_tampered")
        faiss_file = index_dir / _FAISS_INDEX_FILE
        faiss_file.write_bytes(content)

        # 先写入正确的哈希
        _save_index_hash(index_dir)

        # 篡改索引文件
        tampered_content = content + tamper
        faiss_file.write_bytes(tampered_content)

        assert _verify_index_integrity(index_dir) is False

    @given(content=_index_content_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_missing_hash_file_passes_verification(
        self, content, tmp_path_factory
    ):
        """无哈希文件时向前兼容，校验通过。"""
        index_dir = tmp_path_factory.mktemp("faiss_no_hash")
        faiss_file = index_dir / _FAISS_INDEX_FILE
        faiss_file.write_bytes(content)

        # 不写入哈希文件
        assert _verify_index_integrity(index_dir) is True

    @given(content=_index_content_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_hash_file_without_index_fails(self, content, tmp_path_factory):
        """有哈希文件但索引文件不存在时，校验失败。"""
        index_dir = tmp_path_factory.mktemp("faiss_missing_index")
        faiss_file = index_dir / _FAISS_INDEX_FILE
        faiss_file.write_bytes(content)

        # 写入哈希后删除索引文件
        _save_index_hash(index_dir)
        faiss_file.unlink()

        assert _verify_index_integrity(index_dir) is False

    @given(content=_index_content_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_save_hash_creates_correct_hash_file(
        self, content, tmp_path_factory
    ):
        """_save_index_hash 写入的哈希与 _compute_file_sha256 一致。"""
        index_dir = tmp_path_factory.mktemp("faiss_hash_check")
        faiss_file = index_dir / _FAISS_INDEX_FILE
        faiss_file.write_bytes(content)

        _save_index_hash(index_dir)

        hash_file = index_dir / f"{_FAISS_INDEX_FILE}.sha256"
        assert hash_file.exists()

        stored_hash = hash_file.read_text(encoding="utf-8").strip()
        computed_hash = _compute_file_sha256(faiss_file)
        assert stored_hash == computed_hash

    @given(
        content=_index_content_strategy,
        fake_hash=st.text(
            alphabet="0123456789abcdef", min_size=64, max_size=64
        ),
    )
    @settings(max_examples=50, deadline=5000)
    def test_wrong_hash_value_fails(
        self, content, fake_hash, tmp_path_factory
    ):
        """哈希文件内容与实际不符时，校验失败。"""
        index_dir = tmp_path_factory.mktemp("faiss_wrong_hash")
        faiss_file = index_dir / _FAISS_INDEX_FILE
        faiss_file.write_bytes(content)

        # 写入错误的哈希（除非碰巧相同，概率极低）
        actual_hash = _compute_file_sha256(faiss_file)
        if fake_hash == actual_hash:
            # 极小概率碰撞，跳过
            return

        hash_file = index_dir / f"{_FAISS_INDEX_FILE}.sha256"
        hash_file.write_text(fake_hash, encoding="utf-8")

        assert _verify_index_integrity(index_dir) is False
