# -*- coding: utf-8 -*-
"""FAISS 索引完整性属性测试。"""

from __future__ import annotations

from pathlib import Path
from tempfile import TemporaryDirectory

from hypothesis import given, settings, strategies as st

from analytics_assistant.src.infra.storage.vector_store import (
    _FAISS_INDEX_FILE,
    _compute_file_sha256,
    _save_index_hash,
    _verify_index_integrity,
)

_TEMP_ROOT = Path(__file__).resolve().parents[2] / "test_outputs" / "faiss_integrity"
_TEMP_ROOT.mkdir(parents=True, exist_ok=True)

# 随机二进制内容模拟索引文件。
_index_content_strategy = st.binary(min_size=16, max_size=4096)

# 用于篡改索引的随机字节。
_tamper_byte_strategy = st.binary(min_size=1, max_size=64)


class TestFAISSIndexIntegrityPBT:
    """验证索引文件与哈希文件的一致性契约。"""

    @staticmethod
    def _index_dir(prefix: str) -> TemporaryDirectory:
        return TemporaryDirectory(dir=_TEMP_ROOT, prefix=f"{prefix}-")

    @given(content=_index_content_strategy)
    @settings(max_examples=100, deadline=5000)
    def test_valid_hash_passes_verification(self, content) -> None:
        """索引文件与哈希匹配时，校验通过。"""
        with self._index_dir("faiss-valid") as tmp_dir:
            index_dir = Path(tmp_dir)
            faiss_file = index_dir / _FAISS_INDEX_FILE
            faiss_file.write_bytes(content)

            _save_index_hash(index_dir)
            assert _verify_index_integrity(index_dir) is True

    @given(content=_index_content_strategy, tamper=_tamper_byte_strategy)
    @settings(max_examples=100, deadline=5000)
    def test_tampered_index_fails_verification(self, content, tamper) -> None:
        """索引内容被篡改后，校验失败。"""
        with self._index_dir("faiss-tampered") as tmp_dir:
            index_dir = Path(tmp_dir)
            faiss_file = index_dir / _FAISS_INDEX_FILE
            faiss_file.write_bytes(content)

            _save_index_hash(index_dir)
            faiss_file.write_bytes(content + tamper)

            assert _verify_index_integrity(index_dir) is False

    @given(content=_index_content_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_missing_hash_file_passes_verification(self, content) -> None:
        """缺少哈希文件时保持向前兼容。"""
        with self._index_dir("faiss-no-hash") as tmp_dir:
            index_dir = Path(tmp_dir)
            faiss_file = index_dir / _FAISS_INDEX_FILE
            faiss_file.write_bytes(content)

            assert _verify_index_integrity(index_dir) is True

    @given(content=_index_content_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_hash_file_without_index_fails(self, content) -> None:
        """只有哈希文件没有索引文件时，校验失败。"""
        with self._index_dir("faiss-missing-index") as tmp_dir:
            index_dir = Path(tmp_dir)
            faiss_file = index_dir / _FAISS_INDEX_FILE
            faiss_file.write_bytes(content)

            _save_index_hash(index_dir)
            faiss_file.unlink()

            assert _verify_index_integrity(index_dir) is False

    @given(content=_index_content_strategy)
    @settings(max_examples=50, deadline=5000)
    def test_save_hash_creates_correct_hash_file(self, content) -> None:
        """保存的哈希值应与实时计算结果一致。"""
        with self._index_dir("faiss-hash-check") as tmp_dir:
            index_dir = Path(tmp_dir)
            faiss_file = index_dir / _FAISS_INDEX_FILE
            faiss_file.write_bytes(content)

            _save_index_hash(index_dir)

            hash_file = index_dir / f"{_FAISS_INDEX_FILE}.sha256"
            assert hash_file.exists()
            assert hash_file.read_text(encoding="utf-8").strip() == _compute_file_sha256(
                faiss_file
            )

    @given(
        content=_index_content_strategy,
        fake_hash=st.text(alphabet="0123456789abcdef", min_size=64, max_size=64),
    )
    @settings(max_examples=50, deadline=5000)
    def test_wrong_hash_value_fails(self, content, fake_hash) -> None:
        """哈希文件内容错误时，校验失败。"""
        with self._index_dir("faiss-wrong-hash") as tmp_dir:
            index_dir = Path(tmp_dir)
            faiss_file = index_dir / _FAISS_INDEX_FILE
            faiss_file.write_bytes(content)

            actual_hash = _compute_file_sha256(faiss_file)
            if fake_hash == actual_hash:
                return

            hash_file = index_dir / f"{_FAISS_INDEX_FILE}.sha256"
            hash_file.write_text(fake_hash, encoding="utf-8")

            assert _verify_index_integrity(index_dir) is False
