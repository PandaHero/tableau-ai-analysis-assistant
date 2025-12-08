"""
VizQL Runtime Context Definition

Uses LangGraph 1.0 context_schema feature
"""
import logging
from dataclasses import dataclass
from typing import Optional

logger = logging.getLogger(__name__)


@dataclass
class VizQLContext:
    """
    VizQL Runtime Context
    
    Defined using dataclass, passed through LangGraph's context_schema.
    This data is immutable throughout the workflow and not passed between nodes.
    
    Attributes:
        datasource_luid: Datasource LUID
        user_id: User ID
        session_id: Session ID
        max_replan_rounds: Maximum replan rounds (from config)
        parallel_upper_limit: Parallel task upper limit (from config)
        max_retry_times: Maximum retry times (from config)
        max_subtasks_per_round: Maximum subtasks per round (from config)
    
    Note:
        - tableau_token, tableau_site, tableau_domain are managed through StoreManager
        - Use get_tableau_config() to get Tableau config from Store
    """
    datasource_luid: str
    user_id: str
    session_id: str
    max_replan_rounds: int
    parallel_upper_limit: int
    max_retry_times: int
    max_subtasks_per_round: int
    
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
            raise ValueError("max_retry_times must be >= 0")
        if self.max_subtasks_per_round < 1:
            raise ValueError("max_subtasks_per_round must be >= 1")
    
    @classmethod
    def from_config(
        cls,
        datasource_luid: str,
        user_id: str,
        session_id: str
    ) -> "VizQLContext":
        """
        Create Context from config file
        
        Args:
            datasource_luid: Datasource LUID
            user_id: User ID
            session_id: Session ID
        
        Returns:
            VizQLContext instance
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
    Get Tableau config from StoreManager
    
    Args:
        store_manager: StoreManager instance
    
    Returns:
        Tableau config dict containing token, site, domain
    """
    # 兼容两种模式：store_manager 本身就是 StoreManager，或者有 .store 属性
    store = getattr(store_manager, 'store', store_manager)
    
    config = store.get(
        namespace=("tableau_config",),
        key="current"
    )
    
    if config and config.value:
        return config.value
    
    # Fallback to config file
    from tableau_assistant.src.config.settings import settings
    return {
        "tableau_token": settings.tableau_token,
        "tableau_site": settings.tableau_site,
        "tableau_domain": settings.tableau_domain
    }


def set_tableau_config(
    store_manager,
    tableau_token: str,
    tableau_site: str,
    tableau_domain: str
) -> bool:
    """
    Save Tableau config to StoreManager
    
    Args:
        store_manager: StoreManager instance
        tableau_token: Tableau auth token
        tableau_site: Tableau site
        tableau_domain: Tableau domain
    
    Returns:
        Whether save was successful
    """
    try:
        # 兼容两种模式：store_manager 本身就是 StoreManager，或者有 .store 属性
        store = getattr(store_manager, 'store', store_manager)
        
        store.put(
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
        logger.error(f"Failed to save Tableau config: {e}")
        return False
