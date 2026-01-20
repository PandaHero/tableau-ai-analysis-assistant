# 附件 5：分阶段实施计划

本文档详细说明 7 个阶段的实施计划，每个阶段独立可测试和回滚。

## 实施原则

- ✅ **分阶段交付**：每个阶段独立部署
- ✅ **可回滚性**：每个阶段都有回滚方案
- ✅ **增量验证**：每个阶段完成后进行验证
- ✅ **风险可控**：识别风险并提供缓解策略

---

## 阶段 1：基础设施层重构（2 周）

### 目标

建立统一的基础设施服务，为上层提供支撑。

### 任务清单

**Week 1：AI 和 RAG 模块**
- [ ] 实现 ModelManager（多模型管理）
- [ ] 实现 UnifiedRetriever（混合检索）
- [ ] 实现 Indexer（索引构建）
- [ ] 实现 Reranker（重排序）
- [ ] 单元测试（覆盖率 ≥ 80%）

**Week 2：Storage 和 Observability 模块**
- [ ] 实现统一 CacheManager 基类（基于 LangGraph SqliteStore）
- [ ] 实现 LangGraph SqliteStore 集成
- [ ] 迁移现有缓存类到新架构
- [ ] 实现结构化日志（structlog）
- [ ] 实现 Prometheus 指标
- [ ] 实现 OpenTelemetry 追踪
- [ ] 集成测试

### 交付物

- ModelManager 支持多模型配置
- UnifiedRetriever 支持混合检索
- 统一 CacheManager（基于 LangGraph SqliteStore）
- 完整的可观测性体系
- 移除 Redis 依赖

### 验证标准

- 单元测试覆盖率 ≥ 80%
- 集成测试通过
- 性能测试：检索延迟 < 300ms

### 回滚方案

- Git Tag: `v1.0-infra`
- 回滚命令: `git checkout v1.0-infra`
- 数据迁移：无需迁移（新模块）

---

## 阶段 2：Core 层和 Platform 层（2 周）

### 目标

建立领域模型和平台适配器，实现关注点分离。

### 任务清单

**Week 1：Core 层**
- [ ] 定义领域模型（SemanticQuery, DataModel, Field）
- [ ] 定义平台适配器接口（IPlatformAdapter）
- [ ] 实现数据验证器
- [ ] 单元测试

**Week 2：Platform 层**
- [ ] 实现 TableauAdapter
- [ ] 实现 QueryBuilder（VizQL）
- [ ] 实现 DataLoader
- [ ] 集成测试（与 Tableau API）

### 交付物

- 完整的领域模型
- Tableau 平台适配器
- 平台无关的接口定义

### 验证标准

- 单元测试覆盖率 ≥ 80%
- Tableau API 集成测试通过
- 数据模型加载成功

### 回滚方案

- Git Tag: `v2.0-core-platform`
- 回滚命令: `git checkout v2.0-core-platform`
- 数据迁移：无需迁移

---

## 阶段 3：Agent 组件化（3 周）

### 目标

将现有 Agent 重构为组件化架构，提升可复用性。

### 任务清单

**Week 1：Base 组件**
- [ ] 实现 BaseComponent 抽象类
- [ ] 实现 MiddlewareRunner
- [ ] 实现通用错误处理器
- [ ] 单元测试

**Week 2：FieldMapper 和 DimensionHierarchy**
- [ ] 重构 FieldMapper 为组件化架构
- [ ] 重构 DimensionHierarchy 为组件化架构
- [ ] 集成 RAG 检索
- [ ] 单元测试和集成测试

**Week 3：Insight 和 Replanner**
- [ ] 重构 Insight Agent（子图架构）
- [ ] 重构 Replanner Agent
- [ ] 集成测试
- [ ] 性能测试

### 交付物

- 可复用的 Agent 组件
- 组件化的 FieldMapper、DimensionHierarchy、Insight、Replanner

### 验证标准

- 单元测试覆盖率 ≥ 80%
- 集成测试通过
- 性能无退化

### 回滚方案

- Git Tag: `v3.0-agent-components`
- 回滚命令: `git checkout v3.0-agent-components`
- 数据迁移：无需迁移

---

## 阶段 4：语义解析器优化（3 周）

### 目标

实现三层意图路由、Prompt 优化、混合检索，降低 token 消耗 30%。

### 任务清单

**Week 1：三层意图路由**
- [ ] 实现 L0 规则引擎
- [ ] 训练 L1 小模型（DistilBERT）
- [ ] 实现 L2 LLM 兜底
- [ ] 集成三层路由逻辑
- [ ] 单元测试

**Week 2：Prompt 优化**
- [ ] 实现动态 Schema 过滤
- [ ] 设计分层 Prompt（Step1 + Step2）
- [ ] 实现思维链压缩
- [ ] A/B 测试

**Week 3：集成和优化**
- [ ] 集成所有优化
- [ ] 性能测试
- [ ] Token 消耗统计
- [ ] 准确性评估

### 交付物

- 三层意图路由系统
- 优化的 Prompt 模板
- Token 消耗降低 30%

### 验证标准

- L0 命中率 ≥ 30%
- L1 命中率 ≥ 50%
- Token 消耗降低 ≥ 30%
- 准确率提升 ≥ 10%

### 回滚方案

- Git Tag: `v4.0-semantic-optimization`
- 回滚命令: `git checkout v4.0-semantic-optimization`
- 数据迁移：小模型权重文件

---

## 阶段 5：Orchestration 层（2 周）

### 目标

使用 LangGraph 重构主工作流，实现中间件系统。

### 任务清单

**Week 1：LangGraph 工作流**
- [ ] 设计主工作流图
- [ ] 实现状态管理
- [ ] 实现条件路由
- [ ] 集成所有 Agent

**Week 2：中间件系统**
- [ ] 实现 OutputValidationMiddleware
- [ ] 实现 PatchToolCallsMiddleware
- [ ] 实现 FilesystemMiddleware
- [ ] 实现 RetryMiddleware
- [ ] 集成测试

### 交付物

- LangGraph 主工作流
- 完整的中间件系统

### 验证标准

- 工作流集成测试通过
- 中间件功能验证通过
- 端到端测试通过

### 回滚方案

- Git Tag: `v5.0-orchestration`
- 回滚命令: `git checkout v5.0-orchestration`
- 数据迁移：LangGraph checkpoint 数据

---

## 阶段 6：测试和优化（3 周）

### 目标

完善测试体系，优化性能，确保质量。

### 任务清单

**Week 1：单元测试**
- [ ] 补充单元测试（覆盖率 ≥ 80%）
- [ ] 修复测试失败
- [ ] Code Review

**Week 2：属性测试**
- [ ] 实现 20 个核心属性测试
- [ ] 运行属性测试（每个属性 ≥ 100 用例）
- [ ] 修复发现的问题

**Week 3：性能优化**
- [ ] 性能测试（压力测试、延迟测试）
- [ ] 识别性能瓶颈
- [ ] 优化关键路径
- [ ] 验证性能指标

### 交付物

- 单元测试覆盖率 ≥ 80%
- 20 个属性测试全覆盖
- 性能优化报告

### 验证标准

- 单元测试覆盖率 ≥ 80%
- 属性测试全部通过
- 性能指标达标（延迟 < 3s, token < 700）

### 回滚方案

- Git Tag: `v6.0-testing`
- 回滚命令: `git checkout v6.0-testing`
- 数据迁移：无需迁移

---

## 阶段 7：文档和验收（2 周）

### 目标

完善文档，进行最终验收。

### 任务清单

**Week 1：文档更新**
- [ ] 更新架构文档
- [ ] 更新 API 文档
- [ ] 更新开发指南
- [ ] 更新测试指南

**Week 2：最终验收**
- [ ] 端到端测试
- [ ] 性能验收测试
- [ ] 用户验收测试（UAT）
- [ ] 团队培训

### 交付物

- 完整的技术文档
- 验收测试报告
- 培训材料

### 验证标准

- 文档完整且准确
- 端到端测试通过
- 性能指标达标
- 团队培训完成

### 回滚方案

- Git Tag: `v7.0-final`
- 回滚命令: `git checkout v7.0-final`
- 数据迁移：无需迁移

---

## 总体时间线

```
Week 1-2:   阶段 1 - 基础设施层
Week 3-4:   阶段 2 - Core 和 Platform 层
Week 5-7:   阶段 3 - Agent 组件化
Week 8-10:  阶段 4 - 语义解析器优化
Week 11-12: 阶段 5 - Orchestration 层
Week 13-15: 阶段 6 - 测试和优化
Week 16-17: 阶段 7 - 文档和验收
```

**总工期**：17 周（约 4 个月）

**说明**：
- 删除了 CI/CD、部署、监控等非核心任务
- 专注于代码重构和测试
- 部署相关工作由运维团队负责

---

## 风险管理

### 关键风险

1. **阶段 4 延期**：语义解析器优化复杂度高
   - 缓解：提前进行技术预研
   - 应急：简化优化范围

2. **测试覆盖不足**：时间紧张导致测试不充分
   - 缓解：强制覆盖率检查
   - 应急：延长阶段 6 时间

3. **性能不达标**：优化效果不如预期
   - 缓解：每个阶段进行性能测试
   - 应急：回滚到上一版本

### 质量门禁

每个阶段完成后必须通过以下检查：

- ✅ 单元测试覆盖率 ≥ 80%
- ✅ 集成测试全部通过
- ✅ Code Review 完成
- ✅ 性能测试通过
- ✅ 文档更新完成

---

## 总结

通过 7 个阶段的分步实施，我们可以：

✅ **降低风险**：每个阶段独立可测试和回滚  
✅ **增量交付**：每个阶段都有明确的交付物  
✅ **质量保证**：每个阶段都有验证标准  
✅ **可追溯性**：Git Tag 标记每个阶段  

整个重构过程预计 17 周完成，每个阶段都有明确的目标、任务、交付物和回滚方案。
