<template>
  <div v-if="sortedInsights.length" class="insight-cards">
    <div 
      v-for="insight in sortedInsights" 
      :key="insight.id"
      class="insight-card"
      :class="`insight-${insight.type}`"
    >
      <div class="insight-icon">
        {{ getIcon(insight.type) }}
      </div>
      <div class="insight-content">
        <h4 class="insight-title">{{ insight.title }}</h4>
        <p class="insight-description">{{ insight.description }}</p>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * InsightCards 组件
 * 洞察卡片列表
 * Requirements: 6.1, 6.2, 6.3, 6.4, 6.5
 */
import { computed } from 'vue'
import type { Insight } from '@/types'

const props = defineProps<{
  insights: Insight[]
}>()

// 按优先级降序排列
const sortedInsights = computed(() => 
  [...props.insights].sort((a, b) => (b.priority || 0) - (a.priority || 0))
)

// 类型图标映射
function getIcon(type: string): string {
  switch (type) {
    case 'discovery': return '💡'
    case 'anomaly': return '⚠️'
    case 'suggestion': return '✅'
    default: return '📌'
  }
}
</script>

<style scoped>
.insight-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.insight-card {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-radius: 8px;
  border-left: 4px solid;
}

/* 发现 - 蓝色 */
.insight-discovery {
  background-color: rgba(31, 119, 180, 0.08);
  border-left-color: #1F77B4;
}

/* 异常 - 橙色 */
.insight-anomaly {
  background-color: rgba(255, 127, 14, 0.08);
  border-left-color: #FF7F0E;
}

/* 建议 - 绿色 */
.insight-suggestion {
  background-color: rgba(44, 160, 44, 0.08);
  border-left-color: #2CA02C;
}

.insight-icon {
  flex-shrink: 0;
  font-size: 20px;
  line-height: 1;
}

.insight-content {
  flex: 1;
  min-width: 0;
}

.insight-title {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: #2d3748;
}

.insight-description {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: #4a5568;
}
</style>
