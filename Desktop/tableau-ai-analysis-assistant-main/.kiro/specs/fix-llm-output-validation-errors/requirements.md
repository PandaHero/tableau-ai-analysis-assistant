# 需求文档

## 简介

Tableau AI 分析助手在 LLM 输出处理中遇到验证失败问题。测试结果显示执行成功率为 74.3%,但验证通过率仅为 45.7%,表明 LLM 输出与预期数据模型存在系统性不符问题。已识别出五个关键错误模式:

1. **Date Function Schema 违规**: LLM 在 `dimension_intents` 中输出 `date_function` 字段,但该字段只应出现在 `date_field_intents` 中
2. **字段映射错误**: 业务术语如"销售额"被错误映射到不存在的字段,而非元数据中的有效字段
3. **枚举值不匹配**: Post-processing 类型使用无效枚举值如 "comparison",而非有效值 "yoy"
4. **日期范围解析失败**: 日期范围格式 "2024-01-01/2024-03-31" 无法被解析
5. **探索性查询处理不当**: 开放式问题生成空的 dimension_intents 和 measure_intents,导致查询失败

## 术语表

- **LLM**: Large Language Model - 生成查询计划和理解用户问题的 AI 系统
- **Pydantic**: Python 数据验证库,用于强制执行 schema 合规性
- **DimensionIntent**: 表示查询计划中维度字段的数据结构
- **DateFieldIntent**: 专门用于带时间函数的日期维度的数据结构
- **MeasureIntent**: 表示查询计划中度量/指标字段的数据结构
- **Schema Validation**: 验证 LLM 输出是否符合预期数据结构的过程
- **Business Term**: 面向用户的术语(如"销售额")
- **Technical Field**: 数据库字段名(如"netplamt"、"收入")
- **Metadata**: 数据源中可用字段及其属性
- **思维链(Chain of Thought)**: 引导 LLM 逐步思考的提示词结构
- **Intent**: 中间层数据结构,连接业务层和执行层

## 需求

### 需求 1: 问题类型枚举定义优化

**用户故事:** 作为问题理解代理,我希望 QuestionType 枚举能够准确反映问题的本质特征,以便正确分类用户问题。

#### 验收标准

1. WHEN QuestionType 枚举定义问题类型时, THEN 系统 SHALL 包含所有常见的分析问题类型
2. WHEN 问题涉及多个度量对比时, THEN 系统 SHALL 将其分类为"对比"类型而非"多维分解"
3. WHEN 问题涉及按维度分组展示时, THEN 系统 SHALL 将其分类为"多维分解"或"排名"类型
4. WHEN 问题涉及单一度量汇总时, THEN 系统 SHALL 将其分类为"汇总"类型而非"占比"
5. WHEN 问题涉及时间维度分析时, THEN 系统 SHALL 将其分类为"趋势"类型

### 需求 2: Intent列表字段默认值设置

**用户故事:** 作为数据验证系统,我希望 Intent 列表字段有明确的默认值,以便 LLM 输出空列表而非 null 值。

#### 验收标准

1. WHEN 定义包含 Intent 列表的数据模型时, THEN 系统 SHALL 使用 Field(default_factory=list) 而非 Optional[List[...]] = None
2. WHEN LLM 没有识别到相应的 Intent 时, THEN 系统 SHALL 输出空列表 [] 而非 null
3. WHEN Pydantic 验证 Intent 列表字段时, THEN 系统 SHALL 接受空列表作为有效值
4. WHEN 查询构建器处理 Intent 列表时, THEN 系统 SHALL 能够正确处理空列表
5. WHEN 所有 Intent 相关的列表字段定义时, THEN 系统 SHALL 统一使用 default_factory=list 模式

### 需求 3: 枚举值的 Field Description 增强

**用户故事:** 作为后处理处理器,我希望 processing_type 使用有效的枚举值,以便系统能够正确执行对比和计算操作。

#### 验收标准

1. WHEN PostProcessing 数据模型定义 processing_type 字段时, THEN Field description SHALL 清晰说明每个枚举值的使用场景
2. WHEN Field description 描述 'yoy' 枚举值时, THEN 系统 SHALL 说明其用于年度对比(如"2024年和2023年对比")
3. WHEN Field description 描述 'mom' 枚举值时, THEN 系统 SHALL 说明其用于月度对比(如"本月和上月对比")
4. WHEN understanding prompt 的思维链处理对比问题时, THEN 系统 SHALL 包含步骤指导 LLM 根据时间粒度选择正确的 processing_type
5. WHEN LLM 输出 processing_type 值时, THEN 该值 SHALL 是 Pydantic 模型中定义的有效枚举值之一

### 需求 4: TimeRange 数据模型扩展

**用户故事:** 作为日期筛选处理器,我希望 TimeRange 模型能够支持日期范围格式,以便正确解析用户指定的时间段。

#### 验收标准

1. WHEN TimeRange 数据模型定义 absolute 类型时, THEN 系统 SHALL 支持 start_date 和 end_date 字段
2. WHEN LLM 输出日期范围如"2024年1月到3月"时, THEN 系统 SHALL 将其转换为 start_date 和 end_date 格式
3. WHEN query_builder 处理 TimeRange 时, THEN 系统 SHALL 能够解析包含 start_date 和 end_date 的结构
4. WHEN TimeRange 包含单个值(如"2024")时, THEN 系统 SHALL 使用 value 字段
5. WHEN TimeRange 包含范围值时, THEN 系统 SHALL 使用 start_date 和 end_date 字段

### 需求 5: 探索性查询的思维链指导

**用户故事:** 作为问题理解代理,我希望能够正确处理探索性问题,以便为用户提供有意义的分析起点。

#### 验收标准

1. WHEN understanding prompt 的思维链识别探索性问题时, THEN 系统 SHALL 包含步骤指导 LLM 设置 needs_exploration=true
2. WHEN 思维链处理探索性问题时, THEN 系统 SHALL 指导 LLM 从 metadata 中选择 2-3 个关键维度作为分析起点
3. WHEN 思维链选择探索维度时, THEN 系统 SHALL 优先选择地理、时间、分类等高价值维度
4. WHEN 思维链处理探索性问题时, THEN 系统 SHALL 指导 LLM 从 metadata 中选择 2-3 个关键度量
5. WHEN 思维链选择探索度量时, THEN 系统 SHALL 优先选择收入、利润、数量等核心业务指标


