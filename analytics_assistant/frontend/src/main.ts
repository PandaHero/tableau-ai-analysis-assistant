import { createApp } from 'vue'
import { createPinia } from 'pinia'
import ElementPlus from 'element-plus'
import * as ElementPlusIconsVue from '@element-plus/icons-vue'
import 'element-plus/dist/index.css'
import './styles/main.css'
// 导入新的设计系统样式
import './assets/styles/index.scss'
// 导入主题管理器
import { ThemeManager } from './design-system/theme'
// 导入懒加载指令
import { registerLazyLoadDirective } from './directives/lazyLoad'
// 导入焦点指示器
import { useFocusIndicator } from './composables/useKeyboardNavigation'

import App from './App.vue'
import router from './router'

const app = createApp(App)

// 注册所有 Element Plus 图标
for (const [key, component] of Object.entries(ElementPlusIconsVue)) {
  app.component(key, component)
}

app.use(createPinia())
app.use(router)
app.use(ElementPlus)

// 注册懒加载指令
registerLazyLoadDirective(app)

// 初始化主题管理器
const themeManager = ThemeManager.getInstance()
themeManager.init()

// 初始化焦点指示器
// 这会在用户使用键盘导航时自动添加 'keyboard-user' 类到 body
useFocusIndicator()

app.mount('#app')



