# SSL证书目录

此目录用于存储项目所需的SSL/TLS证书文件。

## 目录结构

```
tableau_assistant/certs/
├── README.md                           # 本文件
├── deepseek_full_chain.pem            # DeepSeek完整证书链
├── deepseek_server.pem                # DeepSeek服务器证书
├── geotrust_intermediate.pem          # GeoTrust中间证书
└── tableau_*.pem                      # Tableau Server证书
```

## 证书文件说明

### DeepSeek API证书

- **deepseek_full_chain.pem** - 完整证书链,包含服务器证书和中间证书
  - 用途: 验证DeepSeek API的SSL连接
  - 包含: 服务器证书 + 中间证书
  - 推荐使用此文件

- **deepseek_server.pem** - 服务器证书
  - 用途: 仅包含DeepSeek的服务器证书
  - 不推荐单独使用

- **geotrust_intermediate.pem** - 中间证书
  - 用途: GeoTrust TLS RSA CA G1中间证书
  - 颁发者: DigiCert Global Root G2

### Tableau Server证书

- **tableau_*.pem** - Tableau服务器证书
  - 命名格式: tableau_{hostname}_cert.pem
  - 用途: 验证Tableau Server的SSL连接

## 获取证书

### 使用命令行工具

```bash
# 获取DeepSeek证书
python -m cert_manager.cli fetch deepseek

# 获取Tableau证书
python -m cert_manager.cli fetch tableau --tableau-domain https://your-tableau-server.com

# 获取其他服务器证书
python -m cert_manager.cli fetch api.example.com
```

### 使用Python API

```python
from cert_manager import CertificateManager

manager = CertificateManager()

# 获取DeepSeek证书
manager.fetch_deepseek_certificates()

# 获取Tableau证书
manager.fetch_tableau_certificates("https://your-tableau-server.com")
```

## 证书验证

```bash
# 验证证书文件
python -m cert_manager.cli validate

# 验证SSL连接
python -m cert_manager.cli validate --connection api.deepseek.com

# 验证证书链
python -m cert_manager.cli validate --chain

# 查看所有证书状态
python -m cert_manager.cli status
```

## 环境变量配置

```bash
# 启用SSL验证
LLM_VERIFY_SSL=true

# 指定证书文件(可选)
LLM_CA_BUNDLE=tableau_assistant/certs/deepseek_full_chain.pem

# 证书目录(可选)
CERT_MANAGER_DIR=tableau_assistant/certs
```

## 证书更新

证书会定期过期,建议:

1. **监控证书过期时间**
   ```bash
   python -m cert_manager.cli status
   ```

2. **定期更新证书**
   ```bash
   # 强制重新获取
   python -m cert_manager.cli fetch deepseek --force
   python -m cert_manager.cli fetch tableau --tableau-domain https://your-server.com --force
   ```

3. **自动化更新**
   - 在CI/CD流程中添加证书更新步骤
   - 使用cron job定期检查和更新

## 安全注意事项

1. **权限设置**
   ```bash
   # 设置适当的文件权限
   chmod 644 *.pem
   ```

2. **版本控制**
   - 证书文件可以提交到版本控制系统(公开证书)
   - 私钥文件不应提交到版本控制系统

3. **备份**
   - 定期备份证书文件
   - 记录证书获取时间和来源

## 故障排查

### 证书验证失败

```bash
# 检查证书文件
ls -la tableau_assistant/certs/

# 验证证书
python -m cert_manager.cli validate

# 重新获取证书
python -m cert_manager.cli fetch deepseek --force
```

### 证书过期

```bash
# 查看证书状态
python -m cert_manager.cli status

# 更新证书
python -m cert_manager.cli fetch deepseek --force
```

### 找不到证书文件

```bash
# 检查环境变量
echo $LLM_CA_BUNDLE
echo $CERT_MANAGER_DIR

# 查看配置
python -m cert_manager.cli config
```

## 相关文档

- [Certificate Manager README](../../cert_manager/README.md)
- [生产环境部署指南](../../PRODUCTION_DEPLOYMENT.md)
- [SSL配置指南](../../DEPLOYMENT_SSL_GUIDE.md)
