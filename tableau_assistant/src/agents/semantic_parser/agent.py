"""Semantic Parser Agent - LLM combination architecture.

This agent orchestrates the LLM combination pipeline:
Step 1 → (Step 1 Observer) → Intent Branch → (Step 2) → (Step 2 Observer) → SemanticParseResult

The pipeline:
1. Step 1: Semantic understanding and question restatement (with self-validation)
2. Step 1 Observer: Correct issues if validation fails OR Pydantic error occurs
3. Intent Branch:
   - DATA_QUERY + SIMPLE: Build query directly
   - DATA_QUERY + non-SIMPLE: Continue to Step 2
   - CLARIFICATION: Generate clarification question
   - GENERAL: Generate general response
   - IRRELEVANT: Return rejection
4. Step 2: Computation reasoning and self-validation (only for non-SIMPLE)
5. Step 2 Observer: Consistency checking (only when Step 2 validation fails OR Pydantic error)

Error Handling:
- All errors (Pydantic validation, semantic validation) are routed to Observer
- ValidationError carries original LLM output for Observer to analyze
- Observer decides: CORRECT (fix it), RETRY (try again), CLARIFY (ask user)
- Components do NOT handle errors internally
"""

import logging
from datetime import datetime
from typing import Any

from ...core.models import (
    ClarificationQuestion,
    Computation,
    DimensionField,
    FilterSpec,
    HowType,
    Intent,
    IntentType,
    MeasureField,
    ObserverDecision,
    SemanticParseResult,
    SemanticQuery,
    Step1Output,
    Step1Validation,
    Step2Output,
)
from ...core.exceptions import ValidationError
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
        self._last_thinking = ""  # R1 model's thinking process
        
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
        data_model: Any | None = None,
        state: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> SemanticParseResult:
        """Parse user question into SemanticParseResult.
        
        Args:
            question: Current user question
            history: Conversation history
            data_model: Data source model (DataModel object)
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            
        Returns:
            SemanticParseResult with intent-specific output
        """
        # Step 1: Semantic understanding (may raise ValueError on Pydantic error)
        step1_output, thinking = await self._execute_step1_with_error_handling(
            question, history, data_model, state=state, config=config
        )
        
        # Save thinking process for node to use
        self._last_thinking = thinking
        
        # Check Step 1 validation - trigger Observer if failed
        if not step1_output.validation.all_valid:
            step1_output = await self._correct_step1_with_observer(
                question, step1_output, state=state, config=config
            )
        
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
        return await self._process_complex_query(
            question, step1_output, state=state, config=config
        )
    
    async def _execute_step1_with_error_handling(
        self,
        question: str,
        history: list[dict[str, str]] | None,
        data_model: Any | None,
        state: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> tuple[Step1Output, str]:
        """Execute Step 1 with error handling via Observer.
        
        If Pydantic validation fails, routes to Observer for correction.
        
        Args:
            question: Current user question
            history: Conversation history
            data_model: Data source model
            state: Current workflow state
            config: LangGraph RunnableConfig
            
        Returns:
            Tuple of (Step1Output, thinking_process)
        """
        retries = 0
        last_error = None
        last_output = None
        
        while retries <= self.max_retries:
            try:
                return await self.step1.execute(
                    question, history, data_model, state=state, config=config
                )
            except ValidationError as e:
                last_error = e.message
                last_output = e.original_output
                logger.warning(f"Step 1 Pydantic validation failed: {last_error}")
                
                # Route to Observer for Pydantic error correction
                # Pass original output so Observer can see what LLM produced
                corrected_output = await self._correct_step1_pydantic_error(
                    question, last_error, last_output, state=state, config=config
                )
                
                if corrected_output:
                    return corrected_output, ""
                
                retries += 1
                logger.info(f"Observer returned RETRY, attempt {retries}/{self.max_retries}")
        
        # Max retries exceeded
        logger.error(f"Step 1 failed after {self.max_retries} retries: {last_error}")
        raise ValueError(f"Step 1 failed after {self.max_retries} retries: {last_error}")
    
    async def _correct_step1_pydantic_error(
        self,
        original_question: str,
        error_message: str,
        original_output: str | None = None,
        state: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> Step1Output | None:
        """Correct Step 1 Pydantic error using Observer.
        
        Args:
            original_question: Original user question
            error_message: Pydantic validation error message
            original_output: Original LLM output that failed validation
            state: Current workflow state
            config: LangGraph RunnableConfig
            
        Returns:
            Corrected Step1Output if Observer can fix, None if RETRY needed
        """
        logger.info(f"Routing Step 1 Pydantic error to Observer: {error_message}")
        if original_output:
            logger.debug(f"Original LLM output: {original_output[:500]}...")
        
        # Create a minimal Step1Output with validation failure for Observer
        # Include original output in issues so Observer can see what went wrong
        from ...core.models.step1 import What, Where, Intent
        from ...core.models.enums import IntentType
        
        issues = [f"Pydantic validation error: {error_message}"]
        if original_output:
            # Truncate if too long
            truncated_output = original_output[:1000] + "..." if len(original_output) > 1000 else original_output
            issues.append(f"Original LLM output: {truncated_output}")
        
        placeholder_output = Step1Output(
            restated_question=original_question,
            what=What(measures=[]),
            where=Where(dimensions=[], filters=[]),
            how_type=HowType.SIMPLE,
            intent=Intent(type=IntentType.DATA_QUERY, reasoning="Pydantic error occurred"),
            validation=Step1Validation(
                all_valid=False,
                issues=issues,
            ),
        )
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        observer_output = await self.observer.execute_for_step1(
            original_question=original_question,
            step1_output=placeholder_output,
            current_time=current_time,
            state=state,
            config=config,
        )
        
        if observer_output.decision == ObserverDecision.CORRECT:
            if observer_output.step1_correction:
                # Observer provided corrected filters, but we need full Step1Output
                # For Pydantic errors, Observer should provide complete correction
                logger.info("Observer corrected Pydantic error")
                # Return None to trigger retry with corrected context
                # TODO: Enhance Observer to return full Step1Output for Pydantic errors
                return None
        
        if observer_output.decision == ObserverDecision.CLARIFY:
            # Cannot fix, need user clarification
            logger.info("Observer requests clarification for Pydantic error")
            return placeholder_output
        
        # RETRY or ACCEPT - return None to trigger retry
        return None
    
    async def _correct_step1_with_observer(
        self,
        original_question: str,
        step1_output: Step1Output,
        state: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> Step1Output:
        """Correct Step 1 output using Observer when validation fails.
        
        Args:
            original_question: Original user question
            step1_output: Step 1 output with validation failures
            state: Current workflow state
            config: LangGraph RunnableConfig
            
        Returns:
            Corrected Step1Output
        """
        logger.info(f"Step 1 validation failed, triggering Observer for correction")
        logger.info(f"Validation issues: {step1_output.validation.issues}")
        
        current_time = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        
        retries = 0
        while retries <= self.max_retries:
            # Call Observer for Step 1 correction
            observer_output = await self.observer.execute_for_step1(
                original_question=original_question,
                step1_output=step1_output,
                current_time=current_time,
                state=state,
                config=config,
            )
            
            # Handle Observer decision
            if observer_output.decision == ObserverDecision.CORRECT:
                if observer_output.step1_correction:
                    # Apply correction to Step 1 output
                    corrected_filters = observer_output.step1_correction.corrected_filters
                    logger.info(f"Observer corrected {len(corrected_filters)} filter(s)")
                    
                    # Create new Step1Output with corrected filters
                    from ...core.models.step1 import Where
                    corrected_where = Where(
                        dimensions=step1_output.where.dimensions,
                        filters=corrected_filters,
                    )
                    
                    # Create corrected output with valid validation
                    corrected_output = Step1Output(
                        restated_question=step1_output.restated_question,
                        what=step1_output.what,
                        where=corrected_where,
                        how_type=step1_output.how_type,
                        intent=step1_output.intent,
                        validation=Step1Validation(all_valid=True),
                    )
                    return corrected_output
            
            elif observer_output.decision == ObserverDecision.ACCEPT:
                # Observer accepts despite validation failure (rare case)
                logger.warning("Observer accepted Step 1 despite validation failure")
                return step1_output
            
            elif observer_output.decision == ObserverDecision.CLARIFY:
                # Cannot correct, need user clarification - return as is
                logger.info("Observer requests clarification for Step 1 issues")
                return step1_output
            
            # RETRY - try again
            retries += 1
            logger.info(f"Observer returned RETRY, attempt {retries}/{self.max_retries}")
        
        # Max retries exceeded, return original
        logger.warning(f"Step 1 correction failed after {self.max_retries} retries")
        return step1_output

    async def _process_complex_query(
        self,
        original_question: str,
        step1_output: Step1Output,
        state: dict[str, Any] | None = None,
        config: dict[str, Any] | None = None,
    ) -> SemanticParseResult:
        """Process complex query with Step 2 and Observer.
        
        Handles both Pydantic errors and semantic validation failures.
        
        Args:
            original_question: Original user question
            step1_output: Output from Step 1
            state: Current workflow state (for middleware)
            config: LangGraph RunnableConfig (contains middleware)
            
        Returns:
            SemanticParseResult with semantic query
        """
        retries = 0
        
        while retries <= self.max_retries:
            try:
                # Step 2: Computation reasoning
                step2_output = await self.step2.execute(
                    step1_output, state=state, config=config
                )
                
                # Check validation
                if step2_output.validation.all_valid:
                    # Validation passed, build result
                    return self._build_complex_query_result(step1_output, step2_output)
                
                # Semantic validation failed, trigger Observer
                observer_output = await self.observer.execute(
                    original_question, step1_output, step2_output,
                    state=state, config=config
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
                logger.info(f"Observer returned RETRY for Step 2, attempt {retries}/{self.max_retries}")
                
            except ValidationError as e:
                # Pydantic validation error from Step 2
                logger.warning(f"Step 2 Pydantic validation failed: {e.message}")
                if e.original_output:
                    logger.debug(f"Original LLM output: {e.original_output[:500]}...")
                
                # Route to Observer for Pydantic error
                # Create placeholder Step2Output with original output in inconsistencies
                from ...core.models.step2 import Step2Validation, ValidationCheck
                
                inconsistencies = [f"Pydantic validation error: {e.message}"]
                if e.original_output:
                    truncated = e.original_output[:1000] + "..." if len(e.original_output) > 1000 else e.original_output
                    inconsistencies.append(f"Original LLM output: {truncated}")
                
                placeholder_step2 = Step2Output(
                    reasoning=f"Pydantic error: {e.message}",
                    computations=[],
                    validation=Step2Validation(
                        target_check=ValidationCheck(
                            inferred_value="",
                            reference_value="",
                            is_match=False,
                            note=f"Pydantic error: {e.message}",
                        ),
                        partition_by_check=ValidationCheck(
                            inferred_value="",
                            reference_value="",
                            is_match=False,
                            note="",
                        ),
                        calc_type_check=ValidationCheck(
                            inferred_value="",
                            reference_value="",
                            is_match=False,
                            note="",
                        ),
                        all_valid=False,
                        inconsistencies=inconsistencies,
                    ),
                )
                
                observer_output = await self.observer.execute(
                    original_question, step1_output, placeholder_step2,
                    state=state, config=config
                )
                
                if observer_output.decision == ObserverDecision.CLARIFY:
                    return self._build_clarification_from_observer(
                        step1_output, observer_output
                    )
                
                # RETRY
                retries += 1
                logger.info(f"Observer returned RETRY for Step 2 Pydantic error, attempt {retries}/{self.max_retries}")
        
        # Max retries exceeded, return best effort result
        logger.warning(f"Step 2 failed after {self.max_retries} retries, returning simple query")
        return self._build_simple_query_result(step1_output)
    
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
        from ...core.models.filters import SetFilter, TopNFilter
        from ...core.models.fields import Sort
        from ...core.models.enums import FilterType, SortDirection
        
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
            elif f.type == FilterType.DATE_RANGE:
                from ...core.models.filters import DateRangeFilter
                from datetime import date
                
                # start_date and end_date are already validated by Pydantic in FilterSpec
                # They are guaranteed to be in YYYY-MM-DD format if present
                start_date = date.fromisoformat(f.start_date) if f.start_date else None
                end_date = date.fromisoformat(f.end_date) if f.end_date else None
                
                if start_date or end_date:
                    filters.append(DateRangeFilter(
                        field_name=f.field,
                        start_date=start_date,
                        end_date=end_date,
                    ))
                else:
                    logger.warning(f"DATE_RANGE filter for field '{f.field}' skipped: no dates provided")
            elif f.type == FilterType.TOP_N and f.n and f.by_field:
                # TOP_N filter - for "top 5 cities by sales" or "bottom 5 cities by sales"
                direction = f.direction or SortDirection.DESC  # Default DESC for top N
                filters.append(TopNFilter(
                    field_name=f.field,
                    n=f.n,
                    by_field=f.by_field,
                    direction=direction,
                ))
        
        # Convert sorts from measures with sort_direction
        sorts = []
        for m in step1_output.what.measures:
            if m.sort_direction is not None:
                sorts.append(Sort(
                    field_name=m.field,
                    direction=m.sort_direction,
                    priority=m.sort_priority,
                ))
        
        # Sort by priority
        sorts.sort(key=lambda s: s.priority)
        
        return SemanticQuery(
            dimensions=dimensions if dimensions else None,
            measures=measures if measures else None,
            computations=computations,
            filters=filters if filters else None,
            sorts=sorts if sorts else None,
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
