/**
 * 国际化工具
 * 支持中英文切换
 */
import { computed } from 'vue'
import { useSettingsStore } from '@/stores/settings'
import type { Language } from '@/types'

// 翻译文本定义
const translations: Record<Language, Record<string, string>> = {
  zh: {
    // 通用
    'app.title': 'Tableau AI 分析助手',
    'app.initializing': '正在初始化 Tableau Extension...',
    'app.initFailed': '初始化失败',
    'app.initTimeout': '连接超时，请点击重试',
    'app.retry': '重试',
    'app.preloading': '正在预热数据模型...',
    'app.windowTooSmall': '窗口过小，请调整窗口大小',
    
    // 头部
    'header.back': '返回',
    'header.settings': '设置',
    
    // 欢迎页
    'welcome.title': '您好！我是您的数据分析助手',
    'welcome.subtitle': '我可以帮您分析 Tableau 数据，发现洞察，回答问题',
    'welcome.examples.title': '试试这些问题：',
    'welcome.example.1': '各产品线的销售额是多少？',
    'welcome.example.2': '哪个地区的利润率最高？',
    'welcome.example.3': '最近一个月的销售趋势如何？',
    
    // 输入区
    'input.placeholder': '请输入您的数据分析问题...',
    'input.placeholder.processing': 'AI 正在思考...',
    'input.send': '发送',
    'input.charCount': '字符',
    
    // 思考指示器
    'thinking.understanding': '理解问题...',
    'thinking.building': '构建查询...',
    'thinking.executing': '执行分析...',
    'thinking.generating': '生成洞察...',
    'thinking.replanning': '深入分析...',
    'thinking.error': '处理出错',
    
    // 设置面板
    'settings.title': '设置',
    'settings.datasource': '数据源',
    'settings.datasource.placeholder': '选择数据源',
    'settings.language': '语言',
    'settings.language.zh': '中文',
    'settings.language.en': 'English',
    'settings.analysisDepth': '分析深度',
    'settings.analysisDepth.detailed': '标准',
    'settings.analysisDepth.comprehensive': '深入分析',
    'settings.theme': '主题',
    'settings.theme.light': '浅色',
    'settings.theme.dark': '深色',
    'settings.theme.system': '跟随系统',
    'settings.model': 'AI 模型',
    'settings.model.builtin': '内置模型',
    'settings.model.custom': '自定义模型',
    'settings.model.add': '添加自定义模型',
    
    // 消息
    'message.justNow': '刚刚',
    'message.minutesAgo': '分钟前',
    'message.hoursAgo': '小时前',
    'message.daysAgo': '天前',
    
    // 数据表格
    'table.empty': '暂无数据',
    'table.total': '共',
    'table.items': '条',
    'table.export': '导出 CSV',
    
    // 洞察卡片
    'insight.finding': '发现',
    'insight.anomaly': '异常',
    'insight.suggestion': '建议',
    
    // 技术细节
    'techDetails.title': '技术细节',
    'techDetails.query': 'VizQL 查询',
    'techDetails.execTime': '执行时间',
    'techDetails.rows': '返回行数',
    'techDetails.copy': '复制',
    'techDetails.copied': '已复制',
    
    // 推荐问题
    'suggestions.title': '继续探索',
    'suggestions.more': '更多',
    
    // 错误
    'error.network': '网络连接失败，请检查网络设置',
    'error.timeout': '请求超时，请重试',
    'error.server': '服务器错误，请稍后重试',
    'error.unknown': '发生未知错误',
    'error.retry': '重试',
  },
  en: {
    // Common
    'app.title': 'Tableau AI Analysis Assistant',
    'app.initializing': 'Initializing Tableau Extension...',
    'app.initFailed': 'Initialization failed',
    'app.initTimeout': 'Connection timed out, please retry',
    'app.retry': 'Retry',
    'app.preloading': 'Warming up data model...',
    'app.windowTooSmall': 'Window too small, please resize',
    
    // Header
    'header.back': 'Back',
    'header.settings': 'Settings',
    
    // Welcome page
    'welcome.title': 'Hello! I\'m your data analysis assistant',
    'welcome.subtitle': 'I can help you analyze Tableau data, discover insights, and answer questions',
    'welcome.examples.title': 'Try these questions:',
    'welcome.example.1': 'What are the sales by product line?',
    'welcome.example.2': 'Which region has the highest profit margin?',
    'welcome.example.3': 'What\'s the sales trend for the last month?',
    
    // Input area
    'input.placeholder': 'Enter your data analysis question...',
    'input.placeholder.processing': 'AI is thinking...',
    'input.send': 'Send',
    'input.charCount': 'chars',
    
    // Thinking indicator
    'thinking.understanding': 'Understanding question...',
    'thinking.building': 'Building query...',
    'thinking.executing': 'Executing analysis...',
    'thinking.generating': 'Generating insights...',
    'thinking.replanning': 'Deep analysis...',
    'thinking.error': 'Error occurred',
    
    // Settings panel
    'settings.title': 'Settings',
    'settings.datasource': 'Data Source',
    'settings.datasource.placeholder': 'Select data source',
    'settings.language': 'Language',
    'settings.language.zh': '中文',
    'settings.language.en': 'English',
    'settings.analysisDepth': 'Analysis Depth',
    'settings.analysisDepth.detailed': 'Standard',
    'settings.analysisDepth.comprehensive': 'Comprehensive',
    'settings.theme': 'Theme',
    'settings.theme.light': 'Light',
    'settings.theme.dark': 'Dark',
    'settings.theme.system': 'System',
    'settings.model': 'AI Model',
    'settings.model.builtin': 'Built-in Models',
    'settings.model.custom': 'Custom Models',
    'settings.model.add': 'Add Custom Model',
    
    // Messages
    'message.justNow': 'Just now',
    'message.minutesAgo': 'min ago',
    'message.hoursAgo': 'hr ago',
    'message.daysAgo': 'd ago',
    
    // Data table
    'table.empty': 'No data',
    'table.total': 'Total',
    'table.items': 'items',
    'table.export': 'Export CSV',
    
    // Insight cards
    'insight.finding': 'Finding',
    'insight.anomaly': 'Anomaly',
    'insight.suggestion': 'Suggestion',
    
    // Tech details
    'techDetails.title': 'Technical Details',
    'techDetails.query': 'VizQL Query',
    'techDetails.execTime': 'Execution Time',
    'techDetails.rows': 'Rows Returned',
    'techDetails.copy': 'Copy',
    'techDetails.copied': 'Copied',
    
    // Suggested questions
    'suggestions.title': 'Continue Exploring',
    'suggestions.more': 'More',
    
    // Errors
    'error.network': 'Network connection failed, please check your network',
    'error.timeout': 'Request timeout, please retry',
    'error.server': 'Server error, please try again later',
    'error.unknown': 'An unknown error occurred',
    'error.retry': 'Retry',
  }
}

/**
 * 获取翻译文本
 */
export function t(key: string, lang?: Language): string {
  const settingsStore = useSettingsStore()
  const currentLang = lang || settingsStore.language
  return translations[currentLang]?.[key] || translations['en'][key] || key
}

/**
 * 创建响应式翻译函数
 */
export function useI18n() {
  const settingsStore = useSettingsStore()
  
  const currentLanguage = computed(() => settingsStore.language)
  
  function translate(key: string): string {
    return translations[currentLanguage.value]?.[key] || translations['en'][key] || key
  }
  
  return {
    t: translate,
    language: currentLanguage,
  }
}
