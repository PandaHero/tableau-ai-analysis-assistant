# Implementation Plan

## Overview

Fix LLM output validation errors by enhancing Prompt thought chains and optimizing data model Field descriptions. Target: improve validation pass rate from 45.7% to >80%.

## Tasks

- [x] 1. 增强 understanding.py Prompt / Enhance understanding.py Prompt


  - 添加探索性查询处理思维链 / Add exploratory question handling chain
  - 使用粗颗粒度字段(level 1-2)进行探索 / Use coarse-grained fields (level 1-2) for exploration
  - _Requirements: 需求5_

- [x] 1.1 添加探索性查询处理步骤 / Add exploratory question handling step

  - 在 `get_specific_domain_knowledge()` 中添加 Step X / Add Step X to `get_specific_domain_knowledge()`
  - 引导 LLM 识别探索性意图 / Guide LLM to identify exploratory intent
  - 引导 LLM 设置 needs_exploration=true / Guide LLM to set needs_exploration=true
  - 引导 LLM 选择 1-2 个粗颗粒度维度(level 1-2) / Guide LLM to select 1-2 coarse-grained dimensions (level 1-2)
  - 引导 LLM 选择 1-2 个核心度量 / Guide LLM to select 1-2 core measures
  - _Requirements: 需求5_

- [x] 2. 增强 task_planner.py Prompt / Enhance task_planner.py Prompt

  - 添加 Intent 类型选择思维链 / Add Intent type selection chain
  - 强化字段映射验证 / Strengthen field mapping validation
  - _Requirements: 需求1, 需求2_

- [x] 2.1 添加 Intent 类型选择步骤 / Add Intent type selection step

  - 在 `get_specific_domain_knowledge()` 现有 Step 1 后添加 Step 2 / Add Step 2 after existing Step 1 in `get_specific_domain_knowledge()`
  - 引导 LLM 分析实体特征 / Guide LLM to analyze entity characteristics
  - 引导 LLM 为带时间粒度的日期字段选择 DateFieldIntent / Guide LLM to select DateFieldIntent for date fields with time granularity
  - 引导 LLM 为普通维度选择 DimensionIntent / Guide LLM to select DimensionIntent for regular dimensions
  - 引导 LLM 为度量选择 MeasureIntent / Guide LLM to select MeasureIntent for measures
  - 添加 CRITICAL 约束: date_function 只能出现在 DateFieldIntent / Add CRITICAL constraint: date_function only in DateFieldIntent
  - _Requirements: 需求1_

- [x] 2.2 强化字段映射验证 / Strengthen field mapping validation

  - 修改 `get_specific_domain_knowledge()` 中现有的 Step 1 / Modify existing Step 1 in `get_specific_domain_knowledge()`
  - 添加验证步骤: CRITICAL - technical_field 必须是 metadata.fields 中的精确名称 / Add verification step: CRITICAL - technical_field MUST be exact name from metadata.fields
  - 添加二次检查步骤: 确认所选字段出现在 metadata.fields 中 / Add double-check step: Confirm selected field appears in metadata.fields
  - 修改 Mapping rules #1 强调 CRITICAL 约束 / Modify Mapping rules #1 to emphasize CRITICAL constraint
  - _Requirements: 需求2_

- [x] 3. Optimize intent.py data model

  - Enhance DimensionIntent Field descriptions
  - Enhance DateFieldIntent docstring
  - _Requirements: 需求1_

- [x] 3.1 Enhance DimensionIntent.aggregation description

  - Modify `aggregation` field description
  - Add model-specific selection rules (when to use null, COUNTD, MIN/MAX)
  - Add CRITICAL constraint about DateFieldIntent
  - Remove LLM-known concepts, keep only model-specific rules
  - _Requirements: 需求1_

- [x] 3.2 Enhance DateFieldIntent docstring

  - Modify class docstring
  - Clarify distinction from DimensionIntent
  - Clarify distinction from DateFilterIntent
  - Use English only, keep concise
  - _Requirements: 需求1_

- [x] 4. Optimize question.py data model


  - Extend TimeRange model
  - Enhance processing_type Field description
  - _Requirements: 需求3, 需求4_

- [x] 4.1 Extend TimeRange model

  - Add `start_date` field (Optional[str])
  - Add `end_date` field (Optional[str])
  - Update field descriptions with model-specific usage rules
  - Keep `value` field for single time point
  - _Requirements: 需求4_

- [x] 4.2 Enhance processing_type Field description

  - Modify `processing_type` field description in PostProcessingSubQuestion
  - Add model-specific selection rules (when to use yoy, mom, etc.)
  - Remove LLM-known concept explanations
  - Keep only "Use X when Y" format
  - _Requirements: 需求3_

- [x] 5. Run validation tests


  - Run complete 35 test cases
  - Verify validation pass rate improvement
  - _Requirements: All_

- [x] 5.1 Run targeted test cases

  - Test `date_dimension_and_filter`: Verify DateFieldIntent generation
  - Test `aggregation`: Verify field mapping accuracy
  - Test `edge_yoy`: Verify processing_type selection
  - Test `edge_date_range`: Verify TimeRange parsing
  - Test `exploration_open`: Verify exploratory question handling
  - _Requirements: All_

- [x] 5.2 Analyze and iterate


  - Analyze any remaining failures
  - Identify patterns in failures
  - Iterate on Prompt or Schema if needed
  - _Requirements: All_

- [ ] 6. Checkpoint - Ensure all tests pass
  - Ensure all tests pass, ask the user if questions arise.
