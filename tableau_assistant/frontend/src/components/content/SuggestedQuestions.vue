<template>
  <div v-if="suggestions.length" class="suggested-questions">
    <span class="label">💬 继续探索：</span>
    <div class="chips">
      <button 
        v-for="(question, i) in displayedQuestions" 
        :key="i"
        class="chip"
        @click="$emit('select', question)"
      >
        {{ question }}
      </button>
      <button 
        v-if="hasMore && !expanded"
        class="chip more-btn"
        @click="expanded = true"
      >
        更多 ▼
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
/**
 * SuggestedQuestions 组件
 * 推荐问题芯片
 * Requirements: 9.1, 9.2, 9.3, 9.4, 9.5, 9.6
 */
import { ref, computed } from 'vue'

const props = defineProps<{
  suggestions: string[]
}>()

defineEmits<{
  select: [question: string]
}>()

const expanded = ref(false)

const hasMore = computed(() => props.suggestions.length > 3)

const displayedQuestions = computed(() => {
  if (expanded.value || !hasMore.value) {
    return props.suggestions
  }
  return props.suggestions.slice(0, 3)
})
</script>

<style scoped>
.suggested-questions {
  margin-top: 16px;
  padding-top: 12px;
  border-top: 1px solid var(--color-border);
}

.label {
  display: block;
  font-size: 13px;
  color: var(--color-text-secondary);
  font-weight: 500;
  margin-bottom: 10px;
}

.chips {
  display: flex;
  flex-wrap: wrap;
  gap: 8px;
}

.chip {
  background: var(--btn-bg);
  border: 1px solid var(--color-border);
  border-radius: 16px;
  padding: 8px 16px;
  font-size: 13px;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s ease;
}

.chip:hover {
  background: var(--btn-bg-hover);
  border-color: var(--tableau-blue);
  color: var(--tableau-blue);
}

.chip:active {
  transform: scale(0.98);
}

.more-btn {
  background: transparent;
  border-style: dashed;
  color: var(--color-text-secondary);
}

.more-btn:hover {
  background: var(--btn-bg);
  color: var(--color-text);
}
</style>
