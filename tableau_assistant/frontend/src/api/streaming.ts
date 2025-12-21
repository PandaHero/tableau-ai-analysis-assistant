/**
 * SSE 流式客户端
 * Requirements: 11.1, 11.2, 11.3, 11.4, 11.5, 11.6
 */
import type { ChatRequest } from './client'

const API_BASE_URL = import.meta.env.VITE_API_BASE_URL || 'https://127.0.0.1:8000'

// 默认配置
const DEFAULT_TIMEOUT = 60000      // 60秒超时
const DEFAULT_RECONNECT_DELAY = 5000  // 5秒重连延迟
const MAX_RECONNECT_ATTEMPTS = 3   // 最大重连次数

// SSE 事件类型
export type SSEEventType =
  | 'token'
  | 'node_start'
  | 'node_complete'
  | 'complete'
  | 'error'
  | 'timeout'
  | 'disconnect'

// 后端返回的原始事件格式
interface RawSSEEvent {
  event_type: string
  data: {
    node?: string
    content?: string
    data?: unknown
    message?: string
  }
  timestamp: number
}

export interface SSEEvent {
  type: SSEEventType
  data: unknown
  timestamp: number
}

export interface TokenData {
  content: string  // 后端发送的 token 内容字段
  node?: string    // 产生 token 的节点名称
}

export interface NodeData {
  node: string           // 节点名称
  content?: string       // 节点内容（如有）
  output?: unknown       // 节点输出数据
}

export interface CompleteData {
  duration: number
  response?: unknown
}

export interface ErrorData {
  error: string
}

export interface SSEClientConfig {
  timeout?: number
  reconnectDelay?: number
  maxReconnectAttempts?: number
}

// 事件回调类型
export type SSECallback = (event: SSEEvent) => void

/**
 * SSE 流式客户端
 */
export class SSEClient {
  private abortController: AbortController | null = null
  private callbacks: Map<SSEEventType | 'all', SSECallback[]> = new Map()
  private timeoutId: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempts = 0
  private lastRequest: ChatRequest | null = null
  
  // 配置
  private timeout: number
  private reconnectDelay: number
  private maxReconnectAttempts: number

  constructor(config: SSEClientConfig = {}) {
    this.timeout = config.timeout ?? DEFAULT_TIMEOUT
    this.reconnectDelay = config.reconnectDelay ?? DEFAULT_RECONNECT_DELAY
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? MAX_RECONNECT_ATTEMPTS
  }

  /**
   * 注册事件回调
   */
  on(eventType: SSEEventType | 'all', callback: SSECallback): void {
    if (!this.callbacks.has(eventType)) {
      this.callbacks.set(eventType, [])
    }
    this.callbacks.get(eventType)!.push(callback)
  }

  /**
   * 移除事件回调
   */
  off(eventType: SSEEventType | 'all', callback: SSECallback): void {
    const callbacks = this.callbacks.get(eventType)
    if (callbacks) {
      const index = callbacks.indexOf(callback)
      if (index > -1) callbacks.splice(index, 1)
    }
  }

  /**
   * 触发事件
   */
  private emit(event: SSEEvent): void {
    // 触发特定类型回调
    const typeCallbacks = this.callbacks.get(event.type)
    typeCallbacks?.forEach(cb => cb(event))

    // 触发通用回调
    const allCallbacks = this.callbacks.get('all')
    allCallbacks?.forEach(cb => cb(event))
  }

  /**
   * 开始流式请求
   */
  async connect(request: ChatRequest): Promise<void> {
    this.disconnect()
    this.abortController = new AbortController()
    this.lastRequest = request
    this.reconnectAttempts = 0

    await this.doConnect(request)
  }

  /**
   * 执行连接
   */
  private async doConnect(request: ChatRequest): Promise<void> {
    // 设置超时
    this.startTimeout()

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify(request),
        signal: this.abortController?.signal
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) throw new Error('No response body')

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        
        // 重置超时（收到数据）
        this.resetTimeout()
        
        if (done) break

        buffer += decoder.decode(value, { stream: true })
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || ''

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            try {
              const rawEvent: RawSSEEvent = JSON.parse(line.slice(6))
              // 转换后端格式为前端格式
              const event: SSEEvent = {
                type: rawEvent.event_type as SSEEventType,
                data: rawEvent.data,
                timestamp: rawEvent.timestamp
              }
              this.emit(event)
              
              // 如果是完成事件，清除超时
              if (event.type === 'complete') {
                this.clearTimeout()
              }
            } catch (e) {
              console.error('Failed to parse SSE:', e)
            }
          }
        }
      }
    } catch (error) {
      this.clearTimeout()
      
      if ((error as Error).name === 'AbortError') {
        return
      }
      
      // 尝试重连
      if (this.reconnectAttempts < this.maxReconnectAttempts && this.lastRequest) {
        this.reconnectAttempts++
        this.emit({
          type: 'disconnect',
          data: { 
            error: String(error),
            reconnecting: true,
            attempt: this.reconnectAttempts
          },
          timestamp: Date.now()
        })
        
        // 延迟重连
        await new Promise(resolve => setTimeout(resolve, this.reconnectDelay))
        
        if (this.abortController && !this.abortController.signal.aborted) {
          await this.doConnect(this.lastRequest)
        }
      } else {
        this.emit({
          type: 'error',
          data: { error: String(error) },
          timestamp: Date.now()
        })
      }
    }
  }

  /**
   * 启动超时计时器
   */
  private startTimeout(): void {
    this.clearTimeout()
    this.timeoutId = setTimeout(() => {
      this.emit({
        type: 'timeout',
        data: { message: '请求超时' },
        timestamp: Date.now()
      })
      this.disconnect()
    }, this.timeout)
  }

  /**
   * 重置超时计时器
   */
  private resetTimeout(): void {
    if (this.timeoutId) {
      this.startTimeout()
    }
  }

  /**
   * 清除超时计时器
   */
  private clearTimeout(): void {
    if (this.timeoutId) {
      clearTimeout(this.timeoutId)
      this.timeoutId = null
    }
  }

  /**
   * 断开连接
   */
  disconnect(): void {
    this.clearTimeout()
    this.abortController?.abort()
    this.abortController = null
    this.lastRequest = null
  }

  /**
   * 手动重连
   */
  async reconnect(): Promise<void> {
    if (this.lastRequest) {
      this.reconnectAttempts = 0
      this.abortController = new AbortController()
      await this.doConnect(this.lastRequest)
    }
  }

  /**
   * 清除所有回调
   */
  clear(): void {
    this.callbacks.clear()
  }
}

/**
 * 创建 SSE 客户端
 */
export function createSSEClient(): SSEClient {
  return new SSEClient()
}
