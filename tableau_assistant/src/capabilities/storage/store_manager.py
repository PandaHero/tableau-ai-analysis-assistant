"""
Store管理器

使用LangGraph 1.0的Store功能管理缓存和持久化数据
替代部分Redis缓存功能
"""
from typing import Dict, Any, Optional, List, TYPE_CHECKING
from langgraph.store.memory import InMemoryStore
from langgraph.store.base import Item
import time
import json
import os

if TYPE_CHECKING:
    from tableau_assistant.src.models.metadata import Metadata


class StoreManager:
    """
    Store管理器
    
    封装LangGraph Store的常用操作，提供统一的缓存接口
    
    支持的命名空间：
    - ("metadata",) - 元数据缓存（默认1小时，可通过METADATA_CACHE_TTL配置）
    - ("dimension_hierarchy",) - 维度层级缓存（默认24小时，可通过DIMENSION_HIERARCHY_CACHE_TTL配置）
    - ("user_preferences",) - 用户偏好（永久）
    - ("question_history", user_id) - 问题历史（永久）
    - ("anomaly_knowledge",) - 异常知识库（永久）
    """
    
    # 缓存过期时间（秒）- 从环境变量读取，提供默认值
    METADATA_TTL = int(os.getenv('METADATA_CACHE_TTL', '3600'))  # 默认1小时
    DIMENSION_HIERARCHY_TTL = int(os.getenv('DIMENSION_HIERARCHY_CACHE_TTL', '86400'))  # 默认24小时
    
    # Store查询限制（基于LLM上下文长度）
    # 假设每个item平均1KB，40K上下文可以容纳约40个items
    # 为了安全起见，设置为上下文的10%
    DEFAULT_SEARCH_LIMIT = 4000  # 约4000个items
    
    def __init__(
        self,
        store: Optional[InMemoryStore] = None,
        max_search_limit: Optional[int] = None
    ):
        """
        初始化Store管理器
        
        Args:
            store: InMemoryStore实例，如果为None则创建新实例
            max_search_limit: 最大搜索限制，如果为None则从配置文件读取
        """
        self.store = store or InMemoryStore()
        
        # 优先级：参数 > 配置文件 > 默认值
        if max_search_limit is not None:
            self.max_search_limit = max_search_limit
        else:
            try:
                from tableau_assistant.src.config.settings import settings
                self.max_search_limit = settings.store_max_search_limit
            except Exception:
                self.max_search_limit = self.DEFAULT_SEARCH_LIMIT
    
    # ========== 元数据缓存 ==========
    
    def get_metadata(self, datasource_luid: str, datasource_updated_at: str = None):
        """
        获取元数据缓存
        
        Args:
            datasource_luid: 数据源LUID
            datasource_updated_at: 数据源最后更新时间（可选，用于版本检测）
        
        Returns:
            Metadata对象，如果不存在或已过期返回None
        """
        try:
            from tableau_assistant.src.models.metadata import Metadata
            
            item = self.store.get(
                namespace=("metadata",),
                key=datasource_luid
            )
            
            if item and self._is_valid(item, self.METADATA_TTL):
                metadata_dict = item.value
                
                # 版本检测：如果提供了数据源更新时间，检查是否匹配
                if datasource_updated_at:
                    cached_version = metadata_dict.get("_datasource_updated_at")
                    if cached_version and cached_version != datasource_updated_at:
                        print(f"[StoreManager] 数据源已更新，缓存失效: {datasource_luid}")
                        print(f"  缓存版本: {cached_version}")
                        print(f"  当前版本: {datasource_updated_at}")
                        return None
                
                # 反序列化为Metadata对象
                # 移除内部字段（不属于Metadata模型）
                metadata_dict = {
                    k: v for k, v in metadata_dict.items() 
                    if not k.startswith("_")
                }
                return Metadata.model_validate(metadata_dict)
            
            return None
        except Exception as e:
            print(f"[StoreManager] 获取元数据失败: {e}")
            return None
    
    def put_metadata(
        self,
        datasource_luid: str,
        metadata,
        datasource_updated_at: str = None
    ) -> bool:
        """
        保存元数据到缓存
        
        Args:
            datasource_luid: 数据源LUID
            metadata: Metadata模型对象
            datasource_updated_at: 数据源最后更新时间（可选，用于版本检测）
        
        Returns:
            是否保存成功
        """
        try:
            from tableau_assistant.src.models.metadata import Metadata
            
            # 序列化为字典
            if isinstance(metadata, Metadata):
                metadata_dict = metadata.model_dump()
            else:
                # 向后兼容：如果传入的是字典，直接使用
                metadata_dict = metadata
            
            # 添加内部字段
            data = {
                **metadata_dict,
                "_cached_at": time.time(),
            }
            
            # 添加版本信息（如果提供）
            if datasource_updated_at:
                data["_datasource_updated_at"] = datasource_updated_at
            
            self.store.put(
                namespace=("metadata",),
                key=datasource_luid,
                value=data
            )
            return True
        except Exception as e:
            print(f"[StoreManager] 保存元数据失败: {e}")
            return False
    
    # ========== 维度层级缓存 ==========
    
    def get_dimension_hierarchy(
        self,
        datasource_luid: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取维度层级缓存
        
        Args:
            datasource_luid: 数据源LUID
        
        Returns:
            维度层级字典，如果不存在或已过期返回None
        """
        try:
            item = self.store.get(
                namespace=("dimension_hierarchy",),
                key=datasource_luid
            )
            
            if item and self._is_valid(item, self.DIMENSION_HIERARCHY_TTL):
                return item.value
            
            return None
        except Exception as e:
            print(f"[StoreManager] 获取维度层级失败: {e}")
            return None
    
    def put_dimension_hierarchy(
        self,
        datasource_luid: str,
        hierarchy: Dict[str, Any]
    ) -> bool:
        """
        保存维度层级到缓存
        
        Args:
            datasource_luid: 数据源LUID
            hierarchy: 维度层级字典
        
        Returns:
            是否保存成功
        """
        try:
            # 添加时间戳
            data = {
                **hierarchy,
                "_cached_at": time.time()
            }
            
            self.store.put(
                namespace=("dimension_hierarchy",),
                key=datasource_luid,
                value=data
            )
            return True
        except Exception as e:
            print(f"[StoreManager] 保存维度层级失败: {e}")
            return False
    
    # ========== 用户偏好 ==========
    
    def get_user_preferences(self, user_id: str) -> Optional[Dict[str, Any]]:
        """
        获取用户偏好
        
        Args:
            user_id: 用户ID
        
        Returns:
            用户偏好字典，如果不存在返回None
        """
        try:
            item = self.store.get(
                namespace=("user_preferences",),
                key=user_id
            )
            return item.value if item else None
        except Exception as e:
            print(f"[StoreManager] 获取用户偏好失败: {e}")
            return None
    
    def put_user_preferences(
        self,
        user_id: str,
        preferences: Dict[str, Any]
    ) -> bool:
        """
        保存用户偏好
        
        Args:
            user_id: 用户ID
            preferences: 用户偏好字典
        
        Returns:
            是否保存成功
        """
        try:
            self.store.put(
                namespace=("user_preferences",),
                key=user_id,
                value=preferences
            )
            return True
        except Exception as e:
            print(f"[StoreManager] 保存用户偏好失败: {e}")
            return False
    
    def update_user_preferences(
        self,
        user_id: str,
        updates: Dict[str, Any]
    ) -> bool:
        """
        更新用户偏好（增量更新）
        
        Args:
            user_id: 用户ID
            updates: 要更新的字段
        
        Returns:
            是否更新成功
        """
        try:
            # 获取现有偏好
            current = self.get_user_preferences(user_id) or {}
            
            # 合并更新
            updated = {**current, **updates}
            
            # 保存
            return self.put_user_preferences(user_id, updated)
        except Exception as e:
            print(f"[StoreManager] 更新用户偏好失败: {e}")
            return False
    
    # ========== 问题历史 ==========
    
    def add_question_history(
        self,
        user_id: str,
        question: str,
        metadata: Optional[Dict[str, Any]] = None
    ) -> bool:
        """
        添加问题到历史记录
        
        Args:
            user_id: 用户ID
            question: 问题文本
            metadata: 额外的元数据（如datasource_luid、timestamp等）
        
        Returns:
            是否添加成功
        """
        try:
            # 生成唯一key（使用时间戳）
            key = f"q_{int(time.time() * 1000)}"
            
            # 构建数据
            data = {
                "question": question,
                "timestamp": time.time(),
                **(metadata or {})
            }
            
            self.store.put(
                namespace=("question_history", user_id),
                key=key,
                value=data
            )
            return True
        except Exception as e:
            print(f"[StoreManager] 添加问题历史失败: {e}")
            return False
    
    def search_question_history(
        self,
        user_id: str,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        语义搜索历史问题
        
        Args:
            user_id: 用户ID
            query: 查询文本
            limit: 返回结果数量
        
        Returns:
            相似问题列表
        """
        try:
            results = self.store.search(
                ("question_history", user_id),  # namespace_prefix作为位置参数
                query=query,
                limit=limit
            )
            
            # 转换为字典列表
            return [item.value for item in results]
        except Exception as e:
            print(f"[StoreManager] 搜索问题历史失败: {e}")
            return []
    
    def get_recent_questions(
        self,
        user_id: str,
        limit: int = 10
    ) -> List[Dict[str, Any]]:
        """
        获取最近的问题（按时间倒序）
        
        Args:
            user_id: 用户ID
            limit: 返回结果数量
        
        Returns:
            最近问题列表
        """
        try:
            # 使用search获取所有问题（query=None返回所有）
            # 使用max_search_limit避免超出LLM上下文限制
            items = self.store.search(
                ("question_history", user_id),  # namespace_prefix作为位置参数
                query=None,  # None查询返回所有
                limit=self.max_search_limit
            )
            
            # 按时间戳排序
            sorted_items = sorted(
                items,
                key=lambda x: x.value.get("timestamp", 0),
                reverse=True
            )
            
            # 返回前N个
            return [item.value for item in sorted_items[:limit]]
        except Exception as e:
            print(f"[StoreManager] 获取最近问题失败: {e}")
            return []
    
    # ========== 异常知识库 ==========
    
    def get_anomaly_explanation(
        self,
        anomaly_key: str
    ) -> Optional[Dict[str, Any]]:
        """
        获取异常解释
        
        Args:
            anomaly_key: 异常标识（如"low_profit_rate_east_region"）
        
        Returns:
            异常解释字典，如果不存在返回None
        """
        try:
            item = self.store.get(
                namespace=("anomaly_knowledge",),
                key=anomaly_key
            )
            return item.value if item else None
        except Exception as e:
            print(f"[StoreManager] 获取异常解释失败: {e}")
            return None
    
    def put_anomaly_explanation(
        self,
        anomaly_key: str,
        explanation: Dict[str, Any]
    ) -> bool:
        """
        保存异常解释
        
        Args:
            anomaly_key: 异常标识
            explanation: 异常解释字典（包含description、reason、suggestion等）
        
        Returns:
            是否保存成功
        """
        try:
            # 添加时间戳
            data = {
                **explanation,
                "_created_at": time.time()
            }
            
            self.store.put(
                namespace=("anomaly_knowledge",),
                key=anomaly_key,
                value=data
            )
            return True
        except Exception as e:
            print(f"[StoreManager] 保存异常解释失败: {e}")
            return False
    
    def search_anomaly_knowledge(
        self,
        query: str,
        limit: int = 5
    ) -> List[Dict[str, Any]]:
        """
        语义搜索异常知识库
        
        Args:
            query: 查询文本（如"利润率低"）
            limit: 返回结果数量
        
        Returns:
            相似异常列表
        """
        try:
            results = self.store.search(
                ("anomaly_knowledge",),  # namespace_prefix作为位置参数
                query=query,
                limit=limit
            )
            
            return [item.value for item in results]
        except Exception as e:
            print(f"[StoreManager] 搜索异常知识库失败: {e}")
            return []
    
    # ========== 工具方法 ==========
    
    def _is_valid(self, item: Item, ttl: int) -> bool:
        """
        检查缓存项是否有效（未过期）
        
        Args:
            item: Store中的Item
            ttl: 过期时间（秒）
        
        Returns:
            是否有效
        """
        if not item or not item.value:
            return False
        
        cached_at = item.value.get("_cached_at", 0)
        if cached_at == 0:
            return True  # 没有时间戳，认为永久有效
        
        return (time.time() - cached_at) < ttl
    
    def clear_metadata_cache(self, datasource_luid: str) -> bool:
        """
        清除指定数据源的元数据缓存
        
        Args:
            datasource_luid: 数据源LUID
        
        Returns:
            是否清除成功
        """
        try:
            # 清除元数据缓存
            self.store.delete(
                namespace=("metadata",),
                key=datasource_luid
            )
            
            # 清除维度层级缓存
            self.store.delete(
                namespace=("dimension_hierarchy",),
                key=datasource_luid
            )
            
            print(f"[StoreManager] 已清除数据源缓存: {datasource_luid}")
            return True
        except Exception as e:
            print(f"[StoreManager] 清除缓存失败: {e}")
            return False
    
    def clear_dimension_hierarchy_cache(self, datasource_luid: str) -> bool:
        """
        清除指定数据源的维度层级缓存
        
        Args:
            datasource_luid: 数据源LUID
        
        Returns:
            是否清除成功
        """
        try:
            # 清除维度层级缓存
            self.store.delete(
                namespace=("dimension_hierarchy",),
                key=datasource_luid
            )
            
            print(f"[StoreManager] 已清除维度层级缓存: {datasource_luid}")
            return True
        except Exception as e:
            print(f"[StoreManager] 清除维度层级缓存失败: {e}")
            return False
    
    def clear_namespace(self, namespace: tuple) -> bool:
        """
        清空指定命名空间的所有数据
        
        Args:
            namespace: 命名空间元组
        
        Returns:
            是否清空成功
        
        注意：
            InMemoryStore不支持list和delete方法，此功能暂不可用
        """
        try:
            # InMemoryStore不支持list和delete
            print(f"[StoreManager] 警告: InMemoryStore不支持clear_namespace")
            return False
        except Exception as e:
            print(f"[StoreManager] 清空命名空间失败: {e}")
            return False
    
    def get_stats(self) -> Dict[str, Any]:
        """
        获取Store统计信息
        
        Returns:
            统计信息字典
        """
        try:
            # 使用search(query=None)获取所有items并统计数量
            # 使用max_search_limit避免超出LLM上下文限制
            stats = {
                "metadata_count": len(self.store.search(("metadata",), query=None, limit=self.max_search_limit)),
                "dimension_hierarchy_count": len(self.store.search(("dimension_hierarchy",), query=None, limit=self.max_search_limit)),
                "user_preferences_count": len(self.store.search(("user_preferences",), query=None, limit=self.max_search_limit)),
                "anomaly_knowledge_count": len(self.store.search(("anomaly_knowledge",), query=None, limit=self.max_search_limit)),
            }
            return stats
        except Exception as e:
            print(f"[StoreManager] 获取统计信息失败: {e}")
            return {}





# 全局Store管理器实例（可选）
_global_store_manager: Optional[StoreManager] = None


def get_store_manager(store: Optional[InMemoryStore] = None) -> StoreManager:
    """
    获取全局Store管理器实例
    
    Args:
        store: InMemoryStore实例，如果为None则使用全局实例
    
    Returns:
        StoreManager实例
    """
    global _global_store_manager
    
    if store:
        return StoreManager(store)
    
    if _global_store_manager is None:
        _global_store_manager = StoreManager()
    
    return _global_store_manager


# 示例用法
if __name__ == "__main__":
    # 创建Store管理器
    manager = StoreManager()
    
    print("=" * 60)
    print("测试元数据缓存")
    print("=" * 60)
    
    # 保存元数据
    metadata = {
        "datasource_name": "Superstore",
        "fields": ["地区", "销售额", "利润"],
        "dimensions": ["地区"],
        "measures": ["销售额", "利润"]
    }
    manager.put_metadata("abc123", metadata)
    print("✓ 元数据已保存")
    
    # 获取元数据
    cached = manager.get_metadata("abc123")
    print(f"✓ 元数据已获取: {cached['datasource_name']}")
    
    print("\n" + "=" * 60)
    print("测试维度层级缓存")
    print("=" * 60)
    
    # 保存维度层级
    hierarchy = {
        "地区": {
            "category": "地理",
            "level": 1,
            "granularity": "粗粒度"
        }
    }
    manager.put_dimension_hierarchy("abc123", hierarchy)
    print("✓ 维度层级已保存")
    
    # 获取维度层级
    cached_hierarchy = manager.get_dimension_hierarchy("abc123")
    print(f"✓ 维度层级已获取: {list(cached_hierarchy.keys())}")
    
    print("\n" + "=" * 60)
    print("测试用户偏好")
    print("=" * 60)
    
    # 保存用户偏好
    preferences = {
        "detail_level": "high",
        "preferred_viz": "bar",
        "favorite_dimensions": ["地区", "产品类别"]
    }
    manager.put_user_preferences("user_456", preferences)
    print("✓ 用户偏好已保存")
    
    # 更新用户偏好
    manager.update_user_preferences("user_456", {"detail_level": "medium"})
    print("✓ 用户偏好已更新")
    
    # 获取用户偏好
    cached_prefs = manager.get_user_preferences("user_456")
    print(f"✓ 用户偏好已获取: detail_level={cached_prefs['detail_level']}")
    
    print("\n" + "=" * 60)
    print("测试问题历史")
    print("=" * 60)
    
    # 添加问题历史
    manager.add_question_history("user_456", "2016年各地区的销售额")
    manager.add_question_history("user_456", "2015年各地区的利润")
    manager.add_question_history("user_456", "华东地区的销售趋势")
    print("✓ 问题历史已添加")
    
    # 获取最近问题
    recent = manager.get_recent_questions("user_456", limit=3)
    print(f"✓ 最近问题: {len(recent)}个")
    for i, q in enumerate(recent):
        print(f"  {i+1}. {q['question']}")
    
    # 语义搜索
    similar = manager.search_question_history("user_456", "销售额", limit=2)
    print(f"✓ 相似问题: {len(similar)}个")
    for i, q in enumerate(similar):
        print(f"  {i+1}. {q['question']}")
    
    print("\n" + "=" * 60)
    print("测试异常知识库")
    print("=" * 60)
    
    # 保存异常解释
    anomaly = {
        "description": "华东地区利润率异常低",
        "reason": "促销活动导致折扣过大",
        "suggestion": "调整促销策略，提高利润率"
    }
    manager.put_anomaly_explanation("low_profit_rate_east", anomaly)
    print("✓ 异常解释已保存")
    
    # 获取异常解释
    cached_anomaly = manager.get_anomaly_explanation("low_profit_rate_east")
    print(f"✓ 异常解释已获取: {cached_anomaly['description']}")
    
    print("\n" + "=" * 60)
    print("Store统计信息")
    print("=" * 60)
    
    stats = manager.get_stats()
    for key, value in stats.items():
        print(f"  {key}: {value}")
