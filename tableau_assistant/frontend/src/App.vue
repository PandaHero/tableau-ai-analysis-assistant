<template>
  <div id="app">
    <!-- 初始化状态提示 -->
    <div v-if="tableauStore.isInitializing" class="init-overlay">
      <div class="init-spinner"></div>
      <p>{{ t('app.initializing') }}</p>
    </div>
    
    <!-- 初始化错误提示 -->
    <div v-else-if="tableauStore.initError" class="init-error">
      <el-icon :size="48" color="#D62728"><WarningFilled /></el-icon>
      <p>{{ t('app.initFailed') }}: {{ tableauStore.initError }}</p>
      <el-button type="primary" @click="retryInit">{{ t('app.retry') }}</el-button>
    </div>
    
    <!-- 主内容 -->
    <template v-else>
      <!-- 预热状态指示器 -->
      <div v-if="tableauStore.isPreloading" class="preload-indicator">
        <span class="preload-dot"></span>
        {{ t('app.preloading') }}
      </div>
      
      <!-- 窗口过小提示 -->
      <div v-if="uiStore.isTooSmall" class="too-small-warning">
        <el-icon :size="32"><Warning /></el-icon>
        <p>{{ t('app.windowTooSmall') }}</p>
      </div>

      <!-- 主布局 -->
      <LayoutContainer v-else ref="layoutRef">
        <template #header>
          <HeaderBar 
            :is-chat="chatStore.currentPage === 'chat'" 
            @back="handleBack"
            @settings="showSettings = true"
          />
        </template>

        <template #content>
          <!-- 首页 -->
          <WelcomePage 
            v-if="chatStore.currentPage === 'home'"
            @select-example="handleSelectExample"
          />
          
          <!-- 对话页面 -->
          <ChatPage v-else />
        </template>

        <template #input>
          <InputArea 
            ref="inputRef"
            :disabled="chatStore.isProcessing"
            :placeholder="chatStore.isProcessing ? t('input.placeholder.processing') : t('input.placeholder')"
            @send="handleSend"
          />
        </template>
      </LayoutContainer>

      <!-- 设置面板 -->
      <SettingsPanel 
        :visible="showSettings" 
        @close="showSettings = false"
      />
    </template>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted } from 'vue'
import { Warning, WarningFilled } from '@element-plus/icons-vue'
import { useTableauStore } from '@/stores/tableau'
import { useChatStore } from '@/stores/chat'
import { useSettingsStore } from '@/stores/settings'
import { useSessionStore } from '@/stores/session'
import { useUiStore } from '@/stores/ui'
import { useStreaming } from '@/composables/useStreaming'
import { useI18n } from '@/utils/i18n'
import LayoutContainer from '@/components/layout/LayoutContainer.vue'
import HeaderBar from '@/components/layout/HeaderBar.vue'
import InputArea from '@/components/layout/InputArea.vue'
import WelcomePage from '@/components/layout/WelcomePage.vue'
import ChatPage from '@/components/chat/ChatPage.vue'
import SettingsPanel from '@/components/settings/SettingsPanel.vue'

const tableauStore = useTableauStore()
const chatStore = useChatStore()
const settingsStore = useSettingsStore()
const sessionStore = useSessionStore()
const uiStore = useUiStore()
const { sendMessage: sendStreamingMessage } = useStreaming()
const { t } = useI18n()

// UI 状态
const showSettings = ref(false)

// 组件引用
const layoutRef = ref<InstanceType<typeof LayoutContainer>>()
const inputRef = ref<InstanceType<typeof InputArea>>()

onMounted(async () => {
  // 初始化各个 store
  settingsStore.initialize()
  sessionStore.initialize()
  uiStore.init()
  
  // 初始化 Tableau Extension
  await tableauStore.initialize()
})

onUnmounted(() => {
  uiStore.cleanup()
})

// 事件处理
function handleBack() {
  chatStore.goToHome()
}

function handleSelectExample(text: string) {
  handleSend(text)
}

function handleSend(text: string) {
  if (!text.trim()) return
  
  // 添加用户消息并切换页面
  chatStore.sendMessage(text)
  
  // 发送流式请求
  sendStreamingMessage(text)
}

function retryInit() {
  tableauStore.reset()
  tableauStore.initialize()
}
</script>

<style>
* {
  margin: 0;
  padding: 0;
  box-sizing: border-box;
}

#app {
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial, sans-serif;
  -webkit-font-smoothing: antialiased;
  -moz-osx-font-smoothing: grayscale;
  width: 100%;
  height: 100vh;
}

/* 初始化遮罩 */
.init-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  background: rgba(255, 255, 255, 0.95);
  z-index: 1000;
}

.init-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid #e0e0e0;
  border-top-color: var(--tableau-blue, #1F77B4);
  border-radius: 50%;
  animation: spin 1s linear infinite;
  margin-bottom: 1rem;
}

@keyframes spin {
  to { transform: rotate(360deg); }
}

/* 初始化错误 */
.init-error {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  gap: 16px;
}

.init-error p {
  color: var(--tableau-red, #D62728);
}

/* 预热状态指示器 */
.preload-indicator {
  position: fixed;
  top: 10px;
  right: 10px;
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 8px 12px;
  background: rgba(31, 119, 180, 0.1);
  border: 1px solid rgba(31, 119, 180, 0.3);
  border-radius: 4px;
  font-size: 12px;
  color: var(--tableau-blue, #1F77B4);
  z-index: 100;
}

.preload-dot {
  width: 8px;
  height: 8px;
  background: var(--tableau-blue, #1F77B4);
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}

/* 窗口过小提示 */
.too-small-warning {
  display: flex;
  flex-direction: column;
  align-items: center;
  justify-content: center;
  height: 100vh;
  gap: 12px;
  color: var(--tableau-orange, #FF7F0E);
}


</style>
