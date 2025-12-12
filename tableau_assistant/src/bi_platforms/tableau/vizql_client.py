"""
VizQL Data Service Client

Production-grade client for Tableau VizQL Data Service API with:
- Pydantic model validation
- Connection pooling (sync) / aiohttp session (async)
- Automatic retry with exponential backoff
- Unified error handling
- Both sync and async support
"""
import os
import logging
from typing import Dict, Any, Optional, Union

import requests
from requests.adapters import HTTPAdapter
from pydantic import BaseModel, Field, ConfigDict
from tenacity import retry, stop_after_attempt, wait_exponential, retry_if_exception

# Async imports (optional)
try:
    import aiohttp
    import asyncio
    HAS_AIOHTTP = True
except ImportError:
    HAS_AIOHTTP = False

from tableau_assistant.src.exceptions import (
    VizQLError,
    VizQLAuthError,
    VizQLValidationError,
    VizQLServerError,
    VizQLRateLimitError,
    VizQLTimeoutError,
    VizQLNetworkError,
)

logger = logging.getLogger(__name__)


class VizQLClientConfig(BaseModel):
    """VizQL client configuration."""
    model_config = ConfigDict(extra="forbid")
    
    base_url: str = Field(description="Tableau server URL")
    verify_ssl: bool = Field(default=True, description="Whether to verify SSL certificates")
    ca_bundle: Optional[str] = Field(default=None, description="Custom CA certificate path")
    timeout: int = Field(default=30, description="Request timeout in seconds")
    max_retries: int = Field(default=3, description="Maximum retry attempts")
    pool_connections: int = Field(default=10, description="Connection pool size")
    pool_maxsize: int = Field(default=10, description="Max connections per pool")


def _is_retryable_error(exception: Exception) -> bool:
    """Check if exception is retryable."""
    if isinstance(exception, VizQLError):
        return exception.is_retryable
    if isinstance(exception, (requests.exceptions.Timeout, requests.exceptions.ConnectionError)):
        return True
    return False


class VizQLClient:
    """
    VizQL Data Service Client.
    
    Provides:
    - Pydantic model validation
    - Connection pooling for HTTP reuse
    - Automatic retry with exponential backoff
    - Unified error handling
    """
    
    def __init__(self, config: Optional[VizQLClientConfig] = None):
        """
        Initialize VizQL client.
        
        Args:
            config: Client configuration. If None, reads from environment variables.
        """
        if config is None:
            from tableau_assistant.src.config.settings import settings
            config = VizQLClientConfig(
                base_url=settings.tableau_domain,
                verify_ssl=settings.vizql_verify_ssl,
                ca_bundle=settings.vizql_ca_bundle or None,
                timeout=settings.vizql_timeout,
                max_retries=settings.vizql_max_retries,
            )
        
        self.config = config
        self._session = self._create_session()
        logger.info(f"VizQLClient initialized: {config.base_url}")
    
    def _create_session(self) -> requests.Session:
        """Create HTTP session with connection pooling."""
        session = requests.Session()
        
        adapter = HTTPAdapter(
            pool_connections=self.config.pool_connections,
            pool_maxsize=self.config.pool_maxsize,
            max_retries=0  # Retry handled by tenacity
        )
        session.mount('http://', adapter)
        session.mount('https://', adapter)
        
        return session
    
    def _get_verify(self) -> Union[bool, str]:
        """Get SSL verification setting."""
        if self.config.ca_bundle:
            return self.config.ca_bundle
        return self.config.verify_ssl

    
    def _handle_error(self, response: requests.Response) -> None:
        """
        Handle API error response.
        
        Args:
            response: HTTP response object
        
        Raises:
            VizQLAuthError: For 401/403 errors
            VizQLValidationError: For 400 errors
            VizQLRateLimitError: For 429 errors
            VizQLServerError: For 5xx errors
            VizQLError: For other errors
        """
        status_code = response.status_code
        
        try:
            error_data = response.json()
            error_code = error_data.get("errorCode")
            message = error_data.get("message", response.text)
            debug = error_data.get("debug")
        except ValueError:
            error_code = None
            message = response.text
            debug = None
        
        if status_code in (401, 403):
            raise VizQLAuthError(
                message=f"Authentication failed: {message}",
                error_code=error_code,
                debug=debug
            )
        elif status_code == 400:
            raise VizQLValidationError(
                message=f"Validation error: {message}",
                error_code=error_code,
                debug=debug
            )
        elif status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise VizQLRateLimitError(
                message=f"Rate limit exceeded: {message}",
                retry_after=int(retry_after) if retry_after else None,
                error_code=error_code,
                debug=debug
            )
        elif 500 <= status_code < 600:
            raise VizQLServerError(
                message=f"Server error: {message}",
                status_code=status_code,
                error_code=error_code,
                debug=debug
            )
        else:
            raise VizQLError(
                status_code=status_code,
                message=message,
                error_code=error_code,
                debug=debug
            )

    
    def query_datasource(
        self,
        datasource_luid: str,
        query: Dict[str, Any],
        api_key: str,
        site: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Execute VizQL query.
        
        Args:
            datasource_luid: Datasource LUID
            query: VizQL query dict
            api_key: Tableau auth token
            site: Tableau site (optional)
        
        Returns:
            Query result dict
        
        Raises:
            VizQLError: On API failure
        """
        url = f"{self.config.base_url}/api/v1/vizql-data-service/query-datasource"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json"
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid},
            "query": query
        }
        
        return self._execute_request(url, headers, payload)
    
    def read_metadata(
        self,
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Read datasource metadata.
        
        Args:
            datasource_luid: Datasource LUID
            api_key: Tableau auth token
            site: Tableau site (optional)
        
        Returns:
            Metadata dict with 'data' (field list) and 'extraData' (parameters)
        
        Raises:
            VizQLError: On API failure
        """
        url = f"{self.config.base_url}/api/v1/vizql-data-service/read-metadata"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json"
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid}
        }
        
        return self._execute_request(url, headers, payload)
    
    def get_datasource_model(
        self,
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Get datasource data model (logical tables and relationships).
        
        Args:
            datasource_luid: Datasource LUID
            api_key: Tableau auth token
            site: Tableau site (optional)
        
        Returns:
            Data model dict with 'logicalTables' and 'logicalTableRelationships'
        
        Raises:
            VizQLError: On API failure
        """
        url = f"{self.config.base_url}/api/v1/vizql-data-service/get-datasource-model"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json"
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid}
        }
        
        return self._execute_request(url, headers, payload)

    
    def _execute_request(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any]
    ) -> Dict[str, Any]:
        """
        Execute HTTP request with retry logic.
        
        Args:
            url: Request URL
            headers: Request headers
            payload: Request payload
        
        Returns:
            Response JSON
        
        Raises:
            VizQLError: On failure
        """
        @retry(
            stop=stop_after_attempt(self.config.max_retries),
            wait=wait_exponential(multiplier=1, min=1, max=10),
            retry=retry_if_exception(_is_retryable_error),
            reraise=True
        )
        def _do_request():
            try:
                response = self._session.post(
                    url,
                    headers=headers,
                    json=payload,
                    verify=self._get_verify(),
                    timeout=self.config.timeout
                )
                
                if response.status_code == 200:
                    return response.json()
                else:
                    self._handle_error(response)
                    
            except requests.exceptions.Timeout as e:
                raise VizQLTimeoutError(f"Request timeout: {e}")
            except requests.exceptions.ConnectionError as e:
                raise VizQLNetworkError(f"Connection error: {e}")
        
        return _do_request()
    
    def close(self) -> None:
        """Close connection pool."""
        self._session.close()
        logger.info("VizQLClient connection closed")
    
    def __enter__(self):
        return self
    
    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()
        return False

    # ==================== Async Methods ====================
    
    async def query_datasource_async(
        self,
        datasource_luid: str,
        query: Dict[str, Any],
        api_key: str,
        site: Optional[str] = None,
        session: Optional["aiohttp.ClientSession"] = None
    ) -> Dict[str, Any]:
        """
        Execute VizQL query asynchronously.
        
        Args:
            datasource_luid: Datasource LUID
            query: VizQL query dict
            api_key: Tableau auth token
            site: Tableau site (optional)
            session: Optional aiohttp session (for connection reuse)
        
        Returns:
            Query result dict
        
        Raises:
            VizQLError: On API failure
        """
        if not HAS_AIOHTTP:
            raise ImportError("aiohttp is required for async operations. Install with: pip install aiohttp")
        
        url = f"{self.config.base_url}/api/v1/vizql-data-service/query-datasource"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json"
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid},
            "query": query
        }
        
        return await self._execute_request_async(url, headers, payload, session)
    
    async def read_metadata_async(
        self,
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
        session: Optional["aiohttp.ClientSession"] = None
    ) -> Dict[str, Any]:
        """
        Read datasource metadata asynchronously.
        
        Args:
            datasource_luid: Datasource LUID
            api_key: Tableau auth token
            site: Tableau site (optional)
            session: Optional aiohttp session
        
        Returns:
            Metadata dict
        """
        if not HAS_AIOHTTP:
            raise ImportError("aiohttp is required for async operations")
        
        url = f"{self.config.base_url}/api/v1/vizql-data-service/read-metadata"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json"
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid}
        }
        
        return await self._execute_request_async(url, headers, payload, session)
    
    async def get_datasource_model_async(
        self,
        datasource_luid: str,
        api_key: str,
        site: Optional[str] = None,
        session: Optional["aiohttp.ClientSession"] = None
    ) -> Dict[str, Any]:
        """
        Get datasource data model asynchronously.
        
        Args:
            datasource_luid: Datasource LUID
            api_key: Tableau auth token
            site: Tableau site (optional)
            session: Optional aiohttp session
        
        Returns:
            Data model dict
        """
        if not HAS_AIOHTTP:
            raise ImportError("aiohttp is required for async operations")
        
        url = f"{self.config.base_url}/api/v1/vizql-data-service/get-datasource-model"
        
        headers = {
            "X-Tableau-Auth": api_key,
            "Content-Type": "application/json"
        }
        if site:
            headers["X-Tableau-Site"] = site
        
        payload = {
            "datasource": {"datasourceLuid": datasource_luid}
        }
        
        return await self._execute_request_async(url, headers, payload, session)
    
    async def _execute_request_async(
        self,
        url: str,
        headers: Dict[str, str],
        payload: Dict[str, Any],
        session: Optional["aiohttp.ClientSession"] = None
    ) -> Dict[str, Any]:
        """
        Execute async HTTP request with retry logic.
        
        Args:
            url: Request URL
            headers: Request headers
            payload: Request payload
            session: Optional aiohttp session
        
        Returns:
            Response JSON
        """
        ssl_param = self._get_aiohttp_ssl()
        
        async def _do_request(sess: "aiohttp.ClientSession") -> Dict[str, Any]:
            for attempt in range(self.config.max_retries):
                try:
                    async with sess.post(
                        url,
                        json=payload,
                        headers=headers,
                        ssl=ssl_param,
                        timeout=aiohttp.ClientTimeout(total=self.config.timeout)
                    ) as response:
                        if response.status == 200:
                            return await response.json()
                        else:
                            await self._handle_error_async(response)
                            
                except aiohttp.ClientError as e:
                    if attempt == self.config.max_retries - 1:
                        raise VizQLNetworkError(f"Connection error after {self.config.max_retries} attempts: {e}")
                    await asyncio.sleep(2 ** attempt)  # Exponential backoff
            
            raise VizQLError(message="Max retries exceeded")
        
        # Use provided session or create a new one
        if session:
            return await _do_request(session)
        else:
            async with aiohttp.ClientSession() as new_session:
                return await _do_request(new_session)
    
    def _get_aiohttp_ssl(self):
        """Get SSL parameter for aiohttp."""
        try:
            from tableau_assistant.cert_manager import get_ssl_config
            return get_ssl_config().get_aiohttp_ssl_param()
        except ImportError:
            return self.config.verify_ssl
    
    async def _handle_error_async(self, response: "aiohttp.ClientResponse") -> None:
        """Handle async API error response."""
        status_code = response.status
        
        try:
            error_data = await response.json()
            error_code = error_data.get("errorCode")
            message = error_data.get("message", await response.text())
            debug = error_data.get("debug")
        except Exception:
            error_code = None
            message = await response.text()
            debug = None
        
        if status_code in (401, 403):
            raise VizQLAuthError(
                message=f"Authentication failed: {message}",
                error_code=error_code,
                debug=debug
            )
        elif status_code == 400:
            raise VizQLValidationError(
                message=f"Validation error: {message}",
                error_code=error_code,
                debug=debug
            )
        elif status_code == 429:
            retry_after = response.headers.get("Retry-After")
            raise VizQLRateLimitError(
                message=f"Rate limit exceeded: {message}",
                retry_after=int(retry_after) if retry_after else None,
                error_code=error_code,
                debug=debug
            )
        elif 500 <= status_code < 600:
            raise VizQLServerError(
                message=f"Server error: {message}",
                status_code=status_code,
                error_code=error_code,
                debug=debug
            )
        else:
            raise VizQLError(
                status_code=status_code,
                message=message,
                error_code=error_code,
                debug=debug
            )
