<!-- Logo 组件 -->
<template>
  <img
    :src="logoUrl"
    alt="Tableau AI Assistant"
    class="logo"
    :class="{ large: size === 'large' }"
  />
</template>

<script setup lang="ts">
import { computed } from 'vue'
import { extractLogoFromManifest } from '@/utils/logo'

interface Props {
  size?: 'normal' | 'large'
}

const props = withDefaults(defineProps<Props>(), {
  size: 'normal'
})

// 从 manifest.trex 提取 logo
const logoUrl = computed(() => extractLogoFromManifest())
</script>

<style scoped>
.logo {
  width: 32px;
  height: 32px;
  border-radius: 4px;
  object-fit: contain;
}

.logo.large {
  width: 64px;
  height: 64px;
}
</style>
