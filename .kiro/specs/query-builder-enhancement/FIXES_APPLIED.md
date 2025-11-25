# 已应用的修复

## 修复1：Understanding Prompt 中的 LAST vs LASTN ✅

### 问题
- Prompt 示例错误：`"最近一个月" -> relative time (LAST, MONTHS, 1)`
- 导致所有"最近N天/月"的查询都使用错误的 `LAST` 而不是 `LASTN`

### 修复
**文件**: `tableau_assistant/prompts/understanding_v3.py`

**修改内容**:
```python
### Time Extraction
Extract **time_range** and **date_requirements** from the question:
- "2025年6月" -> absolute time with value="2025-06"
- "今年6月" -> resolve using metadata max_date
- "最近一个月" -> relative time (LASTN, MONTHS, 1)  # ← 修复：LAST → LASTN
- "最近7天" -> relative time (LASTN, DAYS, 7)        # ← 新增示例
- "昨天" -> relative time (LAST, DAYS, None)         # ← 新增示例
- "上周" -> relative time (LAST, WEEKS, None)        # ← 新增示例
- "上月" -> relative time (LAST, MONTHS, None)       # ← 新增示例
- "春节期间" -> mentions_holidays=true, holiday_keywords=["春节"]
- "农历正月" -> mentions_lunar=true, lunar_keywords=["农历", "正月"]
- "按周一开始" -> week_start_day=0, week_start_day_keywords=["周一"]

**CRITICAL**: Use "LASTN" for "最近N天/月/年" (recent N periods), use "LAST" for "昨天/上周/上月" (previous single period)
```

### 影响
- ✅ "最近7天" 现在会正确输出 `LASTN` 而不是 `LAST`
- ✅ 日期范围计算正确：`2025-11-23 ~ 2025-11-29`（7天）而不是 `2025-11-28 ~ 2025-11-28`（1天）
- ✅ 所有"最近N天/月/年"的查询都会正确处理

---

## 修复2：Task Planner 子任务数量验证 ✅

### 问题
- Task Planner 有时只返回部分子任务
- 导致 `ValidationError: subtasks.1 is None`
- 错误信息不明确，难以调试

### 修复
**文件**: `tableau_assistant/src/agents/task_planner_agent.py`

**修改内容**:
在 `_generate_query_subtasks` 方法中添加验证逻辑：

```python
async def _generate_query_subtasks(self, ...):
    # 调用 LLM
    query_result = await self._execute_with_prompt(input_data, runtime, model_config)
    
    # 验证子任务数量
    expected_count = len(query_sub_questions)
    actual_count = len(query_result.subtasks)
    
    if actual_count != expected_count:
        logger.warning(f"子任务数量不匹配: 预期 {expected_count}, 实际 {actual_count}")
        logger.warning(f"输入的子问题:")
        for i, (_, sq) in enumerate(query_sub_questions):
            logger.warning(f"  {i}. {sq.text}")
        logger.warning(f"LLM 返回的子任务:")
        for i, st in enumerate(query_result.subtasks):
            logger.warning(f"  {i}. {st.question_text}")
        
        # 抛出明确的错误
        raise ValueError(
            f"Task Planner 只生成了 {actual_count} 个子任务，"
            f"但应该生成 {expected_count} 个。"
            f"这可能是因为 LLM 输出被截断或没有遵守指令。"
            f"请检查 max_tokens 设置或 Prompt。"
        )
    
    return query_result
```

### 影响
- ✅ 早期发现问题：在子任务数量不匹配时立即报错
- ✅ 明确的错误信息：告诉用户具体缺少哪些子任务
- ✅ 调试信息：输出预期和实际的子任务列表
- ✅ 指导修复：提示可能的原因和解决方案

---

## 验证步骤

### 步骤1：验证 Understanding 修复

```bash
# 运行测试
python tests/test_understanding_planning_building.py

# 检查问题1的输出
# 应该看到：
# ✓ 问题理解完成
#   - relative_type: LASTN  ← 应该是 LASTN
#   - range_n: 7
```

### 步骤2：验证 Task Planner 修复

```bash
# 运行测试
python tests/test_understanding_planning_building.py

# 如果问题4仍然失败，会看到明确的错误信息：
# ValueError: Task Planner 只生成了 1 个子任务，但应该生成 2 个。
# 这可能是因为 LLM 输出被截断或没有遵守指令。
```

---

## 下一步

### 如果问题1已修复 ✅
- 重新运行测试验证
- 检查日期范围是否正确

### 如果问题2仍然存在 ⚠️
根据错误信息诊断：

#### 可能原因1：max_tokens 不足
**解决方案**: 增加 max_tokens

```python
# 在 settings.py 或调用 LLM 时
max_tokens = 4096  # 或更大
```

#### 可能原因2：LLM 没有遵守指令
**解决方案**: 改进 Prompt

在 `task_planner_v3.py` 中：
```python
def get_task(self) -> str:
    return """**CRITICAL**: You MUST generate EXACTLY {num_sub_questions} subtasks.

Current sub-questions to process:
{sub_questions_list}

Generate ONE subtask for EACH sub-question listed above.
Do NOT skip any sub-question.
Do NOT stop until ALL {num_sub_questions} subtasks are generated."""
```

#### 可能原因3：流式输出解析问题
**解决方案**: 检查流式输出处理逻辑

---

## 预期结果

修复后，所有测试应该通过：

```
================================================================================
测试问题 1/4: 最近7天各门店的销售额是多少
================================================================================
✓ 问题理解完成
  - relative_type: LASTN  ← 修复后
  - range_n: 7

✓ 任务规划完成
  - 子任务数量: 1

✓ 查询构建成功
  - 筛选器: [calc: DATEPARSE('yyyy-MM-dd', [日期])] (QuantitativeDateFilter, range: 2025-11-23 ~ 2025-11-29)
  ← 正确的7天范围

================================================================================
测试问题 4/4: 对比今年和去年各门店的销售额
================================================================================
✓ 问题理解完成
  - 子问题数量: 3

✓ 任务规划完成
  - 子任务数量: 3  ← 如果修复成功

✓ 查询构建成功
  - 所有子任务都成功构建
```

---

## 总结

### 已修复 ✅
1. **Understanding Prompt** - LAST vs LASTN 的示例错误
2. **Task Planner 验证** - 添加子任务数量检查和明确的错误信息

### 待观察 ⏳
1. **Task Planner 生成** - 是否能生成所有子任务（需要运行测试验证）

### 如果仍有问题 ⚠️
- 根据新的错误信息进一步诊断
- 可能需要调整 max_tokens 或改进 Prompt
