"""
Dynamic Prompt Builder

Assembles prompts dynamically based on detected question features.
Only includes relevant modules, reducing context noise.

Design Principles:
- Feature-driven: Modules activated by detected features
- Minimal context: Only include what's needed
- Composable: Modules combined in priority order
"""
from typing import Set, List, Optional, Type
from pydantic import BaseModel

from .feature_tags import FeatureTag
from .prompt_module import PromptModule, ALL_MODULES
from .feature_detector import FeatureDetector


class DynamicPromptBuilder:
    """Build prompts dynamically based on question features.
    
    Usage:
        builder = DynamicPromptBuilder()
        
        # Option 1: Auto-detect features from question
        prompt = builder.build_prompt("各省份的销售额")
        
        # Option 2: Provide pre-detected features
        features = {FeatureTag.DIMENSION, FeatureTag.MEASURE}
        prompt = builder.build_prompt_for_features(features)
    """
    
    def __init__(
        self,
        modules: Optional[List[PromptModule]] = None,
        detector: Optional[FeatureDetector] = None
    ):
        """Initialize builder.
        
        Args:
            modules: Custom modules (default: ALL_MODULES)
            detector: Custom feature detector (default: new FeatureDetector)
        """
        self.modules = modules or ALL_MODULES
        self.detector = detector or FeatureDetector()
    
    def detect_features(self, question: str) -> Set[FeatureTag]:
        """Detect features in a question.
        
        Args:
            question: User's question text
            
        Returns:
            Set of detected feature tags
        """
        return self.detector.detect(question)
    
    def select_modules(self, features: Set[FeatureTag]) -> List[PromptModule]:
        """Select modules that match detected features.
        
        Args:
            features: Set of detected feature tags
            
        Returns:
            List of matching modules, sorted by priority
        """
        matching = [m for m in self.modules if m.matches(features)]
        return sorted(matching, key=lambda m: m.priority)
    
    def build_knowledge(self, modules: List[PromptModule]) -> str:
        """Build combined domain knowledge from modules.
        
        Args:
            modules: List of selected modules
            
        Returns:
            Combined knowledge string
        """
        knowledge_parts = []
        for module in modules:
            if module.knowledge.strip():
                knowledge_parts.append(f"### {module.name.title()}\n{module.knowledge}")
        
        return "\n\n".join(knowledge_parts)
    
    def build_prompt(self, question: str) -> str:
        """Build prompt for a question (auto-detect features).
        
        Args:
            question: User's question text
            
        Returns:
            Combined domain knowledge for the question
        """
        features = self.detect_features(question)
        return self.build_prompt_for_features(features)
    
    def build_prompt_for_features(self, features: Set[FeatureTag]) -> str:
        """Build prompt for given features.
        
        Args:
            features: Set of feature tags
            
        Returns:
            Combined domain knowledge for the features
        """
        modules = self.select_modules(features)
        return self.build_knowledge(modules)
    
    def get_feature_summary(self, question: str) -> dict:
        """Get summary of detected features and selected modules.
        
        Useful for debugging and understanding prompt composition.
        
        Args:
            question: User's question text
            
        Returns:
            Dict with features, modules, and knowledge
        """
        features = self.detect_features(question)
        modules = self.select_modules(features)
        knowledge = self.build_knowledge(modules)
        
        return {
            "question": question,
            "features": [f.value for f in features],
            "modules": [m.name for m in modules],
            "knowledge_length": len(knowledge),
            "knowledge": knowledge
        }


class ModularUnderstandingPrompt:
    """Modular prompt for question understanding.
    
    Extends the base understanding prompt with dynamic module selection.
    Only includes relevant domain knowledge based on question features.
    
    Usage:
        prompt = ModularUnderstandingPrompt()
        messages = prompt.format_messages(question="各省份的销售额", max_date="2024-12-04")
    """
    
    def __init__(self, builder: Optional[DynamicPromptBuilder] = None):
        """Initialize modular prompt.
        
        Args:
            builder: Custom builder (default: new DynamicPromptBuilder)
        """
        self.builder = builder or DynamicPromptBuilder()
    
    def get_role(self) -> str:
        """Get role definition."""
        return """Query analyzer: extract entities, classify SQL roles, provide structured reasoning.

Expertise: entity extraction, SQL role classification, time interpretation, step-by-step analysis"""
    
    def get_task(self) -> str:
        """Get task definition."""
        return """Analyze question with structured reasoning:
1. Reason through each step (intent → entities → roles → time → validation)
2. Extract all business entities
3. Classify each entity's SQL role independently
4. Identify time scope if present

Output: reasoning steps + classified entities + time range"""
    
    def get_constraints(self) -> str:
        """Get constraints."""
        return """MUST:
- Provide reasoning steps for valid questions
- Use business terms only (not technical field names)
- Classify each entity independently

MUST NOT:
- Use technical field names like [Table].[Field]
- Skip entities mentioned in question
- Set aggregation for group_by role"""
    
    def get_dynamic_knowledge(self, question: str) -> str:
        """Get dynamic domain knowledge based on question features.
        
        Args:
            question: User's question text
            
        Returns:
            Relevant domain knowledge
        """
        return self.builder.build_prompt(question)
    
    def get_system_message(self, question: str) -> str:
        """Build system message with dynamic knowledge.
        
        Args:
            question: User's question text
            
        Returns:
            Complete system message
        """
        sections = [
            f"# ROLE\n{self.get_role()}",
            f"# TASK\n{self.get_task()}",
            f"# DOMAIN KNOWLEDGE\n{self.get_dynamic_knowledge(question)}",
            f"# CONSTRAINTS\n{self.get_constraints()}"
        ]
        return "\n\n".join(sections)
    
    def get_user_template(self) -> str:
        """Get user message template."""
        return """Question: "{question}"

Current date: {max_date}

Analyze with structured reasoning."""
    
    def get_output_model(self) -> Type[BaseModel]:
        """Get output model."""
        from tableau_assistant.src.models.question import QuestionUnderstanding
        return QuestionUnderstanding
    
    def format_messages(self, question: str, max_date: str, **kwargs) -> list:
        """Format messages for LLM.
        
        Args:
            question: User's question text
            max_date: Current/max date for time interpretation
            **kwargs: Additional template variables
            
        Returns:
            List of message dicts
        """
        import json
        
        # Get output schema
        output_model = self.get_output_model()
        json_schema = output_model.model_json_schema()
        
        # Build system message with dynamic knowledge
        system_content = self.get_system_message(question)
        
        # Add schema instruction
        schema_instruction = f"""
## Output Format

You must output ONLY valid JSON that strictly follows this schema:

{json.dumps(json_schema, indent=2, ensure_ascii=False)}

**CRITICAL REQUIREMENTS:**
1. Output MUST be pure JSON - start with {{ and end with }}
2. DO NOT wrap the JSON in markdown code blocks
3. All required fields must be present
"""
        system_content += schema_instruction
        
        # Build user message
        user_content = self.get_user_template().format(
            question=question,
            max_date=max_date,
            **kwargs
        )
        
        return [
            {"role": "system", "content": system_content},
            {"role": "user", "content": user_content}
        ]


# Singleton builder for convenience
_builder = DynamicPromptBuilder()


def build_dynamic_prompt(question: str) -> str:
    """Convenience function to build dynamic prompt.
    
    Args:
        question: User's question text
        
    Returns:
        Dynamic domain knowledge
    """
    return _builder.build_prompt(question)


__all__ = [
    "DynamicPromptBuilder",
    "ModularUnderstandingPrompt",
    "build_dynamic_prompt",
]
