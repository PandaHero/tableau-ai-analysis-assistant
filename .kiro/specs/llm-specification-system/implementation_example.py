"""
LLM Specification System - Implementation Example

This module demonstrates how to implement the LLM specification system
with concrete Python code, including data models, prompt generation,
and validation logic.
"""

from enum import Enum
from typing import List, Dict, Optional, Any, Union, Callable
from pydantic import BaseModel, Field, validator
from datetime import datetime
import re
import json
import yaml


# ============================================================================
# 枚举类型定义
# ============================================================================

class ThinkingDepth(str, Enum):
    """思考深度级别"""
    QUICK = "quick"
    STANDARD = "standard"
    DEEP = "deep"


class ConfidenceLevel(str, Enum):
    """确信度级别"""
    HIGH = "high"
    MEDIUM = "medium"
    LOW = "low"


class SecurityLevel(str, Enum):
    """安全级别"""
    FORBIDDEN = "forbidden"
    CONFIRM = "confirm"
    ALLOWED = "allowed"


class ContextPriority(int, Enum):
    """上下文优先级"""
    CRITICAL = 100
    HIGH = 80
    MEDIUM = 60
    LOW = 40
    MINIMAL = 20
    DEFAULT = 0


class OutputFormat(str, Enum):
    """输出格式类型"""
    TEXT = "text"
    CODE = "code"
    JSON = "json"
    MARKDOWN = "markdown"


class ToolCategory(str, Enum):
    """工具类别"""
    FILE_READ = "file_read"
    FILE_WRITE = "file_write"
    SEARCH = "search"
    EXECUTE = "execute"
    COMMUNICATE = "communicate"


# ============================================================================
# 核心数据模型
# ============================================================================

class IntentAnalysis(BaseModel):
    """意图分析结果"""
    primary_intent: str
    secondary_intents: List[str] = []
    constraints: List[str] = []
    ambiguities: List[str] = []
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM
    
    class Config:
        use_enum_values = True


class Assumption(BaseModel):
    """假设定义"""
    id: str
    content: str
    basis: str
    verification_method: Optional[str] = None
    verified: bool = False


class ReasoningStep(BaseModel):
    """推理步骤"""
    step_id: int
    description: str
    input_data: Dict[str, Any] = {}
    output_data: Dict[str, Any] = {}
    assumptions_used: List[str] = []
    confidence: ConfidenceLevel = ConfidenceLevel.MEDIUM


class ThinkingProcess(BaseModel):
    """完整的思维过程记录"""
    depth: ThinkingDepth
    intent_analysis: IntentAnalysis
    assumptions: List[Assumption] = []
    reasoning_steps: List[ReasoningStep] = []
    reflection_notes: List[str] = []
    final_decision: str
    decision_rationale: str


class ContextItem(BaseModel):
    """上下文项"""
    id: str
    content: str
    source: str
    priority: ContextPriority
    timestamp: datetime = Field(default_factory=datetime.now)
    token_count: int = 0
    metadata: Dict[str, Any] = {}
    
    @validator('token_count', pre=True, always=True)
    def estimate_tokens(cls, v, values):
        if v == 0 and 'content' in values:
            # 简单估算: 约4个字符一个token
            return len(values['content']) // 4
        return v


class ToolParameter(BaseModel):
    """工具参数定义"""
    name: str
    type: str
    required: bool = True
    description: str
    default: Optional[Any] = None
    validation_pattern: Optional[str] = None


class ToolDefinition(BaseModel):
    """工具定义"""
    name: str
    category: ToolCategory
    description: str
    parameters: List[ToolParameter] = []
    preconditions: List[str] = []
    postconditions: List[str] = []
    security_level: SecurityLevel = SecurityLevel.ALLOWED
    examples: List[Dict[str, Any]] = []


class ToolCall(BaseModel):
    """工具调用记录"""
    id: str
    tool_name: str
    parameters: Dict[str, Any]
    purpose: str
    timestamp: datetime = Field(default_factory=datetime.now)
    result: Optional[Any] = None
    success: bool = False
    error_message: Optional[str] = None
    retry_count: int = 0


class OutputSchema(BaseModel):
    """输出Schema定义"""
    format: OutputFormat
    max_length: Optional[int] = None
    min_length: Optional[int] = None
    required_sections: List[str] = []
    forbidden_patterns: List[str] = []
    language: Optional[str] = None


class QualityCriteria(BaseModel):
    """质量标准"""
    completeness_weight: float = 0.25
    accuracy_weight: float = 0.25
    relevance_weight: float = 0.25
    conciseness_weight: float = 0.25
    min_acceptable_score: float = 0.7


class ValidationResult(BaseModel):
    """验证结果"""
    is_valid: bool
    errors: List[str] = []
    warnings: List[str] = []
    quality_score: float = 0.0
    suggestions: List[str] = []


class SecurityRule(BaseModel):
    """安全规则"""
    id: str
    name: str
    description: str
    level: SecurityLevel
    patterns: List[str] = []
    action: str
    message: str


class SensitiveDataPattern(BaseModel):
    """敏感数据模式"""
    name: str
    pattern: str
    replacement: str = "[REDACTED]"
    description: str


# ============================================================================
# Prompt 模板系统
# ============================================================================

class PromptSection(BaseModel):
    """Prompt段落"""
    name: str
    content: str
    priority: int = 0
    conditional: Optional[str] = None
    variables: List[str] = []


class PromptTemplate(BaseModel):
    """Prompt模板"""
    id: str
    name: str
    version: str = "1.0.0"
    sections: List[PromptSection]
    variables: Dict[str, str] = {}


class PromptGenerator:
    """Prompt生成器"""
    
    def __init__(self, template: PromptTemplate):
        self.template = template
    
    def generate(self, context: Dict[str, Any] = None) -> str:
        """生成完整的Prompt"""
        context = context or {}
        
        # 合并模板变量和上下文变量
        variables = {**self.template.variables, **context}
        
        # 按优先级排序段落
        sorted_sections = sorted(
            self.template.sections, 
            key=lambda s: s.priority, 
            reverse=True
        )
        
        # 渲染每个段落
        rendered_sections = []
        for section in sorted_sections:
            # 检查条件
            if section.conditional:
                if not self._evaluate_condition(section.conditional, variables):
                    continue
            
            # 渲染内容
            content = self._render_content(section.content, variables)
            rendered_sections.append(content)
        
        return "\n\n".join(rendered_sections)
    
    def _render_content(self, content: str, variables: Dict[str, Any]) -> str:
        """渲染模板内容，替换变量"""
        result = content
        for key, value in variables.items():
            result = result.replace(f"{{{{{key}}}}}", str(value))
        return result
    
    def _evaluate_condition(self, condition: str, variables: Dict[str, Any]) -> bool:
        """评估条件表达式"""
        try:
            return eval(condition, {"__builtins__": {}}, variables)
        except:
            return False


# ============================================================================
# 上下文管理器
# ============================================================================

class ContextManager:
    """上下文管理器"""
    
    def __init__(self, max_tokens: int = 128000):
        self.max_tokens = max_tokens
        self.items: List[ContextItem] = []
    
    def add_item(self, item: ContextItem) -> None:
        """添加上下文项"""
        self.items.append(item)
        self._sort_by_priority()
    
    def _sort_by_priority(self) -> None:
        """按优先级排序"""
        self.items.sort(key=lambda x: (x.priority.value, x.timestamp), reverse=True)
    
    def get_total_tokens(self) -> int:
        """获取总token数"""
        return sum(item.token_count for item in self.items)
    
    def compress_if_needed(self, target_tokens: Optional[int] = None) -> None:
        """如果需要，压缩上下文"""
        target = target_tokens or int(self.max_tokens * 0.8)
        
        while self.get_total_tokens() > target and self.items:
            # 移除最低优先级的项
            lowest_priority_item = min(self.items, key=lambda x: x.priority.value)
            self.items.remove(lowest_priority_item)
    
    def detect_conflicts(self) -> List[Dict[str, Any]]:
        """检测上下文冲突"""
        conflicts = []
        # 简化实现：检测相同source的不同内容
        source_map = {}
        for item in self.items:
            if item.source in source_map:
                if source_map[item.source].content != item.content:
                    conflicts.append({
                        "items": [source_map[item.source].id, item.id],
                        "type": "content_mismatch",
                        "source": item.source
                    })
            else:
                source_map[item.source] = item
        return conflicts
    
    def get_context_string(self) -> str:
        """获取格式化的上下文字符串"""
        parts = []
        for item in self.items:
            parts.append(f"[{item.source}] (Priority: {item.priority.name})\n{item.content}")
        return "\n\n---\n\n".join(parts)


# ============================================================================
# 输出验证器
# ============================================================================

class OutputValidator:
    """输出验证器"""
    
    def __init__(self, schema: OutputSchema, criteria: QualityCriteria):
        self.schema = schema
        self.criteria = criteria
    
    def validate(self, output: str) -> ValidationResult:
        """验证输出"""
        errors = []
        warnings = []
        suggestions = []
        
        # 长度检查
        if self.schema.max_length and len(output) > self.schema.max_length:
            errors.append(f"Output exceeds max length: {len(output)} > {self.schema.max_length}")
        
        if self.schema.min_length and len(output) < self.schema.min_length:
            warnings.append(f"Output below min length: {len(output)} < {self.schema.min_length}")
        
        # 禁止模式检查
        for pattern in self.schema.forbidden_patterns:
            if re.search(pattern, output, re.IGNORECASE):
                errors.append(f"Output contains forbidden pattern: {pattern}")
        
        # 代码语法检查（简化版）
        if self.schema.format == OutputFormat.CODE and self.schema.language:
            syntax_result = self._check_code_syntax(output, self.schema.language)
            errors.extend(syntax_result.get("errors", []))
            warnings.extend(syntax_result.get("warnings", []))
        
        # 计算质量分数
        quality_score = self._calculate_quality_score(output, errors, warnings)
        
        if quality_score < self.criteria.min_acceptable_score:
            suggestions.append(f"Quality score {quality_score:.2f} is below threshold {self.criteria.min_acceptable_score}")
        
        return ValidationResult(
            is_valid=len(errors) == 0,
            errors=errors,
            warnings=warnings,
            quality_score=quality_score,
            suggestions=suggestions
        )
    
    def _check_code_syntax(self, code: str, language: str) -> Dict[str, List[str]]:
        """检查代码语法（简化实现）"""
        errors = []
        warnings = []
        
        if language.lower() == "python":
            try:
                compile(code, "<string>", "exec")
            except SyntaxError as e:
                errors.append(f"Python syntax error: {e}")
        
        return {"errors": errors, "warnings": warnings}
    
    def _calculate_quality_score(self, output: str, errors: List[str], warnings: List[str]) -> float:
        """计算质量分数"""
        base_score = 1.0
        
        # 错误扣分
        base_score -= len(errors) * 0.2
        
        # 警告扣分
        base_score -= len(warnings) * 0.05
        
        return max(0.0, min(1.0, base_score))


# ============================================================================
# 安全守卫
# ============================================================================

class SafetyGuard:
    """安全守卫"""
    
    DEFAULT_SENSITIVE_PATTERNS = [
        SensitiveDataPattern(
            name="api_key",
            pattern=r"(?:api[_-]?key|apikey)\s*[:=]\s*['\"]?([A-Za-z0-9_-]{20,})['\"]?",
            replacement="[API_KEY_REDACTED]",
            description="API密钥"
        ),
        SensitiveDataPattern(
            name="password",
            pattern=r"(?:password|passwd|pwd)\s*[:=]\s*['\"]?(\S+)['\"]?",
            replacement="[PASSWORD_REDACTED]",
            description="密码"
        ),
        SensitiveDataPattern(
            name="token",
            pattern=r"(?:token|bearer)\s*[:=]\s*['\"]?([A-Za-z0-9_.-]+)['\"]?",
            replacement="[TOKEN_REDACTED]",
            description="令牌"
        ),
        SensitiveDataPattern(
            name="private_key",
            pattern=r"-----BEGIN\s+(?:RSA\s+)?PRIVATE\s+KEY-----",
            replacement="[PRIVATE_KEY_REDACTED]",
            description="私钥"
        ),
    ]
    
    DEFAULT_SECURITY_RULES = [
        SecurityRule(
            id="no_malicious_code",
            name="禁止恶意代码",
            description="禁止生成可能用于恶意目的的代码",
            level=SecurityLevel.FORBIDDEN,
            patterns=[
                r"rm\s+-rf\s+/",
                r":(){ :|:& };:",  # Fork bomb
                r"dd\s+if=/dev/zero",
            ],
            action="reject",
            message="无法生成可能造成系统损害的代码"
        ),
        SecurityRule(
            id="confirm_file_delete",
            name="确认文件删除",
            description="删除文件前需要确认",
            level=SecurityLevel.CONFIRM,
            patterns=[
                r"rm\s+",
                r"del\s+",
                r"unlink\s*\(",
            ],
            action="confirm",
            message="此操作将删除文件，是否继续？"
        ),
    ]
    
    def __init__(
        self, 
        rules: List[SecurityRule] = None,
        sensitive_patterns: List[SensitiveDataPattern] = None
    ):
        self.rules = rules or self.DEFAULT_SECURITY_RULES
        self.sensitive_patterns = sensitive_patterns or self.DEFAULT_SENSITIVE_PATTERNS
        self.audit_log: List[Dict[str, Any]] = []
    
    def check_input(self, input_text: str) -> Dict[str, Any]:
        """检查输入是否违反安全规则"""
        for rule in self.rules:
            for pattern in rule.patterns:
                if re.search(pattern, input_text, re.IGNORECASE):
                    self._log_event("security_violation", rule.id, input_text[:100])
                    return {
                        "allowed": rule.level != SecurityLevel.FORBIDDEN,
                        "requires_confirmation": rule.level == SecurityLevel.CONFIRM,
                        "rule": rule,
                        "message": rule.message
                    }
        
        return {"allowed": True, "requires_confirmation": False}
    
    def redact_sensitive_data(self, text: str) -> str:
        """脱敏敏感数据"""
        result = text
        for pattern in self.sensitive_patterns:
            result = re.sub(pattern.pattern, pattern.replacement, result, flags=re.IGNORECASE)
        return result
    
    def _log_event(self, event_type: str, rule_id: str, input_summary: str) -> None:
        """记录安全事件"""
        self.audit_log.append({
            "timestamp": datetime.now().isoformat(),
            "event_type": event_type,
            "rule_id": rule_id,
            "input_summary": input_summary[:100]
        })


# ============================================================================
# 工具编排器
# ============================================================================

class ToolOrchestrator:
    """工具编排器"""
    
    def __init__(self, tools: List[ToolDefinition]):
        self.tools = {tool.name: tool for tool in tools}
        self.call_history: List[ToolCall] = []
    
    def select_tool(self, task_description: str, context: Dict[str, Any] = None) -> Optional[str]:
        """根据任务描述选择工具"""
        # 简化的工具选择逻辑
        task_lower = task_description.lower()
        
        if "read" in task_lower or "view" in task_lower or "get content" in task_lower:
            return self._find_tool_by_category(ToolCategory.FILE_READ)
        elif "write" in task_lower or "create" in task_lower or "modify" in task_lower:
            return self._find_tool_by_category(ToolCategory.FILE_WRITE)
        elif "search" in task_lower or "find" in task_lower:
            return self._find_tool_by_category(ToolCategory.SEARCH)
        elif "run" in task_lower or "execute" in task_lower:
            return self._find_tool_by_category(ToolCategory.EXECUTE)
        
        return None
    
    def _find_tool_by_category(self, category: ToolCategory) -> Optional[str]:
        """按类别查找工具"""
        for name, tool in self.tools.items():
            if tool.category == category:
                return name
        return None
    
    def validate_preconditions(self, tool_name: str, context: Dict[str, Any]) -> bool:
        """验证前置条件"""
        tool = self.tools.get(tool_name)
        if not tool:
            return False
        
        # 简化实现：假设所有前置条件都满足
        return True
    
    def record_call(self, call: ToolCall) -> None:
        """记录工具调用"""
        self.call_history.append(call)
    
    def get_audit_log(self) -> List[Dict[str, Any]]:
        """获取审计日志"""
        return [
            {
                "id": call.id,
                "tool": call.tool_name,
                "purpose": call.purpose,
                "timestamp": call.timestamp.isoformat(),
                "success": call.success,
                "error": call.error_message
            }
            for call in self.call_history
        ]


# ============================================================================
# 完整规范定义
# ============================================================================

class Specification(BaseModel):
    """完整规范定义"""
    id: str
    name: str
    version: str = "1.0.0"
    description: str
    
    prompt_template: PromptTemplate
    tool_definitions: List[ToolDefinition] = []
    output_schemas: Dict[str, OutputSchema] = {}
    quality_criteria: QualityCriteria = Field(default_factory=QualityCriteria)
    security_rules: List[SecurityRule] = []
    sensitive_patterns: List[SensitiveDataPattern] = []
    
    created_at: datetime = Field(default_factory=datetime.now)
    updated_at: datetime = Field(default_factory=datetime.now)
    author: str = "system"
    tags: List[str] = []
    
    def to_yaml(self) -> str:
        """序列化为YAML"""
        return yaml.dump(self.dict(), default_flow_style=False, allow_unicode=True)
    
    @classmethod
    def from_yaml(cls, yaml_str: str) -> "Specification":
        """从YAML反序列化"""
        data = yaml.safe_load(yaml_str)
        return cls(**data)
    
    def to_json(self) -> str:
        """序列化为JSON"""
        return self.json(indent=2, ensure_ascii=False)
    
    @classmethod
    def from_json(cls, json_str: str) -> "Specification":
        """从JSON反序列化"""
        return cls.parse_raw(json_str)


# ============================================================================
# 规范引擎
# ============================================================================

class SpecificationEngine:
    """规范引擎 - 核心协调器"""
    
    def __init__(self, spec: Specification):
        self.spec = spec
        self.prompt_generator = PromptGenerator(spec.prompt_template)
        self.context_manager = ContextManager()
        self.safety_guard = SafetyGuard(
            rules=spec.security_rules or SafetyGuard.DEFAULT_SECURITY_RULES,
            sensitive_patterns=spec.sensitive_patterns or SafetyGuard.DEFAULT_SENSITIVE_PATTERNS
        )
        self.tool_orchestrator = ToolOrchestrator(spec.tool_definitions)
    
    def process_request(self, user_input: str, context: Dict[str, Any] = None) -> Dict[str, Any]:
        """处理用户请求的完整流程"""
        
        # Step 1: 安全检查
        security_check = self.safety_guard.check_input(user_input)
        if not security_check["allowed"]:
            return {
                "status": "rejected",
                "reason": security_check["message"],
                "output": None
            }
        
        if security_check.get("requires_confirmation"):
            return {
                "status": "pending_confirmation",
                "message": security_check["message"],
                "output": None
            }
        
        # Step 2: 添加用户输入到上下文
        self.context_manager.add_item(ContextItem(
            id=f"user_input_{datetime.now().timestamp()}",
            content=user_input,
            source="user",
            priority=ContextPriority.CRITICAL
        ))
        
        # Step 3: 检测上下文冲突
        conflicts = self.context_manager.detect_conflicts()
        if conflicts:
            # 记录冲突但继续处理
            pass
        
        # Step 4: 生成Prompt
        full_context = {
            **(context or {}),
            "user_input": user_input,
            "context_string": self.context_manager.get_context_string()
        }
        prompt = self.prompt_generator.generate(full_context)
        
        # Step 5: 脱敏处理
        prompt = self.safety_guard.redact_sensitive_data(prompt)
        
        return {
            "status": "ready",
            "prompt": prompt,
            "context_tokens": self.context_manager.get_total_tokens(),
            "conflicts": conflicts
        }
    
    def validate_output(self, output: str, output_type: str = "default") -> ValidationResult:
        """验证输出"""
        schema = self.spec.output_schemas.get(output_type, OutputSchema(format=OutputFormat.TEXT))
        validator = OutputValidator(schema, self.spec.quality_criteria)
        
        # 先脱敏
        sanitized_output = self.safety_guard.redact_sensitive_data(output)
        
        return validator.validate(sanitized_output)


# ============================================================================
# 使用示例
# ============================================================================

def create_example_specification() -> Specification:
    """创建示例规范"""
    
    # 定义Prompt模板
    prompt_template = PromptTemplate(
        id="coding-assistant-v1",
        name="Coding Assistant Prompt",
        version="1.0.0",
        sections=[
            PromptSection(
                name="identity",
                priority=100,
                content="""<identity>
You are {{agent_name}}, an AI coding assistant.
Your expertise: {{expertise}}
Your goal: Help users write clean, efficient, and secure code.
</identity>"""
            ),
            PromptSection(
                name="thinking",
                priority=95,
                content="""<thinking_rules>
Before responding:
1. Understand what the user is asking
2. Identify any constraints or requirements
3. Plan your approach
4. Execute step by step
5. Verify your solution
</thinking_rules>"""
            ),
            PromptSection(
                name="context",
                priority=90,
                content="""<context>
{{context_string}}
</context>"""
            ),
            PromptSection(
                name="user_request",
                priority=85,
                content="""<user_request>
{{user_input}}
</user_request>"""
            ),
        ],
        variables={
            "agent_name": "CodeAssistant",
            "expertise": "Python, JavaScript, TypeScript, and software architecture"
        }
    )
    
    # 定义工具
    tools = [
        ToolDefinition(
            name="read_file",
            category=ToolCategory.FILE_READ,
            description="Read contents of a file",
            parameters=[
                ToolParameter(name="path", type="string", required=True, description="File path")
            ],
            preconditions=["File must exist"],
            postconditions=["Returns file content or error"],
            security_level=SecurityLevel.ALLOWED
        ),
        ToolDefinition(
            name="write_file",
            category=ToolCategory.FILE_WRITE,
            description="Write content to a file",
            parameters=[
                ToolParameter(name="path", type="string", required=True, description="File path"),
                ToolParameter(name="content", type="string", required=True, description="Content to write")
            ],
            preconditions=["Directory must exist or be creatable"],
            postconditions=["File is created/updated"],
            security_level=SecurityLevel.CONFIRM
        ),
        ToolDefinition(
            name="search_code",
            category=ToolCategory.SEARCH,
            description="Search for code patterns",
            parameters=[
                ToolParameter(name="pattern", type="string", required=True, description="Search pattern"),
                ToolParameter(name="path", type="string", required=False, description="Search path", default=".")
            ],
            security_level=SecurityLevel.ALLOWED
        ),
    ]
    
    # 定义输出Schema
    output_schemas = {
        "code": OutputSchema(
            format=OutputFormat.CODE,
            forbidden_patterns=[r"TODO:", r"FIXME:", r"XXX:"],
            language="python"
        ),
        "explanation": OutputSchema(
            format=OutputFormat.MARKDOWN,
            max_length=2000
        )
    }
    
    return Specification(
        id="coding-assistant-spec-v1",
        name="Coding Assistant Specification",
        version="1.0.0",
        description="A comprehensive specification for a coding assistant LLM",
        prompt_template=prompt_template,
        tool_definitions=tools,
        output_schemas=output_schemas,
        quality_criteria=QualityCriteria(
            completeness_weight=0.3,
            accuracy_weight=0.3,
            relevance_weight=0.2,
            conciseness_weight=0.2,
            min_acceptable_score=0.75
        ),
        tags=["coding", "assistant", "python"]
    )


def main():
    """主函数 - 演示规范系统的使用"""
    
    # 创建规范
    spec = create_example_specification()
    
    # 创建引擎
    engine = SpecificationEngine(spec)
    
    # 处理请求
    result = engine.process_request(
        user_input="Please help me write a function to calculate fibonacci numbers",
        context={"project_type": "python"}
    )
    
    print("=== Request Processing Result ===")
    print(f"Status: {result['status']}")
    print(f"Context Tokens: {result.get('context_tokens', 'N/A')}")
    print(f"\n=== Generated Prompt ===\n{result.get('prompt', 'N/A')[:500]}...")
    
    # 验证输出示例
    sample_output = """
def fibonacci(n: int) -> int:
    if n <= 1:
        return n
    return fibonacci(n-1) + fibonacci(n-2)
"""
    
    validation = engine.validate_output(sample_output, "code")
    print(f"\n=== Output Validation ===")
    print(f"Valid: {validation.is_valid}")
    print(f"Quality Score: {validation.quality_score:.2f}")
    print(f"Errors: {validation.errors}")
    print(f"Warnings: {validation.warnings}")
    
    # 序列化规范
    print(f"\n=== Specification YAML (truncated) ===")
    print(spec.to_yaml()[:500] + "...")


if __name__ == "__main__":
    main()
