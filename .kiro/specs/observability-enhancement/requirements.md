# Requirements Document

## Introduction

本规范定义了 Tableau Assistant 系统的错误处理和可观测性增强功能。系统基于 LangChain/LangGraph 框架构建，需要引入结构化日志、请求追踪、分布式追踪和性能指标监控，以提升系统的可维护性和问题诊断能力。

由于 LangSmith 是收费服务，本方案将采用开源替代方案（OpenTelemetry + 本地存储）实现可观测性。

## Glossary

- **Correlation ID**: 请求追踪标识符，用于关联单个用户请求在整个工作流中的所有日志和追踪信息
- **Structured Logging**: 结构化日志，以 JSON 格式输出日志，便于日志聚合和查询
- **OpenTelemetry (OTel)**: 开源的可观测性框架，提供追踪、指标和日志的统一标准
- **Span**: OpenTelemetry 中的追踪单元，表示一个操作的开始和结束
- **LangGraph Node**: LangGraph 工作流中的处理节点，如 understanding、field_mapper、execute 等
- **Middleware**: 中间件，在请求处理链中执行横切关注点的组件
- **LLM Token**: 大语言模型处理的文本单元，用于计费和性能监控
- **Loguru**: Python 结构化日志库，提供简洁的 API 和丰富的格式化选项
- **Circuit Breaker**: 熔断器模式，当错误率超过阈值时自动停止请求

## Requirements

### Requirement 1

**User Story:** As a developer, I want structured logging with correlation IDs, so that I can trace requests across the entire workflow and quickly diagnose issues.

#### Acceptance Criteria

1. WHEN the system initializes THEN the Logging_System SHALL configure Loguru as the primary logging backend with JSON output format
2. WHEN an API request arrives THEN the Logging_System SHALL generate a unique correlation_id and attach it to all subsequent log entries for that request
3. WHEN a LangGraph node executes THEN the Logging_System SHALL include node_name, correlation_id, and execution_context in the log entry
4. WHEN logging sensitive data THEN the Logging_System SHALL redact API keys, tokens, and personal information before output
5. WHILE the system is running THEN the Logging_System SHALL support configurable log levels (DEBUG, INFO, WARNING, ERROR) per module

### Requirement 2

**User Story:** As a system operator, I want distributed tracing integrated with OpenTelemetry, so that I can visualize request flows and identify performance bottlenecks.

#### Acceptance Criteria

1. WHEN the application starts THEN the Tracing_System SHALL initialize OpenTelemetry with configurable exporters (console, OTLP, Jaeger)
2. WHEN a LangGraph workflow executes THEN the Tracing_System SHALL create a parent span for the workflow and child spans for each node
3. WHEN an LLM call is made THEN the Tracing_System SHALL record span attributes including model_name, prompt_tokens, completion_tokens, and latency_ms
4. WHEN a span completes THEN the Tracing_System SHALL record the status (OK, ERROR) and any error details
5. WHEN tracing is disabled via configuration THEN the Tracing_System SHALL use a no-op tracer with minimal overhead

### Requirement 3

**User Story:** As a system operator, I want performance metrics for critical paths, so that I can monitor system health and set up alerts.

#### Acceptance Criteria

1. WHEN a LangGraph node completes THEN the Metrics_System SHALL record execution duration as a histogram metric with node_name label
2. WHEN an LLM call completes THEN the Metrics_System SHALL record token consumption (prompt_tokens, completion_tokens) as counter metrics with model_name label
3. WHEN a workflow completes THEN the Metrics_System SHALL record success/failure as a counter metric with workflow_name and status labels
4. WHEN the metrics endpoint is queried THEN the Metrics_System SHALL expose metrics in Prometheus-compatible format
5. WHILE the system is running THEN the Metrics_System SHALL track active workflow count as a gauge metric

### Requirement 4

**User Story:** As a developer, I want fine-grained exception types, so that I can handle different error scenarios appropriately without catching broad exceptions.

#### Acceptance Criteria

1. WHEN a Tableau API call fails THEN the Exception_System SHALL raise a specific exception type (TableauAuthError, TableauRateLimitError, TableauTimeoutError) based on the error category
2. WHEN an LLM call fails THEN the Exception_System SHALL raise a specific exception type (LLMRateLimitError, LLMTimeoutError, LLMValidationError) based on the error category
3. WHEN a field mapping fails THEN the Exception_System SHALL raise FieldMappingError with the unmapped_term and available_candidates in the exception context
4. WHEN a workflow node fails THEN the Exception_System SHALL wrap the original exception with NodeExecutionError including node_name and correlation_id
5. IF an exception is caught with a broad except clause THEN the Exception_System SHALL log a warning with the exception type and suggest using specific exception handling

### Requirement 5

**User Story:** As a developer, I want the logging and tracing to integrate seamlessly with LangGraph callbacks, so that I can leverage the framework's built-in observability hooks.

#### Acceptance Criteria

1. WHEN a LangGraph callback fires THEN the Callback_System SHALL emit corresponding OpenTelemetry spans and structured log entries
2. WHEN the on_llm_start callback fires THEN the Callback_System SHALL create a span with model_name, prompt_length, and correlation_id attributes
3. WHEN the on_llm_end callback fires THEN the Callback_System SHALL close the span and record token_usage and response_length
4. WHEN the on_llm_error callback fires THEN the Callback_System SHALL mark the span as error and record the exception details
5. WHEN the on_tool_start callback fires THEN the Callback_System SHALL create a child span with tool_name and input_size attributes

### Requirement 6

**User Story:** As a system operator, I want request timeout and circuit breaker mechanisms, so that the system can gracefully handle downstream service failures.

#### Acceptance Criteria

1. WHEN an LLM request exceeds the configured timeout THEN the Resilience_System SHALL cancel the request and raise LLMTimeoutError
2. WHEN the Tableau API error rate exceeds 50% in a 60-second window THEN the Resilience_System SHALL open the circuit breaker and reject subsequent requests for 30 seconds
3. WHEN the circuit breaker is open THEN the Resilience_System SHALL return a cached response if available or raise CircuitBreakerOpenError
4. WHEN the circuit breaker half-opens THEN the Resilience_System SHALL allow one probe request to test service recovery
5. WHEN a transient error occurs THEN the Resilience_System SHALL retry with exponential backoff (1s, 2s, 4s) up to 3 times before failing

