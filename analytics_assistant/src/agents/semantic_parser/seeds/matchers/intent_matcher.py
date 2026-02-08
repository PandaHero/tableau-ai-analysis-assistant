# -*- coding: utf-8 -*-
"""
意图匹配器

基于关键词匹配用户意图。

用法：
    from analytics_assistant.src.agents.semantic_parser.seeds.matchers import IntentMatcher
    
    matcher = IntentMatcher()
    intent = matcher.match("有哪些字段")
    # 'METADATA'
"""
from typing import List, Literal, Optional

from analytics_assistant.src.infra.seeds import INTENT_KEYWORDS


IntentType = Literal["METADATA", "DATA_QUERY", "AMBIGUOUS", "UNKNOWN"]


class IntentMatcher:
    """意图匹配器
    
    基于关键词匹配用户意图类型。
    """
    
    def match(self, question: str) -> IntentType:
        """匹配用户意图。
        
        优先级：METADATA > DATA_QUERY > AMBIGUOUS > UNKNOWN
        
        Args:
            question: 用户问题
        
        Returns:
            意图类型
        """
        question_lower = question.lower()
        
        # 1. 检查元数据问答（优先级最高）
        if self._match_keywords(question_lower, "metadata"):
            return "METADATA"
        
        # 2. 检查数据分析
        if self._match_keywords(question_lower, "data_analysis"):
            return "DATA_QUERY"
        
        # 3. 检查模糊关键词
        if self._match_keywords(question_lower, "ambiguous"):
            return "AMBIGUOUS"
        
        return "UNKNOWN"
    
    def _match_keywords(self, text: str, category: str) -> bool:
        """检查文本是否包含指定类别的关键词。"""
        keywords = INTENT_KEYWORDS.get(category, [])
        return any(kw.lower() in text for kw in keywords)
    
    def is_metadata_query(self, question: str) -> bool:
        """检测是否为元数据问答。"""
        return self._match_keywords(question.lower(), "metadata")
    
    def is_data_query(self, question: str) -> bool:
        """检测是否为数据分析查询。"""
        return self._match_keywords(question.lower(), "data_analysis")
    
    def get_matched_keywords(self, question: str, category: str) -> List[str]:
        """获取匹配的关键词列表。
        
        Args:
            question: 用户问题
            category: 关键词类别（metadata/data_analysis/ambiguous）
        
        Returns:
            匹配的关键词列表
        """
        question_lower = question.lower()
        keywords = INTENT_KEYWORDS.get(category, [])
        return [kw for kw in keywords if kw.lower() in question_lower]


__all__ = ["IntentMatcher", "IntentType"]
