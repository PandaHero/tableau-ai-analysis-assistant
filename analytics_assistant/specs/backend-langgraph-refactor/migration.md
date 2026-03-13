# Migration Plan

> Status: Draft v1.2
> Read order: 13/14
> Upstream: [requirements.md](./requirements.md), [design.md](./design.md), [data-and-api.md](./data-and-api.md), [artifact-freshness-and-rebuild.md](./artifact-freshness-and-rebuild.md)
> Downstream: [tasks.md](./tasks.md)

## 1. 迁移原则

- 先立边界，再换主干。
- 先兼容入口路径，再替换内部实现。
- SSE 协议采用破坏式升级（v2），不承诺兼容旧事件 payload。
- 先让 `root_graph` 进入主链路，再下线旧 executor。
- 大结果洞察重构与主干切换分阶段推进，避免同窗爆炸。

## 2. 阶段拆分

### Phase 0：观测与错误边界

目标：

- 统一 `request_id/session_id/thread_id/run_id/trace_id`
- 建立统一错误码目录
- 修正吞错和异常归类问题

退出条件：

- 链路可观测字段齐全
- `EMPTY_RESULT` 与执行失败可明确区分

### Phase 1：租户与数据源安全

目标：

- 修正 token cache key
- 改造 datasource identity 解析
- 修正 metadata/artifact cache key

退出条件：

- 多租户并发不串 token
- 同名 datasource 仅通过澄清中断选择

### Phase 2：Root Graph 壳层接入

目标：

- 接入 `root_graph` 运行壳层
- 保留 `/api/chat/stream` 路径（允许切换为 SSE v2 payload）
- 通过 runner 包装旧实现

退出条件：

- root_graph 壳层可稳定承接请求
- checkpointer 可稳定落盘

### Phase 3：语义子图迁移

目标：

- `semantic_graph` 接管语义节点
- 澄清交互切到 `interrupt/resume`

退出条件：

- datasource/slot/value/follow-up 中断可恢复

### Phase 4：查询子图迁移

目标：

- 查询编译与执行迁入 `query_graph`
- 结果归一化与 artifact materialize 正式启用

退出条件：

- 结果产物稳定
- 错误码可观测并可归因

### Phase 5：洞察文件驱动上线

目标：

- 引入 `InsightFilesystemMiddleware`
- 洞察改为文件驱动
- `DataProfile` 退化为辅助信息

退出条件：

- 洞察不再依赖整表注入
- 工具读取全链路受限且可审计

### Phase 6：答案子图与重规划收敛

目标：

- insight/replan/follow-up 收敛到 `answer_graph`
- SSE 事件收敛到稳定目录

退出条件：

- 自动重规划上限有效
- follow-up 选择可跨进程恢复

### Phase 7：业务存储迁移

目标：

- sessions/settings/feedback 迁入业务表
- BaseRepository 从“全能仓库”降级为业务层适配器

退出条件：

- API 不再依赖通用 BaseStore 路径

### Phase 8：旧 executor 下线

目标：

- `WorkflowExecutor` 退出主链路
- root_graph 成为唯一运行路径

退出条件：

- 回归通过，灰度指标稳定

## 3. 风险控制

- 双轨期风险：状态源不一致  
  控制：单写策略 + 显式开关

- 洞察性能风险：读取过大  
  控制：分页上限 + 强制列裁剪

- 协议风险：前后端事件不一致  
  控制：SSE v2 契约测试 + 消费方适配清单

## 4. 发布策略

- feature flag（租户级、会话级）
- shadow compare（新旧路径并行观测）
- 灰度放量（小流量 -> 分租户 -> 全量）
- 一键回滚（切回旧路径）

## 5. 里程碑

- M1：Phase 0~2 完成，root_graph 接入且 SSE 切换到 v2
- M2：Phase 3~5 完成，语义/查询/洞察主能力迁入
- M3：Phase 6~8 完成，旧 executor 下线

## 6. 阶段准入门槛

每阶段进入下一阶段前必须满足：

- 自动化测试通过（契约 + 回归 + 冒烟）
- 关键指标无明显回退
- 中断恢复演练通过
- 回滚演练通过
