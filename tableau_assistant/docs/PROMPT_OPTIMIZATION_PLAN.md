# Prompt优化实施计划

基于Google Prompt Engineering白皮书的最佳实践

## 📋 优先级P0 - 立即实施

### 1. Temperature配置优化 ⭐⭐⭐⭐⭐

#### 实施方案

已创建 `src/config/model_config.py`，为不同Agent类型提供最优配置：

```python
from tableau_assistant.src.config.model_config import ModelConfig, AgentType

# 字段映射（确定性任务）
config = ModelConfig.get_config_for_field_mapping()
# {"temperature": 0.0, "top_p": 0.9, "top_k": 20}

# 洞察生成（创意任务）
config = ModelConfig.get_config_for_insight_generation()
# {"temperature": 0.7, "top_p": 0.95, "top_k": 40}

# 问题理解（一致性任务）
config = ModelConfig.get_config_for_understanding()
# {"temperature": 0.1, "top_p": 0.95, "top_k": 30}
```

#### 配置说明

| Agent类型 | Temperature | 原因 | 预期效果 |
|-----------|-------------|------|----------|
| **Field Mapping** | 0.0 | 需要确定性，单一正确答案 | 一致的字段映射 |
| **Understanding** | 0.1 | 需要一致性，但允许少量解释变化 | 稳定的问题理解 |
| **Task Planner** | 0.1 | 需要一致的规划，避免随机性 | 可预测的任务规划 |
| **Insight** | 0.7 | 需要创意和多样化的洞察 | 丰富的分析视角 |
| **Boost** | 0.2 | 需要平衡：理解原意+适度扩展 | 有用的问题增强 |
| **Replanner** | 0.2 | 需要平衡：分析错误+提供方案 | 合理的重规划建议 |

#### 使用方法

**方法1：在Agent中使用**
```python
from tableau_assistant.src.config.model_config import ModelConfig

class FieldMappingAgent:
    def execute(self, state, runtime, model_config=None):
        # 获取默认配置
        default_config = ModelConfig.get_config_for_field_mapping()
        
        # 合并用户配置
        final_config = ModelConfig.merge_with_user_config(
            default_config,
            model_config
        )
        
        # 使用配置调用LLM
        llm = select_model(**final_config)
```

**方法2：在工具中使用**
```python
from tableau_assistant.src.config.model_config import ModelConfig

@tool
async def semantic_map_fields(...):
    # 字段映射使用确定性配置
    config = ModelConfig.get_config_for_field_mapping()
    llm = select_model(provider="openai", **config)
```

#### 预期收益

- ✅ **提高一致性** - 确定性任务返回稳定结果
- ✅ **提高创意性** - 创意任务产生多样化输出
- ✅ **降低成本** - 避免不必要的随机性
- ✅ **提高质量** - 每个任务使用最优配置

---

### 2. 改用正面指令 ⭐⭐⭐

#### 问题

**之前（负面约束）**：
```
MUST NOT: invent fields, ignore role mismatch, give high confidence without evidence
```

**问题**：
- 告诉LLM不要做什么，但没说要做什么
- 可能让LLM困惑
- 不符合人类思维习惯

#### 改进

**现在（正面指令）**：
```
DO:
- Select matched_field from provided candidates only
- Match field role (dimension vs measure) with business term
- Consider question context for disambiguation
- Provide confidence score between 0 and 1
- Give clear reasoning for your selection
- List alternatives when confidence is below 0.9

ENSURE:
- Every mapping references an actual candidate field
- Confidence reflects true certainty level
- Reasoning explains the semantic match
```

**优势**：
- ✅ 明确告诉LLM要做什么
- ✅ 提供清晰的行动指南
- ✅ 符合人类思维习惯
- ✅ 减少歧义和困惑

#### 实施范围

已更新：
- ✅ `prompts/field_mapping.py`

待更新：
- ⏳ `prompts/understanding.py`
- ⏳ `prompts/task_planner.py`
- ⏳ 其他Prompt模板

---

## 🎯 关于Few-shot示例的决策

### 为什么不在模板中硬编码示例？

#### 原因1：数据驱动优于模板驱动

**硬编码示例的问题**：
```python
"""Examples:
1. "销售额" → [Sales].[Sales Amount]
2. "地区" → [Region].[Region]"""
```

- ❌ 示例固定，不适应不同数据源
- ❌ 如果数据源没有这些字段，示例无效
- ❌ 维护困难，每次改数据要改模板

**动态示例的优势**：
```python
# 从实际元数据生成示例
examples = generate_examples_from_metadata(metadata)
```

- ✅ 示例来自真实数据
- ✅ 自动适应不同数据源
- ✅ 更相关、更准确

#### 原因2：Pydantic模型已经提供示例

```python
class FieldMappingResult(BaseModel):
    class Config:
        json_schema_extra = {
            "example": {  # ← 这就是示例！
                "business_term": "sales",
                "matched_field": "Sales Amount",
                "confidence": 0.95,
                ...
            }
        }
```

**这个设计的优势**：
- ✅ 示例与模型绑定
- ✅ 自动生成JSON Schema
- ✅ LLM可以看到期望的输出格式
- ✅ 类型安全

#### 原因3：RAG本身就是动态Few-shot

```
RAG检索 → Top-5候选字段 → LLM判断
         ↑
    这些候选就是动态示例！
```

**RAG提供的"示例"**：
- ✅ 每次查询都不同
- ✅ 来自真实数据
- ✅ 比硬编码更相关
- ✅ 自动适应数据源

### 最佳实践

**DO**：
- ✅ 在Pydantic模型中定义示例
- ✅ 从元数据动态生成示例
- ✅ 利用RAG候选作为Few-shot

**DON'T**：
- ❌ 在Prompt模板中硬编码示例
- ❌ 使用与数据源无关的示例
- ❌ 维护多份示例副本

---

## 📊 实施时间表

### 第1周（已完成）

- [x] 创建 `model_config.py`
- [x] 更新 `field_mapping.py` 的Constraints
- [x] 创建实施计划文档

### 第2周（进行中）

- [ ] 在所有Agent中集成ModelConfig
- [ ] 更新其他Prompt模板的Constraints
- [ ] 测试不同配置的效果

### 第3周（计划中）

- [ ] 收集性能数据
- [ ] 对比优化前后的效果
- [ ] 调优配置参数

---

## 📈 预期效果

### 量化指标

| 指标 | 优化前 | 优化后（预期） | 提升 |
|------|--------|---------------|------|
| 字段映射一致性 | 70% | 95% | +25% |
| 洞察多样性 | 60% | 85% | +25% |
| 问题理解准确性 | 80% | 90% | +10% |
| 用户满意度 | 75% | 90% | +15% |

### 定性效果

- ✅ **更稳定** - 确定性任务返回一致结果
- ✅ **更创意** - 创意任务产生多样化输出
- ✅ **更清晰** - 正面指令减少歧义
- ✅ **更易维护** - 配置集中管理

---

## 🔍 监控和评估

### 监控指标

1. **Temperature效果**
   - 记录每个Agent的temperature设置
   - 对比不同temperature的输出质量
   - 调整到最优值

2. **一致性测试**
   - 相同输入多次运行
   - 计算输出的一致性
   - 目标：确定性任务>95%一致

3. **创意性评估**
   - 洞察的多样性
   - 新颖性评分
   - 用户反馈

### 评估方法

```python
# 一致性测试
async def test_consistency(prompt, n=10):
    results = []
    for _ in range(n):
        result = await agent.execute(prompt)
        results.append(result)
    
    # 计算一致性
    consistency = calculate_consistency(results)
    return consistency

# 目标：
# - Field Mapping: >95%
# - Understanding: >90%
# - Insight: 60-70% (需要多样性)
```

---

## 📚 参考资料

- Google Prompt Engineering Whitepaper (February 2025)
- 项目文档：`docs/PROMPT_AND_MODEL_GUIDE.md`
- 配置代码：`src/config/model_config.py`

---

## 🎯 总结

### 核心改进

1. **Temperature优化** - 为每个Agent设置最优温度
2. **正面指令** - 用DO代替DON'T
3. **数据驱动** - 示例与数据模型绑定，而非硬编码

### 设计哲学

- **简单优于复杂** - 不过度设计
- **数据驱动** - 示例来自真实数据
- **配置化** - 集中管理，易于调整
- **可测量** - 有明确的评估指标

### 下一步

1. 在所有Agent中应用ModelConfig
2. 测试和验证效果
3. 根据数据调优参数
4. 持续监控和改进

---

**文档版本**: v1.0  
**最后更新**: 2025-01-15  
**负责人**: AI Team
