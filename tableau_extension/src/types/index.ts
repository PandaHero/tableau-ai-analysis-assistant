/**
 * TypeScript类型定义
 */

// 导入Tableau类型定义
import type * as tableau from './tableau'

// 导出Tableau类型
export type { tableau }

// API响应类型
export interface ApiResponse<T = any> {
  status: string
  data?: T
  message?: string
  error?: string
}

// 查询请求类型
export interface QueryRequest {
  question: string
  datasource_luid: string
}

// 查询响应类型
export interface QueryResponse {
  session_id: string
  plan_id: string
  subtasks: SubTask[]
  results: QueryResult[]
  summary: AnalysisSummary
}

// 子任务类型
export interface SubTask {
  question_id: string
  question_text: string
  dims: string[]
  metrics: Metric[]
  filters: Filter[]
  stage: number
  status: 'pending' | 'running' | 'success' | 'failed'
}

// 度量类型
export interface Metric {
  field: string
  aggregation: string
}

// 筛选条件类型
export interface Filter {
  field: string
  type: string
  value: any
}

// 查询结果类型
export interface QueryResult {
  question_id: string
  data: any[]
  insights: Insight[]
}

// 洞察类型
export interface Insight {
  type: 'finding' | 'anomaly' | 'recommendation'
  content: string
}

// 分析摘要类型
export interface AnalysisSummary {
  executive_summary: string
  analysis_path: string[]
  next_suggestions: string[]
}
