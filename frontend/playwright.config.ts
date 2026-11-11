import { defineConfig } from '@playwright/test'

const python = process.env.WELLSPRING_TEST_PYTHON || (process.platform === 'win32'
  ? '../backend/.venv/Scripts/python.exe' : '../backend/.venv/bin/python')
const external = process.env.WELLSPRING_E2E_BASE_URL

export default defineConfig({
  testDir: './e2e',
  fullyParallel: false,
  workers: 1,
  timeout: 60000,
  retries: 0,
  reporter: 'list',
  use: { baseURL: external || 'http://127.0.0.1:4179', headless: true, trace: 'retain-on-failure' },
  webServer: external ? undefined : [
    { command: `"${python}" ../scripts/run_e2e_api.py`, url: 'http://127.0.0.1:8419/api/ready', timeout: 60000, reuseExistingServer: false },
    { command: 'npm run dev -- --port 4179 --strictPort', url: 'http://127.0.0.1:4179',
      env: { VITE_API_TARGET: 'http://127.0.0.1:8419' }, timeout: 60000, reuseExistingServer: false },
  ],
})
