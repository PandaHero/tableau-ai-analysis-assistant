<template>
  <div v-if="isStreaming" class="streaming-progress">
    <div class="thinking-dots">
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
      <span class="thinking-dot"></span>
    </div>
    <span class="status-text">{{ statusText }}</span>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'

const props = defineProps<{
  isStreaming: boolean
  currentNode?: string | null
}>()

const statusText = computed(() => {
  if (!props.currentNode) return '思考中...'
  
  const nodeLabels: Record<string, string> = {
    understanding: '理解问题...',
    field_mapper: '匹配字段...',
    query_builder: '构建查询...',
    execute: '执行分析...',
    insight: '生成洞察...',
    replanner: '规划下一步...'
  }
  
  return nodeLabels[props.currentNode] || '处理中...'
})
</script>

<style scoped>
.streaming-progress {
  display: flex;
  align-items: center;
  gap: 12px;
  padding: 12px 16px;
  background: var(--color-card, #fff);
  border: 1px solid var(--color-border, #e0e0e0);
  border-radius: 12px;
}

.thinking-dots {
  display: flex;
  gap: 4px;
}

.thinking-dot {
  width: 8px;
  height: 8px;
  background: var(--tableau-blue, #1F77B4);
  border-radius: 50%;
  animation: thinking 1.5s ease-in-out infinite;
}

.thinking-dot:nth-child(2) {
  animation-delay: 0.2s;
}

.thinking-dot:nth-child(3) {
  animation-delay: 0.4s;
}

@keyframes thinking {
  0%, 80%, 100% { opacity: 0.3; }
  40% { opacity: 1; }
}

.status-text {
  font-size: 14px;
  color: var(--color-text-secondary, #666);
}
</style>
