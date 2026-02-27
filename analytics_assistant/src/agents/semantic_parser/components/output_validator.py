# -*- coding: utf-8 -*-
"""
OutputValidator - 输出验证器

在 SemanticUnderstanding 输出后立即执行：
- 验证字段引用有效性（是否在 FieldRAGResult 中）
- 验证计算表达式语法正确性
- 自动修正简单错误（如大小写）
- 生成澄清请求（如果无法自动修正）

减少对 ErrorCorrector 的依赖，提前发现问题。

配置来源：
- analytics_assistant/config/app.yaml -> semantic_parser.optimization.output_validator

Requirements: 8.1, 8.2, 8.3, 8.4, 8.5
"""

import logging
from difflib import SequenceMatcher
from typing import Any, Optional

from analytics_assistant.src.infra.config import get_config

from ..schemas.prefilter import (
    FieldRAGResult,
    OutputValidationError,
    ValidationErrorType,
    ValidationResult,
)

logger = logging.getLogger(__name__)

# ═══════════════════════════════════════════════════════════════════════════
# 配置加载
# ═══════════════════════════════════════════════════════════════════════════

def get_fuzzy_match_threshold() -> float:
    """获取模糊匹配阈值。"""
    try:
        config = get_config()
        output_validator_config = config.get_semantic_parser_optimization_config().get(
            "output_validator", {}
        )
        return output_validator_config.get("fuzzy_match_threshold", 0.8)
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return 0.8

def get_auto_correct_case() -> bool:
    """获取是否自动修正大小写。"""
    try:
        config = get_config()
        output_validator_config = config.get_semantic_parser_optimization_config().get(
            "output_validator", {}
        )
        return output_validator_config.get("auto_correct_case", True)
    except Exception as e:
        logger.warning(f"无法加载配置，使用默认值: {e}")
        return True

# ═══════════════════════════════════════════════════════════════════════════
# OutputValidator 组件
# ═══════════════════════════════════════════════════════════════════════════

class OutputValidator:
    """输出验证器
    
    在 SemanticUnderstanding 输出后立即执行：
    - 验证字段引用有效性
    - 验证计算表达式语法
    - 自动修正简单错误
    
    减少对 ErrorCorrector 的依赖。
    
    Examples:
        >>> validator = OutputValidator()
        >>> result = validator.validate(
        ...     semantic_output=semantic_output,
        ...     field_rag_result=field_rag_result,
        ... )
        >>> if result.is_valid:
        ...     print("验证通过")
        >>> elif result.needs_clarification:
        ...     print(result.clarification_message)
    """
    
    # 默认配置
    DEFAULT_FUZZY_THRESHOLD = 0.8
    DEFAULT_AUTO_CORRECT_CASE = True
    
    def __init__(
        self,
        fuzzy_match_threshold: Optional[float] = None,
        auto_correct_case: Optional[bool] = None,
    ):
        """初始化 OutputValidator。
        
        Args:
            fuzzy_match_threshold: 模糊匹配阈值（None 从配置读取）
            auto_correct_case: 是否自动修正大小写（None 从配置读取）
        """
        self.fuzzy_match_threshold = (
            fuzzy_match_threshold if fuzzy_match_threshold is not None
            else get_fuzzy_match_threshold()
        )
        self.auto_correct_case = (
            auto_correct_case if auto_correct_case is not None
            else get_auto_correct_case()
        )
    
    def validate(
        self,
        semantic_output: Any,
        field_rag_result: FieldRAGResult,
    ) -> ValidationResult:
        """验证 LLM 输出
        
        Args:
            semantic_output: SemanticUnderstanding 输出
            field_rag_result: 字段检索结果
            
        Returns:
            ValidationResult 包含验证结果和可能的修正
        """
        errors: list[OutputValidationError] = []
        corrected_output: Optional[dict[str, Any]] = None
        
        # 获取输出字典
        if hasattr(semantic_output, 'model_dump'):
            output_dict = semantic_output.model_dump()
        elif isinstance(semantic_output, dict):
            output_dict = semantic_output.copy()
        else:
            output_dict = {}
        
        has_corrections = False
        
        # 1. 验证度量字段
        what = output_dict.get("what", {})
        measures = what.get("measures", []) if what else []
        if measures:
            measure_errors, corrected_measures = self._validate_measures(
                measures, field_rag_result
            )
            errors.extend(measure_errors)
            if corrected_measures and corrected_measures != measures:
                if corrected_output is None:
                    corrected_output = output_dict.copy()
                if "what" not in corrected_output:
                    corrected_output["what"] = {}
                corrected_output["what"]["measures"] = corrected_measures
                has_corrections = True
        
        # 2. 验证维度字段
        where = output_dict.get("where", {})
        dimensions = where.get("dimensions", []) if where else []
        if dimensions:
            dimension_errors, corrected_dimensions = self._validate_dimensions(
                dimensions, field_rag_result
            )
            errors.extend(dimension_errors)
            if corrected_dimensions and corrected_dimensions != dimensions:
                if corrected_output is None:
                    corrected_output = output_dict.copy()
                if "where" not in corrected_output:
                    corrected_output["where"] = {}
                corrected_output["where"]["dimensions"] = corrected_dimensions
                has_corrections = True
        
        # 3. 验证计算表达式
        computations = output_dict.get("computations", [])
        if computations:
            comp_errors = self._validate_computations(computations, field_rag_result)
            errors.extend(comp_errors)
        
        # 判断是否需要澄清
        uncorrectable_errors = [e for e in errors if not e.auto_correctable]
        
        if uncorrectable_errors:
            return ValidationResult(
                is_valid=False,
                errors=errors,
                needs_clarification=True,
                clarification_message=self._build_clarification_message(uncorrectable_errors),
            )
        
        # 所有错误都可自动修正
        if errors and has_corrections:
            logger.info(f"OutputValidator: 自动修正 {len(errors)} 个错误")
            return ValidationResult(
                is_valid=True,
                errors=errors,
                corrected_output=corrected_output,
            )
        
        return ValidationResult(is_valid=True)

    
    def _validate_measures(
        self,
        measures: list[Any],
        field_rag_result: FieldRAGResult,
    ) -> tuple[list[OutputValidationError], list[str]]:
        """验证度量字段。"""
        errors = []
        corrected = []
        
        # 构建有效字段名映射（小写 -> 原始名）
        valid_names = self._build_valid_names_map(field_rag_result.measures)
        
        for measure in measures:
            # 提取字段名
            field_name = self._extract_field_name(measure)
            if not field_name:
                continue
            
            result = self._validate_field(field_name, valid_names, "度量")
            if result.error:
                errors.append(result.error)
            corrected.append(result.corrected_name or field_name)
        
        return errors, corrected
    
    def _validate_dimensions(
        self,
        dimensions: list[Any],
        field_rag_result: FieldRAGResult,
    ) -> tuple[list[OutputValidationError], list[str]]:
        """验证维度字段。"""
        errors = []
        corrected = []
        
        # 构建有效字段名映射（包含维度和时间字段）
        valid_names = self._build_valid_names_map(field_rag_result.dimensions)
        time_names = self._build_valid_names_map(field_rag_result.time_fields)
        valid_names.update(time_names)
        
        for dimension in dimensions:
            # 提取字段名
            field_name = self._extract_field_name(dimension)
            if not field_name:
                continue
            
            result = self._validate_field(field_name, valid_names, "维度")
            if result.error:
                errors.append(result.error)
            corrected.append(result.corrected_name or field_name)
        
        return errors, corrected
    
    def _validate_computations(
        self,
        computations: list[Any],
        field_rag_result: FieldRAGResult,
    ) -> list[OutputValidationError]:
        """验证计算表达式。"""
        errors = []
        valid_measures = {
            self._extract_field_name(c) 
            for c in field_rag_result.measures 
            if self._extract_field_name(c)
        }
        
        for comp in computations:
            if isinstance(comp, dict):
                # 检查 base_measures 是否有效
                base_measures = comp.get("base_measures", [])
                for measure in base_measures:
                    measure_name = self._extract_field_name(measure)
                    if measure_name and measure_name not in valid_measures:
                        errors.append(OutputValidationError(
                            error_type=ValidationErrorType.INVALID_FIELD,
                            field_name=measure_name,
                            message=f"计算表达式中的字段 '{measure_name}' 不在候选列表中",
                            auto_correctable=False,
                        ))
                
                # 检查公式语法（简单检查括号匹配）
                formula = comp.get("formula", "")
                if formula and not self._check_brackets(formula):
                    errors.append(OutputValidationError(
                        error_type=ValidationErrorType.SYNTAX_ERROR,
                        message=f"公式 '{formula}' 括号不匹配",
                        auto_correctable=False,
                    ))
        
        return errors
    
    def _build_valid_names_map(self, candidates: list[Any]) -> dict[str, str]:
        """构建有效字段名映射（小写 -> 原始名）。
        
        同时考虑：
        - field_name（技术名称）
        - field_caption（显示名称）
        - aliases（别名列表）
        
        因为 LLM 可能输出业务术语、别名而非技术名称。
        """
        valid_names = {}
        for candidate in candidates:
            # 提取技术名称
            field_name = self._extract_field_name(candidate)
            if field_name:
                valid_names[field_name.lower()] = field_name
            
            # 提取显示名称（field_caption）
            field_caption = self._extract_field_caption(candidate)
            if field_caption and field_caption.lower() not in valid_names:
                # 显示名称映射到技术名称
                valid_names[field_caption.lower()] = field_name or field_caption
            
            # 提取别名（aliases）
            aliases = self._extract_aliases(candidate)
            if aliases:
                for alias in aliases:
                    if alias and alias.lower() not in valid_names:
                        # 别名映射到技术名称
                        valid_names[alias.lower()] = field_name or field_caption or alias
        
        return valid_names
    
    def _extract_aliases(self, obj: Any) -> Optional[list[str]]:
        """从对象中提取字段别名列表。"""
        if isinstance(obj, dict):
            return obj.get("aliases") or []
        if hasattr(obj, "aliases"):
            return obj.aliases or []
        return []
    
    def _extract_field_caption(self, obj: Any) -> Optional[str]:
        """从对象中提取字段显示名称。"""
        if isinstance(obj, dict):
            return obj.get("field_caption") or obj.get("caption")
        if hasattr(obj, "field_caption"):
            return obj.field_caption
        return None
    
    def _extract_field_name(self, obj: Any) -> Optional[str]:
        """从对象中提取字段名。"""
        if isinstance(obj, str):
            return obj
        if isinstance(obj, dict):
            return obj.get("field_name") or obj.get("name")
        if hasattr(obj, "field_name"):
            return obj.field_name
        return None

    
    def _validate_field(
        self,
        field_name: str,
        valid_names: dict[str, str],
        field_type: str,
    ) -> "_FieldValidationResult":
        """验证单个字段。"""
        # 精确匹配（忽略大小写）
        if field_name.lower() in valid_names:
            corrected = valid_names[field_name.lower()]
            if corrected != field_name and self.auto_correct_case:
                # 大小写修正
                return _FieldValidationResult(
                    corrected_name=corrected,
                    error=OutputValidationError(
                        error_type=ValidationErrorType.INVALID_FIELD,
                        field_name=field_name,
                        message=f"{field_type}字段 '{field_name}' 大小写已修正为 '{corrected}'",
                        auto_correctable=True,
                        suggested_correction=corrected,
                    ),
                )
            return _FieldValidationResult(corrected_name=corrected)
        
        # 模糊匹配
        best_match = self._fuzzy_match(field_name, list(valid_names.values()))
        if best_match:
            return _FieldValidationResult(
                corrected_name=best_match,
                error=OutputValidationError(
                    error_type=ValidationErrorType.INVALID_FIELD,
                    field_name=field_name,
                    message=f"{field_type}字段 '{field_name}' 不在候选列表中，已修正为 '{best_match}'",
                    auto_correctable=True,
                    suggested_correction=best_match,
                ),
            )
        
        # 无法修正
        return _FieldValidationResult(
            corrected_name=None,
            error=OutputValidationError(
                error_type=ValidationErrorType.INVALID_FIELD,
                field_name=field_name,
                message=f"{field_type}字段 '{field_name}' 不在候选列表中，无法自动修正",
                auto_correctable=False,
            ),
        )
    
    def _fuzzy_match(
        self,
        target: str,
        candidates: list[str],
    ) -> Optional[str]:
        """模糊匹配。"""
        best_match = None
        best_ratio = 0.0
        
        for candidate in candidates:
            ratio = SequenceMatcher(None, target.lower(), candidate.lower()).ratio()
            if ratio > self.fuzzy_match_threshold and ratio > best_ratio:
                best_match = candidate
                best_ratio = ratio
        
        return best_match
    
    def _check_brackets(self, formula: str) -> bool:
        """检查括号是否匹配。"""
        stack = []
        brackets = {'(': ')', '[': ']', '{': '}'}
        
        for char in formula:
            if char in brackets:
                stack.append(char)
            elif char in brackets.values():
                if not stack:
                    return False
                if brackets[stack.pop()] != char:
                    return False
        
        return len(stack) == 0
    
    def _build_clarification_message(
        self,
        errors: list[OutputValidationError],
    ) -> str:
        """构建澄清消息。"""
        messages = []
        for error in errors:
            if error.error_type == ValidationErrorType.INVALID_FIELD:
                messages.append(f"无法识别字段 '{error.field_name}'")
            else:
                messages.append(error.message)
        
        return "请确认以下问题：\n" + "\n".join(f"- {m}" for m in messages)

# ═══════════════════════════════════════════════════════════════════════════
# 内部数据类
# ═══════════════════════════════════════════════════════════════════════════

class _FieldValidationResult:
    """字段验证结果（内部使用）。"""
    
    def __init__(
        self,
        corrected_name: Optional[str] = None,
        error: Optional[OutputValidationError] = None,
    ):
        self.corrected_name = corrected_name
        self.error = error

__all__ = [
    "OutputValidator",
    "get_fuzzy_match_threshold",
    "get_auto_correct_case",
]
