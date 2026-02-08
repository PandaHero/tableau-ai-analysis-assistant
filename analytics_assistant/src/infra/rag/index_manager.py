"""IndexManager - 索引管理器

统一的索引管理，支持增量更新。

职责：
1. 索引元数据管理（IndexInfo 注册表）
2. 索引生命周期（创建、删除、状态追踪）
3. 增量更新（文档哈希、变更检测）
4. 持久化协调（委托给 RetrieverFactory）
5. 启动时加载已有索引（懒加载模式）

不负责：
- 检索器实例创建（委托给 RetrieverFactory）
- 向量存储创建（委托给 get_vector_store）
"""

import json
import logging
from datetime import datetime
from pathlib import Path
from typing import Any, Dict, List, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import CacheManager

from .exceptions import IndexExistsError, IndexCreationError
from .retriever import CascadeRetriever, RetrieverFactory
from .schemas import (
    IndexBackend,
    IndexConfig,
    IndexDocument,
    IndexInfo,
    IndexStatus,
    UpdateResult,
)

logger = logging.getLogger(__name__)


class IndexManager:
    """索引管理器
    
    职责：
    1. 索引元数据管理（IndexInfo 注册表）
    2. 索引生命周期（创建、删除、状态追踪）
    3. 增量更新（文档哈希、变更检测）
    4. 持久化协调（委托给 RetrieverFactory）
    5. 启动时加载已有索引（懒加载模式）
    
    不负责：
    - 检索器实例创建（委托给 RetrieverFactory）
    - 向量存储创建（委托给 get_vector_store）
    """
    
    def __init__(
        self,
        registry_namespace: str = "rag_index_registry",
        doc_hash_namespace: str = "rag_doc_hashes",
        fields_namespace: str = "rag_index_fields",
    ):
        """初始化 IndexManager
        
        Args:
            registry_namespace: 索引注册表的 KV 存储命名空间
            doc_hash_namespace: 文档哈希的 KV 存储命名空间
            fields_namespace: 字段数据的 KV 存储命名空间
        """
        self._registry = CacheManager(registry_namespace, default_ttl=None)
        self._indexes: Dict[str, CascadeRetriever] = {}
        # 文档哈希注册表（持久化到 KV 存储）
        # 格式: {index_name: {doc_id: {"content": hash, "metadata": hash}}}
        self._doc_hashes: Dict[str, Dict[str, Dict[str, str]]] = {}
        self._doc_hash_namespace = doc_hash_namespace
        self._doc_hash_cache = CacheManager(self._doc_hash_namespace, default_ttl=None)
        self._load_doc_hashes()  # 启动时加载
        # 字段数据缓存（持久化到 KV 存储）
        # 用于在加载索引时恢复 chunks 数据
        self._fields_namespace = fields_namespace
        self._fields_cache = CacheManager(self._fields_namespace, default_ttl=None)
        # 注意：索引实例采用懒加载模式，不在初始化时加载
        # 调用 get_index() 时如果内存中没有，会尝试从持久化存储加载
    
    def _load_doc_hashes(self) -> None:
        """从 KV 存储加载文档哈希注册表"""
        try:
            # 获取所有已注册的索引
            all_indexes = self._list_registered_indexes()
            for index_name in all_indexes:
                key = f"doc_hashes:{index_name}"
                stored = self._doc_hash_cache.get(key)
                if stored:
                    self._doc_hashes[index_name] = stored
                    logger.debug(f"加载文档哈希: {index_name}, {len(stored)} 条")
        except Exception as e:
            logger.warning(f"加载文档哈希失败: {e}")
    
    def _save_doc_hashes(self, index_name: str) -> None:
        """将指定索引的文档哈希保存到 KV 存储"""
        try:
            key = f"doc_hashes:{index_name}"
            hashes = self._doc_hashes.get(index_name, {})
            self._doc_hash_cache.set(key, hashes)
            logger.debug(f"保存文档哈希: {index_name}, {len(hashes)} 条")
        except Exception as e:
            logger.warning(f"保存文档哈希失败: {e}")
    
    def _save_fields(self, index_name: str, fields: List[Dict]) -> None:
        """将索引的字段数据保存到 KV 存储
        
        用于在加载索引时恢复 chunks 数据。
        
        Args:
            index_name: 索引名称
            fields: 字段数据列表
        """
        try:
            key = f"fields:{index_name}"
            self._fields_cache.set(key, fields)
            logger.debug(f"保存字段数据: {index_name}, {len(fields)} 条")
        except Exception as e:
            logger.warning(f"保存字段数据失败: {e}")
    
    def _load_fields(self, index_name: str) -> List[Dict]:
        """从 KV 存储加载索引的字段数据
        
        Args:
            index_name: 索引名称
            
        Returns:
            字段数据列表，如果不存在返回空列表
        """
        try:
            key = f"fields:{index_name}"
            fields = self._fields_cache.get(key)
            if fields:
                logger.debug(f"加载字段数据: {index_name}, {len(fields)} 条")
                return fields
            return []
        except Exception as e:
            logger.warning(f"加载字段数据失败: {e}")
            return []
    
    def _list_registered_indexes(self) -> List[str]:
        """列出所有已注册的索引名称"""
        try:
            # 从注册表获取索引列表
            index_list = self._registry.get("_index_list")
            return index_list if index_list else []
        except Exception as e:
            logger.warning(f"列出已注册索引失败: {e}")
            return []
    
    def _register_index_name(self, name: str) -> None:
        """注册索引名称到列表"""
        try:
            index_list = self._list_registered_indexes()
            logger.info(f"注册索引名称: {name}, 当前列表: {index_list}")
            if name not in index_list:
                index_list.append(name)
                result = self._registry.set("_index_list", index_list)
                logger.info(f"注册索引名称结果: {result}, 新列表: {index_list}")
        except Exception as e:
            logger.warning(f"注册索引名称失败: {e}")
    
    def _unregister_index_name(self, name: str) -> None:
        """从列表中移除索引名称"""
        try:
            index_list = self._list_registered_indexes()
            if name in index_list:
                index_list.remove(name)
                self._registry.set("_index_list", index_list)
        except Exception as e:
            logger.warning(f"移除索引名称失败: {e}")
    
    def _load_index_from_storage(self, name: str) -> Optional[CascadeRetriever]:
        """从持久化存储加载索引（懒加载）
        
        当 get_index() 发现内存中没有索引时调用。
        
        实现流程：
        1. 从 IndexRegistry 获取 IndexInfo
        2. 如果不存在，返回 None
        3. 加载持久化的字段数据
        4. 根据 IndexInfo.config.persist_directory 加载 FAISS 索引
        5. 使用 RetrieverFactory 重建检索器实例
        6. 缓存到 _indexes[name]
        """
        # 1. 检查注册表
        index_info = self._get_index_info_from_registry(name)
        if index_info is None:
            return None
        
        # 2. 加载持久化的字段数据
        fields = self._load_fields(name)
        if not fields:
            logger.warning(f"索引 '{name}' 的字段数据不存在，检索功能可能受限")
        
        # 3. 使用 RetrieverFactory 加载已有索引
        try:
            retriever = RetrieverFactory.create_cascade_retriever(
                fields=fields,  # 使用持久化的字段数据恢复 chunks
                collection_name=name,
                persist_directory=index_info.config.persist_directory,
                force_rebuild=False,  # 不重建，加载已有向量索引
                use_batch_embedding=True,  # 如果需要重建，使用批量 embedding
            )
            
            # 4. 缓存到内存
            self._indexes[name] = retriever
            logger.info(f"从持久化存储加载索引: {name}, 字段数: {len(fields)}")
            return retriever
            
        except Exception as e:
            logger.warning(f"加载索引 '{name}' 失败: {e}")
            return None
    
    def _get_index_info_from_registry(self, name: str) -> Optional[IndexInfo]:
        """从注册表获取索引信息"""
        try:
            stored = self._registry.get(name)
            if stored is None:
                return None
            
            # 反序列化 IndexInfo
            if isinstance(stored, dict):
                return self._dict_to_index_info(stored)
            return stored
        except Exception as e:
            logger.warning(f"获取索引信息失败: {e}")
            return None
    
    def _index_info_to_dict(self, info: IndexInfo) -> Dict[str, Any]:
        """将 IndexInfo 序列化为字典"""
        return {
            "name": info.name,
            "config": {
                "backend": info.config.backend.value,
                "persist_directory": info.config.persist_directory,
                "embedding_model_id": info.config.embedding_model_id,
                "default_top_k": info.config.default_top_k,
                "score_threshold": info.config.score_threshold,
                "metadata_fields": info.config.metadata_fields,
            },
            "status": info.status.value,
            "document_count": info.document_count,
            "created_at": info.created_at.isoformat(),
            "updated_at": info.updated_at.isoformat(),
            "total_searches": info.total_searches,
            "last_search_at": info.last_search_at.isoformat() if info.last_search_at else None,
        }
    
    def _dict_to_index_info(self, data: Dict[str, Any]) -> IndexInfo:
        """从字典反序列化 IndexInfo"""
        config_data = data.get("config", {})
        config = IndexConfig(
            backend=IndexBackend(config_data.get("backend", "faiss")),
            persist_directory=config_data.get("persist_directory"),
            embedding_model_id=config_data.get("embedding_model_id"),
            default_top_k=config_data.get("default_top_k", 10),
            score_threshold=config_data.get("score_threshold", 0.0),
            metadata_fields=config_data.get("metadata_fields", []),
        )
        
        return IndexInfo(
            name=data["name"],
            config=config,
            status=IndexStatus(data.get("status", "ready")),
            document_count=data.get("document_count", 0),
            created_at=datetime.fromisoformat(data["created_at"]),
            updated_at=datetime.fromisoformat(data["updated_at"]),
            total_searches=data.get("total_searches", 0),
            last_search_at=datetime.fromisoformat(data["last_search_at"]) if data.get("last_search_at") else None,
        )
    
    def create_index(
        self,
        name: str,
        config: IndexConfig,
        documents: Optional[List[IndexDocument]] = None,
    ) -> IndexInfo:
        """创建索引
        
        实现流程：
        1. 检查索引是否已存在
        2. 将 IndexDocument 转换为 RetrieverFactory 所需的 fields 格式
        3. 调用 RetrieverFactory.create_cascade_retriever() 创建检索器
        4. 注册索引元数据到 IndexRegistry
        5. 缓存检索器实例
        6. 初始化文档哈希表（用于增量更新）
        
        Args:
            name: 索引名称
            config: 索引配置
            documents: 初始文档列表（可选）
            
        Returns:
            IndexInfo 索引信息
            
        Raises:
            IndexExistsError: 索引已存在
            IndexCreationError: 创建失败
        """
        # 1. 检查索引是否已存在
        if self._get_index_info_from_registry(name) is not None:
            raise IndexExistsError(f"索引 '{name}' 已存在")
        
        try:
            # 2. 转换文档格式
            fields = self._convert_documents_to_fields(documents)
            
            # 3. 使用 RetrieverFactory 创建检索器
            retriever = RetrieverFactory.create_cascade_retriever(
                fields=fields,
                collection_name=name,
                persist_directory=config.persist_directory,
                embedding_model_id=config.embedding_model_id,
                force_rebuild=True,  # 新建索引，强制创建
                use_batch_embedding=True,  # 使用批量 embedding 加速首次创建
            )
            
            # 4. 注册元数据
            now = datetime.now()
            index_info = IndexInfo(
                name=name,
                config=config,
                status=IndexStatus.READY,
                document_count=len(documents) if documents else 0,
                created_at=now,
                updated_at=now,
            )
            self._registry.set(name, self._index_info_to_dict(index_info))
            self._register_index_name(name)
            
            # 5. 缓存检索器实例
            self._indexes[name] = retriever
            
            # 6. 初始化文档哈希表并保存字段数据
            if documents:
                self._doc_hashes[name] = {
                    doc.id: {
                        "content": doc.content_hash,
                        "metadata": doc.metadata_hash,
                    }
                    for doc in documents
                }
                self._save_doc_hashes(name)
            
            # 7. 保存字段数据（用于加载索引时恢复 chunks）
            if fields:
                self._save_fields(name, fields)
            
            logger.info(f"创建索引成功: {name}, 文档数: {len(documents) if documents else 0}")
            return index_info
            
        except IndexExistsError:
            raise
        except Exception as e:
            logger.error(f"创建索引失败: {e}")
            raise IndexCreationError(f"创建索引 '{name}' 失败: {e}")
    
    def _convert_documents_to_fields(
        self, documents: Optional[List[IndexDocument]]
    ) -> List[Dict]:
        """将 IndexDocument 转换为 RetrieverFactory 所需的 fields 格式"""
        if not documents:
            return []
        
        fields = []
        for doc in documents:
            field = {
                "field_name": doc.id,
                "field_caption": doc.content[:50] if doc.content else "",
                "index_text": doc.content,
                **doc.metadata,
            }
            fields.append(field)
        return fields
    
    def get_index(self, name: str) -> Optional[CascadeRetriever]:
        """获取检索器实例（懒加载）
        
        如果内存中没有，尝试从持久化存储加载。
        
        Args:
            name: 索引名称
            
        Returns:
            CascadeRetriever 实例，如果不存在返回 None
        """
        if name in self._indexes:
            return self._indexes[name]
        
        # 尝试从持久化存储加载
        return self._load_index_from_storage(name)
    
    def _get_embedding_batch_size(self) -> int:
        """获取 Embedding API 的批次大小限制。
        
        从 app.yaml 的 batch_embedding.batch_size 读取，
        默认 20（智谱 API 单次最多 64 条，保守使用 20）。
        
        Returns:
            每批次最大文档数
        """
        try:
            config = get_config()
            batch_cfg = config.config.get("batch_embedding", {})
            return batch_cfg.get("batch_size", 20)
        except Exception:
            return 20
    
    def delete_index(self, name: str) -> bool:
        """删除索引
        
        Args:
            name: 索引名称
            
        Returns:
            是否删除成功
        """
        # 从内存中移除
        if name in self._indexes:
            del self._indexes[name]
        
        # 从注册表中移除
        info = self._get_index_info_from_registry(name)
        if info is None:
            return False
        
        try:
            self._registry.delete(name)
            self._unregister_index_name(name)
            
            # 删除文档哈希
            if name in self._doc_hashes:
                del self._doc_hashes[name]
            self._doc_hash_cache.delete(f"doc_hashes:{name}")
            
            # 删除字段数据
            self._fields_cache.delete(f"fields:{name}")
            
            logger.info(f"删除索引成功: {name}")
            return True
        except Exception as e:
            logger.error(f"删除索引失败: {e}")
            return False
    
    def list_indexes(self) -> List[IndexInfo]:
        """列出所有索引
        
        Returns:
            IndexInfo 列表
        """
        result = []
        for name in self._list_registered_indexes():
            info = self._get_index_info_from_registry(name)
            if info:
                result.append(info)
        return result
    
    def get_index_info(self, name: str) -> Optional[IndexInfo]:
        """获取索引信息
        
        Args:
            name: 索引名称
            
        Returns:
            IndexInfo，如果不存在返回 None
        """
        return self._get_index_info_from_registry(name)

    
    def add_documents(
        self,
        index_name: str,
        documents: List[IndexDocument],
    ) -> int:
        """添加文档（增量，自动分批）

        使用 FAISS 的 add_texts 方法实现真正的增量添加。
        自动分批处理，避免超过 Embedding API 的批次限制。

        Args:
            index_name: 索引名称
            documents: 要添加的文档列表

        Returns:
            成功添加的文档数量
        """
        retriever = self.get_index(index_name)
        if retriever is None:
            logger.warning(f"索引不存在: {index_name}")
            return 0

        # 过滤已存在的文档
        existing_hashes = self._doc_hashes.get(index_name, {})
        new_docs = [doc for doc in documents if doc.id not in existing_hashes]

        if not new_docs:
            logger.info(f"没有新文档需要添加: {index_name}")
            return 0

        # 获取向量存储并增量添加
        try:
            # 从 CascadeRetriever 获取 EmbeddingRetriever 的向量存储
            if hasattr(retriever, '_embedding') and hasattr(retriever._embedding, '_store'):
                vector_store = retriever._embedding._store

                # 准备文本和元数据
                texts = [doc.content for doc in new_docs]
                metadatas = [
                    {
                        "field_name": doc.id,
                        "field_caption": doc.content[:50] if doc.content else "",
                        **doc.metadata,
                    }
                    for doc in new_docs
                ]

                # 分批添加，避免超过 Embedding API 的批次限制（智谱限制 64 条）
                batch_size = self._get_embedding_batch_size()
                total = len(texts)
                for batch_start in range(0, total, batch_size):
                    batch_end = min(batch_start + batch_size, total)
                    batch_texts = texts[batch_start:batch_end]
                    batch_metadatas = metadatas[batch_start:batch_end]
                    vector_store.add_texts(batch_texts, metadatas=batch_metadatas)
                    logger.debug(
                        f"增量添加批次: {batch_start // batch_size + 1}, "
                        f"文档 {batch_start + 1}-{batch_end}/{total}"
                    )

                # 持久化索引
                info = self._get_index_info_from_registry(index_name)
                if info and info.config.persist_directory:
                    index_path = Path(info.config.persist_directory) / index_name
                    vector_store.save_local(str(index_path))
                    logger.debug(f"索引已持久化: {index_path}")

                logger.info(f"增量添加文档成功: {index_name}, {len(new_docs)} 条")
            else:
                logger.warning(f"无法获取向量存储，跳过增量添加: {index_name}")
        except Exception as e:
            logger.error(f"增量添加文档失败: {index_name}, {e}")

        # 更新哈希记录
        for doc in new_docs:
            existing_hashes[doc.id] = {
                "content": doc.content_hash,
                "metadata": doc.metadata_hash,
            }

        self._doc_hashes[index_name] = existing_hashes
        self._save_doc_hashes(index_name)

        # 更新索引信息
        info = self._get_index_info_from_registry(index_name)
        if info:
            info.document_count += len(new_docs)
            info.updated_at = datetime.now()
            self._registry.set(index_name, self._index_info_to_dict(info))

        return len(new_docs)

    
    def update_documents(
        self,
        index_name: str,
        documents: List[IndexDocument],
    ) -> UpdateResult:
        """更新文档（增量）
        
        增量更新策略：
        1. 比较 content_hash：变化则重新向量化
        2. 比较 metadata_hash：仅元数据变化则只更新元数据，不重新向量化
        3. 两者都没变：跳过
        
        Args:
            index_name: 索引名称
            documents: 要更新的文档列表
            
        Returns:
            UpdateResult 更新结果
        """
        result = UpdateResult()
        existing_hashes = self._doc_hashes.get(index_name, {})
        
        docs_to_reindex = []  # 需要重新向量化
        docs_to_update_metadata = []  # 仅更新元数据
        
        for doc in documents:
            old_hash_data = existing_hashes.get(doc.id)
            
            if old_hash_data is None:
                # 新文档
                docs_to_reindex.append(doc)
                result.added += 1
            else:
                old_content_hash = old_hash_data.get("content")
                old_metadata_hash = old_hash_data.get("metadata")
                
                if doc.content_hash != old_content_hash:
                    # 内容变化 → 重新向量化
                    docs_to_reindex.append(doc)
                    result.updated += 1
                elif doc.metadata_hash != old_metadata_hash:
                    # 仅元数据变化 → 更新元数据，不重新向量化
                    docs_to_update_metadata.append(doc)
                    result.metadata_only_updated += 1
                else:
                    # 完全没变
                    result.unchanged += 1
        
        # 批量重新向量化
        if docs_to_reindex:
            self._reindex_documents(index_name, docs_to_reindex)
            for doc in docs_to_reindex:
                existing_hashes[doc.id] = {
                    "content": doc.content_hash,
                    "metadata": doc.metadata_hash,
                }
        
        # 批量更新元数据（不重新向量化）
        if docs_to_update_metadata:
            self._update_metadata_only(index_name, docs_to_update_metadata)
            for doc in docs_to_update_metadata:
                existing_hashes[doc.id]["metadata"] = doc.metadata_hash
        
        self._doc_hashes[index_name] = existing_hashes
        self._save_doc_hashes(index_name)
        
        # 更新索引信息
        info = self._get_index_info_from_registry(index_name)
        if info:
            info.document_count = len(existing_hashes)
            info.updated_at = datetime.now()
            self._registry.set(index_name, self._index_info_to_dict(info))
        
        logger.info(
            f"更新文档: {index_name}, "
            f"新增={result.added}, 更新={result.updated}, "
            f"仅元数据={result.metadata_only_updated}, 未变={result.unchanged}"
        )
        return result
    
    def _reindex_documents(
        self, index_name: str, documents: List[IndexDocument]
    ) -> None:
        """重新向量化并更新索引
        
        使用 FAISS 的 add_texts 方法添加新向量。
        注意：FAISS 不支持原地更新，需要先删除再添加。
        """
        logger.debug(f"重新向量化: {index_name}, {len(documents)} 条文档")
        
        retriever = self.get_index(index_name)
        if retriever is None:
            logger.warning(f"索引不存在，跳过重新向量化: {index_name}")
            return
        
        try:
            # 从 CascadeRetriever 获取 EmbeddingRetriever 的向量存储
            if hasattr(retriever, '_embedding') and hasattr(retriever._embedding, '_store'):
                vector_store = retriever._embedding._store
                
                # 准备文本和元数据
                texts = [doc.content for doc in documents]
                metadatas = [
                    {
                        "field_name": doc.id,
                        "field_caption": doc.content[:50] if doc.content else "",
                        **doc.metadata,
                    }
                    for doc in documents
                ]
                
                # FAISS 不支持原地更新，直接添加新向量
                # 旧向量会保留，但通过 doc_id 去重可以在检索时过滤
                vector_store.add_texts(texts, metadatas=metadatas)
                
                # 持久化索引
                info = self._get_index_info_from_registry(index_name)
                if info and info.config.persist_directory:
                    index_path = Path(info.config.persist_directory) / index_name
                    vector_store.save_local(str(index_path))
                    logger.debug(f"索引已持久化: {index_path}")
                
                logger.info(f"重新向量化完成: {index_name}, {len(documents)} 条")
            else:
                logger.warning(f"无法获取向量存储，跳过重新向量化: {index_name}")
        except Exception as e:
            logger.error(f"重新向量化失败: {index_name}, {e}")
    
    def _update_metadata_only(
        self, index_name: str, documents: List[IndexDocument]
    ) -> None:
        """仅更新元数据（不重新向量化）
        
        注意：FAISS 不支持原地更新元数据，此方法仅更新内存中的 chunks 缓存。
        向量存储中的元数据需要通过重建索引来更新。
        """
        logger.debug(f"更新元数据: {index_name}, {len(documents)} 条文档")
        
        retriever = self.get_index(index_name)
        if retriever is None:
            logger.warning(f"索引不存在，跳过元数据更新: {index_name}")
            return
        
        try:
            # 更新 EmbeddingRetriever 中的 chunks 缓存
            if hasattr(retriever, '_embedding') and hasattr(retriever._embedding, '_chunks'):
                chunks = retriever._embedding._chunks
                for doc in documents:
                    if doc.id in chunks:
                        # 更新 chunk 的元数据
                        chunk = chunks[doc.id]
                        for key, value in doc.metadata.items():
                            if hasattr(chunk, key):
                                setattr(chunk, key, value)
                            elif hasattr(chunk, 'metadata'):
                                chunk.metadata[key] = value
                
                logger.info(f"元数据更新完成: {index_name}, {len(documents)} 条")
            else:
                logger.warning(f"无法获取 chunks 缓存，跳过元数据更新: {index_name}")
        except Exception as e:
            logger.error(f"元数据更新失败: {index_name}, {e}")
    
    def delete_documents(
        self,
        index_name: str,
        doc_ids: List[str],
    ) -> int:
        """删除文档
        
        Args:
            index_name: 索引名称
            doc_ids: 要删除的文档 ID 列表
            
        Returns:
            成功删除的文档数量
        """
        existing_hashes = self._doc_hashes.get(index_name, {})
        deleted_count = 0
        
        for doc_id in doc_ids:
            if doc_id in existing_hashes:
                del existing_hashes[doc_id]
                deleted_count += 1
        
        if deleted_count > 0:
            self._doc_hashes[index_name] = existing_hashes
            self._save_doc_hashes(index_name)
            
            # 更新索引信息
            info = self._get_index_info_from_registry(index_name)
            if info:
                info.document_count = len(existing_hashes)
                info.updated_at = datetime.now()
                self._registry.set(index_name, self._index_info_to_dict(info))
        
        logger.info(f"删除文档: {index_name}, 删除 {deleted_count} 条")
        return deleted_count
    
    def get_document_hash(self, index_name: str, doc_id: str) -> Optional[Dict[str, str]]:
        """获取文档哈希
        
        Args:
            index_name: 索引名称
            doc_id: 文档 ID
            
        Returns:
            {"content": hash, "metadata": hash}，如果不存在返回 None
        """
        existing_hashes = self._doc_hashes.get(index_name, {})
        return existing_hashes.get(doc_id)
