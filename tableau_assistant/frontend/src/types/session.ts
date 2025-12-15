/**
 * 会话类型定义
 * Requirements: 12.1, 12.2, 12.6
 */

import type { Message } from './message'

// 会话
export interface Session {
  id: string              // UUID v4 格式
  messages: Message[]
  createdAt: number       // 时间戳
  updatedAt: number       // 时间戳
  archived: boolean       // 是否已归档（超过24小时）
  datasourceName?: string // 关联的数据源名称
}

// 存储键
export const STORAGE_KEYS = {
  SESSIONS: 'tableau_ai_sessions',
  CURRENT_SESSION: 'tableau_ai_current_session',
  CONFIG: 'tableau_ai_config',
  SETTINGS: 'tableau_ai_settings'
} as const

// 会话归档阈值（24小时，毫秒）
export const SESSION_ARCHIVE_THRESHOLD = 24 * 60 * 60 * 1000
