# -*- coding: utf-8 -*-
"""
FieldMapper 配置模型

包含：
- FieldMappingConfig: FieldMapper 配置类（Pydantic BaseModel）
"""
from pydantic import BaseModel

from analytics_assistant.src.infra.config import get_config

class FieldMappingConfig(BaseModel):
    """FieldMapper 配置

    配置来源：app.yaml -> field_mapper
    """
    high_confidence_threshold: float = 0.9
    low_confidence_threshold: float = 0.7
    max_concurrency: int = 5
    cache_ttl: int = 86400  # 24 小时
    top_k_candidates: int = 10
    max_alternatives: int = 3
    enable_cache: bool = True
    enable_llm_fallback: bool = True

    @classmethod
    def from_yaml(cls) -> "FieldMappingConfig":
        """从 YAML 配置创建"""
        config = get_config()
        yaml_config = config.get("field_mapper", {})
        return cls(
            high_confidence_threshold=yaml_config.get("high_confidence_threshold", 0.9),
            low_confidence_threshold=yaml_config.get("low_confidence_threshold", 0.7),
            max_concurrency=yaml_config.get("max_concurrency", 5),
            cache_ttl=yaml_config.get("cache_ttl", 86400),
            top_k_candidates=yaml_config.get("top_k_candidates", 10),
            max_alternatives=yaml_config.get("max_alternatives", 3),
            enable_cache=yaml_config.get("enable_cache", True),
            enable_llm_fallback=yaml_config.get("enable_llm_fallback", True),
        )

__all__ = [
    "FieldMappingConfig",
]
