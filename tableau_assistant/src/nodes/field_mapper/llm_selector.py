"""
LLM Candidate Selector

Uses LLM to select the best field match from RAG candidates
when confidence is below threshold.

Features:
- Batch processing for efficiency
- Structured output with reasoning
- Context-aware selection
"""

import logging
from typing import List, Dict, Any, Optional, Tuple
from dataclasses import dataclass

from pydantic import BaseModel, Field

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


class SingleSelectionResult(BaseModel):
    """LLM output for single field selection"""
    business_term: str = Field(description="The business term being mapped")
    selected_field: Optional[str] = Field(
        default=None,
        description="Selected field name, or null if no suitable match"
    )
    confidence: float = Field(
        ge=0.0, le=1.0,
        description="Confidence in the selection (0-1)"
    )
    reasoning: str = Field(description="Explanation for the selection")


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
        llm: Optional[Any] = None,
        confidence_threshold: float = 0.7
    ):
        """
        Initialize LLM candidate selector.
        
        Args:
            llm: LangChain ChatModel instance
            confidence_threshold: Minimum confidence for valid selection
        """
        self._llm = llm
        self.confidence_threshold = confidence_threshold
    
    @property
    def llm(self):
        """Lazy load LLM if not provided"""
        if self._llm is None:
            from tableau_assistant.src.model_manager.llm import select_model
            self._llm = select_model(temperature=0)
        return self._llm
    
    def _build_selection_prompt(
        self,
        term: str,
        candidates: List[FieldCandidate],
        context: Optional[str] = None
    ) -> str:
        """Build prompt for single field selection"""
        candidates_text = self._format_candidates(candidates)
        
        prompt = f"""You are a data analyst expert. Select the best matching field for the business term.

## Business Term
"{term}"

## Context
{context or "No additional context provided."}

## Candidate Fields
{candidates_text}

## Instructions
1. Analyze the semantic meaning of the business term
2. Compare with each candidate field's name, caption, and sample values
3. Consider the field role (dimension vs measure) and data type
4. Select the BEST matching field, or indicate no suitable match

## Output Format
Respond with a JSON object:
{{
    "business_term": "{term}",
    "selected_field": "<field_name or null>",
    "confidence": <0.0-1.0>,
    "reasoning": "<brief explanation>"
}}

Important:
- Only select from the provided candidates
- Set selected_field to null if no candidate is a good match
- Confidence should reflect semantic similarity, not just keyword match
"""
        return prompt
    
    def _build_batch_selection_prompt(
        self,
        terms_with_candidates: List[Tuple[str, List[FieldCandidate]]],
        context: Optional[str] = None
    ) -> str:
        """Build prompt for batch field selection"""
        terms_section = []
        for i, (term, candidates) in enumerate(terms_with_candidates, 1):
            candidates_text = self._format_candidates(candidates)
            terms_section.append(f"""
### Term {i}: "{term}"
Candidates:
{candidates_text}
""")
        
        prompt = f"""You are a data analyst expert. Select the best matching field for each business term.

## Context
{context or "No additional context provided."}

## Terms to Map
{"".join(terms_section)}

## Instructions
For each term:
1. Analyze the semantic meaning of the business term
2. Compare with each candidate field's name, caption, and sample values
3. Consider the field role (dimension vs measure) and data type
4. Select the BEST matching field, or indicate no suitable match

## Output Format
Respond with a JSON object:
{{
    "selections": [
        {{
            "business_term": "<term>",
            "selected_field": "<field_name or null>",
            "confidence": <0.0-1.0>,
            "reasoning": "<brief explanation>"
        }},
        ...
    ]
}}

Important:
- Only select from the provided candidates for each term
- Set selected_field to null if no candidate is a good match
- Confidence should reflect semantic similarity
"""
        return prompt
    
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
                samples = ", ".join(c.sample_values[:3])
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
        
        prompt = self._build_selection_prompt(term, candidates, context)
        
        try:
            # Use structured output if available
            if hasattr(self.llm, 'with_structured_output'):
                structured_llm = self.llm.with_structured_output(SingleSelectionResult)
                result = await structured_llm.ainvoke(prompt)
                return result
            else:
                # Fallback to parsing JSON from response
                response = await self.llm.ainvoke(prompt)
                return self._parse_single_response(response.content, term)
        except Exception as e:
            logger.error(f"LLM selection failed for '{term}': {e}")
            # Fallback: return top candidate with reduced confidence
            if candidates:
                return SingleSelectionResult(
                    business_term=term,
                    selected_field=candidates[0].field_name,
                    confidence=candidates[0].score * 0.8,  # Reduce confidence
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
        Select best field matches for multiple terms in one LLM call.
        
        Args:
            terms_with_candidates: List of (term, candidates) tuples
            context: Optional question context
        
        Returns:
            List of SingleSelectionResult for each term
        """
        if not terms_with_candidates:
            return []
        
        # For single term, use single selection
        if len(terms_with_candidates) == 1:
            term, candidates = terms_with_candidates[0]
            result = await self.select(term, candidates, context)
            return [result]
        
        prompt = self._build_batch_selection_prompt(terms_with_candidates, context)
        
        try:
            # Use structured output if available
            if hasattr(self.llm, 'with_structured_output'):
                structured_llm = self.llm.with_structured_output(BatchSelectionResult)
                result = await structured_llm.ainvoke(prompt)
                return result.selections
            else:
                # Fallback to parsing JSON from response
                response = await self.llm.ainvoke(prompt)
                return self._parse_batch_response(response.content, terms_with_candidates)
        except Exception as e:
            logger.error(f"Batch LLM selection failed: {e}")
            # Fallback: process each term individually
            results = []
            for term, candidates in terms_with_candidates:
                result = await self.select(term, candidates, context)
                results.append(result)
            return results
    
    def _parse_single_response(
        self,
        content: str,
        term: str
    ) -> SingleSelectionResult:
        """Parse single selection response from LLM"""
        import json
        try:
            # Try to extract JSON from response
            content = content.strip()
            if content.startswith("```"):
                # Remove markdown code block
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            
            data = json.loads(content)
            return SingleSelectionResult(
                business_term=data.get("business_term", term),
                selected_field=data.get("selected_field"),
                confidence=float(data.get("confidence", 0.5)),
                reasoning=data.get("reasoning", "Parsed from LLM response")
            )
        except Exception as e:
            logger.warning(f"Failed to parse LLM response: {e}")
            return SingleSelectionResult(
                business_term=term,
                selected_field=None,
                confidence=0.0,
                reasoning=f"Failed to parse response: {e}"
            )
    
    def _parse_batch_response(
        self,
        content: str,
        terms_with_candidates: List[Tuple[str, List[FieldCandidate]]]
    ) -> List[SingleSelectionResult]:
        """Parse batch selection response from LLM"""
        import json
        try:
            content = content.strip()
            if content.startswith("```"):
                lines = content.split("\n")
                content = "\n".join(lines[1:-1])
            
            data = json.loads(content)
            selections = data.get("selections", [])
            
            results = []
            for i, (term, _) in enumerate(terms_with_candidates):
                if i < len(selections):
                    sel = selections[i]
                    results.append(SingleSelectionResult(
                        business_term=sel.get("business_term", term),
                        selected_field=sel.get("selected_field"),
                        confidence=float(sel.get("confidence", 0.5)),
                        reasoning=sel.get("reasoning", "Parsed from batch response")
                    ))
                else:
                    results.append(SingleSelectionResult(
                        business_term=term,
                        selected_field=None,
                        confidence=0.0,
                        reasoning="Missing from batch response"
                    ))
            return results
        except Exception as e:
            logger.warning(f"Failed to parse batch response: {e}")
            # Return empty results for each term
            return [
                SingleSelectionResult(
                    business_term=term,
                    selected_field=None,
                    confidence=0.0,
                    reasoning=f"Failed to parse batch response: {e}"
                )
                for term, _ in terms_with_candidates
            ]
