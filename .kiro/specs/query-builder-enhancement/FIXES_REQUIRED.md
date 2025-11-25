# 需要修复的问题

## 问题1：Understanding Agent 输出错误的 relative_type ✗ 高优先级

### 问题描述
- 用户问题："最近7天各门店的销售额是多少"
- Understanding 输出：`relative_type="LAST"`, `range_n=7`
- **应该输出**：`relative_type="LASTN"`, `range_n=7`

### 根本原因
**Understanding Prompt 中的示例错误**

文件：`tableau_assistant/prompts/understanding_v3.py` 第162行

```python
# 错误的示例
- "最近一个月" -> relative time (LAST, MONTHS, 1)
```

应该是：
```python
# 正确的示例
- "最近一个月" -> relative time (LASTN, MONTHS, 1)
```

### 语义区别
- **LAST**: 上一个周期（昨天、上周、上月）
  - "昨天" → `LAST`, `DAYS`, `range_n=None`
  - "上周" → `LAST`, `WEEKS`, `range_n=None`
  - "上月" → `LAST`, `MONTHS`, `range_n=None`

- **LASTN**: 最近N个周期（最近7天、最近3个月）
  - "最近7天" → `LASTN`, `DAYS`, `range_n=7`
  - "最近3个月" → `LASTN`, `MONTHS`, `range_n=3`

### 修复方案

**文件**: `tableau_assistant/prompts/understanding_v3.py`

```python
### Time Extraction
Extract **time_range** and **date_requirements** from the question:
- "2025年6月" -> absolute time with value="2025-06"
- "今年6月" -> resolve using metadata max_date
- "最近一个月" -> relative time (LASTN, MONTHS, 1)  # ← 修复这里
- "最近7天" -> relative time (LASTN, DAYS, 7)        # ← 添加示例
- "昨天" -> relative time (LAST, DAYS, None)         # ← 添加示例
- "上周" -> relative time (LAST, WEEKS, None)        # ← 添加示例
- "春节期间" -> mentions_holidays=true, holiday_keywords=["春节"]
- "农历正月" -> mentions_lunar=true, lunar_keywords=["农历", "正月"]
- "按周一开始" -> week_start_day=0, week_start_day_keywords=["周一"]
```

### 验证
修复后，重新运行测试：
```bash
python tests/test_understanding_planning_building.py
```

预期输出：
```json
"time_range": {
  "type": "relative",
  "relative_type": "LASTN",  // ← 应该是 LASTN
  "period_type": "DAYS",
  "range_n": 7
}
```

---

## 问题2：Task Planner 只返回部分子任务 ✗ 高优先级

### 问题描述
- 用户问题："对比今年和去年各门店的销售额"
- Understanding 识别：3个子问题
  1. "今年各门店的销售额" (query)
  2. "去年各门店的销售额" (query)
  3. "计算对比" (post_processing)
- **Task Planner 只返回**：1个子任务（只有第1个）
- **导致错误**：`ValidationError: subtasks.1 is None`

### 根本原因分析

#### 可能原因1：LLM 输出被截断
- LLM 开始生成第2个子任务，但输出被截断
- 需要检查 `max_tokens` 设置

#### 可能原因2：LLM 没有遵守指令
- Prompt 已经明确要求生成所有子任务
- 但 LLM 可能理解错误或忽略了指令

#### 可能原因3：流式输出解析问题
- 流式输出可能没有完整接收
- JSON 解析可能在中途停止

### 诊断步骤

#### 步骤1：检查 LLM 的原始输出

在 `task_planner_agent.py` 中添加日志：

```python
async def _generate_query_subtasks(self, ...):
    # 调用 LLM
    query_result = await self._execute_with_prompt(input_data, runtime, model_config)
    
    # 添加诊断日志
    print(f"[诊断] LLM 返回的子任务数量: {len(query_result.subtasks)}")
    print(f"[诊断] 预期的子任务数量: {len(query_sub_questions)}")
    
    if len(query_result.subtasks) != len(query_sub_questions):
        print(f"[警告] 子任务数量不匹配！")
        print(f"[警告] 输入的子问题:")
        for i, (_, sq) in enumerate(query_sub_questions):
            print(f"  {i}. {sq.text}")
        print(f"[警告] LLM 返回的子任务:")
        for i, st in enumerate(query_result.subtasks):
            print(f"  {i}. {st.question_text}")
    
    return query_result
```

#### 步骤2：检查 max_tokens 设置

文件：`tableau_assistant/src/config/settings.py`

```python
# 检查是否设置了足够的 max_tokens
# 对于复杂查询，可能需要更大的值
```

#### 步骤3：检查 Prompt 是否传递了正确的信息

在 `_prepare_input_data` 中添加日志：

```python
def _prepare_input_data(self, state, **kwargs):
    ...
    
    # 添加诊断日志
    print(f"[诊断] 准备输入数据:")
    print(f"  - 子问题数量: {num_sub_questions}")
    print(f"  - 子问题列表:\n{sub_questions_list}")
    
    return {
        "understanding": understanding,
        ...
    }
```

### 修复方案

#### 方案1：增加 max_tokens（如果是截断问题）

```python
# 在 base_agent.py 或 settings.py 中
MAX_TOKENS = 4096  # 增加到足够大
```

#### 方案2：改进 Prompt（如果是理解问题）

在 `task_planner_v3.py` 中强化指令：

```python
def get_task(self) -> str:
    return """For each sub-question in the understanding result, generate a complete VizQL query specification.

**CRITICAL**: You MUST generate EXACTLY {num_sub_questions} subtasks.

Current sub-questions to process:
{sub_questions_list}

**Requirements**:
1. Generate ONE subtask for EACH sub-question listed above
2. Number of subtasks MUST equal {num_sub_questions}
3. Each subtask must have unique question_id (q0, q1, q2, ...)
4. Do NOT skip any sub-question
5. Do NOT stop until ALL sub-questions are processed

**Verification**: Before finishing, count your subtasks and ensure you have {num_sub_questions} subtasks."""
```

#### 方案3：添加验证和重试逻辑

在 `task_planner_agent.py` 中：

```python
async def _generate_query_subtasks(self, ...):
    query_result = await self._execute_with_prompt(input_data, runtime, model_config)
    
    # 验证子任务数量
    expected_count = len(query_sub_questions)
    actual_count = len(query_result.subtasks)
    
    if actual_count != expected_count:
        logger.warning(
            f"子任务数量不匹配: 预期 {expected_count}, 实际 {actual_count}"
        )
        
        # 选项1：抛出错误
        raise ValueError(
            f"Task Planner 只生成了 {actual_count} 个子任务，"
            f"但应该生成 {expected_count} 个"
        )
        
        # 选项2：重试（如果有重试机制）
        # if actual_count < expected_count and retry_count < max_retries:
        #     return await self._generate_query_subtasks(...)
    
    return query_result
```

### 临时解决方案

如果无法立即修复，可以在代码中添加保护：

```python
# 在 execute 方法中
all_subtasks: List[SubTask] = [None] * len(understanding.sub_questions)

# ... 生成子任务 ...

# 检查是否有 None
if None in all_subtasks:
    none_indices = [i for i, st in enumerate(all_subtasks) if st is None]
    raise ValueError(
        f"以下子任务未生成: {none_indices}\n"
        f"这通常是因为 Task Planner 没有生成所有子任务。\n"
        f"请检查 LLM 输出或增加 max_tokens。"
    )
```

---

## 修复优先级

### P0 - 立即修复
1. ✅ **问题1**: 修复 Understanding Prompt 中的示例
   - 影响：所有"最近N天/月"的查询都会出错
   - 修复难度：低（只需改1行）
   - 修复时间：5分钟

### P1 - 尽快修复
2. ⚠️ **问题2**: 诊断并修复 Task Planner 子任务生成问题
   - 影响：所有多子问题的查询都会失败
   - 修复难度：中（需要诊断）
   - 修复时间：1-2小时

---

## 修复步骤

### 第1步：修复 Understanding Prompt（5分钟）

```bash
# 编辑文件
vim tableau_assistant/prompts/understanding_v3.py

# 修改第162行
# 从: - "最近一个月" -> relative time (LAST, MONTHS, 1)
# 到: - "最近一个月" -> relative time (LASTN, MONTHS, 1)

# 添加更多示例
- "最近7天" -> relative time (LASTN, DAYS, 7)
- "昨天" -> relative time (LAST, DAYS, None)
- "上周" -> relative time (LAST, WEEKS, None)
```

### 第2步：验证修复（5分钟）

```bash
# 运行测试
python tests/test_understanding_planning_building.py

# 检查输出
# 应该看到: relative_type="LASTN" 而不是 "LAST"
```

### 第3步：诊断 Task Planner 问题（30分钟）

```bash
# 添加诊断日志
# 在 task_planner_agent.py 中添加上述诊断代码

# 重新运行测试
python tests/test_understanding_planning_building.py

# 查看诊断输出
# 确定是截断、理解还是解析问题
```

### 第4步：修复 Task Planner 问题（30-60分钟）

根据诊断结果选择修复方案：
- 如果是截断：增加 max_tokens
- 如果是理解：改进 Prompt
- 如果是解析：检查流式输出处理

### 第5步：完整测试（10分钟）

```bash
# 运行所有测试
python tests/test_understanding_planning_building.py

# 确保所有4个问题都能正确处理
```

---

## 预期结果

修复后，测试应该显示：

```
================================================================================
测试问题 1/4: 最近7天各门店的销售额是多少
================================================================================
✓ 问题理解完成
  - relative_type: LASTN  ← 修复后
  - range_n: 7

✓ 查询构建成功
  - 筛选器: 2025-11-23 ~ 2025-11-29  ← 正确的7天范围

================================================================================
测试问题 4/4: 对比今年和去年各门店的销售额
================================================================================
✓ 问题理解完成
  - 子问题数量: 3

✓ 任务规划完成
  - 子任务数量: 3  ← 修复后，应该是3个

✓ 查询构建成功
  - 所有子任务都成功构建
```

---

## 总结

### 问题根源
1. **Understanding Prompt 示例错误** - 导致 LAST/LASTN 混淆
2. **Task Planner 生成不完整** - 原因待诊断

### 修复策略
1. **立即修复** Understanding Prompt（简单）
2. **诊断后修复** Task Planner（需要调查）

### 验证方法
- 运行完整测试套件
- 检查所有4个测试问题
- 确保输出正确
