/**
 * 前端日志工具
 * 提供统一的日志记录接口
 */

export enum LogLevel {
  DEBUG = 0,
  INFO = 1,
  WARN = 2,
  ERROR = 3
}

class Logger {
  private level: LogLevel
  private isDevelopment: boolean

  constructor() {
    this.isDevelopment = import.meta.env.DEV
    this.level = this.isDevelopment ? LogLevel.DEBUG : LogLevel.INFO
  }

  /**
   * 设置日志级别
   */
  setLevel(level: LogLevel) {
    this.level = level
  }

  /**
   * Debug 日志
   */
  debug(message: string, ...args: any[]) {
    if (this.level <= LogLevel.DEBUG) {
      console.debug(`[DEBUG] ${message}`, ...args)
    }
  }

  /**
   * Info 日志
   */
  info(message: string, ...args: any[]) {
    if (this.level <= LogLevel.INFO) {
      console.info(`[INFO] ${message}`, ...args)
    }
  }

  /**
   * Warning 日志
   */
  warn(message: string, ...args: any[]) {
    if (this.level <= LogLevel.WARN) {
      console.warn(`[WARN] ${message}`, ...args)
    }
  }

  /**
   * Error 日志
   */
  error(message: string, error?: any, ...args: any[]) {
    if (this.level <= LogLevel.ERROR) {
      console.error(`[ERROR] ${message}`, error, ...args)

      // 生产环境发送到监控服务
      if (!this.isDevelopment) {
        this.sendToMonitoring(message, error)
      }
    }
  }

  /**
   * 发送错误到监控服务
   */
  private sendToMonitoring(message: string, error?: any) {
    try {
      // TODO: 集成实际的监控服务(如 Sentry)
      const errorData = {
        message,
        error: error?.message || error,
        stack: error?.stack,
        timestamp: new Date().toISOString(),
        userAgent: navigator.userAgent,
        url: window.location.href
      }

      // 示例: 发送到后端日志接口
      // fetch('/api/logs/error', {
      //   method: 'POST',
      //   headers: { 'Content-Type': 'application/json' },
      //   body: JSON.stringify(errorData)
      // })

      console.log('Error sent to monitoring:', errorData)
    } catch (err) {
      console.error('Failed to send error to monitoring:', err)
    }
  }
}

// 导出单例
export const logger = new Logger()
