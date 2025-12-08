"""
应用配置

注意：所有环境变量从项目根目录的 .env 文件读取
"""
import os
from pathlib import Path
from pydantic import Field
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from dotenv import load_dotenv

# 获取项目根目录（向上3级：config -> src -> tableau_assistant -> root）
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent

# 从根目录加载 .env 文件
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)
else:
    print(f"⚠️  警告: .env 文件不存在于 {env_path}")


class Settings(BaseSettings):
    """应用配置
    
    所有配置从项目根目录的 .env 文件读取
    """

    # Tableau配置
    tableau_domain: str = os.getenv("TABLEAU_DOMAIN", "")
    tableau_base_url: str = os.getenv("TABLEAU_BASE_URL", "")
    tableau_site: str = os.getenv("TABLEAU_SITE", "")
    tableau_api_version: str = os.getenv("TABLEAU_API_VERSION", "3.21")
    tableau_user: str = os.getenv("TABLEAU_USER", "")
    tableau_jwt_client_id: str = os.getenv("TABLEAU_JWT_CLIENT_ID", "")
    tableau_jwt_secret_id: str = os.getenv("TABLEAU_JWT_SECRET_ID", "")
    tableau_jwt_secret: str = os.getenv("TABLEAU_JWT_SECRET", "")
    datasource_luid: str = os.getenv("DATASOURCE_LUID", "")

    # LLM配置
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:8000/v1")
    llm_model_provider: str = os.getenv("LLM_MODEL_PROVIDER", "qwen3")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_api_timeout: int = int(os.getenv("LLM_API_TIMEOUT", "30"))
    llm_api_max_tokens: int = int(os.getenv("LLM_API_MAX_TOKENS", "40000"))
    tooling_llm_model: str = os.getenv("TOOLING_LLM_MODEL", "")  # 具体的模型名称，必须配置
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")

    # LangChain配置
    langchain_tracing_v2: str = os.getenv("LANGCHAIN_TRACING_V2", "false")
    langchain_endpoint: str = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    langchain_api_key: str = os.getenv("LANGCHAIN_API_KEY", "")
    langchain_project: str = os.getenv("LANGCHAIN_PROJECT", "tableau_agent")
    
    # Store配置（LangGraph持久化存储）
    store_max_search_limit: int = int(os.getenv("STORE_MAX_SEARCH_LIMIT", "4000"))
    store_db_path: str = os.getenv("STORE_DB_PATH", "data/langgraph_store.db")
    store_metadata_ttl: int = int(os.getenv("STORE_METADATA_TTL", "3600"))  # 元数据缓存 TTL（秒）

    # 任务调度配置
    parallel_upper_limit: int = int(os.getenv("Parallel_Upper_Limit", "3"))
    max_retry_times: int = int(os.getenv("MAX_RETRY_TIMES", "2"))
    max_replan_rounds: int = int(os.getenv("MAX_REPLAN_ROUNDS", "3"))
    max_subtasks_per_round: int = int(os.getenv("MAX_SUBTASKS_PER_ROUND", "10"))

    # 中间件配置 (Middleware)
    # SummarizationMiddleware - 根据模型上下文长度调整，预留30%给输出
    # - Claude 3.5: 200K context → threshold ~60K
    # - DeepSeek: 64K context → threshold ~20K
    # - Qwen: 32K context → threshold ~10K
    summarization_token_threshold: int = int(os.getenv("SUMMARIZATION_TOKEN_THRESHOLD", "20000"))
    messages_to_keep: int = int(os.getenv("MESSAGES_TO_KEEP", "10"))
    
    # RetryMiddleware
    model_max_retries: int = int(os.getenv("MODEL_MAX_RETRIES", "3"))
    tool_max_retries: int = int(os.getenv("TOOL_MAX_RETRIES", "3"))
    
    # FilesystemMiddleware - 大结果自动转存阈值
    filesystem_token_limit: int = int(os.getenv("FILESYSTEM_TOKEN_LIMIT", "20000"))
    
    # HumanInTheLoopMiddleware - 需要人工确认的工具列表（逗号分隔）
    _interrupt_on_str: str = os.getenv("INTERRUPT_ON", "")
    
    @property
    def interrupt_on(self) -> list[str] | None:
        """返回需要人工确认的工具列表"""
        if not self._interrupt_on_str:
            return None
        return [tool.strip() for tool in self._interrupt_on_str.split(",") if tool.strip()]

    # API配置
    api_host: str = os.getenv("HOST", "127.0.0.1")
    api_port: int = int(os.getenv("PORT", "8000"))
    api_reload: bool = os.getenv("API_RELOAD", "true").lower() == "true"
    api_log_level: str = os.getenv("API_LOG_LEVEL", "info")

    # SSL配置
    ssl_cert_file: str = os.getenv("SSL_CERT_FILE", "")
    ssl_key_file: str = os.getenv("SSL_KEY_FILE", "")

    # CORS配置 - 存储为字符串，避免Pydantic自动解析
    _cors_origins_str: str = os.getenv("CORS_ORIGINS", "https://localhost:5173,https://127.0.0.1:5173")
    
    @property
    def cors_origins(self) -> List[str]:
        """返回CORS origins列表"""
        return [
            origin.strip().replace("'", "").replace('"', "")
            for origin in self._cors_origins_str.split(",")
            if origin.strip()
        ]

    # VizQL配置
    vizql_return_format: str = os.getenv("VIZQL_RETURN_FORMAT", "OBJECTS")
    vizql_debug: bool = os.getenv("VIZQL_DEBUG", "false").lower() == "true"
    vizql_disaggregate: bool = os.getenv("VIZQL_DISAGGREGATE", "false").lower() == "true"

    # 功能开关
    feature_boost_validate_enabled: bool = os.getenv("FEATURE_BOOST_VALIDATE_ENABLED", "false").lower() == "true"

    # 开发配置
    debug: bool = os.getenv("DEBUG", "0") == "1"

    model_config = SettingsConfigDict(
        case_sensitive=False,
        extra='ignore'  # 忽略未定义的环境变量
    )


# 创建全局配置实例
settings = Settings()

# 打印配置加载信息（仅在DEBUG模式）
if settings.debug:
    print(f"✅ 配置已从 {env_path} 加载")
    print(f"   - Tableau Domain: {settings.tableau_domain}")
    print(f"   - LLM API Base: {settings.llm_api_base}")
    print(f"   - API Host: {settings.api_host}:{settings.api_port}")
