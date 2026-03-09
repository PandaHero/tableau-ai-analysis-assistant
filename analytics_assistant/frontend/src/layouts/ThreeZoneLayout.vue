<template>
  <div class="three-zone-layout">
    <div class="layout-glow layout-glow--top" aria-hidden="true"></div>
    <div class="layout-glow layout-glow--bottom" aria-hidden="true"></div>

    <header class="header-zone">
      <slot name="header" />
    </header>

    <main class="content-zone">
      <slot name="content" />
    </main>

    <footer class="input-zone">
      <slot name="input" />
    </footer>
  </div>
</template>

<script setup lang="ts"></script>

<style scoped lang="scss">
@use '@/assets/styles/variables.scss' as *;

.three-zone-layout {
  position: relative;
  display: grid;
  grid-template-rows: 56px minmax(0, 1fr) auto;
  width: 100%;
  height: 100vh;
  overflow: hidden;
  background:
    linear-gradient(180deg, rgba(248, 250, 252, 0.96), rgba(242, 245, 248, 0.96));
}

.layout-glow {
  position: absolute;
  border-radius: 999px;
  pointer-events: none;
  opacity: 0.65;
}

.layout-glow--top {
  top: -140px;
  right: -90px;
  width: 360px;
  height: 360px;
  background: radial-gradient(circle, rgba(31, 119, 180, 0.12) 0%, transparent 70%);
}

.layout-glow--bottom {
  left: -120px;
  bottom: -180px;
  width: 420px;
  height: 420px;
  background: radial-gradient(circle, rgba(255, 127, 14, 0.08) 0%, transparent 70%);
}

.header-zone {
  position: relative;
  z-index: $z-index-sticky;
  border-bottom: 1px solid rgba(15, 23, 42, 0.06);
  box-shadow: 0 1px 0 rgba(255, 255, 255, 0.55);
}

.content-zone {
  position: relative;
  z-index: 1;
  min-height: 0;
  overflow-y: auto;
  overflow-x: hidden;
}

.content-zone::-webkit-scrollbar {
  width: 8px;
}

.content-zone::-webkit-scrollbar-track {
  background: transparent;
}

.content-zone::-webkit-scrollbar-thumb {
  background: var(--scrollbar-thumb);
  border-radius: 999px;
}

.input-zone {
  position: relative;
  z-index: $z-index-sticky;
  padding-bottom: 8px;
}

:global([data-theme='dark']) .three-zone-layout {
  background: linear-gradient(180deg, #131821 0%, #0f141b 100%);
}

:global([data-theme='dark']) .header-zone {
  border-bottom-color: rgba(255, 255, 255, 0.08);
  box-shadow: none;
}
</style>
