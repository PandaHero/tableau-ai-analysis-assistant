/**
 * 消息类型定义
 * Requirements: 2.1, 2.2
 */

import type { Insight } from './insight'

// 基础消息类型
export interface BaseMessage {
  id: string
  timestamp: number
}

// 用户消息
export interface UserMessage extends BaseMessage {
  type: 'user'
  content: string
}

// 表格数据
export interface TableData {
  columns: ColumnDef[]
  rows: Record<string, unknown>[]
  totalCount: number
}

export interface ColumnDef {
  key: string
  label: string
  type: 'string' | 'number' | 'date'
  align?: 'left' | 'center' | 'right'
}

// 技术细节
export interface TechDetails {
  query: SemanticQuery
  executionTime: number  // 毫秒
  rowCount: number
}

export interface SemanticQuery {
  datasource_luid: string
  columns: QueryColumn[]
  filters?: QueryFilter[]
  sorts?: QuerySort[]
  limit?: number
}

export interface QueryColumn {
  field: string
  aggregation?: 'sum' | 'avg' | 'count' | 'min' | 'max'
}

export interface QueryFilter {
  field: string
  operator: string
  value: unknown
}

export interface QuerySort {
  field: string
  direction: 'asc' | 'desc'
}

// 分析轮次（多轮重规划）
export interface AnalysisRound {
  roundNumber: number
  question: string           // 本轮问题
  data?: TableData           // 查询结果
  insights: Insight[]        // 本轮发现
  reason?: string            // 思考气泡内容（为什么要继续分析）
}

// 语义解析摘要（后端 parse_result 返回）
export interface SemanticSummary {
  restated_question: string
  measures: string[]
  dimensions: string[]
  filters: string[]
}

// AI 消息
export interface AIMessage extends BaseMessage {
  type: 'ai'
  content: string              // Markdown 格式的总结
  rounds?: AnalysisRound[]     // 多轮分析过程
  data?: TableData             // 单轮时的表格数据（兼容）
  tableData?: TableData        // 来自后端 data 事件的真实查询结果
  semanticSummary?: SemanticSummary  // 语义解析摘要
  insights?: Insight[]         // 单轮时的洞察（兼容）
  techDetails?: TechDetails    // 技术细节
  suggestions?: string[]       // 推荐问题
  isStreaming?: boolean        // 是否正在流式输出
}

// 系统消息（错误、提示等）
export interface SystemMessage extends BaseMessage {
  type: 'system'
  content: string
  level: 'info' | 'warning' | 'error'
  retryable?: boolean
}

// 消息联合类型
export type Message = UserMessage | AIMessage | SystemMessage

// 处理阶段
export type ProcessingStage =
  | 'understanding'  // 理解问题
  | 'building'       // 构建查询
  | 'executing'      // 执行分析
  | 'generating'     // 生成洞察
  | 'replanning'     // 重规划
  | 'error'          // 错误状态

// 阶段标签映射
export const STAGE_LABELS: Record<ProcessingStage, string> = {
  understanding: '理解问题...',
  building: '构建查询...',
  executing: '执行分析...',
  generating: '生成洞察...',
  replanning: '深入分析...',
  error: '处理出错'
}
