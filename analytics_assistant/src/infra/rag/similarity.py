"""相似度计算模块

提供统一的相似度计算接口，根据配置选择计算方式。

支持的相似度类型：
- L2: 欧几里得距离，similarity = 1.0 / (1.0 + distance)
- Cosine: 余弦相似度，similarity = (score + 1.0) / 2.0
- Inner Product: 内积，similarity = (score + 1.0) / 2.0
"""

import logging
from enum import Enum
from typing import Callable

from analytics_assistant.src.infra.config import get_config

logger = logging.getLogger(__name__)

class ScoreType(str, Enum):
    """相似度计算类型"""
    L2 = "l2"
    COSINE = "cosine"
    INNER_PRODUCT = "inner_product"

def cosine_similarity(vec1: list[float], vec2: list[float]) -> float:
    """计算两个向量的余弦相似度。
    
    余弦相似度 = (A · B) / (||A|| * ||B||)
    
    Args:
        vec1: 第一个向量
        vec2: 第二个向量
        
    Returns:
        余弦相似度，范围 [-1, 1]，相同向量返回 1.0
        如果任一向量为空或长度不匹配，返回 0.0
    
    Examples:
        >>> cosine_similarity([1.0, 0.0], [1.0, 0.0])
        1.0
        >>> cosine_similarity([1.0, 0.0], [0.0, 1.0])
        0.0
        >>> cosine_similarity([1.0, 2.0, 3.0], [-1.0, -2.0, -3.0])
        -1.0
    """
    if not vec1 or not vec2 or len(vec1) != len(vec2):
        return 0.0
    
    dot_product = sum(a * b for a, b in zip(vec1, vec2))
    norm1 = sum(a * a for a in vec1) ** 0.5
    norm2 = sum(b * b for b in vec2) ** 0.5
    
    if norm1 == 0 or norm2 == 0:
        return 0.0
    
    return dot_product / (norm1 * norm2)

def l2_similarity(distance: float) -> float:
    """将 L2 距离转换为相似度。
    
    公式: similarity = 1.0 / (1.0 + distance)
    
    Args:
        distance: L2 距离（欧几里得距离）
        
    Returns:
        归一化的相似度，范围 (0, 1]
        距离为 0 时返回 1.0，距离越大相似度越低
    
    Examples:
        >>> l2_similarity(0.0)
        1.0
        >>> l2_similarity(1.0)
        0.5
        >>> l2_similarity(9.0)
        0.1
    """
    return 1.0 / (1.0 + distance)

def inner_product_similarity(score: float) -> float:
    """将内积分数转换为相似度。
    
    公式: similarity = (score + 1.0) / 2.0
    
    假设向量已归一化，内积范围为 [-1, 1]。
    
    Args:
        score: 内积分数
        
    Returns:
        归一化的相似度，范围 [0, 1]
    
    Examples:
        >>> inner_product_similarity(1.0)
        1.0
        >>> inner_product_similarity(0.0)
        0.5
        >>> inner_product_similarity(-1.0)
        0.0
    """
    return (score + 1.0) / 2.0

class SimilarityCalculator:
    """相似度计算器
    
    根据配置的 score_type 选择相似度计算公式。
    提供统一的接口供各组件使用。
    
    Attributes:
        score_type: 当前使用的相似度类型
    
    Examples:
        >>> calc = SimilarityCalculator(ScoreType.L2)
        >>> calc.normalize(0.0)  # L2 距离为 0
        1.0
        >>> calc.normalize(1.0)  # L2 距离为 1
        0.5
        
        >>> calc = SimilarityCalculator(ScoreType.COSINE)
        >>> calc.normalize(1.0)  # 余弦相似度为 1
        1.0
        >>> calc.normalize(-1.0)  # 余弦相似度为 -1
        0.0
    """
    
    # 各类型的归一化公式
    FORMULAS: dict[ScoreType, Callable[[float], float]] = {
        ScoreType.L2: l2_similarity,
        ScoreType.COSINE: inner_product_similarity,  # 余弦和内积使用相同公式
        ScoreType.INNER_PRODUCT: inner_product_similarity,
    }
    
    # 默认类型
    _DEFAULT_SCORE_TYPE = ScoreType.L2
    
    def __init__(self, score_type: ScoreType = ScoreType.L2):
        """初始化相似度计算器。
        
        Args:
            score_type: 相似度计算类型
        """
        self._score_type = score_type
        self._formula = self.FORMULAS.get(score_type, l2_similarity)
    
    @property
    def score_type(self) -> ScoreType:
        """获取当前的相似度类型"""
        return self._score_type
    
    def normalize(self, raw_score: float) -> float:
        """归一化原始分数到 [0, 1] 范围。
        
        Args:
            raw_score: 原始分数（L2 距离或内积/余弦分数）
            
        Returns:
            归一化后的相似度，范围 [0, 1]
        """
        result = self._formula(raw_score)
        # 确保结果在 [0, 1] 范围内
        return max(0.0, min(1.0, result))
    
    def compute_cosine(self, vec1: list[float], vec2: list[float]) -> float:
        """计算两个向量的余弦相似度。
        
        这是一个便捷方法，直接计算向量间的余弦相似度，
        不受 score_type 配置影响。
        
        Args:
            vec1: 第一个向量
            vec2: 第二个向量
            
        Returns:
            余弦相似度，范围 [-1, 1]
        """
        return cosine_similarity(vec1, vec2)
    
    def compute_normalized_cosine(self, vec1: list[float], vec2: list[float]) -> float:
        """计算归一化的余弦相似度。
        
        将余弦相似度从 [-1, 1] 映射到 [0, 1]。
        
        Args:
            vec1: 第一个向量
            vec2: 第二个向量
            
        Returns:
            归一化的余弦相似度，范围 [0, 1]
        """
        raw_cosine = cosine_similarity(vec1, vec2)
        return inner_product_similarity(raw_cosine)
    
    @classmethod
    def from_config(cls) -> "SimilarityCalculator":
        """从配置创建实例。
        
        从 app.yaml 的 rag_service.retrieval.score_type 读取配置。
        
        Returns:
            配置的 SimilarityCalculator 实例
        """
        try:
            config = get_config()
            score_type_str = config.config.get("rag_service", {}).get(
                "retrieval", {}
            ).get("score_type", "l2")
            
            try:
                score_type = ScoreType(score_type_str)
            except ValueError:
                logger.warning(
                    f"不支持的 score_type: {score_type_str}，回退到 l2"
                )
                score_type = cls._DEFAULT_SCORE_TYPE
            
            logger.debug(f"SimilarityCalculator 使用 score_type: {score_type.value}")
            return cls(score_type)
            
        except Exception as e:
            logger.warning(f"加载相似度配置失败，使用默认值 l2: {e}")
            return cls(cls._DEFAULT_SCORE_TYPE)

__all__ = [
    "ScoreType",
    "SimilarityCalculator",
    "cosine_similarity",
    "l2_similarity",
    "inner_product_similarity",
]
