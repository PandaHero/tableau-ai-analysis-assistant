<template>
  <div class="message-list" ref="listRef">
    <div class="messages-container">
      <template v-for="message in messages" :key="message.id">
        <UserMessage 
          v-if="message.type === 'user'" 
          :message="message" 
        />
        <AIMessage 
          v-else-if="message.type === 'ai'" 
          :message="message" 
        />
        <SystemMessage 
          v-else-if="message.type === 'system'" 
          :message="message"
          @retry="$emit('retry')"
        />
      </template>
      
      <!-- 思考指示器：仅在处理中且没有流式内容时显示 -->
      <ThinkingIndicator 
        v-if="isProcessing && !hasStreamingContent" 
        :stage="processingStage" 
      />
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, watch, nextTick, computed } from 'vue'
import type { Message, ProcessingStage, AIMessage as AIMessageType } from '@/types'
import UserMessage from './UserMessage.vue'
import AIMessage from './AIMessage.vue'
import SystemMessage from './SystemMessage.vue'
import ThinkingIndicator from './ThinkingIndicator.vue'

const props = defineProps<{
  messages: Message[]
  isProcessing?: boolean
  processingStage?: ProcessingStage | null
}>()

defineEmits<{
  retry: []
}>()

const listRef = ref<HTMLElement | null>(null)

/**
 * 检查是否有正在流式传输的消息（有内容）
 * 如果有，则不显示 ThinkingIndicator
 */
const hasStreamingContent = computed(() => {
  const lastMsg = props.messages[props.messages.length - 1]
  if (!lastMsg || lastMsg.type !== 'ai') return false
  const aiMsg = lastMsg as AIMessageType
  return aiMsg.isStreaming === true && !!aiMsg.content?.trim()
})

// 自动滚动到底部
function scrollToBottom() {
  nextTick(() => {
    if (listRef.value) {
      listRef.value.scrollTop = listRef.value.scrollHeight
    }
  })
}

// 监听消息变化，自动滚动
watch(() => props.messages.length, scrollToBottom)
watch(() => props.isProcessing, scrollToBottom)
</script>

<style scoped>
.message-list {
  height: 100%;
  overflow-y: auto;
  scroll-behavior: smooth;
}

.messages-container {
  display: flex;
  flex-direction: column;
  gap: 16px;
  padding: 16px 0;
  width: 100%;
}
</style>
