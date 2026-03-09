<template>
  <div class="sse-debug">
    <h1>SSE 流式输出调试工具</h1>
    
    <div class="section">
      <h2>1. 测试 Chat Store 响应式</h2>
      <button @click="testChatStore" class="btn">测试 appendToCurrentResponse</button>
      <div class="result">
        <p>消息数量: {{ chatStore.messages.length }}</p>
        <p>currentResponse 存在: {{ !!chatStore.currentResponse }}</p>
        <p>currentResponse 内容长度: {{ chatStore.currentResponse?.content?.length || 0 }}</p>
        <div v-if="chatStore.currentResponse" class="message-preview">
          <strong>当前消息内容:</strong>
          <pre>{{ chatStore.currentResponse.content }}</pre>
        </div>
      </div>
    </div>
    
    <div class="section">
      <h2>2. 测试 SSE 连接</h2>
      <input v-model="testQuestion" placeholder="输入测试问题" class="input" />
      <button @click="testSSE" :disabled="isConnecting" class="btn">
        {{ isConnecting ? '连接中...' : '测试 SSE 连接' }}
      </button>
      <button @click="clearLogs" class="btn btn-secondary">清除日志</button>
      
      <div class="logs">
        <h3>事件日志:</h3>
        <div v-for="(log, i) in eventLogs" :key="i" class="log-item" :class="log.type">
          <span class="log-time">{{ log.time }}</span>
          <span class="log-type">{{ log.type }}</span>
          <span class="log-message">{{ log.message }}</span>
        </div>
      </div>
    </div>
    
    <div class="section">
      <h2>3. 消息列表预览</h2>
      <div class="messages">
        <div v-for="msg in chatStore.messages" :key="msg.id" class="message-item">
          <div class="message-header">
            <span class="message-type">{{ msg.type }}</span>
            <span class="message-id">{{ msg.id }}</span>
            <span v-if="msg.type === 'ai' && msg.isStreaming" class="streaming-badge">流式中</span>
          </div>
          <div class="message-content">{{ msg.content }}</div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useStreaming } from '@/composables/useStreaming'

const chatStore = useChatStore()
const { sendMessage, isConnected } = useStreaming()

const testQuestion = ref('显示销售额前10的产品')
const isConnecting = ref(false)

interface EventLog {
  time: string
  type: string
  message: string
}

const eventLogs = ref<EventLog[]>([])

function addLog(type: string, message: string) {
  const now = new Date()
  const time = `${now.getHours()}:${String(now.getMinutes()).padStart(2, '0')}:${String(now.getSeconds()).padStart(2, '0')}.${String(now.getMilliseconds()).padStart(3, '0')}`
  
  eventLogs.value.push({ time, type, message })
  
  // 限制日志数量
  if (eventLogs.value.length > 100) {
    eventLogs.value.shift()
  }
}

function testChatStore() {
  addLog('info', '开始测试 Chat Store')
  
  // 准备流式响应
  chatStore.prepareStreaming()
  addLog('info', 'prepareStreaming 完成')
  
  // 追加内容
  chatStore.appendToCurrentResponse('测试内容1')
  addLog('success', '追加内容1')
  
  setTimeout(() => {
    chatStore.appendToCurrentResponse('测试内容2')
    addLog('success', '追加内容2')
  }, 500)
  
  setTimeout(() => {
    chatStore.appendToCurrentResponse('测试内容3')
    addLog('success', '追加内容3')
    
    // 完成流式响应
    chatStore.finishStreaming()
    addLog('info', 'finishStreaming 完成')
  }, 1000)
}

async function testSSE() {
  if (!testQuestion.value.trim()) {
    addLog('error', '请输入测试问题')
    return
  }
  
  isConnecting.value = true
  addLog('info', `开始 SSE 连接: ${testQuestion.value}`)
  
  try {
    // 添加用户消息
    chatStore.addUserMessage(testQuestion.value)
    addLog('info', '用户消息已添加')
    
    // 发送消息
    await sendMessage(testQuestion.value)
    addLog('success', 'SSE 连接已建立')
  } catch (error) {
    addLog('error', `SSE 连接失败: ${error}`)
  } finally {
    isConnecting.value = false
  }
}

function clearLogs() {
  eventLogs.value = []
}

// 监听 chatStore 变化
chatStore.$subscribe((mutation, state) => {
  addLog('store', `Store 更新: ${mutation.type}`)
})
</script>

<style scoped>
.sse-debug {
  padding: 20px;
  max-width: 1200px;
  margin: 0 auto;
}

h1 {
  color: #1F77B4;
  margin-bottom: 30px;
}

.section {
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 8px;
  padding: 20px;
  margin-bottom: 20px;
}

h2 {
  font-size: 18px;
  margin-bottom: 15px;
  color: #2d3748;
}

h3 {
  font-size: 14px;
  margin: 15px 0 10px;
  color: #4a5568;
}

.btn {
  background: #1F77B4;
  color: white;
  border: none;
  padding: 10px 20px;
  border-radius: 4px;
  cursor: pointer;
  margin-right: 10px;
  font-size: 14px;
}

.btn:hover {
  background: #1557a0;
}

.btn:disabled {
  background: #cbd5e0;
  cursor: not-allowed;
}

.btn-secondary {
  background: #718096;
}

.btn-secondary:hover {
  background: #4a5568;
}

.input {
  width: 100%;
  padding: 10px;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  margin-bottom: 10px;
  font-size: 14px;
}

.result {
  margin-top: 15px;
  padding: 15px;
  background: #f7fafc;
  border-radius: 4px;
}

.result p {
  margin: 5px 0;
  font-size: 14px;
}

.message-preview {
  margin-top: 10px;
  padding: 10px;
  background: white;
  border: 1px solid #e2e8f0;
  border-radius: 4px;
}

.message-preview pre {
  margin: 5px 0 0;
  white-space: pre-wrap;
  word-break: break-word;
  font-size: 13px;
}

.logs {
  margin-top: 15px;
  max-height: 400px;
  overflow-y: auto;
  background: #1e1e1e;
  border-radius: 4px;
  padding: 10px;
}

.log-item {
  font-family: 'SF Mono', Monaco, Consolas, monospace;
  font-size: 12px;
  padding: 4px 0;
  display: flex;
  gap: 10px;
}

.log-time {
  color: #6a9955;
}

.log-type {
  font-weight: bold;
  min-width: 60px;
}

.log-item.info .log-type {
  color: #4ec9b0;
}

.log-item.success .log-type {
  color: #b5cea8;
}

.log-item.error .log-type {
  color: #f48771;
}

.log-item.store .log-type {
  color: #dcdcaa;
}

.log-message {
  color: #d4d4d4;
}

.messages {
  max-height: 400px;
  overflow-y: auto;
}

.message-item {
  border: 1px solid #e2e8f0;
  border-radius: 4px;
  padding: 10px;
  margin-bottom: 10px;
  background: #f7fafc;
}

.message-header {
  display: flex;
  gap: 10px;
  align-items: center;
  margin-bottom: 8px;
  font-size: 12px;
}

.message-type {
  background: #1F77B4;
  color: white;
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: bold;
}

.message-id {
  color: #718096;
  font-family: monospace;
}

.streaming-badge {
  background: #48bb78;
  color: white;
  padding: 2px 8px;
  border-radius: 3px;
  font-weight: bold;
  animation: pulse 1.5s infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.6; }
}

.message-content {
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
  word-break: break-word;
}
</style>
