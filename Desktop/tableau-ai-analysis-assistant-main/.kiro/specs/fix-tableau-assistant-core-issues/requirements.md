# 需求文档 - Tableau Assistant 核心问题修复

## 简介

基于完整测试结果分析(test_complete_pipeline_results.json),Tableau AI 分析助手存在8个核心问题导致查询执行失败或验证失败。这些问题分为三类:
1. **数据模型问题** (Pydantic模型定义)
2. **模板问题** (Prompt设计)
3. **代码逻辑问题** (Agent实现)

测试统计:
- 总测试数: 35
- 成功执行: 27 (77.1%)
- 验证通过: 15 (42.9%)

## 术语表

- **Understanding Agent**: 问题理解代理,负责分析用户问题并拆分成子问题
- **Task Planner Agent**: 任务规划代理,负责将子问题转换为查询计划
- **Dimension Hierarchy Agent**: 维度层级推断代理,负责分析字段的层级关系
- **Schema Linking**: 将业务术语映射到技术字段的过程
- **Embedding**: 文本向量化表示,用于计算语义相似度
- **Business Term**: 面向用户的术语(如"销售额"、"省份"、"门店")
- **Technical Field**: 数据源中的实际字段名(如"netplamt"、"pro_name"、"门店编码")
- **Metadata**: 数据源的元数据,包含所有可用字段及其属性
- **FilterIntent**: 筛选条件意图,表示WHERE子句
- **DimensionIntent**: 维度意图,表示分组字段
- **MeasureIntent**: 度量意图,表示聚合计算
- **DateFieldIntent**: 日期字段意图,包含时间函数(YEAR/MONTH等)
- **VizQL**: Tableau的查询语言,有特定的查询能力限制
- **Pydantic Model**: Python数据验证模型,定义数据结构和验证规则

## 需求

### 需求 1: 字段映射使用Embedding语义搜索

**用户故事:** 作为 Task Planner Agent,我希望使用embedding语义相似度来映射字段,而不是让LLM猜测,以便提高字段映射的准确性和一致性。

**问题现象:**
- "销售额"和"利润"都映射到了`netplamt_30`(错误)
- "门店"映射到了`门店编码`而不是`门店名称`
- LLM输出不存在的字段名如"销售额"

**根本原因:** Task Planner让LLM通过prompt中的"语义理解"来猜测字段名,这种方法不可靠且不一致。

#### 验收标准

1. WHEN Task Planner需要映射业务术语到技术字段时, THEN 系统 SHALL 使用embedding模型计算语义相似度
2. WHEN 计算字段相似度时, THEN 系统 SHALL 对业务术语和候选字段(包括字段名、描述、示例值)进行向量化
3. WHEN 选择最佳匹配字段时, THEN 系统 SHALL 基于余弦相似度排序并选择得分最高的字段
4. WHEN 最高相似度得分低于阈值(如0.5)时, THEN 系统 SHALL 使用规则映射作为fallback
5. WHEN 字段映射完成后, THEN 系统 SHALL 验证所选字段确实存在于metadata.fields中

### 需求 2: 元数据按维度层级筛选后推送

**用户故事:** 作为系统架构师,我希望根据问题理解的结果筛选元数据后再推送给Task Planner,以便减少LLM的选择空间并提高准确率。

**问题现象:**
- Task Planner收到全量字段,导致选择困难
- "门店"相关问题在所有字段中搜索,而不是只在地理类别中搜索

**根本原因:** 当前实现将所有metadata字段都推送给Task Planner,没有根据问题理解的维度类别进行筛选。

#### 验收标准

1. WHEN Understanding Agent识别出维度实体(如"门店")时, THEN 系统 SHALL 记录该实体的语义类别(如"地理")
2. WHEN 推送metadata给Task Planner时, THEN 系统 SHALL 只包含相关类别的字段
3. WHEN 维度类别为"地理"时, THEN 系统 SHALL 只推送dimension_hierarchy中geographic类别的字段
4. WHEN 维度类别为"时间"时, THEN 系统 SHALL 只推送temporal类别的字段
5. WHEN 无法确定类别时, THEN 系统 SHALL 推送所有字段作为fallback

### 需求 3: 问题类型枚举优化(数据模型)

**用户故事:** 作为数据验证系统,我希望QuestionType枚举能够准确反映问题的本质特征,以便正确分类用户问题。

**问题现象:**
- "显示各省份的销售额"被识别为"多维分解",应该是"排名"
- "显示各省份的销售额和利润"被识别为"多维分解",应该是"对比"
- "总销售额是多少"被识别为"诊断",应该是"汇总"
- "最近一个月各省份的销售额"被识别为"多维分解",应该是"趋势"

**根本原因:** QuestionType枚举定义不清晰,LLM难以区分不同类型。

#### 验收标准

1. WHEN QuestionType枚举定义问题类型时, THEN 每个类型 SHALL 有清晰的Field description说明使用场景
2. WHEN 问题涉及单一维度展示度量时, THEN 系统 SHALL 将其分类为"排名"类型
3. WHEN 问题涉及多个度量对比时, THEN 系统 SHALL 将其分类为"对比"类型
4. WHEN 问题涉及单一度量汇总(无维度)时, THEN 系统 SHALL 将其分类为"汇总"类型
5. WHEN 问题涉及时间维度分析时, THEN 系统 SHALL 将其分类为"趋势"类型

### 需求 4: Intent列表字段默认值设置(数据模型)

**用户故事:** 作为数据验证系统,我希望Intent列表字段有明确的默认值,以便LLM输出空列表而非null值。

**问题现象:**
- Task Planner输出`"dimension_intents": null`而不是`[]`
- 导致后续处理出错

**根本原因:** Pydantic模型定义使用`Optional[List[...]] = None`,LLM倾向于输出null。

#### 验收标准

1. WHEN 定义包含Intent列表的数据模型时, THEN 系统 SHALL 使用`Field(default_factory=list)`而非`Optional[List[...]] = None`
2. WHEN LLM没有识别到相应的Intent时, THEN 系统 SHALL 输出空列表`[]`而非null
3. WHEN Pydantic验证Intent列表字段时, THEN 系统 SHALL 接受空列表作为有效值
4. WHEN 所有Intent相关的列表字段定义时, THEN 系统 SHALL 统一使用`default_factory=list`模式
5. WHEN 查询构建器处理Intent列表时, THEN 系统 SHALL 能够正确处理空列表

### 需求 5: 日期字段年份自动补全

**用户故事:** 作为Task Planner Agent,我希望在处理月度/季度趋势问题时自动补全年份,以便查询返回完整的时间维度。

**问题现象:**
- "显示每月的销售额"只生成MONTH,没有YEAR
- "总销售额是多少"也缺少年份筛选
- LLM将日期字段放在date_field_intents中,但没有生成dimension_intents

**根本原因:** Task Planner的prompt没有明确指导在月度/季度问题中自动补全年份。

#### 验收标准

1. WHEN 子问题包含"每月"等月度关键词时, THEN Task Planner SHALL 在date_field_intents中同时包含YEAR和MONTH
2. WHEN 子问题包含"每季度"等季度关键词时, THEN Task Planner SHALL 在date_field_intents中同时包含YEAR和QUARTER
3. WHEN 用户未明确指定年份时, THEN 系统 SHALL 基于数据的max_date自动推断年份范围
4. WHEN 生成DateFieldIntent时, THEN 系统 SHALL 确保date_function列表按时间粒度从粗到细排序(YEAR在MONTH之前)
5. WHEN 问题为汇总类型(如"总销售额")时, THEN 系统 SHALL 添加最新年份的日期筛选

### 需求 6: 筛选条件自动提取

**用户故事:** 作为Task Planner Agent,我希望能够从问题文本中自动提取筛选条件,以便生成正确的FilterIntent。

**问题现象:**
- "广东省O2O渠道的销售额"没有生成FilterIntent
- 筛选条件"O2O渠道"被忽略

**根本原因:** Task Planner的prompt缺少筛选条件提取的指导步骤。

#### 验收标准

1. WHEN 问题文本包含地理位置(如"广东省")时, THEN Task Planner SHALL 生成对应的FilterIntent
2. WHEN 问题文本包含渠道信息(如"O2O渠道")时, THEN Task Planner SHALL 生成对应的FilterIntent
3. WHEN 生成FilterIntent时, THEN 系统 SHALL 正确映射业务术语到技术字段名(如"广东省"→field="pro_name", values=["广东"])
4. WHEN 问题包含多个筛选条件时, THEN 系统 SHALL 为每个条件生成独立的FilterIntent
5. WHEN 筛选条件的值需要模糊匹配时, THEN 系统 SHALL 使用operator="contains"而非"equals"

### 需求 7: 年度对比问题拆分

**用户故事:** 作为Understanding Agent,我希望能够识别年度对比问题并按VizQL查询能力拆分成多个子问题,以便VizQL能够分别查询不同年份的数据。

**问题现象:**
- "2024年和2023年的销售额对比"没有拆分成多个子问题
- 导致Task Planner尝试在一个查询中处理对比,但VizQL不支持

**根本原因:** Understanding模板没有根据VizQL查询能力进行问题拆解的指导。

#### 验收标准

1. WHEN 用户问题包含"2024年和2023年对比"等年度对比关键词时, THEN Understanding Agent SHALL 识别为对比类型问题
2. WHEN Understanding Agent识别到年度对比问题时, THEN 系统 SHALL 拆分为至少3个子问题
3. WHEN 拆分年度对比问题时, THEN 系统 SHALL 为每个年份创建独立的查询子问题(execution_type="query")
4. WHEN 拆分年度对比问题时, THEN 系统 SHALL 创建一个后处理子问题用于对比计算(execution_type="post_processing")
5. WHEN 后处理子问题的processing_type为年度对比时, THEN 系统 SHALL 使用"yoy"枚举值

### 需求 8: 维度层级推断优化

**用户故事:** 作为Dimension Hierarchy Agent,我希望有清晰的推断规则和模板,以便准确识别字段的层级关系和语义类别。

**问题现象:**
- 维度层级推断不准确
- 影响元数据筛选和字段选择

**根本原因:** Dimension Hierarchy的模板和数据模型没有按照Understanding和Task Planner的标准进行优化。

#### 验收标准

1. WHEN Dimension Hierarchy Agent分析字段时, THEN 系统 SHALL 使用结构化的思维链指导
2. WHEN 推断字段层级时, THEN 系统 SHALL 综合考虑字段名、示例值、unique_count和语义含义
3. WHEN 识别字段类别时, THEN 系统 SHALL 明确标注geographic/temporal/product/customer等类别
4. WHEN 推断parent-child关系时, THEN 系统 SHALL 基于层级和语义进行判断
5. WHEN 输出层级结果时, THEN 系统 SHALL 包含confidence score表示推断的置信度
