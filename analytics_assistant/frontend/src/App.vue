<template>
  <div id="app">
    <!-- 初始化状态提示 -->
    <div v-if="tableauStore.isInitializing" class="init-overlay">
      <div class="init-spinner"></div>
      <p>{{ t('app.initializing') }}</p>
    </div>
    
    <!-- 初始化错误（含超时） -->
    <div v-else-if="tableauStore.initError" class="init-error">
      <el-icon :size="48" color="#D62728"><WarningFilled /></el-icon>
      <p class="init-error__msg">
        {{ (tableauStore.initError === 'RELOAD_REQUIRED' || tableauStore.initError === 'TIMEOUT')
            ? t('app.initTimeout')
            : `${t('app.initFailed')}: ${tableauStore.initError}` }}
      </p>
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

      <!-- 主布局 - 使用路由视图 -->
      <div v-else class="main-content">
        <router-view />
      </div>
    </template>

    <!-- 设置面板 - 移到最外层，始终渲染 -->
    <SettingsPanel 
      v-model:open="uiStore.isSettingsPanelOpen"
      @close="uiStore.closeSettingsPanel"
    />
  </div>
</template>

<script setup lang="ts">
import { onMounted, onUnmounted } from 'vue'
import { Warning, WarningFilled } from '@element-plus/icons-vue'
import { useTableauStore } from '@/stores/tableau'
import { useSettingsStore } from '@/stores/settings'
import { useSessionStore } from '@/stores/session'
import { useUiStore } from '@/stores/ui'
import { useI18n } from '@/utils/i18n'
import SettingsPanel from '@/components/settings/SettingsPanel.vue'

const tableauStore = useTableauStore()
const settingsStore = useSettingsStore()
const sessionStore = useSessionStore()
const uiStore = useUiStore()
const { t } = useI18n()

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

async function retryInit() {
  tableauStore.reset()
  await tableauStore.initialize()
}
</script>

<style lang="scss">
@use '@/assets/styles/index.scss';

#app {
  position: relative;
  width: 100%;
  height: 100vh;
  background: var(--color-background);
  color: var(--color-text-primary);
  overflow: hidden;
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
  background: var(--color-background);
  z-index: 1000;
}

.init-spinner {
  width: 40px;
  height: 40px;
  border: 3px solid var(--color-border);
  border-top-color: var(--color-primary);
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
  padding: 24px;
  text-align: center;
  background: var(--color-background);
}

.init-error__msg {
  color: var(--color-error);
  max-width: 320px;
  line-height: 1.6;
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
  background: var(--color-surface);
  border: 1px solid var(--color-border);
  border-radius: 4px;
  font-size: 12px;
  color: var(--color-primary);
  z-index: 100;
}

.preload-dot {
  width: 8px;
  height: 8px;
  background: var(--color-primary);
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
  color: var(--color-warning);
  background: var(--color-background);
}

/* 主内容区域 */
.main-content {
  width: 100%;
  height: 100%;
}
</style>
