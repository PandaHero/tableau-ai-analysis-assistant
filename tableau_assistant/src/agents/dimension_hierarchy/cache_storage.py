# -*- coding: utf-8 -*-
"""
Dimension Hierarchy Cache Storage Layer (LangGraph Store)

提供维度层级推断的缓存存储功能，基于 LangGraph SqliteStore。

职责：
1. 维度层级缓存（按 datasource_luid 或 luid:tableId，永久，field_hash 变化时失效）
2. RAG 模式元数据（不含向量，向量存 FAISS）

支持错误纠正：
- delete_hierarchy_cache(): 删除指定数据源的缓存
- delete_pattern_metadata(): 删除单个 RAG 模式元数据
- clear_pattern_metadata(): 清空所有 RAG 模式元数据

Requirements: 1.1, 1.3
"""
from typing import Dict, Any, List, Optional
import json
import hashlib
import logging
from datetime import datetime
from enum import Enum

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════
# Namespace 常量
# ═══════════════════════════════════════════════════════════

NS_HIERARCHY_CACHE = "dimension_hierarchy_cache"
NS_DIMENSION_PATTERNS_METADATA = "dimension_patterns_metadata"

# ═══════════════════════════════════════════════════════════
# 阈值常量
# ═══════════════════════════════════════════════════════════

RAG_SIMILARITY_THRESHOLD = 0.92  # RAG 相似度阈值（seed/verified）
RAG_SIMILARITY_THRESHOLD_UNVERIFIED = 0.95  # RAG 相似度阈值（llm/unverified）
RAG_STORE_CONFIDENCE_THRESHOLD = 0.85  # LLM 结果存入 RAG 的置信度阈值

# ═══════════════════════════════════════════════════════════
# 并发控制常量
# ═══════════════════════════════════════════════════════════

MAX_LOCKS = 1000  # 最大锁数量
LOCK_EXPIRE_SECONDS = 3600  # 锁过期时间（秒），1 小时

# ═══════════════════════════════════════════════════════════
# TTL 常量（永久缓存）
# ═══════════════════════════════════════════════════════════

# 设置为 10 年（分钟），实现"永久"缓存（仅 field_hash 变化时失效）
# LangGraph SqliteStore 的 TTL 单位是分钟
PERMANENT_TTL_MINUTES = 10 * 365 * 24 * 60  # 10 年 = 5,256,000 分钟


class PatternSource(str, Enum):
    """RAG 模式来源"""
    SEED = "seed"      # 种子数据（预置）
    LLM = "llm"        # LLM 推断结果
    MANUAL = "manual"  # 人工添加/修正


def compute_field_hash_metadata_only(dimension_fields: List[Any]) -> str:
    """
    计算字段列表的哈希值（仅用元数据，不含样例数据）
    
    用于缓存检查，避免因样例数据变化导致缓存失效。
    
    Args:
        dimension_fields: 维度字段列表（FieldMetadata 对象或 dict）
    
    Returns:
        MD5 哈希值（32 字符）
    
    Examples:
        >>> fields = [field1, field2, field3]
        >>> hash_val = compute_field_hash_metadata_only(fields)
        >>> print(hash_val)  # "a1b2c3d4e5f6g7h8i9j0k1l2m3n4o5p6"
    """
    def get_field_name(f):
        """获取字段名（兼容对象和字典）"""
        if isinstance(f, dict):
            return f.get("field_name", f.get("name", ""))
        return getattr(f, "name", getattr(f, "field_name", ""))
    
    def get_field_caption(f):
        """获取字段标题（兼容对象和字典）"""
        if isinstance(f, dict):
            return f.get("field_caption", f.get("fieldCaption", ""))
        return getattr(f, "fieldCaption", getattr(f, "field_caption", ""))
    
    def get_data_type(f):
        """获取数据类型（兼容对象和字典）"""
        if isinstance(f, dict):
            return f.get("data_type", f.get("dataType", ""))
        return getattr(f, "dataType", getattr(f, "data_type", ""))
    
    field_info = []
    for f in sorted(dimension_fields, key=get_field_name):
        info = {
            "name": get_field_name(f),
            "caption": get_field_caption(f),
            "dataType": get_data_type(f),
            # 不包含 sample_values 和 unique_count
        }
        field_info.append(info)
    
    content = json.dumps(field_info, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


def compute_single_field_hash(
    field_name: str,
    field_caption: str,
    data_type: str,
) -> str:
    """
    计算单个字段的元数据哈希值（用于检测字段变更）
    
    用于增量推断，检测字段的 caption 或 dataType 是否变化。
    
    Args:
        field_name: 字段名
        field_caption: 字段标题
        data_type: 数据类型
    
    Returns:
        MD5 哈希值（32 字符）
    
    Examples:
        >>> field_hash = compute_single_field_hash("year", "年份", "integer")
        >>> print(field_hash)  # "x1y2z3w4v5u6t7s8r9q0p1o2n3m4l5k6"
    """
    info = {
        "name": field_name,
        "caption": field_caption,
        "dataType": data_type,
    }
    content = json.dumps(info, sort_keys=True, ensure_ascii=False)
    return hashlib.md5(content.encode("utf-8")).hexdigest()


class DimensionHierarchyCacheStorage:
    """
    维度层级缓存存储层（LangGraph Store）
    
    职责：
    1. 维度层级缓存（按 datasource_luid，永久，field_hash 变化时失效）
    2. RAG 模式元数据（不含向量，向量存 FAISS）
    
    支持错误纠正：
    - delete_hierarchy_cache(): 删除指定数据源的缓存
    - delete_pattern_metadata(): 删除单个 RAG 模式元数据
    - clear_pattern_metadata(): 清空所有 RAG 模式元数据
    """
    
    def __init__(self, store=None):
        """
        Args:
            store: LangGraph SqliteStore 实例（可选，默认使用全局实例）
        """
        self._store = store or self._get_default_store()
    
    def _get_default_store(self):
        """获取默认 LangGraph Store"""
        from tableau_assistant.src.infra.storage import get_langgraph_store
        return get_langgraph_store()
    
    # ═══════════════════════════════════════════════════════════
    # 维度层级缓存（永久，field_hash 变化时失效）
    # ═══════════════════════════════════════════════════════════
    
    def get_hierarchy_cache(self, cache_key: str) -> Optional[Dict[str, Any]]:
        """
        获取维度层级缓存
        
        Args:
            cache_key: 缓存 key（单表: luid, 多表: luid:tableId）
        
        Returns:
            缓存数据（包含 field_hash, field_meta_hashes, hierarchy_data）或 None
        """
        if not cache_key or not self._store:
            return None
        
        try:
            item = self._store.get((NS_HIERARCHY_CACHE,), cache_key)
            if item and item.value:
                return item.value
        except Exception as e:
            logger.warning(f"获取缓存失败: {e}")
        
        return None
    
    def put_hierarchy_cache(
        self,
        cache_key: str,
        field_hash: str,
        field_meta_hashes: Dict[str, str],
        hierarchy_data: Dict[str, Any],
    ) -> bool:
        """
        存入维度层级缓存（永久，不设 TTL）
        
        Args:
            cache_key: 缓存 key（单表: luid, 多表: luid:tableId）
            field_hash: 整体字段列表 hash（用于快速判断是否需要增量检查）
            field_meta_hashes: 每个字段的元数据 hash（用于检测字段变更）
            hierarchy_data: 推断结果
        
        Returns:
            是否成功
        """
        if not cache_key or not self._store:
            return False
        
        try:
            data = {
                "cache_key": cache_key,
                "field_hash": field_hash,
                "field_meta_hashes": field_meta_hashes,  # 新增：每个字段的元数据 hash
                "hierarchy_data": hierarchy_data,
                "created_at": datetime.now().isoformat(),
            }
            
            # 显式设置超长 TTL（10 年），实现"永久"缓存
            # 缓存仅在 field_hash 变化时失效，而非 TTL 过期
            # 注意：某些 store 实现（如 InMemoryStore）不支持 TTL，需要优雅降级
            try:
                self._store.put((NS_HIERARCHY_CACHE,), cache_key, data, ttl=PERMANENT_TTL_MINUTES)
            except (TypeError, Exception) as ttl_error:
                if "TTL is not supported" in str(ttl_error) or "ttl" in str(ttl_error).lower():
                    # store 不支持 ttl 参数，回退到无 TTL 模式
                    self._store.put((NS_HIERARCHY_CACHE,), cache_key, data)
                else:
                    raise
            logger.debug(f"缓存已更新: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"存入缓存失败: {e}")
            return False
    
    def delete_hierarchy_cache(self, cache_key: str) -> bool:
        """
        删除指定数据源的维度层级缓存
        
        Args:
            cache_key: 缓存 key
        
        Returns:
            是否成功
        """
        if not cache_key or not self._store:
            return False
        
        try:
            self._store.delete((NS_HIERARCHY_CACHE,), cache_key)
            logger.info(f"缓存已删除: {cache_key}")
            return True
        except Exception as e:
            logger.warning(f"删除缓存失败: {e}")
            return False
    
    # ═══════════════════════════════════════════════════════════
    # RAG 模式元数据（不含向量，向量存 FAISS）
    # ═══════════════════════════════════════════════════════════
    
    def get_pattern_metadata(self, pattern_id: str) -> Optional[Dict[str, Any]]:
        """
        获取模式元数据
        
        Args:
            pattern_id: 模式 ID
        
        Returns:
            模式元数据或 None
        """
        if not pattern_id or not self._store:
            return None
        
        try:
            item = self._store.get((NS_DIMENSION_PATTERNS_METADATA,), pattern_id)
            if item and item.value:
                return item.value
        except Exception as e:
            logger.warning(f"获取模式元数据失败: {e}")
        
        return None
    
    def store_pattern_metadata(
        self,
        pattern_id: str,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        category: str,
        category_detail: str,
        level: int,
        granularity: str,
        reasoning: str,
        confidence: float,
        datasource_luid: Optional[str] = None,
        source: PatternSource = PatternSource.LLM,
        verified: bool = False,
    ) -> bool:
        """
        存入 RAG 模式元数据（不含向量）
        
        向量存储在 FAISS 中，这里只存元数据。
        使用超长 TTL（10 年）实现"永久"存储。
        
        Args:
            pattern_id: 模式 ID
            field_caption: 字段标题
            data_type: 数据类型
            sample_values: 样例值列表
            unique_count: 唯一值数量
            category: 维度类别
            category_detail: 详细类别描述
            level: 层级级别
            granularity: 粒度描述
            reasoning: 推理说明
            confidence: 置信度
            datasource_luid: 数据源 LUID（可选）
            source: 模式来源（seed/llm/manual）
            verified: 是否已验证
        
        Returns:
            是否成功
        """
        if not self._store:
            return False
        
        try:
            data = {
                "pattern_id": pattern_id,
                "field_caption": field_caption,
                "data_type": data_type,
                "sample_values": sample_values[:10] if sample_values else [],
                "unique_count": unique_count,
                "category": category,
                "category_detail": category_detail,
                "level": level,
                "granularity": granularity,
                "reasoning": reasoning,
                "confidence": confidence,
                "datasource_luid": datasource_luid,
                "source": source.value if isinstance(source, PatternSource) else source,
                "verified": verified,
                "created_at": datetime.now().isoformat(),
            }
            
            # 显式设置超长 TTL（10 年），实现"永久"存储
            # RAG 模式元数据应永久保存，用于自学习
            # 注意：某些 store 实现（如 InMemoryStore）不支持 TTL，需要优雅降级
            try:
                self._store.put((NS_DIMENSION_PATTERNS_METADATA,), pattern_id, data, ttl=PERMANENT_TTL_MINUTES)
            except (TypeError, Exception) as ttl_error:
                if "TTL is not supported" in str(ttl_error) or "ttl" in str(ttl_error).lower():
                    # store 不支持 ttl 参数，回退到无 TTL 模式
                    self._store.put((NS_DIMENSION_PATTERNS_METADATA,), pattern_id, data)
                else:
                    raise
            logger.debug(f"模式元数据已存入: {field_caption} (source={source})")
            return True
            
        except Exception as e:
            logger.warning(f"存入模式元数据失败: {e}")
            return False
    
    def delete_pattern_metadata(self, pattern_id: str) -> bool:
        """
        删除单个 RAG 模式元数据
        
        Args:
            pattern_id: 模式 ID
        
        Returns:
            是否成功
        """
        if not self._store:
            return False
        
        try:
            self._store.delete((NS_DIMENSION_PATTERNS_METADATA,), pattern_id)
            logger.info(f"模式元数据已删除: {pattern_id}")
            return True
        except Exception as e:
            logger.warning(f"删除模式元数据失败: {e}")
            return False
    
    def update_pattern_verified(self, pattern_id: str, verified: bool) -> bool:
        """
        更新模式的验证状态
        
        Args:
            pattern_id: 模式 ID
            verified: 是否已验证
        
        Returns:
            是否成功
        """
        metadata = self.get_pattern_metadata(pattern_id)
        if not metadata:
            return False
        
        try:
            metadata["verified"] = verified
            metadata["verified_at"] = datetime.now().isoformat() if verified else None
            
            # 显式设置超长 TTL（10 年），实现"永久"存储
            # 注意：某些 store 实现（如 InMemoryStore）不支持 TTL，需要优雅降级
            try:
                self._store.put((NS_DIMENSION_PATTERNS_METADATA,), pattern_id, metadata, ttl=PERMANENT_TTL_MINUTES)
            except (TypeError, Exception) as ttl_error:
                if "TTL is not supported" in str(ttl_error) or "ttl" in str(ttl_error).lower():
                    # store 不支持 ttl 参数，回退到无 TTL 模式
                    self._store.put((NS_DIMENSION_PATTERNS_METADATA,), pattern_id, metadata)
                else:
                    raise
            logger.info(f"模式验证状态已更新: {pattern_id} -> verified={verified}")
            return True
        except Exception as e:
            logger.warning(f"更新验证状态失败: {e}")
            return False
    
    def get_all_pattern_metadata(self, limit: int = 10000) -> List[Dict[str, Any]]:
        """
        获取所有模式元数据（用于重建 FAISS 索引）
        
        Args:
            limit: 最大返回数量（默认 10000，足够覆盖所有模式）
                   注意：LangGraph SqliteStore.search 默认 limit=10，
                   必须显式传递较大值以获取所有数据
        
        Returns:
            所有模式元数据列表
        """
        if not self._store:
            return []
        
        try:
            # 搜索该 namespace 下的所有项
            # 重要：必须显式传递 limit，否则默认只返回 10 条
            items = self._store.search((NS_DIMENSION_PATTERNS_METADATA,), limit=limit)
            return [item.value for item in items if item and item.value]
        except Exception as e:
            logger.warning(f"获取所有模式元数据失败: {e}")
            return []
    
    def clear_pattern_metadata(self) -> int:
        """
        清空所有 RAG 模式元数据（谨慎使用！）
        
        用于完全重置 RAG 索引，通常配合 FAISS rebuild_index 使用。
        
        Returns:
            删除的模式数量
        """
        if not self._store:
            return 0
        
        try:
            # 获取所有模式
            all_patterns = self.get_all_pattern_metadata()
            count = 0
            
            # 逐个删除
            for pattern in all_patterns:
                pattern_id = pattern.get("pattern_id")
                if pattern_id:
                    self._store.delete((NS_DIMENSION_PATTERNS_METADATA,), pattern_id)
                    count += 1
            
            logger.info(f"已清空所有模式元数据: {count} 个")
            return count
        except Exception as e:
            logger.warning(f"清空模式元数据失败: {e}")
            return 0


__all__ = [
    # Namespace 常量
    "NS_HIERARCHY_CACHE",
    "NS_DIMENSION_PATTERNS_METADATA",
    # 阈值常量
    "RAG_SIMILARITY_THRESHOLD",
    "RAG_SIMILARITY_THRESHOLD_UNVERIFIED",
    "RAG_STORE_CONFIDENCE_THRESHOLD",
    # 并发控制常量
    "MAX_LOCKS",
    "LOCK_EXPIRE_SECONDS",
    # TTL 常量
    "PERMANENT_TTL_MINUTES",
    # 枚举
    "PatternSource",
    # 函数
    "compute_field_hash_metadata_only",
    "compute_single_field_hash",
    # 类
    "DimensionHierarchyCacheStorage",
]
