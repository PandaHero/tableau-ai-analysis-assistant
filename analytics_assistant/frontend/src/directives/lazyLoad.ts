/**
 * 图片懒加载指令
 * 使用 Intersection Observer API 实现
 */
import type { Directive, DirectiveBinding } from 'vue'

interface LazyLoadElement extends HTMLElement {
  _lazyLoadObserver?: IntersectionObserver
}

/**
 * 图片懒加载指令
 * 
 * 使用方式:
 * <img v-lazy-load="imageUrl" alt="..." />
 * 
 * 或带配置:
 * <img v-lazy-load="{ src: imageUrl, placeholder: placeholderUrl }" alt="..." />
 */
export const lazyLoad: Directive = {
  mounted(el: LazyLoadElement, binding: DirectiveBinding) {
    // 解析配置
    const config = typeof binding.value === 'string'
      ? { src: binding.value }
      : binding.value

    const { src, placeholder, rootMargin = '50px', threshold = 0.01 } = config

    // 设置占位图
    if (placeholder && el.tagName === 'IMG') {
      (el as HTMLImageElement).src = placeholder
    }

    // 创建 Intersection Observer
    const observer = new IntersectionObserver(
      (entries) => {
        entries.forEach((entry) => {
          if (entry.isIntersecting) {
            const target = entry.target as HTMLImageElement

            // 加载图片
            if (target.tagName === 'IMG') {
              // 图片元素
              const img = new Image()
              
              img.onload = () => {
                target.src = src
                target.classList.add('lazy-loaded')
              }
              
              img.onerror = () => {
                target.classList.add('lazy-error')
                console.error(`Failed to load image: ${src}`)
              }
              
              img.src = src
            } else {
              // 背景图片
              target.style.backgroundImage = `url(${src})`
              target.classList.add('lazy-loaded')
            }

            // 停止观察
            observer.unobserve(target)
          }
        })
      },
      {
        rootMargin,
        threshold
      }
    )

    // 开始观察
    observer.observe(el)

    // 保存 observer 引用,用于清理
    el._lazyLoadObserver = observer
  },

  unmounted(el: LazyLoadElement) {
    // 清理 observer
    if (el._lazyLoadObserver) {
      el._lazyLoadObserver.disconnect()
      delete el._lazyLoadObserver
    }
  }
}

/**
 * 注册懒加载指令
 */
export function registerLazyLoadDirective(app: any) {
  app.directive('lazy-load', lazyLoad)
}
