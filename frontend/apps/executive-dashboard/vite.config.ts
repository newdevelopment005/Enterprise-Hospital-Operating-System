import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    port: 5176,
    proxy: {
      // prediction-service (forecasts)
      '/api/v1/predictions': {
        target: 'http://localhost:8507',
        changeOrigin: true,
      },
      // ai-service (HospitalGPT) for AI insights
      '/api/v1/ai': {
        target: 'http://localhost:8506',
        changeOrigin: true,
      },
      // analytics-service (multi-department KPIs + locale)
      '/api/v1/analytics': {
        target: 'http://localhost:8508',
        changeOrigin: true,
      },
      // Keycloak token endpoint proxied same-origin (no CORS for token grants).
      '/auth': {
        target: 'http://localhost:8400',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/auth/, ''),
      },
    },
  },
})