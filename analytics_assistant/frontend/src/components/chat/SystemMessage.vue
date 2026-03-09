<template>
  <div class="system-message" :class="`level-${message.level}`">
    <div class="message-icon">
      <span v-if="message.level === 'error'">❌</span>
      <span v-else-if="message.level === 'warning'">⚠️</span>
      <span v-else>ℹ️</span>
    </div>
    <div class="message-body">
      <p class="message-text">{{ message.content }}</p>
      <el-button 
        v-if="message.retryable" 
        size="small" 
        type="primary"
        @click="$emit('retry')"
      >
        重试
      </el-button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { SystemMessage as SystemMessageType } from '@/types'

defineProps<{
  message: SystemMessageType
}>()

defineEmits<{
  retry: []
}>()
</script>

<style scoped>
.system-message {
  display: flex;
  align-items: flex-start;
  gap: 10px;
  padding: 12px 16px;
  border-radius: 8px;
  max-width: 80%;
  margin: 0 auto;
}

.level-error {
  background-color: #fef2f2;
  border: 1px solid #fecaca;
}

.level-warning {
  background-color: #fffbeb;
  border: 1px solid #fde68a;
}

.level-info {
  background-color: #eff6ff;
  border: 1px solid #bfdbfe;
}

.message-icon {
  font-size: 18px;
  flex-shrink: 0;
}

.message-body {
  flex: 1;
}

.message-text {
  margin: 0 0 8px 0;
  font-size: 14px;
  line-height: 1.5;
}

.level-error .message-text {
  color: #dc2626;
}

.level-warning .message-text {
  color: #d97706;
}

.level-info .message-text {
  color: #2563eb;
}
</style>
