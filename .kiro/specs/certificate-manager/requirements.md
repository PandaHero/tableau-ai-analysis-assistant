# Requirements Document

## Introduction

完善证书管理器功能，支持从 `cert_config.yaml` 配置文件加载配置，实现公司证书和自签名证书的自动管理，并与启动脚本集成。系统需要支持生产环境的公司证书部署和开发环境的自签名证书自动生成。

## Glossary

- **Certificate_Manager**: 证书管理器，统一管理 SSL/TLS 证书的获取、生成、验证和配置
- **Config_Loader**: 配置加载器，负责读取和解析 `cert_config.yaml` 配置文件
- **App_Certificate**: 应用服务器证书，用于后端 HTTPS 服务器，包含证书文件和私钥
- **Service_Certificate**: 第三方服务证书，用于验证外部 API 服务的 SSL 连接
- **Self_Signed_Generator**: 自签名证书生成器，用于开发环境自动生成证书
- **Hot_Reloader**: 热更新器，监控证书文件变化并自动重新加载

## Requirements

### Requirement 1: 配置管理

**User Story:** As a system administrator, I want the certificate manager to load all configuration from `cert_config.yaml`, so that I can manage certificates in a single dedicated configuration file.

#### Acceptance Criteria

1. WHEN the Certificate_Manager initializes, THE Config_Loader SHALL read and parse `cert_config.yaml` from project root
2. WHEN `cert_config.yaml` does not exist, THE Config_Loader SHALL fall back to `cert_config.example.yaml` with a warning
3. THE Config_Loader SHALL expand environment variable references like `${TABLEAU_DOMAIN}` in YAML values
4. THE Config_Loader SHALL validate configuration schema and report errors for invalid configurations
5. THE Config_Loader SHALL support all certificate settings including application, company, and service certificates

### Requirement 2: 公司证书支持

**User Story:** As a system administrator, I want to use company-issued certificates for production deployment, so that the system meets enterprise security requirements.

#### Acceptance Criteria

1. WHEN `application.source` is "company", THE Certificate_Manager SHALL load certificates from paths specified in `application.company`
2. WHEN loading company certificates, THE Certificate_Manager SHALL validate that cert_file, key_file, and ca_bundle all exist
3. WHEN company certificate files are missing, THE Certificate_Manager SHALL report a clear error with the missing file paths
4. THE Certificate_Manager SHALL verify that the certificate and private key match
5. THE Certificate_Manager SHALL check certificate expiration and warn if expiring within `warning_days`
6. WHEN `application.company.auto_fetch` is true, THE Certificate_Manager SHALL fetch certificates from the company certificate server
7. THE Certificate_Manager SHALL support fetching company certificates via HTTPS endpoint or file share path
8. WHEN company certificate fetch fails, THE Certificate_Manager SHALL fall back to local certificate files if available

### Requirement 3: 自签名证书生成

**User Story:** As a developer, I want self-signed certificates to be automatically generated for development, so that I can run HTTPS locally without manual certificate setup.

#### Acceptance Criteria

1. WHEN `application.source` is "self-signed" and certificates do not exist, THE Self_Signed_Generator SHALL create new certificates
2. THE Self_Signed_Generator SHALL generate a CA certificate, server certificate, and private key
3. THE Self_Signed_Generator SHALL set certificate validity to 365 days by default
4. THE Self_Signed_Generator SHALL include localhost, 127.0.0.1, and configurable hostnames in Subject Alternative Names
5. WHEN self-signed certificates already exist and are valid, THE Self_Signed_Generator SHALL reuse them
6. WHEN self-signed certificates are expired, THE Self_Signed_Generator SHALL regenerate them automatically

### Requirement 4: 第三方服务证书自动获取

**User Story:** As a system administrator, I want third-party service certificates to be automatically fetched, so that SSL connections to external APIs work without manual certificate management.

#### Acceptance Criteria

1. WHEN a service has `auto_fetch: true`, THE Certificate_Manager SHALL fetch its certificate on initialization
2. WHEN fetching service certificates, THE Certificate_Manager SHALL save them to the configured `cert_dir`
3. WHEN a service certificate already exists and is valid, THE Certificate_Manager SHALL skip fetching
4. WHEN certificate fetch fails, THE Certificate_Manager SHALL log an error and continue with other services
5. THE Certificate_Manager SHALL support fetching certificates from services with non-standard ports

### Requirement 5: 启动脚本集成

**User Story:** As a developer, I want the startup script to use the certificate manager, so that certificate configuration is centralized and consistent.

#### Acceptance Criteria

1. WHEN `start.py` runs, THE System SHALL initialize Certificate_Manager before starting servers
2. THE Certificate_Manager SHALL provide SSL certificate and key paths for uvicorn configuration
3. WHEN certificates are not ready, THE System SHALL block startup and report the issue
4. THE System SHALL remove direct SSL_CERT_FILE checks from `start.py` and use Certificate_Manager instead
5. THE Certificate_Manager SHALL export paths to environment variables for frontend (Vite) compatibility

### Requirement 6: 证书热更新

**User Story:** As a system administrator, I want certificates to be reloaded without restarting the server, so that certificate rotation does not cause downtime.

#### Acceptance Criteria

1. THE Hot_Reloader SHALL monitor certificate files for changes using file system events
2. WHEN a certificate file changes, THE Hot_Reloader SHALL validate the new certificate before reloading
3. WHEN the new certificate is valid, THE Hot_Reloader SHALL trigger a reload callback
4. WHEN the new certificate is invalid, THE Hot_Reloader SHALL log an error and keep using the old certificate
5. THE Hot_Reloader SHALL debounce rapid file changes to avoid excessive reloads
6. WHEN `application.company.auto_refresh` is true, THE Hot_Reloader SHALL periodically check for certificate updates from company server
7. THE Hot_Reloader SHALL support configurable refresh interval (default: 24 hours)
8. WHEN company certificate is updated on server, THE Hot_Reloader SHALL fetch and apply the new certificate

### Requirement 7: 证书状态报告

**User Story:** As a system administrator, I want to check certificate status through an API, so that I can monitor certificate health.

#### Acceptance Criteria

1. THE Certificate_Manager SHALL provide a `get_status()` method returning all certificate statuses
2. THE status report SHALL include: certificate type, expiration date, days until expiry, validation status
3. WHEN certificates are expiring within `warning_days`, THE status SHALL include a warning flag
4. THE System SHALL expose certificate status through `/api/health` endpoint

