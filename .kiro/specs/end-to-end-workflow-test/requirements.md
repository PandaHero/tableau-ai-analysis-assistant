# Requirements Document

## Introduction

本规范定义了一个端到端集成测试脚本的需求，该脚本用于测试Tableau Assistant从问题输入到结果输出的完整工作流程。测试将覆盖问题Boost、问题理解、任务规划、查询构建、查询执行等所有核心组件，并使用真实的Tableau数据源和元数据。

## Glossary

- **Test System**: 端到端集成测试系统，用于验证完整工作流程
- **Question Boost Agent**: 问题优化代理，负责增强和优化用户输入的问题
- **Understanding Agent**: 问题理解代理，负责提取问题的语义信息和业务意图
- **Task Planner Agent**: 任务规划代理，负责将问题转换为VizQL查询规格
- **Query Builder**: 查询构建器，负责将查询规格转换为VizQL查询请求
- **Query Executor**: 查询执行器，负责执行VizQL查询并返回结果
- **Metadata Manager**: 元数据管理器，负责获取和缓存Tableau数据源元数据
- **Store Manager**: 存储管理器，负责管理LangGraph Store中的数据
- **Runtime**: LangGraph运行时环境，提供上下文和存储访问
- **Real Data**: 真实数据，指从实际Tableau服务器获取的元数据和查询结果

## Requirements

### Requirement 1

**User Story:** 作为开发人员，我希望能够测试完整的问题处理流程，以便验证从用户输入到最终结果的所有组件是否正常工作

#### Acceptance Criteria

1. WHEN 测试脚本启动时，THE Test System SHALL 创建包含真实Tableau配置的Runtime环境
2. WHEN Runtime环境创建完成时，THE Test System SHALL 初始化Store Manager和Metadata Manager
3. THE Test System SHALL 使用环境变量中配置的真实DATASOURCE_LUID
4. THE Test System SHALL 支持UTF-8编码输出以正确显示中文字符
5. WHEN 测试执行失败时，THE Test System SHALL 提供清晰的错误信息和诊断建议

### Requirement 2

**User Story:** 作为开发人员，我希望测试能够验证问题Boost Agent的功能，以便确认问题优化和增强功能正常工作

#### Acceptance Criteria

1. WHEN 测试执行问题Boost阶段时，THE Test System SHALL 调用Question Boost Agent处理原始用户问题
2. THE Test System SHALL 验证Question Boost Agent返回优化后的问题文本
3. THE Test System SHALL 验证Question Boost Agent返回相关问题建议列表
4. THE Test System SHALL 显示问题优化前后的对比信息
5. WHEN Question Boost Agent执行完成时，THE Test System SHALL 记录执行时间和token使用情况

### Requirement 3

**User Story:** 作为开发人员，我希望测试能够验证问题理解Agent的功能，以便确认语义提取和意图识别正常工作

#### Acceptance Criteria

1. WHEN 测试执行问题理解阶段时，THE Test System SHALL 调用Understanding Agent分析优化后的问题
2. THE Test System SHALL 验证Understanding Agent返回问题类型识别结果
3. THE Test System SHALL 验证Understanding Agent提取的维度、度量和时间范围信息
4. THE Test System SHALL 验证Understanding Agent识别的日期需求（周开始日、节假日、农历）
5. THE Test System SHALL 显示提取的语义信息的详细内容
6. WHEN Understanding Agent执行完成时，THE Test System SHALL 记录执行时间和token使用情况

### Requirement 4

**User Story:** 作为开发人员，我希望测试能够验证元数据管理功能，以便确认元数据获取、缓存和增强功能正常工作

#### Acceptance Criteria

1. WHEN 测试执行元数据获取阶段时，THE Test System SHALL 通过Metadata Manager获取真实的数据源元数据
2. THE Test System SHALL 验证元数据包含数据源名称、字段列表、维度和度量信息
3. THE Test System SHALL 测试元数据缓存功能的读取和写入
4. THE Test System SHALL 测试增强元数据功能（维度层级和最大日期）
5. THE Test System SHALL 显示元数据的统计信息（字段数、维度数、度量数）
6. WHEN 元数据获取完成时，THE Test System SHALL 验证维度层级信息的完整性

### Requirement 5

**User Story:** 作为开发人员，我希望测试能够验证任务规划Agent的功能，以便确认查询规格生成和任务拆分正常工作

#### Acceptance Criteria

1. WHEN 测试执行任务规划阶段时，THE Test System SHALL 调用Task Planner Agent生成查询规格
2. THE Test System SHALL 提供真实的元数据和维度层级信息给Task Planner Agent
3. THE Test System SHALL 验证Task Planner Agent返回的查询任务列表
4. THE Test System SHALL 验证每个查询任务包含字段选择、筛选条件、聚合方式和排序规则
5. THE Test System SHALL 验证任务的Stage分配和依赖关系
6. THE Test System SHALL 显示生成的查询规格的详细内容
7. WHEN Task Planner Agent执行完成时，THE Test System SHALL 记录执行时间和token使用情况

### Requirement 6

**User Story:** 作为开发人员，我希望测试能够验证查询构建器的功能，以便确认VizQL查询请求生成正常工作

#### Acceptance Criteria

1. WHEN 测试执行查询构建阶段时，THE Test System SHALL 使用Query Builder将查询规格转换为VizQL请求
2. THE Test System SHALL 验证Query Builder生成的VizQL请求包含正确的字段引用
3. THE Test System SHALL 验证Query Builder正确处理筛选条件（包括日期筛选）
4. THE Test System SHALL 验证Query Builder正确处理聚合和排序规则
5. THE Test System SHALL 显示生成的VizQL请求的JSON结构
6. WHEN Query Builder执行完成时，THE Test System SHALL 验证生成的请求符合VizQL规范

### Requirement 7

**User Story:** 作为开发人员，我希望测试能够验证查询执行器的功能，以便确认VizQL查询执行和结果解析正常工作

#### Acceptance Criteria

1. WHEN 测试执行查询执行阶段时，THE Test System SHALL 使用Query Executor执行VizQL查询
2. THE Test System SHALL 验证Query Executor成功连接到真实的Tableau服务器
3. THE Test System SHALL 验证Query Executor返回查询结果数据
4. THE Test System SHALL 验证查询结果包含数据行和列信息
5. THE Test System SHALL 显示查询结果的统计信息（行数、列数、执行时间）
6. THE Test System SHALL 显示查询结果的前几行数据样本
7. WHEN 查询执行失败时，THE Test System SHALL 捕获并显示详细的错误信息

### Requirement 8

**User Story:** 作为开发人员，我希望测试能够验证Store Manager的功能，以便确认数据存储和缓存管理正常工作

#### Acceptance Criteria

1. WHEN 测试执行存储管理测试时，THE Test System SHALL 验证Store Manager的元数据缓存功能
2. THE Test System SHALL 测试Store Manager的缓存写入和读取操作
3. THE Test System SHALL 测试Store Manager的缓存清除功能
4. THE Test System SHALL 验证Store Manager正确处理缓存过期时间
5. THE Test System SHALL 显示缓存操作的执行结果和状态信息

### Requirement 9

**User Story:** 作为开发人员，我希望测试脚本能够提供清晰的输出格式，以便快速理解测试结果和诊断问题

#### Acceptance Criteria

1. THE Test System SHALL 使用分隔线和标题清晰地划分不同的测试阶段
2. THE Test System SHALL 为每个测试阶段提供编号和描述性标题
3. THE Test System SHALL 使用符号（✓、✗、⚠️）标识测试结果状态
4. THE Test System SHALL 显示每个阶段的关键输出数据和统计信息
5. THE Test System SHALL 在测试结束时提供完整的测试总结
6. THE Test System SHALL 记录每个阶段的执行时间以便性能分析

### Requirement 10

**User Story:** 作为开发人员，我希望测试脚本能够使用多个测试用例，以便验证不同类型问题的处理能力

#### Acceptance Criteria

1. THE Test System SHALL 支持配置多个测试问题用例
2. THE Test System SHALL 为每个测试用例执行完整的工作流程
3. THE Test System SHALL 支持不同复杂度的问题（简单查询、复杂聚合、多维分析）
4. THE Test System SHALL 支持不同类型的问题（趋势分析、对比分析、排名分析）
5. THE Test System SHALL 为每个测试用例生成独立的测试报告
6. WHEN 所有测试用例执行完成时，THE Test System SHALL 提供汇总统计信息
