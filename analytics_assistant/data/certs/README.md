# SSL 证书统一管理

本目录用于统一管理前后端的 SSL 证书。

## 目录结构

```
analytics_assistant/data/certs/
├── README.md           # 本文档
├── localhost.crt       # 开发环境证书
├── localhost.key       # 开发环境密钥
├── localhost.pfx       # 开发环境 PFX 格式（可选）
├── production.crt      # 生产环境证书（可选）
└── production.key      # 生产环境密钥（可选）
```

## 配置说明

证书配置在 `analytics_assistant/config/app.yaml` 中：

```yaml
ssl:
  # 统一证书存储目录
  cert_dir: analytics_assistant/data/certs
  
  # 证书配置
  certificates:
    # 开发环境
    localhost:
      cert_file: analytics_assistant/data/certs/localhost.crt
      key_file: analytics_assistant/data/certs/localhost.key
      reload_interval: 60  # 热更新检查间隔（秒）
    
    # 生产环境（可选）
    production:
      cert_file: analytics_assistant/data/certs/production.crt
      key_file: analytics_assistant/data/certs/production.key
      reload_interval: 300
  
  # 当前使用的证书
  active_cert: localhost
```

## 证书热更新

系统支持证书热更新，无需重启服务：

1. **检查间隔**：由 `reload_interval` 配置（秒）
2. **自动检测**：系统会定期检查证书文件的修改时间
3. **自动重载**：检测到变化后自动重新加载证书

### 更新证书步骤

1. 将新证书文件复制到 `analytics_assistant/data/certs/` 目录
2. 覆盖原有的 `.crt` 和 `.key` 文件
3. 等待 `reload_interval` 秒后，系统自动重新加载
4. 查看日志确认重载成功

### 禁用热更新

如果不需要热更新，设置 `reload_interval: 0`

## 生成自签名证书

### Windows (PowerShell)

```powershell
# 生成自签名证书
$cert = New-SelfSignedCertificate `
    -DnsName "localhost", "127.0.0.1" `
    -CertStoreLocation "cert:\CurrentUser\My" `
    -NotAfter (Get-Date).AddYears(10) `
    -FriendlyName "Analytics Assistant Dev Cert" `
    -KeyUsageProperty All `
    -KeyUsage CertSign, CRLSign, DigitalSignature

# 导出证书
$certPath = "analytics_assistant/data/certs/localhost.pfx"
$password = ConvertTo-SecureString -String "password" -Force -AsPlainText
Export-PfxCertificate -Cert $cert -FilePath $certPath -Password $password

# 转换为 PEM 格式（需要 OpenSSL）
openssl pkcs12 -in localhost.pfx -out localhost.crt -clcerts -nokeys -password pass:password
openssl pkcs12 -in localhost.pfx -out localhost.key -nocerts -nodes -password pass:password
```

### Linux / macOS

```bash
# 生成私钥
openssl genrsa -out localhost.key 2048

# 生成证书签名请求
openssl req -new -key localhost.key -out localhost.csr \
    -subj "/C=CN/ST=Beijing/L=Beijing/O=Analytics/CN=localhost"

# 生成自签名证书（有效期 10 年）
openssl x509 -req -days 3650 -in localhost.csr -signkey localhost.key -out localhost.crt

# 清理临时文件
rm localhost.csr
```

## 安全注意事项

1. **不要提交私钥到 Git**：`.gitignore` 已配置忽略 `.key` 和 `.pfx` 文件
2. **生产环境使用正式证书**：不要在生产环境使用自签名证书
3. **定期更新证书**：建议在证书过期前 30 天更新
4. **权限控制**：确保证书文件只有必要的用户可读

## 证书验证

使用 Python 脚本验证证书：

```python
from analytics_assistant.src.infra.ssl_manager import get_ssl_manager
from analytics_assistant.src.infra.config import get_config

config = get_config()
ssl_manager = get_ssl_manager(config)

# 验证证书
if ssl_manager.validate_certificate():
    print("证书有效")
    print(ssl_manager.get_cert_info())
else:
    print("证书无效或已过期")
```

## 故障排查

### 证书文件不存在

```
FileNotFoundError: 证书文件不存在: analytics_assistant/data/certs/localhost.crt
```

**解决方法**：
1. 检查证书文件是否存在
2. 检查 `app.yaml` 中的路径配置是否正确
3. 重新生成证书

### 证书已过期

```
WARNING: 证书已过期: analytics_assistant/data/certs/localhost.crt
```

**解决方法**：
1. 生成新的证书
2. 替换旧证书文件
3. 系统会自动重新加载（如果启用了热更新）

### 浏览器不信任证书

**解决方法**：
1. 开发环境：在浏览器中添加例外
2. 生产环境：使用 CA 签发的正式证书
