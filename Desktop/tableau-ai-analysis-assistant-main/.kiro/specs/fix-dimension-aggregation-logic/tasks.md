# Implementation Plan

## Overview

This implementation plan addresses the dimension aggregation logic error in the Tableau Assistant system. The fix involves updating data models, prompts, and adding defensive code to ensure dimensions used for grouping do not receive aggregation functions.

## Tasks

- [x] 1. Update data model Field descriptions



  - Update dimension_aggregations Field description in QuerySubQuestion
    * Include Usage section (when to include/exclude)
    * List Values: 'COUNTD' (count distinct values)
    * Explain special value COUNTD (Tableau-specific)
  - Update measure_aggregations Field description in QuerySubQuestion
    * Include Usage section (include ALL measures)
    * List Values: 'SUM' (default), 'AVG', 'MIN', 'MAX', 'COUNT'
    * Mark default value (SUM)
    * Do NOT explain common values (LLM already knows)
  - Follow LLM prior knowledge boundary principle
  - _Requirements: 1.1, 4.1_




- [x] 2. Update Understanding Agent role and prompt



  - Update get_role() method
    * Define SQL roles: Dimension (Aggregated/Grouped), Measure (Always aggregated)
  - Modify get_specific_domain_knowledge() method
    * Add entity role determination logic
    * For dimensions: Analyze if being counted/aggregated
    * For measures: Analyze aggregation requested
    * Include ONLY judgment logic, NO field filling rules
  - Update get_constraints() method
    * Add constraint: determine SQL role for each entity
  - Ensure English-only, concise, SQL-based semantics
  - _Requirements: 1.2, 1.3, 4.1, 4.2_

- [x] 3. Add defensive code in Understanding Agent



  - Implement _fix_dimension_aggregations() method
    * Detect error: all dimensions have aggregations
    * Auto-fix: clear dimension_aggregations to {}
    * Add warning log with details
  - Integrate into execute() method
    * Call _fix_dimension_aggregations() after LLM output
    * Apply fix before returning result
  - Add comprehensive logging for debugging
  - _Requirements: 1.4, 4.3_


- [x] 4. Update Task Planner Agent prompt

  - Modify get_specific_domain_knowledge() method
    * Add DimensionIntent.aggregation mapping rule
    * Dimension IN dimension_aggregations → aggregation = dict value
    * Dimension NOT IN dimension_aggregations → aggregation = null
  - Update get_constraints() method
    * Add constraint: set aggregation per dimension_aggregations dict
  - Keep concise and precise
  - _Requirements: 2.1, 4.2_

- [x] 5. Verify Query Builder logic



  - Review _build_dimension_field() method
    * Verify: aggregation=None → BasicField (no function property)
    * Verify: aggregation="COUNTD" → FunctionField (with function property)
  - Add validation in _validate_query() if needed
    * Check: dimension fields should not have invalid functions
    * Check: measure fields must have aggregation functions
  - Test with sample DimensionIntent and MeasureIntent
  - _Requirements: 3.1, 3.2, 3.3_

- [x] 6. Update test cases



  - Review existing test cases in test_complete_pipeline.py
    * Update expected VizQL for grouping dimensions (no function)
    * Update expected VizQL for counted dimensions (with COUNTD)
  - Verify test cases match Tableau VizQL API spec
    * Grouping dimension: {"fieldCaption": "pro_name"}
    * Counted dimension: {"fieldCaption": "store", "function": "COUNTD"}
  - Add edge case tests if needed
    * All dimensions for grouping
    * Mix of grouping and counted dimensions
  - _Requirements: 5.1, 5.2, 5.3, 6.1, 6.2_

- [x] 7. Run integration tests




  - Execute all test cases in test_complete_pipeline.py
    * Run: python -m pytest tableau_assistant/tests/test_complete_pipeline.py
  - Verify previously failing tests now pass
    * Check tests that failed due to dimension aggregation errors
  - Verify previously passing tests still pass
    * Ensure no regression
  - Analyze results
    * Check query success rate
    * Review any remaining failures
  - _Requirements: 5.1, 5.2, 5.3_

- [ ] 8. Documentation and validation
  - Update code comments in modified files
    * Add docstrings for new methods
    * Explain key logic changes
  - Verify all changes follow best practices
    * Data model: includes usage, values, special value explanations
    * Prompt: includes only judgment logic, SQL-based semantics
    * Separation of concerns: model vs prompt clearly separated
  - Final checks
    * Ensure English-only in all prompts
    * Verify LLM prior knowledge boundary principle applied
    * Confirm no judgment logic in data model descriptions
  - _Requirements: 4.4, 5.4_
