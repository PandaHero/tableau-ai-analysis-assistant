# 证书迁移指南

## ✅ 已完成的迁移

证书已成功迁移到证书管理器！

### 迁移的文件：
```
cert.pem → tableau_assistant/certs/app_server.pem
key.pem  → tableau_assistant/certs/app_server_key.pem
         → tableau_assistant/certs/app_ca.pem (CA证书)
```

### 备份位置：
```
cert_backup/cert.pem.backup
cert_backup/key.pem.backup
```

## 📝 需要更新的配置

### 1. 更新 .env 文件

将以下行：
```bash
SSL_CERT_FILE=cert.pem
SSL_KEY_FILE=key.pem
FRONTEND_SSL_CERT_FILE=cert.pem
FRONTEND_SSL_KEY_FILE=key.pem
```

改为：
```bash
SSL_CERT_FILE=tableau_assistant/certs/app_server.pem
SSL_KEY_FILE=tableau_assistant/certs/app_server_key.pem
FRONTEND_SSL_CERT_FILE=tableau_assistant/certs/app_server.pem
FRONTEND_SSL_KEY_FILE=tableau_assistant/certs/app_server_key.pem
```

### 2. 测试应用启动

```bash
python start.py
```

应用会自动使用新的证书路径。

## 🔄 未来迁移到公司证书

### 方式 1: 通过代码（推荐）

在 start.py 或应用初始化代码中添加：

```python
from tableau_assistant.cert_manager import CertificateManager

manager = CertificateManager()

# 检查是否配置了公司证书
import os
if os.getenv("APP_CERT_SOURCE") == "company":
    company_cert = os.getenv("COMPANY_CERT_FILE")
    company_key = os.getenv("COMPANY_KEY_FILE")
    company_ca = os.getenv("COMPANY_CA_BUNDLE")
    
    if company_cert and company_key:
        manager.migrate_to_company_certificates(
            cert_file=company_cert,
            key_file=company_key,
            ca_bundle=company_ca
        )
        print("✓ 已切换到公司证书")
```

### 方式 2: 通过环境变量

在 .env 文件中添加：

```bash
# 证书源配置
APP_CERT_SOURCE=company

# 公司证书路径
COMPANY_CERT_FILE=/path/to/company/cert.pem
COMPANY_KEY_FILE=/path/to/company/key.pem
COMPANY_CA_BUNDLE=/path/to/company/ca.pem

# 更新应用证书路径（指向公司证书）
SSL_CERT_FILE=/path/to/company/cert.pem
SSL_KEY_FILE=/path/to/company/key.pem
```

### 方式 3: 通过 CLI

```bash
# 使用证书管理器 CLI
python -m tableau_assistant.cert_manager.cli migrate \
    --cert-file /path/to/company/cert.pem \
    --key-file /path/to/company/key.pem \
    --ca-bundle /path/to/company/ca.pem
```

## 🎯 自动管理（像 Tableau 一样）

证书管理器会在应用启动时自动：

1. ✅ **检测证书** - 检查证书是否存在
2. ✅ **验证证书** - 验证证书有效性和过期时间
3. ✅ **自动获取** - 第三方服务证书自动获取（如智谱 AI）
4. ✅ **过期警告** - 证书即将过期时自动警告
5. ✅ **热重载** - 证书更新后自动重载

### 示例：智谱 AI 证书自动管理

```python
# 在 tableau_assistant/__init__.py 中已经实现
# 应用启动时自动执行：

from tableau_assistant.cert_manager import CertificateManager

manager = CertificateManager()

# 自动注册和获取智谱 AI 证书
manager.register_preconfigured_services(["zhipu-ai"])

# 之后所有代码自动使用正确的证书，无需手动管理
```

## 📊 当前证书状态

运行以下命令查看所有证书状态：

```bash
python -m tableau_assistant.cert_manager.cli status
```

## 🔧 证书续期

### 自签名证书续期

```python
from tableau_assistant.cert_manager import ApplicationCertificateProvider

provider = ApplicationCertificateProvider()

# 重新生成证书（自动续期）
cert_file, key_file = provider.generate_self_signed(
    common_name="localhost",
    validity_days=365
)

print(f"✓ 证书已续期: {cert_file}")
```

### 公司证书续期

公司证书由 IT 部门管理，你只需要：

1. 从 IT 部门获取新证书
2. 更新环境变量中的路径
3. 重启应用（或调用 `manager.reload_certificates()`）

## ✨ 总结

- ✅ 证书已迁移到统一目录
- ✅ 所有证书集中管理
- ✅ 自动验证和警告
- ✅ 轻松切换到公司证书
- ✅ 无需手动维护

**下一步：更新 .env 文件中的证书路径，然后测试应用启动。**
