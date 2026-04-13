import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load all vars (prefix='') from project root .env
  const env = loadEnv(mode, '../', '')

  const apiUrl = env.VITE_API_URL || '/api'
  const baseUrl = env.VITE_BASE_URL || '/'

  return {
    plugins: [react()],
    envDir: '../',
    base: baseUrl,
    server: {
      port: 5888,
      proxy: {
        [apiUrl]: {
          target: env.BACKEND_URL || 'http://localhost:19426',
          changeOrigin: true,
          rewrite: (path) => path.replace(new RegExp(`^${apiUrl}`), '/api'),
        },
      },
    },
  }
})
