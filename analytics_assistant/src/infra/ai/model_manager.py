# -*- coding: utf-8 -*-
"""
ModelManager - 统一的模型管理器（门面类）

设计目标：
1. 统一接口：屏蔽不同提供商的 API 差异
2. 灵活配置：支持多模型、多提供商、动态切换
3. 智能路由：根据任务类型自动选择最优模型
4. 可扩展性：轻松添加新的模型提供商
5. 成本优化：支持模型降级和成本控制

架构设计（门面模式）：
- ModelManager: 门面类，组合以下模块
- ModelRegistry: 模型配置 CRUD 操作
- ModelFactory: 模型实例创建
- TaskRouter: 任务路由
- ModelPersistence: 配置持久化

使用示例：
    from analytics_assistant.src.infra.ai import get_model_manager
    
    manager = get_model_manager()
    
    # 使用默认 LLM
    llm = manager.create_llm()
    
    # 使用任务类型路由
    llm = manager.create_llm(task_type=TaskType.SEMANTIC_PARSING)
    
    # 指定模型并覆盖参数
    llm = manager.create_llm(
        model_id="qwen3-local",
        temperature=0.8,
        enable_json_mode=True
    )
"""
from __future__ import annotations

import asyncio
import concurrent.futures
import hashlib
import logging
import threading
from typing import Any, Callable, Optional

from langchain_core.language_models import BaseChatModel
from langchain_core.embeddings import Embeddings

from .models import (
    EmbeddingResult,
    ModelType,
    ModelStatus,
    TaskType,
    ModelConfig,
    ModelCreateRequest,
    ModelUpdateRequest,
)
from .model_registry import ModelRegistry
from .model_factory import ModelFactory
from .model_router import TaskRouter
from .model_persistence import ModelPersistence
from ..config import get_config
from ..storage import CacheManager

logger = logging.getLogger(__name__)

class ModelManager:
    """
    模型管理器（门面类）
    
    组合以下模块提供统一接口：
    - ModelRegistry: 模型配置 CRUD 操作
    - ModelFactory: 模型实例创建
    - TaskRouter: 任务路由
    - ModelPersistence: 配置持久化
    
    持久化策略：
    - YAML 配置文件中的模型：只读，不持久化（重启后从 YAML 重新加载）
    - 通过 API 动态添加的模型：持久化到 SQLite（重启后自动恢复）
    """
    
    _instance = None
    _lock = threading.Lock()  # 双重检查锁定，确保线程安全
    
    def __new__(cls):
        if cls._instance is None:
            with cls._lock:
                # 双重检查：在获取锁后再次检查，避免竞态条件
                if cls._instance is None:
                    cls._instance = super().__new__(cls)
        return cls._instance
    
    def __init__(self):
        if not hasattr(self, '_initialized'):
            self._initialized = True
            
            # 初始化子模块
            self._registry = ModelRegistry()
            self._factory = ModelFactory()
            self._router = TaskRouter(self._registry)
            self._persistence = ModelPersistence()
            
            # 记录动态添加的配置 ID
            self._dynamic_config_ids: set = set()
            
            logger.info("ModelManager initialized (facade pattern)")
            
            # 从统一配置文件加载配置
            self._load_from_unified_config()
            
            # 从持久化存储加载动态配置
            self._load_from_persistence()
    
    # ═══════════════════════════════════════════════════════════════════════
    # 配置加载
    # ═══════════════════════════════════════════════════════════════════════
    
    def _load_from_unified_config(self):
        """从统一配置文件加载配置"""
        try:
            app_config = get_config()
            
            # 加载 LLM 模型
            llm_models = app_config.get_llm_models()
            for model_data in llm_models:
                try:
                    self._registry.create_from_dict(model_data)
                except Exception as e:
                    logger.warning(f"加载 LLM 模型配置失败 {model_data.get('id')}: {e}")
            
            # 加载 Embedding 模型
            embedding_models = app_config.get_embedding_models()
            for model_data in embedding_models:
                try:
                    self._registry.create_from_dict(model_data)
                except Exception as e:
                    logger.warning(f"加载 Embedding 模型配置失败 {model_data.get('id')}: {e}")
            
            logger.info(f"从统一配置加载了 {len(self._registry.get_all_ids())} 个模型配置")
            
        except Exception as e:
            logger.warning(f"统一配置加载失败: {e}")
            logger.info("将使用空配置，请确保 config/app.yaml 存在")
    
    def _load_from_persistence(self):
        """从持久化存储加载动态配置"""
        if not self._persistence.enabled:
            return
        
        try:
            stored_data = self._persistence.load()
            
            for config_data in stored_data:
                try:
                    config_id = config_data.get("id")
                    
                    # 跳过已存在的配置（YAML 配置优先）
                    if self._registry.get(config_id):
                        logger.debug(f"跳过已存在的配置: {config_id}")
                        continue
                    
                    self._registry.create_from_dict(config_data)
                    self._dynamic_config_ids.add(config_id)
                    
                except Exception as e:
                    logger.warning(f"加载持久化配置失败: {e}")
            
            if self._dynamic_config_ids:
                logger.info(f"从持久化存储加载了 {len(self._dynamic_config_ids)} 个动态配置")
            
        except Exception as e:
            logger.warning(f"加载持久化配置失败: {e}")
    
    def _save_to_persistence(self):
        """保存动态配置到持久化存储"""
        if not self._persistence.enabled:
            return
        
        configs = [
            self._registry.get(config_id)
            for config_id in self._dynamic_config_ids
            if self._registry.get(config_id)
        ]
        self._persistence.save(configs)
    
    # ═══════════════════════════════════════════════════════════════════════
    # CRUD 操作（委托给 ModelRegistry）
    # ═══════════════════════════════════════════════════════════════════════
    
    def create(self, request: ModelCreateRequest) -> ModelConfig:
        """创建新模型配置（动态添加，支持持久化）"""
        config = self._registry.create(request)
        self._dynamic_config_ids.add(config.id)
        self._save_to_persistence()
        return config
    
    def get(self, model_id: str) -> Optional[ModelConfig]:
        """获取模型配置"""
        return self._registry.get(model_id)
    
    def list_configs(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[list[str]] = None,
    ) -> list[ModelConfig]:
        """列出模型配置"""
        return self._registry.list_configs(model_type=model_type, status=status, tags=tags)
    
    def update(self, model_id: str, request: ModelUpdateRequest) -> Optional[ModelConfig]:
        """更新模型配置"""
        config = self._registry.update(model_id, request)
        if config and model_id in self._dynamic_config_ids:
            self._save_to_persistence()
        return config
    
    def delete(self, model_id: str) -> bool:
        """删除模型配置"""
        result = self._registry.delete(model_id)
        if result and model_id in self._dynamic_config_ids:
            self._dynamic_config_ids.discard(model_id)
            self._save_to_persistence()
        return result
    
    # ═══════════════════════════════════════════════════════════════════════
    # 默认模型管理（委托给 ModelRegistry）
    # ═══════════════════════════════════════════════════════════════════════
    
    def get_default(self, model_type: ModelType) -> Optional[ModelConfig]:
        """获取默认模型"""
        return self._registry.get_default(model_type)
    
    def set_default(self, model_id: str) -> bool:
        """设置默认模型"""
        return self._registry.set_default(model_id)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 模型实例创建（委托给 ModelFactory + TaskRouter）
    # ═══════════════════════════════════════════════════════════════════════
    
    def create_llm(
        self,
        model_id: Optional[str] = None,
        task_type: Optional[TaskType] = None,
        **kwargs
    ) -> BaseChatModel:
        """
        创建 LLM 实例
        
        Args:
            model_id: 指定模型 ID（优先级最高）
            task_type: 任务类型（用于智能路由）
            **kwargs: 运行时参数
                - temperature: 温度参数
                - max_tokens: 最大 token 数
                - enable_json_mode: 是否启用 JSON Mode
                - streaming: 是否启用流式输出
        
        Returns:
            LangChain BaseChatModel 实例
        """
        config = self._resolve_config(model_id, task_type, ModelType.LLM)
        if not config:
            raise ValueError("No LLM model available")
        
        return self._factory.create_llm(config, **kwargs)
    
    def create_embedding(
        self,
        model_id: Optional[str] = None,
        **kwargs
    ) -> Embeddings:
        """创建 Embedding 实例"""
        config = self._resolve_config(model_id, None, ModelType.EMBEDDING)
        if not config:
            raise ValueError("No Embedding model available")
        
        return self._factory.create_embedding(config, **kwargs)
    
    def _resolve_config(
        self,
        model_id: Optional[str],
        task_type: Optional[TaskType],
        model_type: ModelType,
    ) -> Optional[ModelConfig]:
        """解析模型配置
        
        优先级：model_id > task_type 路由 > 默认模型
        """
        if model_id:
            config = self._registry.get(model_id)
            if not config:
                raise ValueError(f"Model {model_id} not found")
            return config
        
        if task_type:
            return self._router.route(task_type, model_type)
        
        return self._registry.get_default(model_type)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 持久化管理
    # ═══════════════════════════════════════════════════════════════════════
    
    def enable_persistence(self, enable: bool = True):
        """启用或禁用持久化"""
        self._persistence.enable(enable)
    
    def is_persistence_enabled(self) -> bool:
        """检查持久化是否启用"""
        return self._persistence.enabled
    
    def get_dynamic_config_ids(self) -> list[str]:
        """获取动态添加的配置 ID 列表"""
        return list(self._dynamic_config_ids)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 批量 Embedding
    # ═══════════════════════════════════════════════════════════════════════
    
    def _get_batch_embedding_defaults(self) -> dict[str, Any]:
        """从配置获取批量 Embedding 默认参数"""
        try:
            config = get_config()
            batch_config = config.get_batch_embedding_config()
            # 统一从 ai.embedding_cache_ttl 读取缓存 TTL，batch_embedding.cache_ttl 作为 fallback
            ai_config = config.config.get("ai", {})
            cache_ttl = ai_config.get(
                "embedding_cache_ttl",
                batch_config.get("cache_ttl", 3600),
            )
            return {
                "batch_size": batch_config.get("batch_size", 20),
                "max_concurrency": batch_config.get("max_concurrency", 5),
                "use_cache": batch_config.get("use_cache", True),
                "cache_ttl": cache_ttl,
            }
        except Exception as e:
            logger.warning(f"获取批量 Embedding 配置失败，使用默认值: {e}")
            return {"batch_size": 20, "max_concurrency": 5, "use_cache": True, "cache_ttl": 3600}

    async def _embed_batch_core_async(
        self,
        texts: list[str],
        model_id: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        use_cache: Optional[bool] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> tuple[list[Optional[list[float]]], int, int]:
        """批量 Embedding 核心逻辑，返回 (results, cache_hits, cache_misses)。

        使用 ModelFactory.create_embedding() 创建 LangChain Embeddings 实例，
        替代直接 aiohttp 调用，与框架对齐。

        Args:
            texts: 待向量化的文本列表。
            model_id: 指定 Embedding 模型 ID。
            batch_size: 每批文本数量。
            max_concurrency: 最大并发批次数。
            use_cache: 是否启用缓存。
            progress_callback: 进度回调 (completed, total)。

        Returns:
            (results, cache_hits, cache_misses) 三元组。
        """
        if not texts:
            return [], 0, 0

        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults["batch_size"]
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults["max_concurrency"]
        actual_use_cache = use_cache if use_cache is not None else defaults["use_cache"]
        cache_ttl = defaults["cache_ttl"]

        total = len(texts)
        results: list[Optional[list[float]]] = [None] * total

        # 初始化缓存，统一使用 ai.embedding_cache_ttl
        cache = None
        if actual_use_cache:
            try:
                cache = CacheManager(namespace="embedding", default_ttl=cache_ttl)
            except Exception as e:
                logger.warning(f"无法初始化 embedding 缓存: {e}")

        def make_cache_key(text: str) -> str:
            return hashlib.md5(text.encode("utf-8")).hexdigest()

        # 检查缓存
        uncached_indices: list[int] = []
        uncached_texts: list[str] = []

        for i, text in enumerate(texts):
            if cache:
                cache_key = make_cache_key(text)
                cached = cache.get(cache_key)
                if cached is not None:
                    results[i] = cached
                    continue
            uncached_indices.append(i)
            uncached_texts.append(text)

        cache_hits = total - len(uncached_texts)
        cache_misses = len(uncached_texts)

        if cache_hits > 0:
            logger.info(f"Embedding 缓存命中: {cache_hits}/{total}")

        if progress_callback:
            progress_callback(cache_hits, total)

        if not uncached_texts:
            return results, cache_hits, cache_misses

        # 使用 ModelFactory 创建 LangChain Embeddings 实例，替代直接 aiohttp 调用
        embedding_instance = self.create_embedding(model_id=model_id)

        # 分批处理
        batches = [
            uncached_texts[i:i + actual_batch_size]
            for i in range(0, len(uncached_texts), actual_batch_size)
        ]
        batch_indices = [
            uncached_indices[i:i + actual_batch_size]
            for i in range(0, len(uncached_indices), actual_batch_size)
        ]

        logger.info(f"开始批量 Embedding: {len(uncached_texts)} 条文本, {len(batches)} 批次")

        semaphore = asyncio.Semaphore(actual_max_concurrency)
        completed = cache_hits
        completed_lock = asyncio.Lock()

        async def process_batch(batch_texts: list[str], indices: list[int]) -> None:
            nonlocal completed

            async with semaphore:
                try:
                    # 使用 LangChain Embeddings 异步接口
                    batch_vectors = await embedding_instance.aembed_documents(batch_texts)

                    for idx, text, vector in zip(indices, batch_texts, batch_vectors):
                        results[idx] = vector
                        if cache:
                            cache_key = make_cache_key(text)
                            cache.set(cache_key, vector)

                    async with completed_lock:
                        completed += len(batch_texts)
                        if progress_callback:
                            progress_callback(completed, total)

                except Exception as e:
                    logger.error(
                        f"批量 Embedding 失败: batch_size={len(batch_texts)}, error={e}"
                    )
                    for idx in indices:
                        if results[idx] is None:
                            results[idx] = []

        tasks = [
            process_batch(batch_texts, indices)
            for batch_texts, indices in zip(batches, batch_indices)
        ]
        await asyncio.gather(*tasks)

        logger.info(
            f"批量 Embedding 完成: {total} 条文本 "
            f"(缓存命中: {cache_hits}, 未命中: {cache_misses})"
        )
        return results, cache_hits, cache_misses

    def _run_async_in_sync(self, coro) -> Any:
        """在同步上下文中运行异步协程的辅助方法"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(asyncio.run, coro)
                    return future.result()
            else:
                return loop.run_until_complete(coro)
        except RuntimeError:
            return asyncio.run(coro)

    def embed_documents_batch(
        self,
        texts: list[str],
        model_id: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        use_cache: Optional[bool] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        """批量生成文档 Embedding（同步版本）

        优化策略：
        1. 缓存：已计算的 embedding 直接从缓存读取
        2. 批量：将文本分批处理，每批 batch_size 条
        3. 并发：max_concurrency 个批次同时执行
        """
        return self._run_async_in_sync(
            self.embed_documents_batch_async(
                texts, model_id, batch_size, max_concurrency,
                use_cache, progress_callback,
            )
        )

    async def embed_documents_batch_async(
        self,
        texts: list[str],
        model_id: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        use_cache: Optional[bool] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> list[list[float]]:
        """批量生成文档 Embedding（异步版本）"""
        results, _, _ = await self._embed_batch_core_async(
            texts, model_id, batch_size, max_concurrency,
            use_cache, progress_callback,
        )
        return results

    def embed_documents_batch_with_stats(
        self,
        texts: list[str],
        model_id: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        use_cache: Optional[bool] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EmbeddingResult:
        """批量生成文档 Embedding，返回缓存命中信息"""
        return self._run_async_in_sync(
            self.embed_documents_batch_with_stats_async(
                texts, model_id, batch_size, max_concurrency,
                use_cache, progress_callback,
            )
        )

    async def embed_documents_batch_with_stats_async(
        self,
        texts: list[str],
        model_id: Optional[str] = None,
        batch_size: Optional[int] = None,
        max_concurrency: Optional[int] = None,
        use_cache: Optional[bool] = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EmbeddingResult:
        """批量生成文档 Embedding，返回缓存命中信息（异步版本）"""
        results, cache_hits, cache_misses = await self._embed_batch_core_async(
            texts, model_id, batch_size, max_concurrency,
            use_cache, progress_callback,
        )
        return EmbeddingResult(
            vectors=results, cache_hits=cache_hits, cache_misses=cache_misses,
        )

# ═══════════════════════════════════════════════════════════════════════════
# 全局单例访问
# ═══════════════════════════════════════════════════════════════════════════

_model_manager_instance: Optional[ModelManager] = None

def get_model_manager() -> ModelManager:
    """获取 ModelManager 单例实例"""
    global _model_manager_instance
    if _model_manager_instance is None:
        _model_manager_instance = ModelManager()
    return _model_manager_instance

def get_embeddings(model_id: Optional[str] = None, **kwargs) -> Embeddings:
    """获取 Embedding 实例（便捷函数）"""
    manager = get_model_manager()
    return manager.create_embedding(model_id=model_id, **kwargs)

def embed_documents_batch(
    texts: list[str],
    model_id: Optional[str] = None,
    batch_size: Optional[int] = None,
    max_concurrency: Optional[int] = None,
    use_cache: Optional[bool] = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> list[list[float]]:
    """批量生成文档 Embedding（便捷函数）"""
    manager = get_model_manager()
    return manager.embed_documents_batch(
        texts=texts,
        model_id=model_id,
        batch_size=batch_size,
        max_concurrency=max_concurrency,
        use_cache=use_cache,
        progress_callback=progress_callback,
    )

__all__ = [
    "ModelManager",
    "get_model_manager",
    "get_embeddings",
    "embed_documents_batch",
]
