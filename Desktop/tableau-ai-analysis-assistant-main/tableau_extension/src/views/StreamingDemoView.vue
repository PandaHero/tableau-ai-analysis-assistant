<template>
  <div class="streaming-demo">
    <h1>流式输出演示</h1>
    
    <!-- 输入表单 -->
    <div class="input-section">
      <div class="form-group">
        <label for="question">问题：</label>
        <input
          id="question"
          v-model="question"
          type="text"
          placeholder="例如：2016年各地区的销售额"
          :disabled="isStreaming"
        />
      </div>
      
      <div class="form-group">
        <label for="datasource">数据源 LUID：</label>
        <input
          id="datasource"
          v-model="datasourceLuid"
          type="text"
          placeholder="数据源 LUID"
          :disabled="isStreaming"
        />
      </div>
      
      <div class="form-group">
        <label for="user">用户 ID：</label>
        <input
          id="user"
          v-model="userId"
          type="text"
          placeholder="用户 ID"
          :disabled="isStreaming"
        />
      </div>
      
      <div class="form-group checkbox">
        <label>
          <input
            v-model="boostQuestion"
            type="checkbox"
            :disabled="isStreaming"
          />
          使用问题 Boost
        </label>
      </div>
      
      <div class="button-group">
        <button
          @click="handleStartChat"
          :disabled="isStreaming || !canSubmit"
          class="btn-primary"
        >
          {{ isStreaming ? '处理中...' : '开始分析' }}
        </button>
        
        <button
          v-if="isStreaming"
          @click="handleStopChat"
          class="btn-secondary"
        >
          停止
        </button>
        
        <button
          v-if="currentMessage"
          @click="handleClear"
          :disabled="isStreaming"
          class="btn-secondary"
        >
          清除
        </button>
      </div>
    </div>
    
    <!-- 流式进度显示 -->
    <StreamingProgress :state="state" />
    
    <!-- 事件日志（调试用） -->
    <div v-if="showDebug" class="debug-section">
      <h3>事件日志</h3>
      <div class="event-log">
        <div
          v-for="(event, index) in state.events"
          :key="index"
          class="event-item"
        >
          <span class="event-type">{{ event.type }}</span>
          <span class="event-data">{{ JSON.stringify(event.data) }}</span>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue'
import { useStreaming } from '@/composables/useStreaming'
import StreamingProgress from '@/components/StreamingProgress.vue'

// 使用流式输出
const {
  state,
  isStreaming,
  currentMessage,
  startChat,
  stopStreaming,
  clearMessage
} = useStreaming()

// 表单数据
const question = ref('2016年各地区的销售额')
const datasourceLuid = ref('test_datasource')
const userId = ref('test_user')
const boostQuestion = ref(false)
const showDebug = ref(false)

// 计算属性
const canSubmit = computed(() => {
  return question.value.trim() !== '' &&
         datasourceLuid.value.trim() !== '' &&
         userId.value.trim() !== ''
})

/**
 * 开始聊天
 */
async function handleStartChat() {
  await startChat({
    question: question.value,
    datasource_luid: datasourceLuid.value,
    user_id: userId.value,
    session_id: userId.value,
    boost_question: boostQuestion.value
  })
}

/**
 * 停止聊天
 */
function handleStopChat() {
  stopStreaming()
}

/**
 * 清除消息
 */
function handleClear() {
  clearMessage()
}
</script>

<style scoped>
.streaming-demo {
  max-width: 1200px;
  margin: 0 auto;
  padding: 24px;
}

h1 {
  font-size: 24px;
  font-weight: 600;
  margin-bottom: 24px;
  color: #333;
}

/* 输入部分 */
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
  font-weight: 500;
  margin-bottom: 8px;
  color: #333;
}

.form-group input[type="text"] {
  width: 100%;
  padding: 10px 12px;
  font-size: 14px;
  border: 1px solid #ddd;
  border-radius: 4px;
  transition: border-color 0.3s;
}

.form-group input[type="text"]:focus {
  outline: none;
  border-color: #2196F3;
}

.form-group input[type="text"]:disabled {
  background: #f5f5f5;
  cursor: not-allowed;
}

.form-group.checkbox {
  display: flex;
  align-items: center;
}

.form-group.checkbox label {
  display: flex;
  align-items: center;
  margin-bottom: 0;
  cursor: pointer;
}

.form-group.checkbox input[type="checkbox"] {
  margin-right: 8px;
  cursor: pointer;
}

/* 按钮组 */
.button-group {
  display: flex;
  gap: 12px;
  margin-top: 20px;
}

button {
  padding: 10px 20px;
  font-size: 14px;
  font-weight: 500;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  transition: all 0.3s;
}

.btn-primary {
  background: #2196F3;
  color: white;
}

.btn-primary:hover:not(:disabled) {
  background: #1976D2;
}

.btn-primary:disabled {
  background: #BBDEFB;
  cursor: not-allowed;
}

.btn-secondary {
  background: #fff;
  color: #666;
  border: 1px solid #ddd;
}

.btn-secondary:hover:not(:disabled) {
  background: #f5f5f5;
}

.btn-secondary:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* 调试部分 */
.debug-section {
  background: #f5f5f5;
  border: 1px solid #e0e0e0;
  border-radius: 8px;
  padding: 16px;
  margin-top: 24px;
}

.debug-section h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #333;
}

.event-log {
  max-height: 400px;
  overflow-y: auto;
  background: #fff;
  border: 1px solid #ddd;
  border-radius: 4px;
  padding: 12px;
}

.event-item {
  display: flex;
  gap: 12px;
  padding: 8px;
  border-bottom: 1px solid #f0f0f0;
  font-size: 12px;
  font-family: monospace;
}

.event-item:last-child {
  border-bottom: none;
}

.event-type {
  font-weight: 600;
  color: #2196F3;
  min-width: 150px;
}

.event-data {
  color: #666;
  word-break: break-all;
}
</style>
