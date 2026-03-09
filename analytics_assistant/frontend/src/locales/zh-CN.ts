/**
 * 中文语言包
 */
export default {
  app: {
    title: 'Tableau AI 助手',
    initializing: '正在初始化...',
    initFailed: '初始化失败',
    initTimeout: '初始化超时,请刷新页面重试',
    retry: '重试',
    preloading: '预热中...',
    windowTooSmall: '窗口过小,请调整窗口大小'
  },
  
  home: {
    welcome: '欢迎使用 Tableau AI 助手',
    subtitle: '智能数据分析,让洞察触手可及',
    exampleQuestions: '示例问题',
    examples: {
      sales: '显示各地区的销售额',
      profit: '哪个产品类别利润最高?',
      trend: '分析销售趋势',
      compare: '比较不同时间段的业绩'
    }
  },
  
  chat: {
    inputPlaceholder: '请输入您的问题...',
    send: '发送',
    sending: '发送中...',
    user: '用户',
    assistant: 'AI 助手',
    copy: '复制',
    copied: '已复制',
    justNow: '刚刚',
    minutesAgo: '{n}分钟前',
    hoursAgo: '{n}小时前',
    error: '发生错误,请重试'
  },
  
  settings: {
    title: '设置',
    close: '关闭',
    
    dataConfig: '数据配置',
    datasource: '数据源',
    datasourceAuto: '自动检测',
    datasourceSuperstore: '超市销售数据 (Superstore)',
    datasourceFinance: '财务数据 (Finance)',
    analysisDepth: '分析深度',
    analysisDepthStandard: '标准',
    analysisDepthDeep: '深入分析',
    analysisDepthHint: '💡 标准模式适合快速获取答案,深入分析会进行多轮探索',
    
    aiConfig: 'AI 配置',
    aiModel: 'AI 模型',
    
    uiConfig: '界面设置',
    language: '语言',
    languageZh: '中文',
    languageEn: 'English',
    theme: '主题',
    themeAuto: '跟随系统',
    themeLight: '浅色',
    themeDark: '深色'
  },
  
  common: {
    confirm: '确认',
    cancel: '取消',
    save: '保存',
    delete: '删除',
    edit: '编辑',
    back: '返回',
    loading: '加载中...',
    noData: '暂无数据',
    error: '错误',
    success: '成功',
    warning: '警告',
    info: '提示'
  }
}
