import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

export default defineConfig({
  plugins: [react()],
  server: {
    // Pin to IPv4: some browsers resolve `localhost` to 127.0.0.1 while Vite
    // otherwise binds ::1 only, which breaks the page / login silently.
    host: '127.0.0.1',
    port: 5175,
    strictPort: true,
    proxy: {
      '/api': {
        target: 'http://127.0.0.1:8506',
        changeOrigin: true,
      },
      // Keycloak token endpoint proxied same-origin (no CORS for the login form).
      '/auth': {
        target: 'http://127.0.0.1:8400',
        changeOrigin: true,
        rewrite: (path) => path.replace(/^\/auth/, ''),
      },
    },
  },
})