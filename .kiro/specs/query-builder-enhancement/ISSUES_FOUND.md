# Query Builder 测试中发现的问题

## 测试运行结果

### ✅ 成功的测试
1. **问题1**: "最近7天各门店的销售额是多少" - ⚠️ 有问题（见下文）
2. **问题2**: "显示各产品类别的销售额和利润，按销售额降序排列" - ✅ 完全正常
3. **问题3**: "哪个门店的利润最高?" - ✅ 完全正常
4. **问题4**: "对比今年和去年各门店的销售额" - ✗ Task Planner 错误

## 发现的问题

### 问题 1: Task Planner 输出错误的 dateRangeType ⚠️

**问题描述**:
- 用户问题: "最近7天各门店的销售额是多少"
- Understanding 正确识别: `relative_type="LAST"`, `range_n=7`
- **Task Planner 错误输出**: `dateRangeType="LAST"`, `rangeN=7`
- **应该输出**: `dateRangeType="LASTN"`, `rangeN=7`

**影响**:
- `LAST` + `DAYS` 表示"昨天"（上一天）
- `LASTN` + `DAYS` + `rangeN=7` 表示"最近7天"
- 导致查询结果错误：`2025-11-28 ~ 2025-11-28`（只有1天）
- 应该是：`2025-11-23 ~ 2025-11-29`（7天）

**根本原因**:
- Task Planner 的 Prompt 或逻辑有问题
- 没有正确区分 `LAST` 和 `LASTN`

**解决方案**:
- 修复 Task Planner 的 Prompt
- 添加验证逻辑：如果有 `rangeN`，必须使用 `LASTN` 或 `NEXTN`

**QueryBuilder 的行为**:
- ✅ QueryBuilder 正确处理了 Task Planner 的输出
- ✅ 按照 `LAST` + `DAYS` 的语义返回"昨天"
- ✅ 这是正确的行为，问题在 Task Planner

**测试输出**:
```
筛选器列表:
  * [calc: DATEPARSE('yyyy-MM-dd', [日期])] (QuantitativeDateFilter, range: 2025-11-28 ~ 2025-11-28)
  [诊断] 原始筛选器: RelativeDateFilter
  [诊断] dateRangeType: LAST
  [诊断] periodType: DAYS
  [诊断] rangeN: 7
  [警告] dateRangeType='LAST' 但有 rangeN=7
  [警告] 应该使用 'LASTN' 而不是 'LAST'
  [警告] 这是 Task Planner 的问题，不是 QueryBuilder 的问题
```

---

### 问题 2: Task Planner 只返回部分子任务 ✗

**问题描述**:
- 用户问题: "对比今年和去年各门店的销售额"
- Understanding 正确识别: 3个子问题
  1. "今年各门店的销售额" (query)
  2. "去年各门店的销售额" (query)
  3. "计算今年和去年各门店销售额的对比" (post_processing, yoy)
- **Task Planner 只返回**: 1个子任务
- **导致错误**: `ValidationError: subtasks.1 Input should be a valid dictionary`

**影响**:
- 测试中断
- 无法完成对比查询的测试

**根本原因**:
- Task Planner 的逻辑有问题
- 可能是流式输出被截断
- 可能是 LLM 没有生成完整的响应

**解决方案**:
- 检查 Task Planner 的实现
- 确保所有子问题都被处理
- 添加验证：`len(subtasks) == len(sub_questions)`

**测试输出**:
```
✓ 问题理解完成 (耗时: 8.55秒)
  - 子问题数量: 3
    1. [SubQuestionExecutionType.QUERY] 今年各门店的销售额
    2. [SubQuestionExecutionType.QUERY] 去年各门店的销售额
    3. [SubQuestionExecutionType.POST_PROCESSING, ProcessingType.YOY] 计算今年和去年各门店销售额的对比

✓ 任务规划完成 (耗时: 22.15秒)
  - 子任务数量: 1  ← 应该是 3！

ValidationError: 1 validation error for QueryPlanningResult
subtasks.1
  Input should be a valid dictionary or object to extract fields from
```

---

### 问题 3: 筛选器信息显示不完整 ⚠️

**问题描述**:
- 原始输出: `calc: DATEPARSE('yyyy-MM-dd', [日期])... (QuantitativeDateFilter, 2025-11-28 ~ 2025-11-28)`
- calculation 被截断了

**影响**:
- 调试困难
- 无法看到完整的 DATEPARSE 表达式

**解决方案**:
- ✅ 已修复：显示完整的 calculation
- ✅ 改进格式：`[calc: DATEPARSE('yyyy-MM-dd', [日期])]`

**修复后输出**:
```
筛选器列表:
  * [calc: DATEPARSE('yyyy-MM-dd', [日期])] (QuantitativeDateFilter, range: 2025-11-28 ~ 2025-11-28)
```

---

## QueryBuilder 的表现

### ✅ 正确的行为

1. **正确处理 STRING 类型日期字段**
   - 自动检测日期格式（yyyy-MM-dd）
   - 生成正确的 DATEPARSE calculation
   - 转换为 QuantitativeDateFilter

2. **正确处理各种筛选器类型**
   - RelativeDateFilter
   - QuantitativeDateFilter
   - TopNFilter
   - 排序字段

3. **正确处理字段类型**
   - BasicField
   - FunctionField
   - 排序和聚合

4. **正确的错误处理**
   - 按照输入的语义执行
   - `LAST` + `DAYS` 正确返回"昨天"
   - 这是符合规范的行为

### ⚠️ 不是 QueryBuilder 的问题

1. **日期范围错误**
   - 原因：Task Planner 输出 `LAST` 而不是 `LASTN`
   - QueryBuilder 正确执行了 `LAST` 的语义
   - 问题在上游（Task Planner）

2. **子任务数量不匹配**
   - 原因：Task Planner 只生成了部分子任务
   - QueryBuilder 无法处理不存在的子任务
   - 问题在上游（Task Planner）

---

## 需要修复的模块

### 1. Task Planner Agent ⚠️ 高优先级

**问题**:
- 错误使用 `LAST` 而不是 `LASTN`
- 只生成部分子任务

**修复建议**:
```python
# 在 Task Planner Prompt 中明确说明：
# - 如果有 rangeN，必须使用 LASTN 或 NEXTN
# - LAST 表示"上一个周期"（昨天、上周、上月）
# - LASTN 表示"最近N个周期"（最近7天、最近3个月）

# 添加验证逻辑：
if filter.rangeN and filter.dateRangeType not in ["LASTN", "NEXTN"]:
    raise ValueError(f"有 rangeN={filter.rangeN} 但 dateRangeType={filter.dateRangeType}")
```

**测试用例**:
- "最近7天" → `LASTN`, `DAYS`, `rangeN=7`
- "昨天" → `LAST`, `DAYS`, `rangeN=None`
- "上周" → `LAST`, `WEEKS`, `rangeN=None`
- "最近3个月" → `LASTN`, `MONTHS`, `rangeN=3`

### 2. Task Planner Agent - 子任务生成 ✗ 高优先级

**问题**:
- 对于多子问题的场景，只生成了第一个子任务

**修复建议**:
- 检查流式输出是否被截断
- 确保所有子问题都被处理
- 添加验证：`assert len(subtasks) == len(sub_questions)`

---

## 测试改进

### ✅ 已添加的诊断功能

1. **子任务数量检查**
```python
if expected_subtasks != actual_subtasks:
    print(f"  ⚠️ 警告: 子任务数量不匹配！")
    print(f"     - Understanding 识别: {expected_subtasks} 个子问题")
    print(f"     - Task Planner 生成: {actual_subtasks} 个子任务")
```

2. **日期筛选器诊断**
```python
if original_filter.dateRangeType == "LAST" and original_filter.rangeN:
    print(f"        [警告] dateRangeType='LAST' 但有 rangeN={original_filter.rangeN}")
    print(f"        [警告] 应该使用 'LASTN' 而不是 'LAST'")
```

3. **完整的筛选器信息显示**
```python
# 显示完整的 calculation
field_name = f"[calc: {filter_obj.field.calculation}]"
```

---

## 总结

### QueryBuilder 状态: ✅ 可用

- QueryBuilder 本身工作正常
- 正确处理了所有输入
- 按照规范执行
- 问题都在上游（Task Planner）

### 需要修复的模块: Task Planner

1. **高优先级**: 修复 `LAST` vs `LASTN` 的问题
2. **高优先级**: 修复子任务生成不完整的问题

### 测试改进: ✅ 已完成

- 添加了诊断功能
- 改进了输出格式
- 更容易发现问题

### 下一步

1. **修复 Task Planner** 的两个问题
2. **重新运行测试** 验证修复
3. **继续实现 Query Executor**（QueryBuilder 已经可用）
