"""
Hierarchy Inferrer - RAG-enhanced dimension hierarchy inference

Uses RAG to retrieve similar historical patterns as few-shot examples
for LLM-based dimension hierarchy inference.

Features:
- Retrieve similar patterns (similarity > 0.8)
- Provide top-3 patterns as few-shot examples
- Store successful inferences for future retrieval
- Fallback to pure LLM when no similar patterns exist

Requirements:
- R4.1.1: Retrieve patterns with similarity > 0.8
- R4.1.2: Provide top-3 patterns as few-shot examples
- R4.1.3: Store successful inferences
- R4.1.4: Index includes field name, data type, sample values, unique count, category/level
- R4.1.5: Fallback to pure LLM when similarity < 0.8
"""

import logging
from typing import Dict, Any, Optional, List
from dataclasses import dataclass

from tableau_assistant.src.capabilities.rag.dimension_pattern import (
    DimensionHierarchyRAG,
    DimensionPatternStore,
    DimensionPattern,
)

logger = logging.getLogger(__name__)


@dataclass
class HierarchyInferenceResult:
    """Result of dimension hierarchy inference"""
    field_name: str
    field_caption: str
    category: str
    category_detail: str
    level: int
    granularity: str
    reasoning: str
    confidence: float
    used_rag: bool
    similar_patterns_count: int


class HierarchyInferrer:
    """
    RAG-enhanced dimension hierarchy inferrer.
    
    Uses historical inference patterns to improve accuracy and reduce LLM costs.
    
    Strategy:
    1. Search for similar patterns (similarity > 0.8)
    2. If found, use top-3 as few-shot examples for LLM
    3. If not found, fallback to pure LLM inference
    4. Store successful inferences for future use
    
    Attributes:
        rag: DimensionHierarchyRAG instance
        llm: LLM instance for inference
        similarity_threshold: Minimum similarity for pattern matching
    """
    
    def __init__(
        self,
        rag: Optional[DimensionHierarchyRAG] = None,
        llm: Optional[Any] = None,
        similarity_threshold: float = 0.8,
        pattern_store: Optional[DimensionPatternStore] = None
    ):
        """
        Initialize HierarchyInferrer.
        
        Args:
            rag: DimensionHierarchyRAG instance (created if None)
            llm: LLM instance for inference (lazy loaded if None)
            similarity_threshold: Minimum similarity for pattern matching
            pattern_store: DimensionPatternStore instance (used if rag is None)
        """
        if rag is not None:
            self.rag = rag
        elif pattern_store is not None:
            self.rag = DimensionHierarchyRAG(
                pattern_store=pattern_store,
                similarity_threshold=similarity_threshold
            )
        else:
            self.rag = DimensionHierarchyRAG(
                similarity_threshold=similarity_threshold
            )
        
        self._llm = llm
        self.similarity_threshold = similarity_threshold
        
        # Statistics
        self._total_inferences = 0
        self._rag_assisted = 0
        self._pure_llm = 0
    
    @property
    def llm(self):
        """Lazy load LLM if not provided"""
        if self._llm is None:
            from tableau_assistant.src.model_manager.llm import select_model
            self._llm = select_model(temperature=0)
        return self._llm
    
    async def infer(
        self,
        field_name: str,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        datasource_luid: Optional[str] = None,
        store_result: bool = True
    ) -> HierarchyInferenceResult:
        """
        Infer dimension hierarchy for a field.
        
        Args:
            field_name: Technical field name
            field_caption: Display name
            data_type: Data type (string, integer, etc.)
            sample_values: Sample values from the field
            unique_count: Number of unique values
            datasource_luid: Datasource identifier
            store_result: Whether to store successful inference
        
        Returns:
            HierarchyInferenceResult with inferred hierarchy
        """
        self._total_inferences += 1
        
        # 1. Get RAG context (similar patterns)
        context = self.rag.get_inference_context(
            field_caption=field_caption,
            data_type=data_type,
            sample_values=sample_values,
            unique_count=unique_count
        )
        
        # 2. Build prompt with or without few-shot examples
        if context["has_similar_patterns"]:
            self._rag_assisted += 1
            prompt = self._build_rag_prompt(
                field_caption=field_caption,
                data_type=data_type,
                sample_values=sample_values,
                unique_count=unique_count,
                few_shot_examples=context["few_shot_examples"]
            )
            used_rag = True
            similar_count = len(context["similar_patterns"])
        else:
            self._pure_llm += 1
            prompt = self._build_pure_llm_prompt(
                field_caption=field_caption,
                data_type=data_type,
                sample_values=sample_values,
                unique_count=unique_count
            )
            used_rag = False
            similar_count = 0
        
        # 3. Call LLM for inference
        try:
            result = await self._call_llm(prompt)
        except Exception as e:
            logger.error(f"LLM inference failed for '{field_caption}': {e}")
            # Return default result
            return HierarchyInferenceResult(
                field_name=field_name,
                field_caption=field_caption,
                category="unknown",
                category_detail="Unknown category",
                level=1,
                granularity="unknown",
                reasoning=f"LLM inference failed: {e}",
                confidence=0.0,
                used_rag=used_rag,
                similar_patterns_count=similar_count
            )
        
        # 4. Store successful inference
        if store_result and result.get("confidence", 0) >= 0.7:
            try:
                self.rag.store_inference_result(
                    field_name=field_name,
                    field_caption=field_caption,
                    data_type=data_type,
                    sample_values=sample_values,
                    unique_count=unique_count,
                    category=result["category"],
                    category_detail=result.get("category_detail", ""),
                    level=result["level"],
                    granularity=result.get("granularity", ""),
                    reasoning=result.get("reasoning", ""),
                    confidence=result.get("confidence", 0.8),
                    datasource_luid=datasource_luid
                )
                logger.debug(f"Stored inference result for '{field_caption}'")
            except Exception as e:
                logger.warning(f"Failed to store inference result: {e}")
        
        return HierarchyInferenceResult(
            field_name=field_name,
            field_caption=field_caption,
            category=result["category"],
            category_detail=result.get("category_detail", ""),
            level=result["level"],
            granularity=result.get("granularity", ""),
            reasoning=result.get("reasoning", ""),
            confidence=result.get("confidence", 0.8),
            used_rag=used_rag,
            similar_patterns_count=similar_count
        )
    
    def _build_rag_prompt(
        self,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int,
        few_shot_examples: List[str]
    ) -> str:
        """Build prompt with few-shot examples from RAG"""
        examples_text = "\n\n---\n\n".join(few_shot_examples)
        samples_text = ", ".join(str(v) for v in sample_values[:5])
        
        return f"""You are a data analyst expert. Infer the dimension hierarchy for the given field.

## Similar Examples (for reference)

{examples_text}

---

## Field to Analyze

字段: {field_caption}
数据类型: {data_type}
样本值: {samples_text}
唯一值数量: {unique_count}

## Instructions

Based on the similar examples above, infer the dimension hierarchy for this field.

## Output Format

Respond with a JSON object:
{{
    "category": "<dimension category: geographic, temporal, product, customer, organization, etc.>",
    "category_detail": "<detailed category description>",
    "level": <hierarchy level 1-5, where 1 is highest like country, 5 is lowest like city>,
    "granularity": "<granularity description: country, province, city, year, month, day, etc.>",
    "reasoning": "<brief explanation of your inference>",
    "confidence": <0.0-1.0>
}}
"""
    
    def _build_pure_llm_prompt(
        self,
        field_caption: str,
        data_type: str,
        sample_values: List[str],
        unique_count: int
    ) -> str:
        """Build prompt for pure LLM inference (no RAG examples)"""
        samples_text = ", ".join(str(v) for v in sample_values[:5])
        
        return f"""You are a data analyst expert. Infer the dimension hierarchy for the given field.

## Field to Analyze

字段: {field_caption}
数据类型: {data_type}
样本值: {samples_text}
唯一值数量: {unique_count}

## Dimension Categories

Common dimension categories:
- geographic: Location-based (country, province, city, region)
- temporal: Time-based (year, quarter, month, week, day)
- product: Product-related (category, subcategory, product name)
- customer: Customer-related (segment, type, name)
- organization: Organization structure (department, team, employee)
- other: Other dimensions

## Hierarchy Levels

Level 1: Highest level (e.g., country, year, product category)
Level 2: Second level (e.g., province, quarter, subcategory)
Level 3: Third level (e.g., city, month, product line)
Level 4: Fourth level (e.g., district, week, product)
Level 5: Lowest level (e.g., address, day, SKU)

## Output Format

Respond with a JSON object:
{{
    "category": "<dimension category>",
    "category_detail": "<detailed category description>",
    "level": <hierarchy level 1-5>,
    "granularity": "<granularity description>",
    "reasoning": "<brief explanation of your inference>",
    "confidence": <0.0-1.0>
}}
"""
    
    async def _call_llm(self, prompt: str) -> Dict[str, Any]:
        """Call LLM and parse response"""
        import json
        
        response = await self.llm.ainvoke(prompt)
        content = response.content.strip()
        
        # Try to extract JSON from response
        if content.startswith("```"):
            lines = content.split("\n")
            content = "\n".join(lines[1:-1])
        
        try:
            return json.loads(content)
        except json.JSONDecodeError as e:
            logger.warning(f"Failed to parse LLM response as JSON: {e}")
            # Try to extract key fields from text
            return self._parse_text_response(content)
    
    def _parse_text_response(self, content: str) -> Dict[str, Any]:
        """Parse text response when JSON parsing fails"""
        # Default values
        result = {
            "category": "unknown",
            "category_detail": "",
            "level": 1,
            "granularity": "",
            "reasoning": content[:200],
            "confidence": 0.5
        }
        
        # Try to extract category
        for cat in ["geographic", "temporal", "product", "customer", "organization"]:
            if cat in content.lower():
                result["category"] = cat
                break
        
        # Try to extract level
        import re
        level_match = re.search(r'level[:\s]*(\d)', content.lower())
        if level_match:
            result["level"] = int(level_match.group(1))
        
        return result
    
    def get_stats(self) -> Dict[str, Any]:
        """Get inference statistics"""
        return {
            "total_inferences": self._total_inferences,
            "rag_assisted": self._rag_assisted,
            "pure_llm": self._pure_llm,
            "rag_rate": self._rag_assisted / max(1, self._total_inferences),
            "rag_stats": self.rag.get_stats(),
        }


__all__ = [
    "HierarchyInferrer",
    "HierarchyInferenceResult",
]
