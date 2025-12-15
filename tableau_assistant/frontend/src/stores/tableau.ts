/**
 * Tableau Store
 * 管理 Tableau Extension 状态
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  isInTableauEnvironment,
  initializeTableauExtension,
  getAllDataSources,
  getDashboardName
} from '@/utils/tableau'

export interface DataSourceInfo {
  id: string
  name: string
}

export const useTableauStore = defineStore('tableau', () => {
  // 状态
  const isInitialized = ref(false)
  const isInitializing = ref(false)
  const initError = ref<string | null>(null)
  const dashboardName = ref<string>('')
  const dataSources = ref<DataSourceInfo[]>([])
  const selectedDataSourceId = ref<string | null>(null)
  const isPreloading = ref(false)

  // 计算属性
  const selectedDataSource = computed(() => {
    if (!selectedDataSourceId.value) return null
    return dataSources.value.find(ds => ds.id === selectedDataSourceId.value) ?? null
  })

  const isInTableau = computed(() => isInTableauEnvironment())

  /**
   * 初始化
   */
  async function initialize(): Promise<boolean> {
    if (isInitialized.value || isInitializing.value) {
      return isInitialized.value
    }

    isInitializing.value = true
    initError.value = null

    try {
      // 初始化 Tableau Extension
      await initializeTableauExtension()

      // 获取仪表板名称
      dashboardName.value = getDashboardName()

      // 获取数据源列表
      const sources = await getAllDataSources()
      dataSources.value = sources

      // 默认选择第一个
      if (sources.length > 0) {
        selectedDataSourceId.value = sources[0].id
      }

      isInitialized.value = true
      console.log('Tableau store initialized:', {
        dashboard: dashboardName.value,
        dataSources: sources.length
      })

      return true
    } catch (error) {
      console.error('Failed to initialize:', error)
      initError.value = error instanceof Error ? error.message : String(error)
      return false
    } finally {
      isInitializing.value = false
    }
  }

  /**
   * 选择数据源
   */
  function selectDataSource(id: string): void {
    if (dataSources.value.some(ds => ds.id === id)) {
      selectedDataSourceId.value = id
    }
  }

  /**
   * 重置状态
   */
  function reset(): void {
    isInitialized.value = false
    isInitializing.value = false
    initError.value = null
    dashboardName.value = ''
    dataSources.value = []
    selectedDataSourceId.value = null
  }

  return {
    // 状态
    isInitialized,
    isInitializing,
    initError,
    dashboardName,
    dataSources,
    selectedDataSourceId,
    isPreloading,
    // 计算属性
    selectedDataSource,
    isInTableau,
    // 方法
    initialize,
    selectDataSource,
    reset
  }
})
