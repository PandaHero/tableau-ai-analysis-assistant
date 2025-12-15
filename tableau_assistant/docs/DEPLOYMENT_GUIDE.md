# Tableau AI 分析助手 - CentOS 部署指南

## 目录

1. [系统要求](#系统要求)
2. [环境准备](#环境准备)
3. [证书配置](#证书配置)
4. [项目部署](#项目部署)
5. [生产环境配置](#生产环境配置)
6. [启动服务](#启动服务)
7. [Systemd 服务配置](#systemd-服务配置)
8. [Nginx 反向代理](#nginx-反向代理)
9. [常见问题](#常见问题)

---

## 系统要求

- CentOS 7/8 或 Rocky Linux 8/9
- Python 3.12+
- Node.js 18+ (用于构建前端)
- 4GB+ RAM
- 10GB+ 磁盘空间

---

## 环境准备

### 1. 安装 Python 3.12

```bash
# CentOS 8 / Rocky Linux
sudo dnf install -y python3.12 python3.12-pip python3.12-devel

# 或者从源码编译
sudo dnf groupinstall -y "Development Tools"
sudo dnf install -y openssl-devel bzip2-devel libffi-devel zlib-devel

cd /tmp
wget https://www.python.org/ftp/python/3.12.0/Python-3.12.0.tgz
tar xzf Python-3.12.0.tgz
cd Python-3.12.0
./configure --enable-optimizations
make -j$(nproc)
sudo make altinstall

# 验证
python3.12 --version
```

### 2. 安装 Node.js (仅构建前端需要)

```bash
# 使用 NodeSource 仓库
curl -fsSL https://rpm.nodesource.com/setup_18.x | sudo bash -
sudo dnf install -y nodejs

# 验证
node --version
npm --version
```

### 3. 创建应用用户

```bash
# 创建专用用户
sudo useradd -r -m -s /bin/bash tableau-assistant
sudo passwd tableau-assistant

# 创建应用目录
sudo mkdir -p /opt/tableau-assistant
sudo chown tableau-assistant:tableau-assistant /opt/tableau-assistant
```

---

## 证书配置

### 方式一：使用公司证书（推荐）

如果公司有统一的 SSL 证书，按以下步骤配置：

```bash
# 切换到应用用户
sudo su - tableau-assistant
cd /opt/tableau-assistant

# 创建证书目录
mkdir -p certs

# 复制公司证书（需要从公司获取）
# 通常包含以下文件：
# - server.crt (服务器证书)
# - server.key (私钥)
# - ca.crt (CA 证书链)

cp /path/to/company/server.crt certs/app_server.pem
cp /path/to/company/server.key certs/app_server_key.pem
cp /path/to/company/ca.crt certs/app_ca.pem

# 设置权限
chmod 600 certs/app_server_key.pem
chmod 644 certs/app_server.pem certs/app_ca.pem
```

### 方式二：生成自签名证书（测试环境）

```bash
cd /opt/tableau-assistant/certs

# 生成 CA 私钥
openssl genrsa -out ca_key.pem 4096

# 生成 CA 证书
openssl req -new -x509 -days 3650 -key ca_key.pem -out app_ca.pem \
  -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Company/OU=IT/CN=Tableau Assistant CA"

# 生成服务器私钥
openssl genrsa -out app_server_key.pem 2048

# 生成证书签名请求 (CSR)
openssl req -new -key app_server_key.pem -out server.csr \
  -subj "/C=CN/ST=Shanghai/L=Shanghai/O=Company/OU=IT/CN=your-server-hostname"

# 创建扩展配置文件
cat > server_ext.cnf << EOF
authorityKeyIdentifier=keyid,issuer
basicConstraints=CA:FALSE
keyUsage = digitalSignature, nonRepudiation, keyEncipherment, dataEncipherment
subjectAltName = @alt_names

[alt_names]
DNS.1 = your-server-hostname
DNS.2 = localhost
IP.1 = 127.0.0.1
IP.2 = your-server-ip
EOF

# 签发服务器证书
openssl x509 -req -in server.csr -CA app_ca.pem -CAkey ca_key.pem \
  -CAcreateserial -out app_server.pem -days 365 -extfile server_ext.cnf

# 清理临时文件
rm server.csr server_ext.cnf

# 设置权限
chmod 600 app_server_key.pem ca_key.pem
chmod 644 app_server.pem app_ca.pem
```

### 配置 cert_config.yaml

```bash
cd /opt/tableau-assistant

# 复制示例配置
cp cert_config.example.yaml cert_config.yaml

# 编辑配置
vim cert_config.yaml
```

```yaml
# cert_config.yaml
cert_dir: "/opt/tableau-assistant/certs"
verify_ssl: true
warning_days: 30

application:
  source: "company"  # 使用公司证书时设为 "company"，自签名设为 "self-signed"
  
  backend:
    cert_file: "app_server.pem"
    key_file: "app_server_key.pem"
  
  ca_bundle: "app_ca.pem"
  
  # 公司证书路径（source: "company" 时使用）
  company:
    cert_file: "/opt/tableau-assistant/certs/app_server.pem"
    key_file: "/opt/tableau-assistant/certs/app_server_key.pem"
    ca_bundle: "/opt/tableau-assistant/certs/app_ca.pem"

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
  
  tableau:
    hostname: "${TABLEAU_DOMAIN}"
    port: 443
    ca_bundle: "tableau_cert.pem"
    auto_fetch: false
```

---

## 项目部署

### 1. 克隆代码

```bash
sudo su - tableau-assistant
cd /opt/tableau-assistant

git clone https://github.com/PandaHero/tableau-ai-analysis-assistant.git .
# 或者上传代码包
# scp -r ./tableau-ai-analysis-assistant/* tableau-assistant@server:/opt/tableau-assistant/
```

### 2. 创建虚拟环境

```bash
cd /opt/tableau-assistant

# 创建虚拟环境
python3.12 -m venv venv

# 激活虚拟环境
source venv/bin/activate

# 升级 pip
pip install --upgrade pip

# 安装依赖
pip install -r tableau_assistant/requirements.txt
```

### 3. 构建前端

```bash
cd /opt/tableau-assistant/tableau_assistant/frontend

# 安装依赖
npm install

# 构建生产版本
npm run build

# 构建产物在 dist/ 目录
ls -la dist/
```

### 4. 配置环境变量

```bash
cd /opt/tableau-assistant

# 复制示例配置
cp .env.example .env

# 编辑配置
vim .env
```

```bash
# .env 文件内容

# ============================================
# 服务器配置
# ============================================
HOST=0.0.0.0
PORT=8000

# ============================================
# SSL 证书配置
# ============================================
SSL_CERT_FILE=/opt/tableau-assistant/certs/app_server.pem
SSL_KEY_FILE=/opt/tableau-assistant/certs/app_server_key.pem

# 前端 SSL（如果前端独立部署）
FRONTEND_SSL_CERT_FILE=/opt/tableau-assistant/certs/app_server.pem
FRONTEND_SSL_KEY_FILE=/opt/tableau-assistant/certs/app_server_key.pem

# ============================================
# Tableau 配置
# ============================================
TABLEAU_DOMAIN=your-tableau-server.company.com
TABLEAU_SITE=your-site-name
TABLEAU_USER=your-tableau-user
TABLEAU_JWT_CLIENT_ID=your-jwt-client-id
TABLEAU_JWT_SECRET_ID=your-jwt-secret-id
TABLEAU_JWT_SECRET=your-jwt-secret

# ============================================
# LLM 配置
# ============================================
LLM_API_BASE=https://api.deepseek.com/v1
LLM_API_KEY=your-llm-api-key
LLM_MODEL=deepseek-chat
LLM_VERIFY_SSL=true

# ============================================
# 嵌入模型配置
# ============================================
EMBEDDING_API_BASE=https://api.deepseek.com/v1
EMBEDDING_API_KEY=your-embedding-api-key
EMBEDDING_MODEL=text-embedding-3-small

# ============================================
# 数据存储
# ============================================
DATA_DIR=/opt/tableau-assistant/data
CACHE_DIR=/opt/tableau-assistant/data/cache

# ============================================
# 日志配置
# ============================================
LOG_LEVEL=INFO
LOG_FILE=/opt/tableau-assistant/logs/app.log
```

---

## 生产环境配置

### 1. 创建必要目录

```bash
mkdir -p /opt/tableau-assistant/data
mkdir -p /opt/tableau-assistant/data/cache
mkdir -p /opt/tableau-assistant/data/indexes
mkdir -p /opt/tableau-assistant/logs

chown -R tableau-assistant:tableau-assistant /opt/tableau-assistant
```

### 2. 配置防火墙

```bash
# 开放端口
sudo firewall-cmd --permanent --add-port=8000/tcp
sudo firewall-cmd --permanent --add-port=443/tcp
sudo firewall-cmd --reload
```

---

## 启动服务

### 方式一：直接启动（测试用）

```bash
cd /opt/tableau-assistant
source venv/bin/activate

# 启动后端
uvicorn tableau_assistant.src.main:app \
  --host 0.0.0.0 \
  --port 8000 \
  --ssl-certfile /opt/tableau-assistant/certs/app_server.pem \
  --ssl-keyfile /opt/tableau-assistant/certs/app_server_key.pem \
  --workers 4
```

### 方式二：使用启动脚本

```bash
cd /opt/tableau-assistant
python start.py
```

---

## Systemd 服务配置

### 1. 创建服务文件

```bash
sudo vim /etc/systemd/system/tableau-assistant.service
```

```ini
[Unit]
Description=Tableau AI Analysis Assistant
After=network.target

[Service]
Type=simple
User=tableau-assistant
Group=tableau-assistant
WorkingDirectory=/opt/tableau-assistant
Environment="PATH=/opt/tableau-assistant/venv/bin"
EnvironmentFile=/opt/tableau-assistant/.env
ExecStart=/opt/tableau-assistant/venv/bin/uvicorn \
    tableau_assistant.src.main:app \
    --host 0.0.0.0 \
    --port 8000 \
    --ssl-certfile /opt/tableau-assistant/certs/app_server.pem \
    --ssl-keyfile /opt/tableau-assistant/certs/app_server_key.pem \
    --workers 4
Restart=always
RestartSec=5

[Install]
WantedBy=multi-user.target
```

### 2. 启用并启动服务

```bash
# 重新加载 systemd
sudo systemctl daemon-reload

# 启用开机自启
sudo systemctl enable tableau-assistant

# 启动服务
sudo systemctl start tableau-assistant

# 查看状态
sudo systemctl status tableau-assistant

# 查看日志
sudo journalctl -u tableau-assistant -f
```

---

## Nginx 反向代理（可选）

如果需要通过 Nginx 提供服务：

### 1. 安装 Nginx

```bash
sudo dnf install -y nginx
```

### 2. 配置 Nginx

```bash
sudo vim /etc/nginx/conf.d/tableau-assistant.conf
```

```nginx
upstream tableau_backend {
    server 127.0.0.1:8000;
}

server {
    listen 443 ssl http2;
    server_name your-domain.company.com;

    # SSL 证书
    ssl_certificate /opt/tableau-assistant/certs/app_server.pem;
    ssl_certificate_key /opt/tableau-assistant/certs/app_server_key.pem;
    ssl_trusted_certificate /opt/tableau-assistant/certs/app_ca.pem;

    # SSL 配置
    ssl_protocols TLSv1.2 TLSv1.3;
    ssl_ciphers ECDHE-ECDSA-AES128-GCM-SHA256:ECDHE-RSA-AES128-GCM-SHA256;
    ssl_prefer_server_ciphers off;
    ssl_session_cache shared:SSL:10m;
    ssl_session_timeout 1d;

    # 前端静态文件
    location / {
        root /opt/tableau-assistant/tableau_assistant/frontend/dist;
        try_files $uri $uri/ /index.html;
        
        # 缓存静态资源
        location ~* \.(js|css|png|jpg|jpeg|gif|ico|svg|woff|woff2)$ {
            expires 1y;
            add_header Cache-Control "public, immutable";
        }
    }

    # API 代理
    location /api/ {
        proxy_pass https://tableau_backend;
        proxy_http_version 1.1;
        proxy_set_header Upgrade $http_upgrade;
        proxy_set_header Connection "upgrade";
        proxy_set_header Host $host;
        proxy_set_header X-Real-IP $remote_addr;
        proxy_set_header X-Forwarded-For $proxy_add_x_forwarded_for;
        proxy_set_header X-Forwarded-Proto $scheme;
        
        # SSE 支持
        proxy_buffering off;
        proxy_cache off;
        proxy_read_timeout 86400s;
    }

    # 健康检查
    location /health {
        proxy_pass https://tableau_backend/api/health;
    }
}

# HTTP 重定向到 HTTPS
server {
    listen 80;
    server_name your-domain.company.com;
    return 301 https://$server_name$request_uri;
}
```

### 3. 启动 Nginx

```bash
# 测试配置
sudo nginx -t

# 启动
sudo systemctl enable nginx
sudo systemctl start nginx
```

---

## 常见问题

### 1. 证书问题

```bash
# 验证证书
openssl x509 -in /opt/tableau-assistant/certs/app_server.pem -text -noout

# 验证证书链
openssl verify -CAfile /opt/tableau-assistant/certs/app_ca.pem \
  /opt/tableau-assistant/certs/app_server.pem

# 测试 HTTPS 连接
curl -v --cacert /opt/tableau-assistant/certs/app_ca.pem \
  https://localhost:8000/api/health
```

### 2. 权限问题

```bash
# 修复权限
sudo chown -R tableau-assistant:tableau-assistant /opt/tableau-assistant
chmod 600 /opt/tableau-assistant/certs/*_key.pem
chmod 644 /opt/tableau-assistant/certs/*.pem
```

### 3. 端口被占用

```bash
# 查看端口占用
sudo netstat -tlnp | grep 8000
sudo lsof -i :8000

# 杀死占用进程
sudo kill -9 <PID>
```

### 4. 服务无法启动

```bash
# 查看详细日志
sudo journalctl -u tableau-assistant -n 100 --no-pager

# 手动测试启动
cd /opt/tableau-assistant
source venv/bin/activate
python -c "from tableau_assistant.src.main import app; print('OK')"
```

### 5. Tableau 连接问题

```bash
# 测试 Tableau 连接
curl -v https://your-tableau-server.company.com

# 检查 Tableau 证书
openssl s_client -connect your-tableau-server.company.com:443 -showcerts
```

---

## 快速启动命令汇总

```bash
# 开发环境
cd /opt/tableau-assistant
source venv/bin/activate
python start.py

# 生产环境
sudo systemctl start tableau-assistant
sudo systemctl status tableau-assistant

# 查看日志
sudo journalctl -u tableau-assistant -f

# 重启服务
sudo systemctl restart tableau-assistant
```
