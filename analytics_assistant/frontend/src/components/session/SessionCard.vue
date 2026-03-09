<template>
  <div
    class="session-card"
    :class="{ active: isActive }"
    role="button"
    tabindex="0"
    :aria-label="`${$t('session.title')}: ${session.title}`"
    @click="$emit('select', session)"
    @keydown.enter="$emit('select', session)"
    @keydown.space.prevent="$emit('select', session)"
  >
    <div class="session-content">
      <h4 class="session-title">{{ session.title }}</h4>
      <p class="session-time">{{ formatTimestamp(session.updated_at) }}</p>
    </div>
    <div class="session-actions">
      <button
        class="action-btn"
        :aria-label="$t('session.rename')"
        @click.stop="$emit('rename', session)"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path
            d="M12.146.146a.5.5 0 01.708 0l3 3a.5.5 0 010 .708l-10 10a.5.5 0 01-.168.11l-5 2a.5.5 0 01-.65-.65l2-5a.5.5 0 01.11-.168l10-10zM11.207 2.5L13.5 4.793 14.793 3.5 12.5 1.207 11.207 2.5zm1.586 2.793L10.5 3 4 9.5 3.293 11.5 5.293 10.793 11.793 5.293z"
          />
        </svg>
      </button>
      <button
        class="action-btn delete-btn"
        :aria-label="$t('session.delete')"
        @click.stop="$emit('delete', session)"
      >
        <svg width="16" height="16" viewBox="0 0 16 16" fill="currentColor">
          <path
            d="M5.5 5.5A.5.5 0 016 6v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm2.5 0a.5.5 0 01.5.5v6a.5.5 0 01-1 0V6a.5.5 0 01.5-.5zm3 .5a.5.5 0 00-1 0v6a.5.5 0 001 0V6z"
          />
          <path
            fill-rule="evenodd"
            d="M14.5 3a1 1 0 01-1 1H13v9a2 2 0 01-2 2H5a2 2 0 01-2-2V4h-.5a1 1 0 01-1-1V2a1 1 0 011-1H6a1 1 0 011-1h2a1 1 0 011 1h3.5a1 1 0 011 1v1zM4.118 4L4 4.059V13a1 1 0 001 1h6a1 1 0 001-1V4.059L11.882 4H4.118zM2.5 3V2h11v1h-11z"
            clip-rule="evenodd"
          />
        </svg>
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import type { Session } from '@/types'
import { formatTimestamp } from '@/utils'

defineProps<{
  session: Session
  isActive: boolean
}>()

defineEmits<{
  select: [session: Session]
  rename: [session: Session]
  delete: [session: Session]
}>()
</script>

<style scoped>
.session-card {
  display: flex;
  align-items: center;
  gap: var(--spacing-sm);
  padding: var(--spacing-md);
  border-radius: var(--radius-md);
  cursor: pointer;
  transition: background-color var(--transition-fast);
}

.session-card:hover {
  background-color: var(--color-bg-hover);
}

.session-card.active {
  background-color: var(--color-bg-tertiary);
}

.session-card:focus-visible {
  outline: 2px solid var(--color-primary);
  outline-offset: -2px;
}

.session-content {
  flex: 1;
  min-width: 0;
}

.session-title {
  font-size: var(--font-size-md);
  font-weight: var(--font-weight-medium);
  color: var(--color-text-primary);
  margin-bottom: var(--spacing-xs);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.session-time {
  font-size: var(--font-size-xs);
  color: var(--color-text-tertiary);
}

.session-actions {
  display: flex;
  gap: var(--spacing-xs);
  opacity: 0;
  transition: opacity var(--transition-fast);
}

.session-card:hover .session-actions,
.session-card:focus-within .session-actions {
  opacity: 1;
}

.action-btn {
  display: inline-flex;
  align-items: center;
  justify-content: center;
  width: 28px;
  height: 28px;
  color: var(--color-text-tertiary);
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
