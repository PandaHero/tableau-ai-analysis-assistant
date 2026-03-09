export type Language = 'zh' | 'en'

export type AnalysisDepth = 'detailed' | 'comprehensive'

export type Theme = 'light' | 'dark' | 'auto'

export interface CustomModel {
  name: string
  apiBase: string
  apiKey?: string
  modelId?: string
  createdAt?: number
}

export interface BuiltinModel {
  id: string
  name: string
  description: string
}

export const BUILTIN_MODELS: BuiltinModel[] = [
  { id: 'deepseek', name: 'DeepSeek', description: '深度求索' },
  { id: 'qwen', name: 'Qwen', description: '阿里通义千问' },
  { id: 'glm', name: 'GLM', description: '智谱 ChatGLM' },
  { id: 'kimi', name: 'Kimi', description: '月之暗面 Kimi' },
  { id: 'gpt', name: 'GPT', description: 'OpenAI GPT' },
  { id: 'claude', name: 'Claude', description: 'Anthropic Claude' },
]

export const ANALYSIS_DEPTH_OPTIONS: {
  value: AnalysisDepth
  label: string
  description: string
}[] = [
  {
    value: 'detailed',
    label: '标准',
    description: '标准分析，包含数据支撑和主要发现',
  },
  {
    value: 'comprehensive',
    label: '深入分析',
    description: '完整报告，包含趋势预测和行动建议',
  },
]

export interface AppConfig {
  theme: Theme
  language: Language
  analysisDepth: AnalysisDepth
  selectedModel: string
  datasourceName?: string
  maxMessageLength: number
  autoScroll: boolean
}

export const DEFAULT_CONFIG: AppConfig = {
  theme: 'auto',
  language: 'zh',
  analysisDepth: 'detailed',
  selectedModel: 'deepseek',
  maxMessageLength: 2000,
  autoScroll: true,
}
