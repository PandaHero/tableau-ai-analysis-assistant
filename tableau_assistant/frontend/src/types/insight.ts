/**
 * 洞察类型定义
 * Requirements: 6.1, 6.2, 6.3, 6.4
 */

// 洞察类型
export type InsightType = 'discovery' | 'anomaly' | 'suggestion'

// 洞察
export interface Insight {
  id: string
  type: InsightType
  title: string
  description: string
  confidence: number  // 0-100
  priority: number    // 排序用，数值越大优先级越高
}

// 类型图标和颜色映射
export const INSIGHT_STYLES: Record<InsightType, { icon: string; color: string; label: string }> = {
  discovery: { icon: '💡', color: '#1F77B4', label: '发现' },
  anomaly: { icon: '⚠️', color: '#FF7F0E', label: '异常' },
  suggestion: { icon: '✅', color: '#2CA02C', label: '建议' }
}
