<template>
  <div class="thinking-indicator">
    <div class="indicator-body">
      <!-- 三点动画 + 当前阶段文字 -->
      <div class="indicator-header">
        <div class="dots">
          <span class="dot"></span>
          <span class="dot"></span>
          <span class="dot"></span>
        </div>
        <span class="stage-text">{{ stageLabel }}</span>
      </div>

      <!-- 阶段进度列表（垂直排列） -->
      <div class="stage-list">
        <div
          v-for="s in STAGE_ORDER"
          :key="s"
          class="stage-list-item"
          :class="getStageStatus(s)"
        >
          <span class="stage-bullet">{{ getStageBullet(s) }}</span>
          <span class="stage-list-label">{{ t(STAGE_KEYS[s]) }}</span>
        </div>
      </div>

      <!-- 错误信息 -->
      <div v-if="props.stage === 'error'" class="error-info">
        {{ t('thinking.error') }}
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import type { ProcessingStage } from '@/types'
import { useI18n } from '@/utils/i18n'

const props = defineProps<{
  stage?: ProcessingStage | null
}>()

const { t } = useI18n()

// 阶段顺序（不含 replanning/error）
const STAGE_ORDER: ProcessingStage[] = ['understanding', 'building', 'executing', 'generating']

const STAGE_KEYS: Record<ProcessingStage, string> = {
  understanding: 'thinking.understanding',
  building: 'thinking.building',
  executing: 'thinking.executing',
  generating: 'thinking.generating',
  replanning: 'thinking.replanning',
  error: 'thinking.error',
}

const stageLabel = computed(() => {
  if (!props.stage || props.stage === 'error') return t('thinking.understanding')
  const key = STAGE_KEYS[props.stage]
  return key ? t(key) : t('thinking.understanding')
})

/**
 * 获取阶段状态：completed / active / pending / error
 */
function getStageStatus(s: ProcessingStage): string {
  if (props.stage === 'error') {
    const currentIdx = STAGE_ORDER.indexOf('executing')
    const sIdx = STAGE_ORDER.indexOf(s)
    if (sIdx < currentIdx) return 'stage-completed'
    if (sIdx === currentIdx) return 'stage-error'
    return 'stage-pending'
  }
  const currentIdx = STAGE_ORDER.indexOf(props.stage as ProcessingStage)
  const sIdx = STAGE_ORDER.indexOf(s)
  if (sIdx < currentIdx) return 'stage-completed'
  if (sIdx === currentIdx) return 'stage-active'
  return 'stage-pending'
}

function getStageBullet(s: ProcessingStage): string {
  if (props.stage === 'error') {
    const currentIdx = STAGE_ORDER.indexOf('executing')
    const sIdx = STAGE_ORDER.indexOf(s)
    if (sIdx < currentIdx) return '✓'
    if (sIdx === currentIdx) return '⚠️'
    return '○'
  }
  const currentIdx = STAGE_ORDER.indexOf(props.stage as ProcessingStage)
  const sIdx = STAGE_ORDER.indexOf(s)
  if (sIdx < currentIdx) return '✓'
  if (sIdx === currentIdx) return '●'
  return '○'
}
</script>

<style scoped lang="scss">
@use '@/assets/styles/variables.scss' as *;

.thinking-indicator {
  padding: 16px;
}

/* 外层 body */
.indicator-body {
  display: flex;
  flex-direction: column;
  gap: 12px;
}

/* 头部：三点动画 + 阶段文字 */
.indicator-header {
  display: flex;
  align-items: center;
  gap: 10px;
}

/* 三点动画 */
.dots {
  display: flex;
  gap: 4px;
  align-items: center;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: $tableau-blue;
  opacity: 0.3;
  animation: thinking-pulse 1.5s infinite;
}

.dot:nth-child(2) {
  animation-delay: 0.5s;
}

.dot:nth-child(3) {
  animation-delay: 1s;
}

@keyframes thinking-pulse {
  0%, 100% { opacity: 0.3; }
  50% { opacity: 1; }
}

.stage-text {
  font-size: 14px;
  color: var(--text-secondary);
  transition: opacity 0.3s;
}

/* 阶段进度列表（垂直排列） */
.stage-list {
  display: flex;
  flex-direction: column;
  gap: 0;
  margin-top: 4px;
}

.stage-list-item {
  display: flex;
  align-items: center;
  gap: 8px;
  padding: 4px 0;
  font-size: 13px;
}

.stage-bullet {
  font-size: 12px;
  width: 16px;
  text-align: center;
  flex-shrink: 0;
}

.stage-list-label {
  color: var(--text-tertiary);
}

.stage-completed .stage-bullet {
  color: $tableau-green;
}
.stage-completed .stage-list-label {
  color: $tableau-green;
}

.stage-active .stage-bullet {
  color: $tableau-blue;
}
.stage-active .stage-list-label {
  color: $tableau-blue;
  font-weight: 500;
}

.stage-pending .stage-bullet {
  color: var(--text-disabled);
}
.stage-pending .stage-list-label {
  color: var(--text-tertiary);
}

.stage-error .stage-bullet {
  color: $tableau-red;
}
.stage-error .stage-list-label {
  color: $tableau-red;
}

/* 错误信息 */
.error-info {
  font-size: 13px;
  color: $tableau-red;
  margin-top: 4px;
}
</style>
