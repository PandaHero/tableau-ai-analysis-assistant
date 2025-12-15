import { fileURLToPath, URL } from 'node:url'
import { defineConfig } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'node:fs'
import path from 'node:path'
import dotenv from 'dotenv'

const __dirname = path.dirname(fileURLToPath(import.meta.url))

// 项目根目录（和 settings.py 保持一致：向上2级 frontend -> tableau_assistant -> root）
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
  // 从项目根目录加载 .env（和 settings.py 保持一致）
  const envPath = path.join(PROJECT_ROOT, '.env')
  if (fs.existsSync(envPath)) {
    dotenv.config({ path: envPath })
    console.log(`✅ Loaded .env from: ${envPath}`)
  } else {
    console.warn(`⚠️  .env not found at: ${envPath}`)
  }
  
  const env = process.env
  
  const host = env.VITE_APP_HOST || '127.0.0.1'
  const port = parseInt(env.VITE_APP_PORT || '5173')
  const backendHost = env.HOST || '127.0.0.1'
  const backendPort = env.PORT || '8000'
  
  // 前端应用 URL（用于 manifest.trex）
  const appUrl = `https://${host}:${port}`
  
  // HTTPS配置
  const sslCertFile = env.FRONTEND_SSL_CERT_FILE || env.SSL_CERT_FILE
  const sslKeyFile = env.FRONTEND_SSL_KEY_FILE || env.SSL_KEY_FILE
  
  console.log('Vite Config - SSL Cert:', sslCertFile)
  console.log('Vite Config - SSL Key:', sslKeyFile)
  
  // 检查 SSL 配置
  if (!sslCertFile || !sslKeyFile) {
    console.error('❌ ERROR: SSL certificates are required!')
    console.error('   Please configure SSL_CERT_FILE and SSL_KEY_FILE in .env')
    throw new Error('SSL certificates are required')
  }
  
  const backendProtocol = 'https'
  const apiBaseUrl = `${backendProtocol}://${backendHost}:${backendPort}`
  
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
  
  // 更新 manifest.trex 中的 URL
  updateManifestUrl(appUrl)
  
  return {
    plugins: [vue()],
    resolve: {
      alias: {
        '@': fileURLToPath(new URL('./src', import.meta.url))
      }
    },
    // 定义全局常量，注入到客户端代码
    define: {
      'import.meta.env.VITE_API_BASE_URL': JSON.stringify(apiBaseUrl)
    },
    server: {
      host,
      port,
      https: httpsConfig,
      proxy: {
        '/api': {
          target: `${backendProtocol}://${backendHost}:${backendPort}`,
          changeOrigin: true,
          secure: false, // 开发环境允许自签名证书
          rewrite: (path) => path.replace(/^\/api/, '')
        }
      }
    }
  }
})
