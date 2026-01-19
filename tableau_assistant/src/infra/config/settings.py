"""
应用配置

注意：所有环境变量从项目根目录的 .env 文件读取
"""
import os
from dataclasses import dataclass
from pathlib import Path
from pydantic_settings import BaseSettings, SettingsConfigDict
from typing import List, Optional
from dotenv import load_dotenv

# 获取项目根目录
PROJECT_ROOT = Path(__file__).parent.parent.parent.parent.parent

# 从根目录加载 .env 文件
env_path = PROJECT_ROOT / ".env"
if env_path.exists():
    load_dotenv(env_path)


@dataclass
class TableauConfig:
    """Tableau 配置"""
    domain: str
    site: str
    api_version: str
    user: str
    jwt_client_id: str
    jwt_secret_id: str
    jwt_secret: str
    pat_name: str
    pat_secret: str


class Settings(BaseSettings):
    """应用配置"""

    # Tableau 配置
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
    
    def get_tableau_config(self) -> TableauConfig:
        """获取 Tableau 配置"""
        return TableauConfig(
            domain=self.tableau_domain,
            site=self.tableau_site,
            api_version=self.tableau_api_version,
            user=self.tableau_user,
            jwt_client_id=self.tableau_jwt_client_id,
            jwt_secret_id=self.tableau_jwt_secret_id,
            jwt_secret=self.tableau_jwt_secret,
            pat_name=self.tableau_pat_name,
            pat_secret=self.tableau_pat_secret,
        )

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
    
    # 自定义 LLM 配置（公司内部部署的模型）
    custom_llm_api_base: str = os.getenv("CUSTOM_LLM_API_BASE", "") or os.getenv("DEEPSEEK_R1_API_BASE", "")
    custom_llm_api_key: str = os.getenv("CUSTOM_LLM_API_KEY", "") or os.getenv("DEEPSEEK_R1_API_KEY", "")
    custom_llm_api_endpoint: str = os.getenv("CUSTOM_LLM_API_ENDPOINT", "/api/v1/offline/deep/think")
    custom_llm_model_name: str = os.getenv("CUSTOM_LLM_MODEL_NAME", "deepseek-r1")
    
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
    field_mapping_cache_ttl: int = int(os.getenv("FIELD_MAPPING_CACHE_TTL", "86400"))
    schema_linking_cache_ttl: int = int(os.getenv("SCHEMA_LINKING_CACHE_TTL", "3600"))
    
    # LLM 超时配置

    llm_request_timeout: int = int(os.getenv("LLM_REQUEST_TIMEOUT", "120"))

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
    
    # SemanticParser ReAct error handling configuration
    semantic_parser_max_retries: int = int(os.getenv("SEMANTIC_PARSER_MAX_RETRIES", "3"))
    semantic_parser_max_semantic_retries: int = int(os.getenv("SEMANTIC_PARSER_MAX_SEMANTIC_RETRIES", "2"))
    
    # SemanticParser token limits (Requirements 0.4)
    semantic_parser_max_history_tokens: int = int(os.getenv("SEMANTIC_PARSER_MAX_HISTORY_TOKENS", "2000"))
    semantic_parser_max_schema_tokens: int = int(os.getenv("SEMANTIC_PARSER_MAX_SCHEMA_TOKENS", "3000"))
    
    # SemanticParser format retry limit (Requirements 0.6)
    semantic_parser_max_format_retries: int = int(os.getenv("SEMANTIC_PARSER_MAX_FORMAT_RETRIES", "2"))
    
    # Schema Linking configuration (Requirements 0.13)
    schema_linking_min_candidates: int = int(os.getenv("SCHEMA_LINKING_MIN_CANDIDATES", "1"))
    schema_linking_min_confidence: float = float(os.getenv("SCHEMA_LINKING_MIN_CONFIDENCE", "0.5"))
    schema_linking_timeout_ms: int = int(os.getenv("SCHEMA_LINKING_TIMEOUT_MS", "2000"))
    schema_linking_min_term_hit_ratio: float = float(os.getenv("SCHEMA_LINKING_MIN_TERM_HIT_RATIO", "0.3"))
    schema_linking_min_score_spread: float = float(os.getenv("SCHEMA_LINKING_MIN_SCORE_SPREAD", "0.1"))
    schema_linking_min_avg_score: float = float(os.getenv("SCHEMA_LINKING_MIN_AVG_SCORE", "0.4"))
    
    # IntentRouter configuration (Requirements 0.12)
    intent_router_l1_confidence_threshold: float = float(os.getenv("INTENT_ROUTER_L1_CONFIDENCE_THRESHOLD", "0.8"))
    
    # Preprocess component configuration (Phase 1)
    preprocess_min_term_length: int = int(os.getenv("PREPROCESS_MIN_TERM_LENGTH", "2"))
    preprocess_min_bigram_length: int = int(os.getenv("PREPROCESS_MIN_BIGRAM_LENGTH", "3"))
    preprocess_max_bigram_length: int = int(os.getenv("PREPROCESS_MAX_BIGRAM_LENGTH", "8"))
    
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
