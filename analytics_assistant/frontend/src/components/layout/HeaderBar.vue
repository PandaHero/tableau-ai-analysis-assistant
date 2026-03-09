<template>
  <header class="header-bar" role="banner">
    <a href="#main-content" class="skip-link">跳到主内容</a>

    <div class="header-left">
      <button
        v-if="mode === 'chat'"
        class="action-button"
        type="button"
        @click="handleBack"
        aria-label="返回首页"
        title="返回首页 (Alt+Left)"
      >
        <svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path d="M15 6l-6 6 6 6" />
        </svg>
      </button>

      <div v-if="mode === 'home'" class="brand-block" aria-live="polite">
        <img src="@/assets/tableau_logo.svg" alt="Tableau Logo" class="brand-logo" />
        <div class="brand-copy">
          <span class="brand-eyebrow">Analytics Assistant</span>
          <h1 class="brand-title" id="app-title">Tableau AI 助手</h1>
        </div>
      </div>

      <div v-else class="chat-context">
        <span class="chat-context__eyebrow">分析会话</span>
        <strong class="chat-context__title">实时数据问答</strong>
      </div>
    </div>

    <div class="header-right" role="navigation" aria-label="主导航">
      <div class="connection-pill" :class="connectionStatusClass" :title="connectionTitle">
        <span class="connection-pill__dot"></span>
        <span class="connection-pill__label">{{ connectionText }}</span>
      </div>

      <button
        class="action-button action-button--accent"
        type="button"
        @click.stop="handleSettings"
        aria-label="打开设置面板"
        aria-haspopup="dialog"
        :aria-expanded="settingsOpen"
        aria-controls="settings-panel"
        title="设置 (Alt+S)"
      >
        <svg class="action-icon" viewBox="0 0 24 24" fill="none" aria-hidden="true">
          <path
            d="M12 15a3 3 0 100-6 3 3 0 000 6z"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
          <path
            d="M19.4 15a1 1 0 00.2 1.1l.1.1a1.2 1.2 0 010 1.7l-1 1a1.2 1.2 0 01-1.7 0l-.1-.1a1 1 0 00-1.1-.2 1 1 0 00-.6.9v.3A1.2 1.2 0 0114 22h-2a1.2 1.2 0 01-1.2-1.2v-.2a1 1 0 00-.6-.9 1 1 0 00-1.1.2l-.1.1a1.2 1.2 0 01-1.7 0l-1-1a1.2 1.2 0 010-1.7l.1-.1a1 1 0 00.2-1.1 1 1 0 00-.9-.6h-.3A1.2 1.2 0 014 14v-2a1.2 1.2 0 011.2-1.2h.2a1 1 0 00.9-.6 1 1 0 00-.2-1.1l-.1-.1a1.2 1.2 0 010-1.7l1-1a1.2 1.2 0 011.7 0l.1.1a1 1 0 001.1.2 1 1 0 00.6-.9v-.3A1.2 1.2 0 0112 2h2a1.2 1.2 0 011.2 1.2v.2a1 1 0 00.6.9 1 1 0 001.1-.2l.1-.1a1.2 1.2 0 011.7 0l1 1a1.2 1.2 0 010 1.7l-.1.1a1 1 0 00-.2 1.1 1 1 0 00.9.6h.3A1.2 1.2 0 0122 12v2a1.2 1.2 0 01-1.2 1.2h-.2a1 1 0 00-.9.6z"
            stroke-linecap="round"
            stroke-linejoin="round"
          />
        </svg>
      </button>
    </div>
  </header>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted } from 'vue'

import { useKeyboardNavigation } from '@/composables/useKeyboardNavigation'

interface Props {
  mode?: 'home' | 'chat'
  settingsOpen?: boolean
  connectionStatus?: 'connected' | 'connecting' | 'disconnected'
}

const props = withDefaults(defineProps<Props>(), {
  mode: 'home',
  settingsOpen: false,
  connectionStatus: 'connected',
})

const emit = defineEmits<{
  back: []
  settings: []
}>()

const handleBack = () => emit('back')
const handleSettings = () => emit('settings')

const connectionStatusClass = computed(() => `status-${props.connectionStatus}`)

const connectionText = computed(() => {
  if (props.connectionStatus === 'connected') return '已连接'
  if (props.connectionStatus === 'connecting') return '连接中'
  return '已断开'
})

const connectionTitle = computed(() => {
  if (props.connectionStatus === 'connected') return '服务连接正常'
  if (props.connectionStatus === 'connecting') return '正在建立连接'
  return '服务连接不可用'
})

const { enable, disable } = useKeyboardNavigation([
  {
    key: 's',
    alt: true,
    handler: () => handleSettings(),
    description: '打开设置面板',
  },
  {
    key: 'ArrowLeft',
    alt: true,
    handler: () => {
      if (props.mode === 'chat') {
        handleBack()
      }
    },
    description: '返回首页',
  },
])

onMounted(enable)
onUnmounted(disable)
</script>

<style scoped lang="scss">
.header-bar {
  position: relative;
  width: 100%;
  height: 100%;
  padding: 0 18px 0 20px;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 16px;
  background:
    linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(249, 250, 252, 0.94));
}

.skip-link {
  position: absolute;
  left: -9999px;
  top: 8px;
  z-index: 999;
  padding: 8px 14px;
  background: #1f77b4;
  color: #fff;
  text-decoration: none;
  border-radius: 12px;
}

.skip-link:focus {
  left: 12px;
}

.header-left,
.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
  min-width: 0;
}

.brand-block {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.brand-logo {
  width: 34px;
  height: 34px;
  flex-shrink: 0;
}

.brand-copy {
  min-width: 0;
}

.brand-eyebrow,
.chat-context__eyebrow {
  display: block;
  margin-bottom: 2px;
  color: var(--text-tertiary);
  font-size: 11px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.brand-title,
.chat-context__title {
  margin: 0;
  color: var(--text-primary);
  font-size: 16px;
  line-height: 1.2;
  font-weight: 700;
  white-space: nowrap;
  overflow: hidden;
  text-overflow: ellipsis;
}

.chat-context {
  min-width: 0;
}

.connection-pill {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  min-width: 0;
  padding: 7px 12px;
  border-radius: 999px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: rgba(255, 255, 255, 0.76);
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.65);
}

.connection-pill__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  flex-shrink: 0;
}

.connection-pill__label {
  font-size: 12px;
  font-weight: 600;
  white-space: nowrap;
}

.status-connected .connection-pill__dot {
  background: #2ca02c;
  box-shadow: 0 0 0 5px rgba(44, 160, 44, 0.14);
}

.status-connected .connection-pill__label {
  color: #2ca02c;
}

.status-connecting .connection-pill__dot {
  background: #ff7f0e;
  box-shadow: 0 0 0 5px rgba(255, 127, 14, 0.14);
  animation: pulse 1.1s infinite;
}

.status-connecting .connection-pill__label {
  color: #ff7f0e;
}

.status-disconnected .connection-pill__dot {
  background: #d62728;
  box-shadow: 0 0 0 5px rgba(214, 39, 40, 0.14);
}

.status-disconnected .connection-pill__label {
  color: #d62728;
}

.action-button {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.98), rgba(244, 246, 249, 0.95));
  color: var(--text-secondary);
  box-shadow:
    0 12px 26px rgba(15, 23, 42, 0.10),
    inset 0 1px 0 rgba(255, 255, 255, 0.8);
  transition:
    transform 180ms ease,
    box-shadow 180ms ease,
    border-color 180ms ease,
    color 180ms ease;
}

.action-button:hover {
  transform: translateY(-1px);
  color: #1f77b4;
  border-color: rgba(31, 119, 180, 0.22);
  box-shadow:
    0 16px 30px rgba(31, 119, 180, 0.16),
    inset 0 1px 0 rgba(255, 255, 255, 0.82);
}

.action-button:active {
  transform: scale(0.96);
}

.action-button:focus-visible {
  outline: 2px solid rgba(31, 119, 180, 0.5);
  outline-offset: 2px;
}

.action-button--accent {
  background: linear-gradient(180deg, rgba(247, 250, 255, 0.98), rgba(239, 245, 252, 0.96));
}

.action-icon {
  width: 18px;
  height: 18px;
  stroke: currentColor;
  stroke-width: 1.8;
}

:global([data-theme='dark']) .header-bar {
  background: linear-gradient(180deg, rgba(20, 24, 31, 0.98), rgba(17, 20, 27, 0.96));
}

:global([data-theme='dark']) .connection-pill {
  background: rgba(255, 255, 255, 0.04);
  border-color: rgba(255, 255, 255, 0.10);
}

:global([data-theme='dark']) .action-button {
  background: linear-gradient(180deg, rgba(42, 48, 59, 0.96), rgba(29, 34, 43, 0.96));
  border-color: rgba(255, 255, 255, 0.10);
  color: rgba(255, 255, 255, 0.88);
  box-shadow:
    0 14px 28px rgba(0, 0, 0, 0.36),
    inset 0 1px 0 rgba(255, 255, 255, 0.05);
}

:global([data-theme='dark']) .action-button:hover {
  color: #8fd2ff;
  border-color: rgba(93, 173, 226, 0.32);
  box-shadow:
    0 16px 30px rgba(4, 30, 49, 0.55),
    inset 0 1px 0 rgba(255, 255, 255, 0.06);
}

@media (max-width: 767px) {
  .header-bar {
    padding: 0 14px;
  }

  .brand-eyebrow,
  .chat-context__eyebrow,
  .connection-pill__label {
    display: none;
  }

  .brand-title,
  .chat-context__title {
    font-size: 14px;
  }

  .action-button {
    width: 38px;
    height: 38px;
    border-radius: 12px;
  }
}

@keyframes pulse {
  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.45;
  }
}
</style>
