// Boost Prompt 相关类型定义

export interface BoostPrompt {
  id: string
  title: string
  content: string
  category: BoostPromptCategory
  isBuiltIn: boolean
}

export enum BoostPromptCategory {
  DataExploration = 'data_exploration',
  TrendAnalysis = 'trend_analysis',
  AnomalyDetection = 'anomaly_detection',
  Visualization = 'visualization',
  Custom = 'custom'
}

export const BUILT_IN_PROMPTS: BoostPrompt[] = [
  {
    id: 'overview',
    title: '数据概览',
    content: '请给我一个数据集的整体概览，包括主要维度和度量。',
    category: BoostPromptCategory.DataExploration,
    isBuiltIn: true
  },
  {
    id: 'trend',
    title: '趋势分析',
    content: '分析最近的趋势变化，找出关键的增长或下降模式。',
    category: BoostPromptCategory.TrendAnalysis,
    isBuiltIn: true
  },
  {
    id: 'anomaly',
    title: '异常检测',
    content: '检测数据中的异常值或异常模式。',
    category: BoostPromptCategory.AnomalyDetection,
    isBuiltIn: true
  },
  {
    id: 'viz_suggest',
    title: '可视化建议',
    content: '根据当前数据，建议最合适的可视化类型。',
    category: BoostPromptCategory.Visualization,
    isBuiltIn: true
  },
  {
    id: 'top_metrics',
    title: '关键指标',
    content: '显示最重要的业务指标和它们的当前状态。',
    category: BoostPromptCategory.DataExploration,
    isBuiltIn: true
  }
]
