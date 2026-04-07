import { defineConfig, loadEnv } from 'vite'
import react from '@vitejs/plugin-react'

// https://vite.dev/config/
export default defineConfig(({ mode }) => {
  // Load all vars (prefix='') from project root .env
  const env = loadEnv(mode, '../', '')

  return {
    plugins: [react()],
    envDir: '../',
    server: {
      proxy: {
        '/api': {
          target: env.BACKEND_URL || 'http://localhost:8000',
          changeOrigin: true,
        },
      },
    },
  }
})
