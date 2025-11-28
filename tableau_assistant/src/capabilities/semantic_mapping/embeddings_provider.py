"""
Embeddings Provider - 统一的 Embedding 提供者

支持本地模型和 OpenAI API，优先使用本地模型。
"""
import logging
from typing import List, Optional
from langchain.embeddings.base import Embeddings

logger = logging.getLogger(__name__)


class BCEmbeddingsWrapper(Embeddings):
    """
    BCEmbedding 的 LangChain 包装器
    
    将 BCEmbedding.EmbeddingModel 适配为 LangChain Embeddings 接口
    """
    
    def __init__(self, bce_model):
        """
        初始化包装器
        
        Args:
            bce_model: BCEmbedding.EmbeddingModel 实例
        """
        self.bce_model = bce_model
    
    def embed_documents(self, texts: List[str]) -> List[List[float]]:
        """
        对文档列表进行向量化
        
        Args:
            texts: 文本列表
        
        Returns:
            嵌入向量列表
        """
        # BCEmbedding.encode 返回 numpy 数组
        embeddings = self.bce_model.encode(texts)
        # 转换为列表
        return embeddings.tolist()
    
    def embed_query(self, text: str) -> List[float]:
        """
        对查询文本进行向量化
        
        Args:
            text: 查询文本
        
        Returns:
            嵌入向量
        """
        # BCEmbedding.encode 接受列表，返回 numpy 数组
        embedding = self.bce_model.encode([text])
        # 返回第一个向量（转换为列表）
        return embedding[0].tolist()


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
        
        # 自动选择策略（按优先级）：
        # 1. 智谱 AI（国内可用，速度快，效果好）
        # 2. 本地模型（完全离线，但需要下载）
        # 3. OpenAI（需要科学上网）
        
        import os
        
        # 优先尝试智谱 AI
        if os.environ.get("ZHIPUAI_API_KEY"):
            try:
                logger.info("检测到智谱 AI API Key，使用智谱 AI embedding...")
                return self._create_zhipu_embeddings()
            except Exception as e:
                logger.warning(f"智谱 AI 初始化失败: {e}")
        
        # 回退到本地模型
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
        elif provider == "zhipu":
            return self._create_zhipu_embeddings()
        else:
            raise ValueError(f"不支持的 provider: {provider}")
    
    def _create_local_embeddings(self) -> Embeddings:
        """创建本地 Embedding 模型（使用官方 BCEmbedding 包）"""
        import os
        
        # ⭐ 设置 HuggingFace 镜像（必须在导入 BCEmbedding 前设置）
        # 参考：https://hf-mirror.com
        if 'HF_ENDPOINT' not in os.environ:
            os.environ['HF_ENDPOINT'] = 'https://hf-mirror.com'
            logger.info("设置 HuggingFace 镜像: https://hf-mirror.com")
        
        try:
            from BCEmbedding import EmbeddingModel
        except ImportError:
            raise ImportError(
                "BCEmbedding 包未安装。请运行: pip install BCEmbedding==0.1.1"
            )
        
        # 默认使用 bce-embedding-base-v1（中文优化）
        model_name = self.model_name or "maidalun1020/bce-embedding-base_v1"
        
        logger.info(f"加载本地 embedding 模型: {model_name}")
        logger.info(f"HF_ENDPOINT: {os.environ.get('HF_ENDPOINT', 'not set')}")
        
        # 使用官方 BCEmbedding 包初始化
        bce_model = EmbeddingModel(model_name_or_path=model_name)
        
        # 包装为 LangChain Embeddings 接口
        embeddings = BCEmbeddingsWrapper(bce_model)
        
        logger.info("本地 embedding 模型加载成功")
        return embeddings
    
    def _create_openai_embeddings(self) -> Embeddings:
        """创建 OpenAI Embedding 模型"""
        from tableau_assistant.src.bi_platforms.tableau.models import select_embeddings
        
        # 默认使用 text-embedding-3-small
        model_name = self.model_name or "text-embedding-3-small"
        
        logger.info(f"使用 OpenAI embedding 模型: {model_name}")
        
        embeddings = select_embeddings("openai", model_name)
        
        logger.info("OpenAI embedding 模型配置成功")
        return embeddings
    
    def _create_azure_embeddings(self) -> Embeddings:
        """创建 Azure OpenAI Embedding 模型"""
        from tableau_assistant.src.bi_platforms.tableau.models import select_embeddings
        
        model_name = self.model_name or "text-embedding-ada-002"
        
        logger.info(f"使用 Azure OpenAI embedding 模型: {model_name}")
        
        embeddings = select_embeddings("azure", model_name)
        
        logger.info("Azure OpenAI embedding 模型配置成功")
        return embeddings
    
    def _create_zhipu_embeddings(self) -> Embeddings:
        """创建智谱 AI Embedding 模型（国内可用）"""
        import os
        from langchain_community.embeddings import ZhipuAIEmbeddings
        from zhipuai import ZhipuAI
        import httpx
        
        # 从环境变量获取 API Key
        api_key = os.environ.get("ZHIPUAI_API_KEY")
        if not api_key:
            raise ValueError(
                "智谱 AI API Key 未设置。请设置环境变量 ZHIPUAI_API_KEY\n"
                "获取 API Key: https://open.bigmodel.cn/"
            )
        
        model_name = self.model_name or "embedding-2"
        
        logger.info(f"使用智谱 AI embedding 模型: {model_name}")
        
        # 使用增强的证书管理器
        try:
            from tableau_assistant.cert_manager import CertificateManager
            
            # 初始化证书管理器
            cert_manager = CertificateManager()
            
            # 注册智谱 AI 服务（如果尚未注册）
            try:
                cert_manager.register_preconfigured_services(["zhipu-ai"])
                logger.info("智谱 AI 服务已注册到证书管理器")
            except Exception as e:
                logger.debug(f"智谱 AI 服务可能已注册: {e}")
            
            # 获取智谱 AI 的 SSL 配置
            ssl_config = cert_manager.get_service_ssl_config("zhipu-ai", library="httpx")
            logger.info(f"使用证书管理器的 SSL 配置: {ssl_config}")
            
            # 创建自定义的 httpx 客户端（使用证书管理器的配置）
            http_client = httpx.Client(**ssl_config)
            
            # 创建智谱 AI 客户端（带自定义 SSL 配置）
            zhipu_client = ZhipuAI(
                api_key=api_key,
                http_client=http_client
            )
            
            # 创建 LangChain Embeddings（使用自定义客户端）
            embeddings = ZhipuAIEmbeddings(
                api_key=api_key,
                model=model_name,
                zhipuai_api_key=api_key  # 确保传递 API Key
            )
            
            # 替换内部客户端
            embeddings.client = zhipu_client
            
            logger.info("智谱 AI embedding 模型配置成功（使用增强的证书管理器）")
            return embeddings
            
        except Exception as e:
            logger.error(f"使用证书管理器失败: {e}")
            # 回退到 certifi
            logger.warning("回退到 certifi 证书")
            import ssl
            import certifi
            
            ssl_context = ssl.create_default_context(cafile=certifi.where())
            http_client = httpx.Client(verify=ssl_context)
            
            zhipu_client = ZhipuAI(
                api_key=api_key,
                http_client=http_client
            )
            
            embeddings = ZhipuAIEmbeddings(
                api_key=api_key,
                model=model_name,
                zhipuai_api_key=api_key
            )
            
            embeddings.client = zhipu_client
            
            logger.info("智谱 AI embedding 模型配置成功（使用 certifi 回退）")
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
