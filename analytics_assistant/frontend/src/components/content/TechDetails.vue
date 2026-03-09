<template>
  <div class="tech-details">
    <button class="toggle-btn" @click="expanded = !expanded">
      🔧 查看 VizQL 查询 {{ expanded ? '▲' : '▼' }}
    </button>
    
    <Transition name="slide">
      <div v-if="expanded" class="details-content">
        <!-- 执行信息 -->
        <div class="meta-info">
          <span class="meta-item">
            ⏱️ 执行时间: {{ details.executionTime }}ms
          </span>
          <span class="meta-item">
            📊 返回行数: {{ details.rowCount }}
          </span>
        </div>
        
        <!-- JSON 代码块 -->
        <div class="code-block">
          <button class="copy-btn" @click="copyJson">
            {{ copied ? '已复制 ✓' : '复制' }}
          </button>
          <pre><code>{{ formattedJson }}</code></pre>
        </div>
      </div>
    </Transition>
  </div>
</template>

<script setup lang="ts">
/**
 * TechDetails 组件
 * 可折叠的技术细节展示
 * Requirements: 10.1, 10.2, 10.3, 10.4, 10.5
 */
import { ref, computed } from 'vue'

interface TechDetailsData {
  query: Record<string, unknown>
  executionTime: number
  rowCount: number
}

const props = defineProps<{
  details: TechDetailsData
}>()

const expanded = ref(false)
const copied = ref(false)

const formattedJson = computed(() => 
  JSON.stringify(props.details.query, null, 2)
)

async function copyJson() {
  try {
    await navigator.clipboard.writeText(formattedJson.value)
    copied.value = true
    setTimeout(() => { copied.value = false }, 2000)
  } catch {
    console.error('Failed to copy')
  }
}
</script>

<style scoped>
.tech-details {
  margin-top: 12px;
}

.toggle-btn {
  background: none;
  border: none;
  padding: 8px 0;
  font-size: 13px;
  color: var(--color-text-secondary);
  cursor: pointer;
  transition: color 0.2s;
}

.toggle-btn:hover {
  color: var(--tableau-blue);
}

.details-content {
  margin-top: 8px;
  padding: 12px;
  background-color: var(--btn-bg);
  border-radius: 8px;
  border: 1px solid var(--color-border);
}

.meta-info {
  display: flex;
  gap: 16px;
  margin-bottom: 12px;
  font-size: 13px;
  color: var(--color-text-secondary);
}

.code-block {
  position: relative;
  background-color: #1e1e1e;
  border-radius: 6px;
  overflow: hidden;
}

.copy-btn {
  position: absolute;
  top: 8px;
  right: 8px;
  padding: 4px 10px;
  background: rgba(255,255,255,0.1);
  border: none;
  border-radius: 4px;
  font-size: 12px;
  color: #a0aec0;
  cursor: pointer;
  transition: all 0.2s;
}

.copy-btn:hover {
  background: rgba(255,255,255,0.2);
  color: white;
}

.code-block pre {
  margin: 0;
  padding: 12px 16px;
  overflow-x: auto;
}

.code-block code {
  font-family: 'Consolas', 'Monaco', monospace;
  font-size: 12px;
  line-height: 1.5;
  color: #d4d4d4;
}

/* 过渡动画 */
.slide-enter-active,
.slide-leave-active {
  transition: all 0.3s ease;
  overflow: hidden;
}

.slide-enter-from,
.slide-leave-to {
  opacity: 0;
  max-height: 0;
}

.slide-enter-to,
.slide-leave-from {
  opacity: 1;
  max-height: 500px;
}
</style>
