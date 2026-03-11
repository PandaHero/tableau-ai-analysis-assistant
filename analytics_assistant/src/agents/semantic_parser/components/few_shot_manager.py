# -*- coding: utf-8 -*-
"""
FewShotManager 组件 - Few-shot 示例管理

功能：
- 检索相关示例：基于向量相似度检索 0-3 个相关示例
- 添加示例：将成功的查询添加为示例
- 用户接受优先：接受过的示例排名更高
- 持久化存储：使用 SqliteStore 存储示例

存储后端：LangGraph SqliteStore（复用现有基础设施）

RAG 服务集成：
- 使用 RAGService.embedding 进行向量化
- 使用 RAGService.index 管理示例索引
- 使用 RAGService.retrieval 进行示例检索

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.few_shot_manager

Requirements: 4.1-4.5 - FewShotManager 示例管理
"""

import asyncio
import logging
import uuid
from datetime import datetime
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import get_kv_store
from analytics_assistant.src.infra.rag import get_rag_service, cosine_similarity
from analytics_assistant.src.infra.rag.schemas import IndexConfig, IndexDocument
from analytics_assistant.src.infra.rag.exceptions import IndexNotFoundError

from ..schemas.intermediate import FewShotExample

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> dict[str, Any]:
    """获取 few_shot_manager 配置。"""
    try:
        config = get_config()
        return config.config.get("semantic_parser", {}).get("few_shot_manager", {})
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}

# ═══════════════════════════════════════════════════════════════════════════
# FewShotManager 组件
# ═══════════════════════════════════════════════════════════════════════════

class FewShotManager:
    """Few-shot 示例管理器。
    
    功能：
    - 检索相关示例：基于向量相似度检索 0-3 个相关示例
    - 添加示例：将成功的查询添加为示例
    - 用户接受优先：接受过的示例排名更高
    - 持久化存储：使用 SqliteStore 存储示例
    
    RAG 服务集成：
    - 使用 RAGService.embedding 进行向量化
    - 使用 RAGService.index 管理示例索引
    - 使用 RAGService.retrieval 进行示例检索
    
    存储结构：
    - namespace: ("semantic_parser", "few_shot", datasource_luid)
    - key: example_id
    - value: FewShotExample.model_dump()
    
    排序策略：
    - 首先按 accepted_count 降序（用户接受过的优先）
    - 然后按相似度降序
    
    配置来源：app.yaml -> semantic_parser.few_shot_manager
    
    Examples:
        >>> manager = FewShotManager()
        >>> 
        >>> # 检索示例
        >>> examples = await manager.retrieve(
        ...     question="上个月各地区的销售额",
        ...     datasource_luid="ds_123",
        ...     top_k=3,
        ... )
        >>> 
        >>> # 添加示例
        >>> await manager.add(FewShotExample(
        ...     id="ex_001",
        ...     question="上个月各地区的销售额",
        ...     ...
        ... ))
        >>> 
        >>> # 更新接受次数
        >>> await manager.update_accepted_count("ex_001")
    """
    
    # 缓存命名空间前缀（固定值，不需要配置）
    NAMESPACE_PREFIX = ("semantic_parser", "few_shot")
    
    # 索引名称前缀
    INDEX_PREFIX = "few_shot_"
    
    # 默认配置（作为 fallback）
    _DEFAULT_MAX_EXAMPLES = 3
    _DEFAULT_SIMILARITY_THRESHOLD = 0.8
    _DEFAULT_ACCEPTED_PRIORITY_BOOST = 0.2
    _DEFAULT_MAX_EXAMPLES_PER_DATASOURCE = 100
    
    def __init__(
        self,
        store: Optional[Any] = None,
        default_top_k: Optional[int] = None,
        max_examples_per_datasource: Optional[int] = None,
        similarity_threshold: Optional[float] = None,
    ):
        """初始化 FewShotManager。
        
        Args:
            store: LangGraph SqliteStore 实例，None 则使用全局实例
            default_top_k: 默认返回示例数（None 从配置读取）
            max_examples_per_datasource: 每个数据源最多存储的示例数（None 从配置读取）
            similarity_threshold: 相似度阈值（None 从配置读取）
        """
        # 直接初始化，不延迟
        if store is None:
            store = get_kv_store()
        self._store = store
        
        # 使用 RAGService
        self._rag_service = get_rag_service()
        
        # 从配置加载参数
        self._load_config(default_top_k, max_examples_per_datasource, similarity_threshold)
    
    def _load_config(
        self,
        default_top_k: Optional[int],
        max_examples_per_datasource: Optional[int],
        similarity_threshold: Optional[float],
    ) -> None:
        """从配置加载参数。"""
        config = _get_config()
        
        self.default_top_k = (
            default_top_k
            if default_top_k is not None
            else config.get("max_examples", self._DEFAULT_MAX_EXAMPLES)
        )
        self.max_examples_per_datasource = (
            max_examples_per_datasource
            if max_examples_per_datasource is not None
            else config.get("max_examples_per_datasource", self._DEFAULT_MAX_EXAMPLES_PER_DATASOURCE)
        )
        self.similarity_threshold = (
            similarity_threshold
            if similarity_threshold is not None
            else config.get("similarity_threshold", self._DEFAULT_SIMILARITY_THRESHOLD)
        )
    
    def _make_namespace(self, datasource_luid: str) -> tuple:
        """生成存储命名空间。
        
        Args:
            datasource_luid: 数据源 ID
        
        Returns:
            命名空间元组
        """
        return (*self.NAMESPACE_PREFIX, datasource_luid)
    
    def _get_index_name(self, datasource_luid: str) -> str:
        """获取索引名称。
        
        Args:
            datasource_luid: 数据源 ID
            
        Returns:
            索引名称
        """
        return f"{self.INDEX_PREFIX}{datasource_luid}"
    
    async def retrieve(
        self,
        question: str,
        datasource_luid: str,
        top_k: Optional[int] = None,
    ) -> list[FewShotExample]:
        """检索相关示例。
        
        检索策略：
        1. 使用 RAGService 进行向量相似度搜索
        2. 过滤相似度 < threshold 的结果
        3. 按 (accepted_count DESC, similarity DESC) 排序
        4. 返回 top_k 个示例
        
        Args:
            question: 用户问题
            datasource_luid: 数据源 ID
            top_k: 返回示例数，None 使用默认值（最多 3 个）
        
        Returns:
            FewShotExample 列表（0-3 个）
        """
        if self._store is None:
            logger.debug("FewShotManager 存储不可用，返回空列表")
            return []
        
        top_k = min(top_k or self.default_top_k, 3)  # 最多 3 个
        namespace = self._make_namespace(datasource_luid)
        index_name = self._get_index_name(datasource_luid)
        
        try:
            # 尝试使用 RAGService 进行向量检索
            try:
                search_results = await self._rag_service.retrieval.search_async(
                    index_name=index_name,
                    query=question,
                    top_k=top_k * 2,  # 检索更多以便过滤
                    score_threshold=self.similarity_threshold,
                )
                
                if search_results:
                    # 从搜索结果中并行获取完整示例
                    get_tasks = [
                        self.get(result.doc_id, datasource_luid)
                        for result in search_results
                    ]
                    fetched = await asyncio.gather(*get_tasks, return_exceptions=True)

                    scored_examples: list[tuple] = []
                    for result, example in zip(search_results, fetched):
                        if isinstance(example, BaseException) or example is None:
                            continue
                        scored_examples.append((example, result.score))
                    
                    if scored_examples:
                        # 排序：首先按 accepted_count 降序，然后按相似度降序
                        scored_examples.sort(
                            key=lambda x: (x[0].accepted_count, x[1]),
                            reverse=True
                        )
                        
                        result = [ex for ex, _ in scored_examples[:top_k]]
                        
                        logger.info(
                            f"FewShotManager 检索到 {len(result)} 个示例 (RAG): "
                            f"question='{question[:20]}...', datasource={datasource_luid}"
                        )
                        
                        return result
                        
            except IndexNotFoundError:
                logger.debug(f"FewShotManager 索引不存在: {index_name}，回退到全量搜索")
            except Exception as e:
                logger.warning(f"FewShotManager RAG 检索失败: {e}，回退到全量搜索")
            
            # 回退：获取该数据源的所有示例并手动计算相似度
            items = self._store.search(namespace, limit=self.max_examples_per_datasource)
            
            if not items:
                logger.debug(f"FewShotManager 无示例: datasource={datasource_luid}")
                return []
            
            # 解析示例
            examples: list[FewShotExample] = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    example = FewShotExample.model_validate(item.value)
                    examples.append(example)
                except Exception as e:
                    logger.warning(f"解析示例失败: {e}")
                    continue
            
            if not examples:
                return []
            
            # 使用 RAGService.embedding 计算问题的 embedding
            try:
                question_embedding = self._rag_service.embedding.embed_query(question)
            except Exception as e:
                logger.warning(f"计算 question embedding 失败: {e}")
                # 回退到按 accepted_count 排序
                examples.sort(key=lambda x: x.accepted_count, reverse=True)
                return examples[:top_k]
            
            # 计算相似度并排序
            scored_examples: list[tuple] = []
            for example in examples:
                if example.question_embedding:
                    similarity = cosine_similarity(
                        question_embedding,
                        example.question_embedding
                    )
                else:
                    # 无 embedding：尝试即时计算
                    try:
                        example.question_embedding = self._rag_service.embedding.embed_query(
                            example.question
                        )
                        similarity = cosine_similarity(
                            question_embedding,
                            example.question_embedding
                        )
                    except Exception:
                        # 无法计算 embedding，已被接受过的示例仍保留
                        similarity = self.similarity_threshold if example.accepted_count > 0 else 0.0
                
                # 只保留相似度 >= threshold 的示例
                if similarity >= self.similarity_threshold:
                    scored_examples.append((example, similarity))
            
            if not scored_examples:
                logger.debug(f"FewShotManager 无相似示例: question='{question[:20]}...'")
                return []
            
            # 排序：首先按 accepted_count 降序，然后按相似度降序
            scored_examples.sort(
                key=lambda x: (x[0].accepted_count, x[1]),
                reverse=True
            )
            
            result = [ex for ex, _ in scored_examples[:top_k]]
            
            logger.info(
                f"FewShotManager 检索到 {len(result)} 个示例: "
                f"question='{question[:20]}...', datasource={datasource_luid}"
            )
            
            return result
            
        except Exception as e:
            logger.error(f"FewShotManager retrieve 失败: {e}")
            return []
    
    async def add(self, example: FewShotExample) -> bool:
        """添加示例。
        
        如果示例数超过 max_examples_per_datasource，
        删除 accepted_count 最低且最旧的示例。
        
        同时更新 RAG 索引以支持向量检索。
        
        Args:
            example: FewShotExample 实例
        
        Returns:
            是否成功
        """
        if self._store is None:
            logger.warning("FewShotManager 存储不可用，无法添加示例")
            return False
        
        namespace = self._make_namespace(example.datasource_luid)
        
        try:
            # 如果没有 ID，生成一个
            if not example.id:
                example.id = f"ex_{uuid.uuid4().hex[:12]}"
            
            # 如果没有 embedding，使用 RAGService 计算一个
            if example.question_embedding is None:
                try:
                    example.question_embedding = self._rag_service.embedding.embed_query(example.question)
                except Exception as e:
                    logger.warning(f"计算示例 embedding 失败: {e}")
            
            # 更新时间戳
            example.updated_at = datetime.now()
            
            # 检查是否需要淘汰旧示例
            await self._evict_if_needed(example.datasource_luid)
            
            # 存储示例
            self._store.put(namespace, example.id, example.model_dump())
            
            # 更新 RAG 索引
            await self._update_rag_index(example)
            
            logger.info(
                f"FewShotManager 已添加示例: id={example.id}, "
                f"question='{example.question[:20]}...'"
            )
            return True
            
        except Exception as e:
            logger.error(f"FewShotManager add 失败: {e}")
            return False
    
    async def _update_rag_index(self, example: FewShotExample) -> None:
        """更新 RAG 索引。
        
        Args:
            example: FewShotExample 实例
        """
        index_name = self._get_index_name(example.datasource_luid)
        
        try:
            # 创建索引文档
            doc = IndexDocument(
                id=example.id,
                content=example.question,
                metadata={
                    "datasource_luid": example.datasource_luid,
                    "accepted_count": example.accepted_count,
                },
            )
            
            # 检查索引是否存在
            existing_index = self._rag_service.index.get_index(index_name)
            
            if existing_index is None:
                # 创建新索引
                config = self._get_index_config()
                self._rag_service.index.create_index(
                    name=index_name,
                    config=config,
                    documents=[doc],
                )
                logger.debug(f"FewShotManager 创建索引: {index_name}")
            else:
                # 添加文档到现有索引
                self._rag_service.index.add_documents(index_name, [doc])
                logger.debug(f"FewShotManager 更新索引: {index_name}")
                
        except Exception as e:
            logger.warning(f"FewShotManager 更新 RAG 索引失败: {e}")
    
    def _get_index_config(self) -> IndexConfig:
        """获取索引配置。"""
        rag_config = self._rag_service.get_config()
        index_config = rag_config.get("index", {})
        return IndexConfig(
            persist_directory=index_config.get("persist_directory"),
            default_top_k=self.default_top_k,
        )
    
    async def update_accepted_count(self, example_id: str, datasource_luid: str) -> bool:
        """更新示例的接受次数。
        
        Args:
            example_id: 示例 ID
            datasource_luid: 数据源 ID
        
        Returns:
            是否成功
        """
        if self._store is None:
            return False
        
        namespace = self._make_namespace(datasource_luid)
        
        try:
            item = self._store.get(namespace, example_id)
            if item is None or item.value is None:
                logger.warning(f"FewShotManager 示例不存在: id={example_id}")
                return False
            
            example = FewShotExample.model_validate(item.value)
            example.accepted_count += 1
            example.updated_at = datetime.now()
            
            self._store.put(namespace, example_id, example.model_dump())
            
            logger.info(
                f"FewShotManager 已更新接受次数: id={example_id}, "
                f"accepted_count={example.accepted_count}"
            )
            return True
            
        except Exception as e:
            logger.error(f"FewShotManager update_accepted_count 失败: {e}")
            return False
    
    async def get(self, example_id: str, datasource_luid: str) -> Optional[FewShotExample]:
        """获取单个示例。
        
        Args:
            example_id: 示例 ID
            datasource_luid: 数据源 ID
        
        Returns:
            FewShotExample 或 None
        """
        if self._store is None:
            return None
        
        namespace = self._make_namespace(datasource_luid)
        
        try:
            item = self._store.get(namespace, example_id)
            if item is None or item.value is None:
                return None
            
            return FewShotExample.model_validate(item.value)
            
        except Exception as e:
            logger.error(f"FewShotManager get 失败: {e}")
            return None
    
    async def delete(self, example_id: str, datasource_luid: str) -> bool:
        """删除示例。
        
        Args:
            example_id: 示例 ID
            datasource_luid: 数据源 ID
        
        Returns:
            是否成功
        """
        if self._store is None:
            return False
        
        namespace = self._make_namespace(datasource_luid)
        
        try:
            self._store.delete(namespace, example_id)
            logger.info(f"FewShotManager 已删除示例: id={example_id}")
            return True
            
        except Exception as e:
            logger.error(f"FewShotManager delete 失败: {e}")
            return False
    
    async def list_all(self, datasource_luid: str) -> list[FewShotExample]:
        """列出数据源的所有示例。
        
        Args:
            datasource_luid: 数据源 ID
        
        Returns:
            FewShotExample 列表
        """
        if self._store is None:
            return []
        
        namespace = self._make_namespace(datasource_luid)
        
        try:
            items = self._store.search(namespace, limit=self.max_examples_per_datasource)
            
            examples = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    example = FewShotExample.model_validate(item.value)
                    examples.append(example)
                except Exception as e:
                    logger.debug(f"解析示例条目失败: {e}")
                    continue
            
            return examples
            
        except Exception as e:
            logger.error(f"FewShotManager list_all 失败: {e}")
            return []
    
    async def count(self, datasource_luid: str) -> int:
        """获取数据源的示例数量。
        
        Args:
            datasource_luid: 数据源 ID
        
        Returns:
            示例数量
        """
        examples = await self.list_all(datasource_luid)
        return len(examples)
    
    async def _evict_if_needed(self, datasource_luid: str) -> None:
        """如果示例数超过上限，淘汰旧示例。
        
        淘汰策略：删除 accepted_count 最低且最旧的示例
        
        Args:
            datasource_luid: 数据源 ID
        """
        if self._store is None:
            return
        
        namespace = self._make_namespace(datasource_luid)
        
        try:
            items = self._store.search(namespace, limit=self.max_examples_per_datasource + 10)
            
            if len(items) < self.max_examples_per_datasource:
                return
            
            # 解析所有示例
            examples_with_key: list[tuple] = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    example = FewShotExample.model_validate(item.value)
                    examples_with_key.append((item.key, example))
                except Exception as e:
                    logger.debug(f"解析示例条目失败（淘汰检查）: {e}")
                    continue
            
            if len(examples_with_key) < self.max_examples_per_datasource:
                return
            
            # 按 (accepted_count ASC, created_at ASC) 排序，找出要删除的
            examples_with_key.sort(
                key=lambda x: (x[1].accepted_count, x[1].created_at)
            )
            
            # 删除超出的示例
            to_delete = len(examples_with_key) - self.max_examples_per_datasource + 1
            for i in range(to_delete):
                key, example = examples_with_key[i]
                self._store.delete(namespace, key)
                logger.info(
                    f"FewShotManager 淘汰示例: id={example.id}, "
                    f"accepted_count={example.accepted_count}"
                )
                
        except Exception as e:
            logger.error(f"FewShotManager _evict_if_needed 失败: {e}")

__all__ = [
    "FewShotManager",
]
