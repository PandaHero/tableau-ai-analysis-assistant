/**
 * Settings Store
 * 管理用户设置状态
 * Requirements: 新增设置功能
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Language, AnalysisDepth, CustomModel } from '@/types'
import { STORAGE_KEYS, DEFAULT_CONFIG, BUILTIN_MODELS } from '@/types'

/**
 * 检测系统语言
 * 优先使用浏览器语言设置（在 Tableau Desktop 中会反映系统语言）
 */
function detectSystemLanguage(): Language {
  const browserLang = navigator.language || (navigator as { userLanguage?: string }).userLanguage || ''
  // 如果是中文（zh-CN, zh-TW, zh 等），返回 'zh'，否则返回 'en'
  return browserLang.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

export const useSettingsStore = defineStore('settings', () => {
  // 语言设置 - 默认从系统检测
  const language = ref<Language>(detectSystemLanguage())
  
  // 分析深度
  const analysisDepth = ref<AnalysisDepth>(DEFAULT_CONFIG.analysisDepth)
  
  // 选中的模型
  const selectedModel = ref<string>(DEFAULT_CONFIG.selectedModel)
  
  // 自定义模型列表
  const customModels = ref<CustomModel[]>([])
  
  // 数据源名称
  const datasourceName = ref<string | undefined>(DEFAULT_CONFIG.datasourceName)
  
  // 最大消息长度
  const maxMessageLength = ref<number>(DEFAULT_CONFIG.maxMessageLength)
  
  // 自动滚动
  const autoScroll = ref<boolean>(DEFAULT_CONFIG.autoScroll)

  // 所有可用模型（内置 + 自定义）
  const allModels = computed(() => [
    ...BUILTIN_MODELS.map(m => ({ ...m, isCustom: false })),
    ...customModels.value.map(m => ({ 
      id: `custom_${m.name}`, 
      name: m.name, 
      description: m.apiBase,
      isCustom: true 
    }))
  ])

  // 当前选中的模型信息
  const currentModel = computed(() => 
    allModels.value.find(m => m.id === selectedModel.value) || BUILTIN_MODELS[0]
  )

  /**
   * 初始化 - 从 localStorage 恢复
   */
  function initialize() {
    try {
      const saved = localStorage.getItem(STORAGE_KEYS.SETTINGS)
      if (saved) {
        const settings = JSON.parse(saved)
        if (settings.language) language.value = settings.language
        if (settings.analysisDepth) analysisDepth.value = settings.analysisDepth
        if (settings.selectedModel) selectedModel.value = settings.selectedModel
        if (settings.customModels) customModels.value = settings.customModels
        if (settings.datasourceName) datasourceName.value = settings.datasourceName
        if (settings.maxMessageLength) maxMessageLength.value = settings.maxMessageLength
        if (typeof settings.autoScroll === 'boolean') autoScroll.value = settings.autoScroll
      }
    } catch (e) {
      console.error('Failed to restore settings:', e)
    }
  }

  /**
   * 持久化到 localStorage
   */
  function persist() {
    try {
      const settings = {
        language: language.value,
        analysisDepth: analysisDepth.value,
        selectedModel: selectedModel.value,
        customModels: customModels.value,
        datasourceName: datasourceName.value,
        maxMessageLength: maxMessageLength.value,
        autoScroll: autoScroll.value
      }
      localStorage.setItem(STORAGE_KEYS.SETTINGS, JSON.stringify(settings))
    } catch (e) {
      console.error('Failed to persist settings:', e)
    }
  }

  /**
   * 设置语言
   */
  function setLanguage(lang: Language) {
    language.value = lang
    persist()
  }

  /**
   * 设置分析深度
   */
  function setAnalysisDepth(depth: AnalysisDepth) {
    analysisDepth.value = depth
    persist()
  }

  /**
   * 设置选中的模型
   */
  function setSelectedModel(modelId: string) {
    selectedModel.value = modelId
    persist()
  }

  /**
   * 设置数据源名称
   */
  function setDatasourceName(name: string | undefined) {
    datasourceName.value = name
    persist()
  }

  /**
   * 添加自定义模型
   */
  async function addCustomModel(model: CustomModel): Promise<void> {
    const newModel = {
      ...model,
      createdAt: Date.now()
    }
    customModels.value.push(newModel)
    persist()
  }

  /**
   * 删除自定义模型
   */
  async function removeCustomModel(name: string): Promise<void> {
    const index = customModels.value.findIndex(m => m.name === name)
    if (index !== -1) {
      customModels.value.splice(index, 1)
      
      // 如果删除的是当前选中的模型，切换到默认模型
      if (selectedModel.value === `custom_${name}`) {
        selectedModel.value = DEFAULT_CONFIG.selectedModel
      }
      
      persist()
    }
  }

  /**
   * 测试自定义模型连接
   */
  async function testCustomModel(model: CustomModel): Promise<boolean> {
    try {
      // TODO: 实现实际的连接测试
      // 这里需要调用后端 API 进行测试
      const response = await fetch('/api/models/custom/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(model)
      })
      return response.ok
    } catch {
      return false
    }
  }

  /**
   * 重置为默认设置
   */
  function resetToDefaults() {
    language.value = DEFAULT_CONFIG.language
    analysisDepth.value = DEFAULT_CONFIG.analysisDepth
    selectedModel.value = DEFAULT_CONFIG.selectedModel
    maxMessageLength.value = DEFAULT_CONFIG.maxMessageLength
    autoScroll.value = DEFAULT_CONFIG.autoScroll
    persist()
  }

  return {
    // 状态
    language,
    analysisDepth,
    selectedModel,
    customModels,
    datasourceName,
    maxMessageLength,
    autoScroll,
    
    // 计算属性
    allModels,
    currentModel,
    
    // 方法
    initialize,
    setLanguage,
    setAnalysisDepth,
    setSelectedModel,
    setDatasourceName,
    addCustomModel,
    removeCustomModel,
    testCustomModel,
    resetToDefaults
  }
})
