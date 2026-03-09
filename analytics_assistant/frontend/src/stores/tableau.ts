/**
 * Tableau Store
 * 管理 Tableau Extension 初始化状态
 *
 * 设计原则：
 * 1. 非 Tableau 环境（独立浏览器/localhost 直接打开）→ 降级模式，直接 isInitialized=true，不报错
 * 2. Tableau 环境但 dashboardContent 已就绪 → 快速路径，直接拉数据
 * 3. Tableau 环境且需要 initializeAsync → 最长等待 35s，超时后降级（不卡死用户）
 * 4. initializeAsync 在同一页面只能有效触发一次，重试走 retryWaitForDashboard
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import {
  isInTableauEnvironment,
  isDashboardReady,
  initializeTableauExtension,
  retryWaitForDashboard,
  getAllDataSources,
  getDashboardName,
} from '@/utils/tableau'

export interface DataSourceInfo {
  id: string
  name: string
}

// 等待 dashboardContent 的最大时间（内部轮询 30s，这里多 5s 作为绝对兜底）
const STORE_TIMEOUT_MS = 35_000

export const useTableauStore = defineStore('tableau', () => {
  // ─── 状态 ───────────────────────────────────────────────────────────────────
  const isInitialized = ref(false)
  const isInitializing = ref(false)
  const initError = ref<string | null>(null)
  const dashboardName = ref('')
  const dataSources = ref<DataSourceInfo[]>([])
  const selectedDataSourceId = ref<string | null>(null)
  const isPreloading = ref(false)
  /** 降级模式：非 Tableau 环境或初始化超时后启用，功能受限但界面正常显示 */
  const isDegradedMode = ref(false)

  // 防止并发重入
  let _initPromise: Promise<boolean> | null = null
  // 重试标志：重试时不重新调 initializeAsync
  let _isRetry = false

  // ─── 计算属性 ────────────────────────────────────────────────────────────────
  const selectedDataSource = computed(() =>
    selectedDataSourceId.value
      ? (dataSources.value.find(ds => ds.id === selectedDataSourceId.value) ?? null)
      : null
  )
  const isInTableau = computed(() => isInTableauEnvironment())

  // ─── 内部工具 ────────────────────────────────────────────────────────────────
  function withAbsoluteTimeout<T>(promise: Promise<T>, ms: number, msg: string): Promise<T> {
    let timer: ReturnType<typeof setTimeout> | undefined
    const timeout = new Promise<never>((_, reject) => {
      timer = setTimeout(() => reject(new Error(msg)), ms)
    })
    return Promise.race([promise, timeout]).finally(() => {
      clearTimeout(timer)
    }) as Promise<T>
  }

  async function _fetchDashboardData(): Promise<void> {
    dashboardName.value = getDashboardName()
    const sources = await withAbsoluteTimeout(
      getAllDataSources(),
      15_000,
      '获取数据源超时'
    )
    dataSources.value = sources
    if (sources.length > 0 && !selectedDataSourceId.value) {
      selectedDataSourceId.value = sources[0].id
    }
  }

  /** 进入降级模式：不报错，直接让界面正常显示 */
  function _enterDegradedMode(reason: string): void {
    console.warn(`[TableauStore] Degraded mode: ${reason}`)
    isDegradedMode.value = true
    isInitialized.value = true   // 让主界面正常渲染
    initError.value = null        // 不显示错误页
    isInitializing.value = false
  }

  // ─── 主初始化函数 ─────────────────────────────────────────────────────────────
  async function initialize(): Promise<boolean> {
    if (_initPromise) return _initPromise
    _initPromise = _doInitialize().finally(() => { _initPromise = null })
    return _initPromise
  }

  async function _doInitialize(): Promise<boolean> {
    // ── 情形 1：非 Tableau 环境 → 直接降级，不卡 ──────────────────────────────
    if (!isInTableauEnvironment()) {
      _enterDegradedMode('Not in Tableau environment')
      return true
    }

    // ── 情形 2：快速路径，dashboardContent 已就绪 ─────────────────────────────
    if (isDashboardReady()) {
      console.log('[TableauStore] Fast-path: dashboardContent already ready')
      try {
        isInitializing.value = true
        await _fetchDashboardData()
        isInitialized.value = true
        isDegradedMode.value = false
        initError.value = null
        return true
      } catch (err) {
        console.error('[TableauStore] Fast-path fetch failed:', err)
        // 数据拉取失败也降级，不卡用户
        _enterDegradedMode('fetch failed after fast-path')
        return true
      } finally {
        isInitializing.value = false
      }
    }

    // ── 情形 3：需要走 initializeAsync 流程 ──────────────────────────────────
    if (isInitializing.value) {
      console.warn('[TableauStore] Already initializing, skip')
      return isInitialized.value
    }

    isInitializing.value = true
    isInitialized.value = false
    initError.value = null

    // 绝对超时兜底
    let _forceTimeoutId: ReturnType<typeof setTimeout> | undefined
    const forceCleanup = new Promise<never>((_, reject) => {
      _forceTimeoutId = setTimeout(() => {
        reject(new Error('TIMEOUT'))
      }, STORE_TIMEOUT_MS)
    })

    try {
      const initFn = _isRetry ? retryWaitForDashboard() : initializeTableauExtension()
      await Promise.race([initFn, forceCleanup])

      await _fetchDashboardData()

      isInitialized.value = true
      isDegradedMode.value = false
      _isRetry = false
      console.log('[TableauStore] Initialized:', {
        dashboard: dashboardName.value,
        sources: dataSources.value.length,
      })
      return true
    } catch (err) {
      const msg = err instanceof Error ? err.message : String(err)
      console.error('[TableauStore] Init failed:', msg)

      if (msg === 'TIMEOUT') {
        if (!isInTableauEnvironment()) {
          // 非 Tableau 环境超时：降级进入主界面
          _enterDegradedMode('not in Tableau, timed out')
          return true
        }
        // Tableau 环境超时：提示用户重试（此时 initializeAsync 可能仍在后台运行）
        initError.value = 'TIMEOUT'
        return false
      }

      // 其他真实错误（如网络断开、API 异常）才显示错误页
      initError.value = msg
      return false
    } finally {
      clearTimeout(_forceTimeoutId)
      isInitializing.value = false
    }
  }

  // ─── 其他操作 ─────────────────────────────────────────────────────────────────
  function selectDataSource(id: string): void {
    if (dataSources.value.some(ds => ds.id === id)) {
      selectedDataSourceId.value = id
    }
  }

  /**
   * 重置并重试初始化
   * 不清除 __tableau_init_started__，重试只重新轮询而非重复调 initializeAsync
   */
  function reset(): void {
    isInitialized.value = false
    isInitializing.value = false
    initError.value = null
    isDegradedMode.value = false
    dashboardName.value = ''
    dataSources.value = []
    selectedDataSourceId.value = null
    _initPromise = null
    _isRetry = true
  }

  return {
    isInitialized,
    isInitializing,
    initError,
    isDegradedMode,
    dashboardName,
    dataSources,
    selectedDataSourceId,
    isPreloading,
    selectedDataSource,
    isInTableau,
    initialize,
    selectDataSource,
    reset,
  }
})
