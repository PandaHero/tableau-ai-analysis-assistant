"""
Embedding 提供者

参考 DB-GPT 的 embeddings 实现模式，提供向量化能力抽象。

主要组件：
- EmbeddingProvider: 抽象基类
- ZhipuEmbedding: 智谱 AI embedding-2 实现
- EmbeddingProviderFactory: 工厂类
"""
import hashlib
import logging
from abc import ABC, abstractmethod
from typing import List, Optional, Dict, Any, Tuple
from dataclasses import dataclass

from tableau_assistant.src.capabilities.rag.models import EmbeddingResult

logger = logging.getLogger(__name__)


class EmbeddingProvider(ABC):
    """
    Embedding 提供者抽象基类
    
    定义向量化接口，支持文档和查询的向量化。
    参考 DB-GPT 的 Embeddings 抽象设计。
    
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
        """
        初始化 Embedding 提供者
        
        Args:
            model_name: 模型名称
            dimensions: 向量维度
            batch_size: 批量处理大小（默认 32）
        """
        self.model_name = model_name
        self.dimensions = dimensions
        self.batch_size = batch_size
    
    @abstractmethod
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        向量化文档列表
        
        Args:
            texts: 文档文本列表
        
        Returns:
            向量列表，每个向量对应一个文档
        """
        pass
    
    @abstractmethod
    def embed_query(self, text: str) -> List[float]:
        """
        向量化查询文本
        
        Args:
            text: 查询文本
        
        Returns:
            查询向量
        """
        pass
    
    def embed_documents_with_results(
        self, 
        texts: List[str]
    ) -> List[EmbeddingResult]:
        """
        向量化文档并返回完整结果
        
        Args:
            texts: 文档文本列表
        
        Returns:
            EmbeddingResult 列表
        """
        vectors = self.embed_documents(texts)
        return [
            EmbeddingResult(
                text=text,
                vector=vector,
                model=self.model_name,
                dimensions=self.dimensions
            )
            for text, vector in zip(texts, vectors)
        ]
    
    def embed_query_with_result(self, text: str) -> EmbeddingResult:
        """
        向量化查询并返回完整结果
        
        Args:
            text: 查询文本
        
        Returns:
            EmbeddingResult
        """
        vector = self.embed_query(text)
        return EmbeddingResult(
            text=text,
            vector=vector,
            model=self.model_name,
            dimensions=self.dimensions
        )
    
    @staticmethod
    def compute_text_hash(text: str) -> str:
        """
        计算文本哈希值（用于缓存）
        
        Args:
            text: 文本
        
        Returns:
            哈希值字符串
        """
        return hashlib.md5(text.encode('utf-8')).hexdigest()
    
    def _batch_texts(self, texts: List[str]) -> List[List[str]]:
        """
        将文本列表分批
        
        Args:
            texts: 文本列表
        
        Returns:
            分批后的文本列表
        """
        batches = []
        for i in range(0, len(texts), self.batch_size):
            batches.append(texts[i:i + self.batch_size])
        return batches


class ZhipuEmbedding(EmbeddingProvider):
    """
    智谱 AI Embedding 提供者
    
    使用智谱 AI 的 embedding-2 模型进行向量化。
    
    Attributes:
        api_key: 智谱 AI API Key
        model_name: 模型名称（默认 embedding-2）
        dimensions: 向量维度（embedding-2 为 1024）
    """
    
    DEFAULT_MODEL = "embedding-2"
    DEFAULT_DIMENSIONS = 1024
    
    def __init__(
        self,
        api_key: Optional[str] = None,
        model_name: str = DEFAULT_MODEL,
        batch_size: int = 32
    ):
        """
        初始化智谱 Embedding 提供者
        
        Args:
            api_key: 智谱 AI API Key（可选，默认从环境变量读取）
            model_name: 模型名称（默认 embedding-2）
            batch_size: 批量处理大小（默认 32）
        """
        super().__init__(
            model_name=model_name,
            dimensions=self.DEFAULT_DIMENSIONS,
            batch_size=batch_size
        )
        
        # 获取 API Key（支持两种环境变量名）
        if api_key is None:
            import os
            api_key = os.getenv("ZHIPUAI_API_KEY") or os.getenv("ZHIPU_API_KEY")
        
        if not api_key:
            raise ValueError(
                "智谱 AI API Key 未提供。"
                "请设置 ZHIPUAI_API_KEY 或 ZHIPU_API_KEY 环境变量，或传入 api_key 参数。"
            )
        
        self.api_key = api_key
        self._client = None
    
    @property
    def client(self):
        """延迟初始化智谱客户端（使用证书管理器）"""
        if self._client is None:
            try:
                from zhipuai import ZhipuAI
                import httpx
                
                # 尝试使用证书管理器
                http_client = self._create_http_client_with_certs()
                
                if http_client:
                    self._client = ZhipuAI(api_key=self.api_key, http_client=http_client)
                    logger.info("智谱 AI 客户端初始化成功（使用证书管理器）")
                else:
                    self._client = ZhipuAI(api_key=self.api_key)
                    logger.info("智谱 AI 客户端初始化成功（默认配置）")
                    
            except ImportError:
                raise ImportError(
                    "请安装 zhipuai 包: pip install zhipuai"
                )
        return self._client
    
    def _create_http_client_with_certs(self):
        """
        创建带证书配置的 HTTP 客户端
        
        优先使用证书管理器，回退到 certifi。
        
        Returns:
            httpx.Client 或 None
        """
        import httpx
        
        # 方法1: 使用证书管理器
        try:
            from tableau_assistant.cert_manager import CertificateManager
            
            cert_manager = CertificateManager()
            
            # 注册智谱 AI 服务
            try:
                cert_manager.register_preconfigured_services(["zhipu-ai"])
            except Exception:
                pass  # 可能已注册
            
            # 获取 SSL 配置
            ssl_config = cert_manager.get_service_ssl_config("zhipu-ai", library="httpx")
            logger.debug(f"使用证书管理器 SSL 配置: {ssl_config}")
            
            return httpx.Client(**ssl_config)
            
        except Exception as e:
            logger.debug(f"证书管理器不可用: {e}")
        
        # 方法2: 使用 certifi
        try:
            import ssl
            import certifi
            
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            logger.debug("使用 certifi 证书")
            return httpx.Client(verify=ssl_context)
            
        except Exception as e:
            logger.debug(f"certifi 不可用: {e}")
        
        # 方法3: 返回 None，使用默认配置
        return None
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        向量化文档列表
        
        支持批量处理，自动分批调用 API。
        
        Args:
            texts: 文档文本列表
        
        Returns:
            向量列表
        """
        if not texts:
            return []
        
        all_vectors = []
        batches = self._batch_texts(texts)
        
        for batch_idx, batch in enumerate(batches):
            logger.debug(f"处理批次 {batch_idx + 1}/{len(batches)}, 文档数: {len(batch)}")
            
            try:
                # 调用智谱 API
                response = self.client.embeddings.create(
                    model=self.model_name,
                    input=batch
                )
                
                # 提取向量
                for item in response.data:
                    all_vectors.append(item.embedding)
                    
            except Exception as e:
                logger.error(f"智谱 Embedding API 调用失败: {e}")
                raise
        
        return all_vectors
    
    def embed_query(self, text: str) -> List[float]:
        """
        向量化查询文本
        
        Args:
            text: 查询文本
        
        Returns:
            查询向量
        """
        if not text:
            raise ValueError("查询文本不能为空")
        
        try:
            response = self.client.embeddings.create(
                model=self.model_name,
                input=[text]
            )
            return response.data[0].embedding
            
        except Exception as e:
            logger.error(f"智谱 Embedding API 调用失败: {e}")
            raise


class MockEmbedding(EmbeddingProvider):
    """
    Mock Embedding 提供者（用于测试）
    
    生成固定维度的随机向量，不调用真实 API。
    支持固定种子以生成确定性向量。
    
    Attributes:
        seed: 随机种子（可选，用于生成确定性向量）
        deterministic: 是否使用确定性模式（基于文本哈希）
    """
    
    def __init__(
        self,
        dimensions: int = 1024,
        batch_size: int = 32,
        seed: Optional[int] = None,
        deterministic: bool = False
    ):
        """
        初始化 Mock Embedding 提供者
        
        Args:
            dimensions: 向量维度
            batch_size: 批量处理大小
            seed: 随机种子（可选）
            deterministic: 是否使用确定性模式（相同文本生成相同向量）
        """
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
        """
        基于文本哈希生成确定性向量
        
        Args:
            text: 输入文本
        
        Returns:
            确定性向量
        """
        import random
        # 使用文本哈希作为种子
        text_hash = self.compute_text_hash(text)
        # 将哈希转换为整数种子
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
    
    支持创建不同类型的 Embedding 提供者。
    """
    
    _providers: Dict[str, type] = {
        "zhipu": ZhipuEmbedding,
        "mock": MockEmbedding,
    }
    
    @classmethod
    def register(cls, name: str, provider_class: type) -> None:
        """
        注册新的 Embedding 提供者
        
        Args:
            name: 提供者名称
            provider_class: 提供者类
        """
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
            provider_name: 提供者名称（zhipu, mock）
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
    "EmbeddingProvider",
    "ZhipuEmbedding",
    "MockEmbedding",
    "EmbeddingProviderFactory",
]
