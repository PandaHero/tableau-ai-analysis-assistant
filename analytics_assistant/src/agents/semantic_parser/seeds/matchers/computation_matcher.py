# -*- coding: utf-8 -*-
"""
计算种子匹配器

从文本中匹配计算种子，用于规则预处理阶段。

用法：
    from analytics_assistant.src.agents.semantic_parser.seeds.matchers import ComputationMatcher
    
    matcher = ComputationMatcher()
    seeds = matcher.find_in_text("各地区的利润率和同比增长")
    # [ComputationSeed(name='profit_rate', ...), ComputationSeed(name='yoy_growth', ...)]
"""
from typing import Dict, List, Optional

from analytics_assistant.src.infra.seeds import COMPUTATION_SEEDS, ComputationSeed


class ComputationMatcher:
    """计算种子匹配器
    
    提供计算种子的查找和匹配功能。
    """
    
    def __init__(self):
        """初始化匹配器，构建关键词索引。"""
        self._keyword_to_seed: Dict[str, ComputationSeed] = {}
        self._build_index()
    
    def _build_index(self) -> None:
        """构建关键词索引。"""
        for seed in COMPUTATION_SEEDS:
            for keyword in seed.keywords:
                self._keyword_to_seed[keyword.lower()] = seed
    
    def get_by_keyword(self, keyword: str) -> Optional[ComputationSeed]:
        """根据关键词获取计算种子。
        
        Args:
            keyword: 关键词（如"利润率"、"同比增长"）
        
        Returns:
            匹配的 ComputationSeed，未找到返回 None
        
        Example:
            >>> matcher = ComputationMatcher()
            >>> seed = matcher.get_by_keyword("利润率")
            >>> seed.calc_type
            'RATIO'
        """
        return self._keyword_to_seed.get(keyword.lower())
    
    def find_in_text(self, text: str) -> List[ComputationSeed]:
        """从文本中查找匹配的计算种子。
        
        Args:
            text: 用户问题文本
        
        Returns:
            匹配的 ComputationSeed 列表（去重）
        
        Example:
            >>> matcher = ComputationMatcher()
            >>> seeds = matcher.find_in_text("各地区的利润率和同比增长")
            >>> [s.display_name for s in seeds]
            ['利润率', '同比增长率']
        """
        text_lower = text.lower()
        found: List[ComputationSeed] = []
        seen_names: set = set()
        
        for seed in COMPUTATION_SEEDS:
            if seed.name in seen_names:
                continue
            for keyword in seed.keywords:
                if keyword.lower() in text_lower:
                    found.append(seed)
                    seen_names.add(seed.name)
                    break
        
        return found
    
    def get_all_keywords(self) -> List[str]:
        """获取所有计算关键词。
        
        Returns:
            所有计算种子的关键词列表（去重）
        """
        keywords = set()
        for seed in COMPUTATION_SEEDS:
            keywords.update(seed.keywords)
        return sorted(keywords)
    
    def get_by_calc_type(self, calc_type: str) -> List[ComputationSeed]:
        """根据计算类型获取种子列表。
        
        Args:
            calc_type: 计算类型（如 "RATIO", "TABLE_CALC_PERCENT_DIFF"）
        
        Returns:
            该类型的所有计算种子
        """
        return [seed for seed in COMPUTATION_SEEDS if seed.calc_type == calc_type]
    
    def format_as_guide(self) -> str:
        """格式化计算种子为 Prompt 指南。
        
        生成用于 Prompt 的计算表达式参考指南。
        
        Returns:
            格式化的计算指南字符串
        """
        lines = ["<common_computations>"]
        lines.append("常见计算表达式参考：")
        lines.append("")
        
        # 按类型分组
        type_groups: Dict[str, List[ComputationSeed]] = {}
        for seed in COMPUTATION_SEEDS:
            if seed.calc_type not in type_groups:
                type_groups[seed.calc_type] = []
            type_groups[seed.calc_type].append(seed)
        
        # 类型名称映射
        type_names = {
            "RATIO": "比率计算",
            "DIFFERENCE": "差值计算",
            "SUM": "求和计算",
            "PRODUCT": "乘积计算",
            "TABLE_CALC_PERCENT_OF_TOTAL": "占比计算",
            "TABLE_CALC_PERCENT_DIFF": "增长率计算",
            "TABLE_CALC_DIFFERENCE": "差异计算",
            "TABLE_CALC_RANK": "排名计算",
            "TABLE_CALC_RUNNING": "累计计算",
            "TABLE_CALC_MOVING": "移动计算",
        }
        
        for calc_type, seeds in type_groups.items():
            type_name = type_names.get(calc_type, calc_type)
            lines.append(f"【{type_name}】")
            for seed in seeds:
                keywords_str = "、".join(seed.keywords[:3])
                if seed.formula:
                    lines.append(f"  - {seed.display_name}（{keywords_str}）: {seed.formula}")
                else:
                    lines.append(f"  - {seed.display_name}（{keywords_str}）")
            lines.append("")
        
        lines.append("</common_computations>")
        return "\n".join(lines)


__all__ = ["ComputationMatcher"]
