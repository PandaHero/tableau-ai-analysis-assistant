# -*- coding: utf-8 -*-
"""
向量存储模块

提供 LangChain FAISS / ChromaDB 向量存储的统一入口。

本模块依赖 infra.ai（用于批量 Embedding），因此从 kv_store.py 中分离出来，
避免 infra.ai ↔ infra.storage 的循环导入。

使用示例:
    from analytics_assistant.src.infra.storage import get_vector_store

    # FAISS
    store = get_vector_store("faiss", embeddings, "my_collection",
                             texts=["text1", "text2"])

    # ChromaDB
    store = get_vector_store("chroma", embeddings, "my_fields", "./chroma_db")
"""

import logging
from pathlib import Path
from typing import Any, Dict, List, Optional

from langchain_community.vectorstores import FAISS, Chroma

from ..ai import get_model_manager
from ..config import get_config

logger = logging.getLogger(__name__)


def _get_batch_embedding_config() -> Dict[str, Any]:
    """获取批量 Embedding 配置"""
    try:
        config = get_config()
        return config.get_batch_embedding_config()
    except Exception as e:
        logger.warning(f"获取批量 Embedding 配置失败，使用默认值: {e}")
        return {}


def get_vector_store(
    backend: str,
    embeddings: Any,
    collection_name: str,
    persist_directory: Optional[str] = None,
    texts: Optional[List[str]] = None,
    metadatas: Optional[List[Dict[str, Any]]] = None,
    use_batch_embedding: bool = True,
    batch_size: Optional[int] = None,
    max_concurrency: Optional[int] = None,
) -> Any:
    """获取向量存储实例

    Args:
        backend: 后端类型 ("faiss" 或 "chroma")
        embeddings: LangChain Embeddings 实例
        collection_name: 集合名称
        persist_directory: 持久化目录（可选）
        texts: 初始文本列表（创建新 FAISS 索引时必需）
        metadatas: 文本元数据列表（可选）
        use_batch_embedding: 是否使用批量 embedding（默认 True）
        batch_size: 每批文本数量（默认从配置读取）
        max_concurrency: 最大并发批次数（默认从配置读取）

    Returns:
        LangChain 向量存储实例（FAISS 或 Chroma）
    """
    backend = backend.lower()

    # 从配置获取默认值
    batch_config = _get_batch_embedding_config()
    actual_batch_size = (
        batch_size if batch_size is not None else batch_config.get("batch_size", 20)
    )
    actual_max_concurrency = (
        max_concurrency
        if max_concurrency is not None
        else batch_config.get("max_concurrency", 5)
    )

    if backend == "faiss":
        return _create_faiss_store(
            embeddings,
            collection_name,
            persist_directory,
            texts,
            metadatas,
            use_batch_embedding,
            actual_batch_size,
            actual_max_concurrency,
        )
    elif backend == "chroma":
        return _create_chroma_store(embeddings, collection_name, persist_directory)
    else:
        raise ValueError(f"不支持的向量存储后端: {backend}，支持: faiss, chroma")


def _create_faiss_store(
    embeddings: Any,
    collection_name: str,
    persist_directory: Optional[str],
    texts: Optional[List[str]] = None,
    metadatas: Optional[List[Dict[str, Any]]] = None,
    use_batch_embedding: bool = True,
    batch_size: int = 20,
    max_concurrency: int = 5,
) -> Any:
    """创建 FAISS 向量存储"""
    # 尝试加载已有索引
    if persist_directory:
        index_path = Path(persist_directory) / collection_name
        if index_path.exists():
            logger.info(f"加载已有 FAISS 索引: {index_path}")
            return FAISS.load_local(
                str(index_path),
                embeddings,
                allow_dangerous_deserialization=True,
            )

    # 创建新索引
    if texts:
        if use_batch_embedding and len(texts) >= batch_size:
            return _create_faiss_with_batch_embedding(
                embeddings,
                collection_name,
                persist_directory,
                texts,
                metadatas,
                batch_size,
                max_concurrency,
            )
        else:
            logger.info(
                f"创建新 FAISS 索引: {collection_name}, {len(texts)} 条文本"
            )
            store = FAISS.from_texts(texts, embeddings, metadatas=metadatas)

            if persist_directory:
                index_path = Path(persist_directory) / collection_name
                index_path.parent.mkdir(parents=True, exist_ok=True)
                store.save_local(str(index_path))
                logger.info(f"FAISS 索引已保存: {index_path}")

            return store

    logger.warning(
        f"无法创建 FAISS 索引: {collection_name}，没有提供文本数据"
    )
    return None


def _create_faiss_with_batch_embedding(
    embeddings: Any,
    collection_name: str,
    persist_directory: Optional[str],
    texts: List[str],
    metadatas: Optional[List[Dict[str, Any]]],
    batch_size: int,
    max_concurrency: int,
) -> Any:
    """使用批量 embedding 创建 FAISS 索引（优化首次创建速度）"""
    logger.info(
        f"使用批量 embedding 创建 FAISS 索引: {len(texts)} 条文本, "
        f"batch_size={batch_size}, concurrency={max_concurrency}"
    )

    try:
        manager = get_model_manager()

        vectors = manager.embed_documents_batch(
            texts=texts,
            batch_size=batch_size,
            max_concurrency=max_concurrency,
            use_cache=True,
            progress_callback=lambda done, total: (
                logger.info(f"Embedding 进度: {done}/{total}")
                if done % 50 == 0 or done == total
                else None
            ),
        )

        valid_data = []
        for i, (text, vector) in enumerate(zip(texts, vectors)):
            if vector and len(vector) > 0:
                meta = metadatas[i] if metadatas and i < len(metadatas) else {}
                valid_data.append((text, vector, meta))

        if not valid_data:
            logger.error("所有 embedding 生成失败，回退到传统方式")
            return FAISS.from_texts(texts, embeddings, metadatas=metadatas)

        if len(valid_data) < len(texts):
            logger.warning(
                f"部分 embedding 生成失败: {len(texts) - len(valid_data)} 条"
            )

        valid_texts, valid_vectors, valid_metadatas = zip(*valid_data)

        text_embedding_pairs = list(zip(valid_texts, valid_vectors))
        store = FAISS.from_embeddings(
            text_embeddings=text_embedding_pairs,
            embedding=embeddings,
            metadatas=list(valid_metadatas),
        )

        if persist_directory:
            index_path = Path(persist_directory) / collection_name
            index_path.parent.mkdir(parents=True, exist_ok=True)
            store.save_local(str(index_path))
            logger.info(f"FAISS 索引已保存: {index_path}")

        return store

    except Exception as e:
        logger.warning(f"批量 embedding 失败，回退到传统方式: {e}")
        return FAISS.from_texts(texts, embeddings, metadatas=metadatas)


def _create_chroma_store(
    embeddings: Any,
    collection_name: str,
    persist_directory: Optional[str],
) -> Any:
    """创建 ChromaDB 向量存储"""
    kwargs = {
        "collection_name": collection_name,
        "embedding_function": embeddings,
    }

    if persist_directory:
        kwargs["persist_directory"] = persist_directory

    logger.info(f"创建 Chroma 向量存储: {collection_name}")
    return Chroma(**kwargs)


__all__ = [
    "get_vector_store",
]
