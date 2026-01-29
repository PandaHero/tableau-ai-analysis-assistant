"""RAG 服务异常定义"""


class RAGError(Exception):
    """RAG 服务基础异常"""
    pass


class EmbeddingError(RAGError):
    """Embedding 相关错误"""
    pass


class IndexError(RAGError):
    """索引相关错误"""
    pass


class IndexExistsError(IndexError):
    """索引已存在"""
    pass


class IndexNotFoundError(IndexError):
    """索引不存在"""
    pass


class IndexCreationError(IndexError):
    """索引创建失败"""
    pass


class StorageError(RAGError):
    """存储相关错误"""
    pass


class RetrievalError(RAGError):
    """检索相关错误"""
    pass
