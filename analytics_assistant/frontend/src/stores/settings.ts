import { computed, ref } from 'vue'
import { defineStore } from 'pinia'

import { settingsApi } from '@/api/settings'
import { BUILTIN_MODELS, DEFAULT_CONFIG, STORAGE_KEYS } from '@/types'
import type { AnalysisDepth, CustomModel, Language } from '@/types'

import { useUiStore } from './ui'
import type { Theme as UiTheme } from './ui'

type ApiTheme = 'light' | 'dark' | 'system'

interface PersistedSettings {
  selectedModel?: string
  customModels?: CustomModel[]
  datasourceName?: string
  maxMessageLength?: number
  autoScroll?: boolean
}

function detectSystemLanguage(): Language {
  const browserLanguage =
    navigator.language || (navigator as { userLanguage?: string }).userLanguage || ''

  return browserLanguage.toLowerCase().startsWith('zh') ? 'zh' : 'en'
}

function mapApiThemeToUiTheme(theme: ApiTheme): UiTheme {
  return theme === 'system' ? 'auto' : theme
}

function mapUiThemeToApiTheme(theme: UiTheme): ApiTheme {
  return theme === 'auto' ? 'system' : theme
}

export const useSettingsStore = defineStore('settings', () => {
  const language = ref<Language>(detectSystemLanguage())
  const analysisDepth = ref<AnalysisDepth>(DEFAULT_CONFIG.analysisDepth)
  const selectedModel = ref<string>(DEFAULT_CONFIG.selectedModel)
  const customModels = ref<CustomModel[]>([])
  const datasourceName = ref<string | undefined>(DEFAULT_CONFIG.datasourceName)
  const maxMessageLength = ref<number>(DEFAULT_CONFIG.maxMessageLength)
  const autoScroll = ref<boolean>(DEFAULT_CONFIG.autoScroll)
  const canTestCustomModel = false
  const isInitialized = ref(false)
  const isLoading = ref(false)

  const allModels = computed(() => [
    ...BUILTIN_MODELS.map((model) => ({ ...model, isCustom: false })),
    ...customModels.value.map((model) => ({
      id: `custom_${model.name}`,
      name: model.name,
      description: model.apiBase,
      isCustom: true,
    })),
  ])

  const currentModel = computed(
    () => allModels.value.find((model) => model.id === selectedModel.value) || BUILTIN_MODELS[0],
  )

  function persistLocalSettings(): void {
    const settings: PersistedSettings = {
      selectedModel: selectedModel.value,
      customModels: customModels.value,
      datasourceName: datasourceName.value,
      maxMessageLength: maxMessageLength.value,
      autoScroll: autoScroll.value,
    }

    localStorage.setItem(STORAGE_KEYS.SETTINGS, JSON.stringify(settings))
  }

  function restoreLocalSettings(): void {
    const savedSettings = localStorage.getItem(STORAGE_KEYS.SETTINGS)
    if (!savedSettings) {
      return
    }

    const parsedSettings = JSON.parse(savedSettings) as PersistedSettings

    if (parsedSettings.selectedModel) {
      selectedModel.value = parsedSettings.selectedModel
    }

    if (parsedSettings.customModels) {
      customModels.value = parsedSettings.customModels
    }

    if (parsedSettings.datasourceName) {
      datasourceName.value = parsedSettings.datasourceName
    }

    if (typeof parsedSettings.maxMessageLength === 'number') {
      maxMessageLength.value = parsedSettings.maxMessageLength
    }

    if (typeof parsedSettings.autoScroll === 'boolean') {
      autoScroll.value = parsedSettings.autoScroll
    }
  }

  function applyRemoteSettings(settings: {
    language: Language
    analysis_depth: AnalysisDepth
    theme: ApiTheme
  }): void {
    language.value = settings.language
    analysisDepth.value = settings.analysis_depth
    useUiStore().setTheme(mapApiThemeToUiTheme(settings.theme))
  }

  async function initialize(): Promise<void> {
    if (isInitialized.value || isLoading.value) {
      return
    }

    restoreLocalSettings()
    isLoading.value = true

    try {
      const remoteSettings = await settingsApi.getSettings()
      applyRemoteSettings(remoteSettings)
    } catch (error) {
      console.error('Failed to load remote settings:', error)
    } finally {
      isLoading.value = false
      isInitialized.value = true
      persistLocalSettings()
    }
  }

  async function updateRemoteSettings(payload: {
    language?: Language
    analysis_depth?: AnalysisDepth
    theme?: ApiTheme
  }): Promise<void> {
    try {
      const updatedSettings = await settingsApi.updateSettings(payload)
      applyRemoteSettings(updatedSettings)
    } catch (error) {
      console.error('Failed to update remote settings:', error)
    }
  }

  async function setLanguage(nextLanguage: Language): Promise<void> {
    language.value = nextLanguage
    await updateRemoteSettings({ language: nextLanguage })
  }

  async function setAnalysisDepth(nextDepth: AnalysisDepth): Promise<void> {
    analysisDepth.value = nextDepth
    await updateRemoteSettings({ analysis_depth: nextDepth })
  }

  function setSelectedModel(modelId: string): void {
    selectedModel.value = modelId
    persistLocalSettings()
  }

  function setDatasourceName(name: string | undefined): void {
    datasourceName.value = name
    persistLocalSettings()
  }

  async function setThemePreference(theme: UiTheme): Promise<void> {
    useUiStore().setTheme(theme)
    await updateRemoteSettings({ theme: mapUiThemeToApiTheme(theme) })
  }

  async function addCustomModel(model: CustomModel): Promise<void> {
    customModels.value.push({
      ...model,
      createdAt: Date.now(),
    })
    persistLocalSettings()
  }

  async function removeCustomModel(name: string): Promise<void> {
    const modelIndex = customModels.value.findIndex((model) => model.name === name)
    if (modelIndex === -1) {
      return
    }

    customModels.value.splice(modelIndex, 1)

    if (selectedModel.value === `custom_${name}`) {
      selectedModel.value = DEFAULT_CONFIG.selectedModel
    }

    persistLocalSettings()
  }

  async function testCustomModel(model: CustomModel): Promise<boolean> {
    void model
    throw new Error('当前后端未提供自定义模型连接测试接口')
  }

  async function resetToDefaults(): Promise<void> {
    language.value = DEFAULT_CONFIG.language
    analysisDepth.value = DEFAULT_CONFIG.analysisDepth
    selectedModel.value = DEFAULT_CONFIG.selectedModel
    datasourceName.value = DEFAULT_CONFIG.datasourceName
    maxMessageLength.value = DEFAULT_CONFIG.maxMessageLength
    autoScroll.value = DEFAULT_CONFIG.autoScroll
    useUiStore().setTheme(DEFAULT_CONFIG.theme)
    persistLocalSettings()

    await updateRemoteSettings({
      language: DEFAULT_CONFIG.language,
      analysis_depth: DEFAULT_CONFIG.analysisDepth,
      theme: mapUiThemeToApiTheme(DEFAULT_CONFIG.theme),
    })
  }

  return {
    language,
    analysisDepth,
    selectedModel,
    customModels,
    datasourceName,
    maxMessageLength,
    autoScroll,
    canTestCustomModel,
    isInitialized,
    isLoading,
    allModels,
    currentModel,
    initialize,
    setLanguage,
    setAnalysisDepth,
    setSelectedModel,
    setDatasourceName,
    setThemePreference,
    addCustomModel,
    removeCustomModel,
    testCustomModel,
    resetToDefaults,
  }
})
