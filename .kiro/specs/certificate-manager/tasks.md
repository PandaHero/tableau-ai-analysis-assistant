# Implementation Tasks

## Task Group 1: 配置加载器 (ConfigLoader)

### Task 1.1: 创建配置数据模型
- [ ] 在 `tableau_assistant/src/infra/certs/models.py` 创建数据类
- [ ] 定义 `CertConfigData`, `ApplicationConfig`, `BackendCertConfig`, `CompanyCertConfig`, `ServiceCertConfig`
- [ ] 添加类型注解和文档字符串
- **Requirement**: REQ-1 (配置管理)

### Task 1.2: 实现 ConfigLoader 类
- [ ] 在 `tableau_assistant/src/infra/certs/config_loader.py` 创建 ConfigLoader
- [ ] 实现 `load()` 方法读取 YAML 文件
- [ ] 实现 `_expand_env_vars()` 支持 `${VAR_NAME}` 语法
- [ ] 实现 `_validate_schema()` 验证配置结构
- [ ] 支持回退到 `cert_config.example.yaml`
- **Requirement**: REQ-1 (配置管理)

### Task 1.3: 更新 cert_config.yaml
- [ ] 添加完整的 application 配置节
- [ ] 添加 company 子配置（auto_fetch, fetch_url, auto_refresh, refresh_interval）
- [ ] 添加配置说明注释
- **Requirement**: REQ-1 (配置管理)

---

## Task Group 2: 自签名证书生成器 (SelfSignedGenerator)

### Task 2.1: 创建 SelfSignedGenerator 类
- [ ] 在 `tableau_assistant/src/infra/certs/self_signed.py` 创建类
- [ ] 使用 `cryptography` 库生成证书
- [ ] 实现 `_generate_ca()` 生成 CA 证书
- [ ] 实现 `_generate_server_cert()` 生成服务器证书
- **Requirement**: REQ-3 (自签名证书生成)

### Task 2.2: 实现 SAN 配置
- [ ] 默认包含 `localhost`, `127.0.0.1`
- [ ] 支持从配置读取额外主机名
- [ ] 支持 IP 地址和 DNS 名称
- **Requirement**: REQ-3 (自签名证书生成)

### Task 2.3: 实现证书复用逻辑
- [ ] 实现 `check_existing()` 检查现有证书
- [ ] 验证证书有效期
- [ ] 过期时自动重新生成
- **Requirement**: REQ-3 (自签名证书生成)

---

## Task Group 3: 公司证书支持

### Task 3.1: 创建 CompanyCertFetcher 类
- [ ] 在 `tableau_assistant/src/infra/certs/company_fetcher.py` 创建类
- [ ] 实现 `fetch()` 方法从公司服务器拉取证书
- [ ] 支持 HTTPS URL 拉取 (`https://cert-server.company.com/...`)
- [ ] 支持文件共享路径 (`file:///shared/certs/...`)
- [ ] 实现 `check_for_updates()` 检查服务器证书是否更新
- **Requirement**: REQ-2 (公司证书支持)

### Task 3.2: 实现公司证书加载
- [ ] 在 CertificateManager 中添加 `_load_company_certs()` 方法
- [ ] 如果 `auto_fetch: true`，先从公司服务器拉取
- [ ] 验证三个文件（cert, key, ca_bundle）都存在
- [ ] 拉取失败时回退到本地文件
- **Requirement**: REQ-2 (公司证书支持)

### Task 3.3: 实现证书私钥匹配验证
- [ ] 使用 `cryptography` 验证证书和私钥匹配
- [ ] 提供清晰的错误信息
- **Requirement**: REQ-2 (公司证书支持)

### Task 3.4: 实现证书过期检查
- [ ] 读取证书过期时间
- [ ] 与 `warning_days` 比较
- [ ] 过期阻止启动，即将过期发出警告
- **Requirement**: REQ-2 (公司证书支持)

---

## Task Group 4: 第三方服务证书获取

### Task 4.1: 增强 ServiceRegistry
- [ ] 修改 `ServiceRegistry` 支持从配置加载服务
- [ ] 实现 `load_from_config()` 方法
- [ ] 支持 `auto_fetch` 配置
- **Requirement**: REQ-4 (第三方服务证书自动获取)

### Task 4.2: 实现批量证书获取
- [ ] 在初始化时获取所有 `auto_fetch: true` 的服务证书
- [ ] 并行获取提高效率
- [ ] 单个失败不影响其他服务
- **Requirement**: REQ-4 (第三方服务证书自动获取)

### Task 4.3: 实现证书缓存逻辑
- [ ] 检查现有证书是否有效
- [ ] 有效则跳过获取
- [ ] 支持强制刷新
- **Requirement**: REQ-4 (第三方服务证书自动获取)

### Task 4.4: 实现 Tableau 智能证书处理
- [ ] 检测 Tableau Cloud (`*.online.tableau.com`) 使用系统证书
- [ ] 检测 Tableau Server (内部部署) 自动获取证书
- [ ] 支持 `auto_fetch: "auto"` 智能模式
- [ ] 从 `${TABLEAU_DOMAIN}` 环境变量解析主机名和端口
- **Requirement**: REQ-4 (第三方服务证书自动获取)

---

## Task Group 5: 证书热更新 (HotReloader)

### Task 5.1: 创建 HotReloader 类
- [ ] 在 `tableau_assistant/src/infra/certs/hot_reload.py` 创建类
- [ ] 使用 `watchdog` 库监控文件变化
- [ ] 实现 `start()` 和 `stop()` 方法
- **Requirement**: REQ-6 (证书热更新)

### Task 5.2: 实现防抖逻辑
- [ ] 使用定时器防止频繁触发
- [ ] 默认 2 秒防抖间隔
- [ ] 可配置防抖时间
- **Requirement**: REQ-6 (证书热更新)

### Task 5.3: 实现安全重载
- [ ] 重载前验证新证书
- [ ] 验证失败保持旧证书
- [ ] 记录详细日志
- **Requirement**: REQ-6 (证书热更新)

### Task 5.4: 实现公司证书定期刷新
- [ ] 当 `auto_refresh: true` 时启动定期刷新任务
- [ ] 使用后台线程或 asyncio 定时器
- [ ] 按 `refresh_interval` 配置的间隔检查更新
- [ ] 发现更新时自动拉取并重载
- **Requirement**: REQ-6 (证书热更新)

### Task 5.5: 实现刷新状态跟踪
- [ ] 记录上次刷新时间
- [ ] 记录刷新成功/失败状态
- [ ] 在 `get_status()` 中返回刷新状态
- **Requirement**: REQ-6, REQ-7

---

## Task Group 6: CertificateManager 增强

### Task 6.1: 重构 CertificateManager 初始化
- [ ] 修改 `__init__` 接受 `config_path` 参数
- [ ] 使用 ConfigLoader 加载配置
- [ ] 初始化所有子组件
- **Requirement**: REQ-1, REQ-5

### Task 6.2: 实现 initialize() 方法
- [ ] 根据 `source` 准备应用证书
- [ ] 调用 SelfSignedGenerator 或加载公司证书
- [ ] 获取服务证书
- [ ] 验证所有证书
- **Requirement**: REQ-2, REQ-3, REQ-4

### Task 6.3: 实现 get_app_ssl_config() 方法
- [ ] 返回 uvicorn 需要的 SSL 配置
- [ ] 包含 `ssl_certfile` 和 `ssl_keyfile`
- **Requirement**: REQ-5 (启动脚本集成)

### Task 6.4: 实现 get_status() 方法
- [ ] 返回所有证书状态
- [ ] 包含过期信息和警告
- [ ] 供 `/api/health` 使用
- **Requirement**: REQ-7 (证书状态报告)

### Task 6.5: 实现 export_to_env() 方法
- [ ] 导出证书路径为环境变量格式
- [ ] 支持 `SSL_CERT_FILE`, `SSL_KEY_FILE`, `REQUESTS_CA_BUNDLE`
- **Requirement**: REQ-5 (启动脚本集成)

---

## Task Group 7: start.py 集成

### Task 7.1: 移除直接 SSL 检查
- [ ] 删除 `verify_env_config()` 中的直接 SSL 文件检查
- [ ] 改为调用 CertificateManager
- **Requirement**: REQ-5 (启动脚本集成)

### Task 7.2: 添加证书管理器初始化
- [ ] 在 `main()` 中初始化 CertificateManager
- [ ] 调用 `initialize()` 准备证书
- [ ] 处理初始化失败
- **Requirement**: REQ-5 (启动脚本集成)

### Task 7.3: 使用证书管理器配置 uvicorn
- [ ] 从 `get_app_ssl_config()` 获取 SSL 配置
- [ ] 传递给 uvicorn 命令
- [ ] 移除从 .env 读取 SSL 路径的代码
- **Requirement**: REQ-5 (启动脚本集成)

### Task 7.4: 添加证书状态显示
- [ ] 启动时显示证书状态摘要
- [ ] 显示证书来源（公司/自签名）
- [ ] 显示过期警告
- **Requirement**: REQ-7 (证书状态报告)

---

## Task Group 8: API 健康检查集成

### Task 8.1: 扩展 /api/health 端点
- [ ] 添加证书状态到健康检查响应
- [ ] 包含过期警告
- [ ] 包含各服务证书状态
- **Requirement**: REQ-7 (证书状态报告)

---

## Task Group 9: 更新 cert_config.yaml

### Task 9.1: 完善配置文件
- [ ] 添加 `company` 配置节（带占位符）
- [ ] 确保环境变量引用正确
- [ ] 添加注释说明
- **Requirement**: REQ-1, REQ-2

---

## Task Group 10: 依赖和导出

### Task 10.1: 更新 requirements.txt
- [ ] 添加 `watchdog>=3.0`（文件监控）
- [ ] 确认 `PyYAML` 已存在（pydantic-settings 依赖）
- [ ] 确认 `cryptography` 已存在
- **Requirement**: 所有

### Task 10.2: 更新模块导出
- [ ] 更新 `tableau_assistant/src/infra/certs/__init__.py`
- [ ] 导出新增的类和函数
- **Requirement**: 所有

---

## Implementation Order

建议按以下顺序实现：

1. **Phase 1: 基础设施** (Task Group 1, 10)
   - 配置加载器
   - 依赖更新

2. **Phase 2: 证书生成和加载** (Task Group 2, 3)
   - 自签名证书生成
   - 公司证书拉取和加载

3. **Phase 3: 服务证书** (Task Group 4)
   - 第三方服务证书获取

4. **Phase 4: 管理器整合** (Task Group 6, 9)
   - CertificateManager 增强
   - 配置文件更新

5. **Phase 5: 集成** (Task Group 7, 8)
   - start.py 集成
   - API 健康检查

6. **Phase 6: 热更新** (Task Group 5)
   - 文件监控热更新
   - 公司证书定期刷新
