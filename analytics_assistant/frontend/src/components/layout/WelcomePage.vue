<template>
  <section class="welcome-shell">
    <div class="ambient ambient-left" aria-hidden="true"></div>
    <div class="ambient ambient-right" aria-hidden="true"></div>

    <div class="welcome-stage">
      <div class="hero-panel">
        <div class="hero-badge">
          <span class="hero-badge__dot"></span>
          <span>Tableau 智能分析工作台</span>
        </div>

        <div class="hero-title-row">
          <span class="hero-emoji">{{ greetingIcon }}</span>
          <div>
            <p class="hero-kicker">数据助手已就绪</p>
            <h1 class="hero-title">{{ greetingWord }}</h1>
          </div>
        </div>

        <p class="hero-subtitle">
          我会结合当前 Tableau 数据源，帮你快速定位趋势、异常和可执行结论。
        </p>

        <div class="hero-stats">
          <article class="stat-card">
            <span class="stat-label">数据源</span>
            <strong class="stat-value">{{ datasourceSummary }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">分析模式</span>
            <strong class="stat-value">{{ analysisDepthLabel }}</strong>
          </article>
          <article class="stat-card">
            <span class="stat-label">当前环境</span>
            <strong class="stat-value">{{ environmentLabel }}</strong>
          </article>
        </div>
      </div>

      <div class="examples-panel">
        <div class="panel-heading">
          <div>
            <p class="panel-kicker">快速开始</p>
            <h2 class="panel-title">从这些问题切入</h2>
          </div>
          <p class="panel-description">点击示例即可直接发起分析，也可以在下方输入自己的业务问题。</p>
        </div>

        <div class="examples-grid">
          <button
            v-for="(example, index) in exampleCards"
            :key="example.text"
            class="example-card"
            type="button"
            :style="{ '--card-delay': `${index * 0.07}s` }"
            @click="handleExampleClick(example.text)"
          >
            <span class="example-card__index">0{{ index + 1 }}</span>
            <div class="example-card__icon" :class="`tone-${index + 1}`">
              <svg
                v-if="index === 0"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <polyline points="22 12 18 12 15 21 9 3 6 12 2 12" />
              </svg>
              <svg
                v-else-if="index === 1"
                viewBox="0 0 24 24"
                fill="none"
                aria-hidden="true"
              >
                <circle cx="11" cy="11" r="8" />
                <line x1="21" y1="21" x2="16.65" y2="16.65" />
              </svg>
              <svg v-else viewBox="0 0 24 24" fill="none" aria-hidden="true">
                <line x1="18" y1="20" x2="18" y2="10" />
                <line x1="12" y1="20" x2="12" y2="4" />
                <line x1="6" y1="20" x2="6" y2="14" />
              </svg>
            </div>

            <div class="example-card__body">
              <p class="example-card__title">{{ example.text }}</p>
              <span class="example-card__hint">{{ example.hint }}</span>
            </div>

            <span class="example-card__arrow" aria-hidden="true">
              <svg viewBox="0 0 24 24" fill="none">
                <line x1="5" y1="12" x2="19" y2="12" />
                <polyline points="12 5 19 12 12 19" />
              </svg>
            </span>
          </button>
        </div>
      </div>
    </div>
  </section>
</template>

<script setup lang="ts">
import { computed } from 'vue'

import { useSettingsStore } from '@/stores/settings'
import { useTableauStore } from '@/stores/tableau'
import { useI18n } from '@/utils/i18n'

const { t } = useI18n()
const settingsStore = useSettingsStore()
const tableauStore = useTableauStore()

const greetingWord = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return '上午好'
  if (hour < 18) return '下午好'
  return '晚上好'
})

const greetingIcon = computed(() => {
  const hour = new Date().getHours()
  if (hour < 12) return '☀'
  if (hour < 18) return '✦'
  return '☾'
})

const datasourceSummary = computed(() => {
  if (settingsStore.datasourceName) {
    return settingsStore.datasourceName
  }

  if (tableauStore.selectedDataSource?.name) {
    return tableauStore.selectedDataSource.name
  }

  return tableauStore.dataSources.length > 0
    ? `已发现 ${tableauStore.dataSources.length} 个`
    : '自动检测'
})

const analysisDepthLabel = computed(() =>
  settingsStore.analysisDepth === 'comprehensive' ? '深入分析' : '标准分析',
)

const environmentLabel = computed(() => {
  if (tableauStore.isInTableau) {
    return 'Tableau 环境'
  }

  return '浏览器调试'
})

const exampleCards = computed(() => [
  {
    text: t('welcome.example.1') || '各产品线的销售额是多少？',
    hint: '按产品维度快速看整体表现',
  },
  {
    text: t('welcome.example.2') || '哪个地区的利润率最高？',
    hint: '定位区域差异和高利润板块',
  },
  {
    text: t('welcome.example.3') || '最近一个月的销售趋势如何？',
    hint: '查看近期走势和变化拐点',
  },
])

const emit = defineEmits<{
  selectExample: [text: string]
}>()

function handleExampleClick(example: string) {
  emit('selectExample', example)
}
</script>

<style scoped lang="scss">
@use '@/assets/styles/variables.scss' as *;

.welcome-shell {
  position: relative;
  min-height: 100%;
  padding: 34px 28px 18px;
  overflow: hidden;
  background:
    radial-gradient(circle at 12% 18%, rgba(31, 119, 180, 0.10), transparent 28%),
    radial-gradient(circle at 88% 12%, rgba(23, 190, 207, 0.10), transparent 24%),
    linear-gradient(180deg, #f7f9fc 0%, #f2f4f7 100%);
}

.ambient {
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
  opacity: 0.7;
}

.ambient-left {
  width: 380px;
  height: 380px;
  left: -140px;
  bottom: -120px;
  background: radial-gradient(circle, rgba(255, 127, 14, 0.12) 0%, transparent 70%);
}

.ambient-right {
  width: 440px;
  height: 440px;
  top: -160px;
  right: -120px;
  background: radial-gradient(circle, rgba(31, 119, 180, 0.14) 0%, transparent 70%);
}

.welcome-stage {
  position: relative;
  z-index: 1;
  max-width: 1040px;
  margin: 0 auto;
  display: grid;
  grid-template-columns: minmax(0, 1.2fr) minmax(0, 1fr);
  gap: 20px;
  align-items: stretch;
}

.hero-panel,
.examples-panel {
  position: relative;
  border-radius: 28px;
  border: 1px solid rgba(15, 23, 42, 0.07);
  background: rgba(255, 255, 255, 0.84);
  box-shadow:
    0 18px 45px rgba(15, 23, 42, 0.08),
    inset 0 1px 0 rgba(255, 255, 255, 0.78);
}

.hero-panel {
  padding: 28px;
  display: flex;
  flex-direction: column;
  justify-content: space-between;
  gap: 22px;
}

.hero-badge {
  width: fit-content;
  display: inline-flex;
  align-items: center;
  gap: 8px;
  padding: 8px 14px;
  border-radius: 999px;
  background: rgba(31, 119, 180, 0.10);
  color: #0c5e98;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.04em;
}

.hero-badge__dot {
  width: 8px;
  height: 8px;
  border-radius: 50%;
  background: #1f77b4;
  box-shadow: 0 0 0 5px rgba(31, 119, 180, 0.14);
}

.hero-title-row {
  display: flex;
  align-items: center;
  gap: 16px;
}

.hero-emoji {
  width: 64px;
  height: 64px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 20px;
  background: linear-gradient(135deg, rgba(255, 183, 77, 0.22), rgba(255, 127, 14, 0.12));
  color: #ff8a00;
  font-size: 32px;
  box-shadow: inset 0 1px 0 rgba(255, 255, 255, 0.7);
}

.hero-kicker {
  margin: 0 0 6px;
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.hero-title {
  margin: 0;
  font-size: clamp(34px, 5vw, 52px);
  line-height: 1.02;
  font-weight: 800;
  letter-spacing: -0.04em;
  color: #0f172a;
}

.hero-subtitle {
  margin: 0;
  max-width: 520px;
  color: var(--text-secondary);
  font-size: 15px;
  line-height: 1.75;
}

.hero-stats {
  display: grid;
  grid-template-columns: repeat(3, minmax(0, 1fr));
  gap: 12px;
}

.stat-card {
  padding: 16px 14px;
  border-radius: 18px;
  background: linear-gradient(180deg, rgba(247, 249, 252, 0.92), rgba(241, 244, 248, 0.85));
  border: 1px solid rgba(15, 23, 42, 0.06);
}

.stat-label {
  display: block;
  margin-bottom: 8px;
  font-size: 12px;
  color: var(--text-tertiary);
}

.stat-value {
  display: block;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.4;
}

.examples-panel {
  padding: 24px;
}

.panel-heading {
  display: flex;
  flex-direction: column;
  gap: 8px;
  margin-bottom: 20px;
}

.panel-kicker {
  margin: 0;
  color: #1f77b4;
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
  text-transform: uppercase;
}

.panel-title {
  margin: 0;
  color: var(--text-primary);
  font-size: 26px;
  line-height: 1.1;
}

.panel-description {
  margin: 0;
  color: var(--text-secondary);
  font-size: 14px;
  line-height: 1.7;
}

.examples-grid {
  display: grid;
  gap: 12px;
}

.example-card {
  width: 100%;
  display: grid;
  grid-template-columns: auto auto minmax(0, 1fr) auto;
  align-items: center;
  gap: 14px;
  padding: 16px 18px;
  border: 1px solid rgba(15, 23, 42, 0.08);
  border-radius: 20px;
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.94), rgba(248, 250, 252, 0.92));
  text-align: left;
  cursor: pointer;
  transition:
    transform 180ms ease,
    border-color 180ms ease,
    box-shadow 180ms ease,
    background 180ms ease;
  animation: card-enter 420ms ease var(--card-delay, 0s) both;
}

.example-card:hover {
  transform: translateY(-2px);
  border-color: rgba(31, 119, 180, 0.24);
  box-shadow: 0 18px 35px rgba(31, 119, 180, 0.10);
}

.example-card__index {
  color: var(--text-tertiary);
  font-size: 12px;
  font-weight: 700;
  letter-spacing: 0.08em;
}

.example-card__icon {
  width: 42px;
  height: 42px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 14px;
}

.example-card__icon svg {
  width: 20px;
  height: 20px;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

.tone-1 {
  background: rgba(31, 119, 180, 0.12);
  color: #1f77b4;
}

.tone-2 {
  background: rgba(13, 175, 191, 0.12);
  color: #0b98a6;
}

.tone-3 {
  background: rgba(44, 160, 44, 0.12);
  color: #238023;
}

.example-card__body {
  min-width: 0;
}

.example-card__title {
  margin: 0 0 6px;
  color: var(--text-primary);
  font-size: 15px;
  line-height: 1.55;
  font-weight: 600;
}

.example-card__hint {
  color: var(--text-tertiary);
  font-size: 12px;
}

.example-card__arrow {
  width: 34px;
  height: 34px;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  border-radius: 12px;
  background: rgba(31, 119, 180, 0.08);
  color: #1f77b4;
}

.example-card__arrow svg {
  width: 16px;
  height: 16px;
  stroke: currentColor;
  stroke-width: 2;
  stroke-linecap: round;
  stroke-linejoin: round;
}

:global([data-theme='dark']) .welcome-shell {
  background:
    radial-gradient(circle at 16% 20%, rgba(31, 119, 180, 0.18), transparent 28%),
    radial-gradient(circle at 90% 12%, rgba(23, 190, 207, 0.14), transparent 24%),
    linear-gradient(180deg, #171a1f 0%, #12151a 100%);
}

:global([data-theme='dark']) .hero-panel,
:global([data-theme='dark']) .examples-panel {
  background: rgba(20, 24, 31, 0.84);
  border-color: rgba(255, 255, 255, 0.08);
  box-shadow:
    0 24px 48px rgba(0, 0, 0, 0.34),
    inset 0 1px 0 rgba(255, 255, 255, 0.04);
}

:global([data-theme='dark']) .hero-title {
  color: #f8fafc;
}

:global([data-theme='dark']) .hero-emoji {
  background: linear-gradient(135deg, rgba(255, 170, 0, 0.18), rgba(255, 127, 14, 0.10));
}

:global([data-theme='dark']) .hero-badge {
  background: rgba(31, 119, 180, 0.16);
  color: #8fcfff;
}

:global([data-theme='dark']) .stat-card,
:global([data-theme='dark']) .example-card {
  background: linear-gradient(180deg, rgba(255, 255, 255, 0.04), rgba(255, 255, 255, 0.03));
  border-color: rgba(255, 255, 255, 0.08);
}

:global([data-theme='dark']) .example-card:hover {
  border-color: rgba(93, 173, 226, 0.34);
  box-shadow: 0 18px 35px rgba(4, 30, 49, 0.55);
}

@media (max-width: 980px) {
  .welcome-stage {
    grid-template-columns: 1fr;
  }
}

@media (max-width: 767px) {
  .welcome-shell {
    padding: 22px 16px 12px;
  }

  .hero-panel,
  .examples-panel {
    padding: 20px;
    border-radius: 22px;
  }

  .hero-title-row {
    align-items: flex-start;
  }

  .hero-stats {
    grid-template-columns: 1fr;
  }

  .example-card {
    grid-template-columns: auto minmax(0, 1fr) auto;
  }

  .example-card__index {
    display: none;
  }
}

@keyframes card-enter {
  from {
    opacity: 0;
    transform: translateY(10px);
  }

  to {
    opacity: 1;
    transform: translateY(0);
  }
}
</style>
