import { defineConfig, loadEnv } from 'vite'
import vue from '@vitejs/plugin-vue'
import pkg from './package.json'

export default defineConfig(({ mode }) => {
  const env = loadEnv(mode, '.', '')
  return {
    plugins: [vue()],
    define: {
      __APP_VERSION__: JSON.stringify(pkg.version),
    },
    worker: { format: 'es' },
    server: { proxy: { '/api': env.VITE_API_TARGET || 'http://127.0.0.1:8000' } },
  }
})
