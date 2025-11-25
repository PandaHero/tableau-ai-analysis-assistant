import { fileURLToPath, URL } from 'node:url'
import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import fs from 'fs'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // 加载环境变量 - 从项目根目录加载
  const env = loadEnv(mode, '..', '')
  
  const host = env.VITE_APP_HOST || '127.0.0.1'
  const port = parseInt(env.VITE_APP_PORT || '5173')
  const backendHost = env.HOST || '127.0.0.1'
  const backendPort = env.PORT || '8000'
  
  // HTTPS配置 - 优先使用 FRONTEND_SSL_CERT_FILE
  const sslCertFile = env.FRONTEND_SSL_CERT_FILE || env.SSL_CERT_FILE
  const sslKeyFile = env.FRONTEND_SSL_KEY_FILE || env.SSL_KEY_FILE
  
  console.log('Vite Config - SSL Cert:', sslCertFile)
  console.log('Vite Config - SSL Key:', sslKeyFile)
  
  // 强制使用HTTPS（生产环境要求）
  if (!env.SSL_CERT_FILE || !env.SSL_KEY_FILE) {
    console.error('❌ ERROR: SSL certificates are required!')
    console.error('   Please configure SSL_CERT_FILE and SSL_KEY_FILE in .env')
    throw new Error('SSL certificates are required for production')
  }
  
  const backendProtocol = 'https'
  const apiBaseUrl = `${backendProtocol}://${backendHost}:${backendPort}`
  
  console.log('✓ HTTPS enforced')
  console.log('Vite Config - API Base URL:', apiBaseUrl)
  
  // 强制HTTPS配置（生产环境要求）
  if (!sslCertFile || !sslKeyFile) {
    console.error('❌ ERROR: Frontend SSL certificates are required!')
    console.error('   Please configure FRONTEND_SSL_CERT_FILE and FRONTEND_SSL_KEY_FILE in .env')
    throw new Error('Frontend SSL certificates are required for production')
  }
  
  // 尝试多个可能的路径
  const possibleCertPaths = [
    sslCertFile,
    `../${sslCertFile}`,
    `./${sslCertFile}`
  ]
  const possibleKeyPaths = [
    sslKeyFile,
    `../${sslKeyFile}`,
    `./${sslKeyFile}`
  ]
  
  let certPath = possibleCertPaths.find(p => fs.existsSync(p))
  let keyPath = possibleKeyPaths.find(p => fs.existsSync(p))
  
  if (!certPath || !keyPath) {
    console.error('❌ ERROR: SSL certificate files not found!')
    console.error('   Searched cert paths:', possibleCertPaths)
    console.error('   Searched key paths:', possibleKeyPaths)
    throw new Error('SSL certificate files not found')
  }
  
  const httpsConfig = {
    cert: fs.readFileSync(certPath),
    key: fs.readFileSync(keyPath)
  }
  
  console.log('🔒 前端HTTPS已启用（强制）')
  console.log('   证书路径:', certPath)
  console.log('   密钥路径:', keyPath)
  
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
