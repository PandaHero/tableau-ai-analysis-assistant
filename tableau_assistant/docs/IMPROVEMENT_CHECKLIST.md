# Tableau Assistant 改进实施清单

> 基于 `INDUSTRY_DEEP_COMPARISON.md` 和 `EXTENDED_INDUSTRY_ANALYSIS.md` 的分析结果

---

## P0 - 立即实施（1-2周）

### 1. 训练数据管理
- [ ] 实现 `GoldenQuery` 模型
- [ ] 实现 `TrainingDataStore` 类
- [ ] 添加向量存储集成（FAISS）
- [ ] 实现用户反馈收集 API
- [ ] 实现自动学习逻辑

**文件位置**: `tableau_assistant/src/training/`

### 2. 自我纠错机制
- [ ] 实现 `QueryChecker` 类（执行前检查）
- [ ] 实现 `SelfCorrector` 类（执行后纠错）
- [ ] 实现错误分类逻辑
- [ ] 集成到 Execute 节点

**文件位置**: `tableau_assistant/src/agents/self_correction/`

### 3. 动态 Few-Shot
- [ ] 修改 SemanticParser 支持动态示例
- [ ] 实现 DAIL Selection 策略
- [ ] 优化 Prompt 组织（减少 Token）

**文件位置**: `tableau_assistant/src/agents/semantic_parser/`

---

## P1 - 短期实施（2-4周）

### 4. 同义词系统
- [ ] 实现 `SynonymStore` 类
- [ ] 实现同义词解析逻辑
- [ ] 实现自动同义词建议
- [ ] 添加管理 API

**文件位置**: `tableau_assistant/src/semantic/`

### 5. 值级别检索
- [ ] 实现 `ValueRetriever` 类
- [ ] 建立 MinHash + LSH 索引
- [ ] 集成到 SemanticParser
- [ ] 添加索引构建脚本

**文件位置**: `tableau_assistant/src/retrieval/`

### 6. 置信度评分
- [ ] 实现 `ConfidenceCalculator` 类
- [ ] 定义置信度维度和权重
- [ ] 添加到工作流状态
- [ ] 实现基于置信度的决策

**文件位置**: `tableau_assistant/src/evaluation/`

### 7. Schema 剪枝
- [ ] 实现 `SchemaSelector` 类
- [ ] 实现自适应剪枝逻辑
- [ ] 集成到 FieldMapper

**文件位置**: `tableau_assistant/src/agents/field_mapper/`

---

## P2 - 中期实施（1-2月）

### 8. 语义层配置
- [ ] 设计语义层配置格式
- [ ] 实现配置加载和解析
- [ ] 集成到数据模型

### 9. LLM 单元测试
- [ ] 实现 `LLMUnitTester` 类
- [ ] 实现测试生成逻辑
- [ ] 实现测试运行逻辑
- [ ] 集成到验证流程

**文件位置**: `tableau_assistant/src/validation/`

### 10. 多候选策略
- [ ] 修改 QueryBuilder 支持多候选
- [ ] 实现候选排序逻辑
- [ ] 集成 LLM 单元测试选择

### 11. 建议后续问题
- [ ] 实现问题建议生成
- [ ] 集成到 Insight 节点
- [ ] 添加到 API 响应

---

## 依赖关系

```
训练数据管理 ──┬──▶ 动态 Few-Shot
              │
              └──▶ 自我纠错机制

同义词系统 ──────▶ SemanticParser 增强

值级别检索 ──────▶ SemanticParser 增强

置信度评分 ◀────── Schema 剪枝
              │
              └──── LLM 单元测试
```

---

## 验收标准

| 改进项 | 验收标准 |
|--------|---------|
| 训练数据管理 | 可添加/检索 Golden Query |
| 自我纠错 | 执行错误后自动修复成功率 > 50% |
| 动态 Few-Shot | 准确率提升 > 10% |
| 同义词系统 | 同义词解析准确率 > 90% |
| 值级别检索 | 过滤条件准确率提升 > 5% |
| 置信度评分 | 低置信度查询人工确认率 > 80% |
| Schema 剪枝 | Token 消耗减少 > 30% |
| LLM 单元测试 | 测试通过率与准确率相关性 > 0.7 |

---

## 参考文档

- `INDUSTRY_DEEP_COMPARISON.md` - 6个开源项目深度分析
- `EXTENDED_INDUSTRY_ANALYSIS.md` - 商业产品和学术研究分析
- `IMPROVEMENT_IMPLEMENTATION_GUIDE.md` - 详细实现代码
- `MODULE_ARCHITECTURE_DEEP_ANALYSIS.md` - 现有架构分析
