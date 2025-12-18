"""
应用配置

注意：所有环境变量从项目根目录的 .env 文件读取
"""
import os
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List
from dotenv import load_dotenv

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent

# 从根目录加载 .env 文件
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)


class Settings(BaseSettings):
    """应用配置"""

    # Tableau配置
    tableau_domain: str = os.getenv("TABLEAU_DOMAIN", "")
    tableau_site: str = os.getenv("TABLEAU_SITE", "")
    tableau_api_version: str = os.getenv("TABLEAU_API_VERSION", "3.24")
    tableau_user: str = os.getenv("TABLEAU_USER", "")
    tableau_jwt_client_id: str = os.getenv("TABLEAU_JWT_CLIENT_ID", "")
    tableau_jwt_secret_id: str = os.getenv("TABLEAU_JWT_SECRET_ID", "")
    tableau_jwt_secret: str = os.getenv("TABLEAU_JWT_SECRET", "")
    tableau_pat_name: str = os.getenv("TABLEAU_PAT_NAME", "")
    tableau_pat_secret: str = os.getenv("TABLEAU_PAT_SECRET", "")
    datasource_luid: str = os.getenv("DATASOURCE_LUID", "")
    decimal_precision: int = int(os.getenv("DECIMAL_PRECISION", "2"))

    # LLM配置
    llm_api_base: str = os.getenv("LLM_API_BASE", "http://localhost:8000/v1")
    llm_model_provider: str = os.getenv("LLM_MODEL_PROVIDER", "local")
    llm_api_key: str = os.getenv("LLM_API_KEY", "")
    llm_api_timeout: int = int(os.getenv("LLM_API_TIMEOUT", "30"))
    llm_api_max_tokens: int = int(os.getenv("LLM_API_MAX_TOKENS", "40000"))
    llm_temperature: float = float(os.getenv("LLM_TEMPERATURE", "0.2"))
    tooling_llm_model: str = os.getenv("TOOLING_LLM_MODEL", "")
    embedding_model: str = os.getenv("EMBEDDING_MODEL", "text-embedding-3-small")
    
    # DeepSeek 配置
    deepseek_api_base: str = os.getenv("DEEPSEEK_API_BASE", "https://api.deepseek.com")
    deepseek_api_key: str = os.getenv("DEEPSEEK_API_KEY", "")
    
    # 智谱 AI 配置
    zhipuai_api_key: str = os.getenv("ZHIPUAI_API_KEY", "")
    zhipu_api_base: str = os.getenv("ZHIPU_API_BASE", "https://open.bigmodel.cn/api/paas/v4")

    # LangChain配置
    langchain_tracing_v2: str = os.getenv("LANGCHAIN_TRACING_V2", "false")
    langchain_endpoint: str = os.getenv("LANGCHAIN_ENDPOINT", "https://api.smith.langchain.com")
    langchain_api_key: str = os.getenv("LANGCHAIN_API_KEY", "")
    langchain_project: str = os.getenv("LANGCHAIN_PROJECT", "tableau_agent")
    
    # Store配置
    store_max_search_limit: int = int(os.getenv("STORE_MAX_SEARCH_LIMIT", "4000"))
    store_db_path: str = os.getenv("STORE_DB_PATH", "data/langgraph_store.db")
    store_metadata_ttl: int = int(os.getenv("STORE_METADATA_TTL", "3600"))
    
    # 缓存 TTL 配置
    metadata_cache_ttl: int = int(os.getenv("METADATA_CACHE_TTL", "86400"))
    dimension_hierarchy_cache_ttl: int = int(os.getenv("DIMENSION_HIERARCHY_CACHE_TTL", "86400"))
    data_model_cache_ttl: int = int(os.getenv("DATA_MODEL_CACHE_TTL", "86400"))

    # 任务调度配置
    parallel_upper_limit: int = int(os.getenv("Parallel_Upper_Limit", "3"))
    max_retry_times: int = int(os.getenv("MAX_RETRY_TIMES", "2"))
    max_replan_rounds: int = int(os.getenv("MAX_REPLAN_ROUNDS", "3"))
    max_subtasks_per_round: int = int(os.getenv("MAX_SUBTASKS_PER_ROUND", "10"))

    # 中间件配置
    summarization_token_threshold: int = int(os.getenv("SUMMARIZATION_TOKEN_THRESHOLD", "20000"))
    messages_to_keep: int = int(os.getenv("MESSAGES_TO_KEEP", "10"))
    model_max_retries: int = int(os.getenv("MODEL_MAX_RETRIES", "3"))
    tool_max_retries: int = int(os.getenv("TOOL_MAX_RETRIES", "3"))
    filesystem_token_limit: int = int(os.getenv("FILESYSTEM_TOKEN_LIMIT", "20000"))
    _interrupt_on_str: str = os.getenv("INTERRUPT_ON", "")
    
    @property
    def interrupt_on(self) -> list[str] | None:
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

    # CORS配置
    _cors_origins_str: str = os.getenv("CORS_ORIGINS", "https://localhost:5173,https://127.0.0.1:5173")
    
    @property
    def cors_origins(self) -> List[str]:
        return [origin.strip().replace("'", "").replace('"', "") for origin in self._cors_origins_str.split(",") if origin.strip()]

    # VizQL配置
    vizql_return_format: str = os.getenv("VIZQL_RETURN_FORMAT", "OBJECTS")
    vizql_debug: bool = os.getenv("VIZQL_DEBUG", "false").lower() == "true"
    vizql_disaggregate: bool = os.getenv("VIZQL_DISAGGREGATE", "false").lower() == "true"
    vizql_verify_ssl: bool = os.getenv("VIZQL_VERIFY_SSL", "true").lower() == "true"
    vizql_ca_bundle: str = os.getenv("VIZQL_CA_BUNDLE", "")
    vizql_timeout: int = int(os.getenv("VIZQL_TIMEOUT", "30"))
    vizql_max_retries: int = int(os.getenv("VIZQL_MAX_RETRIES", "3"))

    # 开发配置
    debug: bool = os.getenv("DEBUG", "0") == "1"

    model_config = SettingsConfigDict(case_sensitive=False, extra='ignore')


settings = Settings()
