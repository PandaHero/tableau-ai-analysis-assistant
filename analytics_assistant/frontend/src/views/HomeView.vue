<template>
  <ThreeZoneLayout>
    <template #header>
      <HeaderBar
        mode="home"
        :settings-open="uiStore.isSettingsPanelOpen"
        :connection-status="connectionStatus"
        @settings="uiStore.toggleSettingsPanel"
      />
    </template>

    <template #content>
      <WelcomePage @select-example="handleExampleClick" />
    </template>

    <template #input>
      <InputArea
        placeholder="请输入您的数据分析问题..."
        @send="handleSend"
      />
    </template>
  </ThreeZoneLayout>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useChatStore } from '@/stores/chat'
import { useUiStore } from '@/stores/ui'
import { useTableauStore } from '@/stores/tableau'
import { useRouter } from 'vue-router'
import ThreeZoneLayout from '@/layouts/ThreeZoneLayout.vue'
import HeaderBar from '@/components/layout/HeaderBar.vue'
import InputArea from '@/components/layout/InputArea.vue'
import WelcomePage from '@/components/layout/WelcomePage.vue'

const chatStore = useChatStore()
const uiStore = useUiStore()
const tableauStore = useTableauStore()
const router = useRouter()

const connectionStatus = computed(() => {
  if (tableauStore.isInitializing) return 'connecting'
  if (tableauStore.isInitialized) return 'connected'
  return 'disconnected'
})

/**
 * 跳转到对话页并携带问题。
 * 不在此处发送 SSE——HomeView 卸载时 onUnmounted 会 cancel 掉连接。
 * 由 AnalysisView.onMounted 检测 pendingQuery 后再发送。
 */
function startConversation(query: string) {
  if (!query.trim()) return
  chatStore.addUserMessage(query)
  chatStore.setProcessing(true, 'understanding')
  chatStore.setError(null)
  chatStore.setPendingQuery(query)   // 标记待发送
  router.push('/analysis')
}

function handleExampleClick(query: string) {
  startConversation(query)
}

function handleSend(content: string) {
  startConversation(content)
}
</script>

<style scoped>
/* 样式已移至 WelcomePage 组件 */
</style>
