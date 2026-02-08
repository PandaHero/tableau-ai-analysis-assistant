# -*- coding: utf-8 -*-
"""
FeedbackLearner 组件 - 用户反馈学习

功能：
- 记录反馈：记录用户对查询结果的反馈（accept/modify/reject）
- 学习同义词：从用户确认中学习术语到字段的映射
- 提升示例：将高质量查询提升为 Few-shot 示例

存储后端：LangGraph SqliteStore（复用现有基础设施）

配置来源：analytics_assistant/config/app.yaml -> semantic_parser.feedback_learner

Requirements: 15.1-15.6 - FeedbackLearner 反馈学习
"""

import logging
import uuid
from datetime import datetime
from typing import Any, Dict, List, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import get_kv_store

from ..schemas.feedback import FeedbackType, FeedbackRecord, SynonymMapping
from ..schemas.intermediate import FewShotExample
from .few_shot_manager import FewShotManager

logger = logging.getLogger(__name__)


# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def _get_config() -> Dict[str, Any]:
    """获取 feedback_learner 配置。"""
    try:
        config = get_config()
        return config.config.get("semantic_parser", {}).get("feedback_learner", {})
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return {}


# ═══════════════════════════════════════════════════════════════════════════
# FeedbackLearner 组件
# ═══════════════════════════════════════════════════════════════════════════

class FeedbackLearner:
    """用户反馈学习器。
    
    功能：
    - 记录反馈：记录用户对查询结果的反馈
    - 学习同义词：从用户确认中学习术语到字段的映射
    - 提升示例：将高质量查询提升为 Few-shot 示例
    
    存储结构：
    - 反馈记录: namespace=("semantic_parser", "feedback", datasource_luid)
    - 同义词映射: namespace=("semantic_parser", "synonyms", datasource_luid)
    
    学习策略：
    - 同义词学习阈值：同一映射确认 3 次后自动添加到同义词表
    - 示例提升：接受的查询自动添加到 Few-shot 示例候选池
    
    配置来源：app.yaml -> semantic_parser.feedback_learner
    
    Examples:
        >>> learner = FeedbackLearner()
        >>> 
        >>> # 记录反馈
        >>> await learner.record(FeedbackRecord(
        ...     id="fb_001",
        ...     question="上个月各地区的销售额",
        ...     feedback_type=FeedbackType.ACCEPT,
        ...     datasource_luid="ds_123",
        ... ))
        >>> 
        >>> # 学习同义词
        >>> await learner.learn_synonym(
        ...     original_term="销量",
        ...     correct_field="销售额",
        ...     datasource_luid="ds_123",
        ... )
        >>> 
        >>> # 提升为示例
        >>> await learner.promote_to_example("fb_001")
    """
    
    # 命名空间前缀
    FEEDBACK_NAMESPACE_PREFIX = ("semantic_parser", "feedback")
    SYNONYM_NAMESPACE_PREFIX = ("semantic_parser", "synonyms")
    
    # 默认配置
    _DEFAULT_SYNONYM_THRESHOLD = 3  # 同义词学习阈值
    _DEFAULT_MAX_FEEDBACK_PER_DATASOURCE = 1000  # 每个数据源最多保存的反馈数
    _DEFAULT_AUTO_PROMOTE_ENABLED = True  # 是否自动提升接受的查询为示例
    
    def __init__(
        self,
        store: Optional[Any] = None,
        few_shot_manager: Optional[FewShotManager] = None,
        synonym_threshold: Optional[int] = None,
        max_feedback_per_datasource: Optional[int] = None,
        auto_promote_enabled: Optional[bool] = None,
    ):
        """初始化 FeedbackLearner。
        
        Args:
            store: LangGraph SqliteStore 实例，None 则使用全局实例
            few_shot_manager: FewShotManager 实例，用于提升示例
            synonym_threshold: 同义词学习阈值（None 从配置读取）
            max_feedback_per_datasource: 每个数据源最多保存的反馈数（None 从配置读取）
            auto_promote_enabled: 是否自动提升接受的查询为示例（None 从配置读取）
        """
        if store is None:
            store = get_kv_store()
        self._store = store
        
        self._few_shot_manager = few_shot_manager
        
        # 从配置加载参数
        self._load_config(synonym_threshold, max_feedback_per_datasource, auto_promote_enabled)
    
    def _load_config(
        self,
        synonym_threshold: Optional[int],
        max_feedback_per_datasource: Optional[int],
        auto_promote_enabled: Optional[bool],
    ) -> None:
        """从配置加载参数。"""
        config = _get_config()
        
        self.synonym_threshold = (
            synonym_threshold
            if synonym_threshold is not None
            else config.get("synonym_threshold", self._DEFAULT_SYNONYM_THRESHOLD)
        )
        self.max_feedback_per_datasource = (
            max_feedback_per_datasource
            if max_feedback_per_datasource is not None
            else config.get("max_feedback_per_datasource", self._DEFAULT_MAX_FEEDBACK_PER_DATASOURCE)
        )
        self.auto_promote_enabled = (
            auto_promote_enabled
            if auto_promote_enabled is not None
            else config.get("auto_promote_enabled", self._DEFAULT_AUTO_PROMOTE_ENABLED)
        )
    
    def _make_feedback_namespace(self, datasource_luid: str) -> tuple:
        """生成反馈存储命名空间。"""
        return (*self.FEEDBACK_NAMESPACE_PREFIX, datasource_luid)
    
    def _make_synonym_namespace(self, datasource_luid: str) -> tuple:
        """生成同义词存储命名空间。"""
        return (*self.SYNONYM_NAMESPACE_PREFIX, datasource_luid)
    
    def _make_synonym_key(self, original_term: str, correct_field: str) -> str:
        """生成同义词映射的 key。"""
        return f"{original_term.lower()}:{correct_field.lower()}"

    async def record(self, feedback: FeedbackRecord) -> bool:
        """记录用户反馈。
        
        记录用户对查询结果的反馈，并根据反馈类型执行相应操作：
        - ACCEPT: 如果启用自动提升，将查询添加到 Few-shot 示例候选池
        - MODIFY: 记录修改内容，用于后续分析
        - REJECT: 记录拒绝原因，用于后续分析
        
        Args:
            feedback: FeedbackRecord 实例
        
        Returns:
            是否成功
        """
        if self._store is None:
            logger.warning("FeedbackLearner 存储不可用，无法记录反馈")
            return False
        
        namespace = self._make_feedback_namespace(feedback.datasource_luid)
        
        try:
            # 如果没有 ID，生成一个
            if not feedback.id:
                feedback.id = f"fb_{uuid.uuid4().hex[:12]}"
            
            # 存储反馈
            self._store.put(namespace, feedback.id, feedback.model_dump())
            
            logger.info(
                f"FeedbackLearner 已记录反馈: id={feedback.id}, "
                f"type={feedback.feedback_type.value}, "
                f"question='{feedback.question[:30]}...'"
            )
            
            # 如果是 ACCEPT 且启用自动提升，尝试提升为示例
            if (
                feedback.feedback_type == FeedbackType.ACCEPT
                and self.auto_promote_enabled
                and feedback.semantic_output is not None
            ):
                await self._auto_promote(feedback)
            
            # 检查是否需要淘汰旧反馈
            await self._evict_if_needed(feedback.datasource_luid)
            
            return True
            
        except Exception as e:
            logger.error(f"FeedbackLearner record 失败: {e}")
            return False
    
    async def learn_synonym(
        self,
        original_term: str,
        correct_field: str,
        datasource_luid: str,
    ) -> bool:
        """学习同义词映射。
        
        记录用户确认的术语到字段的映射。当同一映射被确认次数达到阈值时，
        可以自动添加到同义词表供后续查询使用。
        
        Args:
            original_term: 用户使用的原始术语
            correct_field: 正确的字段名
            datasource_luid: 数据源 ID
        
        Returns:
            是否成功
        """
        if self._store is None:
            logger.warning("FeedbackLearner 存储不可用，无法学习同义词")
            return False
        
        namespace = self._make_synonym_namespace(datasource_luid)
        key = self._make_synonym_key(original_term, correct_field)
        
        try:
            # 检查是否已存在该映射
            item = self._store.get(namespace, key)
            
            if item is not None and item.value is not None:
                # 更新已有映射
                mapping = SynonymMapping.model_validate(item.value)
                mapping.confirmation_count += 1
                mapping.updated_at = datetime.now()
            else:
                # 创建新映射
                mapping = SynonymMapping(
                    id=f"syn_{uuid.uuid4().hex[:12]}",
                    original_term=original_term,
                    correct_field=correct_field,
                    datasource_luid=datasource_luid,
                    confirmation_count=1,
                )
            
            # 存储映射
            self._store.put(namespace, key, mapping.model_dump())
            
            logger.info(
                f"FeedbackLearner 已学习同义词: "
                f"'{original_term}' -> '{correct_field}', "
                f"count={mapping.confirmation_count}"
            )
            
            # 检查是否达到阈值
            if mapping.confirmation_count >= self.synonym_threshold:
                logger.info(
                    f"FeedbackLearner 同义词已达到阈值: "
                    f"'{original_term}' -> '{correct_field}' "
                    f"(count={mapping.confirmation_count} >= {self.synonym_threshold})"
                )
                # TODO: 可以在这里触发将同义词添加到全局同义词表的逻辑
            
            return True
            
        except Exception as e:
            logger.error(f"FeedbackLearner learn_synonym 失败: {e}")
            return False
    
    async def promote_to_example(
        self,
        feedback_id: str,
        datasource_luid: str,
    ) -> bool:
        """将接受的查询提升为 Few-shot 示例。
        
        从反馈记录中提取信息，创建 FewShotExample 并添加到示例库。
        
        Args:
            feedback_id: 反馈记录 ID
            datasource_luid: 数据源 ID
        
        Returns:
            是否成功
        """
        if self._store is None:
            logger.warning("FeedbackLearner 存储不可用，无法提升示例")
            return False
        
        if self._few_shot_manager is None:
            logger.warning("FeedbackLearner FewShotManager 不可用，无法提升示例")
            return False
        
        namespace = self._make_feedback_namespace(datasource_luid)
        
        try:
            # 获取反馈记录
            item = self._store.get(namespace, feedback_id)
            if item is None or item.value is None:
                logger.warning(f"FeedbackLearner 反馈记录不存在: id={feedback_id}")
                return False
            
            feedback = FeedbackRecord.model_validate(item.value)
            
            # 只有 ACCEPT 类型的反馈才能提升
            if feedback.feedback_type != FeedbackType.ACCEPT:
                logger.warning(
                    f"FeedbackLearner 只能提升 ACCEPT 类型的反馈: "
                    f"id={feedback_id}, type={feedback.feedback_type.value}"
                )
                return False
            
            # 检查必要字段
            if feedback.semantic_output is None:
                logger.warning(
                    f"FeedbackLearner 反馈缺少 semantic_output: id={feedback_id}"
                )
                return False
            
            # 创建 FewShotExample
            example = FewShotExample(
                id=f"ex_{uuid.uuid4().hex[:12]}",
                question=feedback.question,
                restated_question=feedback.restated_question or feedback.question,
                what=feedback.semantic_output.get("what", {}),
                where=feedback.semantic_output.get("where", {}),
                how=feedback.semantic_output.get("how", "SIMPLE"),
                computations=feedback.semantic_output.get("computations"),
                query=feedback.query or "",
                datasource_luid=datasource_luid,
                accepted_count=1,  # 已被接受一次
                created_at=datetime.now(),
                updated_at=datetime.now(),
            )
            
            # 添加到示例库
            success = await self._few_shot_manager.add(example)
            
            if success:
                logger.info(
                    f"FeedbackLearner 已提升为示例: "
                    f"feedback_id={feedback_id}, example_id={example.id}"
                )
            
            return success
            
        except Exception as e:
            logger.error(f"FeedbackLearner promote_to_example 失败: {e}")
            return False
    
    async def get_feedback(
        self,
        feedback_id: str,
        datasource_luid: str,
    ) -> Optional[FeedbackRecord]:
        """获取单个反馈记录。
        
        Args:
            feedback_id: 反馈记录 ID
            datasource_luid: 数据源 ID
        
        Returns:
            FeedbackRecord 或 None
        """
        if self._store is None:
            return None
        
        namespace = self._make_feedback_namespace(datasource_luid)
        
        try:
            item = self._store.get(namespace, feedback_id)
            if item is None or item.value is None:
                return None
            
            return FeedbackRecord.model_validate(item.value)
            
        except Exception as e:
            logger.error(f"FeedbackLearner get_feedback 失败: {e}")
            return None
    
    async def get_synonym_mapping(
        self,
        original_term: str,
        correct_field: str,
        datasource_luid: str,
    ) -> Optional[SynonymMapping]:
        """获取同义词映射。
        
        Args:
            original_term: 原始术语
            correct_field: 正确字段名
            datasource_luid: 数据源 ID
        
        Returns:
            SynonymMapping 或 None
        """
        if self._store is None:
            return None
        
        namespace = self._make_synonym_namespace(datasource_luid)
        key = self._make_synonym_key(original_term, correct_field)
        
        try:
            item = self._store.get(namespace, key)
            if item is None or item.value is None:
                return None
            
            return SynonymMapping.model_validate(item.value)
            
        except Exception as e:
            logger.error(f"FeedbackLearner get_synonym_mapping 失败: {e}")
            return None
    
    async def get_learned_synonyms(
        self,
        datasource_luid: str,
        min_count: Optional[int] = None,
    ) -> List[SynonymMapping]:
        """获取已学习的同义词映射列表。
        
        Args:
            datasource_luid: 数据源 ID
            min_count: 最小确认次数（None 则返回所有）
        
        Returns:
            SynonymMapping 列表
        """
        if self._store is None:
            return []
        
        namespace = self._make_synonym_namespace(datasource_luid)
        min_count = min_count or 1
        
        try:
            items = self._store.search(namespace, limit=1000)
            
            mappings = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    mapping = SynonymMapping.model_validate(item.value)
                    if mapping.confirmation_count >= min_count:
                        mappings.append(mapping)
                except Exception as e:
                    logger.debug(f"解析同义词映射条目失败: {e}")
                    continue
            
            # 按确认次数降序排序
            mappings.sort(key=lambda x: x.confirmation_count, reverse=True)
            
            return mappings
            
        except Exception as e:
            logger.error(f"FeedbackLearner get_learned_synonyms 失败: {e}")
            return []
    
    async def get_confirmed_synonyms(self, datasource_luid: str) -> List[SynonymMapping]:
        """获取已确认的同义词（达到阈值的映射）。
        
        Args:
            datasource_luid: 数据源 ID
        
        Returns:
            达到阈值的 SynonymMapping 列表
        """
        return await self.get_learned_synonyms(
            datasource_luid,
            min_count=self.synonym_threshold
        )
    
    async def list_feedback(
        self,
        datasource_luid: str,
        feedback_type: Optional[FeedbackType] = None,
        limit: int = 100,
    ) -> List[FeedbackRecord]:
        """列出反馈记录。
        
        Args:
            datasource_luid: 数据源 ID
            feedback_type: 筛选反馈类型（None 则返回所有）
            limit: 返回数量限制
        
        Returns:
            FeedbackRecord 列表
        """
        if self._store is None:
            return []
        
        namespace = self._make_feedback_namespace(datasource_luid)
        
        try:
            items = self._store.search(namespace, limit=limit)
            
            records = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    record = FeedbackRecord.model_validate(item.value)
                    if feedback_type is None or record.feedback_type == feedback_type:
                        records.append(record)
                except Exception as e:
                    logger.debug(f"解析反馈记录条目失败: {e}")
                    continue
            
            # 按创建时间降序排序
            records.sort(key=lambda x: x.created_at, reverse=True)
            
            return records[:limit]
            
        except Exception as e:
            logger.error(f"FeedbackLearner list_feedback 失败: {e}")
            return []
    
    async def count_feedback(
        self,
        datasource_luid: str,
        feedback_type: Optional[FeedbackType] = None,
    ) -> int:
        """统计反馈数量。
        
        Args:
            datasource_luid: 数据源 ID
            feedback_type: 筛选反馈类型（None 则统计所有）
        
        Returns:
            反馈数量
        """
        records = await self.list_feedback(
            datasource_luid,
            feedback_type=feedback_type,
            limit=self.max_feedback_per_datasource
        )
        return len(records)
    
    async def _auto_promote(self, feedback: FeedbackRecord) -> None:
        """自动提升接受的查询为示例。
        
        Args:
            feedback: 已接受的反馈记录
        """
        if self._few_shot_manager is None:
            return
        
        try:
            await self.promote_to_example(feedback.id, feedback.datasource_luid)
        except Exception as e:
            logger.warning(f"FeedbackLearner 自动提升失败: {e}")
    
    async def _evict_if_needed(self, datasource_luid: str) -> None:
        """如果反馈数超过上限，淘汰旧反馈。
        
        淘汰策略：删除最旧的反馈记录
        
        Args:
            datasource_luid: 数据源 ID
        """
        if self._store is None:
            return
        
        namespace = self._make_feedback_namespace(datasource_luid)
        
        try:
            items = self._store.search(namespace, limit=self.max_feedback_per_datasource + 100)
            
            if len(items) <= self.max_feedback_per_datasource:
                return
            
            # 解析所有反馈
            records_with_key: List[tuple] = []
            for item in items:
                if item.value is None:
                    continue
                try:
                    record = FeedbackRecord.model_validate(item.value)
                    records_with_key.append((item.key, record))
                except Exception as e:
                    logger.debug(f"解析反馈记录条目失败（淘汰检查）: {e}")
                    continue
            
            if len(records_with_key) <= self.max_feedback_per_datasource:
                return
            
            # 按创建时间升序排序（最旧的在前）
            records_with_key.sort(key=lambda x: x[1].created_at)
            
            # 删除超出的反馈
            to_delete = len(records_with_key) - self.max_feedback_per_datasource
            for i in range(to_delete):
                key, record = records_with_key[i]
                self._store.delete(namespace, key)
                logger.debug(
                    f"FeedbackLearner 淘汰反馈: id={record.id}, "
                    f"created_at={record.created_at}"
                )
                
        except Exception as e:
            logger.error(f"FeedbackLearner _evict_if_needed 失败: {e}")


__all__ = [
    "FeedbackLearner",
]
