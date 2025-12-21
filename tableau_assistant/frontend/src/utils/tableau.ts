/**
 * Tableau Extensions API 工具类
 * 简化版 - 只保留必要功能
 */

// 连接摘要类型
interface ConnectionSummary {
  id: string
  name: string
  serverURI: string | undefined
  type: string
}

// 数据源类型
interface DataSourceWithConnection {
  id: string
  name: string
  isPublished: boolean | undefined
  getConnectionSummariesAsync(): Promise<ConnectionSummary[]>
}

// 声明 tableau 全局变量类型
declare const tableau: {
  extensions: {
    initializeAsync(): Promise<void>
    dashboardContent: {
      dashboard: {
        name: string
        worksheets: Array<{
          name: string
          getDataSourcesAsync(): Promise<DataSourceWithConnection[]>
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
    environment: {
      apiVersion: string
      context: 'desktop' | 'server' | 'cloud' | 'public-desktop' | 'public-web'
      country?: string
      language: string
      locale: string
      mode: 'authoring' | 'viewing'
      operatingSystem: string
      tableauVersion: string
      uniqueUserId?: string
    }
  }
}

/**
 * 检查是否在 Tableau 环境中
 */
export function isInTableauEnvironment(): boolean {
  const hasTableau = typeof tableau !== 'undefined'
  const hasExtensions = hasTableau && typeof tableau.extensions !== 'undefined'
  console.log('isInTableauEnvironment check:', { hasTableau, hasExtensions })
  return hasExtensions
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

/**
 * 获取 Tableau 环境信息
 * 
 * 注意：Tableau Extensions API 没有直接提供服务器 URL
 * context 可以是: 'desktop' | 'server' | 'cloud' | 'public-desktop' | 'public-web'
 */
export function getTableauEnvironment(): { 
  context: string
  mode: string
  tableauVersion: string
  apiVersion: string
} | null {
  if (!isInTableauEnvironment()) {
    console.warn('getTableauEnvironment: Not in Tableau environment')
    return null
  }
  try {
    const env = {
      context: tableau.extensions.environment.context,
      mode: tableau.extensions.environment.mode,
      tableauVersion: tableau.extensions.environment.tableauVersion,
      apiVersion: tableau.extensions.environment.apiVersion
    }
    console.log('getTableauEnvironment:', env)
    return env
  } catch (error) {
    console.error('getTableauEnvironment error:', error)
    return null
  }
}

/**
 * 数据源连接信息
 */
export interface DataSourceConnectionInfo {
  serverURI?: string
  connectionType?: string
  isPublished?: boolean
}

/**
 * 从数据源连接信息中获取服务器信息
 * 
 * 返回：
 * - serverURI: 服务器地址（对于已发布数据源可能是 localhost）
 * - connectionType: 连接类型（如 "tableau-server-site", "sqlserver" 等）
 * - isPublished: 是否是已发布的数据源
 */
export async function getDataSourceConnectionInfo(): Promise<DataSourceConnectionInfo | undefined> {
  if (!isInTableauEnvironment()) {
    return undefined
  }
  
  try {
    const worksheets = tableau.extensions.dashboardContent.dashboard.worksheets
    
    for (const ws of worksheets) {
      const dataSources = await ws.getDataSourcesAsync()
      
      for (const ds of dataSources) {
        console.log(`DataSource: ${ds.name}, isPublished: ${ds.isPublished}`)
        
        // 获取连接信息
        const connections = await ds.getConnectionSummariesAsync()
        console.log(`DataSource ${ds.name} connections:`, JSON.stringify(connections, null, 2))
        
        // 返回第一个有效的连接信息
        for (const conn of connections) {
          return {
            serverURI: conn.serverURI,
            connectionType: conn.type,
            isPublished: ds.isPublished
          }
        }
      }
    }
    
    console.log('No data source connection info found')
    return undefined
  } catch (error) {
    console.error('Error getting data source connection info:', error)
    return undefined
  }
}

/**
 * 从数据源连接信息中尝试获取服务器 URL
 */
export async function getServerUrlFromDataSource(): Promise<string | undefined> {
  const info = await getDataSourceConnectionInfo()
  
  if (info?.serverURI && info.serverURI !== 'localhost') {
    console.log(`Found server URL from connection: ${info.serverURI}`)
    return info.serverURI
  }
  
  console.log('No valid server URL found from data source connections')
  return undefined
}

/**
 * 获取 Tableau 服务器域名
 * 
 * 优先级：
 * 1. 用户在设置中配置的 URL
 * 2. 从数据源连接信息获取
 * 3. 根据 context 推断（cloud -> online.tableau.com）
 * 4. undefined（让后端使用默认配置）
 */
export async function getTableauDomainAsync(): Promise<string | undefined> {
  // 1. 检查用户设置
  const savedUrl = getSetting('tableauServerUrl')
  if (savedUrl) {
    console.log('Using saved Tableau server URL:', savedUrl)
    return savedUrl
  }
  
  // 2. 尝试从数据源获取
  const serverUrl = await getServerUrlFromDataSource()
  if (serverUrl) {
    return serverUrl
  }
  
  // 3. 根据 context 推断
  const env = getTableauEnvironment()
  if (env?.context === 'cloud') {
    console.log('Running in Tableau Cloud context')
    return 'online.tableau.com'
  }
  
  // 4. 无法确定，返回 undefined
  console.log('Cannot determine Tableau server URL, will use backend default')
  return undefined
}

/**
 * 同步获取 Tableau 域名（用于兼容现有代码）
 * 注意：这个函数只能获取已保存的设置，无法获取数据源连接信息
 */
export function getTableauDomain(): string | undefined {
  // 只返回用户设置的 URL
  const savedUrl = getSetting('tableauServerUrl')
  if (savedUrl) {
    return savedUrl
  }
  
  // 根据 context 推断
  const env = getTableauEnvironment()
  if (env?.context === 'cloud') {
    return 'online.tableau.com'
  }
  
  return undefined
}
