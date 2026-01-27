# -*- coding: utf-8 -*-
"""
FieldMapper Node 单元测试

测试覆盖：
1. FieldMappingConfig - 配置加载
2. FieldCandidate 和 MappingResult - 数据类
3. FieldMapperNode - 核心映射逻辑
   - 缓存方法
   - 元数据加载
   - 字段映射（缓存命中、RAG 直接、LLM 回退）
   - 批量映射
4. field_mapper_node - StateGraph 节点函数
5. 辅助函数
"""
import asyncio
import hashlib
import time
from dataclasses import dataclass
from typing import Any, Dict, List, Optional
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from analytics_assistant.src.agents.field_mapper.node import (
    FieldMappingConfig,
    FieldCandidate,
    MappingResult,
    FieldMapperNode,
    field_mapper_node,
    _extract_terms_from_semantic_query,
    _get_field_mapper,
)
from analytics_assistant.src.agents.field_mapper.schemas import (
    SingleSelectionResult,
    FieldMapping,
    MappedQuery,
)


# ══════════════════════════════════════════════════════════════════════════════
# 测试夹具
# ══════════════════════════════════════════════════════════════════════════════

@pytest.fixture
def mock_config():
    """模拟 YAML 配置"""
    return {
        "field_mapper": {
            "high_confidence_threshold": 0.9,
            "low_confidence_threshold": 0.7,
