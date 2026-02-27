# -*- coding: utf-8 -*-
"""维度种子数据类型定义"""
from dataclasses import dataclass, field

# level → granularity 映射
_LEVEL_GRANULARITY_MAP: dict[int, str] = {
    1: "coarsest",
    2: "coarse",
    3: "medium",
    4: "fine",
    5: "finest",
}

@dataclass
class DimensionSeed:
    """维度模式种子

    granularity 由 level 自动计算，消除冗余字段。
    """

    field_caption: str
    data_type: str
    category: str
    category_detail: str
    level: int
    business_description: str
    aliases: list[str] = field(default_factory=list)
    reasoning: str = ""

    @property
    def granularity(self) -> str:
        """根据 level 自动计算粒度"""
        return _LEVEL_GRANULARITY_MAP.get(self.level, "unknown")

    def to_dict(self) -> dict:
        """转换为字典（兼容旧的 list[dict] 格式）"""
        return {
            "field_caption": self.field_caption,
            "data_type": self.data_type,
            "category": self.category,
            "category_detail": self.category_detail,
            "level": self.level,
            "granularity": self.granularity,
            "business_description": self.business_description,
            "aliases": list(self.aliases),
            "reasoning": self.reasoning,
        }

@dataclass
class MeasureSeed:
    """度量模式种子"""

    field_caption: str
    data_type: str
    measure_category: str
    business_description: str
    aliases: list[str] = field(default_factory=list)
    reasoning: str = ""

    def to_dict(self) -> dict:
        """转换为字典（兼容旧的 list[dict] 格式）"""
        return {
            "field_caption": self.field_caption,
            "data_type": self.data_type,
            "measure_category": self.measure_category,
            "business_description": self.business_description,
            "aliases": list(self.aliases),
            "reasoning": self.reasoning,
        }
