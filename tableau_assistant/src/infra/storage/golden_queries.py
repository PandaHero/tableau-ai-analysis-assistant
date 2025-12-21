# -*- coding: utf-8 -*-
"""
Golden Query Storage - 成功查询存储

使用 LangGraph SqliteStore 存储成功执行的查询，用于：
1. Few-Shot 示例选择
2. 查询缓存
3. 模型改进数据收集

命名空间设计：
- ("golden_queries", datasource_luid) - 按数据源隔离
- ("golden_queries_index", datasource_luid) - 查询索引（用于快速检索）

Requirements:
- 基于 MODULE_ARCHITECTURE_DEEP_ANALYSIS.md 中的 Golden Query 存储改进建议
"""

import hashlib
import logging
import time
from datetime import datetime
from typing import Any, Dict, List, Optional, Tuple

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class GoldenQuery(BaseModel):
    """成功查询记录"""
    query_id: str = Field(description="查询唯一 ID (基于问题和查询的哈希)")
    question: str = Field(description="用户原始问题")
    restated_question: str = Field(default="", description="重述后的问题")
    semantic_query: Optional[Dict[str, Any]] = Field(default=None, description="语义查询")
    vizql_query: Dict[str, Any] = Field(description="VizQL 查询")
    result_summary: Optional[Dict[str, Any]] = Field(default=None, description="结果摘要")
    execution_time: float = Field(default=0.0, description="执行时间(秒)")
    row_count: int = Field(default=0, description="返回行数")
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat())
    used_count: int = Field(default=0, description="被引用次数")
    last_used_at: Optional[str] = Field(default=None, description="最后使用时间")
    tags: List[str] = Field(default_factory=list, description="标签")


class GoldenQueryStore:
    """
    Golden Query 存储管理器
    
    使用 LangGraph SqliteStore 存储成功的查询。
    """
    
    NAMESPACE_PREFIX = "golden_queries"
    INDEX_NAMESPACE_PREFIX = "golden_queries_index"
    
    def __init__(self, store: Optional[Any] = None):
        """
        初始化存储管理器
        
        Args:
            store: LangGraph SqliteStore 实例，如果为 None 则使用全局实例
        """
        self._store = store
    
    def _get_store(self):
        """获取存储实例"""
        if self._store is None:
            from tableau_assistant.src.infra.storage.langgraph_store import get_langgraph_store
            self._store = get_langgraph_store()
        return self._store
    
    def _compute_query_id(self, question: str, vizql_query: Dict[str, Any]) -> str:
        """
        计算查询 ID
        
        基于问题和查询内容生成唯一 ID。
        """
        import json
        content = f"{question}|{json.dumps(vizql_query, sort_keys=True)}"
        return hashlib.sha256(content.encode()).hexdigest()[:16]
    
    def _get_namespace(self, datasource_luid: str) -> Tuple[str, str]:
        """获取命名空间"""
        return (self.NAMESPACE_PREFIX, datasource_luid)
    
    def _get_index_namespace(self, datasource_luid: str) -> Tuple[str, str]:
        """获取索引命名空间"""
        return (self.INDEX_NAMESPACE_PREFIX, datasource_luid)
    
    def save(
        self,
        datasource_luid: str,
        question: str,
        vizql_query: Dict[str, Any],
        restated_question: str = "",
        semantic_query: Optional[Dict[str, Any]] = None,
        result_summary: Optional[Dict[str, Any]] = None,
        execution_time: float = 0.0,
        row_count: int = 0,
        tags: Optional[List[str]] = None,
    ) -> str:
        """
        保存成功的查询
        
        Args:
            datasource_luid: 数据源 LUID
            question: 用户问题
            vizql_query: VizQL 查询
            restated_question: 重述后的问题
            semantic_query: 语义查询
            result_summary: 结果摘要
            execution_time: 执行时间
            row_count: 返回行数
            tags: 标签
            
        Returns:
            查询 ID
        """
        store = self._get_store()
        
        # 计算查询 ID
        query_id = self._compute_query_id(question, vizql_query)
        
        # 检查是否已存在
        namespace = self._get_namespace(datasource_luid)
        existing = store.get(namespace, query_id)
        
        if existing:
            # 更新使用次数
            golden_query = GoldenQuery(**existing.value)
            golden_query.used_count += 1
            golden_query.last_used_at = datetime.now().isoformat()
            store.put(namespace, query_id, golden_query.model_dump())
            logger.debug(f"更新 Golden Query: {query_id}, used_count={golden_query.used_count}")
            return query_id
        
        # 创建新记录
        golden_query = GoldenQuery(
            query_id=query_id,
            question=question,
            restated_question=restated_question,
            semantic_query=semantic_query,
            vizql_query=vizql_query,
            result_summary=result_summary,
            execution_time=execution_time,
            row_count=row_count,
            tags=tags or [],
        )
        
        # 保存到存储
        store.put(namespace, query_id, golden_query.model_dump())
        
        # 更新索引
        self._update_index(datasource_luid, query_id, question)
        
        logger.info(f"保存 Golden Query: {query_id}, question='{question[:50]}...'")
        return query_id
    
    def _update_index(
        self,
        datasource_luid: str,
        query_id: str,
        question: str,
    ) -> None:
        """更新查询索引"""
        store = self._get_store()
        index_namespace = self._get_index_namespace(datasource_luid)
        
        # 获取现有索引
        index_item = store.get(index_namespace, "query_list")
        if index_item:
            query_list = index_item.value
        else:
            query_list = []
        
        # 添加新查询（如果不存在）
        if query_id not in [q.get("id") for q in query_list]:
            query_list.append({
                "id": query_id,
                "question": question[:100],  # 截断问题
                "created_at": datetime.now().isoformat(),
            })
            
            # 限制索引大小（保留最近 1000 条）
            if len(query_list) > 1000:
                query_list = query_list[-1000:]
            
            store.put(index_namespace, "query_list", query_list)
    
    def get(
        self,
        datasource_luid: str,
        query_id: str,
    ) -> Optional[GoldenQuery]:
        """
        获取查询记录
        
        Args:
            datasource_luid: 数据源 LUID
            query_id: 查询 ID
            
        Returns:
            GoldenQuery 或 None
        """
        store = self._get_store()
        namespace = self._get_namespace(datasource_luid)
        
        item = store.get(namespace, query_id)
        if item:
            return GoldenQuery(**item.value)
        return None
    
    def search(
        self,
        datasource_luid: str,
        question: str,
        limit: int = 5,
    ) -> List[GoldenQuery]:
        """
        搜索相似查询
        
        简单实现：基于问题关键词匹配。
        后续可以改进为向量相似度搜索。
        
        Args:
            datasource_luid: 数据源 LUID
            question: 搜索问题
            limit: 返回数量限制
            
        Returns:
            相似查询列表
        """
        store = self._get_store()
        namespace = self._get_namespace(datasource_luid)
        index_namespace = self._get_index_namespace(datasource_luid)
        
        # 获取索引
        index_item = store.get(index_namespace, "query_list")
        if not index_item:
            return []
        
        query_list = index_item.value
        
        # 简单关键词匹配
        question_lower = question.lower()
        keywords = set(question_lower.split())
        
        scored_queries = []
        for q in query_list:
            q_keywords = set(q.get("question", "").lower().split())
            # 计算关键词重叠度
            overlap = len(keywords & q_keywords)
            if overlap > 0:
                scored_queries.append((overlap, q.get("id")))
        
        # 按分数排序
        scored_queries.sort(reverse=True)
        
        # 获取完整记录
        results = []
        for _, query_id in scored_queries[:limit]:
            item = store.get(namespace, query_id)
            if item:
                results.append(GoldenQuery(**item.value))
        
        return results
    
    def get_recent(
        self,
        datasource_luid: str,
        limit: int = 10,
    ) -> List[GoldenQuery]:
        """
        获取最近的查询
        
        Args:
            datasource_luid: 数据源 LUID
            limit: 返回数量限制
            
        Returns:
            最近查询列表
        """
        store = self._get_store()
        namespace = self._get_namespace(datasource_luid)
        index_namespace = self._get_index_namespace(datasource_luid)
        
        # 获取索引
        index_item = store.get(index_namespace, "query_list")
        if not index_item:
            return []
        
        query_list = index_item.value
        
        # 获取最近的记录
        results = []
        for q in reversed(query_list[-limit:]):
            item = store.get(namespace, q.get("id"))
            if item:
                results.append(GoldenQuery(**item.value))
        
        return results
    
    def get_most_used(
        self,
        datasource_luid: str,
        limit: int = 10,
    ) -> List[GoldenQuery]:
        """
        获取使用最多的查询
        
        Args:
            datasource_luid: 数据源 LUID
            limit: 返回数量限制
            
        Returns:
            使用最多的查询列表
        """
        store = self._get_store()
        namespace = self._get_namespace(datasource_luid)
        index_namespace = self._get_index_namespace(datasource_luid)
        
        # 获取索引
        index_item = store.get(index_namespace, "query_list")
        if not index_item:
            return []
        
        query_list = index_item.value
        
        # 获取所有记录并按使用次数排序
        all_queries = []
        for q in query_list:
            item = store.get(namespace, q.get("id"))
            if item:
                golden_query = GoldenQuery(**item.value)
                all_queries.append(golden_query)
        
        # 按使用次数排序
        all_queries.sort(key=lambda x: x.used_count, reverse=True)
        
        return all_queries[:limit]
    
    def delete(
        self,
        datasource_luid: str,
        query_id: str,
    ) -> bool:
        """
        删除查询记录
        
        Args:
            datasource_luid: 数据源 LUID
            query_id: 查询 ID
            
        Returns:
            是否删除成功
        """
        store = self._get_store()
        namespace = self._get_namespace(datasource_luid)
        index_namespace = self._get_index_namespace(datasource_luid)
        
        # 删除记录
        store.delete(namespace, query_id)
        
        # 更新索引
        index_item = store.get(index_namespace, "query_list")
        if index_item:
            query_list = [q for q in index_item.value if q.get("id") != query_id]
            store.put(index_namespace, "query_list", query_list)
        
        logger.info(f"删除 Golden Query: {query_id}")
        return True
    
    def count(self, datasource_luid: str) -> int:
        """
        获取查询数量
        
        Args:
            datasource_luid: 数据源 LUID
            
        Returns:
            查询数量
        """
        store = self._get_store()
        index_namespace = self._get_index_namespace(datasource_luid)
        
        index_item = store.get(index_namespace, "query_list")
        if index_item:
            return len(index_item.value)
        return 0


# 全局实例
_global_store: Optional[GoldenQueryStore] = None


def get_golden_query_store() -> GoldenQueryStore:
    """获取全局 Golden Query 存储实例"""
    global _global_store
    if _global_store is None:
        _global_store = GoldenQueryStore()
    return _global_store


__all__ = [
    "GoldenQuery",
    "GoldenQueryStore",
    "get_golden_query_store",
]
