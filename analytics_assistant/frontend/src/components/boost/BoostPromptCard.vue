<template>
  <div
    class="boost-prompt-card"
    role="button"
    tabindex="0"
    :aria-label="prompt.title"
    @click="$emit('select', prompt)"
    @keydown.enter="$emit('select', prompt)"
    @keydown.space.prevent="$emit('select', prompt)"
  >
    <div class="card-content">
      <h4 class="card-title">{{ prompt.title }}</h4>
      <p class="card-description">{{ prompt.content }}</p>
    </div>
    <div v-if="!prompt.builtin" class="card-actions">
      <button
        class="action-btn"
        :aria-label="$t('boost.edit')"
        @click.stop="$emit('edit', prompt)"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path
            d="M12.146.146a.5.5 0 01.708 0l3 3a.5.5 0 010 .708l-10 10a.5.5 0 01-.168.11l-5 2a.5.5 0 01-.65-.65l2-5a.5.5 0 01.11-.168l10-10z"
          />
        </svg>
      </button>
      <button
        class="action-btn delete-btn"
        :aria-label="$t('boost.delete')"
        @click.stop="$emit('delete', prompt)"
      >
        <svg width="14" height="14" viewBox="0 0 16 16" fill="currentColor">
          <path
            d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"
          />
          <path
            fill-rule="evenodd"
            d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H6a1 1 0 011-1h2a1 1 0 011 1h3.5a1 1 0 011 1v1z"
            clip-rule="evenodd"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { BoostPrompt } from '@/types'

defineProps<{
  prompt: BoostPrompt
}>()

defineEmits<{
  select: [prompt: BoostPrompt]
  edit: [prompt: BoostPrompt]
  delete: [prompt: BoostPrompt]
}>()
</script>

<style scoped>
.boost-prompt-card {
  position: relative;
  padding: var(--spacing-md);
  border: 1px solid var(--color-border-light);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: all var(--transition-fast);
}

.boost-prompt-card:hover {
  border-color: var(--color-primary);
  box-shadow: var(--shadow-sm);
}

.boost-prompt-card:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: 2px;
}

.card-content {
  padding-right: var(--spacing-lg);
}

.card-title {
  font-size: var(--font-size-sm);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
}

.card-description {
  font-size: var(--font-size-xs);
  color: var(--color-text-secondary);
  line-height: var(--line-height-normal);
  display: -webkit-box;
  -webkit-line-clamp: 2;
  -webkit-box-orient: vertical;
  overflow: hidden;
}

.card-actions {
  position: absolute;
  top: var(--spacing-sm);
  right: var(--spacing-sm);
  display: flex;
  gap: var(--spacing-xs);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.boost-prompt-card:hover .card-actions,
.boost-prompt-card:focus-within .card-actions {
  opacity: 1;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 24px;
  height: 24px;
  color: var(--color-text-tertiary);
  background-color: var(--color-bg-primary);
  border-radius: var(--radius-sm);
  transition: all var(--transition-fast);
}

.action-btn:hover {
  color: var(--color-text-secondary);
  background-color: var(--color-bg-hover);
}

.action-btn.delete-btn:hover {
  color: var(--color-error);
}
</style>
