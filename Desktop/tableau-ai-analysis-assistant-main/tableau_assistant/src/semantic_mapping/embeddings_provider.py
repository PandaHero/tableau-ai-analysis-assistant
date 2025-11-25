"""
Embeddings Provider - 统一的 Embedding 提供者

支持本地模型和 OpenAI API，优先使用本地模型。
"""
import logging
from typing import Optional
from langchain.embeddings.base import Embeddings

logger = logging.getLogger(__name__)


class EmbeddingsProvider:
    """
    统一的 Embedding 提供者
    
    策略：
    1. 优先使用本地模型（sentence-transformers）
    2. 如果本地模型加载失败，回退到 OpenAI API
    3. 支持手动指定 provider
    """
    
    def __init__(
        self,
        provider: Optional[str] = None,
        model_name: Optional[str] = None
    ):
        """
        初始化 Embeddings Provider
        
        Args:
            provider: 指定提供者 ("local", "openai", "azure")，None 表示自动选择
            model_name: 模型名称，None 表示使用默认值
        """
        self.provider = provider
        self.model_name = model_name
        self.embeddings = self._create_embeddings()
    
    def _create_embeddings(self) -> Embeddings:
        """创建 Embeddings 实例"""
        
        # 如果指定了 provider，直接使用
        if self.provider:
            return self._create_embeddings_by_provider(self.provider)
        
        # 自动选择：优先本地模型
        try:
            logger.info("尝试加载本地 embedding 模型...")
            return self._create_local_embeddings()
        except Exception as e:
            logger.warning(f"本地模型加载失败: {e}")
            logger.info("回退到 OpenAI API...")
            return self._create_openai_embeddings()
    
    def _create_embeddings_by_provider(self, provider: str) -> Embeddings:
        """根据指定的 provider 创建 Embeddings"""
        if provider == "local":
            return self._create_local_embeddings()
        elif provider == "openai":
            return self._create_openai_embeddings()
        elif provider == "azure":
            return self._create_azure_embeddings()
        else:
            raise ValueError(f"不支持的 provider: {provider}")
    
    def _create_local_embeddings(self) -> Embeddings:
        """创建本地 Embedding 模型"""
        from langchain_community.embeddings import HuggingFaceEmbeddings
        
        # 默认使用中文模型
        model_name = self.model_name or "BAAI/bge-small-zh-v1.5"
        
        logger.info(f"加载本地 embedding 模型: {model_name}")
        
        embeddings = HuggingFaceEmbeddings(
            model_name=model_name,
            model_kwargs={'device': 'cpu'},  # 使用 CPU
            encode_kwargs={'normalize_embeddings': True}  # 归一化向量
        )
        
        logger.info("本地 embedding 模型加载成功")
        return embeddings
    
    def _create_openai_embeddings(self) -> Embeddings:
        """创建 OpenAI Embedding 模型"""
        from tableau_assistant.src.utils.tableau.models import select_embeddings
        
        # 默认使用 text-embedding-3-small
        model_name = self.model_name or "text-embedding-3-small"
        
        logger.info(f"使用 OpenAI embedding 模型: {model_name}")
        
        embeddings = select_embeddings("openai", model_name)
        
        logger.info("OpenAI embedding 模型配置成功")
        return embeddings
    
    def _create_azure_embeddings(self) -> Embeddings:
        """创建 Azure OpenAI Embedding 模型"""
        from tableau_assistant.src.utils.tableau.models import select_embeddings
        
        model_name = self.model_name or "text-embedding-ada-002"
        
        logger.info(f"使用 Azure OpenAI embedding 模型: {model_name}")
        
        embeddings = select_embeddings("azure", model_name)
        
        logger.info("Azure OpenAI embedding 模型配置成功")
        return embeddings
    
    def get_embeddings(self) -> Embeddings:
        """获取 Embeddings 实例"""
        return self.embeddings
    
    def embed_query(self, text: str) -> list:
        """对查询文本进行向量化"""
        return self.embeddings.embed_query(text)
    
    def embed_documents(self, texts: list) -> list:
        """对文档列表进行向量化"""
        return self.embeddings.embed_documents(texts)


# ============= 导出 =============

__all__ = ["EmbeddingsProvider"]
