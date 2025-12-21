# Design Document

## Introduction

本设计文档描述证书管理器增强功能的技术架构，实现从 `cert_config.yaml` 加载配置、支持公司证书和自签名证书、第三方服务证书自动获取、以及与启动脚本的集成。

## Architecture Overview

```
┌─────────────────────────────────────────────────────────────────────────┐
│                           start.py                                       │
│                    (启动脚本 - 调用证书管理器)                              │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                      CertificateManager (增强版)                          │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │  ConfigLoader   │  │ SelfSignedGen   │  │    HotReloader          │  │
│  │  (YAML配置加载)  │  │ (自签名证书生成) │  │    (证书热更新)          │  │
│  └────────┬────────┘  └────────┬────────┘  └───────────┬─────────────┘  │
│           │                    │                       │                 │
│           ▼                    ▼                       ▼                 │
│  ┌─────────────────────────────────────────────────────────────────┐    │
│  │                    CertificateStore                              │    │
│  │  (证书存储: 应用证书 + 服务证书)                                    │    │
│  └─────────────────────────────────────────────────────────────────┘    │
│           │                    │                       │                 │
│           ▼                    ▼                       ▼                 │
│  ┌─────────────────┐  ┌─────────────────┐  ┌─────────────────────────┐  │
│  │ CertValidator   │  │ CertFetcher     │  │   ServiceRegistry       │  │
│  │ (证书验证)       │  │ (证书获取)       │  │   (服务注册)             │  │
│  └─────────────────┘  └─────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
                                    │
                                    ▼
┌─────────────────────────────────────────────────────────────────────────┐
│                         cert_config.yaml                                 │
│  ┌─────────────┐  ┌─────────────────────┐  ┌─────────────────────────┐  │
│  │ 全局设置     │  │ application 配置    │  │ services 配置           │  │
│  │ cert_dir    │  │ source: company/    │  │ deepseek, zhipu,       │  │
│  │ verify_ssl  │  │   self-signed       │  │ tableau, ...           │  │
│  │ warning_days│  │ company: {...}      │  │ auto_fetch: true/false │  │
│  └─────────────┘  └─────────────────────┘  └─────────────────────────┘  │
└─────────────────────────────────────────────────────────────────────────┘
```

## 配置管理策略

### 配置来源

所有证书配置统一由 `cert_config.yaml` 管理：

1. **`cert_config.yaml`** - 主要配置来源
2. **环境变量** - 支持在 YAML 中引用 `${VAR_NAME}`
3. **默认值** - 配置缺失时使用

### 优点

- 证书配置集中管理，与应用配置分离
- YAML 支持复杂嵌套结构
- 支持环境变量引用，灵活适配不同环境
- 配置文件可版本控制（敏感路径用环境变量）

## Component Interfaces

### 1. ConfigLoader (新增)

负责加载和解析 `cert_config.yaml` 配置文件：

```python
@dataclass
class CertConfigData:
    """证书配置数据结构"""
    cert_dir: str
    verify_ssl: bool
    warning_days: int
    application: ApplicationConfig
    services: Dict[str, ServiceCertConfig]

@dataclass
class ApplicationConfig:
    """应用证书配置"""
    source: Literal["self-signed", "company"]
    backend: BackendCertConfig
    ca_bundle: str
    company: Optional[CompanyCertConfig]

@dataclass
class BackendCertConfig:
    """后端证书配置"""
    cert_file: str
    key_file: str

@dataclass
class CompanyCertConfig:
    """公司证书配置"""
    cert_file: str  # 本地路径
    key_file: str   # 本地路径
    ca_bundle: str  # 本地路径
    auto_fetch: bool = False  # 是否自动从公司服务器拉取
    fetch_url: Optional[str] = None  # 公司证书服务器 URL
    auto_refresh: bool = False  # 是否自动刷新
    refresh_interval: int = 86400  # 刷新间隔（秒），默认 24 小时

@dataclass
class ServiceCertConfig:
    """服务证书配置"""
    hostname: str
    port: int = 443
    ca_bundle: str = ""
    auto_fetch: Union[bool, str] = False  # True | False | "auto"
    use_system_certs: bool = False  # 是否使用系统证书（Tableau Cloud）

class ConfigLoader:
    """证书配置加载器"""
    
    def __init__(self, config_path: str = "cert_config.yaml"):
        """初始化配置加载器"""
        pass
    
    def load(self) -> CertConfigData:
        """加载配置文件"""
        pass
    
    def _expand_env_vars(self, value: str) -> str:
        """展开环境变量引用 ${VAR_NAME}"""
        pass
    
    def _validate_schema(self, data: dict) -> None:
        """验证配置结构"""
        pass
```

### 2. SelfSignedGenerator (新增)

负责生成自签名证书（仅用于开发环境）。

```python
class SelfSignedGenerator:
    """自签名证书生成器"""
    
    def __init__(self, cert_dir: str, validity_days: int = 365):
        """初始化生成器"""
        pass
    
    def generate(
        self,
        hostnames: List[str] = None,
        force: bool = False
    ) -> Dict[str, str]:
        """
        生成自签名证书
        
        Returns:
            {
                "ca_cert": "path/to/ca.pem",
                "server_cert": "path/to/server.pem",
                "server_key": "path/to/server_key.pem"
            }
        """
        pass
    
    def _generate_ca(self) -> Tuple[crypto.X509, crypto.PKey]:
        """生成 CA 证书"""
        pass
    
    def _generate_server_cert(
        self,
        ca_cert: crypto.X509,
        ca_key: crypto.PKey,
        hostnames: List[str]
    ) -> Tuple[crypto.X509, crypto.PKey]:
        """生成服务器证书"""
        pass
    
    def check_existing(self) -> Optional[Dict[str, str]]:
        """检查现有证书是否有效"""
        pass
```

### 3. CompanyCertFetcher (新增)

从公司证书服务器拉取证书。

```python
class CompanyCertFetcher:
    """公司证书拉取器"""
    
    def __init__(
        self,
        fetch_url: str,
        cert_dir: str,
        timeout: int = 30
    ):
        """初始化拉取器"""
        pass
    
    def fetch(self) -> Dict[str, str]:
        """
        从公司服务器拉取证书
        
        支持的 URL 格式:
        - https://cert-server.company.com/certs/app
        - file:///shared/certs/app
        - smb://fileserver/certs/app (Windows)
        
        Returns:
            {
                "cert_file": "path/to/cert.pem",
                "key_file": "path/to/key.pem",
                "ca_bundle": "path/to/ca.pem"
            }
        """
        pass
    
    def _fetch_from_https(self, url: str) -> bytes:
        """从 HTTPS 端点获取证书"""
        pass
    
    def _fetch_from_file(self, path: str) -> bytes:
        """从文件共享路径获取证书"""
        pass
    
    def check_for_updates(self) -> bool:
        """检查服务器上是否有更新的证书"""
        pass
```

### 4. HotReloader (新增)

监控证书文件变化并触发重新加载，支持定期从公司服务器刷新。

```python
class HotReloader:
    """证书热更新器"""
    
    def __init__(
        self,
        watch_paths: List[str],
        callback: Callable[[], None],
        debounce_seconds: float = 2.0,
        company_fetcher: Optional[CompanyCertFetcher] = None,
        refresh_interval: int = 86400
    ):
        """初始化热更新器"""
        pass
    
    def start(self) -> None:
        """启动文件监控和定期刷新"""
        pass
    
    def stop(self) -> None:
        """停止文件监控和定期刷新"""
        pass
    
    def _on_file_change(self, event) -> None:
        """文件变化回调"""
        pass
    
    def _validate_and_reload(self) -> bool:
        """验证新证书并重新加载"""
        pass
    
    def _schedule_refresh(self) -> None:
        """调度定期刷新任务"""
        pass
    
    def _refresh_from_company(self) -> bool:
        """从公司服务器刷新证书"""
        pass
```

### 5. CertificateManager (增强)

统一的证书管理入口，整合所有功能。

```python
class CertificateManager:
    """增强版证书管理器"""
    
    def __init__(self, config_path: str = "cert_config.yaml"):
        """
        初始化证书管理器
        
        1. 加载 cert_config.yaml
        2. 初始化各子组件
        3. 准备应用证书
        4. 获取服务证书
        """
        pass
    
    def initialize(self) -> bool:
        """
        初始化证书（启动时调用）
        
        1. 根据 source 准备应用证书
        2. 自动获取 auto_fetch=true 的服务证书
        3. 验证所有证书
        """
        pass
    
    def get_app_ssl_config(self) -> Dict[str, str]:
        """
        获取应用 SSL 配置（供 uvicorn 使用）
        
        Returns:
            {
                "ssl_certfile": "path/to/cert.pem",
                "ssl_keyfile": "path/to/key.pem"
            }
        """
        pass
    
    def get_service_ca_bundle(self, service_id: str) -> Optional[str]:
        """获取服务的 CA 证书路径"""
        pass
    
    def get_status(self) -> Dict[str, Any]:
        """
        获取所有证书状态
        
        Returns:
            {
                "application": {
                    "source": "company",
                    "cert_file": "...",
                    "valid": True,
                    "expires": "2025-12-31",
                    "days_until_expiry": 365
                },
                "services": {
                    "deepseek": {"valid": True, ...},
                    "tableau": {"valid": True, ...}
                }
            }
        """
        pass
    
    def start_hot_reload(self, callback: Callable = None) -> None:
        """启动证书热更新"""
        pass
    
    def stop_hot_reload(self) -> None:
        """停止证书热更新"""
        pass
    
    def export_to_env(self) -> Dict[str, str]:
        """
        导出证书路径到环境变量格式
        
        Returns:
            {
                "SSL_CERT_FILE": "...",
                "SSL_KEY_FILE": "...",
                "REQUESTS_CA_BUNDLE": "..."
            }
        """
        pass
```

## Data Models

### cert_config.yaml 完整结构

```yaml
# ============================================================
# 证书管理器配置文件
# 所有证书配置统一在此管理
# ============================================================

# 全局设置
cert_dir: "tableau_assistant/certs"  # 证书存储目录
verify_ssl: true                      # 是否启用 SSL 验证
warning_days: 30                      # 证书过期前多少天开始警告

# ============================================================
# 应用证书配置（用于后端 HTTPS 服务器）
# ============================================================
application:
  source: "company"  # 证书来源: "self-signed" | "company"
  
  # 后端服务器证书（相对于 cert_dir）
  backend:
    cert_file: "app_server.pem"
    key_file: "app_server_key.pem"
  
  ca_bundle: "app_ca.pem"
  
  # 公司证书配置（当 source: "company" 时使用）
  company:
    # 本地路径（手动管理）
    cert_file: "${COMPANY_CERT_FILE}"  # 可用环境变量
    key_file: "${COMPANY_KEY_FILE}"
    ca_bundle: "${COMPANY_CA_BUNDLE}"
    
    # 自动拉取配置
    auto_fetch: true
    fetch_url: "https://cert-server.company.com/api/certs/tableau-assistant"
    # 或使用文件共享: "file:///shared/certs/tableau-assistant"
    
    # 自动刷新配置
    auto_refresh: true
    refresh_interval: 86400  # 刷新间隔（秒），默认 24 小时

# ============================================================
# 第三方服务证书配置
# ============================================================
services:
  deepseek:
    hostname: "api.deepseek.com"
    port: 443
    ca_bundle: "deepseek_full_chain.pem"
    auto_fetch: true
  
  zhipu-ai:
    hostname: "open.bigmodel.cn"
    port: 443
    ca_bundle: "zhipu_full_chain.pem"
    auto_fetch: true
  
  # Tableau 配置 - 支持 Cloud 和 Server 两种模式
  tableau:
    hostname: "${TABLEAU_DOMAIN}"  # 从环境变量读取
    port: 443
    ca_bundle: "tableau_cert.pem"
    # auto_fetch 智能处理：
    # - Tableau Cloud (*.online.tableau.com): 使用系统证书，跳过获取
    # - Tableau Server (内部部署): 自动获取服务器证书
    auto_fetch: "auto"  # "auto" | true | false
```

### Tableau 证书处理逻辑

```python
def _handle_tableau_cert(self, config: ServiceCertConfig) -> None:
    """智能处理 Tableau 证书"""
    hostname = config.hostname
    
    # Tableau Cloud - 使用系统证书
    if "online.tableau.com" in hostname.lower():
        logger.info("Tableau Cloud 检测到，使用系统证书库")
        config.use_system_certs = True
        return
    
    # Tableau Server - 自动获取证书
    if config.auto_fetch == "auto" or config.auto_fetch == True:
        logger.info(f"Tableau Server 检测到，获取证书: {hostname}")
        self._fetch_service_certificate(config)
```

### CertificateStatus

```python
@dataclass
class CertificateStatus:
    """证书状态"""
    cert_type: str  # "application" | "service"
    source: str     # "company" | "self-signed" | "fetched"
    cert_file: str
    valid: bool
    expires: Optional[datetime]
    days_until_expiry: Optional[int]
    warning: bool
    errors: List[str]
```

## Correctness Properties

### Property 1: 配置加载正确性
- 配置文件必须存在且格式正确
- 环境变量引用必须正确展开
- 缺失的可选字段使用默认值

### Property 2: 公司证书完整性
- 当 `source: company` 时，三个文件必须全部存在
- 证书和私钥必须匹配
- 证书必须在有效期内

### Property 3: 自签名证书有效性
- 生成的证书必须包含正确的 SAN (Subject Alternative Names)
- CA 证书必须能验证服务器证书
- 证书有效期必须正确设置

### Property 4: 服务证书获取可靠性
- 网络失败不应阻止系统启动
- 已存在的有效证书应被复用
- 获取失败应记录详细错误

### Property 5: 热更新安全性
- 新证书必须先验证再加载
- 无效证书不应替换有效证书
- 文件变化应防抖处理

## Error Handling

| 错误场景 | 处理策略 | 用户提示 |
|---------|---------|---------|
| cert_config.yaml 不存在 | 回退到 cert_config.example.yaml | 警告：使用示例配置 |
| YAML 格式错误 | 抛出 ConfigError | 错误：配置文件格式无效 |
| 公司证书文件缺失 | 阻止启动 | 错误：公司证书文件不存在: {path} |
| 证书私钥不匹配 | 阻止启动 | 错误：证书和私钥不匹配 |
| 证书已过期 | 阻止启动 | 错误：证书已过期 |
| 证书即将过期 | 警告但继续 | 警告：证书将在 {days} 天后过期 |
| 服务证书获取失败 | 记录错误，继续启动 | 警告：无法获取 {service} 证书 |
| 自签名生成失败 | 阻止启动 | 错误：无法生成自签名证书 |
| 热更新验证失败 | 保持旧证书 | 警告：新证书无效，保持原证书 |

## Testing Strategy

### 单元测试

1. **ConfigLoader 测试**
   - 测试 YAML 解析
   - 测试环境变量展开
   - 测试配置验证
   - 测试默认值处理

2. **SelfSignedGenerator 测试**
   - 测试证书生成
   - 测试 SAN 配置
   - 测试证书验证
   - 测试过期检测

3. **HotReloader 测试**
   - 测试文件监控
   - 测试防抖逻辑
   - 测试回调触发

### 集成测试

1. **完整流程测试**
   - 测试公司证书模式启动
   - 测试自签名证书模式启动
   - 测试服务证书自动获取

2. **start.py 集成测试**
   - 测试证书管理器集成
   - 测试 SSL 配置传递
   - 测试错误处理

### 手动测试

1. 使用公司证书启动生产环境
2. 使用自签名证书启动开发环境
3. 修改证书文件触发热更新
4. 检查 `/api/health` 证书状态

## Dependencies

### 新增依赖

```
PyYAML>=6.0          # YAML 解析
cryptography>=41.0   # 证书生成
watchdog>=3.0        # 文件监控
```

### 现有依赖（已安装）

```
ssl                  # 标准库
socket               # 标准库
pathlib              # 标准库
```
