<template>
  <div class="chat-page">
    <MessageList
      :messages="chatStore.messages"
      :is-processing="chatStore.isProcessing"
      :processing-stage="chatStore.processingStage"
      @retry="handleRetry"
    />
  </div>
</template>

<script setup lang="ts">
import { useChatStore } from '@/stores/chat'
import MessageList from './MessageList.vue'

const chatStore = useChatStore()

function handleRetry() {
  // TODO: 实现重试逻辑
  console.log('Retry requested')
}
</script>

<style scoped>
.chat-page {
  height: 100%;
  display: flex;
  flex-direction: column;
}
</style>
