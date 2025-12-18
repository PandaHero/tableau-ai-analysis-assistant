"""Parse result models - Final output of Semantic Parser Agent.

SemanticParseResult is the complete output of the Semantic Parser Agent,
containing the restated question, intent classification, and semantic query.
"""

from pydantic import BaseModel, ConfigDict, Field

from .query import SemanticQuery
from .step1 import Intent


class ClarificationQuestion(BaseModel):
    """Clarification question for CLARIFICATION intent.
    
    Generated when user question needs clarification.
    """
    model_config = ConfigDict(extra="forbid")
    
    question: str = Field(
        description="""<what>Clarification question to ask user</what>
<when>ALWAYS required</when>
<rule>Be specific and friendly</rule>"""
    )
    
    options: list[str] | None = Field(
        default=None,
        description="""<what>Possible options for user to choose</what>
<when>When there are known options from metadata</when>
<rule>Provide options from data source metadata</rule>"""
    )
    
    field_reference: str | None = Field(
        default=None,
        description="""<what>Related field that needs clarification</what>
<when>When clarification is about a specific field</when>"""
    )


class SemanticParseResult(BaseModel):
    """Complete output of Semantic Parser Agent.
    
    <what>Final result containing restated question, intent, and semantic query</what>
    
    This is the output of the entire LLM combination pipeline:
    Step 1 → (Step 2) → (Observer) → SemanticParseResult
    
    Different intents produce different outputs:
    - DATA_QUERY: semantic_query is populated
    - CLARIFICATION: clarification is populated
    - GENERAL: general_response is populated
    - IRRELEVANT: only restated_question and intent are populated
    
    <fill_order>
    1. restated_question (ALWAYS)
    2. intent (ALWAYS)
    3. semantic_query (if DATA_QUERY)
    4. clarification (if CLARIFICATION)
    5. general_response (if GENERAL)
    </fill_order>
    """
    model_config = ConfigDict(extra="forbid")
    
    restated_question: str = Field(
        description="""<what>Restated question from Step 1</what>
<when>ALWAYS required</when>"""
    )
    
    intent: Intent = Field(
        description="""<what>Intent classification from Step 1</what>
<when>ALWAYS required</when>"""
    )
    
    semantic_query: SemanticQuery | None = Field(
        default=None,
        description="""<what>Semantic query for DATA_QUERY intent</what>
<when>ONLY when intent.type == DATA_QUERY</when>
<dependency>intent.type == "DATA_QUERY"</dependency>"""
    )
    
    clarification: ClarificationQuestion | None = Field(
        default=None,
        description="""<what>Clarification question for CLARIFICATION intent</what>
<when>ONLY when intent.type == CLARIFICATION</when>
<dependency>intent.type == "CLARIFICATION"</dependency>"""
    )
    
    general_response: str | None = Field(
        default=None,
        description="""<what>General response for GENERAL intent</what>
<when>ONLY when intent.type == GENERAL</when>
<dependency>intent.type == "GENERAL"</dependency>"""
    )
