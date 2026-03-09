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

<style scoped lang="scss">
@use '@/assets/styles/variables.scss' as *;

.insight-cards {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

.insight-card {
  display: flex;
  gap: 12px;
  padding: 12px 16px;
  border-radius: $radius-sm;
  border-left: 4px solid;
  background: var(--bg-primary);
  box-shadow: $shadow-sm;
  transition: transform $transition-normal;
  
  &:hover {
    transform: translateX(4px);
  }
}

/* 发现 - 蓝色 */
.insight-discovery {
  background-color: rgba($tableau-blue, 0.08);
  border-left-color: $tableau-blue;
}

/* 异常 - 橙色 */
.insight-anomaly {
  background-color: rgba($tableau-orange, 0.08);
  border-left-color: $tableau-orange;
}

/* 建议 - 绿色 */
.insight-suggestion {
  background-color: rgba($tableau-green, 0.08);
  border-left-color: $tableau-green;
}

.insight-icon {
  flex-shrink: 0;
  font-size: 20px;
  line-height: 1.2;
}

.insight-content {
  flex: 1;
  min-width: 0;
}

.insight-title {
  margin: 0 0 4px 0;
  font-size: 14px;
  font-weight: 600;
  color: var(--text-primary);
}

.insight-description {
  margin: 0;
  font-size: 13px;
  line-height: 1.5;
  color: var(--text-secondary);
}
</style>
