/**
 * 性能监控工具
 * 提供性能测量和监控功能
 */

import { logger } from './logger'

interface PerformanceMark {
  name: string
  startTime: number
}

class PerformanceMonitor {
  private marks: Map<string, PerformanceMark> = new Map()
  private slowThreshold = 1000 // 慢操作阈值(ms)

  /**
   * 开始性能测量
   */
  start(name: string) {
    this.marks.set(name, {
      name,
      startTime: performance.now()
    })
  }

  /**
   * 结束性能测量
   */
  end(name: string): number | null {
    const mark = this.marks.get(name)
    if (!mark) {
      logger.warn(`Performance mark "${name}" not found`)
      return null
    }

    const duration = performance.now() - mark.startTime
    this.marks.delete(name)

    // 记录慢操作
    if (duration > this.slowThreshold) {
      logger.warn(`Slow operation detected: ${name} took ${duration.toFixed(2)}ms`)
    } else {
      logger.debug(`Performance: ${name} took ${duration.toFixed(2)}ms`)
    }

    return duration
  }

  /**
   * 测量同步函数执行时间
   */
  measure<T>(name: string, fn: () => T): T {
    this.start(name)
    try {
      return fn()
    } finally {
      this.end(name)
    }
  }

  /**
   * 测量异步函数执行时间
   */
  async measureAsync<T>(name: string, fn: () => Promise<T>): Promise<T> {
    this.start(name)
    try {
      return await fn()
    } finally {
      this.end(name)
    }
  }

  /**
   * 设置慢操作阈值
   */
  setSlowThreshold(threshold: number) {
    this.slowThreshold = threshold
  }

  /**
   * 获取页面加载性能指标
   */
  getPageLoadMetrics() {
    if (!window.performance || !window.performance.timing) {
      return null
    }

    const timing = window.performance.timing
    const metrics = {
      // DNS 查询时间
      dns: timing.domainLookupEnd - timing.domainLookupStart,
      // TCP 连接时间
      tcp: timing.connectEnd - timing.connectStart,
      // 请求时间
      request: timing.responseStart - timing.requestStart,
      // 响应时间
      response: timing.responseEnd - timing.responseStart,
      // DOM 解析时间
      domParse: timing.domInteractive - timing.domLoading,
      // 资源加载时间
      resourceLoad: timing.loadEventStart - timing.domContentLoadedEventEnd,
      // 总加载时间
      total: timing.loadEventEnd - timing.navigationStart
    }

    logger.info('Page load metrics:', metrics)
    return metrics
  }

  /**
   * 监听长任务(Long Tasks)
   */
  observeLongTasks() {
    if ('PerformanceObserver' in window) {
      try {
        const observer = new PerformanceObserver((list) => {
          for (const entry of list.getEntries()) {
            logger.warn(`Long task detected: ${entry.duration.toFixed(2)}ms`, entry)
          }
        })

        observer.observe({ entryTypes: ['longtask'] })
      } catch (error) {
        logger.error('Failed to observe long tasks:', error)
      }
    }
  }
}

// 导出单例
export const performanceMonitor = new PerformanceMonitor()
