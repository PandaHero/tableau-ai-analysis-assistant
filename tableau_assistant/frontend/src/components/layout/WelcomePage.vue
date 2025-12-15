<template>
  <div class="welcome-container">
    <div class="welcome-card">
      <h2 class="welcome-title">{{ t('welcome.title') }}</h2>
      <p class="welcome-desc">{{ t('welcome.subtitle') }}</p>
      
      <div class="example-section">
        <div class="example-label">💡 {{ t('welcome.examples.title') }}</div>
        <ul class="example-list">
          <li 
            v-for="(example, index) in examples" 
            :key="index"
            class="example-item"
            @click="handleExampleClick(example)"
          >
            {{ example }}
          </li>
        </ul>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { useI18n } from '@/utils/i18n'

const { t } = useI18n()

const examples = computed(() => [
  t('welcome.example.1'),
  t('welcome.example.2'),
  t('welcome.example.3')
])

const emit = defineEmits<{
  selectExample: [text: string]
}>()

function handleExampleClick(example: string) {
  emit('selectExample', example)
}
</script>

<style scoped>
.welcome-container {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 20px;
}

.welcome-card {
  max-width: 500px;
  padding: 32px;
  background: var(--color-card);
  border: 1px solid var(--color-border);
  border-radius: 12px;
  text-align: center;
}

.welcome-title {
  font-size: 20px;
  font-weight: 600;
  color: var(--color-text);
  margin: 0 0 12px 0;
}

.welcome-desc {
  font-size: 14px;
  color: var(--color-text-secondary);
  margin: 0 0 24px 0;
}

.example-section {
  text-align: left;
}

.example-label {
  font-size: 14px;
  font-weight: 500;
  color: var(--color-text);
  margin-bottom: 12px;
}

.example-list {
  list-style: none;
  padding: 0;
  margin: 0;
}

.example-item {
  padding: 12px 16px;
  margin-bottom: 8px;
  background: var(--btn-bg);
  border-radius: 8px;
  font-size: 14px;
  color: var(--color-text);
  cursor: pointer;
  transition: all 0.2s;
}

.example-item:hover {
  background: var(--btn-bg-hover);
  color: var(--tableau-blue);
}

.example-item:last-child {
  margin-bottom: 0;
}
</style>
