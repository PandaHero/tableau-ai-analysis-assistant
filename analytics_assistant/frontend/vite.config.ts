import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'
import yaml from 'js-yaml'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 项目根目录（和 settings.py 保持一致：向上2级 frontend -> analytics_assistant -> root）
const PROJECT_ROOT = path.resolve(__dirname, '../..')

// 更新 manifest.trex 中的 URL
function updateManifestUrl(appUrl: string) {
  const manifestPath = path.resolve(__dirname, 'public/manifest.trex')
  
  if (fs.existsSync(manifestPath)) {
    let content = fs.readFileSync(manifestPath, 'utf-8')
    content = content.replace(/<url>.*<\/url>/, `<url>${appUrl}</url>`)
    content = content.replace(/website="[^"]*"/, `website="${appUrl}"`)
    fs.writeFileSync(manifestPath, content)
    console.log(`✓ Updated manifest.trex with URL: ${appUrl}`)
  }
}

// https://vite.dev/config/
export default defineConfig(() => {
  // 从 app.yaml 加载配置
  const configPath = path.join(PROJECT_ROOT, 'analytics_assistant', 'config', 'app.yaml')
  
  if (!fs.existsSync(configPath)) {
    console.error(`❌ ERROR: Configuration file not found: ${configPath}`)
    throw new Error('Configuration file not found')
  }
  
  const configContent = fs.readFileSync(configPath, 'utf-8')
  const config = yaml.load(configContent) as any
  
  console.log(`✅ Loaded config from: ${configPath}`)
  
  // 读取配置
  const frontendConfig = config.frontend || {}
  const apiConfig = config.api || {}
  const sslConfig = config.ssl || {}
  
  const host = frontendConfig.host || '127.0.0.1'
  const port = frontendConfig.port || 8000
  const backendHost = apiConfig.host || '127.0.0.1'
  const backendPort = apiConfig.port || 5000

  // HTTPS 配置：从统一证书管理读取
  const activeCert = sslConfig.active_cert || 'localhost'
  const certificates = sslConfig.certificates || {}
  
  if (!certificates[activeCert]) {
    console.error(`❌ ERROR: Certificate configuration not found: ${activeCert}`)
    throw new Error(`Certificate configuration not found: ${activeCert}`)
  }
  
  const certConfig = certificates[activeCert]
  const sslCertFile = certConfig.cert_file
  const sslKeyFile = certConfig.key_file
  
  console.log('Vite Config - SSL Cert:', sslCertFile)
  console.log('Vite Config - SSL Key:', sslKeyFile)
  
  // 检查 SSL 配置
  if (!sslCertFile || !sslKeyFile) {
    console.error('❌ ERROR: SSL certificates are required!')
    console.error('   Please configure ssl.cert_file and ssl.key_file in app.yaml')
    throw new Error('SSL certificates are required')
  }
  
  const backendProtocol = 'https'
  const apiBaseUrl = frontendConfig.api_base_url || `${backendProtocol}://${backendHost}:${backendPort}`
  
  console.log('Vite Config - API Base URL:', apiBaseUrl)
  
  // 证书路径（相对于项目根目录）
  const certPath = path.resolve(PROJECT_ROOT, sslCertFile)
  const keyPath = path.resolve(PROJECT_ROOT, sslKeyFile)
  
  if (!fs.existsSync(certPath) || !fs.existsSync(keyPath)) {
    console.error('❌ ERROR: SSL certificate files not found!')
    console.error('   Cert path:', certPath)
    console.error('   Key path:', keyPath)
    throw new Error('SSL certificate files not found')
  }
  
  const httpsConfig = {
    cert: fs.readFileSync(certPath),
    key: fs.readFileSync(keyPath)
  }
  
  console.log('🔒 HTTPS enabled')
  console.log('   Cert:', certPath)
  console.log('   Key:', keyPath)
  
  // build 时 manifest.trex 指向后端地址（前端由后端 serve）
  const backendUrl = apiBaseUrl
  updateManifestUrl(backendUrl)
  console.log(`✓ manifest.trex URL set to: ${backendUrl}`)

  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    define: {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBaseUrl)
    },
    // build 产物输出到 dist/，供 FastAPI serve
    build: {
      outDir: 'dist',
      emptyOutDir: true,
      // 配置 chunk 大小警告限制（提高到 1500KB 以避免警告）
      chunkSizeWarningLimit: 1500,
      rollupOptions: {
        output: {
          // 手动分割 chunk，优化加载性能
          manualChunks: {
            // Vue 核心库
            'vue-vendor': ['vue', 'vue-router'],
            // UI 组件库（如果有的话）
            // 'ui-vendor': ['element-plus', ...],
          }
        }
      }
    },
    server: {
      host,
      port,
      https: httpsConfig,
      hmr: false,
      proxy: {
        '/api': {
          target: apiBaseUrl,
          changeOrigin: true,
          secure: false,
          rewrite: (p) => p.replace(/^\/api/, '')
        }
      }
    }
  }
})
