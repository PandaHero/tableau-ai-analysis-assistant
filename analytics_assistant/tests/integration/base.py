"""集成测试基类

提供所有集成测试的通用基础设施：
- 真实服务连接管理
- 测试数据库隔离
- 性能指标收集
- 测试日志记录
- 测试前后清理
"""

from abc import ABC
import gc
import logging
import time
from pathlib import Path
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.infra.storage import (
    StoreFactory,
    get_kv_store,
    reset_kv_store,
)
from analytics_assistant.src.agents.base.node import get_llm
from analytics_assistant.src.infra.ai import get_embeddings
from analytics_assistant.src.platform.tableau.adapter import TableauAdapter
from analytics_assistant.src.orchestration.workflow.context import WorkflowContext
from analytics_assistant.tests.integration.config_loader import TestConfigLoader


logger = logging.getLogger(__name__)


class BaseIntegrationTest(ABC):
    """集成测试基类
    
    提供：
    - 真实服务连接管理（LLM、Embedding、Tableau）
    - 测试数据库隔离（独立的测试数据库文件）
    - 性能指标收集（耗时、内存、API 调用次数）
    - 测试日志记录（详细的调试日志）
    - 测试前后清理（自动清理测试数据）
    
    使用方式：
        class TestMyFeature(BaseIntegrationTest):
            def test_something(self):
                # 使用 self._llm, self._embeddings, self._workflow_context
                ...
    """
    
    # 类级别的共享资源（session scope）
    _config: Optional[dict[str, Any]] = None
    _llm = None
    _embeddings = None
    _tableau_adapter: Optional[TableauAdapter] = None
    _workflow_context: Optional[WorkflowContext] = None
    
    @classmethod
    def setup_class(cls):
        """类级别的设置（所有测试开始前执行一次）
        
        初始化共享资源：
        - 加载配置
        - 创建 LLM 和 Embedding 连接
        - 设置测试数据库
        - 配置测试日志
        """
        logger.info(f"设置测试类: {cls.__name__}")
        
        # 加载配置
        cls._config = get_config()
        
        # 创建 LLM 和 Embedding 连接（session 级别共享）
        cls._llm = get_llm()
        cls._embeddings = get_embeddings()
        
        # 设置测试数据库
        cls._setup_test_database()
        
        # 设置测试日志
        cls._setup_test_logger()
        
        logger.info(f"测试类设置完成: {cls.__name__}")
    
    @classmethod
    def teardown_class(cls):
        """类级别的清理（所有测试结束后执行一次）
        
        清理共享资源：
        - 清理测试数据库
        - 关闭连接
        """
        logger.info(f"清理测试类: {cls.__name__}")
        cls._cleanup_test_database()
        logger.info(f"测试类清理完成: {cls.__name__}")
    
    def setup_method(self, method):
        """方法级别的设置（每个测试开始前执行）
        
        为每个测试初始化：
        - 记录开始时间
        - 初始化性能指标字典
        - 创建独立的 WorkflowContext
        """
        self._start_time = time.time()
        self._test_metrics = {}
        self._setup_workflow_context()
        
        test_name = self.__class__.__name__ + "." + method.__name__
        self._test_name = test_name  # 保存测试名称供 teardown 使用
        logger.info(f"开始测试: {test_name}")
    
    def teardown_method(self, method):
        """方法级别的清理（每个测试结束后执行）
        
        记录测试指标：
        - 计算耗时
        - 记录性能指标
        """
        elapsed = time.time() - self._start_time
        self._test_metrics["elapsed_time"] = elapsed
        self._log_test_metrics()
        
        test_name = self.__class__.__name__ + "." + method.__name__
        logger.info(f"测试完成: {test_name}, 耗时: {elapsed:.2f}s")
    
    @classmethod
    def _remove_test_database_file(
        cls,
        test_db_path: Path,
        *,
        required: bool,
    ) -> None:
        """删除测试数据库文件，兼容 Windows 文件句柄释放延迟。"""
        if not test_db_path.exists():
            return

        logger.info(f"清理旧的测试数据库: {test_db_path}")
        gc.collect()
        last_error: Optional[PermissionError] = None
        for attempt in range(10):
            try:
                test_db_path.unlink()
                return
            except PermissionError as exc:
                last_error = exc
                logger.warning(
                    f"测试数据库仍被占用，稍后重试: path={test_db_path}, "
                    f"attempt={attempt + 1}"
                )
                time.sleep(0.3)

        if last_error is not None and required:
            raise last_error
        if last_error is not None:
            logger.warning(
                f"测试数据库清理失败，保留文件供后续 setup 重试: {test_db_path}"
            )

    @classmethod
    def _setup_test_database(cls):
        """设置独立的测试数据库
        
        使用测试专用的数据库路径，避免污染生产数据。
        如果旧的测试数据库存在，先清理。
        """
        test_db_path = TestConfigLoader.get_database_path("test_storage")

        # 先释放可能残留的 SQLite 连接，避免 Windows 上删除文件失败。
        reset_kv_store()
        StoreFactory.reset()

        # 清理旧的测试数据
        cls._remove_test_database_file(test_db_path, required=True)

        # 确保测试数据目录存在
        test_db_path.parent.mkdir(parents=True, exist_ok=True)

        # 测试必须显式重置并绑定到独立数据库，避免污染默认存储。
        reset_kv_store()
        get_kv_store(str(test_db_path))
        
        logger.info(f"测试数据库路径: {test_db_path}")
    
    @classmethod
    def _cleanup_test_database(cls):
        """清理测试数据库
        
        测试结束后删除测试数据库文件。
        """
        test_db_path = TestConfigLoader.get_database_path("test_storage")
        reset_kv_store()
        StoreFactory.reset()
        cls._remove_test_database_file(test_db_path, required=False)
    
    @classmethod
    def _setup_test_logger(cls):
        """设置测试日志
        
        配置日志输出到文件和控制台：
        - 文件日志: DEBUG 级别，包含详细信息
        - 控制台日志: INFO 级别，显示关键信息
        """
        log_path = TestConfigLoader.get_log_file_path()
        log_path.parent.mkdir(parents=True, exist_ok=True)
        
        # 配置日志格式
        log_format = "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
        
        # 配置日志处理器
        logging.basicConfig(
            level=logging.DEBUG,
            format=log_format,
            handlers=[
                logging.FileHandler(log_path, encoding="utf-8"),
                logging.StreamHandler(),
            ],
            force=True,  # 强制重新配置
        )
        
        logger.info(f"测试日志路径: {log_path}")
    
    def _setup_workflow_context(self):
        """设置工作流上下文
        
        每个测试使用独立的 WorkflowContext，避免测试之间的状态污染。
        """
        datasource_luid = self._get_test_datasource_luid()
        self._workflow_context = WorkflowContext(
            datasource_luid=datasource_luid,
        )
        logger.debug(f"创建 WorkflowContext: datasource_luid={datasource_luid}")
    
    def _get_test_datasource_luid(self) -> str:
        """获取测试数据源 LUID
        
        从测试配置中读取测试数据源 LUID。
        如果未配置，返回空字符串。
        
        Returns:
            测试数据源的 LUID
        """
        tableau_config = TestConfigLoader.get_tableau_config()
        datasource_luid = tableau_config.get("test_datasource_luid", "")
        
        if datasource_luid and "${" not in datasource_luid:
            return datasource_luid
        
        resolved_luid = getattr(self.__class__, "_resolved_datasource_luid", "")
        if resolved_luid:
            return resolved_luid

        datasource_name = tableau_config.get("test_datasource_name", "")
        if datasource_name:
            logger.warning(
                f"test_datasource_luid 未显式配置，将依赖运行时解析数据源名称: {datasource_name}"
            )
        else:
            logger.warning("未配置 test_datasource_luid，某些测试可能失败")
        return ""
    
    def _log_test_metrics(self):
        """记录测试指标
        
        输出测试的性能指标到日志。
        """
        # 从 _test_metrics 中获取测试名称（在 setup_method 中设置）
        test_name = getattr(self, '_test_name', self.__class__.__name__)
        logger.info(f"测试指标 [{test_name}]: {self._test_metrics}")
    
    def _record_metric(self, name: str, value: Any):
        """记录性能指标
        
        Args:
            name: 指标名称
            value: 指标值
        """
        self._test_metrics[name] = value
        logger.debug(f"记录指标: {name}={value}")
