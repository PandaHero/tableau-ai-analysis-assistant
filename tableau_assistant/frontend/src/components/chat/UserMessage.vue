<template>
  <div class="user-message">
    <div class="message-content">
      <p class="message-text">{{ message.content }}</p>
      <span class="message-time">{{ formatTime(message.timestamp) }}</span>
    </div>
    <div class="message-avatar">
      <svg width="18" height="18" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 12c2.21 0 4-1.79 4-4s-1.79-4-4-4-4 1.79-4 4 1.79 4 4 4zm0 2c-2.67 0-8 1.34-8 4v2h16v-2c0-2.66-5.33-4-8-4z"/>
      </svg>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { UserMessage as UserMessageType } from '@/types'

defineProps<{
  message: UserMessageType
}>()

// 格式化相对时间
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
.user-message {
  display: flex;
  justify-content: flex-end;
  gap: 10px;
  align-items: flex-end;
}

.message-content {
  max-width: 70%;
  background: linear-gradient(135deg, #1F77B4 0%, #2d8bc9 100%);
  color: white;
  padding: 12px 16px;
  border-radius: 18px 18px 4px 18px;
  word-break: break-word;
  box-shadow: 0 2px 12px rgba(31, 119, 180, 0.25);
}

.message-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #1F77B4 0%, #2d8bc9 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  color: white;
  box-shadow: 0 2px 8px rgba(31, 119, 180, 0.2);
}

.message-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.6;
  white-space: pre-wrap;
}

.message-time {
  display: block;
  font-size: 11px;
  opacity: 0.75;
  margin-top: 6px;
  text-align: right;
}
</style>
