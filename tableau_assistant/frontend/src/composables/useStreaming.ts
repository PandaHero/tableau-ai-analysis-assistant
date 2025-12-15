/**
 * 流式消息处理 Composable
 * 封装 SSE 客户端与 Chat Store 的交互
 */
import { ref, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useSessionStore } from '@/stores/session'
import { useTableauStore } from '@/stores/tableau'
import { SSEClient, type SSEEvent, type TokenData, type NodeData } from '@/api/streaming'
import type { ProcessingStage } from '@/types'

// 节点名称到处理阶段的映射
const NODE_TO_STAGE: Record<string, ProcessingStage> = {
  understanding: 'understanding',
  field_mapper: 'building',
  query_builder: 'building',
  execute: 'executing',
  insight: 'generating',
  replanner: 'replanning',
}

export function useStreaming() {
  const chatStore = useChatStore()
  const settingsStore = useSettingsStore()
  const sessionStore = useSessionStore()
  const tableauStore = useTableauStore()
  
  const client = ref<SSEClient | null>(null)
  const isConnected = ref(false)

  /**
   * 发送消息并处理流式响应
   */
  async function sendMessage(question: string) {
    // 创建 SSE 客户端
    client.value = new SSEClient({
      timeout: 60000,
      reconnectDelay: 5000,
      maxReconnectAttempts: 3,
    })

    // 准备流式响应（不创建消息，等收到第一个 token 时再创建）
    chatStore.prepareStreaming()
    isConnected.value = true

    // 注册事件处理
    client.value.on('token', handleToken)
    client.value.on('node_start', handleNodeStart)
    client.value.on('node_complete', handleNodeComplete)
    client.value.on('complete', handleComplete)
    client.value.on('error', handleError)
    client.value.on('timeout', handleTimeout)
    client.value.on('disconnect', handleDisconnect)

    try {
      // 获取数据源名称
      const datasourceName = settingsStore.datasourceName || 
        tableauStore.selectedDataSource?.name || ''

      // 连接并发送请求
      await client.value.connect({
        question,
        datasource_name: datasourceName,
        session_id: sessionStore.sessionId,
        analysis_depth: settingsStore.analysisDepth,
        language: settingsStore.language,
      })
    } catch (error) {
      handleError({
        type: 'error',
        data: { error: String(error) },
        timestamp: Date.now(),
      })
    }
  }

  /**
   * 处理 token 事件
   * 收到第一个 token 时会自动创建 AI 消息并添加到列表
   */
  function handleToken(event: SSEEvent) {
    const data = event.data as TokenData
    if (data?.token) {
      // 使用 appendToCurrentResponse，它会在第一次调用时创建消息
      chatStore.appendToCurrentResponse(data.token)
    }
  }

  /**
   * 处理节点开始事件
   */
  function handleNodeStart(event: SSEEvent) {
    const data = event.data as NodeData
    const stage = NODE_TO_STAGE[data?.node || '']
    if (stage) {
      chatStore.setProcessing(true, stage)
    }
  }

  /**
   * 处理节点完成事件
   */
  function handleNodeComplete(event: SSEEvent) {
    const data = event.data as NodeData
    // 可以在这里处理节点输出，如更新表格数据、洞察等
    console.log('Node complete:', data?.node, data?.output)
  }

  /**
   * 处理完成事件
   */
  function handleComplete(_event: SSEEvent) {
    chatStore.finishStreaming()
    chatStore.setProcessing(false)
    isConnected.value = false
    cleanup()
  }

  /**
   * 处理错误事件
   */
  function handleError(event: SSEEvent) {
    const data = event.data as { error?: string; message?: string }
    const errorMessage = data?.error || data?.message || '请求失败'
    
    chatStore.setError(errorMessage)
    chatStore.finishStreaming()
    chatStore.setProcessing(false)
    isConnected.value = false
    cleanup()
  }

  /**
   * 处理超时事件
   */
  function handleTimeout(_event: SSEEvent) {
    chatStore.setError('请求超时，请重试')
    chatStore.finishStreaming()
    chatStore.setProcessing(false)
    isConnected.value = false
    cleanup()
  }

  /**
   * 处理断开连接事件
   */
  function handleDisconnect(event: SSEEvent) {
    const data = event.data as { reconnecting?: boolean; attempt?: number }
    if (data?.reconnecting) {
      console.log(`正在重连... (${data.attempt})`)
    }
  }

  /**
   * 取消当前请求
   */
  function cancel() {
    client.value?.disconnect()
    chatStore.finishStreaming()
    chatStore.setProcessing(false)
    isConnected.value = false
    cleanup()
  }

  /**
   * 清理资源
   */
  function cleanup() {
    if (client.value) {
      client.value.clear()
      client.value = null
    }
  }

  // 组件卸载时清理
  onUnmounted(() => {
    cancel()
  })

  return {
    sendMessage,
    cancel,
    isConnected,
  }
}
