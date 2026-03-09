/**
 * Tableau Extensions API 工具类
 *
 * 核心策略：
 * 1. 非 Tableau 环境（独立浏览器打开）→ 立即返回，走降级模式
 * 2. isDashboardReady() 是唯一的"已初始化"判断依据
 * 3. initializeAsync 每次页面加载只调用一次（window 全局去重，防止重复调用挂死）
 * 4. 不 await initializeAsync 的 Promise，改用轮询 dashboardContent
 * 5. 超时抛出 TIMEOUT 而非 RELOAD_REQUIRED，由 store 层决定如何处理
 */

declare const tableau: {
  extensions: {
    initializeAsync(): Promise<void>
    dashboardContent: {
      dashboard: {
        name: string
        worksheets: Array<{
          name: string
          getDataSourcesAsync(): Promise<Array<{ id: string; name: string }>>
          getFiltersAsync(): Promise<Array<{ fieldName: string; appliedValues: unknown[] }>>
          getSummaryDataAsync(): Promise<{
            columns: Array<{ fieldName: string; index: number }>
            data: Array<Array<{ value: unknown }>>
          }>
        }>
      }
    }
    settings: {
      get(key: string): string | undefined
      set(key: string, value: string): void
      getAll(): Record<string, string>
      erase(key: string): void
      saveAsync(): Promise<void>
    }
  }
}

// ─── window 全局 key（跨 HMR 持久） ─────────────────────────────────────────
const KEY_INIT_STARTED = '__tableau_init_started__'

type GlobalWindow = Window & {
  [KEY_INIT_STARTED]?: boolean
}

function gw(): GlobalWindow {
  return window as GlobalWindow
}

// ─── 环境检测 ─────────────────────────────────────────────────────────────────

export function isInTableauEnvironment(): boolean {
  try {
    return typeof tableau !== 'undefined' && tableau?.extensions != null
  } catch {
    return false
  }
}

/**
 * 判断 Tableau Extension 是否已完成初始化
 * initializeAsync 完成后 Tableau SDK 才会赋值 dashboardContent
 */
export function isDashboardReady(): boolean {
  try {
    return (
      isInTableauEnvironment() &&
      tableau.extensions.dashboardContent != null &&
      tableau.extensions.dashboardContent.dashboard != null
    )
  } catch {
    return false
  }
}

// ─── 初始化核心 ───────────────────────────────────────────────────────────────

/**
 * 轮询等待 dashboardContent 就绪
 * 超时时抛出 TIMEOUT 错误
 */
async function waitUntilDashboardReady(timeoutMs: number, intervalMs = 200): Promise<void> {
  if (isDashboardReady()) return
  const deadline = Date.now() + timeoutMs
  while (Date.now() < deadline) {
    await new Promise(r => setTimeout(r, intervalMs))
    if (isDashboardReady()) return
  }
  throw new Error('TIMEOUT')
}

/**
 * 初始化 Tableau Extension
 *
 * - 非 Tableau 环境：立即 resolve（降级模式，外部调用方按需处理）
 * - 已就绪（HMR/快速路径）：立即 resolve
 * - 否则：触发 initializeAsync（去重），轮询 30s 等待就绪
 */
export async function initializeTableauExtension(): Promise<void> {
  // 非 Tableau 环境：直接返回，由 store 层决定是否降级
  if (!isInTableauEnvironment()) {
    console.warn('[Tableau] Not in Tableau environment, skipping init')
    return
  }

  // 快速路径：dashboardContent 已就绪
  if (isDashboardReady()) {
    console.log('[Tableau] Already initialized (dashboardContent ready)')
    return
  }

  // 触发 initializeAsync（同一页面只调一次，重复调用会导致 Tableau 宿主挂死）
  if (!gw()[KEY_INIT_STARTED]) {
    gw()[KEY_INIT_STARTED] = true
    console.log('[Tableau] Calling initializeAsync...')
    tableau.extensions.initializeAsync().then(() => {
      console.log('[Tableau] initializeAsync resolved')
    }).catch((err) => {
      console.warn('[Tableau] initializeAsync rejected (continuing poll):', err)
    })
  } else {
    console.log('[Tableau] initializeAsync already fired, polling dashboardContent...')
  }

  // 轮询等待（30s）
  await waitUntilDashboardReady(30_000)
  console.log('[Tableau] Extension ready')
}

/**
 * 重试：不重新调 initializeAsync，只重新轮询（30s）
 * initializeAsync 在同一页面生命周期内只能有效触发一次
 */
export async function retryWaitForDashboard(): Promise<void> {
  if (!isInTableauEnvironment()) {
    console.warn('[Tableau] Not in Tableau environment on retry')
    return
  }

  if (isDashboardReady()) {
    console.log('[Tableau] dashboardContent ready on retry (fast-path)')
    return
  }

  console.log('[Tableau] Retrying: polling dashboardContent (30s)...')
  await waitUntilDashboardReady(30_000)
  console.log('[Tableau] Extension ready after retry')
}

// ─── Dashboard 工具函数 ───────────────────────────────────────────────────────

export function getDashboardName(): string {
  if (!isDashboardReady()) return ''
  try {
    return tableau.extensions.dashboardContent.dashboard.name
  } catch {
    return ''
  }
}

export async function getAllDataSources(): Promise<Array<{ id: string; name: string }>> {
  if (!isDashboardReady()) {
    console.warn('[Tableau] dashboardContent not ready, returning empty sources')
    return []
  }
  try {
    const worksheets = tableau.extensions.dashboardContent.dashboard.worksheets
    const seen = new Set<string>()
    const result: Array<{ id: string; name: string }> = []
    for (const ws of worksheets) {
      const sources = await ws.getDataSourcesAsync()
      for (const ds of sources) {
        if (!seen.has(ds.id)) {
          seen.add(ds.id)
          result.push({ id: ds.id, name: ds.name })
        }
      }
    }
    return result
  } catch (err) {
    console.warn('[Tableau] Failed to get data sources:', err)
    return []
  }
}

// ─── Settings 工具函数 ────────────────────────────────────────────────────────

export function getSetting(key: string): string | undefined {
  if (!isInTableauEnvironment()) return undefined
  return tableau.extensions.settings.get(key)
}

export function setSetting(key: string, value: string): void {
  if (!isInTableauEnvironment()) return
  tableau.extensions.settings.set(key, value)
}

export async function saveSettings(): Promise<void> {
  if (!isInTableauEnvironment()) return
  await tableau.extensions.settings.saveAsync()
}

export function getAllSettings(): Record<string, string> {
  if (!isInTableauEnvironment()) return {}
  return tableau.extensions.settings.getAll()
}
