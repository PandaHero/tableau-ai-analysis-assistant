<template>
  <div class="thinking-indicator">
    <div class="indicator-avatar">
      <img src="@/assets/tableau_logo.svg" alt="AI" width="24" height="24" />
    </div>
    <div class="indicator-content">
      <div class="dots">
        <span class="dot"></span>
        <span class="dot"></span>
        <span class="dot"></span>
      </div>
      <span class="stage-text">{{ stageLabel }}</span>
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

// 阶段到翻译 key 的映射
const STAGE_KEYS: Record<ProcessingStage, string> = {
  understanding: 'thinking.understanding',
  building: 'thinking.building',
  executing: 'thinking.executing',
  generating: 'thinking.generating',
  replanning: 'thinking.replanning',
  error: 'thinking.error',
}

const stageLabel = computed(() => {
  if (!props.stage) return t('thinking.understanding')
  const key = STAGE_KEYS[props.stage]
  return key ? t(key) : t('thinking.understanding')
})
</script>

<style scoped>
.thinking-indicator {
  display: flex;
  gap: 12px;
  align-items: flex-start;
}

.indicator-avatar {
  flex-shrink: 0;
  width: 36px;
  height: 36px;
  border-radius: 50%;
  background: linear-gradient(135deg, #f8f9fa 0%, #e9ecef 100%);
  display: flex;
  align-items: center;
  justify-content: center;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.06);
}

.indicator-content {
  display: flex;
  align-items: center;
  gap: 12px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 4px 18px 18px 18px;
  padding: 12px 20px;
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.06);
}

.dots {
  display: flex;
  gap: 5px;
}

.dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: linear-gradient(135deg, var(--tableau-blue) 0%, #4a9eda 100%);
  animation: bounce 1.4s infinite ease-in-out both;
}

.dot:nth-child(1) {
  animation-delay: -0.32s;
}

.dot:nth-child(2) {
  animation-delay: -0.16s;
}

.dot:nth-child(3) {
  animation-delay: 0s;
}

@keyframes bounce {
  0%, 80%, 100% {
    transform: scale(0.6);
    opacity: 0.4;
  }
  40% {
    transform: scale(1);
    opacity: 1;
  }
}

.stage-text {
  font-size: 13px;
  font-weight: 500;
  color: var(--color-text-secondary);
  letter-spacing: 0.3px;
}

/* 深色模式 */
html.dark .indicator-avatar {
  background: linear-gradient(135deg, #3a3a3a 0%, #2d2d2d 100%);
}

html.dark .indicator-content {
  box-shadow: 0 2px 12px rgba(0, 0, 0, 0.2);
}
</style>
