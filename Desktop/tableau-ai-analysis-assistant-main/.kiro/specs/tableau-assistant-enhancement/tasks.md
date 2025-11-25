# Tableau Assistant 系统化增强 - 任务列表

## 📖 文档导航

### 🔗 相关文档
- **[需求文档](./requirements.md)** - 功能需求和验收标准
- **[设计文档](./design.md)** - 系统架构和组件设计

---

## 实施说明

### 任务标记说明
- `[ ]` - 未开始
- `[x]` - 已完成
- `*` - 可选任务（测试相关）

### 测试策略
- 所有任务（包括测试）都是必需的
- 单元测试和属性测试是互补的：单元测试验证具体示例，属性测试验证通用规则
- 属性测试使用 Hypothesis 框架，每个测试运行 100 次迭代
- 每个功能实现后立即编写对应的测试

---

## 任务列表

### 第一阶段：任务调度器与查询结果缓存（核心功能）

- [ ] 1. 实现任务调度器核心功能
  - 实现 TaskScheduler 类，支持自动调度 QuerySubTask
  - 实现依赖分析（`_analyze_dependencies`）
  - 实现拓扑排序（`_topological_sort`）
  - 实现并行执行（`_execute_batch`，使用 asyncio.Semaphore）
  - 实现单任务执行（`_execute_single_task`）
  - 集成 QueryExecutor 执行单个查询
  - 支持进度回调（`progress_callback`）
  - _Requirements: 1.4_

- [ ] 1.1 实现查询结果缓存
  - 在 PersistentStore 中添加查询结果缓存表
  - 实现缓存键生成（基于查询内容的哈希）
  - 实现缓存读取（`get_cached_result`）
  - 实现缓存写入（`set_cached_result`）
  - 设置 TTL 为 1-2 小时
  - 实现缓存命中率统计
  - _Requirements: 1.5_

- [ ] 1.2 编写任务调度器属性测试
  - **Property 5: 任务依赖顺序正确性**
  - **Validates: Requirements 1.4**

- [ ] 1.3 编写任务调度器属性测试
  - **Property 6: 并行任务不超过并发限制**
  - **Validates: Requirements 1.4**

- [ ] 1.4 编写任务调度器属性测试
  - **Property 7: 所有任务都被执行**
  - **Validates: Requirements 1.4**

- [ ] 1.5 编写查询缓存属性测试
  - **Property 4: 缓存一致性**
  - **Validates: Requirements 1.5, 1.10**

- [ ] 2. 集成任务调度器到工作流
  - 在 vizql_workflow.py 中添加任务调度节点
  - 在 Planning Agent 后添加调度器节点
  - 传递 QuerySubTask 列表到调度器
  - 收集所有查询结果并更新状态
  - 添加进度流式输出（通过 astream_events）
  - _Requirements: 1.4_

- [ ] 3. 实现累积洞察机制
  - 实现 Insight Agent（分析单个查询结果）
  - 实现 Insight Coordinator（智能合成所有洞察）
  - 定义 Insight 和 FinalInsight 数据模型
  - 在任务调度器中集成累积洞察
  - 并行启动多个 Insight Agent（使用 asyncio）
  - _Requirements: 1.4（累积洞察支持）_

- [ ] 3.1 实现重规划机制
  - 实现 Replan Agent（判断是否需要重规划）
  - 定义 ReplanDecision 数据模型
  - 在工作流中添加重规划节点
  - 实现条件边（continue vs finish）
  - 支持最大轮次限制（默认3轮）
  - _Requirements: 1.4（重规划支持）_

- [ ] 3.2 集成累积洞察和重规划到工作流
  - 在 vizql_workflow.py 中添加 accumulate_insights 节点
  - 在 vizql_workflow.py 中添加 replan 节点
  - 连接节点：planning → task_scheduling → accumulate_insights → replan
  - 实现重规划条件边（回到 understanding 或进入 summary）
  - 更新 VizQLState 数据结构（添加 insights、final_insight、replan_decision）
  - _Requirements: 1.4_

- [ ] 4. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，询问用户是否有问题

---

### 第二阶段：查询验证和错误修正

- [ ] 5. 实现查询验证功能
  - 在 QueryExecutor 中添加 `_validate_query_plan` 方法
  - 实现字段存在性验证（检查字段是否在元数据中）
  - 实现相似字段搜索（使用 difflib.SequenceMatcher）
  - 实现聚合函数验证（检查聚合函数是否适用于字段类型）
  - 返回结构化的验证错误（字段名、错误类型、建议）
  - _Requirements: 2.1, 2.2, 2.3_

- [ ] 5.1 编写查询验证属性测试
  - **Property 8: 不存在字段被检测**
  - **Validates: Requirements 2.1**

- [ ] 5.2 编写查询验证属性测试
  - **Property 9: 相似字段搜索有效性**
  - **Validates: Requirements 2.2**

- [ ] 5.3 编写查询验证属性测试
  - **Property 10: 聚合函数类型检查**
  - **Validates: Requirements 2.3**

- [ ] 6. 实现错误修正功能
  - 在 QueryExecutor 中添加 `_analyze_and_correct` 方法
  - 实现错误信息提取（`_extract_error_info`）
  - 实现 LLM 驱动的错误分析（构建修正提示）
  - 实现修正方案解析（`_parse_correction_response`）
  - 实现智能重试机制（最多 3 次）
  - 记录修正信息到 SQLite（修正前后的查询计划、修正原因）
  - _Requirements: 2.4, 2.5, 2.7_

- [ ] 6.1 编写错误修正属性测试
  - **Property 11: 重试次数限制**
  - **Validates: Requirements 2.5**

- [ ] 6.2 编写错误修正属性测试
  - **Property 12: 修正记录完整性**
  - **Validates: Requirements 2.7**

- [ ] 6.3 编写错误统计属性测试
  - **Property 13: 错误统计准确性**
  - **Validates: Requirements 2.8**

- [ ] 7. 集成验证和修正到查询执行流程
  - 在 `execute_query` 中添加查询前验证
  - 在查询失败时触发错误修正
  - 实现重试循环（验证 → 执行 → 失败 → 修正 → 重试）
  - 添加详细的日志记录
  - _Requirements: 2.1-2.8_

- [ ] 8. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，询问用户是否有问题

---

### 第三阶段：上下文智能管理

- [ ] 9. 实现元数据过滤功能
  - 在 MetadataManager 中添加 `filter_by_categories` 方法
  - 从 Understanding 结果中提取涉及的 Category
  - 只保留相关 Category 的维度字段
  - 保留所有度量字段
  - 记录过滤前后的字段数量
  - _Requirements: 3.3_

- [ ] 9.1 编写元数据过滤属性测试
  - **Property 14: Category 过滤正确性**
  - **Validates: Requirements 3.3**

- [ ] 10. 实现 Token 计算和预算管理
  - 安装 tiktoken 库
  - 在 BaseAgent 中添加 `estimate_tokens` 方法
  - 实现 Token 预算管理（默认 8000 tokens）
  - 按优先级裁剪上下文（元数据 > 对话历史 > 示例）
  - 记录 Token 使用情况
  - _Requirements: 3.4, 3.5, 3.7_

- [ ] 10.1 编写 Token 计算属性测试
  - **Property 15: Token 计算准确性**
  - **Validates: Requirements 3.4**

- [ ] 10.2 编写 Token 预算属性测试
  - **Property 16: Token 预算遵守**
  - **Validates: Requirements 3.5**

- [ ] 10.3 编写上下文记录属性测试
  - **Property 18: 上下文记录完整性**
  - **Validates: Requirements 3.7**

- [ ] 11. 实现对话历史压缩
  - 在 BaseAgent 中添加 `compress_history` 方法
  - 保留最近 5 轮完整对话
  - 使用 LLM 压缩早期对话为摘要
  - 确保摘要长度不超过原内容的 30%
  - 集成到 vizql_workflow.py 中
  - _Requirements: 3.6_

- [ ] 11.1 编写对话历史压缩属性测试
  - **Property 17: 对话历史压缩率**
  - **Validates: Requirements 3.6**

- [ ] 12. 评估上下文优化效果
  - 对比使用和不使用上下文管理的 Token 消耗
  - 统计 Token 消耗减少比例（目标：50%）
  - 记录优化效果到日志
  - _Requirements: 3.8_

- [ ] 12.1 编写优化效果属性测试
  - **Property 19: Token 消耗优化效果**
  - **Validates: Requirements 3.8**

- [ ] 13. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，询问用户是否有问题

---

### 第四阶段：会话管理完善

- [ ] 14. 配置 SQLite Checkpointer
  - 将 InMemorySaver 替换为 SQLite Checkpointer
  - 设置数据库路径（`data/checkpoints.db`）
  - 配置自动清理过期会话（30 天）
  - _Requirements: 4.1_

- [ ] 15. 实现会话管理功能
  - 实现会话创建（生成唯一 session_id）
  - 实现会话保存（持久化状态、对话历史、工具调用记录）
  - 实现会话恢复（从 Checkpointer 加载）
  - 实现会话列表（返回用户的所有会话）
  - 实现会话搜索（按时间、关键词、数据源、状态）
  - 实现会话删除（删除所有相关数据）
  - _Requirements: 4.2-4.7_

- [ ] 15.1 编写会话 ID 唯一性属性测试
  - **Property 20: 会话 ID 唯一性**
  - **Validates: Requirements 4.2**

- [ ] 15.2 编写会话持久化属性测试
  - **Property 21: 会话持久化完整性**
  - **Validates: Requirements 4.3**

- [ ] 15.3 编写会话恢复属性测试
  - **Property 22: 会话恢复一致性（Round-trip）**
  - **Validates: Requirements 4.4**

- [ ] 15.4 编写会话列表属性测试
  - **Property 23: 会话列表完整性**
  - **Validates: Requirements 4.5**

- [ ] 15.5 编写会话搜索属性测试
  - **Property 24: 会话搜索正确性**
  - **Validates: Requirements 4.6**

- [ ] 15.6 编写会话删除属性测试
  - **Property 25: 会话删除完整性**
  - **Validates: Requirements 4.7**

- [ ] 16. 实现会话导出和重放
  - 实现会话导出为 JSON
  - 实现会话重放（重新执行历史对话）
  - 对比原始结果和重放结果
  - _Requirements: 4.8, 4.9_

- [ ] 16.1 编写会话导出属性测试
  - **Property 26: 会话导出完整性**
  - **Validates: Requirements 4.8**

- [ ] 17. 实现会话管理 API
  - 实现 POST /api/sessions（创建会话）
  - 实现 GET /api/sessions（列出会话）
  - 实现 GET /api/sessions/{session_id}（获取会话详情）
  - 实现 DELETE /api/sessions/{session_id}（删除会话）
  - 实现 POST /api/sessions/{session_id}/restore（恢复会话）
  - 实现 GET /api/sessions/{session_id}/export（导出会话）
  - 实现 POST /api/sessions/{session_id}/replay（重放会话）
  - _Requirements: 4.10_

- [ ] 18. Checkpoint - 确保所有测试通过
  - 确保所有测试通过，询问用户是否有问题

---

## 实施优先级

### 🔴 第一阶段：核心功能（4-5 周）
- 任务 1-4：任务调度器、查询结果缓存、累积洞察、重规划
- **预期效果**：
  - 自动调度执行，提升可维护性
  - 通过缓存解决上下文长度问题
  - 重规划时避免重复查询（150x 提升）
  - 多 AI 并行分析 + 智能合成洞察
  - 重规划时避免重复查询（150x 提升）

### 🔴 第二阶段：查询验证和错误修正（2-3 周）
- 任务 5-8：查询验证和错误修正
- **预期效果**：查询成功率提升 20-30%

### 🔴 第三阶段：上下文智能管理（2-3 周）
- 任务 9-13：上下文智能管理
- **预期效果**：Token 消耗减少 50%

### 🟡 第四阶段：会话管理完善（2-3 周）
- 任务 14-18：会话管理
- **预期效果**：支持会话持久化和恢复

---

## 预期成果

### 量化指标

| 指标 | 当前 | 目标 | 提升 |
|------|------|------|------|
| **查询成功率** | ~70% | ~90% | **+20-30%** |
| Token 消耗 | 100% | 50% | -50% |
| 任务执行自动化 | 0% | 100% | +100% |
| **查询结果缓存** | ❌ | ✅ | **新功能** |
| **缓存命中时查询速度** | 5s | 0.1s | **50x** |
| **重规划时查询速度** | 15s | 0.1s | **150x** |
| **自动错误修正** | ❌ | ✅ | **新功能** |
| 会话持久化 | ❌ | ✅ | 新功能 |

---

**文档版本**: 1.0  
**创建时间**: 2025-11-20  
**作者**: Kiro AI Assistant  
**状态**: 待审核
