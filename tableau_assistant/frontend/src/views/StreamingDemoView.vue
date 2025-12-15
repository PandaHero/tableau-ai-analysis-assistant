<template>
  <div class="streaming-demo">
    <h1>流式输出演示</h1>
    
    <div class="input-section">
      <div class="form-group">
        <label>问题：</label>
        <input v-model="question" type="text" placeholder="输入分析问题" :disabled="isStreaming" />
      </div>
      
      <div class="form-group">
        <label>数据源名称：</label>
        <input v-model="datasourceName" type="text" placeholder="数据源名称" :disabled="isStreaming" />
      </div>
      
      <div class="form-group">
        <label>Session ID：</label>
        <input v-model="sessionId" type="text" placeholder="Session ID" :disabled="isStreaming" />
      </div>
      
      <div class="button-group">
        <button @click="handleStart" :disabled="isStreaming || !canSubmit" class="btn-primary">
          {{ isStreaming ? '处理中...' : '开始分析' }}
        </button>
        <button v-if="isStreaming" @click="handleStop" class="btn-secondary">停止</button>
        <button v-if="currentMessage" @click="handleClear" :disabled="isStreaming" class="btn-secondary">清除</button>
      </div>
    </div>
    
    <StreamingProgress :is-streaming="isStreaming" :current-node="state.currentNode" />
    
    <div v-if="currentMessage" class="result-section">
      <h3>结果：</h3>
      <pre>{{ currentMessage }}</pre>
    </div>
    
    <div v-if="state.error" class="error-section">
      <p>错误：{{ state.error }}</p>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useStreaming } from '@/composables/useStreaming'
import { useChatStore } from '@/stores/chat'
import StreamingProgress from '@/components/StreamingProgress.vue'

const { sendMessage, cancel, isConnected } = useStreaming()
const chatStore = useChatStore()

// 兼容旧模板的状态
const state = computed(() => ({
  currentNode: chatStore.processingStage,
  error: chatStore.error
}))
const isStreaming = isConnected
const currentMessage = computed(() => chatStore.currentResponse?.content || '')

const question = ref('')
const datasourceName = ref('')
const sessionId = ref('')

const canSubmit = computed(() => {
  return question.value.trim() !== '' && datasourceName.value.trim() !== '' && sessionId.value.trim() !== ''
})

async function handleStart() {
  // 先添加用户消息
  chatStore.addUserMessage(question.value)
  chatStore.setProcessing(true, 'understanding')
  // 发送流式请求
  await sendMessage(question.value)
}

function handleStop() {
  cancel()
}

function handleClear() {
  chatStore.clearMessages()
}
</script>

<style scoped>
.streaming-demo {
  max-width: 800px;
  margin: 0 auto;
  padding: 24px;
}

h1 { font-size: 24px; margin-bottom: 24px; }

.input-section {
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 24px;
  margin-bottom: 24px;
}

.form-group {
  margin-bottom: 16px;
}

.form-group label {
  display: block;
  font-size: 14px;
  margin-bottom: 8px;
}

.form-group input {
  width: 100%;
  padding: 10px 12px;
  border: 1px solid #ddd;
  border-radius: 4px;
}

.form-group input:disabled {
  background: #f5f5f5;
}

.button-group {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

button {
  padding: 10px 20px;
  border: none;
  border-radius: 4px;
  cursor: pointer;
}

.btn-primary {
  background: #1F77B4;
  color: white;
}

.btn-primary:disabled {
  opacity: 0.5;
}

.btn-secondary {
  background: #fff;
  border: 1px solid #ddd;
}

.result-section {
  background: #f9f9f9;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-top: 24px;
}

.result-section pre {
  white-space: pre-wrap;
  word-break: break-word;
}

.error-section {
  background: #fee2e2;
  border: 1px solid #d62728;
  border-radius: 8px;
  padding: 16px;
  margin-top: 24px;
  color: #991b1b;
}
</style>
