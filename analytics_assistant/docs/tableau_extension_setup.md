# Tableau Desktop 插件配置指南

## 问题：无法连接到 https://127.0.0.1:8000/

当你在 Tableau Desktop 中加载插件时，如果看到"网址为 https://127.0.0.1:8000/ 的网页可能暂时无法连接，或者它已永久性地移动到了新网址"错误，这是因为 Tableau Desktop 不信任自签名证书。

## 解决方案

### 方案 1：在 Windows 中信任证书（推荐）

1. **导出证书到受信任的根证书颁发机构**

   打开 PowerShell（管理员权限）：

   ```powershell
   # 导入证书到受信任的根证书颁发机构
   $certPath = "analytics_assistant\data\certs\localhost.crt"
   Import-Certificate -FilePath $certPath -CertStoreLocation Cert:\LocalMachine\Root
   ```

2. **或者通过 GUI 手动导入**

   a. 双击 `analytics_assistant\data\certs\localhost.crt` 文件
   
   b. 点击"安装证书"
   
   c. 选择"本地计算机"（需要管理员权限）
   
   d. 选择"将所有的证书都放入下列存储"
   
   e. 点击"浏览"，选择"受信任的根证书颁发机构"
   
   f. 点击"下一步"，完成安装

3. **重启 Tableau Desktop**

   安装证书后，需要重启 Tableau Desktop 才能生效。

### 方案 2：配置 Tableau Desktop 忽略证书错误

1. **找到 Tableau Desktop 配置文件**

   路径：`C:\Users\<用户名>\Documents\My Tableau Repository\Preferences.tps`

2. **添加配置**

   在 `<preferences>` 标签内添加：

   ```xml
   <preference name='extensions.dashboard.disable-ssl-verification' value='true' />
   ```

3. **重启 Tableau Desktop**

### 方案 3：使用 Tableau 的开发者模式

1. **启用开发者模式**

   在 Tableau Desktop 中：
   - 帮助 → 设置和性能 → 启用扩展程序开发者模式

2. **允许不安全的扩展程序**

   这会允许加载使用自签名证书的扩展程序。

### 方案 4：使用正式 CA 签发的证书（生产环境推荐）

如果是生产环境，建议使用正式 CA 签发的证书：

1. **购买或申请免费证书**
   - Let's Encrypt（免费）
   - 阿里云、腾讯云等云服务商提供的证书

2. **配置证书**

   在 `analytics_assistant/config/app.yaml` 中添加生产证书配置：

   ```yaml
   ssl:
     certificates:
       production:
         cert_file: analytics_assistant/data/certs/production.crt
         key_file: analytics_assistant/data/certs/production.key
         reload_interval: 300
     
     # 切换到生产证书
     active_cert: production
   ```

3. **将证书文件复制到指定目录**

   ```powershell
   Copy-Item "path\to\your\production.crt" "analytics_assistant\data\certs\production.crt"
   Copy-Item "path\to\your\production.key" "analytics_assistant\data\certs\production.key"
   ```

4. **重启前后端服务**

   ```powershell
   python start.py
   ```

## 验证配置

### 1. 检查前后端服务状态

```powershell
# 检查后端
curl.exe -k https://127.0.0.1:5000/health

# 检查前端
curl.exe -k https://127.0.0.1:8000
```

### 2. 在浏览器中访问

打开浏览器访问 `https://127.0.0.1:8000`，如果看到前端页面，说明服务正常。

### 3. 检查证书信息

```powershell
python analytics_assistant/scripts/manage_certs.py info
```

## 常见问题

### Q1: 证书已安装，但 Tableau Desktop 仍然报错

**解决方法**：
1. 确认证书已安装到"受信任的根证书颁发机构"
2. 重启 Tableau Desktop
3. 清除 Tableau 缓存：删除 `C:\Users\<用户名>\AppData\Local\Tableau` 目录

### Q2: 前端服务无法启动

**解决方法**：
1. 检查端口是否被占用：`netstat -ano | findstr :8000`
2. 检查证书文件是否存在：`ls analytics_assistant\data\certs\`
3. 查看启动日志中的错误信息

### Q3: 后端 API 无法连接

**解决方法**：
1. 检查后端服务是否运行：`curl.exe -k https://127.0.0.1:5000/health`
2. 检查防火墙设置
3. 查看后端日志

### Q4: 证书过期

**解决方法**：
1. 生成新证书：
   ```powershell
   python analytics_assistant/scripts/manage_certs.py generate --days 3650
   ```
2. 系统会自动检测并重新加载（如果启用了热更新）

## 开发环境快速设置

如果只是开发测试，最快的方法是：

1. **启用 Tableau 开发者模式**（方案 3）
2. **启动服务**：
   ```powershell
   python start.py
   ```
3. **在 Tableau Desktop 中加载插件**：
   - 拖入一个"扩展程序"对象
   - 选择 `analytics_assistant\frontend\public\manifest.trex`

## 生产环境部署

生产环境建议：

1. 使用正式 CA 签发的证书
2. 配置域名（而不是 IP 地址）
3. 启用证书热更新
4. 配置 HTTPS 反向代理（如 Nginx）
5. 定期检查证书有效期

## 技术支持

如果遇到问题，可以：

1. 查看日志文件
2. 运行诊断命令：
   ```powershell
   python analytics_assistant/scripts/manage_certs.py validate
   ```
3. 检查配置文件：`analytics_assistant/config/app.yaml`
