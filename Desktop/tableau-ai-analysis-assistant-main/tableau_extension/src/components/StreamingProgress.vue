<template>
  <div class="streaming-progress">
    <!-- 当前消息显示 -->
    <div v-if="currentMessage" class="message-container">
      <div class="message-content">
        {{ currentMessage }}
      </div>
      <div v-if="isStreaming" class="typing-indicator">
        <span></span>
        <span></span>
        <span></span>
      </div>
    </div>

    <!-- Agent 进度显示 -->
    <div v-if="agentProgress.length > 0" class="agent-progress-container">
      <h3>执行进度</h3>
      <div class="agent-list">
        <div
          v-for="agent in agentProgress"
          :key="agent.name"
          class="agent-item"
          :class="agent.status"
        >
          <div class="agent-icon">
            <span v-if="agent.status === 'running'" class="spinner"></span>
            <span v-else-if="agent.status === 'complete'" class="checkmark">✓</span>
            <span v-else-if="agent.status === 'error'" class="error-mark">✗</span>
          </div>
          <div class="agent-info">
            <div class="agent-name">{{ formatAgentName(agent.name) }}</div>
            <div v-if="agent.error" class="agent-error">{{ agent.error }}</div>
            <div v-if="agent.endTime && agent.startTime" class="agent-duration">
              {{ formatDuration(agent.endTime - agent.startTime) }}
            </div>
          </div>
        </div>
      </div>
    </div>

    <!-- 错误显示 -->
    <div v-if="hasError" class="error-container">
      <div class="error-icon">⚠️</div>
      <div class="error-message">{{ state.error }}</div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { StreamingState, AgentProgress } from '@/composables/useStreaming'

interface Props {
  state: StreamingState
}

const props = defineProps<Props>()

const isStreaming = computed(() => props.state.isStreaming)
const currentMessage = computed(() => props.state.currentMessage)
const agentProgress = computed(() => props.state.agentProgress)
const hasError = computed(() => props.state.error !== null)

/**
 * 格式化 Agent 名称
 */
function formatAgentName(name: string): string {
  // 将 understanding_agent 转换为 "问题理解"
  const nameMap: Record<string, string> = {
    'understanding_agent': '问题理解',
    'planning_agent': '查询规划',
    'query_agent': '查询执行',
    'insight_agent': '洞察分析',
    'replanner_agent': '重新规划',
    'summarizer_agent': '结果总结'
  }
  
  return nameMap[name] || name
}

/**
 * 格式化持续时间
 */
function formatDuration(seconds: number): string {
  if (seconds < 1) {
    return `${Math.round(seconds * 1000)}ms`
  }
  return `${seconds.toFixed(2)}s`
}
</script>

<style scoped>
.streaming-progress {
  padding: 16px;
}

/* 消息容器 */
.message-container {
  background: #f5f5f5;
  border-radius: 8px;
  padding: 16px;
  margin-bottom: 16px;
}

.message-content {
  font-size: 14px;
  line-height: 1.6;
  color: #333;
  white-space: pre-wrap;
  word-wrap: break-word;
}

/* 打字指示器 */
.typing-indicator {
  display: flex;
  gap: 4px;
  margin-top: 8px;
}

.typing-indicator span {
  width: 8px;
  height: 8px;
  background: #999;
  border-radius: 50%;
  animation: typing 1.4s infinite;
}

.typing-indicator span:nth-child(2) {
  animation-delay: 0.2s;
}

.typing-indicator span:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes typing {
  0%, 60%, 100% {
    opacity: 0.3;
    transform: translateY(0);
  }
  30% {
    opacity: 1;
    transform: translateY(-8px);
  }
}

/* Agent 进度容器 */
.agent-progress-container {
  margin-bottom: 16px;
}

.agent-progress-container h3 {
  font-size: 16px;
  font-weight: 600;
  margin-bottom: 12px;
  color: #333;
}

.agent-list {
  display: flex;
  flex-direction: column;
  gap: 8px;
}

/* Agent 项 */
.agent-item {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #fff;
  border: 1px solid #e0e0e0;
  border-radius: 6px;
  transition: all 0.3s ease;
}

.agent-item.running {
  border-color: #2196F3;
  background: #E3F2FD;
}

.agent-item.complete {
  border-color: #4CAF50;
  background: #E8F5E9;
}

.agent-item.error {
  border-color: #F44336;
  background: #FFEBEE;
}

/* Agent 图标 */
.agent-icon {
  width: 24px;
  height: 24px;
  display: flex;
  align-items: center;
  justify-content: center;
}

.spinner {
  width: 16px;
  height: 16px;
  border: 2px solid #2196F3;
  border-top-color: transparent;
  border-radius: 50%;
  animation: spin 0.8s linear infinite;
}

@keyframes spin {
  to {
    transform: rotate(360deg);
  }
}

.checkmark {
  color: #4CAF50;
  font-size: 20px;
  font-weight: bold;
}

.error-mark {
  color: #F44336;
  font-size: 20px;
  font-weight: bold;
}

/* Agent 信息 */
.agent-info {
  flex: 1;
}

.agent-name {
  font-size: 14px;
  font-weight: 500;
  color: #333;
}

.agent-error {
  font-size: 12px;
  color: #F44336;
  margin-top: 4px;
}

.agent-duration {
  font-size: 12px;
  color: #666;
  margin-top: 4px;
}

/* 错误容器 */
.error-container {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px;
  background: #FFEBEE;
  border: 1px solid #F44336;
  border-radius: 6px;
}

.error-icon {
  font-size: 24px;
}

.error-message {
  flex: 1;
  font-size: 14px;
  color: #D32F2F;
}
</style>
