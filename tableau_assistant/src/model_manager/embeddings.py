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

# 支持的 Embedding 提供商
SUPPORTED_EMBEDDING_PROVIDERS: List[str] = [
    "zhipu",
    "openai",
    "azure",
    "local",
    "mock",
]

# 尝试导入证书管理器
try:
    from tableau_assistant.cert_manager import get_ssl_config
    def get_httpx_client_kwargs():
        return get_ssl_config().httpx_client_kwargs()
except ImportError:
    try:
        from tableau_assistant.src.utils.ssl_config import get_httpx_client_kwargs
    except ImportError:
        def get_httpx_client_kwargs():
            return {}


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
    if not provider:
        raise ValueError("provider is required")
    if not model_name:
        raise ValueError("model_name is required")
    
    llm_api_base = os.environ.get("LLM_API_BASE")
    llm_api_key = os.environ.get("LLM_API_KEY")
    
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
        azure_deployment = os.environ.get("AZURE_OPENAI_EMBEDDING_DEPLOYMENT_NAME")
        azure_api_version = os.environ.get("AZURE_OPENAI_API_VERSION")
        azure_instance = os.environ.get("AZURE_OPENAI_API_INSTANCE_NAME")
        azure_api_key = os.environ.get("AZURE_OPENAI_API_KEY")
        
        if not all([azure_deployment, azure_api_version, azure_instance, azure_api_key]):
            raise ValueError(
                "Azure OpenAI configuration incomplete. Required: "
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
        openai_api_key = os.environ.get("OPENAI_API_KEY")
        if not openai_api_key:
            raise ValueError("OPENAI_API_KEY must be set for OpenAI embeddings")
        
        return OpenAIEmbeddings(
            model=model_name,
            openai_api_key=openai_api_key
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
    
    def embed_documents_with_results(self, texts: List[str]) -> List["EmbeddingResult"]:
        """
        向量化文档列表并返回带元数据的结果
        
        Args:
            texts: 文本列表
            
        Returns:
            EmbeddingResult 列表
        """
        from tableau_assistant.src.capabilities.rag.models import EmbeddingResult
        
        vectors = self.embed_documents(texts)
        results = []
        for text, vector in zip(texts, vectors):
            results.append(EmbeddingResult(
                text=text,
                vector=vector,
                model=self.model_name,
                dimensions=self.dimensions
            ))
        return results
    
    def embed_query_with_result(self, text: str) -> "EmbeddingResult":
        """
        向量化查询文本并返回带元数据的结果
        
        Args:
            text: 查询文本
            
        Returns:
            EmbeddingResult
        """
        from tableau_assistant.src.capabilities.rag.models import EmbeddingResult
        
        vector = self.embed_query(text)
        return EmbeddingResult(
            text=text,
            vector=vector,
            model=self.model_name,
            dimensions=self.dimensions
        )
    
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
            api_key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
        
        if not api_key:
            raise ValueError(
                "智谱 AI API Key 未提供。"
                "请设置 ZHIPUAI_API_KEY 或 ZHIPU_API_KEY 环境变量。"
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
                async_http_client = self._create_async_http_client_with_certs()
                
                if async_http_client:
                    self._async_client = ZhipuAI(api_key=self.api_key, http_client=async_http_client)
                else:
                    self._async_client = ZhipuAI(api_key=self.api_key)
                    
            except ImportError:
                raise ImportError("请安装 zhipuai 包: pip install zhipuai")
        return self._async_client
    
    def _create_http_client_with_certs(self):
        """创建带证书配置的 HTTP 客户端（同步）"""
        try:
            from tableau_assistant.cert_manager import CertificateManager
            cert_manager = CertificateManager()
            try:
                cert_manager.register_preconfigured_services(["zhipu-ai"])
            except Exception:
                pass
            ssl_config = cert_manager.get_service_ssl_config("zhipu-ai", library="httpx")
            return httpx.Client(**ssl_config)
        except Exception:
            pass
        
        try:
            import ssl
            import certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            return httpx.Client(verify=ssl_context)
        except Exception:
            pass
        
        return None
    
    def _create_async_http_client_with_certs(self):
        """创建带证书配置的异步 HTTP 客户端"""
        try:
            from tableau_assistant.cert_manager import CertificateManager
            cert_manager = CertificateManager()
            try:
                cert_manager.register_preconfigured_services(["zhipu-ai"])
            except Exception:
                pass
            ssl_config = cert_manager.get_service_ssl_config("zhipu-ai", library="httpx")
            return httpx.AsyncClient(**ssl_config)
        except Exception:
            pass
        
        try:
            import ssl
            import certifi
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            return httpx.AsyncClient(verify=ssl_context)
        except Exception:
            pass
        
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
            api_key = os.getenv("OPENAI_API_KEY") or os.getenv("LLM_API_KEY")
        
        if not api_key:
            raise ValueError("OpenAI API Key 未提供。请设置 OPENAI_API_KEY 环境变量。")
        
        self.api_key = api_key
        self.base_url = base_url or os.getenv("OPENAI_API_BASE")
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


class MockEmbedding(EmbeddingProvider):
    """
    Mock Embedding 提供者（用于测试）
    """
    
    def __init__(
        self,
        dimensions: int = 1024,
        batch_size: int = 32,
        seed: Optional[int] = None,
        deterministic: bool = False
    ):
        super().__init__(
            model_name="mock-embedding",
            dimensions=dimensions,
            batch_size=batch_size
        )
        self.seed = seed
        self.deterministic = deterministic or (seed is not None)
        
        if seed is not None:
            import random
            random.seed(seed)
    
    def _get_deterministic_vector(self, text: str) -> List[float]:
        """基于文本哈希生成确定性向量"""
        import random
        text_hash = self.compute_text_hash(text)
        seed = int(text_hash[:8], 16)
        rng = random.Random(seed)
        return [rng.random() for _ in range(self.dimensions)]
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """生成 Mock 向量"""
        import random
        
        if self.deterministic:
            return [self._get_deterministic_vector(text) for text in texts]
        
        return [
            [random.random() for _ in range(self.dimensions)]
            for _ in texts
        ]
    
    def embed_query(self, text: str) -> List[float]:
        """生成 Mock 查询向量"""
        import random
        
        if self.deterministic:
            return self._get_deterministic_vector(text)
        
        return [random.random() for _ in range(self.dimensions)]


class EmbeddingProviderFactory:
    """
    Embedding 提供者工厂
    """
    
    _providers: Dict[str, type] = {
        "zhipu": ZhipuEmbedding,
        "openai": OpenAIEmbedding,
        "mock": MockEmbedding,
    }
    
    @classmethod
    def register(cls, name: str, provider_class: type) -> None:
        """注册新的 Embedding 提供者"""
        cls._providers[name] = provider_class
    
    @classmethod
    def create(
        cls,
        provider_name: str = "zhipu",
        **kwargs
    ) -> EmbeddingProvider:
        """
        创建 Embedding 提供者
        
        Args:
            provider_name: 提供者名称（zhipu, openai, mock）
            **kwargs: 传递给提供者的参数
        
        Returns:
            EmbeddingProvider 实例
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
    def available_providers(cls) -> List[str]:
        """获取可用的提供者列表"""
        return list(cls._providers.keys())


__all__ = [
    "select_embeddings",
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "OpenAIEmbedding",
    "MockEmbedding",
    "EmbeddingProviderFactory",
    "SUPPORTED_EMBEDDING_PROVIDERS",
]
