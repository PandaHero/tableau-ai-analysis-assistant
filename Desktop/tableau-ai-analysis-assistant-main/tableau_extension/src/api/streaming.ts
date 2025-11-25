/**
 * SSE 流式客户端
 * 
 * 用于接收后端的 Server-Sent Events (SSE) 流式数据
 */

// @ts-ignore - Vite env variables
const API_BASE_URL = import.meta.env?.VITE_API_BASE_URL

/**
 * 事件类型枚举
 */
export enum EventType {
  // Token级流式输出
  TOKEN = 'token',
  
  // Agent进度
  AGENT_START = 'agent_start',
  AGENT_COMPLETE = 'agent_complete',
  AGENT_ERROR = 'agent_error',
  
  // 工具调用进度
  TOOL_START = 'tool_start',
  TOOL_COMPLETE = 'tool_complete',
  TOOL_ERROR = 'tool_error',
  
  // 查询执行进度
  QUERY_START = 'query_start',
  QUERY_COMPLETE = 'query_complete',
  QUERY_ERROR = 'query_error',
  
  // 整体进度
  WORKFLOW_START = 'workflow_start',
  WORKFLOW_COMPLETE = 'workflow_complete',
  WORKFLOW_ERROR = 'workflow_error',
  
  // 其他
  PROGRESS = 'progress',
  LOG = 'log'
}

/**
 * 流式事件接口
 */
export interface StreamEvent {
  type: EventType
  data: any
  timestamp: number
}

/**
 * Token事件数据
 */
export interface TokenEventData {
  token: string
  agent?: string
}

/**
 * Agent事件数据
 */
export interface AgentEventData {
  agent: string
  run_id?: string
  output?: any
  error?: string
  timestamp: number
}

/**
 * 工具事件数据
 */
export interface ToolEventData {
  tool: string
  input?: any
  output?: any
  error?: string
  timestamp: number
}

/**
 * 工作流事件数据
 */
export interface WorkflowEventData {
  question?: string
  duration?: number
  error?: string
  timestamp: number
}

/**
 * 事件处理器类型
 */
export type EventHandler = (event: StreamEvent) => void

/**
 * 聊天请求参数
 */
export interface ChatRequest {
  question: string
  datasource_luid: string
  user_id: string
  session_id?: string
  boost_question?: boolean
}

/**
 * SSE 流式客户端类
 */
export class StreamingClient {
  private eventSource: EventSource | null = null
  private handlers: Map<EventType | 'all', EventHandler[]> = new Map()

  /**
   * 开始流式聊天
   */
  async startChat(request: ChatRequest): Promise<void> {
    // 关闭现有连接
    this.close()

    // 创建 EventSource
    // 注意：EventSource 不支持 POST，所以我们需要使用 fetch + ReadableStream
    await this.streamWithFetch(request)
  }

  /**
   * 使用 fetch API 实现 SSE 流式请求
   */
  private async streamWithFetch(request: ChatRequest): Promise<void> {
    try {
      const response = await fetch(`${API_BASE_URL}/api/stream/chat`, {
        method: 'POST',
        headers: {
          'Content-Type': 'application/json'
        },
        body: JSON.stringify(request)
      })

      if (!response.ok) {
        throw new Error(`HTTP error! status: ${response.status}`)
      }

      const reader = response.body?.getReader()
      if (!reader) {
        throw new Error('Response body is not readable')
      }

      const decoder = new TextDecoder()
      let buffer = ''

      while (true) {
        const { done, value } = await reader.read()
        
        if (done) {
          break
        }

        // 解码数据
        buffer += decoder.decode(value, { stream: true })

        // 处理完整的 SSE 消息
        const lines = buffer.split('\n\n')
        buffer = lines.pop() || '' // 保留不完整的消息

        for (const line of lines) {
          if (line.startsWith('data: ')) {
            const jsonStr = line.substring(6) // 去掉 "data: "
            try {
              const event: StreamEvent = JSON.parse(jsonStr)
              this.handleEvent(event)
            } catch (error) {
              console.error('Failed to parse SSE event:', error, jsonStr)
            }
          }
        }
      }
    } catch (error) {
      console.error('Streaming error:', error)
      // 触发错误事件
      this.handleEvent({
        type: EventType.WORKFLOW_ERROR,
        data: { error: String(error) },
        timestamp: Date.now() / 1000
      })
    }
  }

  /**
   * 注册事件处理器
   */
  on(eventType: EventType | 'all', handler: EventHandler): void {
    if (!this.handlers.has(eventType)) {
      this.handlers.set(eventType, [])
    }
    this.handlers.get(eventType)!.push(handler)
  }

  /**
   * 移除事件处理器
   */
  off(eventType: EventType | 'all', handler: EventHandler): void {
    const handlers = this.handlers.get(eventType)
    if (handlers) {
      const index = handlers.indexOf(handler)
      if (index > -1) {
        handlers.splice(index, 1)
      }
    }
  }

  /**
   * 处理事件
   */
  private handleEvent(event: StreamEvent): void {
    // 触发特定类型的处理器
    const typeHandlers = this.handlers.get(event.type as EventType)
    if (typeHandlers) {
      typeHandlers.forEach(handler => handler(event))
    }

    // 触发通用处理器
    const allHandlers = this.handlers.get('all')
    if (allHandlers) {
      allHandlers.forEach(handler => handler(event))
    }
  }

  /**
   * 关闭连接
   */
  close(): void {
    if (this.eventSource) {
      this.eventSource.close()
      this.eventSource = null
    }
  }

  /**
   * 清除所有事件处理器
   */
  clearHandlers(): void {
    this.handlers.clear()
  }
}

/**
 * 创建流式客户端实例
 */
export function createStreamingClient(): StreamingClient {
  return new StreamingClient()
}
