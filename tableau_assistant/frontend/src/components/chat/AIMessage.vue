<template>
  <div class="ai-message">
    <div class="message-avatar">
      <img src="@/assets/tableau_logo.svg" alt="AI" width="24" height="24" />
    </div>
    <div class="message-body">
      <!-- 多轮分析展示 -->
      <template v-if="message.rounds && message.rounds.length > 1">
        <div v-for="(round, index) in message.rounds" :key="index" class="analysis-round">
          <!-- 问题标题 -->
          <div class="round-question">
            <span class="round-icon">❓</span>
            <span class="round-title">{{ round.question }}</span>
          </div>
          
          <!-- 查询结果 -->
          <div v-if="round.data" class="round-data">
            <span class="data-icon">📊</span>
            <span class="data-label">查询到 {{ round.data.totalCount }} 条数据</span>
          </div>
          
          <!-- 发现 -->
          <div v-if="round.insights?.length" class="round-insights">
            <div v-for="insight in round.insights" :key="insight.id" class="insight-item">
              <span class="insight-icon">💡</span>
              <span>{{ insight.content }}</span>
            </div>
          </div>
          
          <!-- 思考气泡（非最后一轮） -->
          <div v-if="round.reason && index < message.rounds!.length - 1" class="thinking-bubble">
            <div class="connector-line">│▼</div>
            <div class="bubble-content">
              <span class="bubble-icon">💭</span>
              <span>{{ round.reason }}</span>
            </div>
          </div>
        </div>
        
        <!-- 分隔线 -->
        <div class="summary-divider">════════════════</div>
      </template>
      
      <!-- 总结内容 -->
      <div class="message-content">
        <MarkdownRenderer 
          :content="message.content || ''" 
          :streaming="message.isStreaming" 
        />
      </div>
      
      <!-- 推荐问题 -->
      <div v-if="message.suggestions?.length" class="suggestions">
        <span class="suggestions-label">💬 继续探索：</span>
        <div class="suggestion-chips">
          <button 
            v-for="(suggestion, i) in message.suggestions.slice(0, 3)" 
            :key="i"
            class="suggestion-chip"
            @click="$emit('suggest', suggestion)"
          >
            {{ suggestion }}
          </button>
        </div>
      </div>
      
      <!-- 时间戳 -->
      <span class="message-time">{{ formatTime(message.timestamp) }}</span>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { AIMessage as AIMessageType } from '@/types'
import MarkdownRenderer from '@/components/content/MarkdownRenderer.vue'

const props = defineProps<{
  message: AIMessageType
}>()

defineEmits<{
  suggest: [question: string]
}>()

function formatTime(timestamp: number): string {
  const now = Date.now()
  const diff = now - timestamp
  
  if (diff < 60000) return '刚刚'
  if (diff < 3600000) return `${Math.floor(diff / 60000)} 分钟前`
  if (diff < 86400000) return `${Math.floor(diff / 3600000)} 小时前`
  
  const date = new Date(timestamp)
  return `${date.getMonth() + 1}/${date.getDate()} ${date.getHours()}:${String(date.getMinutes()).padStart(2, '0')}`
}
</script>

<style scoped>
.ai-message {
  display: flex;
  gap: 10px;
  align-items: flex-start;
}

.message-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.message-body {
  flex: 1;
  max-width: calc(100% - 46px);
}

.message-content {
  background: var(--color-card);
  border: 1px solid var(--color-border);
  padding: 12px 16px;
  border-radius: 4px 18px 18px 18px;
  font-size: 14px;
  line-height: 1.6;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.cursor-blink {
  animation: blink 1s infinite;
  color: var(--tableau-blue);
}

@keyframes blink {
  0%, 50% { opacity: 1; }
  51%, 100% { opacity: 0; }
}

/* 多轮分析样式 */
.analysis-round {
  margin-bottom: 16px;
  padding: 12px;
  background-color: var(--btn-bg);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.round-question {
  font-weight: 600;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 8px;
  color: var(--color-text);
}

.round-data {
  color: var(--color-text-secondary);
  font-size: 13px;
  margin-bottom: 8px;
  display: flex;
  align-items: center;
  gap: 6px;
}

.round-insights {
  margin-top: 8px;
}

.insight-item {
  display: flex;
  align-items: flex-start;
  gap: 6px;
  margin-bottom: 4px;
  font-size: 13px;
  color: var(--color-text);
}

.thinking-bubble {
  margin-top: 12px;
  padding-left: 16px;
}

.connector-line {
  color: var(--color-text-secondary);
  font-family: monospace;
  margin-bottom: 4px;
}

.bubble-content {
  background-color: var(--color-card);
  border: 1px dashed var(--color-border);
  border-radius: 8px;
  padding: 8px 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
  display: flex;
  align-items: flex-start;
  gap: 6px;
}

.summary-divider {
  text-align: center;
  color: var(--color-border);
  margin: 16px 0;
  font-family: monospace;
}

/* 推荐问题 */
.suggestions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.suggestions-label {
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
}

.suggestion-chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
  margin-top: 10px;
}

.suggestion-chip {
  background: var(--btn-bg);
  border: 1px solid var(--color-border);
  border-radius: 20px;
  padding: 8px 16px;
  font-size: 13px;
  cursor: pointer;
  transition: all 0.2s ease;
  color: var(--color-text);
}

.suggestion-chip:hover {
  background: var(--tableau-blue);
  color: white;
  border-color: transparent;
}

.message-time {
  display: block;
  font-size: 11px;
  color: var(--color-text-secondary);
  margin-top: 10px;
}

/* 深色模式 */
html.dark .message-avatar {
  background: linear-gradient(135deg, #3a3a3a 0%, #2d2d2d 100%);
}

html.dark .message-content {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}
</style>
