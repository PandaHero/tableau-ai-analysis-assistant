/**
 * 设置类型定义
 */

// 语言
export type Language = 'zh' | 'en'

// 分析深度
export type AnalysisDepth = 'detailed' | 'comprehensive'

// 主题
export type Theme = 'light' | 'dark' | 'system'

// 自定义模型配置
export interface CustomModel {
  name: string        // 显示名称
  apiBase: string     // API 基础地址
  apiKey?: string     // API Key（可选）
  modelId?: string    // 模型标识（可选）
  createdAt?: number  // 创建时间
}

// 内置模型
export interface BuiltinModel {
  id: string
  name: string
  description: string
}

// 内置模型列表
export const BUILTIN_MODELS: BuiltinModel[] = [
  { id: 'deepseek', name: 'DeepSeek', description: '深度求索' },
  { id: 'qwen', name: 'Qwen', description: '阿里通义千问' },
  { id: 'glm', name: 'GLM', description: '智谱 ChatGLM' },
  { id: 'kimi', name: 'Kimi', description: '月之暗面 Kimi' },
  { id: 'gpt', name: 'GPT', description: 'OpenAI GPT' },
  { id: 'claude', name: 'Claude', description: 'Anthropic Claude' },
]

// 分析深度选项
export const ANALYSIS_DEPTH_OPTIONS: { value: AnalysisDepth; label: string; description: string }[] = [
  { value: 'detailed', label: '标准', description: '标准分析，包含数据支撑和主要发现' },
  { value: 'comprehensive', label: '深入分析', description: '完整报告，包含趋势预测和行动建议' },
]

// 应用配置
export interface AppConfig {
  theme: Theme
  language: Language
  analysisDepth: AnalysisDepth
  selectedModel: string
  datasourceName?: string
  maxMessageLength: number
  autoScroll: boolean
}

// 默认配置
export const DEFAULT_CONFIG: AppConfig = {
  theme: 'light',
  language: 'zh',
  analysisDepth: 'detailed',
  selectedModel: 'deepseek',
  maxMessageLength: 2000,
  autoScroll: true
}
