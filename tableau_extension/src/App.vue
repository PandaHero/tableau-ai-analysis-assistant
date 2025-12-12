<template>
  <div id="app">
    <!-- 初始化状态提示 -->
    <div v-if="tableauStore.isInitializing" class="init-overlay">
      <div class="init-spinner"></div>
      <p>正在初始化 Tableau Extension...</p>
    </div>
    
    <!-- 初始化错误提示 -->
    <div v-else-if="tableauStore.initError" class="init-error">
      <p>初始化失败: {{ tableauStore.initError }}</p>
      <button @click="retryInit">重试</button>
    </div>
    
    <!-- 主内容 -->
    <template v-else>
      <!-- 预热状态指示器 -->
      <div v-if="tableauStore.isPreloading" class="preload-indicator">
        <span class="preload-dot"></span>
        正在预热数据模型...
      </div>
      
      <router-view />
    </template>
  </div>
</template>

<script setup lang="ts">
import { onMounted } from 'vue'
import { useTableauStore } from '@/stores/tableau'

const tableauStore = useTableauStore()

onMounted(async () => {
  // 初始化 Tableau Extension 并触发预热
  await tableauStore.initialize()
})

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
  font-family: -apple-system, BlinkMacSystemFont, 'Segoe UI', Roboto, 'Helvetica Neue', Arial,
    sans-serif;
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
  border-top-color: #42b983;
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
  color: #e74c3c;
}

.init-error button {
  margin-top: 1rem;
  padding: 0.5rem 1rem;
  background: #42b983;
  color: white;
  border: none;
  border-radius: 4px;
  cursor: pointer;
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
  background: rgba(66, 185, 131, 0.1);
  border: 1px solid rgba(66, 185, 131, 0.3);
  border-radius: 4px;
  font-size: 12px;
  color: #42b983;
  z-index: 100;
}

.preload-dot {
  width: 8px;
  height: 8px;
  background: #42b983;
  border-radius: 50%;
  animation: pulse 1.5s ease-in-out infinite;
}

@keyframes pulse {
  0%, 100% { opacity: 1; }
  50% { opacity: 0.4; }
}
</style>
