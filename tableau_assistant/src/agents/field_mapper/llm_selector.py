"""
LLM Candidate Selector

Uses LLM to select the best field match from RAG candidates
when confidence is below threshold.

Features:
- Batch processing for efficiency
- Structured output with reasoning
- Context-aware selection
- Uses base agent utilities
"""

import logging
from typing import List, Optional, Tuple
from dataclasses import dataclass

from pydantic import BaseModel, Field

from tableau_assistant.src.agents.base import (
    get_llm,
    invoke_llm,
    parse_json_response,
)
from .prompt import FIELD_MAPPER_PROMPT, SingleSelectionResult

logger = logging.getLogger(__name__)


@dataclass
class FieldCandidate:
    """A candidate field from RAG retrieval"""
    field_name: str
    field_caption: str
    role: str  # dimension or measure
    data_type: str
    score: float
    category: Optional[str] = None
    level: Optional[int] = None
    granularity: Optional[str] = None
    sample_values: Optional[List[str]] = None


class BatchSelectionResult(BaseModel):
    """LLM output for batch field selection"""
    selections: List[SingleSelectionResult] = Field(
        description="Selection results for each business term"
    )


class LLMCandidateSelector:
    """
    LLM-based candidate selector for field mapping.
    
    Used when RAG retrieval confidence is below threshold (< 0.9).
    Selects the best match from top-k candidates using LLM reasoning.
    """
    
    def __init__(
        self,
        llm=None,
        confidence_threshold: float = 0.7
    ):
        """
        Initialize LLM candidate selector.
        
        Args:
            llm: LangChain ChatModel instance (lazy loaded if None)
            confidence_threshold: Minimum confidence for valid selection
        """
        self._llm = llm
        self.confidence_threshold = confidence_threshold
    
    @property
    def llm(self):
        """Lazy load LLM using base utilities"""
        if self._llm is None:
            self._llm = get_llm(agent_name="field_mapper")
        return self._llm
    
    def _format_candidates(self, candidates: List[FieldCandidate]) -> str:
        """Format candidates for prompt"""
        lines = []
        for i, c in enumerate(candidates, 1):
            line = f"{i}. {c.field_name}"
            if c.field_caption and c.field_caption != c.field_name:
                line += f" (caption: {c.field_caption})"
            line += f" | role: {c.role} | type: {c.data_type}"
            if c.category:
                line += f" | category: {c.category}"
            if c.sample_values:
                samples = ", ".join(str(v) for v in c.sample_values[:3])
                line += f" | samples: [{samples}]"
            line += f" | RAG score: {c.score:.2f}"
            lines.append(line)
        return "\n".join(lines)
    
    async def select(
        self,
        term: str,
        candidates: List[FieldCandidate],
        context: Optional[str] = None
    ) -> SingleSelectionResult:
        """
        Select best field match for a single term.
        
        Args:
            term: Business term to map
            candidates: List of candidate fields from RAG
            context: Optional question context
        
        Returns:
            SingleSelectionResult with selected field and reasoning
        """
        if not candidates:
            return SingleSelectionResult(
                business_term=term,
                selected_field=None,
                confidence=0.0,
                reasoning="No candidates provided"
            )
        
        # Format candidates for prompt
        candidates_text = self._format_candidates(candidates)
        
        # Build messages using prompt template
        messages = FIELD_MAPPER_PROMPT.format_messages(
            term=term,
            context=context or "No additional context provided.",
            candidates=candidates_text
        )
        
        try:
            # Use structured output if available
            if hasattr(self.llm, 'with_structured_output'):
                structured_llm = self.llm.with_structured_output(SingleSelectionResult)
                result = await structured_llm.ainvoke(messages)
                return result
            else:
                # Fallback to parsing JSON from response
                response = await invoke_llm(self.llm, messages)
                return parse_json_response(response, SingleSelectionResult)
        except Exception as e:
            logger.error(f"LLM selection failed for '{term}': {e}")
            # Fallback: return top candidate with reduced confidence
            if candidates:
                return SingleSelectionResult(
                    business_term=term,
                    selected_field=candidates[0].field_name,
                    confidence=candidates[0].score * 0.8,
                    reasoning=f"LLM fallback failed, using top RAG result: {e}"
                )
            return SingleSelectionResult(
                business_term=term,
                selected_field=None,
                confidence=0.0,
                reasoning=f"LLM selection failed: {e}"
            )
    
    async def select_batch(
        self,
        terms_with_candidates: List[Tuple[str, List[FieldCandidate]]],
        context: Optional[str] = None
    ) -> List[SingleSelectionResult]:
        """
        Select best field matches for multiple terms.
        
        For efficiency, processes each term individually with concurrency.
        
        Args:
            terms_with_candidates: List of (term, candidates) tuples
            context: Optional question context
        
        Returns:
            List of SingleSelectionResult for each term
        """
        if not terms_with_candidates:
            return []
        
        # Process each term individually
        results = []
        for term, candidates in terms_with_candidates:
            result = await self.select(term, candidates, context)
            results.append(result)
        
        return results


__all__ = [
    "LLMCandidateSelector",
    "FieldCandidate",
    "SingleSelectionResult",
    "BatchSelectionResult",
]
