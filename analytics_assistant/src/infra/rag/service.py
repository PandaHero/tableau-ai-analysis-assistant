"""RAGService - RAG 服务统一入口

RAGService 是 RAG 功能的统一入口，采用单例模式。

提供三个核心服务：
- embedding: EmbeddingService - 统一的 Embedding 服务
- index: IndexManager - 索引管理器
- retrieval: RetrievalService - 检索服务
"""

import logging
import threading
from typing import Optional

from analytics_assistant.src.infra.config import get_config

from .embedding_service import EmbeddingService
from .index_manager import IndexManager
from .retrieval_service import RetrievalService

logger = logging.getLogger(__name__)


class RAGService:
    """RAG 服务 - 统一入口
    
    采用单例模式，提供 RAG 功能的统一入口。
    线程安全：单例创建使用双重检查锁定。
    
    使用方式：
    ```python
    from analytics_assistant.src.infra.rag import get_rag_service
    
    rag = get_rag_service()
    
    # Embedding
    vectors = rag.embedding.embed_documents(["文本1", "文本2"])
    
    # 索引管理
    rag.index.create_index("my_index", config, documents)
    
    # 检索
    results = rag.retrieval.search("my_index", "查询文本")
    ```
    """
    
    _instance: Optional["RAGService"] = None
    _instance_lock: threading.Lock = threading.Lock()
    
    def __init__(self):
        """初始化 RAGService
        
        注意：不要直接调用此构造函数，使用 get_instance() 或 get_rag_service()。
        """
        self._embedding: Optional[EmbeddingService] = None
        self._index: Optional[IndexManager] = None
        self._retrieval: Optional[RetrievalService] = None
        self._config = self._load_config()
    
    def _load_config(self) -> dict:
        """从 app.yaml 加载配置"""
        try:
            config = get_config()
            return config.config.get("rag_service", {})
        except Exception as e:
            logger.warning(f"加载 rag_service 配置失败，使用默认值: {e}")
            return {}
    
    @classmethod
    def get_instance(cls) -> "RAGService":
        """获取单例实例（线程安全，双重检查锁定）"""
        if cls._instance is None:
            with cls._instance_lock:
                if cls._instance is None:
                    cls._instance = cls()
        return cls._instance
    
    @classmethod
    def reset_instance(cls) -> None:
        """重置单例实例（仅用于测试）"""
        cls._instance = None
    
    @property
    def embedding(self) -> EmbeddingService:
        """Embedding 服务（延迟初始化）"""
        if self._embedding is None:
            self._embedding = EmbeddingService()
        return self._embedding
    
    @property
    def index(self) -> IndexManager:
        """索引管理器（延迟初始化）"""
        if self._index is None:
            index_config = self._config.get("index", {})
            registry_namespace = index_config.get(
                "registry_namespace", "rag_index_registry"
            )
            doc_hash_namespace = index_config.get(
                "doc_hash_namespace", "rag_doc_hashes"
            )
            self._index = IndexManager(
                registry_namespace=registry_namespace,
                doc_hash_namespace=doc_hash_namespace,
            )
        return self._index
    
    @property
    def retrieval(self) -> RetrievalService:
        """检索服务（延迟初始化）"""
        if self._retrieval is None:
            self._retrieval = RetrievalService(
                index_manager=self.index,
                embedding_service=self.embedding,
            )
        return self._retrieval
    
    def get_config(self) -> dict:
        """获取 RAG 服务配置"""
        return self._config


def get_rag_service() -> RAGService:
    """获取 RAG 服务实例（便捷函数）
    
    Returns:
        RAGService 单例实例
    """
    return RAGService.get_instance()
