# 剩余任务清单

## 📊 任务完成情况

### ✅ 已完成 (6/12)
- [x] 任务 1: 创建基础 Prompt 架构
- [x] 任务 2: 创建基础 Agent 架构  
- [x] 任务 3: 重构 Question Boost Prompt
- [x] 任务 4: 重构 Understanding Prompt
- [x] 任务 5: 重构 Task Planner Prompt
- [x] 任务 8: 更新 Task Planner Agent

### ❌ 待完成 (6/12)
- [ ] 任务 6: 更新 Question Boost Agent
- [ ] 任务 7: 更新 Understanding Agent
- [ ] 任务 9: 实现元数据预加载
- [ ] 任务 10: 添加验证工具
- [ ] 任务 11: 更新测试套件
- [ ] 任务 12: 文档和清理

---

## 📝 详细任务说明

### ❌ 任务 6: 更新 Question Boost Agent

**目标**: 更新 Question Boost Agent 使用新的 BaseVizQLAgent 架构

**需要做的事情**:
1. 更新 `tableau_assistant/src/agents/question_boost_agent.py`
2. 让 QuestionBoostAgent 继承 BaseVizQLAgent
3. 实现 `_prepare_input_data()` 方法
   - 格式化问题和元数据
4. 实现 `_process_result()` 方法
   - 包装 QuestionBoost 结果到状态
5. 更新 agent node 函数使用新的 agent 类

**相关需求**: 2.1, 5.3

**预计工作量**: 中等

---

### ❌ 任务 7: 更新 Understanding Agent

**目标**: 更新 Understanding Agent 使用新的 BaseVizQLAgent 架构

**需要做的事情**:
1. 更新 `tableau_assistant/src/agents/understanding_agent.py`
2. 让 UnderstandingAgent 继承 BaseVizQLAgent
3. 实现 `_prepare_input_data()` 方法
   - 格式化问题和元数据
4. 实现 `_process_result()` 方法
   - 包装 QuestionUnderstanding 结果
   - **添加 sub_question_relationships 验证**
5. 更新 agent node 函数使用新的 agent 类

**相关需求**: 2.2, 3.1, 4.1, 5.4

**预计工作量**: 中等

**特别注意**: 需要添加子问题关系验证逻辑

---

### ❌ 任务 9: 实现元数据预加载

**目标**: 将元数据和维度层级推断移到问题处理之前

**需要做的事情**:
1. 更新 `tableau_assistant/tests/test_boost_understanding_planning.py`
2. 在测试开始时预加载 metadata 和 dimension_hierarchy
3. 使用预加载的数据初始化状态
4. 从各个 agent 调用中移除冗余的元数据加载

**相关需求**: 1.1, 1.2, 1.3, 1.4, 1.5, 8.1, 8.2

**预计工作量**: 小

**示例结构**:
```python
# 测试开始时
metadata = load_metadata()
dimension_hierarchy = infer_dimension_hierarchy(metadata)

# 初始化状态
state = VizQLState(
    metadata=metadata,
    dimension_hierarchy=dimension_hierarchy,
    ...
)

# Agent 直接使用状态中的数据
```

---

### ❌ 任务 10: 添加验证工具

**目标**: 创建统一的验证工具函数

**需要做的事情**:
1. 创建 `tableau_assistant/src/utils/validation.py`
2. 实现 `validate_understanding()` 函数
   - 验证子问题关系的完整性
   - 验证关系索引的有效性
   - 验证 comparison 关系的 comparison_dimension
3. 实现 `validate_query_plan()` 函数
   - 验证所有字段名存在于元数据中
   - 验证字段类型使用正确
   - 验证过滤器值的有效性
4. 实现 `validate_relationships()` 函数
   - 验证子问题关系的逻辑一致性

**相关需求**: 2.4, 2.5, 2.6, 4.1, 8.3, 8.4, 8.5

**预计工作量**: 中等

**示例代码**:
```python
def validate_understanding(
    understanding: QuestionUnderstanding
) -> List[str]:
    """验证 QuestionUnderstanding 的业务逻辑"""
    errors = []
    
    # 检查多个子问题必须有关系
    if len(understanding.sub_questions) > 1:
        if not understanding.sub_question_relationships:
            errors.append("Multiple sub-questions must have relationships")
    
    # 检查关系索引有效性
    for rel in understanding.sub_question_relationships:
        for idx in rel.question_indices:
            if idx >= len(understanding.sub_questions):
                errors.append(f"Invalid question index: {idx}")
    
    return errors

def validate_query_plan(
    plan: QueryPlanningResult,
    metadata: dict
) -> List[str]:
    """验证 QueryPlanningResult 的字段映射"""
    errors = []
    valid_fields = {f["fieldCaption"] for f in metadata["fields"]}
    
    for subtask in plan.subtasks:
        for field in subtask.fields:
            if field.fieldCaption not in valid_fields:
                errors.append(
                    f"Unknown field: {field.fieldCaption}"
                )
    
    return errors
```

---

### ❌ 任务 11: 更新测试套件

**目标**: 更新现有测试以使用新架构

**需要做的事情**:
1. 更新现有测试使用新的 prompt 和 agent 类
2. 添加自动 Schema 注入的测试
3. 添加子问题关系验证的测试
4. 添加字段映射验证的测试（业务术语 → 技术字段）
5. 验证所有测试在新架构下通过

**相关需求**: 8.3, 8.4, 8.5

**预计工作量**: 大

**需要更新的测试文件**:
- `test_boost_understanding_planning.py`
- `test_v2_prompts.py`
- 其他相关测试文件

---

### ❌ 任务 12: 文档和清理

**目标**: 完善文档并清理旧代码

**需要做的事情**:
1. 更新 README 或文档以反映新架构
2. 为新的基类添加完整的内联文档
3. 标记或移除旧的 prompt 文件（v1）
4. 添加迁移指南（v1 → v2 → v3）
5. 创建最佳实践文档

**相关需求**: All

**预计工作量**: 中等

**文档清单**:
- [ ] 更新主 README
- [ ] 添加架构图
- [ ] 创建迁移指南
- [ ] 添加最佳实践
- [ ] 标记废弃的文件

---

## 🎯 推荐执行顺序

### 阶段 1: Agent 更新（优先）
1. **任务 6**: 更新 Question Boost Agent
2. **任务 7**: 更新 Understanding Agent

**原因**: 这两个任务是核心功能，需要先完成才能进行后续测试

### 阶段 2: 基础设施
3. **任务 10**: 添加验证工具
4. **任务 9**: 实现元数据预加载

**原因**: 验证工具和元数据预加载是测试的基础

### 阶段 3: 测试和文档
5. **任务 11**: 更新测试套件
6. **任务 12**: 文档和清理

**原因**: 在所有功能完成后进行全面测试和文档整理

---

## 📈 进度追踪

```
总进度: 50% (6/12 完成)

阶段 1 - 基础架构: ████████████████████ 100% (4/4)
  ✅ 任务 1: Prompt 基础架构
  ✅ 任务 2: Agent 基础架构
  ✅ 任务 3: Question Boost Prompt
  ✅ 任务 4: Understanding Prompt

阶段 2 - Prompt 重构: ████████████████████ 100% (2/2)
  ✅ 任务 5: Task Planner Prompt
  ✅ 任务 8: Task Planner Agent

阶段 3 - Agent 更新: ░░░░░░░░░░░░░░░░░░░░ 0% (0/2)
  ❌ 任务 6: Question Boost Agent
  ❌ 任务 7: Understanding Agent

阶段 4 - 基础设施: ░░░░░░░░░░░░░░░░░░░░ 0% (0/2)
  ❌ 任务 9: 元数据预加载
  ❌ 任务 10: 验证工具

阶段 5 - 测试和文档: ░░░░░░░░░░░░░░░░░░░░ 0% (0/2)
  ❌ 任务 11: 测试套件
  ❌ 任务 12: 文档和清理
```

---

## 🚀 下一步行动

### 立即可以开始的任务

1. **任务 6: 更新 Question Boost Agent** ⭐ 推荐
   - 依赖: 无（基础架构已完成）
   - 影响: 中等
   - 难度: 中等

2. **任务 10: 添加验证工具** ⭐ 推荐
   - 依赖: 无
   - 影响: 高（其他任务需要）
   - 难度: 中等

### 需要等待的任务

- **任务 7**: 需要任务 6 完成后参考
- **任务 9**: 可以独立进行，但最好在 Agent 更新后
- **任务 11**: 需要任务 6, 7, 9, 10 完成
- **任务 12**: 需要所有功能任务完成

---

## 💡 建议

1. **优先完成 Agent 更新**（任务 6, 7）
   - 这是核心功能
   - 完成后可以进行端到端测试

2. **并行进行验证工具开发**（任务 10）
   - 独立性强
   - 其他任务会用到

3. **最后进行测试和文档**（任务 11, 12）
   - 确保所有功能稳定后再进行
   - 可以发现集成问题

---

**更新日期**: 2024
**当前状态**: 50% 完成
**预计剩余工作量**: 约 3-4 个工作日
