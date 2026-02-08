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
import asyncio
import concurrent.futures
import hashlib
import logging
from typing import Dict, List, Optional, Any, Callable

import aiohttp
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
    
    def __new__(cls):
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
    
    def list(
        self,
        model_type: Optional[ModelType] = None,
        status: Optional[ModelStatus] = None,
        tags: Optional[List[str]] = None,
    ) -> List[ModelConfig]:
        """列出模型配置"""
        return self._registry.list(model_type=model_type, status=status, tags=tags)
    
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
    
    def get_dynamic_config_ids(self) -> List[str]:
        """获取动态添加的配置 ID 列表"""
        return list(self._dynamic_config_ids)
    
    # ═══════════════════════════════════════════════════════════════════════
    # 批量 Embedding
    # ═══════════════════════════════════════════════════════════════════════
    
    def _get_batch_embedding_defaults(self) -> Dict[str, Any]:
        """从配置获取批量 Embedding 默认参数"""
        try:
            config = get_config()
            batch_config = config.get_batch_embedding_config()
            return {
                'batch_size': batch_config.get('batch_size', 20),
                'max_concurrency': batch_config.get('max_concurrency', 5),
                'use_cache': batch_config.get('use_cache', True),
            }
        except Exception as e:
            logger.warning(f"获取批量 Embedding 配置失败，使用默认值: {e}")
            return {'batch_size': 20, 'max_concurrency': 5, 'use_cache': True}
    
    def embed_documents_batch(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[List[float]]:
        """
        批量生成文档 Embedding（同步版本）
        
        优化策略：
        1. 缓存：已计算的 embedding 直接从缓存读取
        2. 批量：将文本分批处理，每批 batch_size 条
        3. 并发：max_concurrency 个批次同时执行
        """
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.embed_documents_batch_async(
                            texts, model_id, actual_batch_size, actual_max_concurrency, 
                            actual_use_cache, progress_callback
                        )
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.embed_documents_batch_async(
                        texts, model_id, actual_batch_size, actual_max_concurrency,
                        actual_use_cache, progress_callback
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.embed_documents_batch_async(
                    texts, model_id, actual_batch_size, actual_max_concurrency,
                    actual_use_cache, progress_callback
                )
            )

    async def embed_documents_batch_async(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> List[List[float]]:
        """批量生成文档 Embedding（异步版本）"""
        if not texts:
            return []
        
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        total = len(texts)
        results: List[Optional[List[float]]] = [None] * total
        
        # 初始化缓存
        cache = None
        if actual_use_cache:
            try:
                cache = CacheManager(namespace="embedding", default_ttl=3600)
            except Exception as e:
                logger.warning(f"无法初始化 embedding 缓存: {e}")
        
        # 获取 embedding 模型配置
        config = self._resolve_config(model_id, None, ModelType.EMBEDDING)
        if not config:
            raise ValueError("No Embedding model available")
        
        def make_cache_key(text: str) -> str:
            return hashlib.md5(text.encode('utf-8')).hexdigest()
        
        # 检查缓存
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []
        
        for i, text in enumerate(texts):
            if cache:
                cache_key = make_cache_key(text)
                cached = cache.get(cache_key)
                if cached is not None:
                    results[i] = cached
                    continue
            uncached_indices.append(i)
            uncached_texts.append(text)
        
        cached_count = total - len(uncached_texts)
        if cached_count > 0:
            logger.info(f"Embedding 缓存命中: {cached_count}/{total}")
        
        if progress_callback:
            progress_callback(cached_count, total)
        
        if not uncached_texts:
            return results
        
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
        completed = cached_count
        completed_lock = asyncio.Lock()
        
        async def call_embedding_api(batch_texts: List[str]) -> List[List[float]]:
            api_base = config.api_base.rstrip('/')
            url = f"{api_base}/embeddings"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}",
            }
            
            payload = {
                "model": config.model_name,
                "input": batch_texts,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Embedding API 错误 {resp.status}: {error_text}")
                    
                    data = await resp.json()
                    embeddings_data = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
                    return [item["embedding"] for item in embeddings_data]
        
        async def process_batch(batch_texts: List[str], indices: List[int]) -> None:
            nonlocal completed
            
            async with semaphore:
                try:
                    batch_vectors = await call_embedding_api(batch_texts)
                    
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
                    logger.error(f"批量 Embedding 失败: {e}")
                    for idx in indices:
                        if results[idx] is None:
                            results[idx] = []
        
        tasks = [
            process_batch(batch_texts, indices)
            for batch_texts, indices in zip(batches, batch_indices)
        ]
        await asyncio.gather(*tasks)
        
        logger.info(f"批量 Embedding 完成: {total} 条文本")
        return results
    
    def embed_documents_batch_with_stats(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EmbeddingResult:
        """批量生成文档 Embedding，返回缓存命中信息"""
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        try:
            loop = asyncio.get_event_loop()
            if loop.is_running():
                with concurrent.futures.ThreadPoolExecutor() as executor:
                    future = executor.submit(
                        asyncio.run,
                        self.embed_documents_batch_with_stats_async(
                            texts, model_id, actual_batch_size, actual_max_concurrency, 
                            actual_use_cache, progress_callback
                        )
                    )
                    return future.result()
            else:
                return loop.run_until_complete(
                    self.embed_documents_batch_with_stats_async(
                        texts, model_id, actual_batch_size, actual_max_concurrency,
                        actual_use_cache, progress_callback
                    )
                )
        except RuntimeError:
            return asyncio.run(
                self.embed_documents_batch_with_stats_async(
                    texts, model_id, actual_batch_size, actual_max_concurrency,
                    actual_use_cache, progress_callback
                )
            )
    
    async def embed_documents_batch_with_stats_async(
        self,
        texts: List[str],
        model_id: Optional[str] = None,
        batch_size: int = None,
        max_concurrency: int = None,
        use_cache: bool = None,
        progress_callback: Optional[Callable[[int, int], None]] = None,
    ) -> EmbeddingResult:
        """批量生成文档 Embedding，返回缓存命中信息（异步版本）"""
        if not texts:
            return EmbeddingResult(vectors=[], cache_hits=0, cache_misses=0)
        
        defaults = self._get_batch_embedding_defaults()
        actual_batch_size = batch_size if batch_size is not None else defaults['batch_size']
        actual_max_concurrency = max_concurrency if max_concurrency is not None else defaults['max_concurrency']
        actual_use_cache = use_cache if use_cache is not None else defaults['use_cache']
        
        total = len(texts)
        results: List[Optional[List[float]]] = [None] * total
        cache_hits = 0
        cache_misses = 0
        
        cache = None
        if actual_use_cache:
            try:
                cache = CacheManager(namespace="embedding", default_ttl=86400)
            except Exception as e:
                logger.warning(f"无法初始化 embedding 缓存: {e}")
        
        config = self._resolve_config(model_id, None, ModelType.EMBEDDING)
        if not config:
            raise ValueError("No Embedding model available")
        
        def make_cache_key(text: str) -> str:
            return hashlib.md5(text.encode('utf-8')).hexdigest()
        
        uncached_indices: List[int] = []
        uncached_texts: List[str] = []
        
        for i, text in enumerate(texts):
            if cache:
                cache_key = make_cache_key(text)
                cached = cache.get(cache_key)
                if cached is not None:
                    results[i] = cached
                    cache_hits += 1
                    continue
            uncached_indices.append(i)
            uncached_texts.append(text)
        
        cache_misses = len(uncached_texts)
        
        if cache_hits > 0:
            logger.info(f"Embedding 缓存命中: {cache_hits}/{total}")
        
        if progress_callback:
            progress_callback(cache_hits, total)
        
        if not uncached_texts:
            return EmbeddingResult(vectors=results, cache_hits=cache_hits, cache_misses=cache_misses)
        
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
        
        async def call_embedding_api(batch_texts: List[str]) -> List[List[float]]:
            api_base = config.api_base.rstrip('/')
            url = f"{api_base}/embeddings"
            
            headers = {
                "Content-Type": "application/json",
                "Authorization": f"Bearer {config.api_key}",
            }
            
            payload = {
                "model": config.model_name,
                "input": batch_texts,
            }
            
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers=headers, timeout=aiohttp.ClientTimeout(total=60)) as resp:
                    if resp.status != 200:
                        error_text = await resp.text()
                        raise Exception(f"Embedding API 错误 {resp.status}: {error_text}")
                    
                    data = await resp.json()
                    embeddings_data = sorted(data.get("data", []), key=lambda x: x.get("index", 0))
                    return [item["embedding"] for item in embeddings_data]
        
        async def process_batch(batch_texts: List[str], indices: List[int]) -> None:
            nonlocal completed
            
            async with semaphore:
                try:
                    batch_vectors = await call_embedding_api(batch_texts)
                    
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
                    logger.error(f"批量 Embedding 失败: {e}")
                    for idx in indices:
                        if results[idx] is None:
                            results[idx] = []
        
        tasks = [
            process_batch(batch_texts, indices)
            for batch_texts, indices in zip(batches, batch_indices)
        ]
        await asyncio.gather(*tasks)
        
        logger.info(f"批量 Embedding 完成: {total} 条文本 (缓存命中: {cache_hits}, 未命中: {cache_misses})")
        return EmbeddingResult(vectors=results, cache_hits=cache_hits, cache_misses=cache_misses)


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
    texts: List[str],
    model_id: Optional[str] = None,
    batch_size: int = None,
    max_concurrency: int = None,
    use_cache: bool = None,
    progress_callback: Optional[Callable[[int, int], None]] = None,
) -> List[List[float]]:
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
