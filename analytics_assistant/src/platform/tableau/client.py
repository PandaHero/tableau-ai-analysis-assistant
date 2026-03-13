# -*- coding: utf-8 -*-
"""
VizQL Data Service 客户端

提供 Tableau VizQL Data Service API 的异步客户端。
- 使用 httpx 进行 HTTP 请求
- 自动重试（指数退避）
- 统一错误处理
- 连接池复用

使用方式：
    from analytics_assistant.src.platform.tableau.client import VizQLClient
    from analytics_assistant.src.platform.tableau.auth import get_tableau_auth_async
    
    async with VizQLClient() as client:
        auth = await get_tableau_auth_async()
        metadata = await client.read_metadata(
            datasource_luid="xxx",
            api_key=auth.api_key,
            site=auth.site,
        )
"""
import logging
import asyncio
from typing import Any, Optional, Union

import httpx

from analytics_assistant.src.infra.config import get_config
from analytics_assistant.src.core.exceptions import (
    VizQLError,
    VizQLAuthError,
    VizQLValidationError,
    VizQLServerError,
    VizQLRateLimitError,
    VizQLTimeoutError,
    VizQLNetworkError,
)

logger = logging.getLogger(__name__)


class TableauDatasourceAmbiguityError(ValueError):
    """Raised when datasource name resolution returns multiple exact matches."""

    def __init__(
        self,
        message: str,
        *,
        datasource_name: str,
        project_name: Optional[str] = None,
        choices: Optional[list[dict[str, str]]] = None,
    ) -> None:
        super().__init__(message)
        self.datasource_name = datasource_name
        self.project_name = project_name
        self.choices = list(choices or [])

# ══════════════════════════════════════════════════════════════════════════════
# SSL 配置辅助函数
# ══════════════════════════════════════════════════════════════════════════════

from .ssl_utils import get_ssl_verify as _get_ssl_verify

# ══════════════════════════════════════════════════════════════════════════════
# VizQL 客户端
# ══════════════════════════════════════════════════════════════════════════════

class VizQLClient:
    """
    VizQL Data Service 异步客户端
    
    提供：
    - 数据源查询（query_datasource）
    - 元数据读取（read_metadata）
    - 数据模型获取（get_datasource_model）
    
    使用方式：
        async with VizQLClient() as client:
            result = await client.read_metadata(...)
    """
    
    def __init__(
        self,
        base_url: Optional[str] = None,
        timeout: Optional[int] = None,
        max_retries: Optional[int] = None,
    ):
        """
        初始化 VizQL 客户端
        
        Args:
            base_url: Tableau 服务器 URL（可选，从配置读取）
            timeout: 请求超时（秒）（可选，从配置读取）
            max_retries: 最大重试次数（可选，从配置读取）
        """
        config = get_config()
        
        self.base_url = (base_url or config.get_tableau_domain()).rstrip("/")
        self.timeout = timeout or config.get_vizql_timeout()
        self.max_retries = max_retries or config.get_vizql_max_retries()
        
        # httpx 异步客户端（延迟初始化）
        self._client: Optional[httpx.AsyncClient] = None
        
        logger.info(f"VizQLClient 初始化: {self.base_url}")
    
    async def _get_client(self) -> httpx.AsyncClient:
        """获取或创建 httpx 客户端"""
        if self._client is None or self._client.is_closed:
            self._client = httpx.AsyncClient(
                verify=_get_ssl_verify(),
                timeout=httpx.Timeout(self.timeout),
            )
        return self._client
    
    async def close(self) -> None:
        """关闭客户端连接"""
        if self._client and not self._client.is_closed:
            await self._client.aclose()
            self._client = None
            logger.info("VizQLClient 连接已关闭")
    
    async def __aenter__(self) -> "VizQLClient":
        return self
    
    async def __aexit__(self, exc_type, exc_val, exc_tb) -> None:
        await self.close()

    # ══════════════════════════════════════════════════════════════════════════
    # 错误处理
    # ══════════════════════════════════════════════════════════════════════════
    
    def _handle_error(self, response: httpx.Response) -> None:
        """
        处理 API 错误响应
        
        Args:
            response: HTTP 响应对象
        
        Raises:
            VizQLAuthError: 401/403 错误
            VizQLValidationError: 400 错误
            VizQLRateLimitError: 429 错误
            VizQLServerError: 5xx 错误
            VizQLError: 其他错误
        """
        status_code = response.status_code
        
        try:
            error_data = response.json()
            error_code = error_data.get("errorCode")
            message = error_data.get("message", response.text)
            debug = error_data.get("debug")
        except Exception as e:
            # 响应体可能不是 JSON 格式，回退到纯文本
            logger.debug(f"解析错误响应 JSON 失败: status_code={status_code}, error={e}")
            error_code = None
            message = response.text
            debug = None
        
        if status_code in (401, 403):
            raise VizQLAuthError(
                message=f"认证失败: {message}",
                error_code=error_code,
                debug=debug,
            )
        elif status_code == 400:
            raise VizQLValidationError(
                message=f"验证错误: {message}",
                error_code=error_code,
                debug=debug,
            )
        elif status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise VizQLRateLimitError(
                message=f"请求限流: {message}",
                retry_after=int(retry_after) if retry_after else None,
                error_code=error_code,
                debug=debug,
            )
        elif 500 <= status_code < 600:
            raise VizQLServerError(
                message=f"服务器错误: {message}",
                status_code=status_code,
                error_code=error_code,
                debug=debug,
            )
        else:
            raise VizQLError(
                message=message,
                status_code=status_code,
                error_code=error_code,
                debug=debug,
            )
    
    # ══════════════════════════════════════════════════════════════════════════
    # 请求执行
    # ══════════════════════════════════════════════════════════════════════════
    
    async def _execute_request(
        self,
        url: str,
        headers: dict[str, str],
        payload: dict[str, Any],
    ) -> dict[str, Any]:
        """
        执行 HTTP 请求（带重试）
        
        Args:
            url: 请求 URL
            headers: 请求头
            payload: 请求体
        
        Returns:
            响应 JSON
        
        Raises:
            VizQLError: 请求失败
        """
        client = await self._get_client()
        last_error: Optional[Exception] = None
        
        for attempt in range(self.max_retries):
            try:
                response = await client.post(
                    url,
                    headers=headers,
                    json=payload,
                )
                
                if response.status_code == 200:
                    return response.json()
                
                self._handle_error(response)
                
            except (VizQLAuthError, VizQLValidationError):
                # 不可重试的错误，直接抛出
                raise
            except VizQLError as e:
                # 可重试的错误
                last_error = e
                if not e.is_retryable or attempt == self.max_retries - 1:
                    raise
                # 指数退避
                wait_time = 2 ** attempt
                logger.warning(f"请求失败，{wait_time}s 后重试 ({attempt + 1}/{self.max_retries}): {e}")
                await asyncio.sleep(wait_time)
            except httpx.TimeoutException as e:
                last_error = VizQLTimeoutError(f"请求超时: {e}")
                if attempt == self.max_retries - 1:
                    raise last_error
                wait_time = 2 ** attempt
                logger.warning(f"请求超时，{wait_time}s 后重试 ({attempt + 1}/{self.max_retries})")
                await asyncio.sleep(wait_time)
            except httpx.RequestError as e:
                last_error = VizQLNetworkError(f"网络错误: {e}")
                if attempt == self.max_retries - 1:
                    raise last_error
                wait_time = 2 ** attempt
                logger.warning(f"网络错误，{wait_time}s 后重试 ({attempt + 1}/{self.max_retries}): {e}")
                await asyncio.sleep(wait_time)
        
        # 不应该到达这里
        raise last_error or VizQLError("请求失败")

    def _raise_graphql_errors(self, response_data: dict[str, Any]) -> None:
        """检查 GraphQL 响应中的 errors 字段并抛出异常。"""
        errors = response_data.get("errors")
        if not errors:
            return

        messages = []
        for error in errors:
            if isinstance(error, dict):
                messages.append(str(error.get("message", error)))
            else:
                messages.append(str(error))

        error_message = "; ".join(messages) or "GraphQL 查询失败"
        raise VizQLError(message=f"GraphQL 查询失败: {error_message}")

    # ══════════════════════════════════════════════════════════════════════════
    # API 方法
    # ══════════════════════════════════════════════════════════════════════════
    
    async def query_datasource(
        self,
        datasource_luid: str,
        query: dict[str, Any],
        api_key: str,
        site: Optional[str] = None,
        options: Optional[dict[str, Any]] = None,
    ) -> dict[str, Any]:
        """
        执行 VizQL 查询
        
        Args:
            datasource_luid: 数据源 LUID
            query: VizQL 查询字典
            api_key: Tableau 认证 token
            site: Tableau site（可选）
            options: 查询选项（可选），支持：
                - rowLimit: 限制返回行数
                - disaggregate: 是否返回明细数据（不聚合）
                - debug: 是否返回调试信息
        
        Returns:
            查询结果字典
        
        Raises:
            VizQLError: API 调用失败
        """
        url = f"{self.base_url}/api/v1/vizql-data-service/query-datasource"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json",
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid},
            "query": query,
        }
        
        if options:
            payload["options"] = options
        
        return await self._execute_request(url, headers, payload)
    
    async def read_metadata(
        self,
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        读取数据源元数据
        
        Args:
            datasource_luid: 数据源 LUID
            api_key: Tableau 认证 token
            site: Tableau site（可选）
        
        Returns:
            元数据字典，包含 'data'（字段列表）和 'extraData'（参数）
        
        Raises:
            VizQLError: API 调用失败
        """
        url = f"{self.base_url}/api/v1/vizql-data-service/read-metadata"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json",
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid},
        }
        
        return await self._execute_request(url, headers, payload)
    
    async def get_datasource_model(
        self,
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
    ) -> dict[str, Any]:
        """
        获取数据源数据模型（逻辑表和关系）
        
        注意：此 API 是 VizQL Data Service 2025.3 (2025年10月) 新增的功能。
        如果 Tableau Server 版本低于 2025.3，此 API 会返回 500 错误。
        
        参考：https://help.tableau.com/current/api/vizql-data-service/en-us/docs/vds_whats_new.html
        
        Args:
            datasource_luid: 数据源 LUID
            api_key: Tableau 认证 token
            site: Tableau site（可选）
        
        Returns:
            数据模型字典，包含 'logicalTables' 和 'logicalTableRelationships'
        
        Raises:
            VizQLServerError: Tableau Server 版本低于 2025.3 时返回 500 错误
            VizQLError: 其他 API 调用失败
        """
        url = f"{self.base_url}/api/v1/vizql-data-service/get-datasource-model"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json",
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid},
        }
        
        return await self._execute_request(url, headers, payload)
    
    # ══════════════════════════════════════════════════════════════════════════
    # GraphQL Metadata API
    # ══════════════════════════════════════════════════════════════════════════
    
    async def graphql_query(
        self,
        query: str,
        variables: Optional[dict[str, Any]],
        api_key: str,
    ) -> dict[str, Any]:
        """
        执行 GraphQL 查询（Tableau Metadata API）
        
        Args:
            query: GraphQL 查询字符串
            variables: 查询变量（可选）
            api_key: Tableau 认证 token
        
        Returns:
            GraphQL 响应数据
        
        Raises:
            VizQLError: API 调用失败
        """
        url = f"{self.base_url}/api/metadata/graphql"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json",
        }
        
        payload = {"query": query}
        if variables:
            payload["variables"] = variables

        response_data = await self._execute_request(url, headers, payload)
        self._raise_graphql_errors(response_data)
        return response_data
    
    async def get_datasource_fields_metadata(
        self,
        datasource_luid: str,
        api_key: str,
    ) -> dict[str, Any]:
        """
        通过 GraphQL 获取数据源字段的完整元数据
        
        GraphQL Metadata API 提供完整的字段信息：
        - name: 用户友好的显示名称（等于 VizQL 的 fieldCaption）
        - role: 字段角色（DIMENSION / MEASURE）
        - dataType: 数据类型
        - dataCategory: 数据类别（NOMINAL / ORDINAL / QUANTITATIVE）
        - aggregation: 默认聚合方式
        - isHidden: 是否隐藏
        - formula: 计算字段公式（仅 CalculatedField）
        - description: 字段描述
        - folderName: 文件夹名称
        - upstreamTables: 上游表信息（替代 VizQL 的 logicalTableId）
        
        注意：GraphQL 的 name 就是显示名，不需要再调用 VizQL read_metadata
        
        Args:
            datasource_luid: 数据源 LUID
            api_key: Tableau 认证 token
        
        Returns:
            包含字段元数据的字典
        """
        # 使用 inline fragment 查询不同字段类型的特定属性
        query = """
        query GetDatasourceFields($luid: String!) {
            publishedDatasources(filter: {luid: $luid}) {
                name
                luid
                description
                hasExtracts
                extractLastRefreshTime
                owner {
                    name
                    username
                }
                fields {
                    id
                    name
                    description
                    isHidden
                    folderName
                    ... on ColumnField {
                        role
                        dataType
                        dataCategory
                        aggregation
                        upstreamTables {
                            id
                            name
                        }
                    }
                    ... on CalculatedField {
                        role
                        dataType
                        dataCategory
                        aggregation
                        formula
                    }
                    ... on BinField {
                        role
                        dataType
                    }
                    ... on GroupField {
                        role
                        dataType
                    }
                }
            }
        }
        """
        
        return await self.graphql_query(
            query=query,
            variables={"luid": datasource_luid},
            api_key=api_key,
        )
    
    async def get_datasource_luid_by_name(
        self,
        datasource_name: str,
        api_key: str,
        project_name: Optional[str] = None,
    ) -> Optional[str]:
        """
        通过数据源名称获取 LUID

        只允许精确匹配：
        1. `datasource_luid` 优先，由上游直接传入
        2. `datasource_name + project_name` 精确匹配
        3. `datasource_name` 唯一精确匹配

        默认禁止前缀/模糊命中，名称不唯一时必须由上游触发澄清。
        
        Args:
            datasource_name: 数据源名称（可能包含 "| 项目 : xxx" 后缀）
            api_key: Tableau 认证 token
            project_name: 项目名称（可选，用于精确匹配）
        
        Returns:
            数据源 LUID，未找到返回 None
        """
        normalized_name = str(datasource_name or "").strip()
        normalized_project = str(project_name or "").strip()
        if not normalized_name:
            return None

        project_marker = "| 项目 :"
        if project_marker in normalized_name and not normalized_project:
            base_name, _, suffix = normalized_name.partition(project_marker)
            normalized_name = base_name.strip()
            normalized_project = suffix.strip()

        # 查询所有数据源（Tableau Cloud 不支持 name filter）
        query = """
        query {
            publishedDatasources {
                luid
                name
                projectName
            }
        }
        """
        
        result = await self.graphql_query(
            query=query,
            variables=None,
            api_key=api_key,
        )
        
        datasources = result.get("data", {}).get("publishedDatasources", [])

        exact_matches = [
            ds for ds in datasources
            if str(ds.get("name") or "").strip() == normalized_name
        ]
        exact_match_choices = [
            {
                "datasource_luid": str(ds.get("luid") or "").strip(),
                "name": str(ds.get("name") or "").strip(),
                "project": str(ds.get("projectName") or "").strip(),
            }
            for ds in exact_matches
            if str(ds.get("luid") or "").strip()
        ]
        if normalized_project:
            project_matches = [
                ds for ds in exact_matches
                if str(ds.get("projectName") or "").strip() == normalized_project
            ]
            if len(project_matches) == 1:
                match = project_matches[0]
                logger.info(
                    "精确匹配（带项目）: %s / %s -> %s",
                    match.get("name"),
                    match.get("projectName"),
                    match.get("luid"),
                )
                return match.get("luid")
            if len(project_matches) > 1:
                project_choices = [
                    choice for choice in exact_match_choices
                    if choice.get("project") == normalized_project
                ]
                raise TableauDatasourceAmbiguityError(
                    "数据源名称与项目组合不唯一，请改用 datasource_luid",
                    datasource_name=normalized_name,
                    project_name=normalized_project,
                    choices=project_choices,
                )

        if len(exact_matches) == 1:
            match = exact_matches[0]
            logger.info("精确匹配: %s -> %s", match.get("name"), match.get("luid"))
            return match.get("luid")

        if len(exact_matches) > 1:
            raise TableauDatasourceAmbiguityError(
                "数据源名称不唯一，请提供 project_name 或 datasource_luid",
                datasource_name=normalized_name,
                choices=exact_match_choices,
            )

        logger.warning("未找到匹配的数据源: %s", normalized_name)
        logger.debug(
            "可用数据源: %s",
            [f"{ds.get('name')}|{ds.get('projectName')}" for ds in datasources],
        )
        return None

# ══════════════════════════════════════════════════════════════════════════════
# 导出
# ══════════════════════════════════════════════════════════════════════════════

__all__ = ["TableauDatasourceAmbiguityError", "VizQLClient"]
