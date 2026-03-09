<template>
  <div class="loading-spinner" :class="{ small, large }" role="status" :aria-label="$t('common.loading')">
    <svg class="spinner" viewBox="0 0 50 50">
      <circle class="path" cx="25" cy="25" r="20" fill="none" stroke-width="4"></circle>
    </svg>
    <span v-if="text" class="loading-text">{{ text }}</span>
  </div>
</template>

<script setup lang="ts">
defineProps<{
  small?: boolean
  large?: boolean
  text?: string
}>()
</script>

<style scoped>
.loading-spinner {
  display: inline-flex;
  flex-direction: column;
  align-items: center;
  gap: var(--spacing-sm);
}

.spinner {
  width: 40px;
  height: 40px;
  animation: rotate 2s linear infinite;
}

.loading-spinner.small .spinner {
  width: 24px;
  height: 24px;
}

.loading-spinner.large .spinner {
  width: 60px;
  height: 60px;
}

.path {
  stroke: var(--color-primary);
  stroke-linecap: round;
  animation: dash 1.5s ease-in-out infinite;
}

.loading-text {
  font-size: var(--font-size-sm);
  color: var(--color-text-secondary);
}

@keyframes rotate {
  100% {
    transform: rotate(360deg);
  }
}

@keyframes dash {
  0% {
    stroke-dasharray: 1, 150;
    stroke-dashoffset: 0;
  }
  50% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -35;
  }
  100% {
    stroke-dasharray: 90, 150;
    stroke-dashoffset: -124;
  }
}
</style>
