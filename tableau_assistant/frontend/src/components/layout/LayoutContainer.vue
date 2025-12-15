<template>
  <div class="layout-container" :class="layoutModeClass">
    <!-- 顶部导航栏 -->
    <header class="header-bar">
      <slot name="header"></slot>
    </header>

    <!-- 中间内容区域 -->
    <main class="content-area">
      <slot name="content"></slot>
    </main>

    <!-- 底部输入区域 -->
    <footer class="input-area">
      <slot name="input"></slot>
    </footer>
  </div>
</template>

<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref } from 'vue'

// 响应式断点
const BREAKPOINTS = {
  minimal: 320,
  compact: 480,
  standard: 768
}

const windowWidth = ref(window.innerWidth)

const layoutMode = computed(() => {
  if (windowWidth.value >= BREAKPOINTS.standard) return 'standard'
  if (windowWidth.value >= BREAKPOINTS.compact) return 'compact'
  if (windowWidth.value >= BREAKPOINTS.minimal) return 'minimal'
  return 'too-small'
})

const layoutModeClass = computed(() => `layout-${layoutMode.value}`)

function handleResize() {
  windowWidth.value = window.innerWidth
}

onMounted(() => {
  window.addEventListener('resize', handleResize)
})

onUnmounted(() => {
  window.removeEventListener('resize', handleResize)
})

// 暴露给父组件
defineExpose({ layoutMode, windowWidth })
</script>

<style scoped>
.layout-container {
  display: flex;
  flex-direction: column;
  height: 100vh;
  width: 100%;
  background-color: var(--color-bg);
  overflow: hidden;
}

.header-bar {
  height: 48px;
  flex-shrink: 0;
  border-bottom: 1px solid var(--color-border);
  background-color: var(--color-card);
}

.content-area {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
}

.input-area {
  flex-shrink: 0;
  border-top: 1px solid var(--color-border);
  background-color: var(--color-card);
}

/* 标准布局 (>= 768px) */
.layout-standard .content-area {
  padding: 16px;
}
.layout-standard .input-area {
  padding: 12px 16px;
}

/* 紧凑布局 (480-768px) */
.layout-compact .content-area {
  padding: 12px 16px;
}
.layout-compact .input-area {
  padding: 10px 16px;
}
.layout-compact .header-bar {
  height: 44px;
}

/* 最小化布局 (320-480px) */
.layout-minimal .content-area {
  padding: 8px 12px;
}
.layout-minimal .input-area {
  padding: 8px 12px;
}
.layout-minimal .header-bar {
  height: 40px;
}

/* 窗口过小提示 (< 320px) */
.layout-too-small .content-area {
  display: flex;
  align-items: center;
  justify-content: center;
  padding: 16px;
}
.layout-too-small .content-area::before {
  content: '窗口过小，请调整窗口大小';
  color: var(--color-text-secondary);
  font-size: 14px;
  text-align: center;
}
</style>
