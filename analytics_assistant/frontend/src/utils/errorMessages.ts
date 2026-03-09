/**
 * HTTP 错误消息映射
 * Requirements: 14.1, 14.2, 14.3, 14.4
 */

// HTTP 状态码到用户友好消息的映射
export const HTTP_ERROR_MESSAGES: Record<number, string> = {
  400: '请求格式错误',
  401: '请重新登录',
  403: '无访问权限',
  404: '资源不存在',
  408: '请求超时，请稍后重试',
  429: '请求过于频繁，请稍后重试',
  500: '服务器内部错误，请稍后重试',
  502: '网关错误，请稍后重试',
  503: '服务暂时不可用，请稍后重试',
  504: '网关超时，请稍后重试'
}

// 默认错误消息
export const DEFAULT_ERROR_MESSAGE = '发生未知错误，请稍后重试'

// 网络错误消息
export const NETWORK_ERROR_MESSAGE = '网络连接失败，请检查网络后重试'

// 超时错误消息
export const TIMEOUT_ERROR_MESSAGE = '分析时间较长，请稍候或尝试简化问题'

// 数据源连接错误消息
export const DATASOURCE_ERROR_MESSAGE = '数据源连接失败，请联系管理员'

/**
 * 根据 HTTP 状态码获取用户友好的错误消息
 */
export function getHttpErrorMessage(status: number): string {
  return HTTP_ERROR_MESSAGES[status] || DEFAULT_ERROR_MESSAGE
}

/**
 * 根据错误对象获取用户友好的错误消息
 */
export function getErrorMessage(error: unknown): string {
  if (error instanceof Error) {
    // 网络错误
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      return NETWORK_ERROR_MESSAGE
    }
    
    // 超时错误
    if (error.name === 'AbortError' || error.message.includes('timeout')) {
      return TIMEOUT_ERROR_MESSAGE
    }
    
    // HTTP 错误
    const httpMatch = error.message.match(/HTTP (\d+)/)
    if (httpMatch) {
      const status = parseInt(httpMatch[1], 10)
      return getHttpErrorMessage(status)
    }
    
    return error.message || DEFAULT_ERROR_MESSAGE
  }
  
  if (typeof error === 'string') {
    return error
  }
  
  return DEFAULT_ERROR_MESSAGE
}

/**
 * 判断错误是否可重试
 */
export function isRetryableError(error: unknown): boolean {
  if (error instanceof Error) {
    // 网络错误可重试
    if (error.name === 'TypeError' && error.message.includes('fetch')) {
      return true
    }
    
    // 超时可重试
    if (error.name === 'AbortError' || error.message.includes('timeout')) {
      return true
    }
    
    // 5xx 错误可重试
    const httpMatch = error.message.match(/HTTP (\d+)/)
    if (httpMatch) {
      const status = parseInt(httpMatch[1], 10)
      return status >= 500 && status < 600
    }
  }
  
  return false
}
