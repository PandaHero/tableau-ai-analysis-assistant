"""搜索相关数据模型"""

from dataclasses import dataclass, field
from typing import Any, Dict, Optional


@dataclass
class SearchResult:
    """搜索结果"""
    doc_id: str
    content: str
    score: float  # 归一化分数 [0, 1]
    rank: int
    metadata: Dict[str, Any] = field(default_factory=dict)
    
    # 原始分数（用于调试）
    raw_score: Optional[float] = None
