import type { ChatRequest } from './client'
import { API_BASE_URL } from './config'
import { getTableauUsername } from './tableauUser'

const DEFAULT_TIMEOUT = 60000
const DEFAULT_RECONNECT_DELAY = 5000
const MAX_RECONNECT_ATTEMPTS = 3

export type SSEEventType =
  | 'token'
  | 'thinking_token'
  | 'thinking'
  | 'data'
  | 'chart'
  | 'suggestions'
  | 'parse_result'
  | 'clarification'
  | 'node_start'
  | 'node_complete'
  | 'complete'
  | 'error'
  | 'timeout'
  | 'disconnect'
  | 'heartbeat'

export interface SSEEvent {
  type: SSEEventType
  data: unknown
  timestamp: number
}

export interface NodeData {
  node: string
  output?: unknown
}

export interface SSEClientConfig {
  timeout?: number
  reconnectDelay?: number
  maxReconnectAttempts?: number
}

export type SSECallback = (event: SSEEvent) => void

export class SSEClient {
  private abortController: AbortController | null = null
  private callbacks: Map<SSEEventType | 'all', SSECallback[]> = new Map()
  private timeoutId: ReturnType<typeof setTimeout> | null = null
  private reconnectAttempts = 0
  private lastRequest: ChatRequest | null = null
  private timeout: number
  private reconnectDelay: number
  private maxReconnectAttempts: number

  constructor(config: SSEClientConfig = {}) {
    this.timeout = config.timeout ?? DEFAULT_TIMEOUT
    this.reconnectDelay = config.reconnectDelay ?? DEFAULT_RECONNECT_DELAY
    this.maxReconnectAttempts = config.maxReconnectAttempts ?? MAX_RECONNECT_ATTEMPTS
  }

  on(eventType: SSEEventType | 'all', callback: SSECallback): void {
    if (!this.callbacks.has(eventType)) {
      this.callbacks.set(eventType, [])
    }
    this.callbacks.get(eventType)?.push(callback)
  }

  off(eventType: SSEEventType | 'all', callback: SSECallback): void {
    const callbacks = this.callbacks.get(eventType)
    if (!callbacks) {
      return
    }

    const index = callbacks.indexOf(callback)
    if (index >= 0) {
      callbacks.splice(index, 1)
    }
  }

  async connect(request: ChatRequest): Promise<void> {
    this.disconnect()
    this.abortController = new AbortController()
    this.lastRequest = request
    this.reconnectAttempts = 0
    await this.doConnect(request)
  }

  disconnect(): void {
    this.clearTimeout()
    this.abortController?.abort()
    this.abortController = null
    this.lastRequest = null
  }

  async reconnect(): Promise<void> {
    if (!this.lastRequest) {
      return
    }

    this.reconnectAttempts = 0
    this.abortController = new AbortController()
    await this.doConnect(this.lastRequest)
  }

  clear(): void {
    this.callbacks.clear()
  }

  private emit(event: SSEEvent): void {
    this.callbacks.get(event.type)?.forEach((callback) => callback(event))
    this.callbacks.get('all')?.forEach((callback) => callback(event))
  }

  private async doConnect(request: ChatRequest): Promise<void> {
    this.startTimeout()

    try {
      const response = await fetch(`${API_BASE_URL}/api/chat/stream`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json',
          'X-Tableau-Username': getTableauUsername(),
        },
        body: JSON.stringify(request),
        signal: this.abortController?.signal,
      })

      if (!response.ok) {
        throw new Error(`HTTP ${response.status}`)
      }

      if (!response.body) {
        throw new Error('No response body')
      }

      const reader = response.body.getReader()
      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        this.resetTimeout()

        if (done) {
          break
        }

        buffer += decoder.decode(value, { stream: true })
        const chunks = buffer.split('\n\n')
        buffer = chunks.pop() || ''

        for (const chunk of chunks) {
          if (!chunk.startsWith('data: ')) {
            continue
          }

          try {
            const payload = JSON.parse(chunk.slice(6))
            this.emit({
              type: payload.type as SSEEventType,
              data: payload,
              timestamp: Date.now(),
            })

            if (payload.type === 'complete') {
              this.clearTimeout()
            }
          } catch {
            continue
          }
        }
      }
    } catch (error) {
      this.clearTimeout()

      if ((error as Error).name === 'AbortError') {
        return
      }

      if (this.reconnectAttempts < this.maxReconnectAttempts && this.lastRequest) {
        this.reconnectAttempts += 1
        this.emit({
          type: 'disconnect',
          data: {
            reconnecting: true,
            attempt: this.reconnectAttempts,
            error: String(error),
          },
          timestamp: Date.now(),
        })

        await new Promise((resolve) => setTimeout(resolve, this.reconnectDelay))
        if (this.abortController && !this.abortController.signal.aborted) {
          await this.doConnect(this.lastRequest)
        }
        return
      }

      this.emit({
        type: 'error',
        data: { error: String(error) },
        timestamp: Date.now(),
      })
    }
  }

  private startTimeout(): void {
    this.clearTimeout()
    this.timeoutId = setTimeout(() => {
      this.emit({
        type: 'timeout',
        data: { message: '请求超时' },
        timestamp: Date.now(),
      })
      this.disconnect()
    }, this.timeout)
  }

  private resetTimeout(): void {
    if (this.timeoutId) {
      this.startTimeout()
    }
  }

  private clearTimeout(): void {
    if (!this.timeoutId) {
      return
    }

    clearTimeout(this.timeoutId)
    this.timeoutId = null
  }
}

export function createSSEClient(): SSEClient {
  return new SSEClient()
}
