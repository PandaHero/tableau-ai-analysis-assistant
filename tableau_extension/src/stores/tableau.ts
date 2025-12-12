/**
 * Tableau Extension Store
 * 
 * 管理 Tableau Extension 状态和维度层级预热
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import { 
  initializeTableauExtension, 
  getAllDataSources, 
  isInTableauEnvironment 
} from '@/utils/tableau'
import { 
  startDimensionHierarchyPreload, 
  getPreloadStatus,
  type PreloadResponse,
  type PreloadStatusResponse 
} from '@/api/client'

export type PreloadStatus = 'idle' | 'loading' | 'ready' | 'failed'

export interface DataSourceInfo {
  id: string
  name: string
  preloadStatus: PreloadStatus
  preloadTaskId?: string
  preloadError?: string
}

export const useTableauStore = defineStore('tableau', () => {
  // ═══════════════════════════════════════════════════════════════════════════
  // 状态
  // ═══════════════════════════════════════════════════════════════════════════
  
  const isInitialized = ref(false)
  const isInitializing = ref(false)
  const initError = ref<string | null>(null)
  const dataSources = ref<DataSourceInfo[]>([])
  const selectedDataSourceId = ref<string | null>(null)
  
  // ═══════════════════════════════════════════════════════════════════════════
  // 计算属性
  // ═══════════════════════════════════════════════════════════════════════════
  
  const selectedDataSource = computed(() => {
    if (!selectedDataSourceId.value) return null
    return dataSources.value.find(ds => ds.id === selectedDataSourceId.value) || null
  })
  
  const isPreloading = computed(() => {
    return dataSources.value.some(ds => ds.preloadStatus === 'loading')
  })
  
  const allPreloaded = computed(() => {
    return dataSources.value.length > 0 && 
           dataSources.value.every(ds => ds.preloadStatus === 'ready')
  })
  
  // ═══════════════════════════════════════════════════════════════════════════
  // 方法
  // ═══════════════════════════════════════════════════════════════════════════
  
  /**
   * 初始化 Tableau Extension 并触发预热
   */
  async function initialize(): Promise<boolean> {
    if (isInitialized.value || isInitializing.value) {
      return isInitialized.value
    }
    
    isInitializing.value = true
    initError.value = null
    
    try {
      // 1. 检查是否在 Tableau 环境中
      if (!isInTableauEnvironment()) {
        console.warn('Not in Tableau environment, skipping initialization')
        // 开发模式下使用模拟数据
        if (import.meta.env.DEV) {
          dataSources.value = [{
            id: 'mock-datasource-luid',
            name: 'Mock DataSource (Dev)',
            preloadStatus: 'idle'
          }]
          selectedDataSourceId.value = 'mock-datasource-luid'
        }
        isInitialized.value = true
        isInitializing.value = false
        return true
      }
      
      // 2. 初始化 Tableau Extension
      await initializeTableauExtension()
      console.log('Tableau Extension initialized')
      
      // 3. 获取所有数据源
      const tableauDataSources = await getAllDataSources()
      dataSources.value = tableauDataSources.map(ds => ({
        id: ds.id,
        name: ds.name,
        preloadStatus: 'idle' as PreloadStatus
      }))
      
      console.log(`Found ${dataSources.value.length} data sources`)
      
      // 4. 默认选择第一个数据源
      if (dataSources.value.length > 0) {
        selectedDataSourceId.value = dataSources.value[0].id
      }
      
      // 5. 触发所有数据源的预热（后台执行）
      triggerPreloadAll()
      
      isInitialized.value = true
      return true
      
    } catch (error) {
      console.error('Failed to initialize Tableau Extension:', error)
      initError.value = error instanceof Error ? error.message : String(error)
      return false
      
    } finally {
      isInitializing.value = false
    }
  }
  
  /**
   * 触发所有数据源的预热
   */
  function triggerPreloadAll(): void {
    for (const ds of dataSources.value) {
      triggerPreload(ds.id)
    }
  }
  
  /**
   * 触发单个数据源的预热
   */
  async function triggerPreload(datasourceLuid: string, force: boolean = false): Promise<void> {
    const ds = dataSources.value.find(d => d.id === datasourceLuid)
    if (!ds) {
      console.warn(`DataSource not found: ${datasourceLuid}`)
      return
    }
    
    // 如果已经在加载或已就绪，跳过（除非强制刷新）
    if (!force && (ds.preloadStatus === 'loading' || ds.preloadStatus === 'ready')) {
      return
    }
    
    ds.preloadStatus = 'loading'
    ds.preloadError = undefined
    
    try {
      const response = await startDimensionHierarchyPreload(datasourceLuid, force)
      
      if (response.status === 'ready') {
        ds.preloadStatus = 'ready'
        console.log(`Preload ready for ${ds.name}`)
        
      } else if (response.status === 'loading' && response.task_id) {
        ds.preloadTaskId = response.task_id
        // 开始轮询状态
        pollPreloadStatus(datasourceLuid, response.task_id)
        
      } else if (response.status === 'failed') {
        ds.preloadStatus = 'failed'
        ds.preloadError = response.message || 'Preload failed'
        console.error(`Preload failed for ${ds.name}:`, response.message)
      }
      
    } catch (error) {
      ds.preloadStatus = 'failed'
      ds.preloadError = error instanceof Error ? error.message : String(error)
      console.error(`Preload error for ${ds.name}:`, error)
    }
  }
  
  /**
   * 轮询预热状态
   */
  async function pollPreloadStatus(datasourceLuid: string, taskId: string): Promise<void> {
    const ds = dataSources.value.find(d => d.id === datasourceLuid)
    if (!ds) return
    
    const maxAttempts = 120  // 最多轮询 2 分钟
    const pollInterval = 1000  // 1 秒
    
    for (let attempt = 0; attempt < maxAttempts; attempt++) {
      try {
        const status = await getPreloadStatus(taskId)
        
        if (status.status === 'ready') {
          ds.preloadStatus = 'ready'
          console.log(`Preload completed for ${ds.name}`)
          return
          
        } else if (status.status === 'failed') {
          ds.preloadStatus = 'failed'
          ds.preloadError = status.error || 'Preload failed'
          console.error(`Preload failed for ${ds.name}:`, status.error)
          return
        }
        
        // 继续等待
        await new Promise(resolve => setTimeout(resolve, pollInterval))
        
      } catch (error) {
        console.warn(`Poll error for ${ds.name}:`, error)
        // 继续尝试
        await new Promise(resolve => setTimeout(resolve, pollInterval))
      }
    }
    
    // 超时
    ds.preloadStatus = 'failed'
    ds.preloadError = 'Preload timeout'
    console.error(`Preload timeout for ${ds.name}`)
  }
  
  /**
   * 选择数据源
   */
  function selectDataSource(datasourceLuid: string): void {
    if (dataSources.value.some(ds => ds.id === datasourceLuid)) {
      selectedDataSourceId.value = datasourceLuid
    }
  }
  
  /**
   * 重置状态
   */
  function reset(): void {
    isInitialized.value = false
    isInitializing.value = false
    initError.value = null
    dataSources.value = []
    selectedDataSourceId.value = null
  }
  
  return {
    // 状态
    isInitialized,
    isInitializing,
    initError,
    dataSources,
    selectedDataSourceId,
    // 计算属性
    selectedDataSource,
    isPreloading,
    allPreloaded,
    // 方法
    initialize,
    triggerPreload,
    triggerPreloadAll,
    selectDataSource,
    reset
  }
})
