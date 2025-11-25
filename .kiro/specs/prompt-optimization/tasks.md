# Implementation Tasks

## Task List

- [x] 1. 重构Base模板架构


  - 修改StructuredPrompt基类为4段式（Role + Task + Domain Knowledge + Constraints）
  - 移除Principles和Output Requirements sections
  - 更新get_system_message()方法以组装4个sections
  - 测试base类功能确保正常工作
  - _Requirements: Requirement 11_




- [ ] 2. 优化Question Boost Agent
  - [x] 2.1 实现新的QuestionBoostPrompt类


    - 实现get_role()：返回简洁角色定义（~10 tokens）
    - 实现get_task()：返回任务定义含简洁CoT（~30 tokens）


    - 实现get_domain_knowledge()：返回决策规则（MUST补全 vs DON'T补全）（~60 tokens）
    - 实现get_constraints()：返回3-5条约束（~30 tokens）
    - _Requirements: Requirement 7_



  - [x] 2.2 验证Token预算
    - 统计system message的token数
    - 确保总token数 < 400（目标330）
    - 如果超标，进一步精简Domain Knowledge
    - _Requirements: Requirement 1_
  - [x] 2.3 测试准确率



    - 准备5个测试问题（简单、中等、复杂各有）
    - 运行baseline和优化版本
    - 对比boosted_question和changes字段
    - 确保匹配率 > 95%
    - _Requirements: Requirement 12_

- [x] 3. 优化Understanding Agent



  - [x] 3.1 实现新的UnderstandingPrompt类


    - 实现get_role()：返回简洁角色定义（~12 tokens）
    - 实现get_task()：返回任务定义含简洁CoT（~25 tokens）
    - 实现get_domain_knowledge()：返回拆分决策表（~80 tokens）
    - 实现get_constraints()：返回3-5条约束（~30 tokens）
    - _Requirements: Requirement 8_


  - [x] 3.2 验证Token预算



    - 统计system message的token数
    - 确保总token数 < 600（目标547）
    - 如果超标，进一步精简Domain Knowledge




    - _Requirements: Requirement 1_
  - [x] 3.3 测试准确率
    - 准备10个测试问题（覆盖拆分/不拆分场景）
    - 运行baseline和优化版本
    - 对比mentioned_*, sub_questions, needs_exploration字段
    - 确保匹配率 > 95%
    - _Requirements: Requirement 12_

- [ ] 4. 优化Task Planner Agent
  - [x] 4.1 实现新的TaskPlannerPrompt类


    - 实现get_role()：返回简洁角色定义（~12 tokens）
    - 实现get_task()：返回任务定义含简洁CoT（~25 tokens）
    - 实现get_domain_knowledge()：返回映射规则（~120 tokens）
    - 实现get_constraints()：返回3-5条约束（~40 tokens）
    - _Requirements: Requirement 9_


  - [x] 4.2 验证Token预算

    - 统计system message的token数
    - 确保总token数 < 900（目标797）
    - 如果超标，进一步精简Domain Knowledge
    - _Requirements: Requirement 1_
  - [ ] 4.3 测试准确率


    - 准备10个测试问题（覆盖不同字段映射场景）
    - 运行baseline和优化版本
    - 对比field mappings和Intent types字段
    - 确保匹配率 > 95%
    - _Requirements: Requirement 12_

- [ ] 5. 优化Dimension Hierarchy Agent
  - [ ] 5.1 实现新的DimensionHierarchyPrompt类
    - 实现get_role()：返回简洁角色定义（~10 tokens）
    - 实现get_task()：返回任务定义含简洁CoT（~25 tokens）
    - 实现get_domain_knowledge()：返回level推断规则（~150 tokens）
    - 实现get_constraints()：返回3-5条约束（~30 tokens）
    - _Requirements: Requirement 11_
  - [ ] 5.2 验证Token预算
    - 统计system message的token数
    - 确保总token数 < 500（目标465）
    - 如果超标，进一步精简Domain Knowledge
    - _Requirements: Requirement 1_
  - [ ] 5.3 测试准确率
    - 准备5个测试场景（不同类型的维度组合）
    - 运行baseline和优化版本
    - 对比category, level, parent/child字段
    - 确保匹配率 > 95%
    - _Requirements: Requirement 12_

- [ ] 6. 集成测试和性能验证
  - [ ] 6.1 准备完整测试数据集
    - 收集20个真实用户问题
    - 分类：简单（5个）、中等（10个）、复杂（5个）
    - 覆盖各种场景：单一度量、多维度、拆分、探索式等
    - _Requirements: Requirement 12_
  - [ ] 6.2 端到端测试
    - 运行完整流程：Question Boost → Understanding → Task Planner
    - 记录每个Agent的响应时间（P95延迟）
    - 记录每个Agent的token消耗
    - 记录端到端的总响应时间
    - _Requirements: Requirement 12_
  - [ ] 6.3 准确率验证
    - 对比baseline和优化版本的输出
    - 计算关键字段的匹配率
    - 确保整体匹配率 > 95%
    - 如果不达标，分析失败case并调整
    - _Requirements: Requirement 12_
  - [ ] 6.4 性能验证
    - 验证Question Boost响应时间 < 2秒
    - 验证Understanding响应时间 2-3秒
    - 验证Task Planner响应时间 5-10秒
    - 验证Dimension Hierarchy响应时间 < 3秒
    - 如果不达标，分析瓶颈并优化
    - _Requirements: Requirement 1_

- [ ] 7. 失败分析和调整（如果准确率 < 95%）
  - 分析不匹配的case，识别pattern
  - 优先调整Field description（在Pydantic模型中）
  - 其次调整Domain Knowledge中的决策规则
  - 最后考虑添加1个精准示例（如果其他方法都失败）
  - 重新测试直到达标
  - _Requirements: Requirement 12_

- [ ] 8. 文档更新和部署
  - 更新Agent的docstring说明新的prompt策略
  - 更新README说明优化效果（token减少、响应时间提升）
  - 提交代码并创建PR
  - 部署到测试环境
  - 监控性能指标
  - _Requirements: All_
