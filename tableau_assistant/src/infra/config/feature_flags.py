"""vNext 灰度开关配置。

本模块实现 vNext 功能的灰度开关和回滚机制，确保工程可控性。

设计原则（Requirements 0.14）：
- 新功能写入新 namespace，不覆盖旧键
- 回滚只需关闭开关 + 删除/忽略新 namespace
- 数据最小化，不落盘敏感信息

灰度开关：
- SEMANTIC_PARSER_VNEXT_ENABLED: vNext 总开关（默认 False）
- INTENT_ROUTER_ENABLED: IntentRouter 开关（默认 False）
- SCHEMA_LINKING_ENABLED: Schema Linking 开关（默认 False）
- COMPUTATION_PLANNER_ENABLED: ComputationPlanner 开关（默认 False）
- VALIDATOR_ENABLED: Validator 开关（默认 False）

请求级别覆盖：
- X-Semantic-Parser-Version: vnext → 强制使用 vNext
- X-Semantic-Parser-Version: legacy → 强制使用旧链路

Usage:
    from tableau_assistant.src.infra.config.feature_flags import feature_flags
    
    if feature_flags.semantic_parser_vnext_enabled:
        # 使用 vNext 链路
        pass
    else:
        # 使用旧链路
        pass
    
    # 请求级别覆盖
    version = feature_flags.get_version_from_request(request_headers)
    if version == "vnext":
        # 强制使用 vNext
        pass
"""

import logging
import os
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from pydantic_settings import BaseSettings, SettingsConfigDict

logger = logging.getLogger(__name__)


class SemanticParserVersion(str, Enum):
    """语义解析器版本枚举。"""
    LEGACY = "legacy"
    VNEXT = "vnext"


class FeatureFlags(BaseSettings):
    """vNext 灰度开关配置。
    
    支持通过环境变量控制各功能开关。
    
    Attributes:
        semantic_parser_vnext_enabled: vNext 总开关
        intent_router_enabled: IntentRouter 开关
        schema_linking_enabled: Schema Linking 开关
        computation_planner_enabled: ComputationPlanner 开关
        validator_enabled: Validator 开关
    """
    
    # 总开关
    semantic_parser_vnext_enabled: bool = False
    
    # 子功能开关
    intent_router_enabled: bool = False
    schema_linking_enabled: bool = False
    computation_planner_enabled: bool = False
    validator_enabled: bool = False
    
    # Schema Linking 配置
    schema_linking_min_candidates: int = 1
    schema_linking_min_confidence: float = 0.5
    schema_linking_timeout_ms: int = 2000
    schema_linking_min_term_hit_ratio: float = 0.3
    
    # IntentRouter 配置
    intent_router_l1_confidence_threshold: float = 0.8
    intent_router_enable_l1: bool = False
    
    model_config = SettingsConfigDict(
        env_prefix="",  # 直接使用环境变量名
        case_sensitive=False,
        extra="ignore",
    )
    
    def is_feature_enabled(self, feature_name: str) -> bool:
        """检查指定功能是否启用。
        
        Args:
            feature_name: 功能名称
        
        Returns:
            是否启用
        """
        # 总开关必须开启
        if not self.semantic_parser_vnext_enabled:
            return False
        
        # 检查子功能开关
        feature_map = {
            "intent_router": self.intent_router_enabled,
            "schema_linking": self.schema_linking_enabled,
            "computation_planner": self.computation_planner_enabled,
            "validator": self.validator_enabled,
        }
        
        return feature_map.get(feature_name, False)
    
    def get_version_from_request(
        self,
        headers: Optional[Dict[str, str]] = None,
    ) -> SemanticParserVersion:
        """从请求头获取版本覆盖。
        
        支持请求级别的灰度控制：
        - X-Semantic-Parser-Version: vnext → 强制使用 vNext
        - X-Semantic-Parser-Version: legacy → 强制使用旧链路
        
        Args:
            headers: 请求头字典
        
        Returns:
            语义解析器版本
        """
        if headers:
            version_header = headers.get("X-Semantic-Parser-Version", "").lower()
            if version_header == "vnext":
                logger.info("Request-level override: using vNext")
                return SemanticParserVersion.VNEXT
            elif version_header == "legacy":
                logger.info("Request-level override: using legacy")
                return SemanticParserVersion.LEGACY
        
        # 使用全局配置
        if self.semantic_parser_vnext_enabled:
            return SemanticParserVersion.VNEXT
        return SemanticParserVersion.LEGACY
    
    def should_use_vnext(
        self,
        headers: Optional[Dict[str, str]] = None,
        config: Optional[Dict[str, Any]] = None,
    ) -> bool:
        """判断是否应该使用 vNext 链路。
        
        优先级：
        1. 请求头覆盖（X-Semantic-Parser-Version）
        2. config 中的 force_vnext 标志
        3. 全局开关
        
        Args:
            headers: 请求头字典
            config: LangGraph 配置
        
        Returns:
            是否使用 vNext
        """
        # 1. 请求头覆盖
        if headers:
            version_header = headers.get("X-Semantic-Parser-Version", "").lower()
            if version_header == "vnext":
                return True
            elif version_header == "legacy":
                return False
        
        # 2. config 中的 force_vnext 标志
        if config:
            configurable = config.get("configurable", {})
            if configurable.get("force_vnext"):
                return True
            if configurable.get("force_legacy"):
                return False
        
        # 3. 全局开关
        return self.semantic_parser_vnext_enabled


# 全局实例
feature_flags = FeatureFlags()


@dataclass
class FeatureFlagChangeLog:
    """功能开关变更日志。
    
    用于记录灰度开关状态变更。
    """
    timestamp: datetime
    feature_name: str
    old_value: bool
    new_value: bool
    source: str  # "env" / "api" / "config"
    
    def to_dict(self) -> Dict[str, Any]:
        """转换为字典。"""
        return {
            "timestamp": self.timestamp.isoformat(),
            "feature_name": self.feature_name,
            "old_value": self.old_value,
            "new_value": self.new_value,
            "source": self.source,
        }


class FeatureFlagManager:
    """功能开关管理器。
    
    提供功能开关的动态更新和变更日志记录。
    """
    
    def __init__(self):
        self._change_logs: List[FeatureFlagChangeLog] = []
    
    def update_flag(
        self,
        feature_name: str,
        new_value: bool,
        source: str = "api",
    ) -> bool:
        """更新功能开关。
        
        Args:
            feature_name: 功能名称
            new_value: 新值
            source: 变更来源
        
        Returns:
            是否更新成功
        """
        global feature_flags
        
        # 获取旧值
        old_value = getattr(feature_flags, feature_name, None)
        if old_value is None:
            logger.error(f"Unknown feature flag: {feature_name}")
            return False
        
        # 更新值
        setattr(feature_flags, feature_name, new_value)
        
        # 记录变更日志
        change_log = FeatureFlagChangeLog(
            timestamp=datetime.now(),
            feature_name=feature_name,
            old_value=old_value,
            new_value=new_value,
            source=source,
        )
        self._change_logs.append(change_log)
        
        logger.info(
            f"Feature flag updated: {feature_name} = {new_value}",
            extra=change_log.to_dict(),
        )
        
        return True
    
    def get_change_logs(
        self,
        limit: int = 100,
    ) -> List[FeatureFlagChangeLog]:
        """获取变更日志。
        
        Args:
            limit: 返回数量限制
        
        Returns:
            变更日志列表
        """
        return self._change_logs[-limit:]
    
    def get_current_state(self) -> Dict[str, Any]:
        """获取当前所有开关状态。
        
        Returns:
            开关状态字典
        """
        return {
            "semantic_parser_vnext_enabled": feature_flags.semantic_parser_vnext_enabled,
            "intent_router_enabled": feature_flags.intent_router_enabled,
            "schema_linking_enabled": feature_flags.schema_linking_enabled,
            "computation_planner_enabled": feature_flags.computation_planner_enabled,
            "validator_enabled": feature_flags.validator_enabled,
        }


# 全局管理器实例
feature_flag_manager = FeatureFlagManager()


__all__ = [
    "FeatureFlags",
    "SemanticParserVersion",
    "FeatureFlagChangeLog",
    "FeatureFlagManager",
    "feature_flags",
    "feature_flag_manager",
]
