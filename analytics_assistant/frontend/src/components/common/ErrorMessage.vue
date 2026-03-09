<template>
  <div class="error-message">
    <div class="error-icon">
      <svg width="20" height="20" viewBox="0 0 24 24" fill="currentColor">
        <path d="M12 2C6.48 2 2 6.48 2 12s4.48 10 10 10 10-4.48 10-10S17.52 2 12 2zm1 15h-2v-2h2v2zm0-4h-2V7h2v6z"/>
      </svg>
    </div>
    <div class="error-content">
      <p class="error-text">{{ message }}</p>
      <button 
        v-if="showRetry" 
        class="retry-button"
        @click="$emit('retry')"
      >
        重试
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * ErrorMessage 组件
 * 显示错误消息，可选重试按钮
 * Requirements: 14.6
 */
withDefaults(defineProps<{
  message: string
  showRetry?: boolean
}>(), {
  showRetry: false
})

defineEmits<{
  retry: []
}>()
</script>

<style scoped>
.error-message {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  background-color: #FEE2E2;
  border: 1px solid var(--tableau-red);
  border-radius: 8px;
  color: #991B1B;
}

.error-icon {
  flex-shrink: 0;
  color: var(--tableau-red);
}

.error-content {
  flex: 1;
  display: flex;
  flex-direction: column;
  gap: 8px;
}

.error-text {
  margin: 0;
  font-size: 14px;
  line-height: 1.5;
}

.retry-button {
  align-self: flex-start;
  padding: 6px 16px;
  background-color: var(--tableau-red);
  color: white;
  border: none;
  border-radius: 6px;
  font-size: 13px;
  cursor: pointer;
  transition: background-color 0.2s;
}

.retry-button:hover {
  background-color: #B91C1C;
}

/* 深色模式 */
html.dark .error-message {
  background-color: rgba(214, 39, 40, 0.15);
  color: #FCA5A5;
}

html.dark .retry-button:hover {
  background-color: #EF4444;
}
</style>
