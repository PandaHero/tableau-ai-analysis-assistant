/**
 * Settings Store
 * 管理用户设置状态
 * Requirements: 新增设置功能
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Language, AnalysisDepth, CustomModel } from '@/types'
import { STORAGE_KEYS, DEFAULT_CONFIG, BUILTIN_MODELS } from '@/types'
import { 
  isInTableauEnvironment, 
  setSetting, 
  saveSettings as saveTableauSettings,
  getAllSettings 
} from '@/utils/tableau'

// Tableau 设置键名
const TABLEAU_SETTINGS_KEYS = {
  LANGUAGE: 'ai_assistant_language',
  ANALYSIS_DEPTH: 'ai_assistant_analysis_depth',
  SELECTED_MODEL: 'ai_assistant_selected_model',
  DATASOURCE_NAME: 'ai_assistant_datasource_name',
  CUSTOM_MODELS: 'ai_assistant_custom_models'
}

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
   * 初始化 - 从 Tableau 设置或 localStorage 恢复
   * 优先级：Tableau 设置 > localStorage
   * 自定义模型从后端 API 加载
   */
  async function initialize() {
    try {
      // 首先尝试从 Tableau 设置恢复
      if (isInTableauEnvironment()) {
        const tableauSettings = getAllSettings()
        console.log('Restoring settings from Tableau:', tableauSettings)
        
        if (tableauSettings[TABLEAU_SETTINGS_KEYS.LANGUAGE]) {
          language.value = tableauSettings[TABLEAU_SETTINGS_KEYS.LANGUAGE] as Language
        }
        if (tableauSettings[TABLEAU_SETTINGS_KEYS.ANALYSIS_DEPTH]) {
          analysisDepth.value = tableauSettings[TABLEAU_SETTINGS_KEYS.ANALYSIS_DEPTH] as AnalysisDepth
        }
        if (tableauSettings[TABLEAU_SETTINGS_KEYS.SELECTED_MODEL]) {
          selectedModel.value = tableauSettings[TABLEAU_SETTINGS_KEYS.SELECTED_MODEL]
        }
        if (tableauSettings[TABLEAU_SETTINGS_KEYS.DATASOURCE_NAME]) {
          datasourceName.value = tableauSettings[TABLEAU_SETTINGS_KEYS.DATASOURCE_NAME]
        }
      } else {
        // 回退到 localStorage
        const saved = localStorage.getItem(STORAGE_KEYS.SETTINGS)
        if (saved) {
          const settings = JSON.parse(saved)
          if (settings.language) language.value = settings.language
          if (settings.analysisDepth) analysisDepth.value = settings.analysisDepth
          if (settings.selectedModel) selectedModel.value = settings.selectedModel
          if (settings.datasourceName) datasourceName.value = settings.datasourceName
          if (settings.maxMessageLength) maxMessageLength.value = settings.maxMessageLength
          if (typeof settings.autoScroll === 'boolean') autoScroll.value = settings.autoScroll
        }
      }
      
      // 从后端加载自定义模型（统一数据源）
      await loadCustomModels()
      
    } catch (e) {
      console.error('Failed to restore settings:', e)
    }
  }

  /**
   * 持久化到 Tableau 设置和 localStorage
   */
  async function persist() {
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
      
      // 保存到 localStorage
      localStorage.setItem(STORAGE_KEYS.SETTINGS, JSON.stringify(settings))
      
      // 如果在 Tableau 环境中，也保存到 Tableau 设置
      if (isInTableauEnvironment()) {
        setSetting(TABLEAU_SETTINGS_KEYS.LANGUAGE, language.value)
        setSetting(TABLEAU_SETTINGS_KEYS.ANALYSIS_DEPTH, analysisDepth.value)
        setSetting(TABLEAU_SETTINGS_KEYS.SELECTED_MODEL, selectedModel.value)
        if (datasourceName.value) {
          setSetting(TABLEAU_SETTINGS_KEYS.DATASOURCE_NAME, datasourceName.value)
        }
        setSetting(TABLEAU_SETTINGS_KEYS.CUSTOM_MODELS, JSON.stringify(customModels.value))
        
        // 异步保存到 Tableau 服务器
        await saveTableauSettings()
        console.log('Settings saved to Tableau')
      }
    } catch (e) {
      console.error('Failed to persist settings:', e)
    }
  }

  /**
   * 设置语言
   */
  async function setLanguage(lang: Language) {
    language.value = lang
    await persist()
  }

  /**
   * 设置分析深度
   */
  async function setAnalysisDepth(depth: AnalysisDepth) {
    analysisDepth.value = depth
    await persist()
  }

  /**
   * 设置选中的模型
   */
  async function setSelectedModel(modelId: string) {
    selectedModel.value = modelId
    await persist()
  }

  /**
   * 设置数据源名称
   */
  async function setDatasourceName(name: string | undefined) {
    datasourceName.value = name
    await persist()
  }

  /**
   * 从后端加载自定义模型列表
   */
  async function loadCustomModels(): Promise<void> {
    try {
      const response = await fetch('/api/models/custom')
      if (response.ok) {
        const models = await response.json()
        customModels.value = models.map((m: { name: string; apiBase: string; modelId: string; createdAt: number }) => ({
          name: m.name,
          apiBase: m.apiBase,
          modelId: m.modelId,
          apiKey: '', // 后端不返回 apiKey
          createdAt: m.createdAt
        }))
        console.log('Loaded custom models from backend:', customModels.value.length)
      }
    } catch (e) {
      console.error('Failed to load custom models:', e)
    }
  }

  /**
   * 添加自定义模型（通过后端 API）
   */
  async function addCustomModel(model: CustomModel): Promise<void> {
    try {
      const response = await fetch('/api/models/custom', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(model)
      })
      
      if (!response.ok) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to add model')
      }
      
      const created = await response.json()
      customModels.value.push({
        name: created.name,
        apiBase: created.apiBase,
        modelId: created.modelId,
        apiKey: model.apiKey, // 保留本地的 apiKey
        createdAt: created.createdAt
      })
      
      await persist()
    } catch (e) {
      console.error('Failed to add custom model:', e)
      throw e
    }
  }

  /**
   * 删除自定义模型（通过后端 API）
   */
  async function removeCustomModel(name: string): Promise<void> {
    try {
      const response = await fetch(`/api/models/custom/${encodeURIComponent(name)}`, {
        method: 'DELETE'
      })
      
      if (!response.ok && response.status !== 404) {
        const error = await response.json()
        throw new Error(error.detail || 'Failed to delete model')
      }
      
      // 从本地列表移除
      const index = customModels.value.findIndex(m => m.name === name)
      if (index !== -1) {
        customModels.value.splice(index, 1)
      }
      
      // 如果删除的是当前选中的模型，切换到默认模型
      if (selectedModel.value === `custom_${name}`) {
        selectedModel.value = DEFAULT_CONFIG.selectedModel
      }
      
      await persist()
    } catch (e) {
      console.error('Failed to remove custom model:', e)
      throw e
    }
  }

  /**
   * 测试自定义模型连接（通过后端 API）
   */
  async function testCustomModel(model: CustomModel): Promise<{ success: boolean; message: string; latency_ms?: number }> {
    try {
      const response = await fetch('/api/models/custom/test', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          apiBase: model.apiBase,
          apiKey: model.apiKey,
          modelId: model.modelId
        })
      })
      
      const result = await response.json()
      return result
    } catch (e) {
      return {
        success: false,
        message: `连接失败: ${e instanceof Error ? e.message : '未知错误'}`
      }
    }
  }

  /**
   * 重置为默认设置
   */
  async function resetToDefaults() {
    language.value = DEFAULT_CONFIG.language
    analysisDepth.value = DEFAULT_CONFIG.analysisDepth
    selectedModel.value = DEFAULT_CONFIG.selectedModel
    maxMessageLength.value = DEFAULT_CONFIG.maxMessageLength
    autoScroll.value = DEFAULT_CONFIG.autoScroll
    await persist()
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
    loadCustomModels,
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
