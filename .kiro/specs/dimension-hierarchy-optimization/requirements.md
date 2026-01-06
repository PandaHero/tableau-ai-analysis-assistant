# Dimension Hierarchy Agent 优化需求文档

## 背景

Dimension Hierarchy Agent 负责推断维度字段的层级属性。当前实现存在性能问题：

| 问题 | 影响 |
|------|------|
| 每个字段都调用 LLM | 20 字段 = 4 次 LLM 调用，耗时 ~6s |
| RAG 仅用于 few-shot | 增加了复杂度，但没有减少 LLM 调用 |
| 逐个 embedding 计算 | N 字段 = N 次 API 调用 |

## 目标

采用 **RAG 优先 + LLM 兜底** 方案：
- RAG 相似度 >= 0.92 → 直接复用历史结果（跳过 LLM）
- RAG 相似度 < 0.92 → LLM 推断 → 存入 RAG

**预期效果**：
- 耗时减少 60-90%（从 6s 降到 0.6-1.5s）
- 成本减少 80-95%（从 $1.00 降到 $0.05-0.20）

## 需求

### 需求 1: RAG 优先推断

**用户故事**: 作为系统架构师，我希望优先使用 RAG 复用历史结果，减少 LLM 调用。

#### 验收标准

1. WHEN RAG 相似度 >= 0.92 THEN THE System SHALL 直接复用历史推断结果
2. WHEN RAG 相似度 < 0.92 THEN THE System SHALL 调用 LLM 推断
3. WHEN LLM 推断完成且置信度 >= 0.85 THEN THE System SHALL 将结果存入 RAG 索引
4. THE System SHALL 记录 RAG 命中率统计

### 需求 2: 批量 Embedding

**用户故事**: 作为系统架构师，我希望批量计算 embedding，减少 API 调用次数。

#### 验收标准

1. THE System SHALL 支持批量 embedding 计算（单次 API 调用）
2. WHEN 有 N 个字段需要检索 THEN THE System SHALL 将 embedding 调用从 N 次降到 1 次
3. THE System SHALL 支持批量向量检索

### 需求 3: 种子数据初始化

**用户故事**: 作为系统架构师，我希望预置常见维度模式，解决冷启动问题。

#### 验收标准

1. THE System SHALL 预置 30+ 常见维度模式（时间、地理、产品、客户）
2. WHEN RAG 索引为空 THEN THE System SHALL 自动初始化种子数据
3. THE System SHALL 支持中英文字段名

### 需求 4: 性能监控

**用户故事**: 作为系统架构师，我希望监控优化效果。

#### 验收标准

1. THE System SHALL 记录以下指标：
   - RAG 命中率
   - LLM 调用次数
   - 推断延迟
   - 估算节省成本
2. THE System SHALL 支持指标导出

## 非功能需求

### 性能需求

| 指标 | 当前 | 目标 |
|------|------|------|
| 20 字段耗时 | ~6s | < 2s（80% 命中） |
| 成本 | ~$1.00 | < $0.20 |
| RAG 命中率 | 0% | > 80%（稳定后） |

### 质量需求

1. 推断准确率不低于当前水平
2. RAG 复用结果的置信度 >= 0.9

## 实施优先级

| 需求 | 优先级 | 工时 |
|------|--------|------|
| 需求 1: RAG 优先推断 | P0 | 1d |
| 需求 2: 批量 Embedding | P0 | 1d |
| 需求 3: 种子数据 | P1 | 0.5d |
| 需求 4: 性能监控 | P2 | 0.5d |

**总计：3 天**
