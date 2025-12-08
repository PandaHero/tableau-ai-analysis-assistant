"""
测试环境管理器

负责创建和管理测试所需的运行时环境，包括：
- Runtime环境
- Store Manager
- DataModelManager
- Tableau配置
"""
import os
import sys
from pathlib import Path
from typing import Optional
from dotenv import load_dotenv

from langgraph.runtime import Runtime
from tableau_assistant.src.models.workflow.context import VizQLContext, set_tableau_config
from tableau_assistant.src.capabilities.storage import StoreManager
from tableau_assistant.src.capabilities.data_model import DataModelManager


class TestEnvironment:
    """
    测试环境管理器
    
    负责创建和配置测试所需的所有组件，提供统一的环境管理接口
    
    Attributes:
        runtime: LangGraph Runtime实例
        store_manager: Store Manager实例
        data_model_manager: DataModelManager实例
        datasource_luid: 数据源LUID
        tableau_config: Tableau配置信息
    """
    
    def __init__(self, use_persistent_store: bool = True, db_path: str = "data/test_store.db"):
        """
        初始化测试环境管理器
        
        Args:
            use_persistent_store: 是否使用持久化存储（默认True）
            db_path: 数据库文件路径（仅在use_persistent_store=True时使用）
        """
        self.runtime: Optional[Runtime] = None
        self.store_manager: Optional[StoreManager] = None
        self.data_model_manager: Optional[DataModelManager] = None
        self.datasource_luid: Optional[str] = None
        self.tableau_config: Optional[dict] = None
        self.use_persistent_store = use_persistent_store
        self.db_path = db_path
        self.store: Optional[StoreManager] = None
        self._is_setup = False
    
    async def setup(self) -> bool:
        """
        设置测试环境
        
        执行以下操作：
        1. 设置UTF-8编码（Windows平台）
        2. 加载环境变量
        3. 创建Runtime环境
        4. 初始化Store Manager
        5. 初始化Metadata Manager
        6. 设置Tableau配置
        
        Returns:
            bool: 是否成功设置环境
        
        Raises:
            ValueError: 如果缺少必要的环境变量
            Exception: 如果设置过程中发生错误
        """
        try:
            # 1. 设置UTF-8编码（Windows平台）
            self._setup_encoding()
            
            # 2. 加载环境变量
            load_dotenv()
            
            # 3. 验证必要的环境变量
            self.datasource_luid = os.getenv("DATASOURCE_LUID")
            if not self.datasource_luid:
                raise ValueError(
                    "缺少必要的环境变量: DATASOURCE_LUID\n"
                    "请在.env文件中设置DATASOURCE_LUID"
                )
            
            # 4. 创建Runtime环境
            self._create_runtime()
            
            # 5. 初始化Store Manager
            self._initialize_store_manager()
            
            # 6. 初始化 DataModelManager
            self._initialize_data_model_manager()
            
            # 7. 设置Tableau配置
            self._setup_tableau_config()
            
            self._is_setup = True
            return True
            
        except Exception as e:
            print(f"✗ 环境设置失败: {str(e)}")
            raise
    
    def _setup_encoding(self):
        """设置UTF-8编码（Windows平台）"""
        # 注意：如果在主脚本中已经设置了编码，这里就不需要再设置
        # 避免重复包装stdout导致问题
        if sys.platform == 'win32':
            try:
                # 检查是否已经设置了UTF-8编码
                if hasattr(sys.stdout, 'buffer') and sys.stdout.encoding != 'utf-8':
                    import io
                    sys.stdout = io.TextIOWrapper(sys.stdout.buffer, encoding='utf-8')
                    sys.stderr = io.TextIOWrapper(sys.stderr.buffer, encoding='utf-8')
            except Exception:
                # 如果设置失败，忽略（可能已经设置过）
                pass
    
    def _create_runtime(self):
        """创建Runtime环境"""
        # 创建Store（统一使用 StoreManager，基于 SQLite 持久化）
        self.store = StoreManager(db_path=self.db_path)
        print(f"✓ 使用持久化存储: {self.db_path}")
        
        # 创建VizQLContext
        context = VizQLContext(
            datasource_luid=self.datasource_luid,
            user_id="test_user",
            session_id="test_session",
            max_replan_rounds=3,
            parallel_upper_limit=3,
            max_retry_times=3,
            max_subtasks_per_round=10
        )
        
        # 创建Runtime
        self.runtime = Runtime(
            context=context,
            store=self.store
        )
    
    def _initialize_store_manager(self):
        """初始化Store Manager"""
        if not self.runtime:
            raise RuntimeError("Runtime未初始化")
        
        self.store_manager = StoreManager(self.runtime.store)
    
    def _initialize_data_model_manager(self):
        """初始化 DataModelManager"""
        if not self.runtime:
            raise RuntimeError("Runtime未初始化")
        
        self.data_model_manager = DataModelManager(self.runtime)
    
    def _setup_tableau_config(self):
        """设置Tableau配置"""
        if not self.store_manager:
            raise RuntimeError("Store Manager未初始化")
        
        # 从环境变量获取Tableau配置
        from tableau_assistant.src.utils.tableau.auth import _get_tableau_context_from_env
        tableau_ctx = _get_tableau_context_from_env()
        
        # 保存配置信息
        self.tableau_config = {
            "tableau_token": tableau_ctx.get("api_key", ""),
            "tableau_site": tableau_ctx.get("site", ""),
            "tableau_domain": tableau_ctx.get("domain", "")
        }
        
        # 设置Tableau配置到Store
        set_tableau_config(
            store_manager=self.store_manager,
            tableau_token=self.tableau_config["tableau_token"],
            tableau_site=self.tableau_config["tableau_site"],
            tableau_domain=self.tableau_config["tableau_domain"]
        )
    
    async def teardown(self):
        """
        清理测试环境
        
        执行以下操作：
        1. 清理缓存
        2. 关闭连接
        3. 重置状态
        """
        try:
            # 清理元数据缓存
            if self.store_manager and self.datasource_luid:
                self.store_manager.clear_metadata_cache(self.datasource_luid)
            
            # 关闭持久化存储连接
            if self.store and hasattr(self.store, 'close'):
                self.store.close()
                print("✓ 持久化存储连接已关闭")
            
            # 重置状态
            self.runtime = None
            self.store_manager = None
            self.data_model_manager = None
            self.datasource_luid = None
            self.tableau_config = None
            self.store = None
            self._is_setup = False
            
        except Exception as e:
            print(f"⚠️  环境清理时发生错误: {str(e)}")
    
    def get_runtime(self) -> Runtime:
        """
        获取Runtime实例
        
        Returns:
            Runtime实例
        
        Raises:
            RuntimeError: 如果环境未设置
        """
        if not self._is_setup or not self.runtime:
            raise RuntimeError("环境未设置，请先调用setup()")
        return self.runtime
    
    def get_store_manager(self) -> StoreManager:
        """
        获取Store Manager实例
        
        Returns:
            StoreManager实例
        
        Raises:
            RuntimeError: 如果环境未设置
        """
        if not self._is_setup or not self.store_manager:
            raise RuntimeError("环境未设置，请先调用setup()")
        return self.store_manager
    
    def get_data_model_manager(self) -> DataModelManager:
        """
        获取 DataModelManager 实例
        
        Returns:
            DataModelManager 实例
        
        Raises:
            RuntimeError: 如果环境未设置
        """
        if not self._is_setup or not self.data_model_manager:
            raise RuntimeError("环境未设置，请先调用setup()")
        return self.data_model_manager
    
    def get_datasource_luid(self) -> str:
        """
        获取数据源LUID
        
        Returns:
            数据源LUID
        
        Raises:
            RuntimeError: 如果环境未设置
        """
        if not self._is_setup or not self.datasource_luid:
            raise RuntimeError("环境未设置，请先调用setup()")
        return self.datasource_luid
    
    def get_tableau_config(self) -> dict:
        """
        获取Tableau配置
        
        Returns:
            Tableau配置字典
        
        Raises:
            RuntimeError: 如果环境未设置
        """
        if not self._is_setup or not self.tableau_config:
            raise RuntimeError("环境未设置，请先调用setup()")
        return self.tableau_config
    
    def is_setup(self) -> bool:
        """
        检查环境是否已设置
        
        Returns:
            bool: 是否已设置
        """
        return self._is_setup
    
    def get_environment_info(self) -> dict:
        """
        获取环境信息
        
        Returns:
            环境信息字典
        """
        if not self._is_setup:
            return {"status": "not_setup"}
        
        info = {
            "status": "ready",
            "datasource_luid": self.datasource_luid,
            "tableau_domain": self.tableau_config.get("tableau_domain", ""),
            "tableau_site": self.tableau_config.get("tableau_site", ""),
            "platform": sys.platform,
            "python_version": sys.version,
            "store_type": "persistent" if self.use_persistent_store else "memory",
        }
        
        # 如果使用持久化存储，添加数据库信息
        if self.use_persistent_store and self.store:
            info["db_path"] = self.db_path
            if hasattr(self.store, 'get_stats'):
                stats = self.store.get_stats()
                info["db_size_mb"] = stats.get("db_size_mb", 0)
                info["total_records"] = stats.get("total_count", 0)
        
        return info


# ============= 导出 =============

__all__ = [
    "TestEnvironment",
]
