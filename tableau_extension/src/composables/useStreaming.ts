/**
 * 流式输出 Composable
 * 
 * 管理 SSE 流式输出的状态和逻辑
 */

import { ref, computed, onUnmounted } from 'vue'
import {
  createStreamingClient,
  EventType,
  type StreamEvent,
  type ChatRequest,
  type TokenEventData,
  type AgentEventData,
  type WorkflowEventData
} from '@/api/streaming'

/**
 * Agent 进度状态
 */
export interface AgentProgress {
  name: string
  status: 'running' | 'complete' | 'error'
  startTime?: number
  endTime?: number
  error?: string
}

/**
 * 流式输出状态
 */
export interface StreamingState {
  isStreaming: boolean
  currentMessage: string
  agentProgress: AgentProgress[]
  currentAgent: string | null
  error: string | null
  events: StreamEvent[]
}

/**
 * 使用流式输出
 */
export function useStreaming() {
  // 状态
  const state = ref<StreamingState>({
    isStreaming: false,
    currentMessage: '',
    agentProgress: [],
    currentAgent: null,
    error: null,
    events: []
  })

  // 客户端实例
  const client = createStreamingClient()

  // 计算属性
  const isStreaming = computed(() => state.value.isStreaming)
  const currentMessage = computed(() => state.value.currentMessage)
  const agentProgress = computed(() => state.value.agentProgress)
  const hasError = computed(() => state.value.error !== null)

  /**
   * 开始流式聊天
   */
  async function startChat(request: ChatRequest) {
    // 重置状态
    state.value = {
      isStreaming: true,
      currentMessage: '',
      agentProgress: [],
      currentAgent: null,
      error: null,
      events: []
    }

    // 注册事件处理器
    setupEventHandlers()

    // 开始流式请求
    try {
      await client.startChat(request)
    } catch (error) {
      state.value.error = String(error)
      state.value.isStreaming = false
    }
  }

  /**
   * 设置事件处理器
   */
  function setupEventHandlers() {
    // Token 级流式输出
    client.on(EventType.TOKEN, (event: StreamEvent) => {
      const data = event.data as TokenEventData
      state.value.currentMessage += data.token
    })

    // Agent 开始
    client.on(EventType.AGENT_START, (event: StreamEvent) => {
      const data = event.data as AgentEventData
      state.value.currentAgent = data.agent
      
      // 添加到进度列表
      state.value.agentProgress.push({
        name: data.agent,
        status: 'running',
        startTime: data.timestamp
      })
    })

    // Agent 完成
    client.on(EventType.AGENT_COMPLETE, (event: StreamEvent) => {
      const data = event.data as AgentEventData
      
      // 更新进度状态
      const progress = state.value.agentProgress.find(p => p.name === data.agent)
      if (progress) {
        progress.status = 'complete'
        progress.endTime = data.timestamp
      }
      
      state.value.currentAgent = null
    })

    // Agent 错误
    client.on(EventType.AGENT_ERROR, (event: StreamEvent) => {
      const data = event.data as AgentEventData
      
      // 更新进度状态
      const progress = state.value.agentProgress.find(p => p.name === data.agent)
      if (progress) {
        progress.status = 'error'
        progress.error = data.error
        progress.endTime = data.timestamp
      }
      
      state.value.currentAgent = null
    })

    // 工作流开始
    client.on(EventType.WORKFLOW_START, (event: StreamEvent) => {
      const data = event.data as WorkflowEventData
      console.log('Workflow started:', data.question)
    })

    // 工作流完成
    client.on(EventType.WORKFLOW_COMPLETE, (event: StreamEvent) => {
      const data = event.data as WorkflowEventData
      state.value.isStreaming = false
      console.log('Workflow completed in', data.duration, 'seconds')
    })

    // 工作流错误
    client.on(EventType.WORKFLOW_ERROR, (event: StreamEvent) => {
      const data = event.data as WorkflowEventData
      state.value.error = data.error || 'Unknown error'
      state.value.isStreaming = false
    })

    // 记录所有事件（用于调试）
    client.on('all', (event: StreamEvent) => {
      state.value.events.push(event)
    })
  }

  /**
   * 停止流式输出
   */
  function stopStreaming() {
    client.close()
    state.value.isStreaming = false
  }

  /**
   * 清除消息
   */
  function clearMessage() {
    state.value.currentMessage = ''
  }

  /**
   * 清除错误
   */
  function clearError() {
    state.value.error = null
  }

  // 组件卸载时清理
  onUnmounted(() => {
    client.close()
    client.clearHandlers()
  })

  return {
    // 状态
    state,
    isStreaming,
    currentMessage,
    agentProgress,
    hasError,
    
    // 方法
    startChat,
    stopStreaming,
    clearMessage,
    clearError
  }
}
