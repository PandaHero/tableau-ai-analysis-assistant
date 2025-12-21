# -*- coding: utf-8 -*-
"""
Query Corrector - 查询纠错器

分析 VizQL 执行错误，生成修复建议。
"""

import logging
import re
from typing import Any, Dict, List, Optional, Tuple
from enum import Enum

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


class ErrorCategory(str, Enum):
    """错误类别"""
    FIELD_NOT_FOUND = "field_not_found"  # 字段不存在
    TYPE_MISMATCH = "type_mismatch"  # 类型不匹配
    INVALID_AGGREGATION = "invalid_aggregation"  # 无效聚合
    INVALID_FILTER = "invalid_filter"  # 无效过滤器
    SYNTAX_ERROR = "syntax_error"  # 语法错误
    PERMISSION_DENIED = "permission_denied"  # 权限不足
    TIMEOUT = "timeout"  # 超时
    UNKNOWN = "unknown"  # 未知错误


class CorrectionSuggestion(BaseModel):
    """修复建议"""
    category: ErrorCategory = Field(description="错误类别")
    original_value: str = Field(default="", description="原始值")
    suggested_value: str = Field(default="", description="建议值")
    confidence: float = Field(default=0.5, description="置信度 0-1")
    reason: str = Field(default="", description="修复原因")


class CorrectionResult(BaseModel):
    """纠错结果"""
    can_correct: bool = Field(default=False, description="是否可以纠错")
    error_category: ErrorCategory = Field(default=ErrorCategory.UNKNOWN)
    suggestions: List[CorrectionSuggestion] = Field(default_factory=list)
    corrected_query: Optional[Dict[str, Any]] = Field(default=None)
    reason: str = Field(default="", description="纠错说明")


class QueryCorrector:
    """
    查询纠错器
    
    分析 VizQL 执行错误，尝试自动修复查询。
    """
    
    # 常见错误模式
    FIELD_NOT_FOUND_PATTERNS = [
        r"field[s]?\s+['\"]?(\w+)['\"]?\s+(?:not found|does not exist|unknown)",
        r"unknown\s+(?:field|column)[s]?\s*[:\s]+['\"]?(\w+)['\"]?",
        r"['\"](\w+)['\"]?\s+is not a valid (?:field|column)",
        r"cannot find (?:field|column)\s+['\"]?(\w+)['\"]?",
    ]
    
    TYPE_MISMATCH_PATTERNS = [
        r"type mismatch.*['\"]?(\w+)['\"]?",
        r"cannot (?:compare|convert).*['\"]?(\w+)['\"]?",
        r"invalid type for (?:field|column)\s+['\"]?(\w+)['\"]?",
    ]
    
    INVALID_AGGREGATION_PATTERNS = [
        r"cannot aggregate\s+['\"]?(\w+)['\"]?",
        r"invalid aggregation.*['\"]?(\w+)['\"]?",
        r"['\"]?(\w+)['\"]?\s+cannot be used with\s+(\w+)",
    ]
    
    def __init__(self, data_model: Optional[Any] = None):
        """
        初始化纠错器
        
        Args:
            data_model: 数据模型，用于字段验证和建议
        """
        self._data_model = data_model
        self._field_names: set[str] = set()
        self._field_captions: Dict[str, str] = {}  # caption -> name
        
        if data_model:
            self._build_field_index(data_model)
    
    def _build_field_index(self, data_model: Any) -> None:
        """构建字段索引"""
        fields = []
        if hasattr(data_model, 'fields'):
            fields = data_model.fields
        elif isinstance(data_model, dict):
            fields = data_model.get('fields', [])
        
        for field in fields:
            if hasattr(field, 'name'):
                name = field.name
                caption = getattr(field, 'fieldCaption', name)
            else:
                name = field.get('name', '')
                caption = field.get('fieldCaption', name)
            
            if name:
                self._field_names.add(name)
                self._field_names.add(name.lower())
            if caption:
                self._field_captions[caption.lower()] = name
                self._field_captions[caption] = name
    
    def analyze_error(self, error_message: str) -> Tuple[ErrorCategory, List[str]]:
        """
        分析错误消息，识别错误类别和相关字段
        
        Args:
            error_message: 错误消息
            
        Returns:
            (错误类别, 相关字段列表)
        """
        error_lower = error_message.lower()
        
        # 检查字段不存在错误
        for pattern in self.FIELD_NOT_FOUND_PATTERNS:
            match = re.search(pattern, error_lower, re.IGNORECASE)
            if match:
                fields = [g for g in match.groups() if g]
                return ErrorCategory.FIELD_NOT_FOUND, fields
        
        # 检查类型不匹配错误
        for pattern in self.TYPE_MISMATCH_PATTERNS:
            match = re.search(pattern, error_lower, re.IGNORECASE)
            if match:
                fields = [g for g in match.groups() if g]
                return ErrorCategory.TYPE_MISMATCH, fields
        
        # 检查无效聚合错误
        for pattern in self.INVALID_AGGREGATION_PATTERNS:
            match = re.search(pattern, error_lower, re.IGNORECASE)
            if match:
                fields = [g for g in match.groups() if g]
                return ErrorCategory.INVALID_AGGREGATION, fields
        
        # 检查权限错误
        if any(kw in error_lower for kw in ['permission', 'denied', 'unauthorized', 'forbidden']):
            return ErrorCategory.PERMISSION_DENIED, []
        
        # 检查超时错误
        if any(kw in error_lower for kw in ['timeout', 'timed out']):
            return ErrorCategory.TIMEOUT, []
        
        # 检查过滤器错误
        if any(kw in error_lower for kw in ['filter', 'where', 'condition']):
            return ErrorCategory.INVALID_FILTER, []
        
        return ErrorCategory.UNKNOWN, []
    
    def find_similar_field(self, field_name: str) -> Optional[str]:
        """
        查找相似字段名
        
        Args:
            field_name: 原始字段名
            
        Returns:
            最相似的字段名，如果没有找到返回 None
        """
        if not self._field_names:
            return None
        
        field_lower = field_name.lower()
        
        # 精确匹配（大小写不敏感）
        if field_lower in self._field_names:
            for name in self._field_names:
                if name.lower() == field_lower:
                    return name
        
        # 检查 caption 映射
        if field_lower in self._field_captions:
            return self._field_captions[field_lower]
        
        # 编辑距离匹配
        best_match = None
        best_distance = float('inf')
        
        for name in self._field_names:
            distance = self._levenshtein_distance(field_lower, name.lower())
            # 只接受编辑距离 <= 3 的匹配
            if distance < best_distance and distance <= 3:
                best_distance = distance
                best_match = name
        
        return best_match
    
    def _levenshtein_distance(self, s1: str, s2: str) -> int:
        """计算编辑距离"""
        if len(s1) < len(s2):
            return self._levenshtein_distance(s2, s1)
        
        if len(s2) == 0:
            return len(s1)
        
        previous_row = range(len(s2) + 1)
        for i, c1 in enumerate(s1):
            current_row = [i + 1]
            for j, c2 in enumerate(s2):
                insertions = previous_row[j + 1] + 1
                deletions = current_row[j] + 1
                substitutions = previous_row[j] + (c1 != c2)
                current_row.append(min(insertions, deletions, substitutions))
            previous_row = current_row
        
        return previous_row[-1]
    
    def correct(
        self,
        query: Dict[str, Any],
        error_message: str,
    ) -> CorrectionResult:
        """
        尝试纠正查询
        
        Args:
            query: 原始查询
            error_message: 错误消息
            
        Returns:
            CorrectionResult
        """
        category, related_fields = self.analyze_error(error_message)
        
        # 不可纠正的错误类别
        if category in [ErrorCategory.PERMISSION_DENIED, ErrorCategory.TIMEOUT, ErrorCategory.UNKNOWN]:
            return CorrectionResult(
                can_correct=False,
                error_category=category,
                reason=f"错误类别 {category.value} 无法自动纠正",
            )
        
        suggestions: List[CorrectionSuggestion] = []
        corrected_query = query.copy()
        
        # 处理字段不存在错误
        if category == ErrorCategory.FIELD_NOT_FOUND:
            for field in related_fields:
                similar = self.find_similar_field(field)
                if similar:
                    suggestions.append(CorrectionSuggestion(
                        category=category,
                        original_value=field,
                        suggested_value=similar,
                        confidence=0.8,
                        reason=f"字段 '{field}' 不存在，建议使用 '{similar}'",
                    ))
                    # 在查询中替换字段名
                    corrected_query = self._replace_field_in_query(
                        corrected_query, field, similar
                    )
        
        # 处理类型不匹配错误
        elif category == ErrorCategory.TYPE_MISMATCH:
            # 类型不匹配通常需要 LLM 介入
            return CorrectionResult(
                can_correct=False,
                error_category=category,
                reason="类型不匹配错误需要重新理解查询意图",
            )
        
        # 处理无效聚合错误
        elif category == ErrorCategory.INVALID_AGGREGATION:
            # 尝试移除聚合
            suggestions.append(CorrectionSuggestion(
                category=category,
                original_value="aggregation",
                suggested_value="none",
                confidence=0.6,
                reason="尝试移除无效的聚合操作",
            ))
            corrected_query = self._remove_aggregation(corrected_query, related_fields)
        
        if suggestions:
            return CorrectionResult(
                can_correct=True,
                error_category=category,
                suggestions=suggestions,
                corrected_query=corrected_query,
                reason=f"找到 {len(suggestions)} 个修复建议",
            )
        
        return CorrectionResult(
            can_correct=False,
            error_category=category,
            reason="无法生成有效的修复建议",
        )
    
    def _replace_field_in_query(
        self,
        query: Dict[str, Any],
        old_field: str,
        new_field: str,
    ) -> Dict[str, Any]:
        """在查询中替换字段名"""
        import json
        query_str = json.dumps(query)
        # 替换字段名（保留引号）
        query_str = query_str.replace(f'"{old_field}"', f'"{new_field}"')
        query_str = query_str.replace(f"'{old_field}'", f"'{new_field}'")
        return json.loads(query_str)
    
    def _remove_aggregation(
        self,
        query: Dict[str, Any],
        fields: List[str],
    ) -> Dict[str, Any]:
        """移除指定字段的聚合"""
        result = query.copy()
        
        # 处理 columns 中的聚合
        if 'columns' in result:
            for col in result['columns']:
                if isinstance(col, dict):
                    field_name = col.get('fieldName', '')
                    if field_name in fields or not fields:
                        col.pop('aggregation', None)
        
        return result
