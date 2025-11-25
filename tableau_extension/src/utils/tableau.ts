/**
 * Tableau Extensions API工具类
 * 
 * 封装常用的Tableau API操作
 */

/**
 * 初始化Tableau Extension
 */
export async function initializeTableauExtension(): Promise<void> {
  try {
    await tableau.extensions.initializeAsync()
    console.log('Tableau Extension initialized successfully')
  } catch (error) {
    console.error('Failed to initialize Tableau Extension:', error)
    throw error
  }
}

/**
 * 获取当前Dashboard
 */
export function getCurrentDashboard(): tableau.Dashboard {
  return tableau.extensions.dashboardContent.dashboard
}

/**
 * 获取所有Worksheets
 */
export function getWorksheets(): tableau.Worksheet[] {
  const dashboard = getCurrentDashboard()
  return dashboard.worksheets
}

/**
 * 根据名称获取Worksheet
 */
export function getWorksheetByName(name: string): tableau.Worksheet | undefined {
  const worksheets = getWorksheets()
  return worksheets.find((ws) => ws.name === name)
}

/**
 * 获取所有DataSources
 */
export async function getAllDataSources(): Promise<tableau.DataSource[]> {
  const worksheets = getWorksheets()
  const dataSourcesPromises = worksheets.map((ws) => ws.getDataSourcesAsync())
  const dataSourcesArrays = await Promise.all(dataSourcesPromises)

  // 去重
  const uniqueDataSources = new Map<string, tableau.DataSource>()
  dataSourcesArrays.flat().forEach((ds) => {
    if (!uniqueDataSources.has(ds.id)) {
      uniqueDataSources.set(ds.id, ds)
    }
  })

  return Array.from(uniqueDataSources.values())
}

/**
 * 获取DataSource的字段信息
 */
export async function getDataSourceFields(
  dataSource: tableau.DataSource
): Promise<tableau.Field[]> {
  return dataSource.fields
}

/**
 * 获取DataSource的底层数据
 */
export async function getUnderlyingData(
  dataSource: tableau.DataSource,
  options?: tableau.GetUnderlyingDataOptions
): Promise<tableau.DataTable> {
  return await dataSource.getUnderlyingDataAsync(options)
}

/**
 * 应用筛选器
 */
export async function applyFilter(
  worksheet: tableau.Worksheet,
  fieldName: string,
  values: string[],
  updateType: tableau.FilterUpdateType = tableau.FilterUpdateType.Replace
): Promise<void> {
  try {
    await worksheet.applyFilterAsync(fieldName, values, updateType)
    console.log(`Filter applied: ${fieldName} = ${values.join(', ')}`)
  } catch (error) {
    console.error('Failed to apply filter:', error)
    throw error
  }
}

/**
 * 清除筛选器
 */
export async function clearFilter(
  worksheet: tableau.Worksheet,
  fieldName: string
): Promise<void> {
  try {
    await worksheet.clearFilterAsync(fieldName)
    console.log(`Filter cleared: ${fieldName}`)
  } catch (error) {
    console.error('Failed to clear filter:', error)
    throw error
  }
}

/**
 * 获取所有筛选器
 */
export async function getFilters(worksheet: tableau.Worksheet): Promise<tableau.Filter[]> {
  return await worksheet.getFiltersAsync()
}

/**
 * 获取所有参数
 */
export async function getParameters(): Promise<tableau.Parameter[]> {
  const dashboard = getCurrentDashboard()
  return await dashboard.getParametersAsync()
}

/**
 * 根据名称获取参数
 */
export async function getParameterByName(name: string): Promise<tableau.Parameter> {
  const dashboard = getCurrentDashboard()
  return await dashboard.findParameterAsync(name)
}

/**
 * 更改参数值
 */
export async function changeParameterValue(
  parameter: tableau.Parameter,
  newValue: string | number | boolean | Date
): Promise<void> {
  try {
    await parameter.changeValueAsync(newValue)
    console.log(`Parameter changed: ${parameter.name} = ${newValue}`)
  } catch (error) {
    console.error('Failed to change parameter:', error)
    throw error
  }
}

/**
 * 获取选中的标记
 */
export async function getSelectedMarks(
  worksheet: tableau.Worksheet
): Promise<tableau.MarksCollection> {
  return await worksheet.getSelectedMarksAsync()
}

/**
 * 保存设置
 */
export async function saveSettings(): Promise<void> {
  try {
    await tableau.extensions.settings.saveAsync()
    console.log('Settings saved successfully')
  } catch (error) {
    console.error('Failed to save settings:', error)
    throw error
  }
}

/**
 * 获取设置值
 */
export function getSetting(key: string): string | undefined {
  return tableau.extensions.settings.get(key)
}

/**
 * 设置设置值
 */
export function setSetting(key: string, value: string): void {
  tableau.extensions.settings.set(key, value)
}

/**
 * 获取所有设置
 */
export function getAllSettings(): { [key: string]: string } {
  return tableau.extensions.settings.getAll()
}

/**
 * 删除设置
 */
export function eraseSetting(key: string): void {
  tableau.extensions.settings.erase(key)
}

/**
 * 显示对话框
 */
export async function displayDialog(
  url: string,
  payload?: string,
  options?: tableau.DialogOptions
): Promise<string> {
  return await tableau.extensions.ui.displayDialogAsync(url, payload, options)
}

/**
 * 关闭对话框
 */
export function closeDialog(payload?: string): void {
  tableau.extensions.ui.closeDialog(payload)
}

/**
 * 检查是否在Tableau环境中
 */
export function isInTableauEnvironment(): boolean {
  return typeof tableau !== 'undefined' && typeof tableau.extensions !== 'undefined'
}
