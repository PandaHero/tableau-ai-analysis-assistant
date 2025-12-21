/**
 * 流式消息处理 Composable
 * 封装 SSE 客户端与 Chat Store 的交互
 */
import { ref, onUnmounted } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useSessionStore } from '@/stores/session'
import { useTableauStore } from '@/stores/tableau'
import { SSEClient, type SSEEvent, type NodeData } from '@/api/streaming'
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
      
      // 获取 Tableau 环境信息（支持多环境）
      const tableauDomain = tableauStore.tableauDomain
      const tableauSite = tableauStore.tableauSite
      const tableauContext = tableauStore.tableauContext
      const datasourceConnectionInfo = tableauStore.datasourceConnectionInfo
      
      console.log('useStreaming - Tableau环境:', { 
        tableauDomain, 
        tableauSite,
        tableauContext,
        datasourceConnectionInfo,
        isInTableau: tableauStore.isInTableau 
      })

      // 连接并发送请求
      await client.value.connect({
        question,
        datasource_name: datasourceName,
        session_id: sessionStore.sessionId,
        analysis_depth: settingsStore.analysisDepth,
        language: settingsStore.language,
        // Tableau 环境信息
        tableau_domain: tableauDomain,
        tableau_site: tableauSite,
        tableau_context: tableauContext,
        datasource_connection_info: datasourceConnectionInfo,
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
   * 
   * 后端发送格式: { node, content, output }
   * content 字段包含 token 内容
   * 
   * 现在所有节点都会输出用户友好的消息，直接显示给用户
   */
  function handleToken(event: SSEEvent) {
    const data = event.data as { content?: string; node?: string }
    if (data?.content) {
      chatStore.appendToCurrentResponse(data.content)
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
   * 根据节点类型更新消息的不同属性
   */
  function handleNodeComplete(event: SSEEvent) {
    const data = event.data as NodeData
    if (!data?.node) return
    
    const output = data.output as Record<string, unknown> | undefined
    
    // 根据节点类型处理输出
    switch (data.node) {
      case 'execute':
        // 执行节点完成，更新表格数据
        if (output?.data) {
          // 转换列定义，确保 type 是有效的枚举值
          const rawColumns = (output.columns as Array<{ key: string; label: string; type?: string }>) || []
          const columns = rawColumns.map(col => ({
            key: col.key,
            label: col.label,
            type: (['string', 'number', 'date'].includes(col.type || '') 
              ? col.type 
              : 'string') as 'string' | 'number' | 'date'
          }))
          
          chatStore.updateCurrentResponse({
            data: {
              columns,
              rows: (output.data as Record<string, unknown>[]) || [],
              totalCount: (output.row_count as number) || 0
            }
          })
        }
        break
        
      case 'insight':
        // 洞察节点完成，更新洞察列表
        if (output?.insights) {
          const insights = (output.insights as Array<{
            type?: string
            title?: string
            finding?: string
            description?: string
            confidence?: number
            priority?: number
          }>).map((item, index) => ({
            id: `insight-${Date.now()}-${index}`,
            type: (item.type || 'discovery') as 'discovery' | 'anomaly' | 'suggestion',
            title: item.title || item.finding || '发现',
            description: item.description || item.finding || '',
            confidence: item.confidence || 80,
            priority: item.priority || (100 - index)
          }))
          chatStore.updateCurrentResponse({ insights })
        }
        break
        
      case 'replanner':
        // 重规划节点完成，更新推荐问题
        if (output?.suggested_questions) {
          chatStore.updateCurrentResponse({
            suggestions: output.suggested_questions as string[]
          })
        }
        break
    }
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
