// Tableau 相关类型定义

export interface DataSource {
  id: string
  name: string
  type: string
  connectionName: string
}

export interface TableauContext {
  username: string
  dashboardName: string
  dataSources: DataSource[]
}
