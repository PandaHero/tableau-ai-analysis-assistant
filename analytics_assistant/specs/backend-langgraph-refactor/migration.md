# Migration Plan

> 状态: Draft v1.0
> 读取顺序: 11/12
> 上游文档: [design.md](./design.md), [data-and-api.md](./data-and-api.md), [middleware.md](./middleware.md)
> 下游文档: [tasks.md](./tasks.md)
> 关联文档: [requirements.md](./requirements.md)

## 1. 迁移原则

- 先稳边界，再换主干。
- 先兼容现有 API，再逐步替换内部实现。
- 先让 root graph 进入链路，再逐步迁走旧 executor。
- 洞察文件中间件作为独立阶段推进，不和主干切换混在同一阶段爆炸上线。

## 2. 阶段划分

### Phase 0: 观测与错误边界

目标：

- 统一 `request_id`、`session_id`、`thread_id`、`run_id`、`trace_id`
- 统一 error code
- 修正 repository 吞错问题

验收：

- 每个请求都能完整链路追踪
- 空结果和执行失败能明确区分

### Phase 1: 租户与数据源安全

目标：

- 修正 token cache key
- 修正 datasource identity 解析规则
- 修正 metadata cache key

验收：

- 多租户不串 token
- 同名 datasource 不被误绑定

### Phase 2: Root Graph Shell

目标：

- 引入 `root_graph`
- 保留现有 `/api/chat/stream`
- 内部从 `executor` 切换为 `graph runner` 包装

验收：

- 前端协议不破坏
- graph 能建立 checkpoint

### Phase 3: 迁移 `semantic_graph`

目标：

- 迁移语义解析节点
- 所有澄清统一转为 `interrupt/resume`

验收：

- datasource 歧义、缺失槽位都能通过 interrupt 恢复

### Phase 4: 迁移 `query_graph`

目标：

- 迁移查询计划构建
- 迁移 Tableau 执行与结果规范化
- 引入结果 artifact materialization

验收：

- `QUERY_EXECUTION_ERROR` 和 `EMPTY_RESULT` 可稳定区分
- 结果能生成 manifest 和只读 artifact

### Phase 5: 引入 `InsightFilesystemMiddleware`

目标：

- 洞察 agent 切换到文件驱动模式
- `DataProfile` 降级为辅助摘要
- 结果探索通过结果文件工具完成

验收：

- 洞察节点不再依赖整表 JSON 进入上下文
- agent 能通过文件工具完成局部探索

### Phase 6: 迁移 `answer_graph`

目标：

- 把洞察、follow-up、replan 都收进 `answer_graph`
- 收敛 SSE 事件模型

验收：

- follow-up 选择走 interrupt/resume
- SSE 事件只保留稳定业务事件

### Phase 7: 迁移业务存储

目标：

- 会话、设置、反馈迁到正式业务表
- 旧通用 repository 降级

验收：

- sessions/settings/feedback 不再依赖通用 BaseStore 主路径

### Phase 8: 下线旧 executor

目标：

- 旧 `WorkflowExecutor` 退出主链

验收：

- root graph 成为唯一主运行路径

## 3. 风险控制

### 3.1 技术风险

- root graph 与旧 executor 并存期间可能产生双状态源
- 结果 artifact 设计不当会让洞察工具过慢
- interrupt 契约切换会影响前端

### 3.2 控制策略

- 每一阶段保留兼容入口
- 关键路径增加契约测试
- SSE 和 resume 先做兼容层再切新协议

## 4. 发布策略

建议使用：

- feature flag
- 按租户灰度
- 按 session 路由到新运行时

## 5. 里程碑

### M1

- Phase 0 到 Phase 2 完成
- 新旧入口兼容

### M2

- Phase 3 到 Phase 5 完成
- 语义和洞察核心能力迁入新主干

### M3

- Phase 6 到 Phase 8 完成
- 旧 executor 下线

## 6. 阶段退出条件

阶段只有在以下条件满足后才能进入下一阶段：

- 自动化测试通过
- 关键错误码可观测
- 中断恢复演练通过
- 灰度指标没有明显回退
