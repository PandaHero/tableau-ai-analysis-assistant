/**
 * Tableau Extensions API类型定义
 * 
 * 这个文件提供Tableau Extensions API的TypeScript类型定义
 * 官方文档: https://tableau.github.io/extensions-api/
 */

declare namespace tableau {
  /**
   * Extensions命名空间
   */
  namespace extensions {
    /**
     * 初始化Extension
     */
    function initializeAsync(options?: InitializationOptions): Promise<void>

    /**
     * Dashboard内容
     */
    const dashboardContent: DashboardContent

    /**
     * 设置
     */
    const settings: Settings

    /**
     * UI命名空间
     */
    namespace ui {
      function displayDialogAsync(
        url: string,
        payload?: string,
        options?: DialogOptions
      ): Promise<string>

      function closeDialog(payload?: string): void
    }
  }

  /**
   * 初始化选项
   */
  interface InitializationOptions {
    configure?: () => void
  }

  /**
   * Dashboard内容
   */
  interface DashboardContent {
    dashboard: Dashboard
  }

  /**
   * Dashboard
   */
  interface Dashboard {
    name: string
    worksheets: Worksheet[]
    objects: DashboardObject[]
    getParametersAsync(): Promise<Parameter[]>
    findParameterAsync(parameterName: string): Promise<Parameter>
  }

  /**
   * Worksheet
   */
  interface Worksheet {
    name: string
    getDataSourcesAsync(): Promise<DataSource[]>
    getSelectedMarksAsync(): Promise<MarksCollection>
    applyFilterAsync(
      fieldName: string,
      values: string[],
      updateType: FilterUpdateType,
      options?: FilterOptions
    ): Promise<string>
    clearFilterAsync(fieldName: string): Promise<string>
    getFiltersAsync(): Promise<Filter[]>
  }

  /**
   * DataSource
   */
  interface DataSource {
    id: string
    name: string
    fields: Field[]
    getLogicalTablesAsync(): Promise<LogicalTable[]>
    getActiveTablesAsync(): Promise<Table[]>
    getUnderlyingDataAsync(options?: GetUnderlyingDataOptions): Promise<DataTable>
  }

  /**
   * Field
   */
  interface Field {
    id: string
    name: string
    description: string
    dataType: DataType
    role: FieldRole
    aggregation: FieldAggregationType
  }

  /**
   * DataType枚举
   */
  enum DataType {
    Bool = 'bool',
    Date = 'date',
    DateTime = 'date-time',
    Float = 'float',
    Int = 'int',
    String = 'string',
  }

  /**
   * FieldRole枚举
   */
  enum FieldRole {
    Dimension = 'dimension',
    Measure = 'measure',
    Unknown = 'unknown',
  }

  /**
   * FieldAggregationType枚举
   */
  enum FieldAggregationType {
    Sum = 'sum',
    Avg = 'avg',
    Min = 'min',
    Max = 'max',
    Count = 'count',
    CountDistinct = 'count-distinct',
  }

  /**
   * Filter
   */
  interface Filter {
    fieldName: string
    filterType: FilterType
    appliedValues: any[]
  }

  /**
   * FilterType枚举
   */
  enum FilterType {
    Categorical = 'categorical',
    Range = 'range',
    RelativeDate = 'relative-date',
  }

  /**
   * FilterUpdateType枚举
   */
  enum FilterUpdateType {
    Add = 'add',
    All = 'all',
    Remove = 'remove',
    Replace = 'replace',
  }

  /**
   * FilterOptions
   */
  interface FilterOptions {
    isExcludeMode?: boolean
  }

  /**
   * Parameter
   */
  interface Parameter {
    id: string
    name: string
    currentValue: DataValue
    dataType: DataType
    allowableValues: ParameterAllowableValues
    changeValueAsync(newValue: string | number | boolean | Date): Promise<DataValue>
  }

  /**
   * DataValue
   */
  interface DataValue {
    value: string | number | boolean | Date
    formattedValue: string
  }

  /**
   * ParameterAllowableValues
   */
  interface ParameterAllowableValues {
    type: ParameterValueType
    allowableValues?: DataValue[]
  }

  /**
   * ParameterValueType枚举
   */
  enum ParameterValueType {
    All = 'all',
    List = 'list',
    Range = 'range',
  }

  /**
   * MarksCollection
   */
  interface MarksCollection {
    data: DataTable[]
  }

  /**
   * DataTable
   */
  interface DataTable {
    name: string
    data: any[][]
    columns: Column[]
    totalRowCount: number
    isSummaryData: boolean
  }

  /**
   * Column
   */
  interface Column {
    fieldName: string
    dataType: DataType
    index: number
  }

  /**
   * LogicalTable
   */
  interface LogicalTable {
    id: string
    caption: string
  }

  /**
   * Table
   */
  interface Table {
    id: string
    name: string
  }

  /**
   * GetUnderlyingDataOptions
   */
  interface GetUnderlyingDataOptions {
    maxRows?: number
    ignoreAliases?: boolean
    ignoreSelection?: boolean
    includeAllColumns?: boolean
  }

  /**
   * DashboardObject
   */
  interface DashboardObject {
    id: string
    name: string
    type: DashboardObjectType
    position: Point
    size: Size
  }

  /**
   * DashboardObjectType枚举
   */
  enum DashboardObjectType {
    Blank = 'blank',
    Extension = 'extension',
    Image = 'image',
    Legend = 'legend',
    PageFilter = 'page-filter',
    ParameterControl = 'parameter-control',
    QuickFilter = 'quick-filter',
    Text = 'text',
    Title = 'title',
    WebPage = 'web-page',
    Worksheet = 'worksheet',
  }

  /**
   * Point
   */
  interface Point {
    x: number
    y: number
  }

  /**
   * Size
   */
  interface Size {
    width: number
    height: number
  }

  /**
   * Settings
   */
  interface Settings {
    get(key: string): string | undefined
    getAll(): { [key: string]: string }
    set(key: string, value: string): void
    erase(key: string): void
    saveAsync(): Promise<string>
  }

  /**
   * DialogOptions
   */
  interface DialogOptions {
    height?: number
    width?: number
  }
}

export = tableau
export as namespace tableau
