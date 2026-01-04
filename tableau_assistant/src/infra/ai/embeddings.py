"""
Embedding 模型管理

统一管理 Embedding 模型的选择和配置。

支持的提供商：
- zhipu: 智谱 AI embedding-2
- openai: OpenAI text-embedding-ada-002 / text-embedding-3-small
- azure: Azure OpenAI Embeddings
- local: 本地/内部 Embedding 服务
- mock: Mock 实现（用于测试）
"""
import hashlib
import logging
import os
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any

import httpx
from langchain_openai import OpenAIEmbeddings, AzureOpenAIEmbeddings
from langchain.embeddings.base import Embeddings

logger = logging.getLogger(__name__)

# 导入证书管理器
from tableau_assistant.src.infra.certs import get_certificate_config


def get_httpx_client_kwargs():
    """获取 httpx 客户端的 SSL 配置"""
    return get_certificate_config().httpx_client_kwargs()


def select_embeddings(
    provider: str,
    model_name: str
) -> Embeddings:
    """
    选择并配置 Embedding 模型（LangChain 接口）
    
    Args:
        provider: 模型提供商
            - "local": 本地/内部 Embedding 服务
            - "openai": OpenAI Embeddings
            - "azure": Azure OpenAI Embeddings
        model_name: 模型名称（必需）
        
    Returns:
        配置好的 LangChain Embeddings 实例
        
    Raises:
        ValueError: 配置缺失或提供商不支持
        
    Examples:
        >>> embeddings = select_embeddings("openai", "text-embedding-3-small")
    """
    from tableau_assistant.src.infra.config import settings
    
    if not provider:
        raise ValueError("provider is required")
    if not model_name:
        raise ValueError("model_name is required")
    
    llm_api_base = settings.llm_api_base
    llm_api_key = settings.llm_api_key
    
    ssl_kwargs = get_httpx_client_kwargs()
    http_client = httpx.Client(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    http_async_client = httpx.AsyncClient(**ssl_kwargs) if ssl_kwargs.get("verify") is not True else None
    
    if provider == "local":
        if not llm_api_base:
            raise ValueError("LLM_API_BASE must be set for local provider")
        if not llm_api_key:
            raise ValueError("LLM_API_KEY must be set for local provider")
        
        return OpenAIEmbeddings(
            base_url=llm_api_base,
            api_key=llm_api_key,
            model=model_name,
            http_client=http_client,
            http_async_client=http_async_client
        )
    
    elif provider == "azure":
        # Azure 配置暂时保留使用 os.environ，因为这些是 Azure 特定的配置
        azure_deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
        azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
        azure_instance = os.environ.get("AZURE_OPENAI_API_INSTANCE_NAME")
        azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        
        if not all([azure_deployment, azure_api_version, azure_instance, azure_api_key]):
            raise ValueError(
                "Azure OpenAI configuration incomplete. Required in .env: "
                "AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME, AZURE_OPENAI_API_VERSION, "
                "AZURE_OPENAI_API_INSTANCE_NAME, AZURE_OPENAI_API_KEY"
            )
        
        return AzureOpenAIEmbeddings(
            azure_deployment=azure_deployment,
            openai_api_version=azure_api_version,
            azure_endpoint=f"https://{azure_instance}.openai.azure.com",
            openai_api_key=azure_api_key,
            model=model_name
        )
    
    elif provider == "openai":
        # 使用 LLM_API_KEY 作为 OpenAI key
        if not llm_api_key:
            raise ValueError("LLM_API_KEY must be set in .env for OpenAI embeddings")
        
        return OpenAIEmbeddings(
            model=model_name,
            openai_api_key=llm_api_key
        )
    
    else:
        raise ValueError(
            f"Unknown provider: {provider}. "
            f"Supported providers: local, azure, openai"
        )


# ============= 自定义 Embedding Provider（用于 RAG）=============

class EmbeddingProvider(ABC):
    """
    Embedding 提供者抽象基类
    
    定义向量化接口，支持文档和查询的向量化。
    支持同步和异步两种调用方式。
    
    Attributes:
        model_name: 模型名称
        dimensions: 向量维度
        batch_size: 批量处理大小
    """
    
    def __init__(
        self,
        model_name: str,
        dimensions: int,
        batch_size: int = 32
    ):
        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = batch_size
    
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """向量化文档列表（同步）"""
        pass
    
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """向量化查询文本（同步）"""
        pass
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        向量化文档列表（异步）
        
        默认实现使用线程池执行同步方法。
        子类可以覆盖此方法提供原生异步实现。
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_documents, texts)
    
    async def aembed_query(self, text: str) -> List[float]:
        """
        向量化查询文本（异步）
        
        默认实现使用线程池执行同步方法。
        子类可以覆盖此方法提供原生异步实现。
        
        Args:
            text: 查询文本
            
        Returns:
            向量
        """
        import asyncio
        loop = asyncio.get_event_loop()
        return await loop.run_in_executor(None, self.embed_query, text)
    
    @staticmethod
    def compute_text_hash(text: str) -> str:
        """计算文本哈希值（用于缓存）"""
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _batch_texts(self, texts: List[str]) -> List[List[str]]:
        """将文本列表分批"""
        batches = []
        for i in range(0, len(texts), self.batch_size):
            batches.append(texts[i:i + self.batch_size])
        return batches


class ZhipuEmbedding(EmbeddingProvider):
    """
    智谱 AI Embedding 提供者
    
    使用智谱 AI 的 embedding-2 模型进行向量化。
    支持同步和异步两种调用方式。
    """
    
    DEFAULT_MODEL = "embedding-2"
    DEFAULT_DIMENSIONS = 1024
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        batch_size: int = 32
    ):
        super().__init__(
            model_name=model_name,
            dimensions=self.DEFAULT_DIMENSIONS,
            batch_size=batch_size
        )
        
        if api_key is None:
            from tableau_assistant.src.infra.config import settings
            api_key = settings.zhipuai_api_key
        
        if not api_key:
            raise ValueError(
                "智谱 AI API Key 未提供。"
                "请在 .env 中设置 ZHIPUAI_API_KEY。"
            )
        
        self.api_key = api_key
        self._client = None
        self._async_client = None
    
    @property
    def client(self):
        """延迟初始化智谱客户端（同步）"""
        if self._client is None:
            try:
                from zhipuai import ZhipuAI
                http_client = self._create_http_client_with_certs()
                
                if http_client:
                    self._client = ZhipuAI(api_key=self.api_key, http_client=http_client)
                else:
                    self._client = ZhipuAI(api_key=self.api_key)
                    
            except ImportError:
                raise ImportError("请安装 zhipuai 包: pip install zhipuai")
        return self._client
    
    @property
    def async_client(self):
        """延迟初始化智谱异步客户端"""
        if self._async_client is None:
            try:
                from zhipuai import ZhipuAI
                async_http_client = self._create_http_client_with_certs(async_mode=True)
                
                if async_http_client:
                    self._async_client = ZhipuAI(api_key=self.api_key, http_client=async_http_client)
                else:
                    self._async_client = ZhipuAI(api_key=self.api_key)
                    
            except ImportError:
                raise ImportError("请安装 zhipuai 包: pip install zhipuai")
        return self._async_client
    
    def _create_http_client_with_certs(self, async_mode: bool = False):
        """
        创建带证书配置的 HTTP 客户端
        
        Args:
            async_mode: 是否创建异步客户端
        
        优先级：
        1. Linux/Mac: 优先使用系统证书（公网 API 通常不需要自定义证书）
        2. Windows 或系统证书失败: 使用 cert_config.yaml 中的服务证书
        3. 回退到 certifi
        """
        import platform
        from pathlib import Path
        from tableau_assistant.src.infra.certs import get_cert_config
        
        client_class = httpx.AsyncClient if async_mode else httpx.Client
        mode_suffix = "(异步)" if async_mode else ""
        
        # Linux/Mac 优先尝试系统证书
        if platform.system() != "Windows":
            try:
                logger.debug(f"zhipu-ai: 使用系统证书{mode_suffix}")
                return client_class(verify=True, timeout=60.0)
            except Exception as e:
                logger.warning(f"zhipu-ai: 系统证书不可用{mode_suffix}，尝试自定义证书: {e}")
        
        # 使用证书管理器中的 zhipu-ai 服务证书
        try:
            config = get_cert_config()
            zhipu_service = config.services.get("zhipu-ai")
            if zhipu_service and zhipu_service.ca_bundle:
                cert_path = Path(config.cert_dir) / zhipu_service.ca_bundle
                if cert_path.exists():
                    logger.info(f"使用证书管理器的 zhipu-ai 证书{mode_suffix}: {cert_path}")
                    return client_class(verify=str(cert_path), timeout=60.0)
                else:
                    logger.warning(f"zhipu-ai 证书文件不存在: {cert_path}")
        except Exception as e:
            logger.warning(f"从证书管理器获取 zhipu-ai 证书失败: {e}")
        
        # 回退到 certifi 证书
        try:
            import certifi
            logger.debug(f"回退使用 certifi 证书{mode_suffix}: {certifi.where()}")
            return client_class(verify=certifi.where(), timeout=60.0)
        except ImportError:
            logger.warning("certifi 未安装")
        except Exception as e:
            logger.warning(f"使用 certifi 创建客户端失败{mode_suffix}: {e}")
        
        # 回退到系统默认证书
        try:
            logger.debug(f"回退使用系统默认证书{mode_suffix}")
            return client_class(verify=True, timeout=60.0)
        except Exception as e:
            logger.warning(f"使用系统证书失败{mode_suffix}: {e}")
        
        # 最后使用默认配置
        logger.warning(f"无法配置 SSL 证书{mode_suffix}，使用默认配置")
        return None
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """向量化文档列表（同步）"""
        if not texts:
            return []
        
        all_vectors = []
        batches = self._batch_texts(texts)
        
        for batch in batches:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=batch
            )
            for item in response.data:
                all_vectors.append(item.embedding)
        
        return all_vectors
    
    def embed_query(self, text: str) -> List[float]:
        """向量化查询文本（同步）"""
        if not text:
            raise ValueError("查询文本不能为空")
        
        response = self.client.embeddings.create(
            model=self.model_name,
            input=[text]
        )
        return response.data[0].embedding
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        向量化文档列表（异步）
        
        使用智谱 AI 的异步 API 进行向量化。
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        import asyncio
        
        all_vectors = []
        batches = self._batch_texts(texts)
        
        # 并发处理所有批次
        async def process_batch(batch: List[str]) -> List[List[float]]:
            # 智谱 SDK 目前不支持原生异步，使用线程池
            loop = asyncio.get_event_loop()
            response = await loop.run_in_executor(
                None,
                lambda: self.client.embeddings.create(model=self.model_name, input=batch)
            )
            return [item.embedding for item in response.data]
        
        # 并发执行所有批次
        batch_results = await asyncio.gather(*[process_batch(batch) for batch in batches])
        
        for batch_vectors in batch_results:
            all_vectors.extend(batch_vectors)
        
        return all_vectors
    
    async def aembed_query(self, text: str) -> List[float]:
        """
        向量化查询文本（异步）
        
        Args:
            text: 查询文本
            
        Returns:
            向量
        """
        if not text:
            raise ValueError("查询文本不能为空")
        
        import asyncio
        loop = asyncio.get_event_loop()
        response = await loop.run_in_executor(
            None,
            lambda: self.client.embeddings.create(model=self.model_name, input=[text])
        )
        return response.data[0].embedding


class OpenAIEmbedding(EmbeddingProvider):
    """
    OpenAI Embedding 提供者
    
    使用 OpenAI 的 text-embedding 模型进行向量化。
    支持同步和异步两种调用方式。
    """
    
    DEFAULT_MODEL = "text-embedding-3-small"
    DEFAULT_DIMENSIONS = 1536
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        dimensions: int = DEFAULT_DIMENSIONS,
        batch_size: int = 32,
        base_url: Optional[str] = None
    ):
        super().__init__(
            model_name=model_name,
            dimensions=dimensions,
            batch_size=batch_size
        )
        
        if api_key is None:
            from tableau_assistant.src.infra.config import settings
            api_key = settings.llm_api_key
        
        if not api_key:
            raise ValueError("OpenAI API Key 未提供。请在 .env 中设置 LLM_API_KEY。")
        
        self.api_key = api_key
        if base_url is None:
            from tableau_assistant.src.infra.config import settings
            base_url = settings.llm_api_base if settings.llm_api_base else None
        self.base_url = base_url
        self._client = None
        self._async_client = None
    
    @property
    def client(self):
        """延迟初始化 OpenAI 客户端（同步）"""
        if self._client is None:
            try:
                from openai import OpenAI
                kwargs = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self._client = OpenAI(**kwargs)
            except ImportError:
                raise ImportError("请安装 openai 包: pip install openai")
        return self._client
    
    @property
    def async_client(self):
        """延迟初始化 OpenAI 异步客户端"""
        if self._async_client is None:
            try:
                from openai import AsyncOpenAI
                kwargs = {"api_key": self.api_key}
                if self.base_url:
                    kwargs["base_url"] = self.base_url
                self._async_client = AsyncOpenAI(**kwargs)
            except ImportError:
                raise ImportError("请安装 openai 包: pip install openai")
        return self._async_client
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """向量化文档列表（同步）"""
        if not texts:
            return []
        
        all_vectors = []
        batches = self._batch_texts(texts)
        
        for batch in batches:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=batch
            )
            for item in response.data:
                all_vectors.append(item.embedding)
        
        return all_vectors
    
    def embed_query(self, text: str) -> List[float]:
        """向量化查询文本（同步）"""
        if not text:
            raise ValueError("查询文本不能为空")
        
        response = self.client.embeddings.create(
            model=self.model_name,
            input=[text]
        )
        return response.data[0].embedding
    
    async def aembed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        向量化文档列表（异步）
        
        使用 OpenAI 的原生异步 API 进行向量化。
        
        Args:
            texts: 文本列表
            
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        import asyncio
        
        all_vectors = []
        batches = self._batch_texts(texts)
        
        # 并发处理所有批次
        async def process_batch(batch: List[str]) -> List[List[float]]:
            response = await self.async_client.embeddings.create(
                model=self.model_name,
                input=batch
            )
            return [item.embedding for item in response.data]
        
        # 并发执行所有批次
        batch_results = await asyncio.gather(*[process_batch(batch) for batch in batches])
        
        for batch_vectors in batch_results:
            all_vectors.extend(batch_vectors)
        
        return all_vectors
    
    async def aembed_query(self, text: str) -> List[float]:
        """
        向量化查询文本（异步）
        
        Args:
            text: 查询文本
            
        Returns:
            向量
        """
        if not text:
            raise ValueError("查询文本不能为空")
        
        response = await self.async_client.embeddings.create(
            model=self.model_name,
            input=[text]
        )
        return response.data[0].embedding


class EmbeddingProviderFactory:
    """
    Embedding 提供者工厂
    
    支持两种使用方式：
    1. create(provider_name) - 显式指定提供者
    2. get_default() - 根据环境变量自动检测可用的提供者
    """
    
    _providers: Dict[str, type] = {
        "zhipu": ZhipuEmbedding,
        "openai": OpenAIEmbedding,
    }
    
    @classmethod
    def register(cls, name: str, provider_class: type) -> None:
        """注册新的 Embedding 提供者"""
        cls._providers[name] = provider_class
    
    @classmethod
    def create(
        cls,
        provider_name: str,
        **kwargs
    ) -> EmbeddingProvider:
        """
        创建指定的 Embedding 提供者
        
        Args:
            provider_name: 提供者名称（zhipu, openai）
            **kwargs: 传递给提供者的参数
        
        Returns:
            EmbeddingProvider 实例
            
        Raises:
            ValueError: 未知的提供者名称
        """
        if provider_name not in cls._providers:
            available = ", ".join(cls._providers.keys())
            raise ValueError(
                f"未知的 Embedding 提供者: {provider_name}。"
                f"可用的提供者: {available}"
            )
        
        provider_class = cls._providers[provider_name]
        return provider_class(**kwargs)
    
    @classmethod
    def get_default(cls, **kwargs) -> Optional[EmbeddingProvider]:
        """
        根据环境变量自动检测并创建默认的 Embedding 提供者
        
        检测顺序：
        1. ZHIPUAI_API_KEY / ZHIPU_API_KEY → 使用智谱 AI
        2. OPENAI_API_KEY → 使用 OpenAI
        3. 都没有配置 → 返回 None
        
        Args:
            **kwargs: 传递给提供者的参数
        
        Returns:
            EmbeddingProvider 实例，或 None（表示没有可用的提供者）
            
        Example:
            # 自动检测
            provider = EmbeddingProviderFactory.get_default()
            if provider:
                vector = provider.embed_query("hello")
        """
        from tableau_assistant.src.infra.config import settings
        
        # 1. 尝试智谱 AI
        if settings.zhipuai_api_key:
            try:
                provider = cls.create("zhipu", **kwargs)
                logger.debug("使用智谱 AI Embedding 提供者")
                return provider
            except Exception as e:
                logger.warning(f"初始化智谱 AI Embedding 失败: {e}")
        
        # 2. 尝试 OpenAI
        if settings.llm_api_key:
            try:
                provider = cls.create("openai", **kwargs)
                logger.debug("使用 OpenAI Embedding 提供者")
                return provider
            except Exception as e:
                logger.warning(f"初始化 OpenAI Embedding 失败: {e}")
        
        # 3. 没有可用的提供者
        logger.warning(
            "未配置 Embedding API Key (ZHIPUAI_API_KEY 或 LLM_API_KEY)，"
            "Embedding 功能不可用"
        )
        return None
    
    @classmethod
    def available_providers(cls) -> List[str]:
        """获取可用的提供者列表"""
        return list(cls._providers.keys())


def get_embeddings(model_id: Optional[str] = None, **kwargs) -> EmbeddingProvider:
    """获取 Embedding 实例
    
    统一的 Embedding 获取入口，从 ModelManager 获取模型配置并创建实例。
    
    Args:
        model_id: 模型 ID（可选，不指定则使用默认 Embedding）
        **kwargs: 其他参数（如 batch_size, dimensions）
    
    Returns:
        配置好的 EmbeddingProvider 实例
    
    Raises:
        ValueError: 未找到模型配置
    
    Examples:
        # 使用默认 Embedding
        embeddings = get_embeddings()
        
        # 指定模型
        embeddings = get_embeddings(model_id="env-zhipu-embedding")
        
        # 自定义参数
        embeddings = get_embeddings(batch_size=64)
    """
    from tableau_assistant.src.infra.ai.model_manager import get_model_manager
    
    manager = get_model_manager()
    return manager.create_embedding(model_id=model_id, **kwargs)


__all__ = [
    "get_embeddings",
    "select_embeddings",
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "OpenAIEmbedding",
    "EmbeddingProviderFactory",
]
