# -*- coding: utf-8 -*-
"""快速导入测�?""
import sys
from pathlib import Path

# 添加项目根目�?
project_root = Path(__file__).parent.parent.parent.parent
sys.path.insert(0, str(project_root))

# 测试导入
from analytics_assistant.src.agents.dimension_hierarchy import (
    DimensionHierarchyInference,
    DimensionCategory,
    DimensionAttributes,
    DimensionHierarchyResult,
    IncrementalFieldsResult,
    InferenceStats,
    PatternSource,
    compute_fields_hash,
    compute_single_field_hash,
    compute_incremental_fields,
    build_cache_key,
    infer_dimension_hierarchy,
    SYSTEM_PROMPT,
    build_user_prompt,
    build_dimension_inference_prompt,
    get_system_prompt,
)
print("All imports OK!")

# 测试配置读取
from analytics_assistant.src.infra.config import get_config
config = get_config()
dim_config = config.get("dimension_hierarchy", {})
print(f"cache_namespace: {dim_config.get('cache_namespace')}")
print(f"pattern_namespace: {dim_config.get('pattern_namespace')}")
print(f"high_confidence_threshold: {dim_config.get('high_confidence_threshold')}")
print(f"max_retry_attempts: {dim_config.get('max_retry_attempts')}")
print(f"incremental.enabled: {dim_config.get('incremental', {}).get('enabled')}")

# 测试实例�?
inference = DimensionHierarchyInference()
print(f"\nDimensionHierarchyInference 实例化成�?")
print(f"  enable_rag: {inference._enable_rag}")
print(f"  enable_cache: {inference._enable_cache}")
print(f"  enable_self_learning: {inference._enable_self_learning}")
print(f"  high_confidence_threshold: {inference._high_confidence_threshold}")
print(f"  max_retry: {inference._max_retry}")
print(f"  incremental_enabled: {inference._incremental_enabled}")

print("\n�?所有测试通过!")
