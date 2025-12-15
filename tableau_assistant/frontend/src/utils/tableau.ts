/**
 * Tableau Extensions API 工具类
 * 简化版 - 只保留必要功能
 */

// 声明 tableau 全局变量类型
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

/**
 * 检查是否在 Tableau 环境中
 */
export function isInTableauEnvironment(): boolean {
  return typeof tableau !== 'undefined' && typeof tableau.extensions !== 'undefined'
}

/**
 * 初始化 Tableau Extension
 */
export async function initializeTableauExtension(): Promise<void> {
  if (!isInTableauEnvironment()) {
    console.warn('Not in Tableau environment')
    return
  }
  
  try {
    await tableau.extensions.initializeAsync()
    console.log('Tableau Extension initialized')
  } catch (error) {
    console.error('Failed to initialize Tableau Extension:', error)
    throw error
  }
}

/**
 * 获取仪表板名称
 */
export function getDashboardName(): string {
  if (!isInTableauEnvironment()) return 'Development Mode'
  return tableau.extensions.dashboardContent.dashboard.name
}

/**
 * 获取所有数据源
 */
export async function getAllDataSources(): Promise<Array<{ id: string; name: string }>> {
  if (!isInTableauEnvironment()) {
    console.warn('Not in Tableau environment, cannot get data sources')
    return []
  }
  
  const worksheets = tableau.extensions.dashboardContent.dashboard.worksheets
  const allDataSources: Array<{ id: string; name: string }> = []
  const seen = new Set<string>()
  
  for (const ws of worksheets) {
    const dataSources = await ws.getDataSourcesAsync()
    for (const ds of dataSources) {
      if (!seen.has(ds.id)) {
        seen.add(ds.id)
        allDataSources.push({ id: ds.id, name: ds.name })
      }
    }
  }
  
  return allDataSources
}

/**
 * 获取设置值
 */
export function getSetting(key: string): string | undefined {
  if (!isInTableauEnvironment()) {
    console.warn('Not in Tableau environment')
    return undefined
  }
  return tableau.extensions.settings.get(key)
}

/**
 * 设置值
 */
export function setSetting(key: string, value: string): void {
  if (!isInTableauEnvironment()) {
    console.warn('Not in Tableau environment')
    return
  }
  tableau.extensions.settings.set(key, value)
}

/**
 * 保存设置
 */
export async function saveSettings(): Promise<void> {
  if (!isInTableauEnvironment()) return
  await tableau.extensions.settings.saveAsync()
}

/**
 * 获取所有设置
 */
export function getAllSettings(): Record<string, string> {
  if (!isInTableauEnvironment()) return {}
  return tableau.extensions.settings.getAll()
}
