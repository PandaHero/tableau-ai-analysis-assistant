"""错误消息脱敏工具。"""

_SENSITIVE_KEYWORDS = [
    "api_key",
    "api_secret",
    "password",
    "token",
    "secret",
    "connection_string",
    "sqlite",
    "postgresql",
    "postgres",
    "traceback",
    'file "',
    "\\analytics_assistant\\",
    "/analytics_assistant/",
    "deepseek",
    "zhipu",
    "openai",
    "sk-",
    "conn_string",
    "db_path",
]


def sanitize_error_message(message: str) -> str:
    """清理错误消息，移除可能泄露内部细节的内容。

    Args:
        message: 原始错误消息。

    Returns:
        对客户端安全的错误消息。
    """
    for keyword in _SENSITIVE_KEYWORDS:
        if keyword.lower() in message.lower():
            return "服务内部错误，请稍后重试"
    return message


__all__ = ["sanitize_error_message"]
