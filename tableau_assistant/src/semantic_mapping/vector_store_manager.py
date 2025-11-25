"""
Vector Store Manager - FAISS 向量存储管理

负责创建、保存、加载和检索 FAISS 向量索引。
"""
import os
import logging
from typing import List, Tuple, Optional
from pathlib import Path
from langchain.schema import Document
from langchain_community.vectorstores import FAISS
from langchain.embeddings.base import Embeddings

logger = logging.getLogger(__name__)


class VectorStoreManager:
    """
    FAISS 向量存储管理器
    
    功能：
    - 创建向量索引
    - 保存/加载索引
    - 相似度检索
    - 增量更新
    """
    
    def __init__(
        self,
        datasource_luid: str,
        embeddings: Embeddings,
        store_base_path: str = "data/vector_stores"
    ):
        """
        初始化 Vector Store Manager
        
        Args:
            datasource_luid: 数据源 LUID
            embeddings: Embeddings 实例
            store_base_path: 存储基础路径
        """
        self.datasource_luid = datasource_luid
        self.embeddings = embeddings
        self.store_base_path = store_base_path
        self.store_path = os.path.join(store_base_path, datasource_luid)
        
        # 确保存储目录存在
        Path(self.store_path).mkdir(parents=True, exist_ok=True)
        
        # 缓存的 vectorstore 实例
        self._vectorstore: Optional[FAISS] = None
    
    def create_index(self, documents: List[Document]) -> FAISS:
        """
        创建 FAISS 索引
        
        Args:
            documents: 文档列表
        
        Returns:
            FAISS vectorstore 实例
        """
        if not documents:
            raise ValueError("文档列表不能为空")
        
        logger.info(f"创建 FAISS 索引: {len(documents)} 个文档")
        
        # 创建 FAISS 索引
        vectorstore = FAISS.from_documents(
            documents=documents,
            embedding=self.embeddings
        )
        
        # 保存到磁盘
        self.save_index(vectorstore)
        
        # 缓存
        self._vectorstore = vectorstore
        
        logger.info(f"FAISS 索引创建成功，已保存到: {self.store_path}")
        
        return vectorstore
    
    def save_index(self, vectorstore: FAISS):
        """
        保存 FAISS 索引到磁盘
        
        Args:
            vectorstore: FAISS vectorstore 实例
        """
        vectorstore.save_local(self.store_path)
        logger.debug(f"FAISS 索引已保存: {self.store_path}")
    
    def load_index(self) -> FAISS:
        """
        从磁盘加载 FAISS 索引
        
        Returns:
            FAISS vectorstore 实例
        
        Raises:
            FileNotFoundError: 如果索引文件不存在
        """
        # 检查缓存
        if self._vectorstore is not None:
            logger.debug("使用缓存的 FAISS 索引")
            return self._vectorstore
        
        # 检查索引文件是否存在
        index_file = os.path.join(self.store_path, "index.faiss")
        if not os.path.exists(index_file):
            raise FileNotFoundError(
                f"FAISS 索引不存在: {index_file}。"
                f"请先调用 create_index() 创建索引。"
            )
        
        logger.info(f"加载 FAISS 索引: {self.store_path}")
        
        # 加载索引
        vectorstore = FAISS.load_local(
            self.store_path,
            embeddings=self.embeddings,
            allow_dangerous_deserialization=True  # 信任本地文件
        )
        
        # 缓存
        self._vectorstore = vectorstore
        
        logger.info("FAISS 索引加载成功")
        
        return vectorstore
    
    def index_exists(self) -> bool:
        """
        检查索引是否存在
        
        Returns:
            True 如果索引存在，否则 False
        """
        index_file = os.path.join(self.store_path, "index.faiss")
        return os.path.exists(index_file)
    
    def similarity_search(
        self,
        query: str,
        k: int = 5,
        score_threshold: Optional[float] = None
    ) -> List[Tuple[Document, float]]:
        """
        相似度检索
        
        Args:
            query: 查询文本
            k: 返回的结果数量
            score_threshold: 相似度阈值（可选），过滤低于此分数的结果
        
        Returns:
            (Document, score) 元组列表，按相似度降序排列
        """
        vectorstore = self.load_index()
        
        logger.debug(f"执行相似度检索: query='{query}', k={k}")
        
        # 执行检索
        results = vectorstore.similarity_search_with_score(query, k=k)
        
        # 过滤低分结果
        if score_threshold is not None:
            results = [
                (doc, score) for doc, score in results
                if score >= score_threshold
            ]
            logger.debug(f"过滤后剩余 {len(results)} 个结果")
        
        logger.debug(f"检索完成: 返回 {len(results)} 个结果")
        
        return results
    
    def add_documents(self, documents: List[Document]):
        """
        增量添加文档到现有索引
        
        Args:
            documents: 要添加的文档列表
        """
        if not documents:
            logger.warning("没有文档需要添加")
            return
        
        logger.info(f"增量添加 {len(documents)} 个文档到索引")
        
        try:
            # 加载现有索引
            vectorstore = self.load_index()
            
            # 添加新文档
            vectorstore.add_documents(documents)
            
            # 保存更新后的索引
            self.save_index(vectorstore)
            
            # 更新缓存
            self._vectorstore = vectorstore
            
            logger.info("文档添加成功")
            
        except FileNotFoundError:
            # 如果索引不存在，创建新索引
            logger.info("索引不存在，创建新索引")
            self.create_index(documents)
    
    def delete_index(self):
        """删除索引文件"""
        import shutil
        
        if os.path.exists(self.store_path):
            shutil.rmtree(self.store_path)
            logger.info(f"索引已删除: {self.store_path}")
        
        # 清除缓存
        self._vectorstore = None
    
    def get_document_count(self) -> int:
        """
        获取索引中的文档数量
        
        Returns:
            文档数量
        """
        try:
            vectorstore = self.load_index()
            return vectorstore.index.ntotal
        except FileNotFoundError:
            return 0


# ============= 导出 =============

__all__ = ["VectorStoreManager"]
