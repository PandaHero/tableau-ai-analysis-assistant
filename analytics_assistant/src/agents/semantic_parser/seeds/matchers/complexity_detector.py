# -*- coding: utf-8 -*-
"""
复杂度检测器

基于关键词和计算种子检测问题复杂度。

用法：
    from analytics_assistant.src.agents.semantic_parser.seeds.matchers import ComplexityDetector
    
    detector = ComplexityDetector()
    complexity = detector.detect("各地区的利润率同比增长")
    # ['RATIO', 'TIME_COMPARE']
"""
from typing import List

from analytics_assistant.src.infra.seeds import COMPLEXITY_KEYWORDS, ComputationSeed


class ComplexityDetector:
    """复杂度检测器
    
    基于计算种子的 calc_type 和关键词检测问题复杂度。
    """
    
    # calc_type 到复杂度类型的映射
    CALC_TYPE_TO_COMPLEXITY = {
        "RATIO": "RATIO",
        "TABLE_CALC_PERCENT_OF_TOTAL": "SHARE",
        "TABLE_CALC_PERCENT_DIFF": "TIME_COMPARE",
        "TABLE_CALC_DIFFERENCE": "TIME_COMPARE",
        "TABLE_CALC_RANK": "RANK",
        "TABLE_CALC_RUNNING": "CUMULATIVE",
        "TABLE_CALC_MOVING": "CUMULATIVE",
    }
    
    def detect(
        self, 
        question: str, 
        matched_computations: List[ComputationSeed] | None = None,
    ) -> List[str]:
        """检测问题复杂度类型。
        
        复杂度主要从计算种子的 calc_type 推断，而不是重复匹配关键词。
        
        Args:
            question: 用户问题
            matched_computations: 已匹配的计算种子列表（可选）
        
        Returns:
            复杂度类型列表，如 ['RATIO', 'TIME_COMPARE']
        """
        detected: List[str] = []
        
        # 从计算种子的 calc_type 推断复杂度
        if matched_computations:
            for comp in matched_computations:
                complexity = self.CALC_TYPE_TO_COMPLEXITY.get(comp.calc_type)
                if complexity and complexity not in detected:
                    detected.append(complexity)
        
        # 补充：检测子查询（这个在 computation_seeds 中没有覆盖）
        subquery_keywords = COMPLEXITY_KEYWORDS.get("subquery", [])
        question_lower = question.lower()
        if any(kw in question_lower for kw in subquery_keywords):
            if "SUBQUERY" not in detected:
                detected.append("SUBQUERY")
        
        # 如果没有检测到复杂类型，标记为简单
        if not detected:
            detected.append("SIMPLE")
        
        return detected
    
    def has_derived_metric(self, question: str) -> bool:
        """检测是否包含派生度量关键词。"""
        keywords = COMPLEXITY_KEYWORDS.get("derived_metric", [])
        question_lower = question.lower()
        return any(kw in question_lower for kw in keywords)
    
    def has_time_calc(self, question: str) -> bool:
        """检测是否包含时间计算关键词。"""
        keywords = COMPLEXITY_KEYWORDS.get("time_calc", [])
        question_lower = question.lower()
        return any(kw in question_lower for kw in keywords)
    
    def has_subquery(self, question: str) -> bool:
        """检测是否包含子查询关键词。"""
        keywords = COMPLEXITY_KEYWORDS.get("subquery", [])
        question_lower = question.lower()
        return any(kw in question_lower for kw in keywords)
    
    def has_table_calc(self, question: str) -> bool:
        """检测是否包含表计算关键词。"""
        keywords = COMPLEXITY_KEYWORDS.get("table_calc", [])
        question_lower = question.lower()
        return any(kw in question_lower for kw in keywords)


__all__ = ["ComplexityDetector"]
