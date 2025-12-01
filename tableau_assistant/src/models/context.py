"""
VizQL运行时上下文定义

使用LangGraph 1.0的context_schema特性
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VizQLContext:
    """
    VizQL运行时上下文
    
    使用dataclass定义，通过LangGraph的context_schema传递
    这些数据在整个工作流中是不可变的，不会在节点间传递
    
    Attributes:
        datasource_luid: 数据源LUID
        user_id: 用户ID
        session_id: 会话ID
        max_replan_rounds: 最大重规划轮数（从配置文件读取）
        parallel_upper_limit: 并行任务上限（从配置文件读取）
        max_retry_times: 最大重试次数（从配置文件读取）
        max_subtasks_per_round: 每轮最大子任务数（从配置文件读取）
    
    注意：
        - tableau_token、tableau_site、tableau_domain通过StoreManager管理
        - 使用get_tableau_config()从Store获取Tableau配置
    """
    datasource_luid: str
    user_id: str
    session_id: str
    max_replan_rounds: int  # 从配置文件MAX_REPLAN_ROUNDS读取
    parallel_upper_limit: int  # 从配置文件PARALLEL_UPPER_LIMIT读取
    max_retry_times: int  # 从配置文件MAX_RETRY_TIMES读取
    max_subtasks_per_round: int  # 从配置文件MAX_SUBTASKS_PER_ROUND读取
    
    def __post_init__(self):
        """Validate required fields"""
        if not self.datasource_luid:
            raise ValueError("datasource_luid cannot be empty")
        if not self.user_id:
            raise ValueError("user_id cannot be empty")
        if not self.session_id:
            raise ValueError("session_id cannot be empty")
        if self.max_replan_rounds < 0:
            raise ValueError("max_replan_rounds must be >= 0")
        if self.parallel_upper_limit < 1:
            raise ValueError("parallel_upper_limit must be >= 1")
        if self.max_retry_times < 0:
            raise ValueError("max_retry_times必须>=0")
        if self.max_subtasks_per_round < 1:
            raise ValueError("max_subtasks_per_round必须>=1")
    
    @classmethod
    def from_config(
        cls,
        datasource_luid: str,
        user_id: str,
        session_id: str
    ) -> "VizQLContext":
        """
        从配置文件创建Context
        
        Args:
            datasource_luid: 数据源LUID
            user_id: 用户ID
            session_id: 会话ID
        
        Returns:
            VizQLContext实例
        
        注意：
            tableau_token、tableau_site、tableau_domain通过StoreManager管理
        """
        from tableau_assistant.src.config.settings import settings
        
        return cls(
            datasource_luid=datasource_luid,
            user_id=user_id,
            session_id=session_id,
            max_replan_rounds=settings.max_replan_rounds,
            parallel_upper_limit=settings.parallel_upper_limit,
            max_retry_times=settings.max_retry_times,
            max_subtasks_per_round=settings.max_subtasks_per_round
        )


def get_tableau_config(store_manager) -> dict:
    """
    从StoreManager获取Tableau配置
    
    Args:
        store_manager: StoreManager实例
    
    Returns:
        Tableau配置字典，包含token、site、domain
    """
    # 从Store获取Tableau配置
    config = store_manager.store.get(
        namespace=("tableau_config",),
        key="current"
    )
    
    if config and config.value:
        return config.value
    
    # 如果Store中没有，从配置文件读取
    from tableau_assistant.src.config.settings import settings
    return {
        "tableau_token": settings.tableau_token,
        "tableau_site": settings.tableau_site,
        "tableau_domain": settings.tableau_domain
    }


def set_tableau_config(store_manager, tableau_token: str, tableau_site: str, tableau_domain: str) -> bool:
    """
    保存Tableau配置到StoreManager
    
    Args:
        store_manager: StoreManager实例
        tableau_token: Tableau认证token
        tableau_site: Tableau站点
        tableau_domain: Tableau域名
    
    Returns:
        是否保存成功
    """
    try:
        store_manager.store.put(
            namespace=("tableau_config",),
            key="current",
            value={
                "tableau_token": tableau_token,
                "tableau_site": tableau_site,
                "tableau_domain": tableau_domain
            }
        )
        return True
    except Exception as e:
        logger.error(f"保存Tableau配置失败: {e}")
        return False


# 示例用法
if __name__ == "__main__":
    # 方式1：直接创建context
    context = VizQLContext(
        datasource_luid="abc123",
        user_id="user_456",
        session_id="session_789",
        max_replan_rounds=3,
        parallel_upper_limit=3,
        max_retry_times=2,
        max_subtasks_per_round=10
    )
    
    print(f"Context创建成功:")
    print(f"  数据源: {context.datasource_luid}")
    print(f"  用户: {context.user_id}")
    print(f"  会话: {context.session_id}")
    print(f"  最大重规划轮数: {context.max_replan_rounds}")
    print(f"  并行上限: {context.parallel_upper_limit}")
    
    # 方式2：从配置文件创建context（推荐）
    print("\n从配置文件创建context:")
    context2 = VizQLContext.from_config(
        datasource_luid="abc123",
        user_id="user_456",
        session_id="session_789"
    )
    print(f"  最大重规划轮数（从配置读取）: {context2.max_replan_rounds}")
