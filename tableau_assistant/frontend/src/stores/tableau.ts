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
  getDashboardName,
  getTableauEnvironment,
  getTableauDomainAsync,
  getDataSourceConnectionInfo,
  type DataSourceConnectionInfo
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
  
  // Tableau 环境信息（支持多环境）
  const tableauDomain = ref<string | undefined>(undefined)
  const tableauSite = ref<string | undefined>(undefined)
  // Tableau 运行环境上下文
  type TableauContext = 'desktop' | 'server' | 'cloud' | 'public-desktop' | 'public-web'
  const tableauContext = ref<TableauContext | undefined>(undefined)
  // 数据源连接信息
  const datasourceConnectionInfo = ref<DataSourceConnectionInfo | undefined>(undefined)

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
    console.log('=== Tableau Store Initialize Start ===')
    console.log('isInTableau:', isInTableauEnvironment())
    
    if (isInitialized.value || isInitializing.value) {
      console.log('Already initialized or initializing, skipping')
      return isInitialized.value
    }

    isInitializing.value = true
    initError.value = null

    try {
      // 初始化 Tableau Extension
      console.log('Calling initializeTableauExtension...')
      await initializeTableauExtension()
      console.log('initializeTableauExtension completed')

      // 获取仪表板名称
      dashboardName.value = getDashboardName()
      console.log('Dashboard name:', dashboardName.value)

      // 获取数据源列表
      const sources = await getAllDataSources()
      dataSources.value = sources
      console.log('Data sources:', sources)

      // 默认选择第一个
      if (sources.length > 0) {
        selectedDataSourceId.value = sources[0].id
      }
      
      // 获取 Tableau 环境信息（支持多环境）
      console.log('Getting Tableau environment...')
      const env = getTableauEnvironment()
      console.log('Tableau environment result:', env)
      
      // 保存 context 信息
      if (env) {
        tableauContext.value = env.context as TableauContext
        console.log('Set tableauContext to:', tableauContext.value)
      }
      
      // 获取数据源连接信息
      console.log('Getting datasource connection info...')
      const connInfo = await getDataSourceConnectionInfo()
      datasourceConnectionInfo.value = connInfo
      console.log('Datasource connection info:', connInfo)
      
      // 异步获取 Tableau 域名
      console.log('Getting Tableau domain...')
      const domain = await getTableauDomainAsync()
      tableauDomain.value = domain
      console.log('Set tableauDomain to:', tableauDomain.value)

      isInitialized.value = true
      console.log('=== Tableau Store Initialize Complete ===', {
        dashboard: dashboardName.value,
        dataSources: sources.length,
        tableauDomain: tableauDomain.value
      })

      return true
    } catch (error) {
      console.error('=== Tableau Store Initialize FAILED ===', error)
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
    tableauDomain,
    tableauSite,
    tableauContext,
    datasourceConnectionInfo,
    // 计算属性
    selectedDataSource,
    isInTableau,
    // 方法
    initialize,
    selectDataSource,
    reset
  }
})
