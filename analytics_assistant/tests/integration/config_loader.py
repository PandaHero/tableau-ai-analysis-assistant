"""Integration test configuration loader."""

from __future__ import annotations

import logging
import os
import re
from pathlib import Path
from typing import Any, Dict, Optional

import yaml

logger = logging.getLogger(__name__)


class TestConfigLoader:
    """Load and query integration-test config."""

    _config: Optional[Dict[str, Any]] = None

    @classmethod
    def _get_project_root(cls) -> Path:
        return Path(__file__).resolve().parents[3]

    @classmethod
    def _resolve_repo_path(cls, value: str) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return cls._get_project_root() / path

    @classmethod
    def load_config(cls, config_path: Optional[Path] = None) -> Dict[str, Any]:
        if cls._config is not None:
            return cls._config

        if config_path is None:
            config_path = Path(__file__).parent / "test_config.yaml"

        if not config_path.exists():
            raise FileNotFoundError(f"配置文件不存在: {config_path}")

        logger.info("加载测试配置: %s", config_path)
        with open(config_path, "r", encoding="utf-8") as file:
            config = yaml.safe_load(file)

        cls._replace_env_vars(config)
        cls._validate_config(config)
        cls._config = config
        return config

    @classmethod
    def _replace_env_vars(cls, config: Dict[str, Any]) -> None:
        env_var_pattern = re.compile(r"\$\{([^}]+)\}")

        def replace_value(value: Any) -> Any:
            if not isinstance(value, str):
                return value
            for var_name in env_var_pattern.findall(value):
                env_value = os.environ.get(var_name)
                if env_value is not None:
                    value = value.replace(f"${{{var_name}}}", env_value)
                else:
                    logger.warning("环境变量未设置: %s", var_name)
            return value

        def replace_recursive(obj: Any) -> Any:
            if isinstance(obj, dict):
                for key, value in obj.items():
                    obj[key] = replace_recursive(value)
                return obj
            if isinstance(obj, list):
                return [replace_recursive(item) for item in obj]
            return replace_value(obj)

        replace_recursive(config)

    @classmethod
    def _validate_config(cls, config: Dict[str, Any]) -> None:
        required_keys = ["mode", "timeouts", "database", "test_data"]
        for key in required_keys:
            if key not in config:
                raise ValueError(f"配置缺少必需键: {key}")

    @classmethod
    def get_timeout(cls, operation: str) -> float:
        config = cls.load_config()
        timeouts = config.get("timeouts", {})
        return timeouts.get(operation, timeouts.get("default", 60.0))

    @classmethod
    def get_test_data_dir(cls) -> Path:
        config = cls.load_config()
        return cls._resolve_repo_path(config["test_data"]["dir"])

    @classmethod
    def get_database_path(cls, db_name: str = "test_storage") -> Path:
        config = cls.load_config()
        return cls._resolve_repo_path(config["database"][db_name])

    @classmethod
    def get_log_file_path(cls) -> Path:
        config = cls.load_config()
        logging_config = config.get("logging", {})
        log_file = logging_config.get(
            "file",
            "analytics_assistant/tests/test_outputs/integration_tests.log",
        )
        return cls._resolve_repo_path(log_file)

    @classmethod
    def get_tableau_config(cls) -> Dict[str, Any]:
        config = cls.load_config()
        return config.get("tableau", {})

    @classmethod
    def get_performance_config(cls) -> Dict[str, Any]:
        config = cls.load_config()
        return config.get("performance", {})

    @classmethod
    def get_performance_baseline_path(cls) -> Path:
        performance_config = cls.get_performance_config()
        baseline_file = performance_config.get(
            "baseline_file",
            "analytics_assistant/tests/test_outputs/performance_baseline.json",
        )
        return cls._resolve_repo_path(baseline_file)

    @classmethod
    def get_retry_config(cls) -> Dict[str, Any]:
        config = cls.load_config()
        return config.get("retry", {})

    @classmethod
    def get_hypothesis_config(cls) -> Dict[str, Any]:
        config = cls.load_config()
        return config.get("hypothesis", {})

    @classmethod
    def is_performance_monitoring_enabled(cls) -> bool:
        return cls.get_performance_config().get("enable_monitoring", True)

    @classmethod
    def get_mode(cls) -> str:
        config = cls.load_config()
        return config.get("mode", "integration")

    @classmethod
    def reload_config(cls) -> None:
        cls._config = None
        logger.info("配置缓存已清除，将重新加载")

    @staticmethod
    def _is_env_flag_enabled(env_name: str) -> bool:
        return os.environ.get(env_name, "").strip().lower() in {
            "1",
            "true",
            "yes",
            "on",
        }

    @classmethod
    def allow_real_llm_tests(cls) -> bool:
        return cls._is_env_flag_enabled(
            "AA_RUN_EXTERNAL_INTEGRATION_TESTS"
        ) or cls._is_env_flag_enabled("AA_RUN_REAL_LLM_TESTS")

    @classmethod
    def allow_tableau_integration_tests(cls) -> bool:
        return cls._is_env_flag_enabled(
            "AA_RUN_EXTERNAL_INTEGRATION_TESTS"
        ) or cls._is_env_flag_enabled("AA_RUN_TABLEAU_INTEGRATION_TESTS")
