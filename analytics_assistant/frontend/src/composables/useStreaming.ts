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

// 语义解析摘要类型
interface SemanticSummary {
  restated_question: string
  measures: string[]
  dimensions: string[]
  filters: string[]
}

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
    console.log('[useStreaming] 开始发送消息:', question)
    
    // 创建 SSE 客户端
    client.value = new SSEClient({
      timeout: 180000,  // 增加到 180 秒,匹配后端超时
      reconnectDelay: 5000,
      maxReconnectAttempts: 3,
    })

    // 准备流式响应（不创建消息，等收到第一个 token 时再创建）
    chatStore.prepareStreaming()
    isConnected.value = true

    // 注册事件处理
    console.log('[useStreaming] 注册事件处理器')
    client.value.on('token', handleToken)
    client.value.on('thinking_token', handleThinkingToken)
    client.value.on('thinking', handleThinking)
    client.value.on('node_start', handleNodeStart)
    client.value.on('node_complete', handleNodeComplete)
    client.value.on('parse_result', handleParseResult)
    client.value.on('suggestions', handleSuggestions)
    client.value.on('data', handleData)
    client.value.on('clarification', handleClarification)
    client.value.on('complete', handleComplete)
    client.value.on('error', handleError)
    client.value.on('timeout', handleTimeout)
    client.value.on('disconnect', handleDisconnect)

    try {
      // 获取数据源名称
      const datasourceName = settingsStore.datasourceName || 
        tableauStore.selectedDataSource?.name || ''

      console.log('[useStreaming] 数据源名称:', datasourceName)

      // 数据源为空时拦截，避免后端报错
      if (!datasourceName) {
        handleError({
          type: 'error',
          data: { error: '请先在设置中选择数据源' },
          timestamp: Date.now(),
        })
        return
      }

      // 构建消息数组（转换前端格式到后端格式）
      const messages = chatStore.messages.map(msg => {
        const role: 'user' | 'assistant' | 'system' = 
          msg.type === 'user' ? 'user' : 
          msg.type === 'ai' ? 'assistant' : 
          'system'
        return {
          role,
          content: msg.content
        }
      })

      console.log('[useStreaming] 消息数组:', messages.length, '条')
      console.log('[useStreaming] 开始连接 SSE...')

      // 连接并发送请求
      await client.value.connect({
        messages,
        datasource_name: datasourceName,
        session_id: sessionStore.sessionId,
        analysis_depth: settingsStore.analysisDepth,
        language: settingsStore.language,
      })
      
      console.log('[useStreaming] SSE 连接已建立')
    } catch (error) {
      console.error('[useStreaming] 连接失败:', error)
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
   * 过滤掉结构化 JSON token（语义解析产生的 JSON 碎片不应展示给用户）
   */
  function handleToken(event: SSEEvent) {
    // event.data 就是后端发送的完整事件对象: { type: "token", content: "..." }
    const data = event.data as any
    const token = data?.content
    if (!token) return

    // 过滤纯 JSON 结构 token（如 `{`, `}`, `"key":`, `[`, `]` 等裸 JSON 片段）
    // 正常自然语言 token 不会全部由 JSON 结构符号组成
    const isJsonFragment = /^[\s\n]*[{}\[\],":]*[\s\n]*$/.test(token)
    if (isJsonFragment) {
      console.debug('[Token] 跳过 JSON 碎片:', JSON.stringify(token))
      return
    }

    console.log('[Token]', token)
    chatStore.appendToCurrentResponse(token)
  }

  /**
   * 处理 thinking token 事件（R1 模型的思考过程）
   */
  function handleThinkingToken(event: SSEEvent) {
    // event.data 就是后端发送的完整事件对象: { type: "thinking_token", content: "..." }
    const data = event.data as any
    const thinking = data?.content
    if (thinking) {
      console.log('[Thinking Token]', thinking)
      // 可以在这里处理思考过程的显示
    }
  }

  /**
   * 处理 thinking 事件（处理阶段状态）
   */
  function handleThinking(event: SSEEvent) {
    // event.data 就是后端发送的完整事件对象: { type: "thinking", stage: "...", name: "...", status: "..." }
    const data = event.data as any
    const stage = data?.stage as ProcessingStage
    const status = data?.status
    const name = data?.name
    
    console.log('[Thinking]', { stage, status, name })
    
    if (stage && status === 'running') {
      chatStore.setProcessing(true, stage)
    } else if (stage && status === 'completed') {
      // 阶段完成，可以在这里更新 UI
      console.log('[Stage Complete]', stage, name)
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
   * 处理语义解析结果事件（feedback_learner 完成后触发）
   */
  function handleParseResult(event: SSEEvent) {
    const data = event.data as any
    if (!data?.success) return
    const summary = data?.summary as SemanticSummary | undefined
    if (!summary) return
    console.log('[ParseResult] 语义解析摘要:', summary)
    // 将解析摘要更新到当前 AI 消息
    chatStore.updateCurrentResponse({ semanticSummary: summary })
  }

  /**
   * 处理推荐问题事件
   */
  function handleSuggestions(event: SSEEvent) {
    const data = event.data as any
    const questions: string[] = data?.questions || []
    if (questions.length === 0) return
    console.log('[Suggestions]', questions)
    chatStore.updateCurrentResponse({ suggestions: questions })
  }

  /**
   * 处理数据表格事件（有真实查询结果时）
   */
  function handleData(event: SSEEvent) {
    const data = event.data as any
    const tableData = data?.tableData
    if (!tableData) return
    console.log('[Data] 收到表格数据')
    chatStore.updateCurrentResponse({ tableData })
  }

  /**
   * 处理需要用户澄清事件
   */
  function handleClarification(event: SSEEvent) {
    const data = event.data as any
    const question = data?.question || ''
    const options: string[] = data?.options || []
    console.log('[Clarification] 需要澄清:', question, options)
    // 将澄清请求作为 AI 消息内容显示
    const content = options.length > 0
      ? `${question}\n\n${options.map((o: string, i: number) => `${i + 1}. ${o}`).join('\n')}`
      : question
    chatStore.appendToCurrentResponse(content)
    chatStore.finishStreaming()
    chatStore.setProcessing(false)
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
