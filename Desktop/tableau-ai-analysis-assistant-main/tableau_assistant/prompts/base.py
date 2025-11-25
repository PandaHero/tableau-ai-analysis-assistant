"""
Base prompt classes for Tableau Assistant

Provides a clean, maintainable architecture for prompt management with:
- Automatic JSON Schema injection
- Standardized 4-section structure (ROLE, TASK, DOMAIN KNOWLEDGE, CONSTRAINTS)
- Schema-first design: let Field descriptions do the heavy lifting
- Layered design (Base → Structured → Domain-Specific)
- Validation and quality assurance

Design principle: "Schema优先" - prompt only provides what schema cannot express
(decision rules, IF-THEN logic, field relationships).
"""
from abc import ABC, abstractmethod
from typing import Type, Dict, Any, List, Optional
from pydantic import BaseModel
import json


class BasePrompt(ABC):
    """
    Base class for all prompts with automatic JSON Schema injection
    
    This class provides a structured approach to prompt engineering:
    1. Define role and instructions in get_system_message()
    2. Define user input template in get_user_template()
    3. Define output structure in get_output_model()
    4. Schema is automatically injected into the prompt
    
    Example:
        class MyPrompt(BasePrompt):
            def get_system_message(self) -> str:
                return "You are a helpful assistant..."
            
            def get_user_template(self) -> str:
                return "User question: {question}"
            
            def get_output_model(self) -> Type[BaseModel]:
                return MyOutputModel
    """
    
    @abstractmethod
    def get_system_message(self) -> str:
        """
        Get the system message defining role and core instructions
        
        This should include:
        - Role definition
        - Task description
        - Key principles or guidelines
        - Available context (metadata, etc.)
        
        Returns:
            System message string with placeholders for format()
        """
        pass
    
    @abstractmethod
    def get_user_template(self) -> str:
        """
        Get the user message template with placeholders
        
        This should be a simple template with {placeholder} variables
        that will be filled in by format_messages()
        
        Returns:
            User message template string
        """
        pass
    
    @abstractmethod
    def get_output_model(self) -> Type[BaseModel]:
        """
        Get the Pydantic model for output validation
        
        The model's JSON Schema will be automatically injected into
        the prompt to guide the LLM's output format.
        
        Returns:
            Pydantic BaseModel class (not instance)
        """
        pass

    
    def get_schema_instruction(self) -> str:
        """
        Get JSON Schema instruction (can be overridden for customization)
        
        This provides the standard instruction for LLM to follow the schema.
        Subclasses can override this to provide custom instructions.
        
        Returns:
            Schema instruction string with {json_schema} placeholder
        """
        return """
## Output Format

You must output ONLY valid JSON that strictly follows this schema:

{json_schema}

**CRITICAL REQUIREMENTS:**
1. Output MUST be pure JSON - start with {{ and end with }}
2. DO NOT wrap the JSON in markdown code blocks (no ```json or ```)
3. DO NOT add any text before or after the JSON
4. All required fields must be present
5. Field types must match exactly
6. No additional fields beyond schema definition

**WRONG (DO NOT DO THIS):**
```json
{{"field": "value"}}
```

**CORRECT (DO THIS):**
{{"field": "value"}}
"""
    
    def format_messages(self, **kwargs) -> list:
        """
        Format messages for LLM with automatic schema injection
        
        This method:
        1. Generates JSON Schema from the output model
        2. Injects schema into kwargs
        3. Builds system message (instructions + schema)
        4. Builds user message from template
        
        Args:
            **kwargs: Variables to fill in the templates
        
        Returns:
            List of message dicts with 'role' and 'content' keys
        
        Example:
            messages = prompt.format_messages(
                question="What is the sales?",
                metadata={...}
            )
        """
        # Generate JSON schema from output model
        output_model = self.get_output_model()
        json_schema = output_model.model_json_schema()
        
        # Add schema to kwargs for template formatting
        kwargs_with_schema = {
            **kwargs,
            "json_schema": json.dumps(json_schema, indent=2, ensure_ascii=False)
        }
        
        # Build system message (instructions + schema)
        system_content = self.get_system_message() + self.get_schema_instruction()
        
        # Format system message with kwargs (in case it has placeholders)
        try:
            system_content = system_content.format(**kwargs_with_schema)
        except KeyError:
            # If system message doesn't use all kwargs, that's fine
            pass
        
        # Build user message from template
        user_content = self.get_user_template().format(**kwargs_with_schema)
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]


class StructuredPrompt(BasePrompt):
    """
    Structured prompt template with 4 standardized sections + auto-injected schema
    
    The 4 sections focus on business logic:
    1. ROLE - Define the AI's role (1 sentence, ~20 words)
    2. TASK - Define the task with implicit CoT (~50 words)
    3. DOMAIN KNOWLEDGE - Provide domain-specific rules (~200 words)
    4. CONSTRAINTS - Define boundaries (3-5 rules, ~10 words each)
    
    Output Format (JSON Schema) is automatically injected and not counted in the 4 sections.
    
    Design principle: "Schema优先" - let Field descriptions do the heavy lifting,
    prompt only provides what schema cannot express (decision rules, IF-THEN logic).
    """
    
    def get_role(self) -> str:
        """
        Define the AI's role in one concise sentence
        
        Target: ~20 words or less
        
        Example: "Data analyst who completes missing essential information."
        
        Returns:
            Role definition string
        """
        return ""
    
    def get_task(self) -> str:
        """
        Define the task with implicit Chain-of-Thought
        
        Should include:
        - What to do (1 sentence)
        - Process (3-5 steps using "→" or "THEN")
        
        Target: ~50 words or less
        
        Example:
        "Extract and classify entities.
        
        Process: Extract → Classify → Check aggregation → Decide split"
        
        Returns:
            Task description string with implicit CoT
        """
        return ""
    
    def get_domain_knowledge(self) -> str:
        """
        Provide domain-specific knowledge that schema cannot express
        
        Should include:
        - Decision rules (IF-THEN format)
        - Field relationships
        - Execution priorities
        - Domain-specific constraints
        
        Should NOT include:
        - Field descriptions (already in schema)
        - Generic instructions (LLM already knows)
        
        Target: ~200 words or less
        
        Returns:
            Domain knowledge string
        """
        return ""
    
    def get_constraints(self) -> str:
        """
        Define boundaries in concise rules
        
        Format: "MUST NOT: X" or "MUST: Y"
        
        Target: 3-5 rules, each ~10 words or less
        
        Example:
        "MUST NOT: invent entities, use technical names
        MUST: extract ALL entities, use business terms"
        
        Returns:
            Constraints string
        """
        return ""
    
    def get_system_message(self) -> str:
        """
        Compose system message from 4 sections
        
        Automatically assembles all non-empty sections.
        Schema is injected separately by format_messages().
        
        Returns:
            Complete system message string (without schema)
        """
        sections = []
        
        # Add each non-empty section
        if role := self.get_role():
            sections.append(f"# ROLE\n{role}")
        
        if task := self.get_task():
            sections.append(f"# TASK\n{task}")
        
        if knowledge := self.get_domain_knowledge():
            sections.append(f"# DOMAIN KNOWLEDGE\n{knowledge}")
        
        if constraints := self.get_constraints():
            sections.append(f"# CONSTRAINTS\n{constraints}")
        
        return "\n\n".join(sections)
    
    def validate(self) -> List[str]:
        """
        Validate prompt completeness
        
        Returns:
            List of warnings (empty if all good)
        """
        warnings = []
        
        if not self.get_role():
            warnings.append("ROLE section is empty")
        
        if not self.get_task():
            warnings.append("TASK section is empty")
        
        if not self.get_domain_knowledge():
            warnings.append("DOMAIN KNOWLEDGE section is empty (recommended)")
        
        return warnings


class DataAnalysisPrompt(StructuredPrompt):
    """
    Base prompt for data analysis tasks
    
    Provides common data analysis fundamentals.
    Subclasses override get_domain_knowledge() for specific rules.
    """
    
    def get_data_analysis_fundamentals(self) -> str:
        """
        Common data analysis fundamentals (very concise)
        
        Returns:
            Brief data analysis principles
        """
        return """Use business terminology, maintain user intent, focus on actionable insights."""
    
    def get_domain_knowledge(self) -> str:
        """
        Combine fundamentals with specific domain knowledge
        
        Subclasses should override get_specific_domain_knowledge()
        
        Returns:
            Complete domain knowledge
        """
        fundamentals = self.get_data_analysis_fundamentals()
        specific = self.get_specific_domain_knowledge()
        
        if specific:
            return f"{fundamentals}\n\n{specific}"
        return fundamentals
    
    def get_specific_domain_knowledge(self) -> str:
        """
        Override in subclasses for specific domain knowledge
        
        Returns:
            Specific domain knowledge for the particular task
        """
        return ""


class VizQLPrompt(DataAnalysisPrompt):
    """
    Base prompt for VizQL-related tasks
    
    Extends DataAnalysisPrompt with VizQL-specific knowledge.
    Subclasses should override get_specific_domain_knowledge() to include VizQL rules.
    """
    
    def get_vizql_capabilities(self) -> str:
        """
        VizQL capabilities description (detailed version)
        
        Returns:
            Detailed description of VizQL query capabilities and limitations
            
        Note:
            Understanding Agent should use simplified version for decomposition rules only
        """
        from tableau_assistant.prompts.vizql_capabilities import vizql_capabilities
        return vizql_capabilities.get_content()
    
    def format_messages(self, **kwargs) -> list:
        """
        Override to inject VizQL context into kwargs for backward compatibility
        
        Args:
            **kwargs: Template variables
        
        Returns:
            Formatted messages with VizQL context injected
        """
        # Add VizQL context to kwargs for backward compatibility
        kwargs['vizql_context'] = self.get_vizql_capabilities()
        
        # Call parent implementation
        return super().format_messages(**kwargs)


# ============= 导出 =============

__all__ = [
    "BasePrompt",
    "StructuredPrompt",
    "DataAnalysisPrompt",
    "VizQLPrompt",
]
