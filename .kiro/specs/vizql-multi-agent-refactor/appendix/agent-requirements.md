# Agent详细规格

本文档包含6个Agent的详细验收标准、提示词设计、输入输出示例和实现指南。

**7个Agent**：
- 需求0：维度层级推断Agent
- 需求15：问题Boost Agent
- 需求1：问题理解Agent（拆分子问题、提取关键信息）
- 需求2：任务规划Agent（智能规划查询策略、字段映射）
- 需求5：洞察Agent（贡献度分析、业务洞察）
- 需求6：重规划Agent（下钻维度查找、问题清单生成）
- 需求7：总结Agent

---

## 需求0：维度层级推断Agent

### 详细功能说明

#### 1. 维度层级推断

根据字段元数据、统计信息和数据样例，推断每个维度的以下属性：

**基础属性**：
- **category**: 维度类别（由LLM智能推断）
  - 标准类别：地理、时间、产品、客户、组织、财务、其他
  - LLM应将推断的类别映射到最接近的标准类别
- **category_detail**: 详细类别描述
  - 示例："地理-省级"、"地理-城市"、"时间-年"、"时间-月"、"产品-一级分类"
- **unique_count**: 唯一值数量（来自统计信息）
- **sample_values**: 示例值列表（最多10个代表性值）

**层级属性**：
- **level**: 层级级别（数字，越小越粗粒度）
  - 计算规则：主要基于unique_count，辅以LLM的语义理解
  - unique_count < 10 → level=1（粗粒度）
  - 10 <= unique_count < 100 → level=2（中粒度）
  - unique_count >= 100 → level=3（细粒度）
  - LLM可根据语义调整±1个level（如"国家"即使unique_count=200也应该是level=1）
- **granularity**: 粒度描述（"粗粒度" | "中粒度" | "细粒度"）
- **parent_dimension**: 父维度（更粗粒度，LLM根据语义推断）
- **child_dimension**: 子维度（更细粒度，LLM根据语义推断）

**质量属性**：
- **level_confidence**: 层级判断的置信度（0-1）
  - 基于数据样例的完整性、字段名称的明确性、统计信息的可靠性
- **reasoning**: LLM的推理过程（为什么这样判断，用于调试和优化）

**重要说明**：
- 允许多个维度具有相同的level值（如"地区"和"产品类别"都可以是level=1）
- 不同category的维度可以有相同的粒度

#### 2. 缓存策略

- **写入元数据**：结果写入元数据的`dimension_hierarchy`字段
- **Redis缓存**：缓存key为`dimension_hierarchy:{datasource_luid}`，有效期24小时
- **缓存失效**：手动刷新、数据源结构变更、超过24小时
- **手动调整**：提供接口允许用户覆盖AI判断的维度层级

#### 3. Fallback机制

- **LLM调用失败**：使用基于unique_count的默认规则计算level
- **置信度过低**（<0.7）：记录警告日志并使用fallback规则
- **默认规则**：
  - 根据unique_count计算level
  - 根据字段名称关键词推断category（地区→地理、年月日→时间、产品→产品、客户→客户）
  - parent_dimension和child_dimension设为null
  - level_confidence设为0.5

#### 4. 性能优化

- **分批推断**：如果维度数量>100，分批推断（每批20个维度）
- **并行处理**：多个数据源的维度层级推断可并行执行
- **增量更新**：只对新增或变更的维度重新推断

### 输入输出详细示例

**输入示例**（~5,500 tokens）：
```json
{
  "datasource_luid": "abc123",
  "dimensions": [
    {
      "field_name": "地区",
      "data_type": "string",
      "unique_count": 34,
      "sample_values": ["北京", "上海", "广东", "浙江", "江苏", "四川", "湖北", "河南", "山东", "福建"]
    },
    {
      "field_name": "城市",
      "data_type": "string",
      "unique_count": 337,
      "sample_values": ["北京市", "上海市", "深圳市", "广州市", "杭州市", "成都市", "武汉市", "郑州市", "济南市", "福州市"]
    }
  ]
}
```

**输出示例**：
```json
{
  "dimension_hierarchy": {
    "地区": {
      "category": "地理",
      "category_detail": "地理-省级",
      "level": 1,
      "granularity": "粗粒度",
      "unique_count": 34,
      "parent_dimension": null,
      "child_dimension": "城市",
      "sample_values": ["北京", "上海", "广东", "浙江", "江苏"],
      "level_confidence": 0.95,
      "reasoning": "unique_count=34，对应中国省级行政区，属于粗粒度地理维度"
    },
    "城市": {
      "category": "地理",
      "category_detail": "地理-城市",
      "level": 2,
      "granularity": "中粒度",
      "unique_count": 337,
      "parent_dimension": "地区",
      "child_dimension": "门店",
      "sample_values": ["北京市", "上海市", "深圳市", "广州市", "杭州市"],
      "level_confidence": 0.92,
      "reasoning": "unique_count=337，对应中国地级市，属于中粒度地理维度，父维度为地区"
    }
  }
}
```

### 详细验收标准

#### 1. 推断准确性

**测试方法**：
- 准备10个不同行业的数据源（零售、金融、医疗、教育等）
- 每个数据源包含10-50个维度
- 人工标注正确的category和level
- 对比AI推断结果与人工标注

**验收指标**：
- level_confidence >= 0.7 的维度占比 >= 80%
- category推断准确率 >= 90%（通过人工抽样验证）
- level推断准确率 >= 85%（允许±1个level的误差）
- parent/child关系推断准确率 >= 80%

#### 2. 缓存有效性

**测试方法**：
- 首次访问数据源，记录推断时间
- 24小时内再次访问，验证是否使用缓存
- 手动刷新缓存，验证是否重新推断

**验收指标**：
- 缓存命中率 >= 95%（24小时内）
- 缓存失效后能自动重新推断
- 手动刷新功能正常工作

#### 3. Fallback可靠性

**测试方法**：
- 模拟LLM调用失败（网络错误、超时等）
- 验证fallback规则是否正常工作
- 检查fallback结果的level_confidence是否设为0.5

**验收指标**：
- LLM调用失败时，fallback规则能正常工作
- fallback结果的level_confidence设为0.5
- fallback结果的category基于关键词推断

#### 4. 性能要求

**测试方法**：
- 测试不同维度数量的数据源（10、50、100、200个维度）
- 记录推断时间和token消耗

**验收指标**：
- 单次推断耗时 <= 3秒（50个维度以内）
- 分批推断不阻塞主流程
- Token消耗 <= 6,000（50个维度以内）

### 提示词设计指南

**提示词结构**：
1. **角色定义** - 你是一位资深的数据建模专家
2. **任务说明** - 推断维度的层级关系和粒度
3. **输入说明** - 字段名称、唯一值数量、样本值
4. **输出格式** - JSON格式，包含category、level、granularity等
5. **推理要求** - 解释推理过程，提供置信度

**关键提示**：
- 强调level的计算规则（基于unique_count）
- 强调允许多个维度具有相同的level
- 强调parent/child关系的推断（基于语义）
- 强调置信度的评估（基于数据完整性和字段名称明确性）

---


## 需求1：问题理解Agent

### 详细功能说明

#### 1. 问题有效性验证

识别问题类型：
- **数据分析问题** - 可以通过查询数据回答（如"2016年各地区的销售额"）
- **操作指令** - 需要执行操作（如"导出报表"、"发送邮件"）→ 拒绝
- **定义查询** - 询问字段定义（如"销售额是什么意思"）→ 引导到元数据

#### 2. 问题类型识别

支持的问题类型：
- **对比** - 比较不同维度的值（如"各地区的销售额对比"）
- **趋势** - 时间序列分析（如"2016年各月的销售额趋势"）
- **排名** - TopN分析（如"销售额Top 10的门店"）
- **诊断** - 根因分析（如"为什么华东地区利润率低"）
- **多维分解** - 多个维度的交叉分析（如"各地区各产品类别的销售额"）
- **占比** - 百分比分析（如"各地区销售额占比"）
- **同比** - 同期对比（如"2016年vs 2015年"）
- **环比** - 连续期对比（如"本月vs上月"）

#### 3. 关键信息提取

**时间范围**：
- **明确时间**：提取具体日期（如"2016年" → `{"start": "2016-01-01", "end": "2016-12-31"}`）
- **相对时间**：理解相对表达（如"最近3个月" → `{"relative": "LAST", "period": "MONTH", "count": 3}`）
- **注意**：AI只负责理解和提取，具体日期计算由查询构建器完成

**筛选条件**：
- **维度筛选**：如"地区=北京"、"产品类别包含家具"
- **度量筛选**：如"销售额>1000"、"利润率<10%"

**排序要求**：
- 排序字段和方向（如"按销售额降序"）

**TopN限制**：
- 是否需要TopN筛选（如"Top 10门店"）

**时间粒度**：
- 日/周/月/季/年（如"按月统计"）

**聚合方式**：
- 求和/平均/计数/最大/最小（如"平均销售额"）

#### 4. 日期特征提取

**目的**：识别问题中的日期相关特征，用于指导查询构建器的日期字段处理策略。

**提取内容**：

**周开始日识别**：
- **周一开始关键词**："周一开始"、"周一到周日"、"从周一"、"周一至周日"、"Monday start"
- **周日开始关键词**："周日开始"、"周日到周六"、"从周日"、"周日至周六"、"Sunday start"
- **输出**：`week_start_day: 0 | 6 | null`（0=周一，6=周日，null=未指定）

**节假日相关识别**：
- **通用关键词**："节假日"、"法定节假日"、"假期"、"工作日"、"非工作日"、"休息日"、"上班日"
- **具体节日**："春节"、"国庆"、"五一"、"清明"、"端午"、"中秋"、"元旦"
- **英文关键词**："holiday"、"working day"、"weekday"、"business day"、"weekend"
- **输出**：`consider_holidays: true | false`

**农历相关识别**：
- **历法关键词**："农历"、"阴历"、"传统历法"、"中国历法"
- **农历节日**："春节"、"中秋"、"端午"、"清明"、"七夕"、"重阳"
- **农历时间**："正月"、"腊月"、"初一"、"十五"、"二十四节气"
- **英文关键词**："lunar"、"chinese calendar"、"traditional festival"
- **输出**：`support_lunar: true | false`

**特殊情况处理**：
- **重叠节日**（既是法定节假日又是农历节日）：
  - 春节、中秋、清明、端午 → `consider_holidays=true, support_lunar=true`
- **非法定节假日**：
  - 双十一、双十二、情人节、圣诞节 → `consider_holidays=false`
- **工作日相关**：
  - "工作日"、"上班日"、"weekday" → `consider_holidays=true`

**输出格式**：
```json
{
  "date_features": {
    "week_start_day": 0 | 6 | null,
    "week_start_day_mentioned": true | false,
    "consider_holidays": true | false,
    "holiday_keywords": ["工作日", "节假日"],
    "support_lunar": true | false,
    "lunar_keywords": ["农历", "春节"]
  }
}
```

**注意**：时区配置从外部获取（如系统配置、用户设置），不需要从问题中提取。

#### 5. 隐含需求识别

- **同比分析** → 需要两个时间段（当期+去年同期）
- **环比分析** → 需要两个连续时间段（当期+上期）
- **占比分析** → 需要先计算总计
- **增长率分析** → 需要两个时间点的数据

#### 6. 问题复杂度评估

- **Simple** - 单一维度、单一度量、单一时间段
- **Medium** - 多个维度或多个度量，或需要对比
- **Complex** - 多个时间段对比、多层级下钻、复杂计算

### 输入输出详细示例

**示例1：明确时间**

输入：
```
用户问题：2016年各地区的销售额和利润对比
```

输出：
```json
{
  "original_question": "2016年各地区的销售额和利润对比",
  "sub_questions": ["2016年各地区的销售额和利润对比"],
  "question_type": ["对比"],
  "time_range": {
    "type": "absolute",
    "year": 2016
  },
  "mentioned_dimensions": ["地区"],
  "mentioned_metrics": ["销售额", "利润"],
  "sort_requirement": "按销售额降序",
  "topn_requirement": null,
  "grain_requirement": null,
  "aggregation_intent": "求和",
  "complexity": "Simple",
  "implicit_requirements": ["需要排序", "降序排列"],
  "date_features": {
    "week_start_day": null,
    "week_start_day_mentioned": false,
    "consider_holidays": false,
    "holiday_keywords": [],
    "support_lunar": false,
    "lunar_keywords": []
  }
}
```

**示例2：相对时间**

输入：
```
用户问题：最近3个月的销售额趋势
```

输出：
```json
{
  "original_question": "最近3个月的销售额趋势",
  "sub_questions": ["最近3个月的销售额趋势"],
  "question_type": ["趋势"],
  "time_range": {
    "type": "relative",
    "relative": "LAST",
    "period": "MONTH",
    "count": 3
  },
  "mentioned_dimensions": ["时间"],
  "mentioned_metrics": ["销售额"],
  "sort_requirement": "按时间升序",
  "topn_requirement": null,
  "grain_requirement": "按日统计",
  "aggregation_intent": "求和",
  "complexity": "Simple",
  "implicit_requirements": ["需要时间序列", "按时间排序"],
  "note": "具体日期由查询构建器根据当前日期计算"
}
```

**示例3：同比分析**

输入：
```
用户问题：2024年1月的销售额同比增长率
```

输出：
```json
{
  "original_question": "2024年1月的销售额同比增长率",
  "sub_questions": ["2024年1月的销售额同比增长率"],
  "question_type": ["对比", "同比"],
  "time_range": {
    "type": "comparison",
    "current_period": "2024年1月",
    "comparison_type": "year_over_year"
  },
  "mentioned_dimensions": [],
  "mentioned_metrics": ["销售额", "增长率"],
  "sort_requirement": null,
  "topn_requirement": null,
  "grain_requirement": null,
  "aggregation_intent": "求和",
  "complexity": "Medium",
  "implicit_requirements": [
    "需要两个时间段：当期和去年同期",
    "需要计算增长率",
    "去年同期是2023年1月"
  ],
  "note": "具体日期计算和增长率公式由任务规划Agent和查询构建器处理"
}
```

**示例4：TopN排名**

输入：
```
用户问题：销售额Top 10的门店是哪些？
```

输出：
```json
{
  "original_question": "销售额Top 10的门店是哪些？",
  "sub_questions": ["销售额Top 10的门店是哪些？"],
  "question_type": ["排名"],
  "time_range": null,
  "mentioned_dimensions": ["门店"],
  "mentioned_metrics": ["销售额"],
  "sort_requirement": "按销售额降序",
  "topn_requirement": "Top 10",
  "grain_requirement": null,
  "aggregation_intent": "求和",
  "complexity": "Simple",
  "implicit_requirements": ["需要排序", "只返回前10条"],
  "date_features": {
    "week_start_day": null,
    "week_start_day_mentioned": false,
    "consider_holidays": false,
    "holiday_keywords": [],
    "support_lunar": false,
    "lunar_keywords": []
  }
}
```

**示例5：周开始日**

输入：
```
用户问题：周日开始的本周销售额
```

输出：
```json
{
  "question_type": ["总结"],
  "time_range": {
    "type": "relative",
    "relative": "THIS",
    "period": "WEEK",
    "count": 1
  },
  "mentioned_dimensions": [],
  "mentioned_metrics": ["销售额"],
  "sort_requirement": null,
  "topn_requirement": null,
  "grain_requirement": null,
  "aggregation_intent": "求和",
  "complexity": "Simple",
  "implicit_requirements": [],
  "date_features": {
    "week_start_day": 6,
    "week_start_day_mentioned": true,
    "consider_holidays": false,
    "holiday_keywords": [],
    "support_lunar": false,
    "lunar_keywords": []
  }
}
```

**示例6：工作日**

输入：
```
用户问题：最近一个月的工作日销售额
```

输出：
```json
{
  "question_type": ["总结"],
  "time_range": {
    "type": "relative",
    "relative": "LAST",
    "period": "MONTH",
    "count": 1
  },
  "mentioned_dimensions": [],
  "mentioned_metrics": ["销售额"],
  "sort_requirement": null,
  "topn_requirement": null,
  "grain_requirement": null,
  "aggregation_intent": "求和",
  "complexity": "Simple",
  "implicit_requirements": ["需要筛选工作日"],
  "date_features": {
    "week_start_day": null,
    "week_start_day_mentioned": false,
    "consider_holidays": true,
    "holiday_keywords": ["工作日"],
    "support_lunar": false,
    "lunar_keywords": []
  }
}
```

**示例7：农历节日**

输入：
```
用户问题：春节期间的销售额，排除法定节假日
```

输出：
```json
{
  "question_type": ["总结"],
  "time_range": {
    "type": "custom",
    "description": "春节期间"
  },
  "mentioned_dimensions": [],
  "mentioned_metrics": ["销售额"],
  "sort_requirement": null,
  "topn_requirement": null,
  "grain_requirement": null,
  "aggregation_intent": "求和",
  "complexity": "Medium",
  "implicit_requirements": ["需要识别春节日期", "需要排除法定节假日"],
  "date_features": {
    "week_start_day": null,
    "week_start_day_mentioned": false,
    "consider_holidays": true,
    "holiday_keywords": ["春节", "法定节假日"],
    "support_lunar": true,
    "lunar_keywords": ["春节"]
  }
}
```

### 详细验收标准

#### 1. 问题类型识别准确率 >= 90%

**测试方法**：
- 准备100个不同类型的问题
- 人工标注正确的问题类型
- 对比AI识别结果与人工标注

**测试用例**：
- 对比问题：20个
- 趋势问题：15个
- 排名问题：15个
- 诊断问题：10个
- 多维分解：15个
- 占比问题：10个
- 同环比问题：15个

#### 2. 时间范围提取准确率 >= 95%

**测试方法**：
- 准备50个包含时间范围的问题
- 验证提取的时间范围是否正确

**测试用例**：
- 明确时间：20个（如"2016年"、"2024年1月"）
- 相对时间：20个（如"最近3个月"、"上个季度"）
- 同比时间：10个（如"2024年vs 2023年"）

#### 3. 隐含需求识别准确率 >= 85%

**测试方法**：
- 准备30个包含隐含需求的问题
- 验证是否正确识别隐含需求

**测试用例**：
- 同比分析：10个
- 环比分析：10个
- 占比分析：5个
- 增长率分析：5个

#### 4. 响应时间 <= 2秒

**测试方法**：
- 测试100个问题的响应时间
- 计算平均响应时间和P95响应时间

**验收指标**：
- 平均响应时间 <= 1.5秒
- P95响应时间 <= 2秒

---



---

## 需求2：任务规划Agent

### 详细功能说明

任务规划Agent负责根据问题复杂度智能规划查询策略，生成完整的查询规格。它合并了原字段选择Agent和任务拆分Agent的功能，并增加了智能规划策略。

#### 执行顺序

```
1. 评估问题复杂度（从问题理解Agent获取）
   ↓
2. 选择规划策略
   - Simple/Medium：直接生成完整查询，needs_replan=False
   - Complex：生成1-2个现象确认查询，needs_replan=True
   ↓
3. 完整字段映射
   - 从元数据中匹配真实字段（fieldCaption、dataType、role、level）
   - 将自然语言维度名称映射到技术字段
   ↓
4. 生成查询规格
   - 生成完整的QuerySpec（fields、filters、reasoning）
   - 处理筛选条件的技术实现
   ↓
5. 处理重规划问题（如果是重规划轮次）
   - 接收重规划Agent生成的自然语言问题清单
   - 生成对应的查询规格
```

#### 1. 智能规划策略

**基于问题复杂度选择规划策略**：

**Simple/Medium问题**（直接生成完整查询）：
- ✅ 单一维度、单一度量、单一时间段
  - 例："2016年各地区的销售额" → 生成1个完整查询，needs_replan=False
- ✅ 多个度量 + 相同维度组合
  - 例："2016年各门店的销售额、利润和订单量" → 生成1个完整查询，needs_replan=False
- ✅ 多个维度 + 多个度量
  - 例："各地区各产品类别的销售额和利润" → 生成1个完整查询，needs_replan=False

**Complex问题**（生成现象确认查询）：
- ❌ 多维度深入分析
  - 例："分析销售额下降的原因" → 生成1-2个现象确认查询，needs_replan=True
- ❌ 根因分析
  - 例："为什么华东地区利润率低" → 生成1-2个现象确认查询，needs_replan=True
- ❌ 探索式分析
  - 例："找出影响销售额的主要因素" → 生成1-2个现象确认查询，needs_replan=True

**重规划问题处理**：
- 接收重规划Agent生成的自然语言问题清单
- 为每个问题生成完整的查询规格
- 不再判断needs_replan（由重规划Agent决定）

#### 2. 完整字段映射

**从元数据中匹配真实字段**：

**自然语言到技术字段的映射**：
- "产品分类" → 匹配元数据中的"产品一级分类"（fieldCaption）
- "地区" → 匹配元数据中的"地区"（fieldCaption）
- "收入" → 匹配元数据中的"销售额"（fieldCaption）

**获取完整字段信息**：
- **fieldCaption**: 字段显示名称（如"销售额"）
- **dataType**: 数据类型（如"real"、"string"、"date"）
- **role**: 字段角色（"dimension" | "measure"）
- **level**: 维度层级（1/2/3，仅维度字段）
- **function**: 聚合函数（如"SUM"、"AVG"，仅度量字段）
- **sortDirection**: 排序方向（"ASC" | "DESC"，可选）
- **sortPriority**: 排序优先级（数字，可选）

**维度粒度选择**：
- 根据问题要求选择合适粒度的维度
- 利用维度层级信息（level 1/2/3）
- 示例：
  - "各地区" → 选择level=1的"地区"（粗粒度）
  - "各门店" → 选择level=3的"门店"（细粒度）

**字段验证**：
- 字段名必须与元数据中的fieldCaption完全一致
- 不要臆造字段名
- 确保dataType与使用场景匹配

#### 3. 查询规格生成

**生成完整的QuerySpec**：

**fields数组**：
- 包含所有维度和度量字段
- 每个字段包含完整信息（fieldCaption、dataType、role、level、function、sortDirection、sortPriority）

**filters数组**：
- 处理筛选条件的技术实现
- 用户说"2016年" → `{"fieldCaption": "订单日期", "filterType": "QUANTITATIVE_DATE", "year": 2016}`
- 用户说"北京和上海" → `{"fieldCaption": "地区", "filterType": "SET", "values": ["北京", "上海"]}`

**reasoning字段**：
- 说明该查询的目的和推理过程
- 例："单个查询即可完成，选择粗粒度的地区维度"

**needs_replan标志**：
- Simple/Medium问题：needs_replan=False
- Complex问题：needs_replan=True
- 重规划轮次：不设置（由重规划Agent决定）

**replan_mode字段**：
- Complex问题：replan_mode="exploratory"
- Simple/Medium问题：replan_mode=null

#### 4. 重规划问题处理

**处理重规划Agent生成的问题清单**：
- 接收自然语言问题列表
- 接收建议的维度、筛选条件、度量
- 为每个问题生成完整的QuerySpec
- 确保查询规格可以被查询构建器正确转换为VizQL查询JSON

**Stage分配**：
- 无依赖的任务分配到同一stage（可并行执行）
- 有依赖的任务分配到不同stage（顺序执行）

### 输入输出详细示例

**示例1：简单查询（不拆分）**

输入：
```json
{
  "user_question": "2016年各地区的销售额，按销售额降序",
  "understanding_result": {
    "question_type": ["对比"],
    "time_range": {"type": "absolute", "year": 2016},
    "implicit_requirements": ["需要排序", "降序"],
    "complexity": "Simple"
  },
  "metadata": {
    "dimensions": [
      {"fieldCaption": "地区", "dataType": "STRING", "dimension_hierarchy": {"level": 1, "granularity": "粗粒度"}},
      {"fieldCaption": "城市", "dataType": "STRING", "dimension_hierarchy": {"level": 2, "granularity": "中粒度"}}
    ],
    "measures": [
      {"fieldCaption": "销售额", "dataType": "REAL", "defaultAggregation": "SUM"},
      {"fieldCaption": "订单日期", "dataType": "DATE"}
    ]
  }
}
```

输出：
```json
{
  "subtasks": [
    {
      "question_id": "q1",
      "question_text": "2016年各地区的销售额，按销售额降序",
      "dims": ["地区"],
      "metrics": [{"field": "销售额", "aggregation": "sum"}],
      "filters": [{"field": "订单日期", "type": "year", "value": 2016}],
      "sort_by": {"field": "销售额", "direction": "desc"},
      "limit": null,
      "grain": null,
      "stage": 1,
      "depends_on": [],
      "priority": "HIGH",
      "rationale": "单个查询即可完成，选择粗粒度的地区维度（level=1）"
    }
  ]
}
```

**示例2：同比分析（需要拆分）**

输入：
```json
{
  "user_question": "2024年vs 2023年各地区的销售额",
  "understanding_result": {
    "question_type": ["对比", "同比"],
    "time_range": {"type": "comparison", "current": 2024, "comparison": 2023},
    "complexity": "Medium"
  },
  "metadata": {...}
}
```

输出：
```json
{
  "subtasks": [
    {
      "question_id": "q1",
      "question_text": "2024年各地区的销售额",
      "dims": ["地区"],
      "metrics": [{"field": "销售额", "aggregation": "sum"}],
      "filters": [{"field": "订单日期", "type": "year", "value": 2024}],
      "sort_by": {"field": "销售额", "direction": "desc"},
      "stage": 1,
      "depends_on": [],
      "priority": "HIGH",
      "rationale": "需要拆分为两个查询，因为VizQL不支持在一个查询中查询多个不连续时间段"
    },
    {
      "question_id": "q2",
      "question_text": "2023年各地区的销售额",
      "dims": ["地区"],
      "metrics": [{"field": "销售额", "aggregation": "sum"}],
      "filters": [{"field": "订单日期", "type": "year", "value": 2023}],
      "sort_by": {"field": "销售额", "direction": "desc"},
      "stage": 1,
      "depends_on": [],
      "priority": "HIGH",
      "rationale": "与q1并行执行，查询去年同期数据"
    }
  ]
}
```

### 详细验收标准

#### 1. 字段选择准确率 >= 90%

**测试方法**：
- 准备100个不同类型的问题
- 人工标注正确的字段
- 对比AI选择结果与人工标注

**测试用例**：
- 明确字段：20个（如"各地区的销售额"）
- 模糊字段：30个（如"各区域的收入"→"地区"+"销售额"）
- 粒度选择：30个（如"各地区"→level=1，"各门店"→level=3）
- 多字段：20个（如"各地区的销售额和利润"）

#### 2. 智能补全准确率 >= 85%

**测试方法**：
- 准备50个需要补全的问题
- 验证补全的聚合、排序、筛选是否正确

**测试用例**：
- 聚合补全：15个（如"销售额"→"sum"，"平均销售额"→"avg"）
- 排序补全：15个（如"最高"→"desc"，"趋势"→"asc"）
- 筛选补全：10个（如"2016年"→year filter）
- 粒度补全：10个（如"各月"→"month"）

#### 3. 拆分决策准确率 >= 90%

**测试方法**：
- 准备50个问题（25个需要拆分，25个不需要拆分）
- 验证拆分决策是否正确

**测试用例**：
- 不需要拆分：25个
  - 多度量单时间段：10个
  - 多维度多度量：10个
  - 多筛选单时间段：5个
- 需要拆分：25个
  - 多时间段对比：10个
  - 不同维度组合：5个
  - 计算依赖：5个
  - 不同筛选对比：5个

#### 4. 依赖关系识别准确率 >= 95%

**测试方法**：
- 准备30个有依赖关系的问题
- 验证依赖关系识别是否正确

**测试用例**：
- 无依赖（并行）：15个
- 有依赖（顺序）：15个

#### 5. 响应时间 <= 2秒

**测试方法**：
- 测试100个问题的响应时间
- 计算平均响应时间和P95响应时间

**验收指标**：
- 平均响应时间 <= 1.5秒
- P95响应时间 <= 2秒

### 提示词设计指南

**提示词结构**：
```
# 角色定义
你是一位资深的数据分析架构师。

# 任务说明
你的任务是：
1. 分析问题复杂度，决定是否需要拆分
2. 为每个子任务从元数据中选择字段
3. 智能补全聚合、排序、筛选、粒度
4. 识别依赖关系和分配Stage

# 输入说明
- 用户问题：{question}
- 问题理解结果：{understanding_result}
- 元数据：{metadata}（包含维度层级信息）
- VizQL查询能力：{vizql_capabilities}

# 输出格式
请输出JSON格式的子任务列表：
{
  "subtasks": [
    {
      "question_id": "q1",
      "question_text": "...",
      "dims": [...],
      "metrics": [...],
      "filters": [...],
      "sort_by": {...},
      "stage": 1,
      "depends_on": [],
      "rationale": "..."
    }
  ]
}

# 执行顺序
1. 先判断是否需要拆分（基于VizQL查询能力）
2. 再为每个子任务选择字段（从元数据中选择）
3. 智能补全（聚合、排序、筛选、粒度）
4. 识别依赖关系和分配Stage

# 规则
{COMMON_FIELD_NAME_RULES}
{VIZQL_CAPABILITIES_SUMMARY}

# 注意事项
1. 字段名必须与元数据中的fieldCaption完全一致
2. 利用维度层级信息选择合适粒度
3. 智能补全缺失的信息（聚合、排序、筛选）
4. 避免不必要的拆分
5. 正确识别依赖关系
```

---


## 需求5：洞察Agent

### 详细功能说明

洞察Agent负责分析查询结果和统计检测结果，计算贡献度，生成业务洞察。

#### 1. 数据分析

**分析查询结果，计算贡献度**：
- 识别数据中的模式和趋势
- 计算各维度值的贡献百分比
- 结合统计检测结果识别异常

#### 2. 贡献度分析（核心功能）

**计算各维度值的贡献度**：
- **贡献百分比**：计算每个维度值占总量的百分比
- **贡献排名**：按贡献度排序（rank: 1, 2, 3...）
- **识别主要贡献因素**：找出贡献度最高的维度值
- **评估显著性**：判断贡献度的显著性（high/medium/low）

**注意**：不判断是否可下钻（由重规划Agent负责）

#### 3. 洞察生成

**生成自然语言描述**：
- 将统计结果转化为业务语言
- 提供业务解读
- 识别关键发现
- 生成新问题列表

#### 4. 结合统计检测

**分析统计检测器的异常结果**：
- 结合z-score等统计指标
- 识别统计显著性
- 为统计异常提供业务解释

### 输入输出详细示例

**输入**（~4,050 tokens）：
- 子任务问题
- VizQL查询结果（智能采样，最多30行）
- 统计报告（由统计检测器生成）
- 上下文信息

**输出**：
```json
{
  "key_findings": [
    "华东地区销售额最高，占总销售额的35%",
    "华东地区利润率异常低（5%），远低于平均水平（15%）"
  ],
  "metrics": {
    "total_sales": 1000000,
    "avg_sales": 250000,
    "max_sales": 350000,
    "min_sales": 50000
  },
  "contribution_analysis": [
    {
      "dimension": "地区",
      "dimension_value": "华东",
      "contribution_percentage": 35.0,
      "contribution_absolute": 350000,
      "rank": 1,
      "significance": "high"
    },
    {
      "dimension": "地区",
      "dimension_value": "华北",
      "contribution_percentage": 25.0,
      "contribution_absolute": 250000,
      "rank": 2,
      "significance": "high"
    },
    {
      "dimension": "地区",
      "dimension_value": "华南",
      "contribution_percentage": 20.0,
      "contribution_absolute": 200000,
      "rank": 3,
      "significance": "medium"
    }
  ],
  "anomalies": [
    "华东地区利润率异常低（5%），远低于平均水平（15%）",
    "西北地区销售额异常低，可能存在数据质量问题"
  ],
  "trends": [
    "销售额呈上升趋势",
    "利润率整体下降"
  ],
  "answered_questions": [
    "2016年各地区的销售额分布",
    "哪个地区销售额最高"
  ],
  "new_questions": [
    "华东地区利润率为什么这么低？",
    "华东地区各产品类别的利润率分别是多少？"
  ],
  "insight_reasoning": "基于贡献度分析和统计检测结果，华东地区虽然销售额最高，但利润率异常低，需要深入分析"
}
```

**注意**：
- `contribution_analysis`是核心输出，必须包含
- 不包含`can_drill_down`和`next_level_dimension`（由重规划Agent负责）
- `new_questions`供重规划Agent参考

### 详细验收标准

1. 关键发现识别准确率 >= 85%
2. 异常解释合理性 >= 80%
3. 行动建议可执行性 >= 75%
4. 响应时间 <= 2秒

---

## 需求6：重规划Agent

### 详细功能说明

重规划Agent负责基于洞察结果智能决策下一步分析方向，自动查找下钻维度，生成问题清单。

#### 1. 重规划决策

**评估分析完整性，决定是否继续**：
- 检查是否回答了用户的核心问题
- 评估分析的深度和广度（<80%需要继续）
- 判断重规划类型（drill_down、dimension_expansion等）
- **复杂问题必须走重规划流程**

#### 2. 下钻维度查找（核心功能）

**基于贡献度分析选择下钻目标**：
- 从contribution_analysis中找到贡献度最高的维度
- 从metadata中查找该维度的child_dimension属性
- 或从dimension_hierarchy中查找下一级维度
- 确认child_dimension存在则可下钻

**示例**：
- 贡献度最高：地区=华东（rank=1）
- 查找metadata：地区的child_dimension="城市"
- 确认可下钻：can_drill_down=True
- 生成下钻目标：drill_down_target={parent_dimension="地区", parent_value="华东", child_dimension="城市"}

#### 3. 问题清单生成

**生成自然语言问题**：
- 基于下钻目标生成问题
- 提供建议的维度、筛选条件、度量
- 为任务调度器提供完整的问题清单


### 输入输出详细示例

**输入**（~5,250 tokens）：
- 原始问题
- 问题理解结果
- 数据摘要（不是完整数据）
- 关键发现摘要

**输出**：
```json
{
  "should_replan": true,
  "replan_type": "drill_down",
  "drill_down_target": {
    "parent_dimension": "地区",
    "parent_value": "华东",
    "child_dimension": "城市",
    "can_drill_down": true
  },
  "new_questions": [
    "华东地区各城市的销售额和利润率分别是多少？",
    "华东地区各产品类别的利润率分别是多少？"
  ],
  "suggested_dimensions": ["城市", "产品类别"],
  "suggested_filters": ["地区=华东"],
  "suggested_metrics": ["销售额", "利润率"],
  "reasoning": "华东地区贡献度最高但利润率异常低，需要下钻到城市和产品类别进行分析",
  "confidence": 0.9,
  "max_rounds_reached": false
}
```

**重规划类型说明**（replan_type）：
- `drill_down`：维度下钻（更细粒度，如从"地区"到"城市"）
- `drill_up`：维度上卷（更粗粒度，如从"门店"到"地区"）
- `pivot`：横向对比（切换维度，如从"地区"到"产品类别"）
- `metric_expansion`：指标扩展（增加度量，如增加"利润率"）
- `time_adjustment`：时间窗口调整（如从"年"到"月"）
- `anomaly_focus`：异常聚焦（深入异常，如聚焦"华东地区"）
- `related_question`：相关问题探索（探索相关维度）
- `mixed`：混合类型（多种类型组合）

### 详细验收标准

1. 重规划决策准确率 >= 85%
2. 新问题质量评分 >= 80%
3. 最多重规划轮数按环境变量执行
4. 响应时间 <= 2秒

---

## 需求7：总结Agent

### 详细功能说明

总结Agent负责整合所有结果，生成结构化、易理解的分析报告。

#### 1. 结果整合

**去重和排序关键发现**：
- 合并多轮分析的关键发现
- 去除重复的发现
- 按重要性排序

#### 2. 执行摘要生成

**一句话回答原始问题**：
- 提炼核心结论
- 简洁明了
- 直接回答用户问题

#### 3. 分析路径回顾

**展示分析思路和过程**：
- 记录分析的步骤
- 展示重规划的路径
- 说明为什么这样分析

#### 4. 后续探索建议

**推荐深入分析方向**：
- 基于分析结果推荐后续问题
- 评估优先级
- 提供探索方向

### 输入输出详细示例

**输入**（~4,050 tokens）：
- 原始问题
- 关键发现摘要（去重后）
- 重规划历史

**输出**：
```json
{
  "executive_summary": "2016年华东地区销售额最高但利润率偏低，主要原因是电子产品类别的价格竞争激烈",
  "analysis_path": ["总体对比", "异常发现", "深入分析", "根因诊断"],
  "key_findings_summary": [...],
  "next_suggestions": [
    "分析华东地区的竞争对手策略",
    "评估价格调整的可行性"
  ]
}
```

### 详细验收标准

1. 执行摘要准确性 >= 90%
2. 分析路径完整性 100%
3. 后续建议质量评分 >= 80%
4. 响应时间 <= 2秒

---
