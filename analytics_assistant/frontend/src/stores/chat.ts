/**
 * Chat Store
 * 管理对话状态和页面切换
 * Requirements: 2.1, 2.2, 11.1
 */
import { defineStore } from 'pinia'
import { ref, computed } from 'vue'
import type { Message, UserMessage, AIMessage, ProcessingStage } from '@/types'

export type PageState = 'home' | 'chat'

export const useChatStore = defineStore('chat', () => {
  // 页面状态
  const currentPage = ref<PageState>('home')
  
  // 消息列表
  const messages = ref<Message[]>([])
  
  // 当前流式响应（正在生成的 AI 消息，未添加到列表前为 null）
  const currentResponse = ref<AIMessage | null>(null)
  
  // 流式响应是否已添加到消息列表
  const isStreamingMessageAdded = ref(false)
  
  // 处理状态
  const isProcessing = ref(false)
  const processingStage = ref<ProcessingStage | null>(null)
  
  // 错误状态
  const error = ref<string | null>(null)

  // 待发送的问题（由 HomeView 设置，AnalysisView 消费，避免路由切换时 SSE 被取消）
  const pendingQuery = ref<string | null>(null)

  // 计算属性
  const hasMessages = computed(() => messages.value.length > 0)
  const lastMessage = computed(() => messages.value[messages.value.length - 1])

  // 页面切换
  function goToChat() {
    currentPage.value = 'chat'
  }

  function goToHome() {
    currentPage.value = 'home'
    clearMessages()
    // 重置处理状态，确保返回首页后可以正常输入
    setProcessing(false)
  }

  // 消息管理
  function addUserMessage(content: string): UserMessage {
    const message: UserMessage = {
      id: generateId(),
      type: 'user',
      content,
      timestamp: Date.now()
    }
    messages.value.push(message)
    return message
  }

  function addAIMessage(message: Omit<AIMessage, 'id' | 'timestamp' | 'type'>): AIMessage {
    const aiMessage: AIMessage = {
      id: generateId(),
      type: 'ai',
      timestamp: Date.now(),
      ...message
    }
    messages.value.push(aiMessage)
    return aiMessage
  }

  /**
   * 追加内容到当前流式响应
   * 如果是第一次追加内容，会创建消息并添加到列表
   */
  function appendToCurrentResponse(content: string) {
    if (!currentResponse.value) {
      // 创建新的 AI 消息
      currentResponse.value = {
        id: generateId(),
        type: 'ai',
        content: content,
        timestamp: Date.now(),
        isStreaming: true
      }
      // 添加到消息列表
      messages.value.push(currentResponse.value)
      isStreamingMessageAdded.value = true
    } else {
      // 追加内容
      currentResponse.value.content = (currentResponse.value.content || '') + content
    }
  }

  /**
   * 更新当前流式响应的其他属性（非内容）
   * 如果还没有消息（纯数据响应，没有 token），自动创建一条空 AI 消息并加入列表
   */
  function updateCurrentResponse(partial: Partial<Omit<AIMessage, 'content'>>) {
    if (!currentResponse.value) {
      // 没有 token 时（如纯数据查询），创建空 AI 消息容纳 tableData / semanticSummary 等
      currentResponse.value = {
        id: generateId(),
        type: 'ai',
        content: '',
        timestamp: Date.now(),
        isStreaming: true,
      }
      messages.value.push(currentResponse.value)
      isStreamingMessageAdded.value = true
    }
    Object.assign(currentResponse.value, partial)
  }

  /**
   * 准备开始流式响应（不创建消息，只重置状态）
   */
  function prepareStreaming() {
    currentResponse.value = null
    isStreamingMessageAdded.value = false
  }

  /**
   * 完成流式响应
   */
  function finishStreaming() {
    if (currentResponse.value) {
      currentResponse.value.isStreaming = false
    }
    currentResponse.value = null
    isStreamingMessageAdded.value = false
  }

  function clearMessages() {
    messages.value = []
    currentResponse.value = null
    isStreamingMessageAdded.value = false
    error.value = null
    pendingQuery.value = null
  }

  // 处理状态
  function setProcessing(processing: boolean, stage?: ProcessingStage) {
    isProcessing.value = processing
    processingStage.value = stage || null
  }

  function setError(err: string | null) {
    error.value = err
    if (err) {
      processingStage.value = 'error'
    }
  }

  function setPendingQuery(query: string | null) {
    pendingQuery.value = query
  }

  function consumePendingQuery(): string | null {
    const q = pendingQuery.value
    pendingQuery.value = null
    return q
  }

  // 发送消息（核心流程）
  async function sendMessage(content: string) {
    if (!content.trim() || isProcessing.value) return

    // 添加用户消息
    addUserMessage(content)
    
    // 切换到对话页面
    if (currentPage.value === 'home') {
      goToChat()
    }

    // 开始处理
    setProcessing(true, 'understanding')
    setError(null)

    // 注意：实际的 API 调用在 useStreaming composable 中处理
    // 这里只负责状态管理
  }

  return {
    // 状态
    currentPage,
    messages,
    currentResponse,
    isProcessing,
    processingStage,
    error,
    pendingQuery,
    
    // 计算属性
    hasMessages,
    lastMessage,
    
    // 页面切换
    goToChat,
    goToHome,
    
    // 消息管理
    addUserMessage,
    addAIMessage,
    appendToCurrentResponse,
    updateCurrentResponse,
    prepareStreaming,
    finishStreaming,
    clearMessages,
    
    // 处理状态
    setProcessing,
    setError,
    sendMessage,

    // pendingQuery
    setPendingQuery,
    consumePendingQuery,
  }
})

// 生成唯一 ID
function generateId(): string {
  return `${Date.now()}-${Math.random().toString(36).substr(2, 9)}`
}
