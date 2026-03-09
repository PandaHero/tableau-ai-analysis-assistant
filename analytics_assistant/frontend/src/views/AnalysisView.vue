<template>
  <ThreeZoneLayout>
    <template #header>
      <HeaderBar
        mode="chat"
        :settings-open="uiStore.isSettingsPanelOpen"
        :connection-status="connectionStatus"
        @back="handleBack"
        @settings="handleSettings"
      />
    </template>

    <template #content>
      <main id="main-content" class="chat-container">
        <div class="messages-wrapper" ref="messagesWrapper">
          <div class="messages-list">
            <MessageItem
              v-for="message in chatStore.messages"
              :key="message.id"
              :message="message"
              @suggest="handleSuggest"
            />

            <div v-if="chatStore.isProcessing && !chatStore.currentResponse" class="thinking-card">
              <div class="thinking-card-header">
                <span class="thinking-title">AI 助手</span>
              </div>
              <div class="thinking-card-body">
                <ThinkingIndicator :stage="chatStore.processingStage" />
              </div>
            </div>
          </div>
        </div>
      </main>
    </template>

    <template #input>
      <InputArea
        :disabled="chatStore.isProcessing"
        :placeholder="inputPlaceholder"
        @send="handleSend"
      />
    </template>
  </ThreeZoneLayout>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick, onMounted } from 'vue'
import { useRouter } from 'vue-router'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'
import { useSettingsStore } from '@/stores/settings'
import { useTableauStore } from '@/stores/tableau'
import { useStreaming } from '@/composables/useStreaming'
import ThreeZoneLayout from '@/layouts/ThreeZoneLayout.vue'
import HeaderBar from '@/components/layout/HeaderBar.vue'
import InputArea from '@/components/layout/InputArea.vue'
import MessageItem from '@/components/chat/MessageItem.vue'
import ThinkingIndicator from '@/components/chat/ThinkingIndicator.vue'

const router = useRouter()
const chatStore = useChatStore()
const uiStore = useUiStore()
const settingsStore = useSettingsStore()
const tableauStore = useTableauStore()
const { sendMessage: sendStreamingMessage } = useStreaming()

const messagesWrapper = ref<HTMLElement>()

const connectionStatus = computed(() => {
  if (tableauStore.isInitializing) return 'connecting'
  if (tableauStore.isInitialized) return 'connected'
  return 'disconnected'
})

const inputPlaceholder = computed(() => {
  if (chatStore.isProcessing) return 'AI 正在思考...'
  return settingsStore.language === 'zh' ? '请输入您的问题...' : 'Type your question...'
})

function dispatchQuestion(question: string) {
  if (!question.trim() || chatStore.isProcessing) return
  chatStore.addUserMessage(question)
  chatStore.setProcessing(true, 'understanding')
  chatStore.setError(null)
  sendStreamingMessage(question)
}

function handleSuggest(question: string) {
  dispatchQuestion(question)
}

function handleSend(content: string) {
  dispatchQuestion(content)
}

function handleBack() {
  chatStore.goToHome()
  router.push('/')
}

function handleSettings() {
  uiStore.toggleSettingsPanel()
}

function scrollToBottom() {
  if (!messagesWrapper.value || !settingsStore.autoScroll) return
  nextTick(() => {
    if (messagesWrapper.value) {
      messagesWrapper.value.scrollTop = messagesWrapper.value.scrollHeight
    }
  })
}

watch(() => chatStore.messages.length, scrollToBottom, { flush: 'post' })
watch(() => chatStore.currentResponse?.content, scrollToBottom, { flush: 'post' })

onMounted(() => {
  if (!chatStore.hasMessages) {
    router.push('/')
    return
  }
  // 消费来自 HomeView 的待发送问题（避免 HomeView 卸载时取消 SSE）
  const pending = chatStore.consumePendingQuery()
  if (pending) {
    sendStreamingMessage(pending)
  }
})
</script>

<style scoped lang="scss">
.chat-container {
  height: 100%;
  display: flex;
  flex-direction: column;
  background: #FAFAFA;
}

.messages-wrapper {
  flex: 1;
  overflow-y: auto;
  padding: 16px;
}

.messages-list {
  display: flex;
  flex-direction: column;
  gap: 16px;
  max-width: 980px;
  margin: 0 auto;
}

.thinking-card {
  max-width: 90%;
  background: #FFFFFF;
  border: 1px solid #E0E0E0;
  border-radius: 12px;
  overflow: hidden;
}

.thinking-card-header {
  padding: 10px 16px;
  border-bottom: 1px solid #F0F0F0;
  background: #FAFAFA;
}

.thinking-title {
  font-size: 13px;
  font-weight: 600;
  color: #1A1A1A;
}

.thinking-card-body {
  padding: 16px;
}

@media (max-width: 767px) {
  .messages-wrapper {
    padding: 12px;
  }

  .messages-list {
    gap: 12px;
  }
}

@media (max-width: 479px) {
  .messages-wrapper {
    padding: 8px;
  }
}
</style>
