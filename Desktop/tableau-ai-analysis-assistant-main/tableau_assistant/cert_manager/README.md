# Certificate Manager

生产级别的SSL/TLS证书管理包,提供证书获取、验证、存储和配置功能。

## 特性

- ✅ 自动获取和更新证书
- ✅ 证书验证和过期检查
- ✅ 多环境配置支持(开发/测试/生产)
- ✅ 证书链完整性验证
- ✅ 统一的SSL配置接口
- ✅ 支持多种HTTP客户端库(requests, httpx, aiohttp)
- ✅ 命令行工具
- ✅ 详细的日志记录

## 安装

```bash
# 基础安装
pip install -r requirements.txt

# 完整安装(包含证书验证功能)
pip install pyopenssl
```

## 快速开始

### 1. 作为Python包使用

```python
from cert_manager import CertificateManager, get_ssl_config

# 初始化证书管理器
manager = CertificateManager(cert_dir="certs")

# 获取DeepSeek证书
manager.fetch_deepseek_certificates()

# 验证证书
result = manager.validate_certificate()
print(f"证书有效: {result['valid']}")

# 获取SSL配置
ssl_config = get_ssl_config()

# 在requests中使用
import requests
response = requests.get(
    "https://api.deepseek.com",
    **ssl_config.requests_kwargs()
)

# 在httpx中使用
import httpx
client = httpx.Client(**ssl_config.httpx_client_kwargs())
response = client.get("https://api.deepseek.com")

# 在aiohttp中使用
import aiohttp
async with aiohttp.ClientSession() as session:
    async with session.get(
        "https://api.deepseek.com",
        **ssl_config.aiohttp_kwargs()
    ) as response:
        data = await response.json()
```

### 2. 使用命令行工具

```bash
# 获取DeepSeek证书
python -m cert_manager.cli fetch deepseek

# 获取Tableau Server证书
python -m cert_manager.cli fetch tableau --tableau-domain https://tableau.company.com

# 获取指定服务器证书
python -m cert_manager.cli fetch api.example.com --port 443

# 验证证书文件
python -m cert_manager.cli validate

# 验证SSL连接
python -m cert_manager.cli validate --connection api.deepseek.com

# 验证证书链
python -m cert_manager.cli validate --chain

# 查看状态
python -m cert_manager.cli status

# 查看配置
python -m cert_manager.cli config
```

## 环境变量配置

```bash
# 启用/禁用SSL验证
LLM_VERIFY_SSL=true  # true(默认) 或 false

# 自定义证书文件路径
LLM_CA_BUNDLE=/path/to/cert.pem

# 证书目录
CERT_MANAGER_DIR=certs

# 启用调试日志
CERT_MANAGER_DEBUG=true
```

## 使用场景

### 场景1: 开发环境(Windows)

```python
# 使用系统证书,无需额外配置
from cert_manager import get_ssl_config

ssl_config = get_ssl_config()
# 自动使用Windows系统证书库
```

### 场景2: 生产环境(CentOS) - 系统证书

```bash
# 更新系统证书
sudo yum update ca-certificates -y
sudo update-ca-trust extract

# 配置环境变量
export LLM_VERIFY_SSL=true
# LLM_CA_BUNDLE 留空,使用系统证书
```

```python
from cert_manager import get_ssl_config

ssl_config = get_ssl_config()
# 自动使用系统证书
```

### 场景3: 生产环境(CentOS) - 自定义证书

```bash
# 获取证书
python -m cert_manager.cli fetch deepseek --cert-dir /opt/app/certs

# 配置环境变量
export LLM_VERIFY_SSL=true
export LLM_CA_BUNDLE=/opt/app/certs/deepseek_full_chain.pem
```

```python
from cert_manager import get_ssl_config

ssl_config = get_ssl_config()
# 使用自定义证书
```

### 场景4: Docker容器

```dockerfile
FROM python:3.11-slim

# 安装系统证书
RUN apt-get update && \
    apt-get install -y ca-certificates && \
    rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY . /app

# 安装依赖
RUN pip install -r requirements.txt

# 方案A: 使用系统证书
ENV LLM_VERIFY_SSL=true

# 方案B: 使用自定义证书
# COPY certs/deepseek_full_chain.pem /app/certs/
# ENV LLM_CA_BUNDLE=/app/certs/deepseek_full_chain.pem

CMD ["python", "app.py"]
```

## API文档

### CertificateManager

主要的证书管理类。

```python
from cert_manager import CertificateManager

manager = CertificateManager(
    cert_dir="certs",          # 证书目录
    verify=True,               # 启用SSL验证
    ca_bundle=None,            # 证书文件路径
    timeout=10,                # 网络超时
    warning_days=30            # 过期警告天数
)
```

#### 方法

**fetch_deepseek_certificates(force=False)**

获取DeepSeek API的完整证书链。

```python
result = manager.fetch_deepseek_certificates()
# 返回: {
#     "server_cert": "certs/deepseek_server.pem",
#     "intermediate_cert": "certs/geotrust_intermediate.pem",
#     "full_chain": "certs/deepseek_full_chain.pem",
#     "status": "fetched"
# }
```

**fetch_certificate(hostname, port=443, output_file=None)**

获取指定服务器的证书。

```python
result = manager.fetch_certificate("api.example.com", 443)
# 返回: {
#     "cert_info": {...},
#     "cert_file": "certs/api_example_com_cert.pem",
#     "hostname": "api.example.com",
#     "port": 443
# }
```

**validate_certificate(cert_file=None)**

验证证书文件。

```python
result = manager.validate_certificate()
# 返回: {
#     "valid": True,
#     "exists": True,
#     "readable": True,
#     "cert_count": 2,
#     "errors": [],
#     "warnings": [],
#     "days_remaining": 365
# }
```

**validate_connection(hostname, port=443, cert_file=None)**

验证SSL连接。

```python
result = manager.validate_connection("api.deepseek.com")
# 返回: {
#     "success": True,
#     "hostname": "api.deepseek.com",
#     "port": 443,
#     "protocol": "TLSv1.3",
#     "cipher": "TLS_AES_256_GCM_SHA384",
#     "cert_info": {...}
# }
```

**validate_certificate_chain(cert_file=None)**

验证证书链完整性。

```python
result = manager.validate_certificate_chain()
# 返回: {
#     "valid": True,
#     "cert_count": 2,
#     "certificates": [
#         {
#             "index": 1,
#             "subject_cn": "*.deepseek.com",
#             "issuer_cn": "GeoTrust TLS RSA CA G1",
#             ...
#         },
#         ...
#     ]
# }
```

**get_status()**

获取证书管理器状态。

```python
status = manager.get_status()
# 返回完整的状态信息
```

### SSLConfig

SSL配置类。

```python
from cert_manager import get_ssl_config

ssl_config = get_ssl_config()
```

#### 方法

**get_verify_param() -> Union[bool, str]**

获取SSL验证参数,用于requests/httpx的verify参数。

```python
verify = ssl_config.get_verify_param()
# 返回: True (系统证书) 或 False (禁用) 或 str (证书路径)
```

**get_ssl_context() -> ssl.SSLContext**

获取SSL上下文,用于底层socket连接。

```python
context = ssl_config.get_ssl_context()
```

**requests_kwargs() -> dict**

获取requests库的参数。

```python
kwargs = ssl_config.requests_kwargs()
response = requests.get(url, **kwargs)
```

**httpx_client_kwargs() -> dict**

获取httpx库的参数。

```python
kwargs = ssl_config.httpx_client_kwargs()
client = httpx.Client(**kwargs)
```

**aiohttp_kwargs() -> dict**

获取aiohttp库的参数。

```python
kwargs = ssl_config.aiohttp_kwargs()
async with aiohttp.ClientSession() as session:
    async with session.get(url, **kwargs) as response:
        ...
```

## 故障排查

### 问题1: SSL验证失败

```
SSLError: [SSL: CERTIFICATE_VERIFY_FAILED]
```

**解决方案:**

1. 检查系统时间是否正确
2. 更新系统证书库
3. 使用自定义证书

```bash
# 获取证书
python -m cert_manager.cli fetch deepseek

# 配置环境变量
export LLM_CA_BUNDLE=certs/deepseek_full_chain.pem
```

### 问题2: 证书文件不存在

```
FileNotFoundError: 证书文件不存在
```

**解决方案:**

```bash
# 检查证书文件
python -m cert_manager.cli status

# 重新获取证书
python -m cert_manager.cli fetch deepseek --force
```

### 问题3: 证书过期

```
证书已过期
```

**解决方案:**

```bash
# 强制重新获取证书
python -m cert_manager.cli fetch deepseek --force

# 验证新证书
python -m cert_manager.cli validate
```

## 最佳实践

### 1. 生产环境部署

```python
# 1. 初始化证书管理器
from cert_manager import CertificateManager

manager = CertificateManager(
    cert_dir="/opt/app/certs",
    verify=True,
    warning_days=30
)

# 2. 获取证书(首次部署)
try:
    manager.fetch_deepseek_certificates()
except Exception as e:
    logger.error(f"获取证书失败: {e}")
    # 使用系统证书作为后备

# 3. 验证证书
result = manager.validate_certificate()
if not result["valid"]:
    logger.error(f"证书无效: {result['errors']}")

# 4. 使用SSL配置
ssl_config = manager.get_ssl_config()
```

### 2. 定期检查证书

```python
import schedule
import time

def check_certificate():
    """定期检查证书有效性"""
    manager = CertificateManager()
    result = manager.validate_certificate()
    
    if not result["valid"]:
        # 发送告警
        send_alert(f"证书无效: {result['errors']}")
    elif result.get("expiring_soon"):
        # 发送警告
        send_warning(f"证书即将过期: {result['days_remaining']}天")

# 每天检查一次
schedule.every().day.at("00:00").do(check_certificate)

while True:
    schedule.run_pending()
    time.sleep(3600)
```

### 3. 自动更新证书

```python
def auto_update_certificate():
    """自动更新证书"""
    manager = CertificateManager()
    
    # 检查证书
    result = manager.validate_certificate()
    
    # 如果证书即将过期或无效,重新获取
    if not result["valid"] or result.get("expiring_soon"):
        logger.info("证书需要更新")
        manager.fetch_deepseek_certificates(force=True)
        logger.info("证书已更新")
```

## 许可证

MIT License

## 贡献

欢迎提交Issue和Pull Request!
