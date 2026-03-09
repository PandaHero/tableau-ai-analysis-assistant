# 设计系统 (Design System)

基于 Tableau 设计语言的前端设计系统。

## 目录结构

```
design-system/
├── tokens.ts       # 设计令牌 (颜色、字体、间距等)
├── theme.ts        # 主题管理器 (浅色/深色主题切换)
└── README.md       # 本文档

assets/styles/
├── variables.scss  # SCSS 变量
├── reset.scss      # 样式重置
├── theme.scss      # 主题样式
├── mixins.scss     # SCSS 混入
└── index.scss      # 主样式入口
```

## 使用方法

### 1. 设计令牌 (Design Tokens)

设计令牌定义了设计系统的基础值,包括颜色、字体、间距等。

```typescript
import { designTokens } from '@/design-system/tokens'

// 使用 Tableau 色板
const primaryColor = designTokens.colors.tableau.blue // #1F77B4

// 使用间距
const spacing = designTokens.spacing.md // 16px

// 使用字体
const fontSize = designTokens.typography.fontSize.base // 14px
```

### 2. 主题管理器 (Theme Manager)

主题管理器负责浅色/深色主题的切换和持久化。

```typescript
import { ThemeManager } from '@/design-system/theme'

// 获取单例实例
const themeManager = ThemeManager.getInstance()

// 初始化 (在 main.ts 中调用)
themeManager.init()

// 切换主题
themeManager.setTheme('dark')  // 'light' | 'dark' | 'auto'

// 获取当前主题
const currentTheme = themeManager.getTheme()

// 监听主题变化
themeManager.onThemeChange((theme) => {
  console.log('主题已切换:', theme)
})
```

### 3. SCSS 变量

在 Vue 组件中使用 SCSS 变量:

```vue
<style scoped lang="scss">
@import '@/assets/styles/variables.scss';

.my-component {
  color: $tableau-blue;
  padding: $spacing-md;
  border-radius: $radius-sm;
}
</style>
```

### 4. SCSS Mixins

使用预定义的 SCSS 混入:

```vue
<style scoped lang="scss">
@import '@/assets/styles/mixins.scss';

.my-button {
  @include button-primary;
  @include transition-fast(background-color, opacity);
}

.my-card {
  @include card;
  @include shadow-md;
}

// 响应式
.my-container {
  padding: 16px;
  
  @include breakpoint-down(sm) {
    padding: 8px;
  }
}
</style>
```

### 5. CSS 变量

在组件中使用 CSS 变量:

```vue
<style scoped>
.my-element {
  color: var(--text-primary);
  background-color: var(--bg-primary);
  border: 1px solid var(--border-color);
  box-shadow: var(--shadow-sm);
}
</style>
```

## 设计令牌参考

### 颜色系统

#### Tableau 10 色板
- `tableau.blue`: #1F77B4 (主蓝色)
- `tableau.orange`: #FF7F0E
- `tableau.green`: #2CA02C
- `tableau.red`: #D62728
- `tableau.purple`: #9467BD
- `tableau.brown`: #8C564B
- `tableau.pink`: #E377C2
- `tableau.gray`: #7F7F7F
- `tableau.olive`: #BCBD22
- `tableau.cyan`: #17BECF

#### 中性色系
- `neutral.white`: #FFFFFF
- `neutral.gray50`: #FAFAFA
- `neutral.gray100`: #F5F5F5
- `neutral.gray200`: #E0E0E0
- `neutral.gray300`: #CCCCCC
- `neutral.gray400`: #999999
- `neutral.gray500`: #666666
- `neutral.gray600`: #4D4D4D
- `neutral.gray700`: #333333
- `neutral.gray800`: #1A1A1A
- `neutral.gray900`: #0D0D0D

#### 语义色系
- `semantic.primary`: #1F77B4
- `semantic.success`: #2CA02C
- `semantic.warning`: #FF7F0E
- `semantic.error`: #D62728
- `semantic.info`: #1F77B4

### 间距系统 (8px 基准)
- `xs`: 4px
- `sm`: 8px
- `md`: 16px
- `lg`: 24px
- `xl`: 32px
- `xxl`: 48px

### 圆角系统
- `sm`: 8px
- `md`: 12px
- `lg`: 16px
- `full`: 9999px

### 阴影系统
- `sm`: 0 1px 3px rgba(0, 0, 0, 0.08)
- `md`: 0 2px 8px rgba(0, 0, 0, 0.12)
- `lg`: 0 4px 16px rgba(0, 0, 0, 0.16)
- `xl`: 0 8px 24px rgba(0, 0, 0, 0.20)

### 字体系统
- 字号: xs(12px), sm(13px), base(14px), md(15px), lg(16px), xl(18px), xxl(20px), 3xl(24px)
- 字重: normal(400), medium(500), semibold(600), bold(700)
- 行高: tight(1.25), normal(1.5), relaxed(1.75)

### 过渡动画
- `fast`: 150ms ease-out
- `normal`: 200ms ease-out
- `slow`: 300ms ease-out
- `spring`: 300ms cubic-bezier(0.34, 1.56, 0.64, 1)

## 响应式断点

- `xs`: 320px
- `sm`: 480px
- `md`: 768px
- `lg`: 1024px
- `xl`: 1280px

## 布局尺寸

- `headerHeight`: 48px
- `inputAreaHeight`: 64px
- `inputMinHeight`: 40px
- `inputMaxHeight`: 120px
- `settingsPanelWidth`: 360px

## 最佳实践

### 1. 优先使用 CSS 变量

CSS 变量支持主题切换,优先使用:

```css
/* ✅ 推荐 */
color: var(--text-primary);

/* ❌ 不推荐 */
color: #333333;
```

### 2. 使用 SCSS Mixins 减少重复

```scss
/* ✅ 推荐 */
@include button-primary;
@include flex-center;

/* ❌ 不推荐 */
display: flex;
align-items: center;
justify-content: center;
background-color: var(--color-primary);
color: var(--text-inverse);
```

### 3. 遵循间距系统

```scss
/* ✅ 推荐 */
padding: $spacing-md;
margin-bottom: $spacing-lg;

/* ❌ 不推荐 */
padding: 15px;
margin-bottom: 20px;
```

### 4. 使用响应式 Mixins

```scss
/* ✅ 推荐 */
@include breakpoint-down(sm) {
  padding: $spacing-sm;
}

/* ❌ 不推荐 */
@media (max-width: 479px) {
  padding: 8px;
}
```

## 主题切换示例

```vue
<template>
  <button @click="toggleTheme">
    切换主题
  </button>
</template>

<script setup lang="ts">
import { ThemeManager } from '@/design-system/theme'

const themeManager = ThemeManager.getInstance()

const toggleTheme = () => {
  const current = themeManager.getTheme()
  const next = current === 'light' ? 'dark' : 'light'
  themeManager.setTheme(next)
}
</script>
```

## 参考资源

- [Tableau 设计语言](https://www.tableau.com/design)
- [Tableau 10 色板](https://www.tableau.com/about/blog/2016/7/colors-upgrade-tableau-10-56782)
