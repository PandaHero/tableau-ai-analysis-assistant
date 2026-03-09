// API 响应相关类型定义

export interface ApiResponse<T> {
  data: T
  message?: string
  error?: string
}

export interface ApiError {
  code: string
  message: string
  details?: any
}
