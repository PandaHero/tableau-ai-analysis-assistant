# 需求文档

## 简介

本文档定义了修复 COUNTD 聚合在表计算（Table Calculation）中的问题的需求。当前系统存在以下问题：

1. **QueryBuilder 问题**：`_build_analysis_field` 方法中硬编码了 `aggregation=AggregationType.SUM`，忽略了 `AnalysisSpec.aggregation` 字段的值
2. **VizQL API 错误**：导致 COUNTD 度量的表计算使用了错误的聚合函数，VizQL API 返回 "Functions can only be specified for numerical or date fields" 错误

## 术语表

- **COUNTD**: Count Distinct，去重计数聚合函数
- **TableCalcField**: VizQL 表计算字段，用于执行窗口函数计算（如累计、排名、占比、移动平均、同比环比）
- **AnalysisSpec**: 语义查询中的分析规格，定义派生计算类型，包含 `aggregation` 字段
- **QueryBuilder**: 将语义查询转换为 VizQL 查询的节点
- **ExpressionGenerator**: 生成 VizQL 表达式的组件
- **_build_analysis_field**: QueryBuilder 中构建分析字段的方法，当前硬编码了 `aggregation=AggregationType.SUM`

## 需求

### 需求 1

**用户故事：** 作为数据分析师，我希望能够对 COUNTD 度量计算占比，以便了解去重计数在各维度上的分布情况。

#### 验收标准

1. 当 QueryBuilder._build_analysis_field 构建分析字段时，QueryBuilder 应使用 analysis.aggregation 而不是硬编码的 AggregationType.SUM
2. 当 ExpressionGenerator.generate 接收到 aggregation=COUNTD 时，ExpressionGenerator 应返回 function=FunctionEnum.COUNTD 的 GeneratedExpression
3. 当为 COUNTD 分析创建 TableCalcField 时，TableCalcField 的 function 应设置为 COUNTD
4. 当 VizQL API 接收到 COUNTD 表计算时，VizQL API 应成功执行，不返回验证错误

### 需求 2

**用户故事：** 作为数据分析师，我希望系统能够在所有表计算类型中正确处理 COUNTD 度量，以便对去重计数执行累计、排名、移动和同比计算。

#### 验收标准

1. 当 QueryBuilder 为 COUNTD 构建累计分析时，QueryBuilder 应将 aggregation=COUNTD 传递给 ExpressionGenerator
2. 当 QueryBuilder 为 COUNTD 构建排名分析时，QueryBuilder 应将 aggregation=COUNTD 传递给 ExpressionGenerator
3. 当 QueryBuilder 为 COUNTD 构建移动分析时，QueryBuilder 应将 aggregation=COUNTD 传递给 ExpressionGenerator
4. 当 QueryBuilder 为 COUNTD 构建同比分析时，QueryBuilder 应将 aggregation=COUNTD 传递给 ExpressionGenerator

### 需求 3

**用户故事：** 作为开发者，我希望代码修改最小化且聚焦，以避免引入回归问题。

#### 验收标准

1. 修改 _build_analysis_field 时，开发者应仅将 aggregation 参数从硬编码的 SUM 改为 analysis.aggregation
2. 当 analysis.aggregation 为 None 时，QueryBuilder 应默认使用 AggregationType.SUM 以保持向后兼容
3. 修复应用后，现有的 SUM 聚合测试应继续通过
