"""Custom exceptions for Semantic Parser.

These exceptions carry additional context for Observer-based error correction.
"""


class ValidationError(Exception):
    """Validation error with original output for Observer correction.
    
    Carries both the error message and the original LLM output,
    allowing Observer to see what went wrong and attempt correction.
    """
    
    def __init__(
        self,
        message: str,
        original_output: str | None = None,
        step: str = "unknown",
    ):
        """Initialize ValidationError.
        
        Args:
            message: Error message describing what went wrong
            original_output: Original LLM output that failed validation
            step: Which step failed ("step1" or "step2")
        """
        super().__init__(message)
        self.message = message
        self.original_output = original_output
        self.step = step
    
    def __str__(self) -> str:
        return f"[{self.step}] {self.message}"
