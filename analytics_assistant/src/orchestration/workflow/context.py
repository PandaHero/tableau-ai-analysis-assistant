# -*- coding: utf-8 -*-
"""工作流上下文定义与上下文快照工具。

这个模块负责两件事：
1. 定义运行时使用的 `WorkflowContext`。
2. 定义可持久化的 `PreparedContextSnapshot`，用于 LangGraph checkpoint。

设计原则：
- checkpoint 中只保存可序列化状态，不保存 HTTP 客户端、平台适配器等运行时对象。
- 需要执行语义图或查询时，再用快照重建运行时上下文。
"""

from __future__ import annotations

import hashlib
import logging
from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, ConfigDict, Field, PrivateAttr

from analytics_assistant.src.agents.field_semantic import infer_field_semantic
from analytics_assistant.src.agents.semantic_parser.components.query_cache import (
    build_query_cache_scope_key,
    compute_schema_hash,
)
from analytics_assistant.src.core.interfaces import BasePlatformAdapter
from analytics_assistant.src.core.schemas.data_model import DataModel
from analytics_assistant.src.orchestration.retrieval_memory import (
    MemoryInvalidationService,
)
from analytics_assistant.src.platform.tableau.auth import TableauAuthContext, get_tableau_auth_async

logger = logging.getLogger(__name__)


class PreparedContextSnapshot(BaseModel):
    """可持久化的上下文快照。

    只保留能够安全进入 checkpoint 的数据，不保留以下运行时依赖：
    - auth token
    - platform adapter
    - 实时 current_time
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    datasource_luid: str = Field(description="数据源 LUID")
    data_model: Optional[DataModel] = Field(default=None, description="数据模型")
    field_semantic: Optional[dict[str, Any]] = Field(
        default=None,
        description="字段语义结果",
    )
    field_samples: Optional[dict[str, dict[str, Any]]] = Field(
        default=None,
        description="字段样例缓存",
    )
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    fiscal_year_start_month: int = Field(default=1, description="财年起始月份")
    business_calendar: Optional[dict[str, Any]] = Field(
        default=None,
        description="业务日历配置",
    )
    previous_schema_hash: Optional[str] = Field(
        default=None,
        description="上一次请求的 schema hash",
    )

    def to_workflow_context(
        self,
        *,
        auth: Optional[Any] = None,
        platform_adapter: Optional[BasePlatformAdapter] = None,
        current_time: Optional[str] = None,
        user_id: Optional[str] = None,
    ) -> "WorkflowContext":
        """把快照恢复为运行时 `WorkflowContext`。"""
        return WorkflowContext(
            auth=auth,
            datasource_luid=self.datasource_luid,
            data_model=self.data_model,
            field_semantic=self.field_semantic,
            previous_schema_hash=self.previous_schema_hash,
            current_time=current_time or datetime.now().isoformat(),
            timezone=self.timezone,
            fiscal_year_start_month=self.fiscal_year_start_month,
            business_calendar=self.business_calendar,
            field_samples=self.field_samples,
            platform_adapter=platform_adapter,
            user_id=user_id,
        )


class WorkflowContext(BaseModel):
    """工作流运行时上下文。

    这个对象通过 `RunnableConfig["configurable"]["workflow_context"]` 传递给图节点。
    其中允许包含运行时对象，例如 auth、platform_adapter，因此不能直接写入持久化 checkpoint。
    """

    model_config = ConfigDict(arbitrary_types_allowed=True)

    auth: Optional[Any] = Field(default=None, description="平台认证上下文")
    datasource_luid: str = Field(description="数据源 LUID")
    data_model: Optional[Any] = Field(default=None, description="完整数据模型")
    field_semantic: Optional[dict[str, Any]] = Field(default=None, description="字段语义")
    previous_schema_hash: Optional[str] = Field(default=None, description="上次 schema hash")
    _cached_schema_hash: Optional[str] = PrivateAttr(default=None)

    current_time: Optional[str] = Field(default=None, description="当前时间 ISO 字符串")
    timezone: str = Field(default="Asia/Shanghai", description="时区")
    fiscal_year_start_month: int = Field(default=1, description="财年起始月份")
    business_calendar: Optional[dict[str, Any]] = Field(default=None, description="业务日历")
    field_values_cache: dict[str, list[str]] = Field(
        default_factory=dict,
        description="字段值缓存",
    )
    field_samples: Optional[dict[str, dict[str, Any]]] = Field(
        default=None,
        description="字段样例缓存",
    )
    platform_adapter: Optional[Any] = Field(default=None, description="平台适配器")
    user_id: Optional[str] = Field(default=None, description="当前用户 ID")

    @property
    def schema_hash(self) -> str:
        """返回当前数据模型的 schema hash。"""
        if self._cached_schema_hash is not None:
            return self._cached_schema_hash

        if self.data_model is None:
            result = hashlib.md5(b"empty").hexdigest()
            object.__setattr__(self, "_cached_schema_hash", result)
            return result

        if hasattr(self.data_model, "schema_hash"):
            result = self.data_model.schema_hash
            object.__setattr__(self, "_cached_schema_hash", result)
            return result

        result = compute_schema_hash(self.data_model)
        object.__setattr__(self, "_cached_schema_hash", result)
        return result

    def has_schema_changed(self) -> bool:
        """判断当前 schema 是否相对上一轮发生变化。"""
        if self.previous_schema_hash is None:
            return False
        return self.schema_hash != self.previous_schema_hash

    @property
    def query_cache_scope_key(self) -> str:
        """返回当前请求对应的 query cache 隔离范围键。"""
        return build_query_cache_scope_key(
            tenant_domain=getattr(self.auth, "domain", None),
            tenant_site=getattr(self.auth, "site", None),
            user_id=self.user_id,
        )

    def invalidate_cache_if_schema_changed(
        self,
        invalidation_service: Optional[MemoryInvalidationService] = None,
    ) -> dict[str, Any]:
        """当 schema 变化时，统一清理依赖旧 schema 的缓存与记忆。"""
        report = {
            "trigger": "none",
            "datasource_luid": self.datasource_luid,
            "scope_key": None,
            "previous_schema_hash": self.previous_schema_hash,
            "new_schema_hash": self.schema_hash,
            "query_cache_deleted": 0,
            "candidate_fields_deleted": 0,
            "candidate_values_deleted": 0,
            "fewshot_examples_deleted": 0,
            "filter_value_deleted": 0,
            "synonym_deleted": 0,
            "feedback_deleted": 0,
            "total_deleted": 0,
        }
        if not self.has_schema_changed():
            return report

        try:
            service = invalidation_service or MemoryInvalidationService()
            report = service.invalidate_for_schema_change(
                datasource_luid=self.datasource_luid,
                new_schema_hash=self.schema_hash,
                previous_schema_hash=self.previous_schema_hash,
            )
            logger.info(
                "Schema 发生变化，已执行统一失效: datasource=%s total_deleted=%s",
                self.datasource_luid,
                report["total_deleted"],
            )
            return report
        except Exception as exc:
            logger.error("Schema 变化时缓存失效失败: %s", exc)
            return report

    def is_auth_valid(self, buffer_seconds: int = 60) -> bool:
        """判断当前认证是否仍然有效。"""
        if self.auth is None:
            return False
        if hasattr(self.auth, "is_expired"):
            return not self.auth.is_expired(buffer_seconds)
        return True

    async def refresh_auth_if_needed(self) -> "WorkflowContext":
        """在 token 过期前刷新认证。"""
        if self.auth is None:
            return self
        if self.is_auth_valid():
            return self

        logger.info("认证即将过期，开始刷新 Tableau token")
        if self.platform_adapter and hasattr(self.platform_adapter, "refresh_auth"):
            new_auth = await self.platform_adapter.refresh_auth()
        else:
            logger.warning("未注入平台适配器，回退到 get_tableau_auth_async()")
            new_auth = await get_tableau_auth_async(force_refresh=True)
        return self.model_copy(update={"auth": new_auth})

    def get_field_values(self, field_name: str) -> Optional[list[str]]:
        """读取字段值缓存。"""
        return self.field_values_cache.get(field_name)

    def set_field_values(self, field_name: str, values: list[str]) -> None:
        """写入字段值缓存。"""
        self.field_values_cache[field_name] = values

    def update_current_time(self) -> "WorkflowContext":
        """为新一轮请求刷新 current_time，并保留 schema hash 追踪。"""
        return self.model_copy(
            update={
                "previous_schema_hash": self.schema_hash,
                "current_time": datetime.now().isoformat(),
            }
        )

    async def load_field_semantic(
        self,
        force_refresh: bool = False,
        allow_online_inference: bool = True,
    ) -> "WorkflowContext":
        """加载字段语义与字段样例。"""
        if self.data_model is None:
            logger.warning("无法加载字段语义：data_model 为空")
            return self

        cached_samples = None
        if hasattr(self.data_model, "_field_samples_cache"):
            cached_samples = self.data_model._field_samples_cache or None

        if self.field_semantic is not None and not force_refresh:
            if cached_samples and self.field_samples is None:
                return self.model_copy(update={"field_samples": cached_samples})
            return self

        if not force_refresh and hasattr(self.data_model, "_field_semantic_cache"):
            cached_semantic = self.data_model._field_semantic_cache
            if cached_semantic:
                logger.info("复用 data_model 中缓存的字段语义: %s 个字段", len(cached_semantic))
                update_fields: dict[str, Any] = {"field_semantic": cached_semantic}
                if cached_samples and self.field_samples is None:
                    update_fields["field_samples"] = cached_samples
                return self.model_copy(update=update_fields)

        if not allow_online_inference:
            logger.info("当前请求禁止在线推断字段语义，仅复用已有产物")
            if cached_samples and self.field_samples is None:
                return self.model_copy(update={"field_samples": cached_samples})
            return self

        try:
            fields = getattr(self.data_model, "fields", []) or []
            if not fields:
                logger.warning("无法加载字段语义：字段列表为空")
                return self

            result = await infer_field_semantic(
                datasource_luid=self.datasource_luid,
                fields=fields,
                field_samples=self.field_samples or cached_samples,
            )
            semantic_dict = {}
            if result and hasattr(result, "field_semantic"):
                semantic_dict = result.field_semantic

            logger.info("字段语义推断完成: %s 个字段", len(semantic_dict))
            if semantic_dict:
                try:
                    self.data_model._field_semantic_cache = semantic_dict
                except AttributeError:
                    pass

            update_fields = {"field_semantic": semantic_dict}
            if cached_samples and self.field_samples is None:
                update_fields["field_samples"] = cached_samples
            return self.model_copy(update=update_fields)
        except Exception as exc:
            logger.error("字段语义推断失败: %s", exc)
            return self

    def enrich_field_candidates_with_hierarchy(self, field_candidates: list[Any]) -> list[Any]:
        """用字段语义补全候选字段的层级和描述信息。"""
        if not self.field_semantic or not field_candidates:
            return field_candidates

        def _semantic_get(info: Any, key: str, default: Any = None) -> Any:
            if isinstance(info, dict):
                value = info.get(key, default)
            else:
                value = getattr(info, key, default)
            if hasattr(value, "value"):
                return value.value
            return value

        for candidate in field_candidates:
            field_name = getattr(candidate, "field_name", None)
            if not field_name:
                continue

            semantic_info = self.field_semantic.get(field_name)
            if not semantic_info:
                continue

            semantic_role = _semantic_get(semantic_info, "role")
            semantic_category = _semantic_get(semantic_info, "category")
            semantic_level = _semantic_get(semantic_info, "level")
            semantic_granularity = _semantic_get(semantic_info, "granularity")
            semantic_parent = _semantic_get(semantic_info, "parent_dimension")
            semantic_child = _semantic_get(semantic_info, "child_dimension")
            semantic_description = _semantic_get(semantic_info, "business_description")
            semantic_measure_category = _semantic_get(semantic_info, "measure_category")
            semantic_aliases = [
                str(alias).strip()
                for alias in (_semantic_get(semantic_info, "aliases", []) or [])
                if str(alias).strip()
            ]

            current_description = getattr(candidate, "business_description", None)
            if (
                hasattr(candidate, "business_description")
                and semantic_description
                and (
                    not current_description
                    or current_description in {
                        getattr(candidate, "field_name", ""),
                        getattr(candidate, "field_caption", ""),
                    }
                )
            ):
                candidate.business_description = semantic_description

            if hasattr(candidate, "description") and semantic_description and not getattr(candidate, "description", None):
                candidate.description = semantic_description

            if hasattr(candidate, "aliases"):
                existing_aliases = [
                    str(alias).strip()
                    for alias in (getattr(candidate, "aliases", None) or [])
                    if str(alias).strip()
                ]
                merged_aliases: list[str] = []
                seen_aliases: set[str] = set()
                for alias in [*existing_aliases, *semantic_aliases]:
                    alias_key = alias.lower()
                    if alias_key in seen_aliases:
                        continue
                    seen_aliases.add(alias_key)
                    merged_aliases.append(alias)
                if merged_aliases:
                    candidate.aliases = merged_aliases

            if hasattr(candidate, "role") and semantic_role and not getattr(candidate, "role", None):
                candidate.role = semantic_role
            if hasattr(candidate, "category") and semantic_category and not getattr(candidate, "category", None):
                candidate.category = semantic_category
            if hasattr(candidate, "level") and semantic_level and not getattr(candidate, "level", None):
                candidate.level = semantic_level
            if hasattr(candidate, "granularity") and semantic_granularity:
                candidate.granularity = semantic_granularity
            if hasattr(candidate, "measure_category") and semantic_measure_category and not getattr(candidate, "measure_category", None):
                candidate.measure_category = semantic_measure_category
            if hasattr(candidate, "hierarchy_category") and semantic_category:
                candidate.hierarchy_category = semantic_category
            if hasattr(candidate, "hierarchy_level") and semantic_level:
                candidate.hierarchy_level = semantic_level
            if hasattr(candidate, "parent_dimension") and semantic_parent:
                candidate.parent_dimension = semantic_parent
            if hasattr(candidate, "child_dimension") and semantic_child:
                candidate.child_dimension = semantic_child
            if hasattr(candidate, "drill_down_options") and semantic_child:
                existing_options = list(getattr(candidate, "drill_down_options", None) or [])
                if semantic_child not in existing_options:
                    candidate.drill_down_options = [*existing_options, semantic_child]

        return field_candidates

    def to_snapshot(self) -> PreparedContextSnapshot:
        """提取可进入 checkpoint 的上下文快照。"""
        return PreparedContextSnapshot(
            datasource_luid=self.datasource_luid,
            data_model=self.data_model,
            field_semantic=self.field_semantic,
            field_samples=self.field_samples,
            timezone=self.timezone,
            fiscal_year_start_month=self.fiscal_year_start_month,
            business_calendar=self.business_calendar,
            previous_schema_hash=self.previous_schema_hash,
        )


def create_workflow_config(
    thread_id: str,
    context: WorkflowContext,
    **extra_configurable: object,
) -> dict[str, Any]:
    """创建带 `WorkflowContext` 的 RunnableConfig。"""
    return {
        "configurable": {
            "thread_id": thread_id,
            "workflow_context": context,
            **extra_configurable,
        }
    }


def get_context(config: Optional[dict[str, Any]]) -> Optional[WorkflowContext]:
    """从 RunnableConfig 读取 `WorkflowContext`。"""
    if config is None:
        return None
    configurable = config.get("configurable", {})
    return configurable.get("workflow_context")


def get_context_or_raise(config: Optional[dict[str, Any]]) -> WorkflowContext:
    """读取 `WorkflowContext`，不存在时直接失败。"""
    if config is None:
        raise ValueError("config is None, cannot get WorkflowContext")

    ctx = get_context(config)
    if ctx is None:
        raise ValueError(
            "WorkflowContext not found in config. "
            "Make sure to use create_workflow_config() to create the config."
        )
    return ctx


__all__ = [
    "PreparedContextSnapshot",
    "TableauAuthContext",
    "WorkflowContext",
    "create_workflow_config",
    "get_context",
    "get_context_or_raise",
]
