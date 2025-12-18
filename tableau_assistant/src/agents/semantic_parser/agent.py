"""Semantic Parser Agent - LLM combination architecture.

This agent orchestrates the LLM combination pipeline:
Step 1 → Intent Branch → (Step 2) → (Observer) → SemanticParseResult

The pipeline:
1. Step 1: Semantic understanding and question restatement
2. Intent Branch:
   - DATA_QUERY + SIMPLE: Build query directly
   - DATA_QUERY + non-SIMPLE: Continue to Step 2
   - CLARIFICATION: Generate clarification question
   - GENERAL: Generate general response
   - IRRELEVANT: Return rejection
3. Step 2: Computation reasoning and self-validation (only for non-SIMPLE)
4. Observer: Consistency checking (only when validation fails)
"""

import logging
from typing import Any

from ...core.models import (
    ClarificationQuestion,
    Computation,
    DimensionField,
    HowType,
    Intent,
    IntentType,
    MeasureField,
    ObserverDecision,
    SemanticParseResult,
    SemanticQuery,
    Step1Output,
    Step2Output,
)
from .components.observer import ObserverComponent
from .components.step1 import Step1Component
from .components.step2 import Step2Component

logger = logging.getLogger(__name__)


class SemanticParserAgent:
    """Semantic Parser Agent - LLM combination architecture.
    
    Orchestrates the LLM combination pipeline to parse user questions
    into platform-agnostic SemanticParseResult.
    """
    
    def __init__(self, llm=None, max_retries: int = 2):
        """Initialize Semantic Parser Agent.
        
        Args:
            llm: LangChain LLM instance (lazy loaded if None)
            max_retries: Maximum retries when Observer returns RETRY
        """
        self._llm = llm
        self.max_retries = max_retries
        
        # Initialize components (they will share the same LLM)
        self.step1 = Step1Component(llm)
        self.step2 = Step2Component(llm)
        self.observer = ObserverComponent(llm)
    
    def _get_llm(self):
        """Get or create LLM instance."""
        if self._llm is None:
            from tableau_assistant.src.agents.base import get_llm
            self._llm = get_llm(agent_name="semantic_parser")
        return self._llm
    
    async def parse(
        self,
        question: str,
        history: list[dict[str, str]] | None = None,
        metadata: dict[str, Any] | None = None,
    ) -> SemanticParseResult:
        """Parse user question into SemanticParseResult.
        
        Args:
            question: Current user question
            history: Conversation history
            metadata: Data source metadata
            
        Returns:
            SemanticParseResult with intent-specific output
        """
        # Step 1: Semantic understanding
        step1_output = await self.step1.execute(question, history, metadata)
        
        # Intent branch
        intent_type = step1_output.intent.type
        
        if intent_type == IntentType.CLARIFICATION:
            return self._build_clarification_result(step1_output)
        
        if intent_type == IntentType.GENERAL:
            return self._build_general_result(step1_output)
        
        if intent_type == IntentType.IRRELEVANT:
            return self._build_irrelevant_result(step1_output)
        
        # DATA_QUERY intent
        if step1_output.how_type == HowType.SIMPLE:
            # Simple query, skip Step 2
            return self._build_simple_query_result(step1_output)
        
        # Non-SIMPLE query, continue to Step 2
        return await self._process_complex_query(question, step1_output)

    async def _process_complex_query(
        self,
        original_question: str,
        step1_output: Step1Output,
    ) -> SemanticParseResult:
        """Process complex query with Step 2 and Observer.
        
        Args:
            original_question: Original user question
            step1_output: Output from Step 1
            
        Returns:
            SemanticParseResult with semantic query
        """
        retries = 0
        
        while retries <= self.max_retries:
            # Step 2: Computation reasoning
            step2_output = await self.step2.execute(step1_output)
            
            # Check validation
            if step2_output.validation.all_valid:
                # Validation passed, build result
                return self._build_complex_query_result(step1_output, step2_output)
            
            # Validation failed, trigger Observer
            observer_output = await self.observer.execute(
                original_question, step1_output, step2_output
            )
            
            # Handle Observer decision
            if observer_output.decision == ObserverDecision.ACCEPT:
                # Observer accepts despite validation failure
                return self._build_complex_query_result(step1_output, step2_output)
            
            if observer_output.decision == ObserverDecision.CORRECT:
                # Observer corrected the result
                return self._build_corrected_result(
                    step1_output, observer_output.final_result
                )
            
            if observer_output.decision == ObserverDecision.CLARIFY:
                # Need user clarification
                return self._build_clarification_from_observer(
                    step1_output, observer_output
                )
            
            # RETRY - try again
            retries += 1
        
        # Max retries exceeded, return best effort result
        return self._build_complex_query_result(step1_output, step2_output)
    
    def _build_simple_query_result(
        self, step1_output: Step1Output
    ) -> SemanticParseResult:
        """Build result for simple query (no computation)."""
        semantic_query = self._build_semantic_query(step1_output, computations=None)
        
        return SemanticParseResult(
            restated_question=step1_output.restated_question,
            intent=step1_output.intent,
            semantic_query=semantic_query,
        )
    
    def _build_complex_query_result(
        self,
        step1_output: Step1Output,
        step2_output: Step2Output,
    ) -> SemanticParseResult:
        """Build result for complex query (with computation)."""
        semantic_query = self._build_semantic_query(
            step1_output, computations=step2_output.computations
        )
        
        return SemanticParseResult(
            restated_question=step1_output.restated_question,
            intent=step1_output.intent,
            semantic_query=semantic_query,
        )
    
    def _build_corrected_result(
        self,
        step1_output: Step1Output,
        corrected_computation: Computation | None,
    ) -> SemanticParseResult:
        """Build result with Observer's correction."""
        computations = [corrected_computation] if corrected_computation else None
        semantic_query = self._build_semantic_query(step1_output, computations)
        
        return SemanticParseResult(
            restated_question=step1_output.restated_question,
            intent=step1_output.intent,
            semantic_query=semantic_query,
        )
    
    def _build_semantic_query(
        self,
        step1_output: Step1Output,
        computations: list[Computation] | None,
    ) -> SemanticQuery:
        """Build SemanticQuery from Step 1 output and computations."""
        from ...core.models.filters import SetFilter
        from ...core.models.enums import FilterType
        
        # Convert dimensions
        dimensions = [
            DimensionField(
                field_name=d.field,
                date_granularity=d.granularity,
            )
            for d in step1_output.where.dimensions
        ]
        
        # Convert measures
        measures = [
            MeasureField(
                field_name=m.field,
                aggregation=m.aggregation,
            )
            for m in step1_output.what.measures
        ]
        
        # Convert filters
        filters = []
        for f in step1_output.where.filters:
            if f.type == FilterType.SET and f.values:
                filters.append(SetFilter(
                    field_name=f.field,
                    values=f.values,
                    include=True,
                ))
            # TODO: Add other filter type conversions as needed
        
        return SemanticQuery(
            dimensions=dimensions if dimensions else None,
            measures=measures if measures else None,
            computations=computations,
            filters=filters if filters else None,
            sorts=None,
        )
    
    def _build_clarification_result(
        self, step1_output: Step1Output
    ) -> SemanticParseResult:
        """Build result for CLARIFICATION intent."""
        clarification = ClarificationQuestion(
            question=f"请问您能具体说明一下吗？{step1_output.intent.reasoning}",
            options=None,
            field_reference=None,
        )
        
        return SemanticParseResult(
            restated_question=step1_output.restated_question,
            intent=step1_output.intent,
            clarification=clarification,
        )
    
    def _build_clarification_from_observer(
        self,
        step1_output: Step1Output,
        observer_output: Any,
    ) -> SemanticParseResult:
        """Build clarification result from Observer's CLARIFY decision."""
        conflicts = observer_output.conflicts
        conflict_desc = "; ".join([c.description for c in conflicts]) if conflicts else ""
        
        clarification = ClarificationQuestion(
            question=f"我需要确认一下您的问题：{conflict_desc}",
            options=None,
            field_reference=None,
        )
        
        # Update intent to CLARIFICATION
        intent = Intent(
            type=IntentType.CLARIFICATION,
            reasoning=f"Observer requested clarification: {conflict_desc}",
        )
        
        return SemanticParseResult(
            restated_question=step1_output.restated_question,
            intent=intent,
            clarification=clarification,
        )
    
    def _build_general_result(
        self, step1_output: Step1Output
    ) -> SemanticParseResult:
        """Build result for GENERAL intent."""
        return SemanticParseResult(
            restated_question=step1_output.restated_question,
            intent=step1_output.intent,
            general_response=step1_output.intent.reasoning,
        )
    
    def _build_irrelevant_result(
        self, step1_output: Step1Output
    ) -> SemanticParseResult:
        """Build result for IRRELEVANT intent."""
        return SemanticParseResult(
            restated_question=step1_output.restated_question,
            intent=step1_output.intent,
        )
