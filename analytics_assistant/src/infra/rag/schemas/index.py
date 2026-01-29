"""索引相关数据模型"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional
import hashlib


class IndexStatus(str, Enum):
    """索引状态"""
    CREATING = "creating"
    READY = "ready"
    UPDATING = "updating"
    ERROR = "error"
    DELETED = "deleted"


class IndexBackend(str, Enum):
    """索引后端"""
    FAISS = "faiss"
    CHROMA = "chroma"


@dataclass
class IndexConfig:
    """索引配置"""
    backend: IndexBackend = IndexBackend.FAISS
    persist_directory: Optional[str] = None
    embedding_model_id: Optional[str] = None
    
    # 检索配置
    default_top_k: int = 10
    score_threshold: float = 0.0
    
    # 元数据字段
    metadata_fields: List[str] = field(default_factory=list)


@dataclass
class IndexDocument:
    """索引文档"""
    id: str
    content: str
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 缓存哈希（私有字段，懒加载）
    _content_hash: Optional[str] = field(default=None, init=False, repr=False)
    _metadata_hash: Optional[str] = field(default=None, init=False, repr=False)
    
    @property
    def content_hash(self) -> str:
        """内容哈希（懒加载，只计算一次）
        
        只基于 content 计算，不包含 metadata。
        内容变化才需要重新向量化。
        """
        if self._content_hash is None:
            self._content_hash = hashlib.md5(self.content.encode()).hexdigest()
        return self._content_hash
    
    @property
    def metadata_hash(self) -> str:
        """元数据哈希（懒加载）
        
        只基于 metadata 计算。
        元数据变化不需要重新向量化，只更新元数据。
        """
        if self._metadata_hash is None:
            meta_str = str(sorted(self.metadata.items()))
            self._metadata_hash = hashlib.md5(meta_str.encode()).hexdigest()
        return self._metadata_hash


@dataclass
class IndexInfo:
    """索引信息"""
    name: str
    config: IndexConfig
    status: IndexStatus
    document_count: int
    created_at: datetime
    updated_at: datetime
    
    # 统计信息
    total_searches: int = 0
    last_search_at: Optional[datetime] = None


@dataclass
class UpdateResult:
    """更新结果"""
    added: int = 0
    updated: int = 0
    unchanged: int = 0
    metadata_only_updated: int = 0  # 仅元数据变化（不重新向量化）
    failed: int = 0
