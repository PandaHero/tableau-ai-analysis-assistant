# 需求文档

## 简介

本需求文档定义了将语义解析器（Semantic Parser）中的表计算逻辑从自定义表计算（Custom Table Calculation）重构为快速表计算（Quick Table Calculation）的功能需求。同时，需要正确区分LOD表达式和表计算的使用场景，确保系统能够根据用户意图选择正确的计算方式。

### 背景

根据VizQL Data Service API（openapi.json），系统支持以下字段类型：
- **DimensionField** - 维度字段
- **MeasureField** - 度量字段（带聚合函数）
- **CalculatedField** - 计算字段（用于LOD表达式等自定义计算）
- **BinField** - 分箱字段
- **TableCalcField** - 表计算字段

### VizQL API表计算类型（TableCalcSpecification）

根据OpenAPI文档，`tableCalcType`枚举值如下：

**快速表计算类型**：
- `RANK` - 排名
- `RUNNING_TOTAL` - 累计总计
- `PERCENT_OF_TOTAL` - 总计百分比
- `DIFFERENCE_FROM` - 差异（与参考值的差）
- `PERCENT_DIFFERENCE_FROM` - 百分比差异（增长率）
- `PERCENT_FROM` - 百分比（相对于参考值）
- `MOVING_CALCULATION` - 移动计算
- `PERCENTILE` - 百分位

**自定义表计算类型**：
- `CUSTOM` - 自定义表计算公式
- `NESTED` - 嵌套表计算（引用其他表计算结果）

### VizQL API表计算通用结构

所有表计算都继承自`TableCalcSpecification`基类，包含两个必需字段：
- `tableCalcType` (required): 表计算类型枚举
- `dimensions` (required): `TableCalcFieldReference[]` - 分区维度数组

**TableCalcFieldReference结构**：
```json
{
  "fieldCaption": "string (required)",
  "function": "Function (optional)"
}
```

**TableCalcCustomSort结构**：
```json
{
  "fieldCaption": "string (required)",
  "function": "Function (required)",
  "direction": "SortDirection (required)"  // ASC | DESC
}
```

### 各快速表计算类型的完整参数定义

#### 1. RankTableCalcSpecification (RANK)
```json
{
  "tableCalcType": "RANK",
  "dimensions": [{"fieldCaption": "..."}],
  "rankType": "COMPETITION | MODIFIED COMPETITION | DENSE | UNIQUE",  // 默认: COMPETITION
  "direction": "ASC | DESC"  // 排序方向
}
```
- `rankType`: 排名类型
  - `COMPETITION`: 标准竞争排名（1,2,2,4）
  - `MODIFIED COMPETITION`: 修改的竞争排名（1,3,3,4）
  - `DENSE`: 密集排名（1,2,2,3）
  - `UNIQUE`: 唯一排名（1,2,3,4）
- `direction`: 排序方向，ASC升序/DESC降序

#### 2. RunningTotalTableCalcSpecification (RUNNING_TOTAL)
```json
{
  "tableCalcType": "RUNNING_TOTAL",
  "dimensions": [{"fieldCaption": "..."}],
  "aggregation": "SUM | AVG | MIN | MAX",  // 默认: SUM
  "restartEvery": {"fieldCaption": "..."},  // 可选，重新开始的维度
  "customSort": {...},  // 可选，自定义排序
  "secondaryTableCalculation": {...}  // 可选，二次表计算
}
```
- `aggregation`: 累计聚合方式
- `restartEvery`: 在哪个维度处重新开始累计
- `secondaryTableCalculation`: 在累计结果上再应用一个表计算

#### 3. PercentOfTotalTableCalcSpecification (PERCENT_OF_TOTAL)
```json
{
  "tableCalcType": "PERCENT_OF_TOTAL",
  "dimensions": [{"fieldCaption": "..."}],
  "levelAddress": {"fieldCaption": "..."},  // 可选，计算级别
  "customSort": {...}  // 可选，自定义排序
}
```
- `levelAddress`: 指定计算的级别（所在级别）

#### 4. DifferenceTableCalcSpecification (DIFFERENCE_FROM, PERCENT_DIFFERENCE_FROM, PERCENT_FROM)
```json
{
  "tableCalcType": "DIFFERENCE_FROM | PERCENT_DIFFERENCE_FROM | PERCENT_FROM",
  "dimensions": [{"fieldCaption": "..."}],
  "relativeTo": "PREVIOUS | NEXT | FIRST | LAST",  // 默认: PREVIOUS
  "levelAddress": {"fieldCaption": "..."},  // 可选
  "customSort": {...}  // 可选
}
```
- `relativeTo`: 参考值位置
  - `PREVIOUS`: 上一个值（环比）
  - `NEXT`: 下一个值
  - `FIRST`: 第一个值（与期初比较）
  - `LAST`: 最后一个值（与期末比较）

#### 5. MovingTableCalcSpecification (MOVING_CALCULATION)
```json
{
  "tableCalcType": "MOVING_CALCULATION",
  "dimensions": [{"fieldCaption": "..."}],
  "aggregation": "SUM | AVG | MIN | MAX",  // 默认: SUM
  "previous": 2,  // 默认: 2，向前取N个值
  "next": 0,  // 默认: 0，向后取N个值
  "includeCurrent": true,  // 默认: true，是否包含当前值
  "fillInNull": false,  // 默认: false，是否填充空值
  "customSort": {...},  // 可选
  "secondaryTableCalculation": {...}  // 可选，二次表计算
}
```

#### 6. PercentileTableCalcSpecification (PERCENTILE)
```json
{
  "tableCalcType": "PERCENTILE",
  "dimensions": [{"fieldCaption": "..."}],
  "direction": "ASC | DESC"  // 排序方向
}
```

#### 7. CustomTableCalcSpecification (CUSTOM)
```json
{
  "tableCalcType": "CUSTOM",
  "dimensions": [{"fieldCaption": "..."}],
  "levelAddress": {"fieldCaption": "..."},  // 可选
  "restartEvery": {"fieldCaption": "..."},  // 可选
  "customSort": {...}  // 可选
}
```
- 需要配合`TableCalcField.calculation`字段提供自定义公式

#### 8. NestedTableCalcSpecification (NESTED)
```json
{
  "tableCalcType": "NESTED",
  "dimensions": [{"fieldCaption": "..."}],
  "fieldCaption": "string (required)",  // 引用的表计算字段名
  "levelAddress": {"fieldCaption": "..."},  // 可选
  "restartEvery": {"fieldCaption": "..."},  // 可选
  "customSort": {...}  // 可选
}
```
- 用于引用`TableCalcField.nestedTableCalculations`中定义的其他表计算

### TableCalcField完整结构

```json
{
  "fieldCaption": "string (required)",  // 字段名称
  "fieldAlias": "string",  // 可选，字段别名
  "function": "Function",  // 可选，聚合函数
  "calculation": "string",  // 可选，自定义计算公式
  "tableCalculation": {...},  // required，表计算规格
  "nestedTableCalculations": [...],  // 可选，嵌套表计算数组
  "maxDecimalPlaces": "integer",  // 可选，小数位数
  "sortDirection": "ASC | DESC",  // 可选，排序方向
  "sortPriority": "integer"  // 可选，排序优先级
}
```

### LOD表达式（通过CalculatedField实现）

VizQL API中LOD表达式通过`CalculatedField`类型实现：

```json
{
  "fieldCaption": "每个客户的销售额",
  "calculation": "{FIXED [客户ID] : SUM([销售额])}"
}
```

**LOD表达式语法**：
- `{FIXED [维度1], [维度2] : 聚合表达式}` - 固定LOD
- `{INCLUDE [维度] : 聚合表达式}` - 包含LOD
- `{EXCLUDE [维度] : 聚合表达式}` - 排除LOD
- `{聚合表达式}` - 表范围LOD（等价于`{FIXED : 聚合表达式}`）


### LOD与表计算的核心差异

**LOD表达式**：
- 在数据源级别计算，结果是静态的数据字段
- 可以访问原始数据行级别的信息
- 计算发生在聚合之前
- 通过`CalculatedField.calculation`字段传递LOD表达式字符串

**表计算**：
- 在可视化项级别对已聚合的数据进行二次计算
- 只能在已聚合的视图数据上运算
- 计算发生在聚合之后
- 通过`TableCalcField.tableCalculation`字段传递表计算规格

### 选择决策流程

**使用LOD的场景**：
1. 需要访问原始数据行级别的信息（如：每个客户的首次购买日期）
2. 需要创建独立于视图的、可重用的指标（如：每个客户的终身消费额）
3. 需要在不同于视图的粒度上进行聚合
4. 需要一个"锚点"值，无论视图如何变化都保持不变

**使用表计算的场景**：
1. 对视图内已聚合的数据进行排名 → `RANK`
2. 对视图内已聚合的数据进行累计 → `RUNNING_TOTAL`
3. 对视图内已聚合的数据计算占比 → `PERCENT_OF_TOTAL`
4. 对视图内已聚合的数据计算差异或增长率 → `DIFFERENCE_FROM` / `PERCENT_DIFFERENCE_FROM`
5. 对视图内已聚合的数据计算移动平均 → `MOVING_CALCULATION`
6. 需要相对位置计算（前N行、后N行）

### 典型业务场景与API映射

| 业务场景 | 计算类型 | API映射 |
|---------|---------|---------|
| 销售额排名 | 表计算 | `RANK` |
| YTD累计销售额 | 表计算 | `RUNNING_TOTAL` + `restartEvery` |
| 子类别占大类百分比 | 表计算 | `PERCENT_OF_TOTAL` + `dimensions` |
| 环比增长率 | 表计算 | `PERCENT_DIFFERENCE_FROM` + `relativeTo: PREVIOUS` |
| 同比增长率 | 表计算 | `PERCENT_DIFFERENCE_FROM` + 适当的`dimensions` |
| 滚动3个月平均 | 表计算 | `MOVING_CALCULATION` + `previous: 2, includeCurrent: true` |
| 每个客户首次购买日期 | LOD | `CalculatedField` + `{FIXED [客户ID] : MIN([订单日期])}` |
| 每个客户终身消费额 | LOD | `CalculatedField` + `{FIXED [客户ID] : SUM([销售额])}` |
| 客户留存分析 | LOD+表计算 | 先用LOD计算首购日期，再用表计算分析留存 |

## 术语表

- **语义解析器（Semantic_Parser）**: 负责将用户自然语言问题转换为结构化查询
- **第一步输出（Step1_Output）**: 包含restated_question、what、where、how_type
- **第二步输出（Step2_Output）**: 包含computations，需要对齐VizQL API结构
- **TableCalcField**: VizQL API中的表计算字段类型
- **TableCalcSpecification**: 表计算规格，定义表计算的类型和参数
- **CalculatedField**: VizQL API中的计算字段类型，用于LOD表达式
- **dimensions**: 表计算的分区维度，在每个分区内独立执行计算
- **levelAddress**: 所在级别，用于设置计算重启点
- **restartEvery**: 重新开始的维度
- **customSort**: 自定义排序
- **secondaryTableCalculation**: 二次表计算
- **TableCalcFieldReference**: 字段引用，包含fieldCaption和可选的function
- **Function**: 聚合函数枚举（SUM、AVG、COUNT、COUNTD、MIN、MAX等）
- **SortDirection**: 排序方向枚举（ASC、DESC）

## 需求

### 需求1：简化HowType枚举为二元分类

**用户故事：** 作为开发者，我希望Step1只判断是否需要复杂计算，具体计算类型由Step2推理，以便简化Step1职责并支持组合场景。

#### 验收标准

1. 当用户问题被分类时，Step1应当将how_type设置为SIMPLE或COMPLEX
2. 当用户问题是简单聚合且无复杂计算时，Step1应当将how_type设置为SIMPLE
3. 当用户问题需要排名、累计、环比、移动平均、占比等表计算时，Step1应当将how_type设置为COMPLEX
4. 当用户问题需要LOD表达式（如每个客户的首购日期）时，Step1应当将how_type设置为COMPLEX
5. 当用户问题需要LOD与表计算组合（如新客户销售额排名）时，Step1应当将how_type设置为COMPLEX
6. 当how_type为SIMPLE时，系统不执行Step2
7. 当how_type为COMPLEX时，系统执行Step2来推理具体的计算类型和参数

### 需求2：Step2输出对齐VizQL API的TableCalcField结构

**用户故事：** 作为开发者，我希望Step2的输出能够直接对齐VizQL API的TableCalcField结构，以便减少转换逻辑的复杂度。

#### 验收标准

1. 当how_type为TABLE_CALC时，Step2_Output应当生成符合TableCalcField结构的输出
2. Step2_Output应当包含tableCalcType字段，值为以下之一：RANK、RUNNING_TOTAL、PERCENT_OF_TOTAL、DIFFERENCE_FROM、PERCENT_DIFFERENCE_FROM、PERCENT_FROM、MOVING_CALCULATION、PERCENTILE
3. Step2_Output应当包含dimensions字段，类型为TableCalcFieldReference数组
4. 当tableCalcType为RANK时，Step2_Output应当包含rankType（默认COMPETITION）和direction
5. 当tableCalcType为RUNNING_TOTAL时，Step2_Output应当包含aggregation（默认SUM）、可选的restartEvery、可选的customSort、可选的secondaryTableCalculation
6. 当tableCalcType为PERCENT_OF_TOTAL时，Step2_Output应当包含可选的levelAddress和可选的customSort
7. 当tableCalcType为DIFFERENCE_FROM、PERCENT_DIFFERENCE_FROM或PERCENT_FROM时，Step2_Output应当包含relativeTo（默认PREVIOUS）、可选的levelAddress、可选的customSort
8. 当tableCalcType为MOVING_CALCULATION时，Step2_Output应当包含aggregation（默认SUM）、previous（默认2）、next（默认0）、includeCurrent（默认true）、fillInNull（默认false）、可选的customSort、可选的secondaryTableCalculation
9. 当tableCalcType为PERCENTILE时，Step2_Output应当包含direction

### 需求3：Step2输出支持CalculatedField结构用于LOD表达式

**用户故事：** 作为开发者，我希望Step2的输出能够支持CalculatedField结构，以便系统能够生成LOD表达式。

#### 验收标准

1. 当how_type为LOD时，Step2_Output应当生成符合CalculatedField结构的输出
2. Step2_Output应当包含fieldCaption字段，用于指定计算字段的名称
3. Step2_Output应当包含calculation字段，用于存储LOD表达式字符串
4. Step2_Output应当包含lod_type字段，值为FIXED、INCLUDE或EXCLUDE
5. Step2_Output应当包含lod_dimensions字段，用于指定LOD计算的维度列表
6. Step2_Output应当包含aggregation字段，用于指定聚合函数（SUM、AVG、MIN、MAX、COUNT、COUNTD）
7. 系统应当能够根据lod_type、lod_dimensions和aggregation自动生成正确的LOD表达式字符串

### 需求4：重构Step2 Prompt引导LLM选择正确的计算类型和参数

**用户故事：** 作为开发者，我希望Step2 Prompt能够引导LLM正确选择表计算类型和参数，以便生成的计算定义准确且完整。

#### 验收标准

1. Step2_Prompt应当包含VizQL API中每种tableCalcType的完整参数说明
2. Step2_Prompt应当包含dimensions字段的语义说明：分区维度，在每个分区内独立执行计算
3. Step2_Prompt应当包含levelAddress字段的语义说明：所在级别，用于设置计算重启点
4. Step2_Prompt应当包含restartEvery字段的语义说明：在哪个维度处重新开始计算
5. Step2_Prompt应当包含relativeTo字段的语义说明：参考值位置（PREVIOUS/NEXT/FIRST/LAST）
6. Step2_Prompt应当包含每种快速表计算类型的业务场景示例
7. Step2_Prompt应当包含LOD表达式的语法和使用场景说明
8. 当how_type为TABLE_CALC时，Step2_Prompt应当引导LLM选择适当的tableCalcType和对应参数
9. 当how_type为LOD时，Step2_Prompt应当引导LLM选择适当的lod_type和维度

### 需求5：重构QueryBuilder直接生成VizQL API请求

**用户故事：** 作为开发者，我希望QueryBuilder能够直接生成VizQL API请求，以便减少中间转换步骤。

#### 验收标准

1. 当how_type为TABLE_CALC时，QueryBuilder应当生成TableCalcField对象
2. TableCalcField.fieldCaption应当来自Step2_Output的目标字段
3. TableCalcField.tableCalculation应当包含完整的TableCalcSpecification
4. TableCalcField.tableCalculation.dimensions应当包含TableCalcFieldReference数组
5. 当tableCalcType为RANK时，tableCalculation应当包含rankType和direction
6. 当tableCalcType为RUNNING_TOTAL时，tableCalculation应当包含aggregation，以及可选的restartEvery、customSort、secondaryTableCalculation
7. 当tableCalcType为PERCENT_OF_TOTAL时，tableCalculation应当包含可选的levelAddress和customSort
8. 当tableCalcType为DIFFERENCE_FROM/PERCENT_DIFFERENCE_FROM/PERCENT_FROM时，tableCalculation应当包含relativeTo，以及可选的levelAddress和customSort
9. 当tableCalcType为MOVING_CALCULATION时，tableCalculation应当包含aggregation、previous、next、includeCurrent、fillInNull，以及可选的customSort和secondaryTableCalculation
10. 当how_type为LOD时，QueryBuilder应当生成CalculatedField对象，其中calculation为LOD表达式字符串

### 需求6：dimensions语义正确映射

**用户故事：** 作为开发者，我希望dimensions能够正确映射到VizQL API的TableCalcSpecification.dimensions字段，以便表计算的分区范围正确。

#### 验收标准

1. Step2_Output.dimensions字段应当映射到TableCalcSpecification.dimensions
2. dimensions数组中的每个元素应当是TableCalcFieldReference对象，包含fieldCaption和可选的function
3. 当dimensions为空数组时，表计算应当在所有行上计算（全局范围）
4. 当dimensions包含维度时，表计算应当在每个分区内独立执行
5. 当用户问题指定了分区范围（如"按地区"、"每个类别内"）时，系统应当将对应维度添加到dimensions

### 需求7：LOD与表计算组合使用

**用户故事：** 作为开发者，我希望系统能够支持LOD与表计算的组合使用，以便能够处理复杂的分析场景（如客户留存分析）。

#### 验收标准

1. Step2应当能够在computations列表中同时输出LOD类型和表计算类型的Computation
2. 当用户问题需要先创建独立于视图的原子指标，再对其进行视角转换时，Step2应当先输出LOD Computation，再输出表计算Computation
3. QueryBuilder应当按正确顺序生成字段：先生成CalculatedField（LOD），再生成TableCalcField（表计算）
4. 系统应当支持在TableCalcField中引用CalculatedField的结果
5. 当视图维度已经包含所需的聚合粒度时，Step2应当仅输出表计算Computation而不需要LOD
