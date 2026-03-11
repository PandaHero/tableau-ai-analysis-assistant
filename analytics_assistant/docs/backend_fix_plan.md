# 后端修复方案

> 综合 Cascade 审查 + GPT-5.4 审查，按优先级排列。

---

## P0 — 安全 & 数据正确性（必须立即修复）

### FIX-01: 数据源解析误绑 + 缓存放大
- **文件**: `src/platform/tableau/client.py:570-585`, `src/platform/tableau/data_loader.py:139,246,261`
- **问题**: prefix/fuzzy 匹配取第一个命中，遍历顺序依赖 API 返回顺序，不确定；误绑被进程级缓存放大
- **方案**:
  1. `get_datasource_luid_by_name()` 移除 prefix/fuzzy 策略，仅保留 exact match（带项目名 + 不带项目名）
  2. 若精确匹配失败，返回 `None` 并让上层向用户提示可用数据源列表
  3. 前端应优先传 `datasource_luid` 而非 `datasource_name`
  4. `_datasource_name_cache` 加 LRU 上限（如 64 个）
- **影响范围**: `client.py`, `data_loader.py`, 前端数据源选择逻辑
- **风险**: 低（移除模糊匹配只会让匹配更严格，不会破坏已工作的精确匹配）

### FIX-02: API key 明文落盘
- **文件**: `src/infra/ai/model_persistence.py:78-87`
- **问题**: 无 Fernet 密钥时 `_encrypt_api_key()` 原样返回，API key 裸存 SQLite
- **方案**:
  1. 无 Fernet 时，仅允许 `${ENV_VAR}` 引用格式的 API key 被持久化
  2. 非引用格式的 API key 应拒绝持久化并抛出 `ConfigurationError`
  3. 在 `_encrypt_api_key()` 中增加日志告警
- **影响范围**: `model_persistence.py`, 模型动态注册 API
- **风险**: 低（只影响动态添加模型的场景，YAML 配置的模型不走持久化）

### FIX-03: Tableau token 缓存键粒度不足
- **文件**: `src/platform/tableau/auth.py:512-517`
- **问题**: 缓存键只用 `domain`，多 site/多 principal 场景会串 token
- **方案**:
  1. 缓存键改为 `f"{domain}:{site}:{auth_method}"`
  2. 从 `TableauAuthContext` 中提取 `site` 和 `auth_method` 纳入缓存键
  3. 可选：尊重 Tableau API 返回的 `credentials.token` 过期时间，而非本地估算
- **影响范围**: `auth.py`
- **风险**: 低（单 site 场景下行为不变，只是缓存键更精确）

---

## P1 — 可靠性 & 可观测性

### FIX-04: 存储异常被静默吞掉
- **文件**: `src/infra/storage/repository.py:124-134,150-173,237-247,263-285`
- **问题**: `find_by_id`/`find_all` 等方法 catch Exception 后返回 None/[]，上层将基础设施故障误判为 404/空列表
- **方案**:
  1. 定义 `StoreError` 异常类（在 `core/exceptions.py` 中）
  2. `find_by_id`: key not found → 返回 None；store 连接/IO 错误 → 抛 `StoreError`
  3. `find_all`: store 错误 → 抛 `StoreError`
  4. API 路由层 catch `StoreError` → 返回 503 而非 404
- **影响范围**: `repository.py`, `sessions.py`, `settings.py`, `feedback.py`
- **风险**: 中（需要确保所有调用方都处理了新异常）

### FIX-05: 测试契约修复
- **文件**: `tests/agents/semantic_parser/nodes/test_understanding.py:14`
- **问题**: 导入 `_try_build_simple_clarification_output` 但源码中已不存在
- **方案**:
  1. 在 `understanding.py` 中确认该函数被重命名/移除的原因
  2. 更新测试导入和测试用例以匹配当前源码 API
  3. 确保 `pytest --collect-only` 能收集到所有测试
- **影响范围**: `test_understanding.py`（约 900 行测试）
- **风险**: 中（需要理解重构意图才能正确更新测试）

### FIX-06: Repository/Store 生命周期脱节
- **文件**: `src/api/dependencies.py:21-44`
- **问题**: `_repositories` 模块级 dict 无锁、无 TTL、无 reset，与 `StoreFactory.reset()` 不联动
- **方案**:
  1. 在 `dependencies.py` 中添加 `reset_repositories()` 函数
  2. `StoreFactory.reset()` 调用时同步清理 `_repositories`
  3. 或改为从 `StoreFactory` 统一获取 store，`BaseRepository` 不缓存 store 引用
- **影响范围**: `dependencies.py`, `store_factory.py`, 测试文件
- **风险**: 低

---

## P2 — 健壮性 & 代码质量

### FIX-07: 聊天入口缺少最后一条消息校验
- **文件**: `src/api/models/chat.py:20-42`
- **问题**: 未校验 `messages[-1].role == "user"`
- **方案**:
  在 `ChatRequest` 上添加 `model_validator`:
  ```python
  @model_validator(mode="after")
  def validate_last_message_is_user(self):
      if self.messages and self.messages[-1].role != "user":
          raise ValueError("最后一条消息必须来自用户")
      return self
  ```
- **影响范围**: `chat.py` (model)
- **风险**: 低

### FIX-08: SSE 事件队列无界
- **文件**: `src/orchestration/workflow/executor.py:847`
- **问题**: `asyncio.Queue()` 无界，理论上可内存溢出
- **方案**:
  1. 改为 `asyncio.Queue(maxsize=1000)`
  2. `put` 改为 `put_nowait`，队满时丢弃旧 heartbeat 事件或阻塞等待
- **影响范围**: `executor.py`
- **风险**: 低（需要测试背压场景下的行为）

### FIX-09: 会话分页 + find_all 上限截断
- **文件**: `src/api/routers/sessions.py:92-102`, `src/infra/storage/repository.py:139`
- **问题**: `find_all` 硬限 1000 条 + 内存排序分页，total 不准
- **方案**:
  1. 短期：将 `find_all` 的 `limit` 参数暴露给 API 层，sessions.py 传入足够大的值或循环分页
  2. 中期：在 `BaseStore` 层实现 SQL ORDER BY + OFFSET/LIMIT（SqliteStore 支持）
  3. 长期：迁移到 Postgres，使用原生分页
- **影响范围**: `repository.py`, `sessions.py`
- **风险**: 低

### FIX-10: middleware.py 重复导入
- **文件**: `src/api/middleware.py:19-22`
- **问题**: `sanitize_error_message` 导入两次，别名版本未使用
- **方案**: 删除 `sanitize_error_message as _sanitize_error_message`
- **影响范围**: 1 行代码
- **风险**: 无

### FIX-11: error_sanitizer 过度脱敏
- **文件**: `src/infra/error_sanitizer.py:35-38`
- **问题**: "token" 出现在任何错误消息中就返回通用错误，如 "max_tokens exceeded" 也被吞掉
- **方案**:
  1. 改为正则匹配敏感模式（如 `sk-xxx`、`Bearer xxx`、文件路径）
  2. 或维护白名单：允许 "max_tokens"、"token limit" 等安全消息通过
- **影响范围**: `error_sanitizer.py`
- **风险**: 低

### FIX-12: 认证日志降级
- **文件**: `src/api/dependencies.py:130-136`
- **问题**: 每个请求都在 INFO 级别打印 5+ 行分隔线日志
- **方案**: 将分隔线和详细认证信息降为 `DEBUG`，仅保留结果行在 `INFO`
- **影响范围**: `dependencies.py`
- **风险**: 无

### FIX-13: model_registry.py 格式规范化
- **文件**: `src/infra/ai/model_registry.py`
- **问题**: 整个文件充斥多余空行
- **方案**: 用 `ruff format` 或手动清理多余空行
- **影响范围**: 纯格式
- **风险**: 无

---

## P3 — 架构优化（中长期）

### FIX-14: 摘要构建函数统一
- **涉及文件**: `insight/graph.py`, `replanner/graph.py`, `executor.py`
- **方案**: 抽取到 `src/orchestration/workflow/summary_builder.py`，统一摘要格式

### FIX-15: 配置加载模式统一
- **涉及文件**: 6+ 组件各自的 `_get_config()` / `_load_config()`
- **方案**: 在 `AppConfig` 上为每个组件提供 typed accessor 方法

### FIX-16: executor God Object 拆分
- **文件**: `src/orchestration/workflow/executor.py`（2155 行）
- **方案**: 将嵌套函数提取为独立类/方法，考虑 LangGraph 子图拆分

### FIX-17: DataModel 缓存加 LRU 上限
- **文件**: `src/platform/tableau/data_loader.py`
- **方案**: 使用 `functools.lru_cache` 或 `collections.OrderedDict` 实现 LRU，限制 16-32 个

### FIX-18: 激活未使用的有价值能力
- 启用 IntentRouter L1 LLM 分类
- 将 API 路由改为 async + 使用 BaseRepository 异步 CRUD
- 集成 FeedbackLearner 到主流程
- 充分利用 field_value_cache 做筛选条件验证

---

## 修复顺序建议

```
Phase 1 (安全): FIX-01 → FIX-02 → FIX-03
Phase 2 (可靠): FIX-04 → FIX-05 → FIX-06
Phase 3 (健壮): FIX-07 → FIX-08 → FIX-09 → FIX-10 → FIX-11 → FIX-12 → FIX-13
Phase 4 (架构): FIX-14 → FIX-15 → FIX-16 → FIX-17 → FIX-18
```
